from __future__ import annotations

__magicalpython_internal__ = True

import ctypes
import sys

from .asm import inline_asm

# All of these operate on memory via the FIRST argument (the address) and a
# value via the SECOND. None of xadd/xchg/cmpxchg clobber the argument
# registers themselves, so no register-staging tricks needed here (unlike
# cpuid) - xadd/xchg/cmpxchg only ever touch eax/rax (as the accumulator)
# plus whichever register you choose to hold the new value.

if sys.platform == "win32":
    # win64: arg1(addr)=rcx, arg2(value)=rdx
    _ADD32 = "mov eax, edx\nlock xadd [rcx], eax\nret"
    _ADD64 = "mov rax, rdx\nlock xadd [rcx], rax\nret"
    _XCHG32 = "mov eax, edx\nxchg [rcx], eax\nret"
    _XCHG64 = "mov rax, rdx\nxchg [rcx], rax\nret"
    # cmpxchg Python-facing order is (addr, expected, new) -> win64: rcx, rdx, r8
    _CMPXCHG32 = "mov eax, edx\nlock cmpxchg [rcx], r8d\nret"
    _CMPXCHG64 = "mov rax, rdx\nlock cmpxchg [rcx], r8\nret"
else:
    # System V: arg1(addr)=rdi, arg2(value)=rsi
    _ADD32 = "mov eax, esi\nlock xadd [rdi], eax\nret"
    _ADD64 = "mov rax, rsi\nlock xadd [rdi], rax\nret"
    _XCHG32 = "mov eax, esi\nxchg [rdi], eax\nret"
    _XCHG64 = "mov rax, rsi\nxchg [rdi], rax\nret"
    # cmpxchg Python-facing order is (addr, expected, new) -> SysV: rdi, rsi, rdx
    _CMPXCHG32 = "mov eax, esi\nlock cmpxchg [rdi], edx\nret"
    _CMPXCHG64 = "mov rax, rsi\nlock cmpxchg [rdi], rdx\nret"

_add32 = inline_asm(_ADD32, argtypes=[ctypes.c_void_p, ctypes.c_int32], restype=ctypes.c_int32)
_add64 = inline_asm(_ADD64, argtypes=[ctypes.c_void_p, ctypes.c_int64], restype=ctypes.c_int64)
_xchg32 = inline_asm(_XCHG32, argtypes=[ctypes.c_void_p, ctypes.c_int32], restype=ctypes.c_int32)
_xchg64 = inline_asm(_XCHG64, argtypes=[ctypes.c_void_p, ctypes.c_int64], restype=ctypes.c_int64)
_cmpxchg32 = inline_asm(_CMPXCHG32, argtypes=[ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32], restype=ctypes.c_int32)
_cmpxchg64 = inline_asm(_CMPXCHG64, argtypes=[ctypes.c_void_p, ctypes.c_int64, ctypes.c_int64], restype=ctypes.c_int64)


def atomic_add(address: int, delta: int, width: int = 4) -> int:
    """Atomically adds delta to the value at address. Returns the OLD value (pre-add)."""
    if width == 4:
        return _add32(address, delta)
    elif width == 8:
        return _add64(address, delta)
    raise ValueError("width must be 4 or 8")


def atomic_exchange(address: int, new_value: int, width: int = 4) -> int:
    """Atomically stores new_value at address. Returns the OLD value."""
    if width == 4:
        return _xchg32(address, new_value)
    elif width == 8:
        return _xchg64(address, new_value)
    raise ValueError("width must be 4 or 8")


def atomic_compare_exchange(address: int, expected: int, new_value: int, width: int = 4) -> int:
    """
    Atomically: if the value at address == expected, store new_value.
    Always returns the value that was actually at address before the attempt
    (matches classic CAS semantics) - compare the return value to `expected`
    yourself to know whether the swap actually happened.
    """
    if width == 4:
        return _cmpxchg32(address, expected, new_value)
    elif width == 8:
        return _cmpxchg64(address, expected, new_value)
    raise ValueError("width must be 4 or 8")