import unittest
import infi.asi_utils
import StringIO
import sys
from infi.instruct import Struct, UBInt8
from infi.instruct.buffer import Buffer, uint_field, bytes_ref


class FakeOutput(infi.asi_utils.OutputContext):
    def __init__(self):
        super(FakeOutput, self).__init__()
        self.stdout = StringIO.StringIO()

    def _print(self, string, file=sys.stdout):
        self.stdout.write(string)
        self.stdout.flush()


class MyStruct(Struct):
    _fields_ = [UBInt8('x')]

class MyBuffer(Buffer):
    x = uint_field(where=bytes_ref[0:1])

_struct = MyStruct(x=0)
_buffer = MyBuffer(x=0)


def test_verbose():
    output = FakeOutput()
    output.output_command(None)
    assert output.stdout.getvalue() == ''
    output.enable_verbose()
    output.output_command(_struct)
    assert output.stdout.getvalue() != ''


def test_raw__struct():
    output = FakeOutput()
    output.enable_raw()
    output._print_item(_struct)
    assert output.stdout.getvalue() == '\x00'


def test_raw__buffer():
    output = FakeOutput()
    output.enable_raw()
    output._print_item(_buffer)
    assert output.stdout.getvalue() == '\x00'


def test_hex__struct():
    output = FakeOutput()
    output.enable_hex()
    output._print_item(_struct)
    assert output.stdout.getvalue() == '00000000: 00                                                .'


def test_hex__buffer():
    output = FakeOutput()
    output.enable_hex()
    output._print_item(_buffer)
    assert output.stdout.getvalue() == '00000000: 00                                                .'

