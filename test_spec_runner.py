from typing import Any, List, Dict
from datetime import datetime
import multiprocessing
import threading
import argparse
import asyncio
import time
import json
import os

from common.adapters.adapter import adapter, adapter_type
from common.adapters.adapter import can_worker_adapter
from common.adapters.comm_adapter import comm_adapter
from common.adapters.dut_adapter import dut_adapter
from common.structures.a2l_file import a2l_file
from common.structures.dbc_file import dbc_file, dbc_message
from common.structures.test_spec import (test_spec, step, step_type, common_step,
        special_step, special_step_action, signal, signal_source)
from common.tools.type_conversion import str_to_type
from common.tools.files import get_file

finish_event = threading.Event()
error_event = threading.Event()
new_step_event = threading.Event()
feedbacks_queue = multiprocessing.Queue()
faults_queue = multiprocessing.Queue()

dbc_messages: Dict[str, dbc_message] = {}
signals: Dict[str, signal] = {}
logged_data: Dict[str, str] = {}
a2l_signals: Dict[str, str] = {}
active_sending_tasks: List[str] = []
reading_task_filters: List[Dict[str, Any]] = {}
reading_task_dbc_to_can_map: List[Dict[str, Any]] = {}

def prepare_caption(data_dict: dict) -> str:
    caption: str = 'timestamp,'
    for field in data_dict:
        caption += f'{field},'
    return f'{caption}\n'

def prepare_data(data_dict: dict) -> str:
    data: str = f'{datetime.now().time().isoformat()},'
    for field in data_dict:
        data += f'{data_dict[field]},'
    return f'{data}\n'   

def process_message(step: step, message: Dict[str, Any], step_timestamp_ns: int):
    global logged_data
    message_name = message[4]['message_name']
    for signal in message[4]['signals']:
        signal_name = f'{message_name}_{signal}'
        if signal_name in step.logged_signals:
            logged_data[signal_name] = message[4]['signals'][signal]
        if signal_name in step.monitored_signals:
            monitored_signal = step.monitored_signals[signal_name]
            range_index = None
            time_from_start = (time.time_ns() - step_timestamp_ns) / 1000000
            for index, range in enumerate(monitored_signal.ranges):
                if (time_from_start >= range.start_ms and 
                        time_from_start <= range.stop_ms):
                    range_index = index
                    break
            if not range_index is None:
                expected = monitored_signal.calculate_estimation(
                        timestamp_ms=time_from_start)
                real = message[4]['signals'][signal]
                tolerance = monitored_signal.ranges[range_index].tolerance
                base = tolerance / 100 * abs(expected)
                if base == 0:
                    base = tolerance
                if abs(expected - real) > base:
                    faults_queue.put_nowait(f'ERROR - the signal {signal_name} ' + 
                        f'is out of the expected range {expected} ± {tolerance}%; ' + 
                        f'measured value: {real}; range index: {range_index}; ' + 
                        f'time from start: {time_from_start}\n')

def monitoring_thread_handle(spec: test_spec, log_path: str):
    global logged_data
    log_file_name = f'{spec.xray_id}.csv'
    log_file = open(f'{log_path}/{log_file_name}', 'w')
    step_cntr = 0
    current_step = spec.initial_state
    step_timestamp_ns = time.time_ns()
    while True:
        while not feedbacks_queue.empty():
            messages = feedbacks_queue.get()
            for message in messages:
                if len(message[4]) > 0:
                    process_message(step=current_step, message=message, 
                            step_timestamp_ns=step_timestamp_ns)
            log_file.write(f'{prepare_data(logged_data)}')

        if new_step_event.wait(0.001) == True:
            new_step_event.clear()
            step_timestamp_ns = time.time_ns()
            if step_cntr < len(spec.steps):
                current_step = spec.steps[step_cntr]
            step_cntr += 1
        if error_event.wait(0.001) == True:
            break
        if finish_event.wait(0.001) == True:
            break

    log_file.close()
    with open(f'{log_path}/{log_file_name}', 'r+') as log_file:
        content = log_file.read()
        log_file.seek(0, 0)
        log_file.write(prepare_caption(logged_data) + content)

def read_feedbacks(messages: list) -> None:
    feedbacks_queue.put(messages)

async def perform_special_step(adapter: adapter, dut: dut_adapter, 
        step: special_step, log_file: Any, e2e_protection: bool = False, 
        e2e_gateway: dut_adapter = None) -> None:
    if step.step_action == special_step_action.REBOOT:
        await dut.reboot()
        await configure_reading_task(adapter=adapter, dut=dut)
    elif step.step_action == special_step_action.POWER_OFF:
        await dut.power_off()
    elif step.step_action == special_step_action.POWER_ON:
        await dut.power_on()
    elif step.step_action == special_step_action.GET_INFO:
        log_file.write(f'{dut.dut_info.print()}\n')
    elif step.step_action == special_step_action.GET_PARAMETERS:
        log_file.write(json.dumps(await dut.get_parameters()))
    elif step.step_action == special_step_action.UPDATE_PARAMETERS:
        await dut.update_parameters(parameters=step.action_details)
    elif step.step_action == special_step_action.GET_FRAM:
        await dut.read_fram()
    else:
        raise Exception(f'{step.step_action} is not implemented yet')

async def perform_common_step(adapter: adapter, dut: dut_adapter, 
        step: common_step, log_file: Any, e2e_protection: bool = False, 
        e2e_gateway: dut_adapter = None) -> None:
    global active_sending_tasks
    dbc_signals = {}
    for signal in step.control_signals:
        control_signal = step.control_signals[signal]
        value = control_signal.calculate_reference(timestamp_ms=0.0)
        if control_signal.signal.source_type == signal_source.DBC:
            if not control_signal.signal.parent in dbc_signals:
                dbc_signals[control_signal.signal.parent] = {}
            dbc_signals[control_signal.signal.parent][
                control_signal.signal.name] = value
        elif control_signal.signal.source_type == signal_source.A2L:
            await dut.calibrate_signal(definition=control_signal.signal.origin, 
                    value=value)
        else:
            raise Exception(f'{control_signal.signal.source} is not supported')
    for message in dbc_signals:
        signals = dbc_signals[message]
        can = dut.dut_info.can
        da = dut.dut_info.j1939_sa
        if not e2e_gateway is None:
            can = e2e_gateway.dut_info.can
            da = e2e_gateway.dut_info.j1939_sa
        sending_task = can_worker_adapter.sending_task(
                message=dbc_messages[message], can=can, sa='FE', da=da)
        id = await dut.start_sending_task(task=sending_task, signals=signals, 
                e2e_protection=e2e_protection)
        if not id in active_sending_tasks:
            active_sending_tasks.append(id)

async def perform_step(adapter: adapter, dut: dut_adapter, step: step, 
        log_file: Any, step_number: int, e2e_protection: bool = False, 
        e2e_gateway: dut_adapter = None) -> bool:
    step_status = True
    action = step.action
    log_file.write(f'Step {step_number}: {step.action}\n')
    step_action = None
    if step.type == step_type.COMMON:
        step_action = perform_common_step
    elif step.type == step_type.SPECIAL:
        step_action = perform_special_step
    else:
        raise Exception(f'Test type ({step.type}) is not supported')
    asyncio.gather(
        await step_action(adapter=adapter, dut=dut, step=step, log_file=log_file, 
                e2e_protection=e2e_protection, e2e_gateway=e2e_gateway),
        await asyncio.sleep(step.duration_ms / 1000)
    )    
    while not faults_queue.empty():
        step_status = False
        log_file.write(faults_queue.get())
    log_file.write(f'Step status: {step_status}\n')
    return step_status

async def set_initial_state(adapter: adapter, dut: dut_adapter, 
        initial_state: common_step, log_file: Any, e2e_protection: bool = False,
        e2e_gateway: dut_adapter = None) -> None:
    tasks: List[Dict[str, str]] = await adapter.get_sending_tasks()
    tasks_to_stop: List[str] = []
    for task in tasks:
        if 'da' in task and task['da'] == dut.dut_info.j1939_sa:
            tasks_to_stop.append(task['id'])
        if not e2e_gateway is None:
            if 'da' in task and task['da'] == e2e_gateway.dut_info.j1939_sa:
                tasks_to_stop.append(task['id'])
    if len(tasks_to_stop) > 0:
        await adapter.stop_sending_tasks(sending_tasks_ids=tasks_to_stop)
    await dut.reboot()
    await perform_step(adapter=adapter, dut=dut, step=initial_state, 
            log_file=log_file, step_number=0, e2e_protection=e2e_protection, 
            e2e_gateway=e2e_gateway)  

async def configure_reading_task(adapter: adapter, dut: dut_adapter, 
        dbc_paths: List[str] = None, first_call: bool = False) -> None:
    if first_call:
        for dbc_path in dbc_paths:
            await adapter.upload_dbc(dbc_path=dbc_path) 
        global reading_task_filters
        global reading_task_dbc_to_can_map
        reading_task_filters = dut.prepare_reading_filter(dbc_files=dbc_paths)
        reading_task_dbc_to_can_map = dut.prepare_dbc_to_can_map(
                dbc_files=dbc_paths)
    await adapter.start_read_can_messages(callback=read_feedbacks, interval_ms=100, 
            filters=reading_task_filters, dbc_to_can=reading_task_dbc_to_can_map)

async def test_scenario_thread_handle(adapter: adapter, dut: dut_adapter, 
        spec: test_spec, dbc_paths: str, log_path: str, 
        e2e_protection: bool = False, e2e_gateway: dut_adapter = None) -> None:
    test_status = True
    async with adapter:
        async with dut:
            if not e2e_gateway is None:
                await e2e_gateway.set_connection()
            if not os.path.exists(log_path):
                os.mkdir(log_path)
            log_file = open(f'{log_path}/{spec.xray_id}.log', 'w')
            log_file.write(f'Test ID: {spec.xray_id}\n')
            log_file.write(f'Test name: {spec.name}\n')
            log_file.write(f'Test description: {spec.dscr}\n')
            log_file.write(f'\nDUT info: {dut.dut_info.print()}\n\n')
            
            await set_initial_state(adapter=adapter, dut=dut, 
                    initial_state=spec.initial_state, log_file=log_file, 
                    e2e_protection=e2e_protection, e2e_gateway=e2e_gateway)
            new_step_event.set()
            await configure_reading_task(adapter=adapter, dut=dut, 
                    dbc_paths=dbc_paths, first_call=True)
            
            for index, step in enumerate(spec.steps):
                if not await perform_step(adapter=adapter, dut=dut, step=step, 
                        log_file=log_file, step_number=(index + 1), 
                        e2e_protection=e2e_protection, e2e_gateway=e2e_gateway):
                    test_status = False
                new_step_event.set()

            log_file.write(f'\nTest status: {test_status}\n')
            log_file.close()
            finish_event.set()
            await dut.stop_sending_tasks(ids=active_sending_tasks)

def start_test_scenario_thread(adapter: adapter, dut: dut_adapter, spec: test_spec,
        dbc_paths: List[str], log_path: str, e2e_protection: bool = False, 
        e2e_gateway: dut_adapter = None) -> None:
    asyncio.run(test_scenario_thread_handle(adapter=adapter, dut=dut, spec=spec, 
            dbc_paths=dbc_paths, log_path=log_path, e2e_protection=e2e_protection, 
            e2e_gateway=e2e_gateway))

def run_test_spec(args: argparse.Namespace) -> None:
    global dbc_messages
    a2l: a2l_file = None
    dbcs: List[dbc_file] = []
    dbc_paths: List[str] = []
    try:
        a2l_path = get_file(file_path=args.a2l_file)
        a2l = a2l_file(a2l_file_path=a2l_path)
        paths = args.dbc_files.split(',')
        for path in paths:
            dbc_path = get_file(file_path=path)
            dbc_paths.append(dbc_path)
            file = dbc_file(dbc_file_path=dbc_path)
            dbcs.append(file)
            dbc_messages = {**dbc_messages, **file.dbc_messages}
    except:
        raise Exception(f'Failed to parse the input files')

    global signals
    spec: test_spec = None
    try:
        spec_path = get_file(file_path=args.test_spec)
        with open(spec_path, 'r', encoding='utf-8') as file:
            spec_json = json.loads(file.read())
        for signal_name in spec_json['used_signals']:
            signal = None
            if signal_name.startswith('a2l_'):
                signal = a2l.find_signal_from_spec(signal_name=signal_name)
            else:
                for dbc in dbcs:
                    signal = dbc.find_signal_from_spec(signal_name=signal_name)
                    if not signal is None:
                        break
            if signal is None:
                raise Exception(f'Failed to find the signal {signal_name}')
            signals[signal_name] = signal.convert_to_test_spec_signal()
        spec = test_spec.create_from_spec(spec=spec_json, signals=signals)
    except:
        raise Exception(f'Failed to parse the test spec {args.test_spec}')

    adapter = None
    try:
        if args.adapter == adapter_type.COMM.value:
            adapter = comm_adapter(ip=args.adapter_path)
        elif args.adapter == adapter_type.DTLv01.value:
            raise Exception('DTLv01 is not supported')
        elif args.adapter == adapter_type.DTLv02.value:
            raise Exception('DTLv02 is not supported')
        elif args.adapter == adapter_type.CanFlasher.value:
            raise Exception('CanFlasher is not supported')
        elif args.adapter == adapter_type.EDIC.value:
            raise Exception('EDIC is not supported')
        elif args.adapter == adapter_type.PCAN.value:
            raise Exception('PCAN is not supported')
        elif args.adapter == adapter_type.VECTOR.value:
            raise Exception('Vector is not supported')
    except:
        raise Exception(f'Failed to connect to the adapter')

    dut = None
    try:
        dut = dut_adapter(serial_number=args.serial, adapter=adapter)
    except:
        raise Exception(f'Failed to connect to the DUT')

    e2e_protection = str_to_type(value=args.e2e_protection, type='bool')

    e2e_gateway = None
    if not args.e2e_gateway is None:
        try:
            e2e_gateway = dut_adapter(serial_number=args.e2e_gateway, 
                    adapter=adapter)
        except:
            raise Exception(f'Failed to connect to the E2E gateway')

    try:
        test_scenario_thread = threading.Thread(target=start_test_scenario_thread, 
                args=[adapter, dut, spec, dbc_paths, args.log_path, e2e_protection, 
                        e2e_gateway])
        monitoring_thread = threading.Thread(target=monitoring_thread_handle, 
                args=[spec, args.log_path])
        test_scenario_thread.start()
        monitoring_thread.start()
    except:
        raise Exception('Failed to start runner\'s threads')

    status: bool = False
    while True:
        if finish_event.wait(0.1) == True:
            status = True
            break
        if error_event.wait(0.1) == True:
            status = False
            break
    if test_scenario_thread.is_alive():
        test_scenario_thread.join()
    if monitoring_thread.is_alive():
        monitoring_thread.join()
    finish_event.clear()
    error_event.clear()
    if status == False:
        raise Exception('PIL framework error occurred')