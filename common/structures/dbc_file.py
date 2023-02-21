from __future__ import annotations
from typing import Dict, Any, List
from enum import Enum
import sys
import os

root_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if not root_path in sys.path:
    sys.path.append(root_path)

from common.structures.test_spec import signal, signal_source, signal_direction
from common.tools.crc8 import crc8

class dbc_message_type(Enum):
    NOT_DEFINED = None
    UNUSED = 'PpCcUnused'
    INPUT = 'PpCcInput'
    OUTPUT = 'PpCcOutput'
    HEALTH = 'PpCcHealth'

class dbc_signal:
    def __init__(self, name: str, position: int, length: int, factor: float, 
            offset: float, min: float, max: float, unit: str, dscr: str, 
            signal_type: str, start_value: float, values: Dict[int, str], 
            parent: str, source: str, message_type: dbc_message_type) -> None:
        self.name: str = name
        self.position: int = position
        self.length: int = length
        self.factor: float = factor
        self.offset: float = offset
        self.min: float = min
        self.max: float = max
        self.unit: str = unit
        self.dscr: str = dscr
        self.signal_type: str = signal_type
        self.start_value: float = start_value
        self.values: Dict[int, str] = values
        self.parent: str = parent
        self.source: str = source
        self.message_type: dbc_message_type = message_type

    @staticmethod
    def create_from_spec(spec: Dict[str, Any], parent: str, source: str, 
            message_type: dbc_message_type) -> dbc_signal:
        signal_type = None
        if 'signal_type' in spec:
            signal_type = spec['signal_type']
        start_value = None
        if 'start_value' in spec:
            start_value = spec['start_value']
        values = None
        if 'values' in spec:
            values = spec['values']
        description = ''
        if 'description' in spec:
            description = spec['description']
        return dbc_signal(name=spec['name'], position=spec['position'], 
                length=spec['length'], factor=spec['factor'], 
                offset=spec['offset'], min=spec['min'], max=spec['max'], 
                unit=spec['unit'], dscr=description, signal_type=signal_type, 
                start_value=start_value, values=values, parent=parent, 
                source=source, message_type=message_type)    

    def convert_to_test_spec_signal(self) -> signal:
        direction = signal_direction.OUTOUT
        if self.message_type == dbc_message_type.INPUT:
            direction = signal_direction.BOTH
        return signal(name=self.name, parent=self.parent, 
                source_type=signal_source.DBC, source=self.source, 
                direction=direction, origin=self)

class dbc_message:
    def __init__(self, name: str, id: str, length: str, 
            signals: Dict[str, dbc_signal], dscr: str, 
            message_type: dbc_message_type, period_ms: int, frame_format: str, 
            source: str) -> None:
        self.name: str = name
        self.id: str = id
        self.length: str = length
        self.signals: Dict[str, dbc_signal] = signals
        self.dscr: str = dscr
        self.message_type: dbc_message_type = message_type
        self.period_ms: int = period_ms
        self.frame_format: str = frame_format
        self.source: str = source    

    @staticmethod
    def __prepare_dict_of_signals(signals: Dict[str, Dict[str, Any]], 
            parent: str, source: str, 
            message_type: dbc_message_type) -> Dict[str, dbc_signal]:
        dbc_signals: Dict[str, dbc_signal] = {}
        for signal in signals:
            dbc_signals[signal] = dbc_signal.create_from_spec(
                    spec=signals[signal], parent=parent, source=source, 
                    message_type=message_type)
        return dbc_signals

    def __e2e_protection_crc(self, data: int, data_len: int, data_id: int) -> int:
        crc = 0x00 ^ 0xFF
        crc = crc8(data_id & 0xFF, 1, crc)
        crc = crc8((data_id >> 8) & 0xFF, 1, crc)
        crc = crc8(data, data_len, crc)
        crc = crc ^ 0xFF
        return crc

    @staticmethod
    def reverse_bytes(input: int, length: int) -> int:
        ret_val: int = 0x00
        tmp_list: List[int] = []
        for index in range(length):
            tmp_list.append((input >> index * 8) & 0xFF)
        tmp_list.reverse()
        for index in range(length):
            ret_val |= (tmp_list[index] << index * 8)
        return ret_val

    @staticmethod
    def create_from_spec(spec: Dict[str, Any], source: str) -> dbc_message:
        message_type = dbc_message_type.NOT_DEFINED
        if 'message_type' in spec:
            message_type = dbc_message_type(spec['message_type'])
        period_ms = None
        if 'period_ms' in spec:
            period_ms = spec['period_ms']
        frame_format = None
        if 'frame_format' in spec:
            frame_format = spec['frame_format']
        signals = dbc_message.__prepare_dict_of_signals(signals=spec['signals'], 
                parent=spec['name'], source=source, message_type=message_type)
        return dbc_message(name=spec['name'], id=hex(int(spec['id'])), 
                length=spec['length'], signals=signals, dscr=spec['description'], 
                message_type=message_type, period_ms=period_ms, 
                frame_format=frame_format, source=source)  

    def prepare_data(self, signals: Dict[str, int], e2e_protection: bool = False,
            data_id: int = 0, cntr: int = 0) -> str:
        ret_val = 0xFFFFFFFFFFFFFFFF
        for signal in self.signals:
            signal_dscr = self.signals[signal]
            ret_val &= ~((pow(2, int(signal_dscr.length)) - 1) << 
                    int(signal_dscr.position))
        for signal in signals:
            if signal in self.signals:
                signal_dscr = self.signals[signal]
                if (signals[signal] > float(signal_dscr.max) or 
                        signals[signal] < float(signal_dscr.min)):
                    raise Exception('Signal value is out of the valid range')
                value = int(float(signals[signal]) / float(signal_dscr.factor))
                if not signal_dscr.start_value is None:
                    value = int(signal_dscr.start_value) + value 
                ret_val |= (value << int(signal_dscr.position))
            else:
                raise Exception('Worng signal name')
        if e2e_protection:
            cntr_signal = [s for s in self.signals if s.endswith('_CNT')]
            if len(cntr_signal) > 0:
                cntr_signal = self.signals[cntr_signal[0]]
                ret_val |= ((cntr & 0x0F) << int(cntr_signal.position))
            else:
                raise Exception('E2E counter signal is missing')
            crc_signal = [s for s in self.signals if s.endswith('_CRC')]
            if len(crc_signal) > 0:
                crc_signal = self.signals[crc_signal[0]]
                crc = self.__e2e_protection_crc(data=ret_val, 
                        data_len=int(self.length) - 1, data_id=data_id)
                ret_val |= ((crc & 0xFF) << int(crc_signal.position))
            else:
                raise Exception('E2E CRC signal is missing')
        #return hex(dbc_message.__reverse_bytes(input=ret_val, length=8))[2:]
        return "{:016x}".format(dbc_message.reverse_bytes(input=ret_val, length=8))

class dbc_file:
    def __init__(self, dbc_file_path: str) -> None:
        self.dbc_file_path = dbc_file_path
        from common.parsers.dbc_parser import dbc_parser
        self.dbc_messages = dbc_parser.parse_dbc_messages(
                dbc_file_path=dbc_file_path)

    def find_signal_from_spec(self, signal_name: str) -> dbc_signal:
        for message in self.dbc_messages:
            if signal_name.startswith(message):
                for signal in self.dbc_messages[message].signals:
                    if signal_name == f'{message}_{signal}':
                        return self.dbc_messages[message].signals[signal]
        return None