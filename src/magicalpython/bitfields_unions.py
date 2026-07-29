from __future__ import annotations

__magicalpython_internal__ = True

import ctypes
from typing import List, Tuple, Type

from .error import Error


class BitfieldError(Error):
    pass


class UnionError(Error):
    pass


def bitfield(fields: List[Tuple[str, Type, int]], name: str = "magicalPythonBitfield") -> Type[ctypes.Structure]:
    """
    Builds a ctypes.Structure with real bit-packed fields, C-style:

        Flags = bitfield([
            ("is_admin", ctypes.c_uint32, 1),
            ("level", ctypes.c_uint32, 4),
            ("reserved", ctypes.c_uint32, 27),
        ])
        f = Flags()
        f.is_admin = 1
        f.level = 9
        print(f.is_admin, f.level)

    Each tuple is (name, ctype, bit_width). Packing/overlap rules follow
    whatever your C compiler's ABI would do - ctypes bitfields ride on the
    real underlying platform bitfield support, not a reimplementation.
    """
    if not fields:
        raise BitfieldError("bitfield needs at least one field")
    for fname, ftype, bits in fields:
        if bits <= 0:
            raise BitfieldError(f"Field '{fname}' has non-positive bit width: {bits}")
        max_bits = ctypes.sizeof(ftype) * 8
        if bits > max_bits:
            raise BitfieldError(f"Field '{fname}' wants {bits} bits but {ftype.__name__} only has {max_bits}")

    return type(name, (ctypes.Structure,), {"_fields_": fields})


def union(fields: List[Tuple[str, Type]], name: str = "magicalPythonUnion") -> Type[ctypes.Union]:
    """
    Builds a ctypes.Union - all fields share the SAME underlying memory, C-style:

        Punned = union([
            ("as_float", ctypes.c_float),
            ("as_int", ctypes.c_uint32),
            ("as_bytes", ctypes.c_ubyte * 4),
        ])
        u = Punned()
        u.as_float = 1.5
        print(hex(u.as_int))       # the raw IEEE-754 bit pattern of 1.5, reinterpreted as an int
        print(list(u.as_bytes))    # the same 4 bytes, reinterpreted as an array
    """
    if not fields:
        raise UnionError("union needs at least one field")
    return type(name, (ctypes.Union,), {"_fields_": fields})