from __future__ import annotations

import ctypes
import os
import threading
import time
from collections.abc import Callable

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def is_process_running(process_id: int) -> bool:
    """Return whether a process exists without sending a signal to it."""

    if process_id <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(process_id, 0)
        except (OSError, ProcessLookupError):
            return False
        return True

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_bool
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def start_parent_process_watcher(
    parent_process_id: int,
    on_parent_exit: Callable[[], None],
    *,
    poll_interval: float = 0.5,
) -> threading.Thread:
    """Run a daemon watcher and invoke the callback after the parent exits."""

    def watch() -> None:
        while is_process_running(parent_process_id):
            time.sleep(poll_interval)
        on_parent_exit()

    thread = threading.Thread(
        target=watch,
        name="qingjuan-parent-process-watcher",
        daemon=True,
    )
    thread.start()
    return thread
