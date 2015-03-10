from infi.pyutils.contexts import contextmanager


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
