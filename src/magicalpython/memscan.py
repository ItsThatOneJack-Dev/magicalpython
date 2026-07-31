# (C) 2026 ItsThatOneJack (Jack Bacon)
# This Source Code Form is subject to the terms of the Zenith Public License,
# v. 1.0. If you did not receive a copy of the Zenith Public License with this
# software, you can obtain one at <https://itoj.dev/licenses/ZPL-1.0.md>.

from __future__ import annotations

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import ctypes
import os
import sys
import time
from typing import List, Tuple, Optional, Dict, Any

from .error import Error

class MemScanError(Error):
    pass

class ProcessAccessError(MemScanError):
    def __init__(self, pid: int, detail: str = ""):
        super().__init__(f"Could not access process {pid}. {detail}".strip())

class RegionReadError(MemScanError):
    def __init__(self, address: int, detail: str = ""):
        super().__init__(f"Failed to read memory at 0x{address:x}. {detail}".strip())

class RegionWriteError(MemScanError):
    def __init__(self, address: int, detail: str = ""):
        super().__init__(f"Failed to write memory at 0x{address:x}. {detail}".strip())

# ==========
# Backend stub
# ==========

class _Backend:
    def read(self, address: int, size: int) -> bytes:
        raise NotImplementedError

    def write(self, address: int, data: bytes) -> None:
        raise NotImplementedError

    def regions(self) -> List[Tuple[int, int]]:
        """Return [(start_address, size), ...] for readable+writable regions."""
        raise NotImplementedError

    def close(self) -> None:
        pass

# ==========
# Linux backend
# ==========

class _LinuxBackend(_Backend):
    def __init__(self, pid: int):
        self.pid = pid
        self._attached = False
        self._mem_path = f"/proc/{pid}/mem"
        self._maps_path = f"/proc/{pid}/maps"
        if not os.path.exists(f"/proc/{pid}"):
            raise ProcessAccessError(pid, "no such process")

    def _try_ptrace_attach(self) -> None:
        """
        This is a best-effort attempt.
        Many distros permit same-UID access without this at all, however some stricter `ptrace_scope` set systems require an actual ptrace attach first.
        If this fails, the direct read/write attempt will raise a clear RegionReadError or RegionWriteError, instead of silently not working.
        """
        if self._attached:
            return
        try:
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            PTRACE_ATTACH = 16
            libc.ptrace(PTRACE_ATTACH, self.pid, None, None)
            for _ in range(50):
                try:
                    with open(f"/proc/{self.pid}/stat") as f:
                        state = f.read().split(") ", 1)[1].split(" ", 1)[0]
                    if state in ("t", "T"):
                        break
                except Exception:
                    pass
                time.sleep(0.01)
            self._attached = True
        except Exception:
            pass

    def regions(self) -> List[Tuple[int, int]]:
        result = []
        with open(self._maps_path) as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                addr_range, perms = parts[0], parts[1]
                if "r" in perms and "w" in perms:
                    start_s, end_s = addr_range.split("-")
                    start, end = int(start_s, 16), int(end_s, 16)
                    result.append((start, end - start))
        return result

    def read(self, address: int, size: int) -> bytes:
        try:
            with open(self._mem_path, "rb") as mem:
                mem.seek(address)
                return mem.read(size)
        except OSError:
            self._try_ptrace_attach()
            try:
                with open(self._mem_path, "rb") as mem:
                    mem.seek(address)
                    return mem.read(size)
            except OSError as e2:
                raise RegionReadError(address, str(e2))

    def write(self, address: int, data: bytes) -> None:
        try:
            with open(self._mem_path, "r+b") as mem:
                mem.seek(address)
                mem.write(data)
        except OSError:
            self._try_ptrace_attach()
            try:
                with open(self._mem_path, "r+b") as mem:
                    mem.seek(address)
                    mem.write(data)
            except OSError as e2:
                raise RegionWriteError(address, str(e2))

    def close(self) -> None:
        if self._attached:
            try:
                libc = ctypes.CDLL("libc.so.6", use_errno=True)
                PTRACE_DETACH = 17
                libc.ptrace(PTRACE_DETACH, self.pid, None, None)
            except Exception:
                pass
            self._attached = False

# ==========
# Windows backend
# ==========

class _WindowsBackend(_Backend):
    PROCESS_VM_READ = 0x0010
    PROCESS_VM_WRITE = 0x0020
    PROCESS_VM_OPERATION = 0x0008
    PROCESS_QUERY_INFORMATION = 0x0400
    ACCESS_RIGHTS = PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION

    MEM_COMMIT = 0x1000
    PAGE_GUARD = 0x100
    WRITABLE_PROTECTS = {0x04, 0x08, 0x40, 0x80} # READWRITE, WRITECOPY, EXECUTE_READWRITE, EXECUTE_WRITECOPY

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", ctypes.c_ulong),
            ("RegionSize", ctypes.c_size_t),
            ("State", ctypes.c_ulong),
            ("Protect", ctypes.c_ulong),
            ("Type", ctypes.c_ulong),
        ]

    @staticmethod
    def _is_admin() -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin()) # type: ignore
        except Exception:
            return False

    def __init__(self, pid: int):
        self.pid = pid
        self.kernel32 = ctypes.windll.kernel32 # type: ignore
        self.kernel32.OpenProcess.restype = ctypes.c_void_p
        self.handle = self.kernel32.OpenProcess(self.ACCESS_RIGHTS, False, pid)
        if not self.handle:
            if self._is_admin():
                raise ProcessAccessError(
                    pid,
                    "OpenProcess failed even while elevated, the target is likely a protected process (common for antivirus/anti-cheat/some system processes), owned by a different account, or already exited."
                )
            raise ProcessAccessError(
                pid,
                "OpenProcess failed. If the target process is owned by a different user account or runs at a higher integrity level, try running as Administrator. If it's already the same user and still fails, the target may be a protected process this can't reach regardless of elevation."
            )

    def regions(self) -> List[Tuple[int, int]]:
        result = []
        address = 0
        mbi = self.MEMORY_BASIC_INFORMATION()
        max_address = 0x00007FFFFFFEFFFF
        while address < max_address:
            ret = self.kernel32.VirtualQueryEx(
                self.handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi)
            )
            if ret == 0:
                break
            if (
                mbi.State == self.MEM_COMMIT
                and mbi.Protect in self.WRITABLE_PROTECTS
                and not (mbi.Protect & self.PAGE_GUARD)
            ):
                result.append((mbi.BaseAddress or 0, mbi.RegionSize))
            if mbi.RegionSize == 0:
                break
            address = (mbi.BaseAddress or 0) + mbi.RegionSize
        return result

    def read(self, address: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        read_n = ctypes.c_size_t(0)
        ok = self.kernel32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(read_n)
        )
        if not ok:
            raise RegionReadError(address)
        return buf.raw

    def write(self, address: int, data: bytes) -> None:
        written = ctypes.c_size_t(0)
        ok = self.kernel32.WriteProcessMemory(
            self.handle, ctypes.c_void_p(address), data, len(data), ctypes.byref(written)
        )
        if not ok:
            raise RegionWriteError(address)

    def close(self) -> None:
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None

# ---------------- macOS backend: Mach VM APIs (best effort - see caveat below) ----------------

class _MacBackend(_Backend):
    """
    This is best-effort MacOS support via task_for_pid and mach_vm_* calls.

    On modern MacOS with System Integrity Protection (SIP) enabled, task_for_pid against an arbitrary process will fail with a permissions error, even when running as root.
    This is an OS-level restriction, the only way around it is per-process entitlements, or disabling SIP.
    """

    KERN_SUCCESS = 0
    VM_REGION_BASIC_INFO_64 = 9
    VM_PROT_READ = 0x1
    VM_PROT_WRITE = 0x2

    class vm_region_basic_info_64(ctypes.Structure):
        _fields_ = [
            ("protection", ctypes.c_uint32),
            ("max_protection", ctypes.c_uint32),
            ("inheritance", ctypes.c_uint32),
            ("shared", ctypes.c_uint32),
            ("reserved", ctypes.c_uint32),
            ("offset", ctypes.c_ulonglong),
            ("behavior", ctypes.c_uint32),
            ("user_wired_count", ctypes.c_ushort),
        ]

    def __init__(self, pid: int):
        self.pid = pid
        self.libc = ctypes.CDLL(None)
        task = ctypes.c_uint32(0)
        self_task = self.libc.mach_task_self()
        ret = self.libc.task_for_pid(self_task, pid, ctypes.byref(task))
        if ret != self.KERN_SUCCESS:
            raise ProcessAccessError(
                pid,
                f"Task_for_pid failed (kern_return_t={ret}). On modern macOS this almost always means System Integrity Protection is blocking access, this is an OS-level restriction, not something MagicalPython can get around."
            )
        self.task = task

    def regions(self) -> List[Tuple[int, int]]:
        result = []
        address = ctypes.c_uint64(0)
        while True:
            size = ctypes.c_uint64(0)
            info = self.vm_region_basic_info_64()
            info_count = ctypes.c_uint32(ctypes.sizeof(info) // ctypes.sizeof(ctypes.c_uint32))
            object_name = ctypes.c_uint32(0)
            ret = self.libc.mach_vm_region(
                self.task,
                ctypes.byref(address),
                ctypes.byref(size),
                self.VM_REGION_BASIC_INFO_64,
                ctypes.byref(info),
                ctypes.byref(info_count),
                ctypes.byref(object_name),
            )
            if ret != self.KERN_SUCCESS:
                break
            if info.protection & self.VM_PROT_READ and info.protection & self.VM_PROT_WRITE:
                result.append((address.value, size.value))
            address = ctypes.c_uint64(address.value + size.value)
        return result

    def read(self, address: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        out_size = ctypes.c_uint64(0)
        ret = self.libc.mach_vm_read_overwrite(
            self.task,
            ctypes.c_uint64(address),
            ctypes.c_uint64(size),
            ctypes.cast(buf, ctypes.c_void_p),
            ctypes.byref(out_size),
        )
        if ret != self.KERN_SUCCESS:
            raise RegionReadError(address)
        return buf.raw[: out_size.value]

    def write(self, address: int, data: bytes) -> None:
        ret = self.libc.mach_vm_write(
            self.task, ctypes.c_uint64(address), data, ctypes.c_uint32(len(data))
        )
        if ret != self.KERN_SUCCESS:
            raise RegionWriteError(address)

    def close(self) -> None:
        pass

# ==========
# Backend selection
# ==========

_backend_cache: Dict[int, _Backend] = {}

def _get_backend(pid: int) -> _Backend:
    if pid in _backend_cache:
        return _backend_cache[pid]

    if sys.platform == "win32":
        backend: _Backend = _WindowsBackend(pid)
    elif sys.platform == "darwin":
        backend = _MacBackend(pid)
    elif sys.platform.startswith("linux"):
        backend = _LinuxBackend(pid)
    else:
        raise MemScanError(f"Unsupported platform for remote memory access: {sys.platform}")

    _backend_cache[pid] = backend
    return backend

def accessible(pid: int) -> Tuple[bool, bool]:
    """
    Returns (can_read, can_write) for a given process ID, doesn't raise.

    The check is performed by opening the process, trying to read (returning instantly with (False, False) if fails), then trying to write back what was read.
    """
    try:
        backend = _get_backend(pid)
    except MemScanError:
        return (False, False)

    can_read = False
    can_write = False

    try:
        regions = backend.regions()
    except MemScanError:
        regions = []

    for start, size in regions:
        if size < 8:
            continue
        try:
            original = backend.read(start, 1)
            can_read = True
        except MemScanError:
            continue
        try:
            backend.write(start, original) # Write back the same byte, a real write but nothing is actually changed.
            can_write = True
        except MemScanError:
            pass
        break # One successful region is enough to provide a result.

    return (can_read, can_write)

# ==========
# MemoryScanner
# ==========

class ScannerNotInitializedError(MemScanError):
    def __init__(self):
        super().__init__("Call scan_unknown() (or set a ctype) before rescanning/refreshing candidates.")

class PatternError(MemScanError):
    def __init__(self, pattern: str, detail: str = ""):
        super().__init__(f"Invalid pattern {pattern!r}. {detail}".strip())

def _parse_pattern(pattern: str):
    """Parses 'AA BB ?? CC' into (bytes_with_wildcards_as_0, mask_list_of_bool)."""
    tokens = pattern.split()
    if not tokens:
        raise PatternError(pattern, "pattern is empty.")
    values = bytearray()
    mask = []
    for tok in tokens:
        if tok in ("??", "?"):
            values.append(0)
            mask.append(False)
        else:
            try:
                values.append(int(tok, 16))
            except ValueError:
                raise PatternError(pattern, f"'{tok}' is not a valid hex byte or wildcard.")
            mask.append(True)
    return bytes(values), mask

class MemoryScanner:
    """
    Scan and narrow candidate addresses in a process' memory (same-process or remote, just pass the PID if remote). Only the primitives are provided, all else is up to the creator.
    """

    def __init__(self, pid: int):
        self.pid = pid
        self._backend = _get_backend(pid)
        self._candidates: Dict[int, Any] = {}
        self._ctype: Optional[type] = None

    def scan_unknown(self, ctype: type = ctypes.c_long, alignment: Optional[int] = None) -> int:
        """
        First scan with no known value, recording every aligned position across every readable/writable region as a candidate, with its current value.
        This is understandably very slow, and uses a lot of memory.
        """
        width = ctypes.sizeof(ctype)
        step = alignment or width
        self._ctype = ctype
        self._candidates = {}

        for start, size in self._backend.regions():
            try:
                data = self._backend.read(start, size)
            except MemScanError:
                continue # A region can vanish/become unreadable mid-scan, skip it, don't abort the whole scan.
            for offset in range(0, len(data) - width + 1, step):
                addr = start + offset
                value = ctype.from_buffer_copy(data, offset).value
                self._candidates[addr] = value

        return len(self._candidates)

    def rescan_equal(self, value: Any) -> int:
        """Narrow candidates to those currently holding exactly `value`. Also usable as the first scan if you already have a guess."""
        self._refresh_candidates()
        self._candidates = {a: v for a, v in self._candidates.items() if v == value}
        return len(self._candidates)

    def rescan_changed(self) -> int:
        old = dict(self._candidates)
        self._refresh_candidates()
        self._candidates = {a: v for a, v in self._candidates.items() if v != old.get(a)}
        return len(self._candidates)

    def rescan_unchanged(self) -> int:
        old = dict(self._candidates)
        self._refresh_candidates()
        self._candidates = {a: v for a, v in self._candidates.items() if v == old.get(a)}
        return len(self._candidates)

    def rescan_increased(self) -> int:
        old = dict(self._candidates)
        self._refresh_candidates()
        self._candidates = {
            a: v for a, v in self._candidates.items() if old.get(a) is not None and v > old[a]
        }
        return len(self._candidates)

    def rescan_decreased(self) -> int:
        old = dict(self._candidates)
        self._refresh_candidates()
        self._candidates = {
            a: v for a, v in self._candidates.items() if old.get(a) is not None and v < old[a]
        }
        return len(self._candidates)

    def candidates(self) -> List[int]:
        """Current candidate addresses."""
        return list(self._candidates.keys())

    def candidate_values(self) -> Dict[int, Any]:
        """Current candidate addresses mapped to their last-known values."""
        return dict(self._candidates)

    def to_pointers(self, ctype: Optional[type] = None) -> list:
        """Wrap all remaining candidates as real Pointer objects (same pid, remote-aware automatically)."""
        from .pointer import Pointer # Local impor, this way we avoid a circular import at module load time.

        ct = ctype or self._ctype
        return [Pointer(addr, ct, pid=self.pid, sure=True) for addr in self._candidates]

    def scan_pattern(self, pattern: str) -> List[int]:
        """
        AoB (array-of-bytes) scan. Pattern is space-separated hex bytes with
        '??' as a wildcard for "any byte", e.g. "48 8B ?? ?? 89 C8".
        Returns a list of absolute addresses where the pattern matches,
        searched across every readable+writable region.
        """
        values, mask = _parse_pattern(pattern)
        n = len(values)
        matches: List[int] = []

        for start, size in self._backend.regions():
            try:
                data = self._backend.read(start, size)
            except MemScanError:
                continue
            limit = len(data) - n
            i = 0
            while i <= limit:
                ok = True
                for j in range(n):
                    if mask[j] and data[i + j] != values[j]:
                        ok = False
                        break
                if ok:
                    matches.append(start + i)
                i += 1

        return matches

    def _refresh_candidates(self) -> None:
        if self._ctype is None:
            raise ScannerNotInitializedError()
        ctype = self._ctype
        width = ctypes.sizeof(ctype)
        refreshed = {}
        for addr in self._candidates:
            try:
                data = self._backend.read(addr, width)
                refreshed[addr] = ctype.from_buffer_copy(data).value
            except MemScanError:
                continue # Candidate address became unreadable, drop it silently, it's no longer valid anyway.
        self._candidates = refreshed