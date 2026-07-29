from __future__ import annotations

__magicalpython_internal__ = True

import ctypes
import sys

from .asm import inline_asm
from .cpu import cpu_features

_features = cpu_features()

if sys.platform == "win32":
    _POPCNT_ASM = "popcnt rax, rcx\nret"
    _BSWAP32_ASM = "mov eax, ecx\nbswap eax\nret"
    _BSWAP64_ASM = "mov rax, rcx\nbswap rax\nret"
    _BSR_ASM = "bsr rax, rcx\nret"   # bit scan reverse - index of highest set bit
    _BSF_ASM = "bsf rax, rcx\nret"   # bit scan forward - index of lowest set bit
else:
    _POPCNT_ASM = "popcnt rax, rdi\nret"
    _BSWAP32_ASM = "mov eax, edi\nbswap eax\nret"
    _BSWAP64_ASM = "mov rax, rdi\nbswap rax\nret"
    _BSR_ASM = "bsr rax, rdi\nret"
    _BSF_ASM = "bsf rax, rdi\nret"

_bswap32_fn = inline_asm(_BSWAP32_ASM, argtypes=[ctypes.c_uint32], restype=ctypes.c_uint32)
_bswap64_fn = inline_asm(_BSWAP64_ASM, argtypes=[ctypes.c_uint64], restype=ctypes.c_uint64)
_bsr_fn = inline_asm(_BSR_ASM, argtypes=[ctypes.c_uint64], restype=ctypes.c_uint64)
_bsf_fn = inline_asm(_BSF_ASM, argtypes=[ctypes.c_uint64], restype=ctypes.c_uint64)

if _features.get("popcnt"):
    _popcnt_fn = inline_asm(_POPCNT_ASM, argtypes=[ctypes.c_uint64], restype=ctypes.c_uint64)
else:
    _popcnt_fn = None


class __builtin__:
    """GCC-style builtins - real hardware instructions where the CPU supports them, correct pure-Python fallback otherwise."""

    @staticmethod
    def popcount(x: int) -> int:
        """Number of set bits in x (like GCC's __builtin_popcount)."""
        if x < 0:
            raise ValueError("popcount expects a non-negative integer")
        if _popcnt_fn is not None:
            return _popcnt_fn(x)
        return bin(x).count("1")  # correct, portable fallback

    @staticmethod
    def clz(x: int, width: int = 64) -> int:
        """Count leading zeros in a `width`-bit representation of x (like GCC's __builtin_clz)."""
        if x < 0:
            raise ValueError("clz expects a non-negative integer")
        if x == 0:
            return width
        highest_set_bit = _bsr_fn(x)  # index of highest set bit, 0-based
        return width - 1 - highest_set_bit

    @staticmethod
    def ctz(x: int) -> int:
        """Count trailing zeros in x (like GCC's __builtin_ctz). Undefined-in-C for x==0; we return 64 instead of undefined behavior."""
        if x < 0:
            raise ValueError("ctz expects a non-negative integer")
        if x == 0:
            return 64
        return _bsf_fn(x)

    @staticmethod
    def bswap32(x: int) -> int:
        """Byte-swap a 32-bit value (like GCC's __builtin_bswap32)."""
        return _bswap32_fn(x)

    @staticmethod
    def bswap64(x: int) -> int:
        """Byte-swap a 64-bit value (like GCC's __builtin_bswap64)."""
        return _bswap64_fn(x)

    @staticmethod
    def expect(value, expected):
        """No-op branch-prediction hint (like GCC's __builtin_expect) - CPython has no branch predictor hint mechanism, so this purely returns `value` unchanged; it exists for API-compatible porting of C-style code, not for any real effect."""
        return value