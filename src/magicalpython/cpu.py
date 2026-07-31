from __future__ import annotations

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import ctypes
import sys
from typing import Dict, Tuple

from .asm import inline_asm
from .pointer import malloc

# CPUID clobbers EBX, which is callee-saved in both calling conventions,
# so we save/restore it ourselves rather than relying on the @asm clobbers system as we need manual control over register layout for this.

if sys.platform == "win32":
    # Windowx x64: Leaf = ECX, Subleaf = EDX, Out Pointer = R8
    _CPUID_ASM = """
        push rbx
        mov eax, ecx
        mov ecx, edx
        cpuid
        mov [r8], eax
        mov [r8+4], ebx
        mov [r8+8], ecx
        mov [r8+12], edx
        pop rbx
        ret
    """
else:
    # System V x64 (Linux/macOS): Leaf = EDI, Subleaf = ESI, Out Pointer = RDX
    # IMPORTANT: CPUID clobbers EDX (one of its own output registers), which collides with RDX being the 3rd argument register.
    # out_ptr must be staged into a register CPUID doesn't touch (R10) before calling it, or the pointer will be destroyed before we can write results.
    _CPUID_ASM = """
        push rbx
        mov r10, rdx
        mov eax, edi
        mov ecx, esi
        cpuid
        mov [r10], eax
        mov [r10+4], ebx
        mov [r10+8], ecx
        mov [r10+12], edx
        pop rbx
        ret
    """

_cpuid_fn = inline_asm(
    _CPUID_ASM,
    argtypes=[ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p],
    restype=None,
)

def cpuid(leaf: int, subleaf: int = 0) -> Tuple[int, int, int, int]:
    """Raw CPUID.
    Returns (EAX, EBX, ECX, EDX) for the given leaf/subleaf.
    """
    out = malloc(ctypes.c_uint32, 4)
    try:
        _cpuid_fn(leaf, subleaf, out.address)
        return (out[0], out[1], out[2], out[3])
    finally:
        out.free()

def vendor_string() -> str:
    """Gets the CPU vendor string from CPUID leaf 0.
    E.g. 'GenuineIntel' or 'AuthenticAMD'."""
    _, ebx, ecx, edx = cpuid(0)
    return b"".join(
        v.to_bytes(4, "little") for v in (ebx, edx, ecx)
    ).decode("ascii", errors="replace")

# (leaf, subleaf, register, bit, feature_name), this is deliberately a small, well-known subset.
_FEATURE_BITS = [
    (1, 0, "edx", 25, "sse"),
    (1, 0, "edx", 26, "sse2"),
    (1, 0, "ecx", 0, "sse3"),
    (1, 0, "ecx", 9, "ssse3"),
    (1, 0, "ecx", 19, "sse4_1"),
    (1, 0, "ecx", 20, "sse4_2"),
    (1, 0, "ecx", 23, "popcnt"),
    (1, 0, "ecx", 28, "avx"),
    (1, 0, "ecx", 30, "rdrand"),
    (7, 0, "ebx", 5, "avx2"),
    (7, 0, "ebx", 3, "bmi1"),
    (7, 0, "ebx", 8, "bmi2"),
    (7, 0, "ebx", 16, "avx512f"),
    (0x80000001, 0, "ecx", 5, "lzcnt"),
    (0x80000001, 0, "edx", 29, "long_mode"),
]

def cpu_features() -> Dict[str, bool]:
    """Decoded boolean feature flags for a well-known subset of CPUID bits."""
    cache: Dict[Tuple[int, int], Tuple[int, int, int, int]] = {}
    result = {}
    for leaf, subleaf, reg, bit, name in _FEATURE_BITS:
        key = (leaf, subleaf)
        if key not in cache:
            cache[key] = cpuid(leaf, subleaf)
        eax, ebx, ecx, edx = cache[key]
        value = {"eax": eax, "ebx": ebx, "ecx": ecx, "edx": edx}[reg]
        result[name] = bool(value & (1 << bit))
    return result