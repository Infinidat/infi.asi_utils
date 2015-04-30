from infi.pyutils.contexts import contextmanager


MS = 1000
SG_TIMEOUT_IN_SEC = 3
SG_TIMEOUT_IN_MS = SG_TIMEOUT_IN_SEC * MS


@contextmanager
def windows(device):
    from infi.asi.win32 import OSFile
    from infi.asi import create_platform_command_executer
    handle = OSFile(device)
    executer = create_platform_command_executer(handle)
    try:
        yield executer
    finally:
        handle.close()


@contextmanager
def linux_dm(device):
    import os
    from infi.asi.unix import OSFile
    from infi.asi.linux import LinuxIoctlCommandExecuter

    handle = OSFile(os.open(device, os.O_RDWR))
    executer = LinuxIoctlCommandExecuter(handle)
    try:
        yield executer
    finally:
        handle.close()


@contextmanager
def linux_sg(device):
    import os
    from infi.asi.unix import OSFile
    from infi.asi import create_platform_command_executer

    handle = OSFile(os.open(device, os.O_RDWR))
    executer = create_platform_command_executer(handle, timeout=SG_TIMEOUT_IN_MS)
    try:
        yield executer
    finally:
        handle.close()


@contextmanager
def solaris(device):
    import os
    from infi.asi.unix import OSFile
    from infi.asi import create_platform_command_executer

    handle = OSFile(os.open(device, os.O_RDWR))
    executer = create_platform_command_executer(handle)
    try:
        yield executer
    finally:
        handle.close()


@contextmanager
def aix(device):
    import os
    from infi.asi.unix import OSFile
    from infi.asi import create_platform_command_executer

    handle = OSFile(os.open(device, os.O_RDWR))
    executer = create_platform_command_executer(handle)
    try:
        yield executer
    finally:
        handle.close()