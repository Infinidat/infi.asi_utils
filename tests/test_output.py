import unittest
import infi.asi_utils
import six.moves
import sys
from infi.instruct import Struct, UBInt8
from infi.instruct.buffer import Buffer, uint_field, bytes_ref
from infi.asi_utils import formatters


class FakeOutput(infi.asi_utils.OutputContext):
    def __init__(self):
        super(FakeOutput, self).__init__()
        self.stdout = six.moves.StringIO()

    def _print(self, string, file=sys.stdout):
        self.stdout.write(string)
        self.stdout.flush()


class MyStruct(Struct):
    _fields_ = [UBInt8('x')]

class MyBuffer(Buffer):
    x = uint_field(where=bytes_ref[0:1])

_struct = MyStruct(x=0)
_buffer = MyBuffer(x=0)


class OutputTestCase(unittest.TestCase):

    def test_verbose(self):
        output = FakeOutput()
        output.output_command(None)
        self.assertEqual(output.stdout.getvalue(), '')
        output.enable_verbose()
        output.output_command(_struct)
        self.assertNotEqual(output.stdout.getvalue(), '')

    def test_raw__struct(self):
        output = FakeOutput()
        output.set_formatters(formatters.RawOutputFormatter())
        output.output_result(_struct)
        self.assertEqual(output.stdout.getvalue(), '\x00')

    def test_raw__buffer(self):
        output = FakeOutput()
        output.set_formatters(formatters.RawOutputFormatter())
        output.output_result(_buffer)
        self.assertEqual(output.stdout.getvalue(), '\x00')

    def test_hex__struct(self):
        output = FakeOutput()
        output.set_formatters(formatters.HexOutputFormatter())
        output.output_result(_struct)
        self.assertEqual(output.stdout.getvalue(), '00000000: 00                                                .')

    def test_hex__buffer(self):
        output = FakeOutput()
        output.set_formatters(formatters.HexOutputFormatter())
        output.output_result(_buffer)
        self.assertEqual(output.stdout.getvalue(), '00000000: 00                                                .')
