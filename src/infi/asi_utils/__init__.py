"""asi-utils, a partial cross-platform, pure-python implementation of sg3-utils

Usage:
    asi-utils turs                [options] <device> [--number=NUM]
    asi-utils inq                 [options] <device> [--page=PG]
    asi-utils luns                [options] <device> [--select=SR]
    asi-utils rtpg                [options] <device> [--extended]
    asi-utils pr_readkeys         [options] <device>
    asi-utils pr_readcap          [options] <device> [--long]
    asi-utils pr_readreservation  [options] <device>
    asi-utils pr_register         [options] <device> <key>
    asi-utils pr_unregister       [options] <device> <key>
    asi-utils pr_reserve          [options] <device> <key>
    asi-utils pr_release          [options] <device> <key>
    asi-utils reserve             [options] <device> <third_party_device_id>
    asi-utils release             [options] <device> <third_party_device_id>
    asi-utils raw                 [options] <device> <cdb>... [--request=RLEN] [--outfile=OFILE] [--infile=IFILE] [--send=SLEN]
    asi-utils logs                [options] <device> [--page=PG]
    asi-utils reset               [options] <device> [--target | --host | --device]

Options:
    -n NUM, --number=NUM        number of test_unit_ready commands [default: 1]
    -p PG, --page=PG            page number or abbreviation
    -s SR, --select=SR          select report SR [default: 0]
    --extended                  get rtpg extended response instead of length only
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
    -j, --json                  output response in json
    -v, --verbose               increase verbosity
    -V, --version               print version string and exit
"""

from __future__ import print_function
import sys
import docopt
from infi.pyutils.contexts import contextmanager
from infi.pyutils.decorators import wraps
from formatters import *


def exception_handler(func):
    from infi.asi.errors import AsiCheckConditionError
    from infi.asi.errors import AsiOSError, AsiSCSIError

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AsiCheckConditionError, error:
            ActiveOutputContext.output_error(error.sense_obj, file=sys.stderr)
        except (ValueError, NotImplementedError), error:
            print(error, file=sys.stderr)
            raise SystemExit(1)
        except (AsiOSError, AsiSCSIError), error:
            print(error, file=sys.stderr)
            raise SystemExit(1)
    return wrapper


class OutputContext(object):
    def __init__(self):
        super(OutputContext, self).__init__()
        self._verbose = False
        self._command_formatter = DefaultOutputFormatter()
        self._result_formatter = DefaultOutputFormatter()

    def enable_verbose(self):
        self._verbose = True

    def set_command_formatter(self, formatter):
        self._command_formatter = formatter

    def set_result_formatter(self, formatter):
        self._result_formatter = formatter

    def set_formatters(self, formatter):
        self.set_command_formatter(formatter)
        self.set_result_formatter(formatter)

    def _print(self, string, file=sys.stdout):
        print(string, file=file)

    def output_command(self, command, file=sys.stdout):
        if not self._verbose:
            return
        self._print(self._command_formatter.format(command), file=file)

    def output_result(self, result, file=sys.stdout):
        self._print(self._result_formatter.format(result), file=file)

    def output_error(self, result, file=sys.stdout):
        self._print(ErrorOutputFormatter().format(result), file=file)


ActiveOutputContext = OutputContext()


@contextmanager
def asi_context(device):
    from infi.asi import executers
    from infi.os_info import get_platform_string
    platform = get_platform_string()
    if platform.startswith('windows'):
        _func = executers.windows
    elif platform.startswith('linux'):
        if device.startswith('/dev/sd'):
            from infi.sgutils.sg_map import get_sg_from_sd
            device = get_sg_from_sd(device)
        _func = executers.linux_sg if device.startswith('/dev/sg') else executers.linux_dm
    elif platform.startswith('solaris'):
        _func = executers.solaris
    elif platform.startswith('aix'):
        _func = executers.aix
    else:
        raise NotImplementedError("this platform is not supported")
    with _func(device) as executer:
        yield executer


def sync_wait(asi, command, supresss_output=False):
    from infi.asi.coroutines.sync_adapter import sync_wait as _sync_wait
    ActiveOutputContext.output_command(command)
    result = _sync_wait(command.execute(asi))
    if not supresss_output:
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

def parse_key(key):
    return int(key, 16) if key.startswith('0x') else int(key)

def pr_in_command(service_action, device):
    from infi.asi.cdb.persist.input import PersistentReserveInCommand
    allocation_length=520
    with asi_context(device) as asi:
        allocated_enough = False
        while not allocated_enough:
            command = PersistentReserveInCommand(service_action=service_action,
                                                 allocation_length=allocation_length)
            response = sync_wait(asi, command, supresss_output=True)
            allocated_enough = allocation_length >= response.required_allocation_length()
            allocation_length = response.required_allocation_length()
        ActiveOutputContext.output_result(response)

def pr_read_keys(device):
    from infi.asi.cdb.persist.input import PERSISTENT_RESERVE_IN_SERVICE_ACTION_CODES
    pr_in_command(PERSISTENT_RESERVE_IN_SERVICE_ACTION_CODES.READ_KEYS, device)

def pr_read_reservation(device):    
    from infi.asi.cdb.persist.input import PERSISTENT_RESERVE_IN_SERVICE_ACTION_CODES
    pr_in_command(PERSISTENT_RESERVE_IN_SERVICE_ACTION_CODES.READ_RESERVATION, device)

def pr_out_command(command, device):
    with asi_context(device) as asi:
        response = sync_wait(asi, command)

def pr_register(device, key):
    from infi.asi.cdb.persist.output import PersistentReserveOutCommand, PERSISTENT_RESERVE_OUT_SERVICE_ACTION_CODES
    command = PersistentReserveOutCommand(service_action=PERSISTENT_RESERVE_OUT_SERVICE_ACTION_CODES.REGISTER,
                                          service_action_reservation_key=parse_key(key))
    pr_out_command(command, device)

def pr_unregister(device, key):
    from infi.asi.cdb.persist.output import PersistentReserveOutCommand, PERSISTENT_RESERVE_OUT_SERVICE_ACTION_CODES
    command = PersistentReserveOutCommand(service_action=PERSISTENT_RESERVE_OUT_SERVICE_ACTION_CODES.REGISTER,
                                          reservation_key=parse_key(key))
    pr_out_command(command, device)

def pr_reserve(device, key):
    from infi.asi.cdb.persist.output import PersistentReserveOutCommand, PERSISTENT_RESERVE_OUT_SERVICE_ACTION_CODES
    command = PersistentReserveOutCommand(service_action=PERSISTENT_RESERVE_OUT_SERVICE_ACTION_CODES.RESERVE,
                                          reservation_key=parse_key(key))
    pr_out_command(command, device)

def pr_release(device, key):
    from infi.asi.cdb.persist.output import PersistentReserveOutCommand, PERSISTENT_RESERVE_OUT_SERVICE_ACTION_CODES
    command = PersistentReserveOutCommand(service_action=PERSISTENT_RESERVE_OUT_SERVICE_ACTION_CODES.RELEASE,
                                          reservation_key=parse_key(key))    
    pr_out_command(command, device)
  
def reserve(device, third_party_device_id):
    from infi.asi.cdb.reserve import Reserve10Command
    command = Reserve10Command(parse_key(third_party_device_id))
    with asi_context(device) as asi:
        sync_wait(asi, command)

def release(device, third_party_device_id):
    from infi.asi.cdb.release import Release10Command
    command = Release10Command(parse_key(third_party_device_id))
    with asi_context(device) as asi:
        sync_wait(asi, command)

def luns(device, select_report):
    from infi.asi.cdb.report_luns import ReportLunsCommand
    command = ReportLunsCommand(select_report=int(select_report))
    with asi_context(device) as asi:
        sync_wait(asi, command)


def rtpg(device, extended):
    from infi.asi.cdb.rtpg import RTPGCommand
    data_format = 1 if extended else 0
    command = RTPGCommand(parameter_data_format=data_format)
    with asi_context(device) as asi:
        sync_wait(asi, command)


def readcap(device, read_16):
    from infi.asi.cdb.read_capacity import ReadCapacity10Command
    from infi.asi.cdb.read_capacity import ReadCapacity16Command
    command = ReadCapacity16Command() if read_16 else ReadCapacity10Command()
    with asi_context(device) as asi:
        sync_wait(asi, command)


def build_raw_command(cdb, request_length, output_file, send_length, input_file):
    from infi.asi.cdb import CDBBuffer
    from infi.asi import SCSIReadCommand, SCSIWriteCommand
    from hexdump import restore

    class CDB(object):
        def create_datagram(self):
            return cdb_raw

        def execute(self, executer):
            datagram = self.create_datagram()
            if send_length:
                result_datagram = yield executer.call(SCSIWriteCommand(datagram, data))
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

    return CDB()


def raw(device, cdb, request_length, output_file, send_length, input_file):
    command = build_raw_command(cdb, request_length, output_file, send_length, input_file)
    with asi_context(device) as asi:
        result = sync_wait(asi, command, supresss_output=True)
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

def set_formatters(arguments):
    # Output formatters for specific commands
    if arguments['readcap']:
        ActiveOutputContext.set_result_formatter(ReadcapOutputFormatter())
    if arguments['readkeys']:
        ActiveOutputContext.set_result_formatter(ReadkeysOutputFormatter())
    if arguments['readreservation']:
        ActiveOutputContext.set_result_formatter(ReadreservationOutputFormatter())
    elif arguments['luns']:
        ActiveOutputContext.set_result_formatter(LunsOutputFormatter())
    elif arguments['rtpg']:
        ActiveOutputContext.set_result_formatter(RtpgOutputFormatter())
    # Hex/raw/json modes override
    if arguments['--hex']:
        ActiveOutputContext.set_formatters(HexOutputFormatter())
    elif arguments['--raw']:
        ActiveOutputContext.set_formatters(RawOutputFormatter())
    elif arguments['--json']:
        ActiveOutputContext.set_formatters(JsonOutputFormatter())


@exception_handler
def main(argv=sys.argv[1:]):
    from infi.asi_utils.__version__ import __version__
    arguments = docopt.docopt(__doc__, version=__version__)

    if arguments['--verbose']:
        ActiveOutputContext.enable_verbose()
    set_formatters(arguments)

    if arguments['turs']:
        turs(arguments['<device>'], number=arguments['--number'])
    elif arguments['inq']:
        inq(arguments['<device>'], page=arguments['--page'])
    elif arguments['luns']:
        luns(arguments['<device>'], select_report=arguments['--select'])
    elif arguments['rtpg']:
        rtpg(arguments['<device>'], extended=arguments['--extended'])
    elif arguments['readcap']:
        readcap(arguments['<device>'], read_16=arguments['--long'])
    elif arguments['pr_readkeys']:
        pr_read_keys(arguments['<device>'])
    elif arguments['pr_register']:
        pr_register(arguments['<device>'], arguments['<key>'])
    elif arguments['pr_unregister']:
        pr_unregister(arguments['<device>'], arguments['<key>'])
    elif arguments['pr_reserve']:
        pr_reserve(arguments['<device>'], arguments['<key>'])
    elif arguments['pr_release']:
        pr_release(arguments['<device>'], arguments['<key>'])
    elif arguments['reserve']:
        reserve(arguments['<device>'], arguments['<third_party_device_id>'])
    elif arguments['release']:
        release(arguments['<device>'], arguments['<third_party_device_id>'])
    elif arguments['pr_readreservation']:
        pr_read_reservation(arguments['<device>'])
    elif arguments['raw']:
        raw(arguments['<device>'], cdb=arguments['<cdb>'],
            request_length=arguments['--request'], output_file=arguments['--outfile'],
            send_length=arguments['--send'], input_file=arguments['--infile'])
    elif arguments['logs']:
        logs(arguments['<device>'], page=arguments['--page'])
    elif arguments['reset']:
        reset(arguments['<device>'], target_reset=arguments['--target'],
              host_reset=arguments['--host'], lun_reset=arguments['--device'])

