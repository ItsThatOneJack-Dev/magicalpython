from __future__ import annotations

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import ctypes

from .atomics import atomic_compare_exchange
from .pointer import malloc
from .error import Error

class LockNotAcquiredError(Error):
    def __init__(self, message: str = "Could not acquire the lock"):
        super().__init__(message)

class TryLock:
    """
    A trylock backed by genuine atomic compare-and-swap. Not a Python-level lock.
    BEWARE: Trylocks work like Spinlocks, but make exactly one attempt. If it can't get the lock, it will raise a LockNotAcquiredError.
    
    If you plan to wait for a long time, it is advisable you use an OSLock, as those will wake the process as soon as the lock is available, allowing you to get it instantly.
    If you want to spin until you get a lock, use a Spinlock.
    """

    def __init__(self):
        self._ptr = malloc(ctypes.c_int32)
        self._ptr.value = 0 # Unlocked = 0, Locked = 1

    def acquire(self) -> bool:
        old = atomic_compare_exchange(self._ptr.address, 0, 1, width=4)
        if old == 0:
            return True
        return False

    def release(self) -> None:
        self._ptr.value = 0

    def locked(self) -> bool:
        return self._ptr.value != 0

    def __enter__(self) -> "TryLock":
        if not self.acquire():
            raise LockNotAcquiredError()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def __del__(self):
        try:
            self._ptr.free()
        except Exception:
            pass