from __future__ import annotations
from typing import Dict
import sys
import os

root_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if not root_path in sys.path:
    sys.path.append(root_path)

from common.structures.test_spec import signal, signal_source, signal_direction

class a2l_signal:
    def __init__(self, name: str, dscr: str, address: str, upper_limit: str, 
            lower_limit: str, record_layout: str, source: str) -> None:
        self.name: str = name
        self.dscr: str = dscr
        self.address: str = address
        self.upper_limit: str = upper_limit
        self.lower_limit: str = lower_limit
        self.record_layout: str = record_layout
        self.parent: str = 'a2l'
        self.source: str = source

    @staticmethod
    def create_from_spec(spec: Dict[str, str], source: str) -> a2l_signal:
        return a2l_signal(name=spec['name'], dscr=spec['description'], 
                address=spec['address'], upper_limit=spec['upper_limit'], 
                lower_limit=spec['lower_limit'], 
                record_layout=spec['record_layout'], source=source)   

    def convert_to_test_spec_signal(self) -> signal:
        return signal(name=self.name, parent=self.parent, 
                source_type=signal_source.A2L, source=self.source, 
                direction=signal_direction.INPUT, origin=self)

class a2l_file:
    def __init__(self, a2l_file_path: str) -> None:
        self.a2l_file_path: str = a2l_file_path
        from common.parsers.a2l_parser import a2l_parser
        self.a2l_signals: Dict[str, a2l_signal] = a2l_parser.parse_a2l_signals(
                a2l_file_path=a2l_file_path)

    def find_signal_from_spec(self, signal_name: str) -> a2l_signal:
        name = signal_name
        if not name.startswith('a2l_'):
            raise Exception('Wrong signal name')
        else:
            name = signal_name[4:]
        if name in self.a2l_signals:
            return self.a2l_signals[name]
        return None