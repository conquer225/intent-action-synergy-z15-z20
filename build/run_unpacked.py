"""Run an executable and its descendants outside the caller's MSIX package.

Usage: python run_unpacked.py python path/to/script.py [arguments...]
The child inherits cwd, environment, stdin/stdout/stderr and its exit code is
returned by this launcher. Redirect the launcher's streams normally for logs.
Windows console windows are hidden. No installation or registry changes occur.

Microsoft API reference:
https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute
"""

import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
import sys


class StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", ctypes.c_void_p),
        ("lpDesktop", ctypes.c_void_p),
        ("lpTitle", ctypes.c_void_p),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class StartupInfoEx(ctypes.Structure):
    _fields_ = [("info", StartupInfo), ("attributes", ctypes.c_void_p)]


class ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("process", wintypes.HANDLE),
        ("thread", wintypes.HANDLE),
        ("pid", wintypes.DWORD),
        ("tid", wintypes.DWORD),
    ]


def run_unpacked(arguments):
    """Launch a native executable, forward standard handles, and wait for exit."""
    if os.name != "nt":
        raise OSError("run_unpacked.py requires Windows")
    if not arguments:
        raise ValueError("Provide an executable followed by its arguments")
    executable = shutil.which(arguments[0])
    if executable is None:
        raise FileNotFoundError(arguments[0])

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    size = ctypes.c_size_t
    declarations = [
        ("InitializeProcThreadAttributeList", [pointer, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(size)], wintypes.BOOL),
        ("UpdateProcThreadAttribute", [pointer, wintypes.DWORD, size, pointer, size, pointer, pointer], wintypes.BOOL),
        ("DeleteProcThreadAttributeList", [pointer], None),
        ("CreateProcessW", [wintypes.LPCWSTR, wintypes.LPWSTR, pointer, pointer, wintypes.BOOL, wintypes.DWORD, pointer, wintypes.LPCWSTR, ctypes.POINTER(StartupInfoEx), ctypes.POINTER(ProcessInformation)], wintypes.BOOL),
        ("GetCurrentProcess", [], wintypes.HANDLE),
        ("GetStdHandle", [wintypes.DWORD], wintypes.HANDLE),
        ("DuplicateHandle", [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.BOOL),
        ("WaitForSingleObject", [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        ("GetExitCodeProcess", [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
    ]
    for name, parameters, return_type in declarations:
        function = getattr(kernel, name)
        function.argtypes = parameters
        function.restype = return_type

    attribute_bytes = size()
    kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(attribute_bytes))
    attribute_buffer = ctypes.create_string_buffer(attribute_bytes.value)
    if not kernel.InitializeProcThreadAttributeList(attribute_buffer, 1, 0, ctypes.byref(attribute_bytes)):
        raise ctypes.WinError(ctypes.get_last_error())

    inherited_handles = []
    process_info = ProcessInformation()
    try:
        # ProcThreadAttributeDesktopAppPolicy (18) | PROC_THREAD_ATTRIBUTE_INPUT.
        # Value 1 is PROCESS_CREATION_DESKTOP_APP_BREAKAWAY_ENABLE_PROCESS_TREE.
        desktop_policy = wintypes.DWORD(1)
        if not kernel.UpdateProcThreadAttribute(attribute_buffer, 0, 0x20012, ctypes.byref(desktop_policy), ctypes.sizeof(desktop_policy), None, None):
            raise ctypes.WinError(ctypes.get_last_error())

        startup = StartupInfoEx()
        startup.info.cb = ctypes.sizeof(startup)
        startup.info.dwFlags = 0x100 | 0x1  # USESTDHANDLES | USESHOWWINDOW
        startup.info.wShowWindow = 0
        startup.attributes = ctypes.cast(attribute_buffer, pointer)
        caller_process = kernel.GetCurrentProcess()
        for identifier, field in [(-10, "hStdInput"), (-11, "hStdOutput"), (-12, "hStdError")]:
            original = kernel.GetStdHandle(wintypes.DWORD(identifier).value)
            if original in (None, pointer(-1).value):
                continue
            duplicate = wintypes.HANDLE()
            if not kernel.DuplicateHandle(caller_process, original, caller_process, ctypes.byref(duplicate), 0, True, 2):
                raise ctypes.WinError(ctypes.get_last_error())
            inherited_handles.append(duplicate)
            setattr(startup.info, field, duplicate)

        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline([executable, *arguments[1:]]))
        creation_flags = 0x80000 | 0x08000000  # EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW
        if not kernel.CreateProcessW(executable, command_line, None, None, True, creation_flags, None, None, ctypes.byref(startup), ctypes.byref(process_info)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        for handle in inherited_handles:
            kernel.CloseHandle(handle)
        kernel.DeleteProcThreadAttributeList(attribute_buffer)

    try:
        while True:
            result = kernel.WaitForSingleObject(process_info.process, 250)
            if result == 0:
                break
            if result != 258:  # WAIT_TIMEOUT
                raise ctypes.WinError(ctypes.get_last_error())
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(process_info.process, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return exit_code.value
    finally:
        kernel.CloseHandle(process_info.thread)
        kernel.CloseHandle(process_info.process)


if __name__ == "__main__":
    command = sys.argv[1:]
    if command[:1] == ["--"]:
        command = command[1:]
    try:
        sys.exit(run_unpacked(command))
    except (OSError, ValueError) as error:
        print(f"run_unpacked: {error}", file=sys.stderr)
        sys.exit(1)
