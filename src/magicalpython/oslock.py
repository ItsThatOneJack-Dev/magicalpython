# (C) 2026 ItsThatOneJack (Jack Bacon)
# This Source Code Form is subject to the terms of the Zenith Public License,
# v. 1.0. If you did not receive a copy of the Zenith Public License with this
# software, you can obtain one at <https://itoj.dev/licenses/ZPL-1.0.md>.

from __future__ import annotations

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import builtins
import ctypes
import os
import sys
import tempfile
from typing import Optional

from .error import Error

class OSLockError(Error):
    pass

# ==========
# NAMED CROSS-PROCESS LOCK
# ==========

class OSLock:
    """
    This is a real OS-mediated cross-process lock, identified by a plain string name.
    Unrelated processes can use the same string to lock against eachother, ensuring only one can run the lock-protected code at once.
    Failiure to obtain the lock will result in the OS suspending the processes that fail, and waking them once the lock is available again.

    On POSIX systems, a file descriptor is needed in order to perform a lock, so a temporary file is created in the system temp directory, and that file is locked against.
    Behaviour is still consistent with Windows.
    """

    def __init__(self, name: str):
        self._name = name
        self._closed = False

        if sys.platform == "win32":
            kernel32 = ctypes.windll.kernel32 # type: ignore
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            self._handle = kernel32.CreateMutexW(None, False, name)
            if not self._handle:
                raise OSLockError(f"CreateMutexW failed for lock name {name!r}")
        else:
            import fcntl
            self._fcntl = fcntl
            self._path = os.path.join(tempfile.gettempdir(), f"magicalpython_lock_{name}.lock")
            self._fd = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o666)

    def acquire(self) -> None:
        """
        Blocks until the lock is acquired.
        The OS will suspend the process until the lock is available, if it is not available when this method runs.
        """
        if sys.platform == "win32":
            kernel32 = ctypes.windll.kernel32 # type: ignore
            INFINITE = 0xFFFFFFFF
            WAIT_FAILED = 0xFFFFFFFF
            ret = kernel32.WaitForSingleObject(self._handle, INFINITE)
            if ret == WAIT_FAILED:
                raise OSLockError(f"WaitForSingleObject failed for lock {self._name!r}")
        else:
            self._fcntl.flock(self._fd, self._fcntl.LOCK_EX)

    def release(self) -> None:
        """
        Releases the lock, letting the next waiting process (if any) acquire it.
        """
        if sys.platform == "win32":
            kernel32 = ctypes.windll.kernel32 # type: ignore
            if not kernel32.ReleaseMutex(self._handle):
                raise OSLockError(f"ReleaseMutex failed for lock {self._name!r}")
        else:
            self._fcntl.flock(self._fd, self._fcntl.LOCK_UN)

    def close(self) -> None:
        """
        Releases the underlying OS handle/descriptor. Does not delete the POSIX placeholder file, other processes may still be using it.
        """
        if self._closed:
            return
        if sys.platform == "win32":
            ctypes.windll.kernel32.CloseHandle(self._handle) # type: ignore
        else:
            os.close(self._fd)
        self._closed = True

    def __enter__(self) -> "OSLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

# ==========
# PER-FILE OS LOCK
# ==========

def _lock_native(fileobj, exclusive: bool, blocking: bool) -> None:
    """
    Applies an OS-level lock directly to the file object's own underlying descriptor.
    """
    if sys.platform == "win32":
        import msvcrt
        kernel32 = ctypes.windll.kernel32  # type: ignore
        handle = msvcrt.get_osfhandle(fileobj.fileno())

        LOCKFILE_EXCLUSIVE_LOCK = 0x2
        LOCKFILE_FAIL_IMMEDIATELY = 0x1
        flags = (LOCKFILE_EXCLUSIVE_LOCK if exclusive else 0) | (LOCKFILE_FAIL_IMMEDIATELY if not blocking else 0)

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", ctypes.c_ulong),
                ("OffsetHigh", ctypes.c_ulong),
                ("hEvent", ctypes.c_void_p),
            ]

        overlapped = OVERLAPPED()
        ok = kernel32.LockFileEx(handle, flags, 0, 0xFFFFFFFF, 0xFFFFFFFF, ctypes.byref(overlapped))
        if not ok:
            if not blocking:
                raise OSLockError("Could not acquire file lock immediately (already locked elsewhere).")
            raise OSLockError("LockFileEx failed")
    else:
        import fcntl
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        if not blocking:
            mode |= fcntl.LOCK_NB
        try:
            fcntl.flock(fileobj.fileno(), mode)
        except BlockingIOError:
            raise OSLockError("Could not acquire file lock immediately (already locked elsewhere).")

def _unlock_native(fileobj) -> None:
    """
    Releases the OS-level lock held on the file object's own underlying descriptor.
    """
    if sys.platform == "win32":
        import msvcrt
        kernel32 = ctypes.windll.kernel32 # type: ignore
        handle = msvcrt.get_osfhandle(fileobj.fileno())

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", ctypes.c_ulong),
                ("OffsetHigh", ctypes.c_ulong),
                ("hEvent", ctypes.c_void_p),
            ]

        overlapped = OVERLAPPED()
        kernel32.UnlockFileEx(handle, 0, 0xFFFFFFFF, 0xFFFFFFFF, ctypes.byref(overlapped))
    else:
        import fcntl
        fcntl.flock(fileobj.fileno(), fcntl.LOCK_UN)


class _LockedFile:
    """
    Thin proxy around a real file object.
    Delegates everything, but unlocks before closing.
    """

    def __init__(self, fileobj):
        object.__setattr__(self, "_fileobj", fileobj)
        object.__setattr__(self, "_unlocked", False)

    def __getattr__(self, name):
        return getattr(self._fileobj, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __iter__(self):
        return iter(self._fileobj)

    def close(self) -> None:
        if not self._unlocked:
            try:
                _unlock_native(self._fileobj)
            finally:
                object.__setattr__(self, "_unlocked", True)
        self._fileobj.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

def lockopen(file, mode: str = "r", *, exclusive: Optional[bool] = None, blocking: bool = True, **kwargs):
    """
    This opens a file, pretty much exactly as `open()` does, except we get an OS-level lock on it.
    The docstring for `open()` is below:
    
    Open file and return a stream. Raise OSError upon failure.

    file is either a text or byte string giving the name (and the path if the file isn't in the current working directory) of the file to be opened or an integer file descriptor of the file to be wrapped. (If a file descriptor is given, it is closed when the returned I/O object is closed, unless closefd is set to False.)
    mode is an optional string that specifies the mode in which the file is opened. It defaults to 'r' which means open for reading in text mode. Other common values are 'w' for writing (truncating the file if it already exists), 'x' for creating and writing to a new file, and 'a' for appending (which on some Unix systems, means that all writes append to the end of the file regardless of the current seek position). In text mode, if encoding is not specified the encoding used is platform dependent: locale.getencoding() is called to get the current locale encoding. (For reading and writing raw bytes use binary mode and leave encoding unspecified.) The available modes are:

    Character	Meaning
    'r'         open for reading (default)
    'w'         open for writing, truncating the file first
    'x'         create a new file and open it for writing
    'a'         open for writing, appending to the end of the file if it exists
    'b'         binary mode
    't'         text mode (default)
    '+'         open a disk file for updating (reading and writing)
    The default mode is 'rt' (open for reading text). For binary random access, the mode 'w+b' opens and truncates the file to 0 bytes, while 'r+b' opens the file without truncation. The 'x' mode implies 'w' and raises an FileExistsError if the file already exists.
    Python distinguishes between files opened in binary and text modes, even when the underlying operating system doesn't. Files opened in binary mode (appending 'b' to the mode argument) return contents as bytes objects without any decoding. In text mode (the default, or when 't' is appended to the mode argument), the contents of the file are returned as strings, the bytes having been first decoded using a platform-dependent encoding or using the specified encoding if given.

    buffering is an optional integer used to set the buffering policy. Pass 0 to switch buffering off (only allowed in binary mode), 1 to select line buffering (only usable in text mode), and an integer > 1 to indicate the size of a fixed-size chunk buffer. When no buffering argument is given, the default buffering policy works as follows:
    Binary files are buffered in fixed-size chunks; the size of the buffer is chosen using a heuristic trying to determine the underlying device's "block size" and falling back on io.DEFAULT_BUFFER_SIZE. On many systems, the buffer will typically be 4096 or 8192 bytes long.
    "Interactive" text files (files for which isatty() returns True) use line buffering. Other text files use the policy described above for binary files.

    encoding is the name of the encoding used to decode or encode the file. This should only be used in text mode. The default encoding is platform dependent, but any encoding supported by Python can be passed. See the codecs module for the list of supported encodings.
    errors is an optional string that specifies how encoding errors are to be handled---this argument should not be used in binary mode. Pass 'strict' to raise a ValueError exception if there is an encoding error (the default of None has the same effect), or pass 'ignore' to ignore errors. (Note that ignoring encoding errors can lead to data loss.) See the documentation for codecs.register or run 'help(codecs.Codec)' for a list of the permitted encoding error strings.
    newline controls how universal newlines works (it only applies to text mode). It can be None, '', '\n', '\r', and '\r\n'. It works as follows:
    
    On input, if newline is None, universal newlines mode is enabled. Lines in the input can end in '\n', '\r', or '\r\n', and these are translated into '\n' before being returned to the caller. If it is '', universal newline mode is enabled, but line endings are returned to the caller untranslated. If it has any of the other legal values, input lines are only terminated by the given string, and the line ending is returned to the caller untranslated.
    On output, if newline is None, any '\n' characters written are translated to the system default line separator, os.linesep. If newline is '' or '\n', no translation takes place. If newline is any of the other legal values, any '\n' characters written are translated to the given string.
    
    If closefd is False, the underlying file descriptor will be kept open when the file is closed. This does not work when a file name is given and must be True in that case.
    
    A custom opener can be used by passing a callable as opener. The underlying file descriptor for the file object is then obtained by calling opener with (file, flags). opener must return an open file descriptor (passing os.open as opener results in functionality similar to passing None).
    open() returns a file object whose type depends on the mode, and through which the standard file operations such as reading and writing are performed. When open() is used to open a file in a text mode ('w', 'r', 'wt', 'rt', etc.), it returns a TextIOWrapper. When used to open a file in a binary mode, the returned class varies: in read binary mode, it returns a BufferedReader; in write binary and append binary modes, it returns a BufferedWriter, and in read/write mode, it returns a BufferedRandom.
    It is also possible to use a string or bytearray as a file for both reading and writing. For strings StringIO can be used like a file opened in a text mode, and for bytes a BytesIO can be used like a file opened in a binary mode.
    """
    is_exclusive = exclusive if exclusive is not None else any(c in mode for c in ("w", "a", "x", "+"))

    fileobj = builtins.open(file, mode, **kwargs)
    try:
        _lock_native(fileobj, exclusive=is_exclusive, blocking=blocking)
    except Exception:
        fileobj.close()
        raise

    return _LockedFile(fileobj)