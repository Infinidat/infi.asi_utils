"""asi-utils, a partial cross-platform, pure-python implementation of sg3-utils

Usage:
    asi-utils turs    [options] <device> [--number=NUM]
    asi-utils inq     [options] <device> [--page=PG]
    asi-utils luns    [options] <device> [--select=SR]
    asi-utils readcap [options] <device> [--long]
    asi-utils raw     [options] <device> <cdb>... [--request=RLEN] [--outfile=OFILE]
    asi-utils logs    [options] <device> [--page=PG]
    asi-utils reset   [options] <device> [--target | --host | --device]

Options:
    --number=NUM    number of test_unit_ready commands [default: 1]
    --page=PG       page number or abbreviation
    --select=SR     select report SR [default: 0]
    --long          use READ CAPACITY (16) cdb
    --request=RLEN  Request up to RLEN bytes of data (data-in)
    --outfile=OFILE Write binary data to OFILE
    --target        target reset
    --host          host (bus adapter: HBA) reset
    --device        device (logical unit) reset
    --raw           output response in binary
    --hex           output response in hexadecimal
    --verbose       increase verbosity
"""

import sys
import docopt
from infi.pyutils.contexts import contextmanager


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

    def _print_item(self, item):
        from infi.instruct import Struct
        from infi.instruct.buffer import Buffer
        data = type(item).write_to_string(item) if isinstance(item, Struct) else item.pack()
        pretty = repr(item) if isinstance(item, Struct) else item
        if self._hex or self._raw:
            if self._raw:
                print str(data)
            if self._hex:
                print repr(str(data))
        else:
            print pretty

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
        _func = executers.linux_dm if 'dm-' in device else executers.linux_sg
    elif platform.startswith('solaris'):
        raise NotImplementedError()
    else:
        raise NotImplementedError()
    with _func(device) as executer:
        yield executer


def sync_wait(asi, command):
    from infi.asi.coroutines.sync_adapter import sync_wait as _sync_wait
    ActiveOutputContext.output_command(command)
    result = _sync_wait(command.execute(asi))
    ActiveOutputContext.output_result(result)


def turs(device, number):
    from infi.asi.cdb.inquiry.standard import StandardInquiryCommand
    with asi_context(device) as asi:
        for i in xrange(int(number)):
            command = StandardInquiryCommand()
            sync_wait(asi, command)


def inq(device, page):
    from infi.asi.cdb.inquiry import standard, vpd_pages
    if page is None:
        command = standard.StandardInquiryCommand()
    elif page.isdigit():
        command = vpd_pages.get_vpd_page(int(page))
    elif page.startswith('0x'):
        command = vpd_pages.get_vpd_page(int(page, 16))
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


def raw(device, cdb, request_length, output_file):
    raise NotImplementedError()


def logs(device, page):
    raise NotImplementedError()


def reset(device, target_reset, host_reset, lun_reset):
    raise NotImplementedError()


def main(argv=sys.argv[1:]):
    from infi.asi.__version__ import __version__
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
            request_length=arguments['--request'], output_file=arguments['--outfile'])
    elif arguments['logs']:
        logs(arguments['<device>'], page=arguments['--page'])
    elif arguments['reset']:
        reset(arguments['<device>'], target_reset=arguments['--target'],
              host_reset=arguments['--host'], lun_reset=arguments['--device'])
