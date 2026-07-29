from __future__ import annotations

__magicalpython_internal__ = True

import ctypes
import time

from .atomics import atomic_compare_exchange
from .pointer import malloc


class SpinLock:
    """
    A real spinlock backed by a genuine atomic compare-and-swap - not a
    Python-level lock, an actual busy-wait over a lock-prefixed x86
    instruction. Usable as a context manager.

        lock = SpinLock()
        with lock:
            ...critical section...

    Note: this busy-waits (spins), burning CPU while contended, by design -
    that's what a spinlock is. Use threading.Lock instead for anything that
    might be held for a while; spinlocks are for very short critical sections
    where the overhead of a real OS mutex would dwarf the work being guarded.
    """

    def __init__(self):
        self._ptr = malloc(ctypes.c_int32)
        self._ptr.value = 0  # 0 = unlocked, 1 = locked

    def acquire(self, spin_pause: bool = True) -> None:
        while True:
            old = atomic_compare_exchange(self._ptr.address, 0, 1, width=4)
            if old == 0:
                return
            if spin_pause:
                # a tiny yield keeps this from being a pure power-burning
                # busy-loop on a heavily contended lock - real spinlocks
                # often use a `pause` instruction here for the same reason
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