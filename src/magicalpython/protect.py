from __future__ import annotations

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import ctypes
import enum
import sys
from contextlib import contextmanager

from .error import Error

class ProtectionError(Error):
    pass

class Protection(enum.IntFlag):
    """Combinable memory protection flags, e.g. Protection.READ | Protection.WRITE."""
    NONE = 0
    READ = 1
    WRITE = 2
    EXEC = 4

def _page_size() -> int:
    if sys.platform == "win32":
        class SYSTEM_INFO(ctypes.Structure):
            _fields_ = [
                ("wProcessorArchitecture", ctypes.c_ushort),
                ("wReserved", ctypes.c_ushort),
                ("dwPageSize", ctypes.c_ulong),
                ("lpMinimumApplicationAddress", ctypes.c_void_p),
                ("lpMaximumApplicationAddress", ctypes.c_void_p),
                ("dwActiveProcessorMask", ctypes.c_void_p),
                ("dwNumberOfProcessors", ctypes.c_ulong),
                ("dwProcessorType", ctypes.c_ulong),
                ("dwAllocationGranularity", ctypes.c_ulong),
                ("wProcessorLevel", ctypes.c_ushort),
                ("wProcessorRevision", ctypes.c_ushort),
            ]
        info = SYSTEM_INFO()
        ctypes.windll.kernel32.GetSystemInfo(ctypes.byref(info)) # type: ignore
        return info.dwPageSize
    import os
    return os.sysconf("SC_PAGE_SIZE")

_PAGE_SIZE = _page_size()

def _page_align(address: int, size: int):
    start = address & ~(_PAGE_SIZE - 1)
    end = (address + size + _PAGE_SIZE - 1) & ~(_PAGE_SIZE - 1)
    return start, end - start

if sys.platform == "win32":
    _WIN_PROTECT_MAP = {
        0: 0x01,                                                    # PAGE_NOACCESS
        Protection.READ: 0x02,                                      # PAGE_READONLY
        Protection.READ | Protection.WRITE: 0x04,                   # PAGE_READWRITE
        Protection.EXEC: 0x10,                                      # PAGE_EXECUTE
        Protection.EXEC | Protection.READ: 0x20,                    # PAGE_EXECUTE_READ
        Protection.EXEC | Protection.READ | Protection.WRITE: 0x40, # PAGE_EXECUTE_READWRITE
    }
    _WIN_PROTECT_MAP_REVERSE = {v: k for k, v in _WIN_PROTECT_MAP.items()}

    def _set_protection(address: int, size: int, flags: int) -> Protection:
        win_flag = _WIN_PROTECT_MAP.get(int(flags))
        if win_flag is None:
            raise ProtectionError(f"Unsupported flag combination for Windows: {flags}")
        old_protect = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.VirtualProtect( # type: ignore
            ctypes.c_void_p(address), ctypes.c_size_t(size), win_flag, ctypes.byref(old_protect)
        )
        if not ok:
            raise ProtectionError(f"VirtualProtect failed at 0x{address:x}")
        return Protection(_WIN_PROTECT_MAP_REVERSE.get(old_protect.value, 0))

else:
    def _posix_prot_value(flags: int) -> int:
        value = 0
        if flags & Protection.READ:
            value |= 0x1
        if flags & Protection.WRITE:
            value |= 0x2
        if flags & Protection.EXEC:
            value |= 0x4
        return value

    def _current_protection_linux(address: int) -> Protection:
        with open("/proc/self/maps") as f:
            for line in f:
                parts = line.split()
                addr_range, perms = parts[0], parts[1]
                start_s, end_s = addr_range.split("-")
                start, end = int(start_s, 16), int(end_s, 16)
                if start <= address < end:
                    flags = Protection.NONE
                    if "r" in perms:
                        flags |= Protection.READ
                    if "w" in perms:
                        flags |= Protection.WRITE
                    if "x" in perms:
                        flags |= Protection.EXEC
                    return flags
        return Protection.NONE

    def _set_protection(address: int, size: int, flags: int) -> Protection:
        libc = ctypes.CDLL(None, use_errno=True)
        prot = _posix_prot_value(flags)

        old_flags = _current_protection_linux(address) if sys.platform.startswith("linux") else Protection.NONE

        ret = libc.mprotect(ctypes.c_void_p(address), ctypes.c_size_t(size), ctypes.c_int(prot))
        if ret != 0:
            err = ctypes.get_errno()
            raise ProtectionError(f"Mprotect failed at 0x{address:x} (errno {err}).")
        return old_flags

def protect(address: int, size: int, flags: int) -> int:
    """
    Changes memory protection for the page(s) covering [address, address+size).
    Flags is a combination of Protection.READ/WRITE/EXEC (e.g. Protection.READ | Protection.WRITE).
    Returns the previous flags on Windows and Linux, and defaults to 0 on MacOS as there isn't a cheap way to check the previous flags.
    If you need to guarantee that the protection flags will be restored, use temporary_protection().

    Note: Protection is page-granular, this affect the entire page(s) containing the range, not the exact bytes requested.
    """
    page_addr, page_size = _page_align(address, size)
    return _set_protection(page_addr, page_size, flags)

@contextmanager
def temporary_protection(address: int, size: int, flags: int):
    """
    This is a context manager that changes the memory protection of [address, address+size), and then sets it back afterwards.
    The only time the protection flags are not set back is if an exception occurs inside the block, or other serious errors such as faults interrupt Python itself.
    In those cases, it is probably the least of your worries anyway.
    """
    old_flags = protect(address, size, flags)
    try:
        yield
    finally:
        protect(address, size, old_flags)