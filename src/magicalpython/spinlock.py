# (C) 2026 ItsThatOneJack (Jack Bacon)
# This Source Code Form is subject to the terms of the Zenith Public License,
# v. 1.0. If you did not receive a copy of the Zenith Public License with this
# software, you can obtain one at <https://itoj.dev/licenses/ZPL-1.0.md>.

from __future__ import annotations

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import ctypes
import time

from .atomics import atomic_compare_exchange
from .pointer import malloc

class SpinLock:
    """
    A spinlock backed by genuine atomic compare-and-swap. Not a Python-level lock.
    BEWARE: This is not like many popular implementations, that are a hybrid between locks and spinlocks. This is a true spinlock.
        That means this will spin the core it is running on FOREVER until it gets the lock.
        So it will utilise said core at nearly 100% until it gets it, this is incredibly wasteful for long waits, use normal locks.
        
    If you plan to wait for a long time, it is advisable you use an OSLock, as those will wake the process as soon as the lock is available, allowing you to get it instantly.
    For a quick try, use a trylock! They work the same way as a spinlock, but make only one attempt to lock, returning a boolean of if it did get the lock.
    """

    def __init__(self):
        self._ptr = malloc(ctypes.c_int32)
        self._ptr.value = 0 # Unlocked = 0, Locked = 1

    def acquire(self, spin_pause: bool = True) -> None:
        while True:
            old = atomic_compare_exchange(self._ptr.address, 0, 1, width=4)
            if old == 0:
                return
            if spin_pause:
                # We do a tiny yield to keep this from being a pure busy-loop.
                # A sleep of 0 allows the CPython GIL to swap between threads, so your code doesn't freeze up.
                time.sleep(0)

    def release(self) -> None:
        self._ptr.value = 0

    def locked(self) -> bool:
        return self._ptr.value != 0

    def __enter__(self) -> "SpinLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def __del__(self):
        try:
            self._ptr.free()
        except Exception:
            pass