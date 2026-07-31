# (C) 2026 ItsThatOneJack (Jack Bacon)
# This Source Code Form is subject to the terms of the Zenith Public License,
# v. 1.0. If you did not receive a copy of the Zenith Public License with this
# software, you can obtain one at <https://itoj.dev/licenses/ZPL-1.0.md>.

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import ast
import sys
import importlib.machinery
import ctypes
import os

from .result import q, Err, Ok, Result
from .error import Error
from .asm import asm, AsmError, AsmTypeError, AssemblyError, AllocationError, ExecutionError, ClobberError, UnknownArchError, UnsupportedArchError
from .native_guard import install_segfault_guard
from .pointer import (
    malloc, calloc, Pointer, PointerError, NullPointerError,
    CachedObjectError, CachedAddressError, FreedPointerError, AlignmentError,
    is_safe, is_interned,
)
from .memscan import (
    MemoryScanner, MemScanError, RegionReadError, RegionWriteError,
    ProcessAccessError, ScannerNotInitializedError, PatternError, accessible,
)
from .elevate import (
    elevated_entrypoint, relaunch_elevated, is_elevated,
    ElevationError, UnpicklableHandoffError,
)
from .cpu import cpuid, vendor_string, cpu_features
from .atomics import atomic_add, atomic_exchange, atomic_compare_exchange
from .spinlock import SpinLock
from .oslock import OSLock, OSLockError
from .trylock import TryLock, LockNotAcquiredError
from .lifecycle import register_crash_handler, unregister_crash_handler, defer, undefer, LifecycleError
from .protect import protect, temporary_protection, Protection, ProtectionError
from .bitfields_unions import bitfield, union, BitfieldError, UnionError
from .gccbuiltins import __builtin__

__all__ = [
    "q", "Err", "Ok", "Result",
    "Error",
    "asm", "AsmError", "AsmTypeError", "AssemblyError", "AllocationError", "ExecutionError", "ClobberError", "UnknownArchError", "UnsupportedArchError",

    "malloc", "calloc", "Pointer", "PointerError", "NullPointerError", "CachedObjectError", "CachedAddressError", "FreedPointerError", "AlignmentError", "is_safe", "is_interned",
    "MemoryScanner", "MemScanError", "RegionReadError", "RegionWriteError", "ProcessAccessError", "ScannerNotInitializedError", "PatternError", "accessible",
    "elevated_entrypoint", "relaunch_elevated", "is_elevated", "ElevationError", "UnpicklableHandoffError",
    "cpuid", "vendor_string", "cpu_features",
    "atomic_add", "atomic_exchange", "atomic_compare_exchange",
    "SpinLock",
    "OSLock", "OSLockError",
    "TryLock", "LockNotAcquiredError",
    "register_crash_handler", "unregister_crash_handler", "defer", "undefer", "LifecycleError",
    "protect", "temporary_protection", "Protection", "ProtectionError",
    "bitfield", "union", "BitfieldError", "UnionError",
    "__builtin__"
]

__version__ = "0.2.2"

class _AutoTryTransform(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        node.decorator_list.insert(
            0, ast.Name(id="__magicalpython_auto_try__", ctx=ast.Load())
        )
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        self.generic_visit(node)
        node.decorator_list.insert(
            0, ast.Name(id="__magicalpython_auto_try__", ctx=ast.Load())
        )
        return node

class magicalPythonLoader(importlib.machinery.SourceFileLoader):
    def source_to_code(self, data, path, *, _optimize=-1):
        src = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        tree = ast.parse(src, filename=path)
        assert isinstance(tree, ast.Module)

        tree.body.insert(0, ast.ImportFrom(
            module="magicalpython_magic.result",
            names=[ast.alias(name="_auto_try", asname="__magicalpython_auto_try__")],
            level=0,
        ))

        tree = _AutoTryTransform().visit(tree)
        ast.fix_missing_locations(tree)
        return compile(tree, path, "exec", dont_inherit=True, optimize=_optimize)

class magicalPythonFinder(importlib.machinery.PathFinder):
    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        spec = super().find_spec(fullname, path, target)
        if (
            spec
            and spec.loader
            and isinstance(spec.loader, importlib.machinery.SourceFileLoader)
            and spec.origin is not None
        ):
            spec.loader = magicalPythonLoader(spec.loader.name, spec.origin)
        return spec

_LIB = None

def install_segfault_guard():
    global _LIB
    if _LIB is not None:
        return

    here = os.path.dirname(__file__)
    if sys.platform == "win32":
        path = os.path.join(here, "native", "segfault_msg.dll")
    else:
        path = os.path.join(here, "native", "segfault_msg.so")

    if not os.path.exists(path):
        raise RuntimeError(
            f"Python++ native guard not built for this platform: {path} not found. This is developer error, please report it."
        )

    _LIB = ctypes.CDLL(path)
    _LIB.magicalpython_install_segfault_handler.argtypes = []
    _LIB.magicalpython_install_segfault_handler.restype = None
    _LIB.magicalpython_install_segfault_handler()

install_segfault_guard()
sys.meta_path.insert(0, magicalPythonFinder)