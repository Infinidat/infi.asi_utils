"""asi-utils, a partial cross-platform, pure-python implementation of sg3-utils

Usage:
    asi-utils turs    [options] <device> [--number=NUM]
    asi-utils inq     [options] <device> [--page=PG]
    asi-utils luns    [options] <device> [--select=SR]
    asi-utils readcap [options] <device> [--long]
    asi-utils raw     [options] <device> <cdb>... [--request=RLEN] [--outfile=OFILE] [--infile=IFILE] [--send=SLEN]
    asi-utils logs    [options] <device> [--page=PG]
    asi-utils reset   [options] <device> [--target | --host | --device]

Options:
    -n NUM, --number=NUM        number of test_unit_ready commands [default: 1]
    -p PG, --page=PG            page number or abbreviation
    -s SR, --select=SR          select report SR [default: 0]
    -l, --long                  use READ CAPACITY (16) cdb
    --request=RLEN              request up to RLEN bytes of data (data-in)
    --outfile=OFILE             write binary data to OFILE
    --infile=IFILE              read data to send from IFILE [default: <stdin>]
    --send=SLEN                 send SLEN bytes of data (data-out)
    --target                    target reset
    --host                      host (bus adapter: HBA) reset
    --device                    device (logical unit) reset
    -r, --raw                   output response in binary
    -h, --hex                   output response in hexadecimal
    -v, --verbose               increase verbosity
    -V, --version               print version string and exit
"""

import sys
import docopt
from infi.pyutils.contexts import contextmanager
from infi.pyutils.decorators import wraps


def exception_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ValueError, NotImplementedError), error:
            print error
            raise SystemExit(1)
    return wrapper


class OutputContext(object):
    def __init__(self):
        super(OutputContext, self).__init__()
        self._verbose = False
        self._raw = False
        self._hex = False

    def enable_verbose(self):
        self._verbose = True

    def enable_raw(self):
        self._raw = True

    def enable_hex(self):
        self._hex = True

    def _print(self, string):
        print string

    def _to_raw(self, data):
        return str(data)

    def _to_hex(self, data):
        from hexdump import hexdump
        return hexdump(data, result='return')

    def _print_item(self, item):
        from infi.instruct import Struct
        from infi.instruct.buffer import Buffer
        from infi.asi.cdb import CDB, CDBBuffer
        data = str(type(item).write_to_string(item)) if isinstance(item, Struct) else \
               str(item.pack()) if isinstance(item, Buffer) else \
               '' if item is None else str(item)
        pretty = repr(item) if isinstance(item, Struct) else \
                  str(item) if isinstance(item, Buffer) else \
                  '' if item is None else str(item)
        if self._hex or self._raw:
            if self._raw:
                self._print(self._to_raw(data))
            if self._hex:
                self._print(self._to_hex(data))
        else:
            self._print(pretty)

    def output_command(self, command):
        if not self._verbose:
            return
        self._print_item(command)

    def output_result(self, result):
        self._print_item(result)


ActiveOutputContext = OutputContext()


@contextmanager
def asi_context(device):
    from . import executers
    from infi.os_info import get_platform_string
    platform = get_platform_string()
    if platform.startswith('windows'):
        _func = executers.windows
    elif platform.startswith('linux'):
        _func = executers.linux_sg if device.startswith('/dev/sg') else executers.linux_dm
    elif platform.startswith('solaris'):
        raise NotImplementedError("this platform is not supported")
    else:
        raise NotImplementedError("this platform is not supported")
    with _func(device) as executer:
        yield executer


def sync_wait(asi, command):
    from infi.asi.coroutines.sync_adapter import sync_wait as _sync_wait
    ActiveOutputContext.output_command(command)
    result = _sync_wait(command.execute(asi))
    ActiveOutputContext.output_result(result)
    return result


def turs(device, number):
    from infi.asi.cdb.tur import TestUnitReadyCommand
    with asi_context(device) as asi:
        for i in xrange(int(number)):
            command = TestUnitReadyCommand()
            sync_wait(asi, command)


def inq(device, page):
    from infi.asi.cdb.inquiry import standard, vpd_pages
    if page is None:
        command = standard.StandardInquiryCommand(allocation_length=219)
    elif page.isdigit():
        command = vpd_pages.get_vpd_page(int(page))()
    elif page.startswith('0x'):
        command = vpd_pages.get_vpd_page(int(page, 16))()
    else:
        raise ValueError("invalid vpd page: %s" % page)
    if command is None:
        raise ValueError("unsupported vpd page: %s" % page)
    with asi_context(device) as asi:
        sync_wait(asi, command)


def luns(device, select_report):
    from infi.asi.cdb.report_luns import ReportLunsCommand
    command = ReportLunsCommand(select_report=int(select_report))
    with asi_context(device) as asi:
        sync_wait(asi, command)


def readcap(device, read_16):
    from infi.asi.cdb.read_capacity import ReadCapacity10Command
    from infi.asi.cdb.read_capacity import ReadCapacity16Command
    command = ReadCapacity16Command() if read_16 else ReadCapacity10Command()
    with asi_context(device) as asi:
        sync_wait(asi, command)


def raw(device, cdb, request_length, output_file, send_length, input_file):
    from infi.asi.cdb import CDBBuffer
    from infi.asi import SCSIReadCommand, SCSIWriteCommand
    from hexdump import restore

    class CDB(object):
        def create_datagram(self):
            return cdb_raw

        def execute(self, executer):
            datagram = self.create_datagram()
            if send_length:
                request_length = yield executer.call(SCSIWriteCommand(datagram, data))
            else:
                result_datagram = yield executer.call(SCSIReadCommand(datagram, request_length))
            yield result_datagram

        def __str__(self):
            return cdb_raw

    cdb_raw = restore(' '.join(cdb) if isinstance(cdb, list) else cdb)

    if request_length is None:
        request_length = 0
    elif request_length.isdigit():
        request_length = int(request_length)
    elif request_length.startswith('0x'):
        request_length = int(request_length, 16)
    else:
        raise ValueError("invalid request length: %s" % request_length)

    if send_length is None:
        send_length = 0
    elif send_length.isdigit():
        send_length = int(send_length)
    elif send_length.startswith('0x'):
        send_length = int(send_length, 16)
    else:
        raise ValueError("invalid send length: %s" % send_length)

    data = ''
    if send_length:
        if input_file == '<stdin>':
            data = sys.stdin.read(send_length)
        else:
            with open(input_file) as fd:
                data = fd.read(send_length)
    assert len(data) == send_length


    with asi_context(device) as asi:
        result = sync_wait(asi, CDB())
        if output_file:
            with open(output_file, 'w') as fd:
                fd.write(result)


def logs(device, page):
    from infi.asi.cdb.log_sense import LogSenseCommand
    if page is None:
        page = 0
    elif page.isdigit():
        page = int(page)
    elif page.startswith('0x'):
        page = int(page, 16)
    else:
        raise ValueError("invalid vpd page: %s" % page)
    command = LogSenseCommand(page_code=page)
    with asi_context(device) as asi:
        sync_wait(asi, command)


def reset(device, target_reset, host_reset, lun_reset):
    from infi.os_info import get_platform_string
    if get_platform_string().startswith('linux'):
        from infi.sgutils import sg_reset
        if target_reset:
            sg_reset.target_reset(device)
        elif host_reset:
            sg_reset.host_reset(device)
        elif lun_reset:
            sg_reset.lun_reset(device)
    else:
        raise NotImplementedError("task management commands not supported on this platform")


@exception_handler
def main(argv=sys.argv[1:]):
    from infi.asi_utils.__version__ import __version__
    arguments = docopt.docopt(__doc__, version=__version__)

    if arguments['--hex']:
        ActiveOutputContext.enable_hex()
    if arguments['--verbose']:
        ActiveOutputContext.enable_verbose()
    if arguments['--raw']:
        ActiveOutputContext.enable_raw()

    if arguments['turs']:
        turs(arguments['<device>'], number=arguments['--number'])
    elif arguments['inq']:
        inq(arguments['<device>'], page=arguments['--page'])
    elif arguments['luns']:
        luns(arguments['<device>'], select_report=arguments['--select'])
    elif arguments['readcap']:
        readcap(arguments['<device>'], read_16=arguments['--long'])
    elif arguments['raw']:
        raw(arguments['<device>'], cdb=arguments['<cdb>'],
            request_length=arguments['--request'], output_file=arguments['--outfile'],
            send_length=arguments['--send'], input_file=arguments['--infile'])
    elif arguments['logs']:
        logs(arguments['<device>'], page=arguments['--page'])
    elif arguments['reset']:
        reset(arguments['<device>'], target_reset=arguments['--target'],
              host_reset=arguments['--host'], lun_reset=arguments['--device'])

