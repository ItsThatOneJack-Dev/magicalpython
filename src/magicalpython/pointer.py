from __future__ import annotations

__magicalpython_internal__ = True

import ctypes
import os
import sys
from typing import Any, Optional, Type

from .error import Error

class PointerError(Error):
    pass

class CachedObjectError(PointerError):
    def __init__(self, obj):
        super().__init__(
            f"{obj!r} is a CPython-cached object shared across your whole process. "
            f"Writing to it will corrupt every other use of this value everywhere. "
            f"Pass sure=True if you really mean it."
        )

class CachedAddressError(PointerError):
    def __init__(self, address: int):
        super().__init__(
            f"Address 0x{address:x} belongs to a CPython-cached small int shared "
            f"across your whole process. Writing to it will corrupt every other use "
            f"of that value everywhere. Pass sure=True if you really mean it."
        )

class NullPointerError(PointerError):
    def __init__(self):
        super().__init__("Attempted to dereference a null pointer")

class FreedPointerError(PointerError):
    def __init__(self):
        super().__init__("Attempted to use a pointer after its memory was freed")

class AlignmentError(PointerError):
    def __init__(self, n):
        super().__init__(f"Alignment boundary must be a positive integer, got {n!r}")

_SMALL_INT_RANGE = range(-5, 257)
_CACHED_INT_ADDRESSES = frozenset(id(i) for i in _SMALL_INT_RANGE)

def is_interned(s: str) -> bool:
    """True if this exact string object is CPython's canonical interned copy."""
    try:
        return sys.intern(s) is s
    except Exception:
        return False

def _is_cached(obj) -> bool:
    if isinstance(obj, int) and obj in _SMALL_INT_RANGE:
        return True
    if isinstance(obj, str):
        return is_interned(obj)
    return False

def is_safe(value: Any) -> bool:
    """
    True if `value` is safe to point at without corrupting shared process state.
    int: safe unless cached (-5..256). str: safe unless interned. Anything
    else: always safe.
    """
    if isinstance(value, int):
        return value not in _SMALL_INT_RANGE
    if isinstance(value, str):
        return not is_interned(value)
    return True

def _address_is_known_cached(address: int) -> bool:
    """Address-only check - only catches cached small ints (see is_safe/Pointer.of for the fuller, object-based check)."""
    return address in _CACHED_INT_ADDRESSES

class Pointer:
    """
    A raw pointer into process memory - your own process by default, or any
    other process by passing pid=<that process's pid>. Mode is picked
    automatically: pid omitted or equal to os.getpid() -> local ctypes access;
    any other pid -> routed through the appropriate remote backend
    (see memscan.py) with the exact same API either way.
    """

    __slots__ = ("_address", "_ctype", "_owns_memory", "_freed", "_keepalive", "_pid", "_is_remote")

    def __init__(
        self,
        address: int,
        ctype: Optional[Type] = None,
        *,
        pid: Optional[int] = None,
        sure: bool = False,
        owns_memory: bool = False,
        _keepalive=None,
    ):
        resolved_pid = pid if pid is not None else os.getpid()
        is_remote = resolved_pid != os.getpid()

        # the cached-small-int check is a CPython-in-THIS-process concept - it
        # doesn't apply (and can't be meaningfully checked) against another process
        if not is_remote and not sure and _address_is_known_cached(address):
            raise CachedAddressError(address)

        self._pid = resolved_pid
        self._is_remote = is_remote
        self._address = address
        self._ctype = ctype
        self._owns_memory = owns_memory
        self._freed = False
        self._keepalive = _keepalive

    # --- core state ---

    @property
    def address(self) -> int:
        return self._address

    @property
    def ctype(self) -> Optional[Type]:
        return self._ctype

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def is_remote(self) -> bool:
        return self._is_remote

    @property
    def is_null(self) -> bool:
        return self._address == 0

    def _check_usable(self):
        if self._freed:
            raise FreedPointerError()
        if self.is_null:
            raise NullPointerError()

    def _backend(self):
        from .memscan import _get_backend
        return _get_backend(self._pid)

    # --- typed deref ---

    @property
    def value(self) -> Any:
        self._check_usable()
        ct = self._ctype or ctypes.c_ubyte
        if self._is_remote:
            data = self._backend().read(self._address, ctypes.sizeof(ct))
            return ct.from_buffer_copy(data).value
        return ct.from_address(self._address).value

    @value.setter
    def value(self, new_value: Any) -> None:
        self._check_usable()
        ct = self._ctype or ctypes.c_ubyte
        if self._is_remote:
            self._backend().write(self._address, bytes(ct(new_value)))
            return
        ct.from_address(self._address).value = new_value

    def read(self, as_type: Optional[Type] = None) -> Any:
        self._check_usable()
        ct = as_type or self._ctype or ctypes.c_ubyte
        if self._is_remote:
            data = self._backend().read(self._address, ctypes.sizeof(ct))
            return ct.from_buffer_copy(data).value
        return ct.from_address(self._address).value

    def write(self, new_value: Any, as_type: Optional[Type] = None) -> None:
        self._check_usable()
        ct = as_type or self._ctype or ctypes.c_ubyte
        if self._is_remote:
            self._backend().write(self._address, bytes(ct(new_value)))
            return
        ct.from_address(self._address).value = new_value

    # --- raw byte access ---

    def read_bytes(self, n: int) -> bytes:
        self._check_usable()
        if self._is_remote:
            return self._backend().read(self._address, n)
        return ctypes.string_at(self._address, n)

    def write_bytes(self, data: bytes) -> None:
        self._check_usable()
        if self._is_remote:
            self._backend().write(self._address, data)
            return
        buf = ctypes.create_string_buffer(data, len(data))
        ctypes.memmove(self._address, buf, len(data))

    # --- pointer-to-pointer ---

    def read_ptr(self) -> "Pointer":
        self._check_usable()
        if self._is_remote:
            data = self._backend().read(self._address, ctypes.sizeof(ctypes.c_void_p))
            raw = ctypes.c_void_p.from_buffer_copy(data).value or 0
        else:
            raw = ctypes.c_void_p.from_address(self._address).value or 0
        return Pointer(raw, pid=self._pid)

    def write_ptr(self, other: "Pointer") -> None:
        self._check_usable()
        if self._is_remote:
            self._backend().write(self._address, bytes(ctypes.c_void_p(other._address)))
            return
        ctypes.c_void_p.from_address(self._address).value = other._address

    # --- reinterpret ---

    def cast(self, new_ctype: Type) -> "Pointer":
        self._check_usable()
        return Pointer(
            self._address, ctype=new_ctype, pid=self._pid, sure=True,
            owns_memory=False, _keepalive=self._keepalive,
        )

    # --- seek / arithmetic ---

    def _elem_size(self) -> int:
        return ctypes.sizeof(self._ctype) if self._ctype else 1

    def at(self, offset: int) -> "Pointer":
        return Pointer(
            self._address + offset, ctype=self._ctype, pid=self._pid, sure=True, _keepalive=self._keepalive
        )

    def align_up(self, n: int) -> "Pointer":
        if n <= 0:
            raise AlignmentError(n)
        remainder = self._address % n
        offset = 0 if remainder == 0 else (n - remainder)
        return self.at(offset)

    def align_down(self, n: int) -> "Pointer":
        if n <= 0:
            raise AlignmentError(n)
        remainder = self._address % n
        return self.at(-remainder)

    def align(self, n: int) -> "Pointer":
        return self.align_up(n)

    def __add__(self, n: int) -> "Pointer":
        return Pointer(
            self._address + n * self._elem_size(), ctype=self._ctype, pid=self._pid,
            sure=True, _keepalive=self._keepalive,
        )

    def __sub__(self, other) -> Any:
        if isinstance(other, Pointer):
            return (self._address - other._address) // self._elem_size()
        return Pointer(
            self._address - other * self._elem_size(), ctype=self._ctype, pid=self._pid,
            sure=True, _keepalive=self._keepalive,
        )

    def __invert__(self) -> Any:
        return self.value

    def __getitem__(self, i: int) -> Any:
        return self.at(i * self._elem_size()).value

    def __setitem__(self, i: int, new_value: Any) -> None:
        self.at(i * self._elem_size()).value = new_value

    # --- safety introspection ---

    def is_safe(self) -> bool:
        """
        True if this pointer's CURRENT address is known-safe to write to.
        Only meaningful (and only checked) for local pointers - a remote
        pointer's target process may not even be Python, so the CPython
        cached-object concept doesn't apply there; always reports True for
        remote pointers.
        """
        if self._is_remote:
            return True
        return not _address_is_known_cached(self._address)

    # --- freeing (owned local memory only) ---

    def free(self) -> None:
        if self._is_remote:
            raise PointerError("Cannot free memory in another process - Python++ doesn't allocate remote memory")
        if not self._owns_memory:
            raise PointerError(
                "Cannot free a pointer that doesn't own its memory "
                "(only pointers from malloc/calloc can be freed)"
            )
        self._freed = True
        self._keepalive = None

    def __repr__(self) -> str:
        tag = self._ctype.__name__ if self._ctype else "void"
        loc = f"pid={self._pid}" if self._is_remote else "local"
        return f"Pointer<{tag}>(0x{self._address:016x}, {loc})"

    # --- construction from a live Python object (local only) ---

    @classmethod
    def of(cls, value: Any, ctype: Optional[Type] = None, sure: bool = False) -> "Pointer":
        """
        Get a raw Pointer to a live Python object's actual memory in THIS
        process, via id(). Refuses (by default) to point at cached/interned
        values - pass sure=True to override.
        """
        if not sure and not is_safe(value):
            raise CachedObjectError(value)
        return cls(id(value), ctype=ctype, sure=True)


# --- allocation primitives (always local - no such thing as remote malloc) ---

def malloc(ctype: Type[ctypes._CData], count: int = 1) -> Pointer:
    buf = (ctype * count)() # pyright: ignore[reportOperatorIssue]
    addr = ctypes.addressof(buf)
    return Pointer(addr, ctype=ctype, owns_memory=True, _keepalive=buf)

def calloc(ctype: Type[ctypes._CData], count: int = 1) -> Pointer:
    buf = (ctype * count)() # pyright: ignore[reportOperatorIssue]
    ctypes.memset(ctypes.addressof(buf), 0, ctypes.sizeof(buf))
    addr = ctypes.addressof(buf)
    return Pointer(addr, ctype=ctype, owns_memory=True, _keepalive=buf)