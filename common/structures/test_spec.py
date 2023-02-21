from __future__ import annotations
from typing import Dict, List, Any
from enum import Enum
import json
import sys
import os

root_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if not root_path in sys.path:
    sys.path.append(root_path)

class signal_source(Enum):
    NOT_DEFINED = 0
    DBC = 1
    A2L = 2

class signal_direction(Enum):
    NOT_DEFINED = 0
    INPUT = 1
    OUTOUT = 2
    BOTH = 3

class signal_form(Enum):
    NOT_DEFINED = 0
    CONSTANT = 1
    PWM = 2
    LINE = 3
    PARABOLA = 4
    ROOT = 5
    HYPERBOLA = 6
    EXPONENTA = 7
    SINUS = 8   

#y = AMPLITUDE
class constant_coef(Enum):
    AMPLITUDE = 0

# if x <= DUTY_CYCLE * 1000 / FREQUENCY -> OFFSET + AMPLITUDE
# if x > DUTY_CYCLE * 1000 / FREQUENCY -> OFFSET
class pwm_coef(Enum):
    AMPLITUDE = 0
    OFFSET = 1
    FREQUENCY = 2  # Hz
    DUTY_CYCLE = 3  # %

# y = SLOPE * x + OFFSET
class line_coef(Enum):
    SLOPE = 0
    OFFSET = 1

# y = ax^2 + bx + c
class parabola_coef(Enum):
    A = 0
    B = 1
    C = 2

# y = ax^1/2 + b
class root_coef(Enum):
    A = 0
    B = 1

# y = a/x + b
class hyperbola_coef(Enum):
    A = 0
    B = 1

# y = ae^x + b
class exponenta_coef(Enum):
    A = 0
    B = 1

# y = a sin(2pi f + p)
class sinus_coef(Enum):
    A = 0
    F = 1
    P = 2

class step_type(Enum):
    NOT_DEFINED = 0
    COMMON = 1
    SPECIAL = 2

class special_step_action(Enum):
    NOT_DEFINED = 0
    REBOOT = 1
    RESET_POWER_SUPPLY = 2
    POWER_OFF = 3
    POWER_ON = 4
    GET_INFO = 5
    GET_PARAMETERS = 6
    UPDATE_PARAMETERS = 7
    UPDATE_FIRMWARE = 8
    GET_REPORT = 9
    GET_FRAM = 10

class signal:        
    def __init__(self, name: str, parent: str, source_type: signal_source, 
            source: str, direction: signal_direction, origin: Any = None) -> None:
        self.name: str = name
        self.parent: str = parent
        self.source_type: signal_source = source_type
        self.source: str = source
        self.direction: signal_direction = direction
        self.value: float = 0.0
        self.origin: Any = origin

    @staticmethod
    def create_from_spec(spec: Dict[str, Any]) -> signal:
        return signal(name=spec['name'], parent=spec['parent'], 
                source_type=signal_source(spec['source_type']), 
                source=spec['source'], 
                direction=signal_direction(spec['direction']))

    @staticmethod
    def check_signals_equality(signal1: signal, signal2: signal) -> bool:
        if signal1.name != signal2.name:
            return False
        if signal1.parent != signal2.parent:
            return False
        if signal1.source_type != signal2.source_type:
            return False
        if signal1.source != signal2.source:
            return False
        if signal1.direction != signal2.direction:
            return False
        if signal1.value != signal2.value:
            return False
        if signal1.origin != signal2.origin:
            return False
        return True
        
class control_signal:
    def __init__(self, signal: signal, form: signal_form, 
            coef: List[float]) -> None:
        self.signal: signal = signal
        self.form: signal_form = form
        self.coef: List[Any] = coef

    @staticmethod
    def create_from_spec(signal: signal, spec: Dict[str, Any]) -> control_signal:
        return control_signal(signal=signal, form=signal_form(spec['form']), 
                coef=spec['coef'])

    @staticmethod
    def check_signals_equality(signal1: control_signal, 
            signal2: control_signal) -> bool:
        if signal1.form != signal2.form:
            return False
        if len(signal1.coef) != len(signal2.coef):
            return False
        for index, coef in enumerate(signal1.coef):
            if coef != signal2.coef[index]:
                return False 
        return True

    def calculate_reference(self, timestamp_ms: float) -> float:
        ret_val = None
        if self.form == signal_form.CONSTANT:
            ret_val = self.coef[constant_coef.AMPLITUDE.value]
        elif self.form == signal_form.PWM:
            raise Exception('Not implemented')
        elif self.form == signal_form.LINE:
            ret_val = self.coef[line_coef.SLOPE.value] * timestamp_ms / 1000
            ret_val += self.coef[line_coef.OFFSET.value]
        elif self.form == signal_form.PARABOLA:
            raise Exception('Not implemented')
        elif self.form == signal_form.ROOT:
            raise Exception('Not implemented')
        elif self.form == signal_form.HYPERBOLA:
            raise Exception('Not implemented')
        elif self.form == signal_form.EXPONENTA:
            raise Exception('Not implemented')
        elif self.form == signal_form.SINUS:
            raise Exception('Not implemented')
        return ret_val

    def to_dict(self) -> Dict[str, Any]:
        ret_val: Dict[str, Any] = {}
        ret_val['form'] = self.form.value
        ret_val['coef'] = self.coef
        return ret_val 
        
class monitored_range:
    def __init__(self, start_ms: float, stop_ms: float, tolerance: float) -> None:
        self.start_ms: float = start_ms
        self.stop_ms: float = stop_ms
        self.tolerance: float = tolerance

    @staticmethod
    def create_from_spec(spec: Dict[str, float]) -> monitored_range:
        return monitored_range(start_ms=spec['start_ms'], stop_ms=spec['stop_ms'], 
                tolerance=spec['tolerance'])

    @staticmethod
    def check_ranges_equality(range1: monitored_range, 
            range2: monitored_range) -> bool:
        if range1.start_ms != range2.start_ms:
            return False
        if range1.stop_ms != range2.stop_ms:
            return False
        if range1.tolerance != range2.tolerance:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        ret_val: Dict[str, Any] = {}
        ret_val['start_ms'] = self.start_ms
        ret_val['stop_ms'] = self.stop_ms
        ret_val['tolerance'] = self.tolerance
        return ret_val

class monitored_signal:
    def __init__(self, signal: signal, ranges: List[monitored_range], 
            form: signal_form, coef: List[float]) -> None:
        self.signal: signal = signal
        self.ranges: List[monitored_range] = ranges
        self.form: signal_form = form
        self.coef: List[float] = coef

    @staticmethod
    def create_from_spec(signal: signal, 
            spec: Dict[str, float]) -> monitored_signal:
        return monitored_signal(signal=signal, 
                ranges=monitored_signal.__prepare_monitored_ranges(
                        spec=spec['monitored_ranges']),
                form=signal_form(spec['form']), coef=spec['coef'])

    @staticmethod
    def check_signals_equality(signal1: monitored_signal, 
            signal2: monitored_signal) -> bool:
        if len(signal1.ranges) != len(signal2.ranges):
            return False
        for index in enumerate(signal1.ranges):
            if monitored_range.check_ranges_equality(range1=signal1.ranges[index], 
                    range2=signal2.ranges[index]):
                return False 
        if signal1.form != signal2.form:
            return False
        if len(signal1.coef) != len(signal2.coef):
            return False
        for index, coef in enumerate(signal1.coef):
            if coef != signal2.coef[index]:
                return False 
        return True

    @staticmethod
    def __prepare_monitored_ranges(
            spec: List[Dict[str, float]]) -> List[monitored_range]:
        monitored_ranges: List[monitored_range] = []
        for range_spec in spec:
            monitored_ranges.append(monitored_range(
                    start_ms=range_spec['start_ms'],
                    stop_ms=range_spec['stop_ms'], 
                    tolerance=range_spec['tolerance']))
        return monitored_ranges

    def calculate_estimation(self, timestamp_ms: float) -> float:
        ret_val = None
        if self.form == signal_form.CONSTANT:
            ret_val = self.coef[constant_coef.AMPLITUDE.value]
        elif self.form == signal_form.PWM:
            raise Exception('Not implemented')
        elif self.form == signal_form.LINE:
            ret_val = self.coef[line_coef.SLOPE.value] * timestamp_ms / 1000
            ret_val += self.coef[line_coef.OFFSET.value]
        elif self.form == signal_form.PARABOLA:
            raise Exception('Not implemented')
        elif self.form == signal_form.ROOT:
            raise Exception('Not implemented')
        elif self.form == signal_form.HYPERBOLA:
            raise Exception('Not implemented')
        elif self.form == signal_form.EXPONENTA:
            raise Exception('Not implemented')
        elif self.form == signal_form.SINUS:
            raise Exception('Not implemented')
        return ret_val

    def to_dict(self) -> Dict[str, Any]:
        ret_val: Dict[str, Any] = {}
        ret_val['monitored_ranges'] = []
        for range in self.ranges:
            ret_val['monitored_ranges'].append(range.to_dict())
        ret_val['form'] = self.form.value
        ret_val['coef'] = self.coef
        return ret_val

class logged_signal:
    def __init__(self, signal: signal) -> None:
        self.signal = signal

    @staticmethod
    def create_from_spec(signal: signal, spec: Dict[str, float]) -> logged_signal:
        return logged_signal(signal=signal)

    def to_dict(self) -> Dict[str, Any]:
        ret_val: Dict[str, Any] = {}
        return ret_val

class step:
    def __init__(self, test_spec: test_spec, type: step_type, action: str, 
            duration_ms: float, monitored_signals: Dict[str, monitored_signal], 
            logged_signals: Dict[str, logged_signal]) -> None:
        self.test_spec: test_spec = test_spec
        self.type: step_type = type
        self.action: str = action
        self.duration_ms: float = duration_ms
        self.monitored_signals: Dict[str, monitored_signal] = monitored_signals
        self.logged_signals: Dict[str, logged_signal] = logged_signals

    @staticmethod
    def create_from_spec(test_spec: test_spec, spec: Dict[str, Any], 
            signals: Dict[str, signal]) -> step:
        monitored_signals: Dict[str, monitored_signal] = {}
        if 'monitored_signals' in spec:
            monitored_signals = step.__prepare_monitored_signals(
                    spec=spec['monitored_signals'], signals=signals)
        logged_signals: Dict[str, logged_signal] = {}
        if 'logged_signals' in spec:
            logged_signals = step.__prepare_logged_signals(
                    spec=spec['logged_signals'], signals=signals)
        return step(test_spec=test_spec, type=step_type(spec['type']),
                action=spec['action'], duration_ms=spec['duration_ms'], 
                monitored_signals=monitored_signals, 
                logged_signals=logged_signals)
        
    @staticmethod
    def __prepare_monitored_signals(spec: List[Dict[str, Any]], 
            signals: Dict[str, signal]) -> Dict[str, monitored_signal]:
        monitored_signals: Dict[str, monitored_signal] = {}
        for signal_spec in spec:
            if not signal_spec in signals:
                raise Exception('Signal is missing in the input files')
            monitored_signals[signal_spec] = monitored_signal.create_from_spec(
                    signal=signals[signal_spec], spec=spec[signal_spec])
        return monitored_signals

    @staticmethod
    def __prepare_logged_signals(spec: List[Dict[str, Any]], 
            signals: Dict[str, signal]) -> Dict[str, logged_signal]:
        logged_signals: Dict[str, logged_signal] = {}
        for signal_spec in spec:
            if not signal_spec in signals:
                raise Exception('Signal is missing in the input files')
            logged_signals[signal_spec] = logged_signal.create_from_spec(
                    signal=signals[signal_spec], spec=spec[signal_spec])
        return logged_signals

    def to_dict(self) -> Dict[str, Any]:
        ret_val: Dict[str, Any] = {}
        ret_val['type'] = self.type.value
        ret_val['action'] = self.action
        ret_val['duration_ms'] = self.duration_ms
        ret_val['monitored_signals'] = {}
        for signal in self.monitored_signals:
            ret_val['monitored_signals'][signal] = self.monitored_signals[
                    signal].to_dict()
        ret_val['logged_signals'] = {}
        for signal in self.logged_signals:
            ret_val['logged_signals'][signal] = self.logged_signals[
                    signal].to_dict()
        return ret_val

class common_step(step):
    def __init__(self, test_spec: test_spec, action: str, duration_ms: float, 
            monitored_signals: Dict[str, monitored_signal], 
            logged_signals: Dict[str, logged_signal], 
            control_signals: Dict[str, control_signal]) -> None:
        super().__init__(test_spec=test_spec, type=step_type.COMMON, 
                action=action, duration_ms=duration_ms, 
                monitored_signals=monitored_signals, 
                logged_signals=logged_signals)
        self.control_signals: Dict[str, control_signal] = control_signals

    @staticmethod
    def create_from_spec(test_spec: test_spec, spec: Dict[str, Any], 
            signals: Dict[str, signal]) -> common_step:
        ret_val: common_step = step.create_from_spec(test_spec=test_spec, 
                spec=spec, signals=signals)
        ret_val.control_signals: Dict[str, control_signal] = \
                common_step.__prepare_control_signals(spec=spec['control_signals'], 
                        signals=signals)
        return ret_val

    @staticmethod
    def create_empty() -> common_step:
        ret_val: common_step = common_step(test_spec=None, action='', 
                duration_ms=0, monitored_signals={}, logged_signals={}, 
                control_signals={})
        return ret_val

    @staticmethod
    def __prepare_control_signals(spec: List[Dict[str, Any]], 
            signals: Dict[str, signal]) -> Dict[str, control_signal]:
        control_signals: Dict[str, control_signal] = {}
        for signal_spec in spec:
            if not signal_spec in signals:
                raise Exception('Signal is missing in the input files')
            control_signals[signal_spec] = control_signal.create_from_spec(
                    signal=signals[signal_spec], spec=spec[signal_spec])
        return control_signals

    def to_dict(self) -> Dict[str, Any]:
        ret_val: Dict[str, Any] = step.to_dict(self=self)
        ret_val['control_signals'] = {}
        for signal in self.control_signals:
            ret_val['control_signals'][signal] = self.control_signals[
                    signal].to_dict()
        return ret_val
        
class special_step(step):
    def __init__(self, test_spec: test_spec, action: str, duration_ms: float, 
            monitored_signals: Dict[str, monitored_signal], 
            logged_signals: List[logged_signal], step_action: special_step_action, 
            action_details: Any) -> None:
        super().__init__(test_spec=test_spec, type=step_type.SPECIAL, 
                action=action, duration_ms=duration_ms, 
                monitored_signals=monitored_signals, 
                logged_signals=logged_signals)
        self.step_action: special_step_action = step_action
        self.action_details: Any = action_details

    @staticmethod
    def create_from_spec(test_spec: test_spec, 
            spec: Dict[str, Any], signals: Dict[str, signal]) -> special_step:
        ret_val: special_step = step.create_from_spec(test_spec=test_spec, 
                spec=spec, signals=signals)
        ret_val.step_action: special_step_action = special_step_action(
                spec['step_action'])
        ret_val.action_details: Any = spec['action_details']
        return ret_val

    def to_dict(self) -> Dict[str, Any]:
        ret_val: Dict[str, Any] = step.to_dict(self=self)
        ret_val['step_action'] = self.step_action.value
        ret_val['action_details'] = self.action_details
        return ret_val

class test_spec:
    def __init__(self, name: str, dscr: str, initial_state: common_step, 
            steps: List[step], used_signals: List[str], 
            xray_id: str = None) -> None:
        self.name: str = name
        self.dscr: str = dscr
        self.initial_state: common_step = initial_state
        self.steps: List[step] = steps
        self.xray_id: str = xray_id
        if xray_id == None:
            self.xray_id: str = test_spec.__define_xray_id(name)
        self.used_signals: List[str] = used_signals

    @staticmethod
    def __prepare_steps(test_spec: test_spec, spec: List[Any], 
            signals: Dict[str, signal]) -> List[step]:
        ret_val: List[step] = []
        for step_spec in spec:
            if step_type(step_spec['type']) == step_type.COMMON:
                ret_val.append(common_step.create_from_spec(test_spec=test_spec, 
                        spec=step_spec, signals=signals))
            elif step_type(step_spec['type']) == step_type.SPECIAL:
                ret_val.append(special_step.create_from_spec(test_spec=test_spec, 
                        spec=step_spec, signals=signals))
            else:
                raise Exception(f'Type {step_spec["type"]} is not implemented')
        return ret_val

    @staticmethod
    def __define_xray_id(name: str) -> str:
        raise Exception('Definition of the test XRAY ID is not implemented yet')

    @staticmethod
    def create_from_spec(spec: Dict[str, Any], 
            signals: Dict[str, signal]) -> test_spec:
        xray_id: str = None
        if 'xray_id' in spec:
            xray_id: str = spec['xray_id']
        ret_val: test_spec = test_spec(name=spec['name'], dscr=spec['dscr'], 
                initial_state=None, steps=None, used_signals=spec['used_signals'], 
                xray_id=xray_id)
        ret_val.initial_state = common_step.create_from_spec(test_spec=ret_val,
                spec=spec['initial_state'], signals=signals)
        ret_val.steps = test_spec.__prepare_steps(test_spec=ret_val, 
                spec=spec['steps'], signals=signals)
        return ret_val
        
    @staticmethod
    def create_empty() -> test_spec:
        ret_val: test_spec = test_spec(name='', dscr='', used_signals=[],
                initial_state=common_step.create_empty(), steps=[], xray_id='')
        return ret_val

    def __prepare_list_of_used_signals(self) -> List[str]:
        ret_val: List[str] = []
        for signal in self.initial_state.control_signals:
            if not signal in ret_val:
                ret_val.append(signal)
        for signal in self.initial_state.monitored_signals:
            if not signal in ret_val:
                ret_val.append(signal)
        for signal in self.initial_state.logged_signals:
            if not signal in ret_val:
                ret_val.append(signal)
        for step in self.steps:
            if step.type == step_type.COMMON:
                for signal in step.control_signals:
                    if not signal in ret_val:
                        ret_val.append(signal)
            for signal in step.monitored_signals:
                if not signal in ret_val:
                    ret_val.append(signal)
            for signal in step.logged_signals:
                if not signal in ret_val:
                    ret_val.append(signal)
        return ret_val

    def to_dict(self) -> Dict[str, Any]:
        ret_val: Dict[str, Any] = {}
        ret_val['name'] = self.name
        ret_val['dscr'] = self.dscr
        ret_val['xray_id'] = self.xray_id
        ret_val['initial_state'] = common_step.to_dict(self=self.initial_state)
        ret_val['steps'] = []
        for step in self.steps:
            if step.type == step_type.COMMON:
                ret_val['steps'].append(common_step.to_dict(self=step))
            elif step.type == step_type.SPECIAL:
                ret_val['steps'].append(special_step.to_dict(self=step))
        ret_val['used_signals'] = self.__prepare_list_of_used_signals()
        return ret_val

    def to_json(self) -> json:
        return json.dumps(self.to_dict(), indent=4)