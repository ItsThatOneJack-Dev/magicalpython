__magicalpython_internal__ = True

import ctypes
import platform
import sys
from typing import Any, Optional, Callable

from keystone import (
    Ks, KS_ARCH_X86, KS_MODE_64, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, # pyright: ignore[reportAttributeAccessIssue]
)

from .error import Error

# --- errors ---

class AsmError(Error):
    """Base class for every inline-asm-related failure."""
    pass

class AssemblyError(AsmError):
    def __init__(self, message: str = "Failed to assemble provided instructions"):
        super().__init__(message)

class AllocationError(AsmError):
    def __init__(self, message: str = "Failed to allocate executable memory"):
        super().__init__(message)

class ExecutionError(AsmError):
    def __init__(self, message: str = "Inline assembly execution failed"):
        super().__init__(message)

class AsmTypeError(AsmError):
    def __init__(self, message: str = "Unsupported type for inline asm argument/return"):
        super().__init__(message)

class ClobberError(AsmError):
    def __init__(self, message: str = "Invalid clobber register"):
        super().__init__(message)

class UnknownArchError(AsmError):
    def __init__(self, arch):
        super().__init__(f"Unknown arch tag '{arch}'. Known tags: {list(_ARCH_CHECKS)}")

class UnsupportedArchError(AsmError):
    def __init__(self, name):
        super().__init__(f"No @asm variant of '{name}' matched this platform/architecture")

# --- type mapping: plain python types -> ctypes, or pass a ctypes type through untouched ---

_TYPE_MAP = {
    int: ctypes.c_long,
    float: ctypes.c_double,
    bool: ctypes.c_bool,
    bytes: ctypes.c_char_p,
    str: ctypes.c_wchar_p,
}

def _resolve_ctype(t):
    if t is None:
        return None  # ctypes convention for void
    if isinstance(t, type) and (
        issubclass(t, ctypes._SimpleCData) or issubclass(t, ctypes._Pointer)  # type: ignore
    ):
        return t  # already a real ctypes type, use as-is
    if t in _TYPE_MAP:
        return _TYPE_MAP[t]
    raise AsmTypeError(f"No known ctypes mapping for {t!r}; pass a ctypes type directly")


# --- assembler / memory allocation ---

_CALLEE_SAVED = {
    "win32": {"rbx", "rbp", "rdi", "rsi", "r12", "r13", "r14", "r15"},
    "posix": {"rbx", "rbp", "r12", "r13", "r14", "r15"},
}

_VOLATILE = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}

_ALL_KNOWN_REGS = _CALLEE_SAVED["win32"] | _CALLEE_SAVED["posix"] | _VOLATILE

_ASM_REGISTRY: dict = {}

_ARCH_CHECKS = {
    "win86":     lambda: sys.platform == "win32"  and platform.machine().lower() in ("x86_64", "amd64"),
    "linux86":   lambda: sys.platform.startswith("linux") and platform.machine().lower() in ("x86_64", "amd64"),
    "mac86":     lambda: sys.platform == "darwin" and platform.machine().lower() in ("x86_64", "amd64"),
    "winarm64":  lambda: sys.platform == "win32"  and platform.machine().lower() in ("arm64", "aarch64"),
    "linuxarm64":lambda: sys.platform.startswith("linux") and platform.machine().lower() in ("arm64", "aarch64"),
    "macarm64":  lambda: sys.platform == "darwin" and platform.machine().lower() in ("arm64", "aarch64"),
}

def _callee_saved_set():
    return _CALLEE_SAVED["win32"] if sys.platform == "win32" else _CALLEE_SAVED["posix"]

def _build_clobber_wrap(asm_code: str, clobbers: list) -> str:
    unknown = [r for r in clobbers if r.lower() not in _ALL_KNOWN_REGS]
    if unknown:
        raise ClobberError(f"Unknown register(s) in clobber list: {unknown}")

    callee_saved = _callee_saved_set()
    to_protect = [r.lower() for r in clobbers if r.lower() in callee_saved]
    # volatile clobbers are accepted but need no protection - they're already
    # fair game per the calling convention. Purely documentation for the reader.

    if "ret" in asm_code.lower():
        raise AssemblyError(
            "When using clobbers=[...], omit your own 'ret' - "
            "Python++ appends the epilogue and return for you."
        )

    prologue = "\n".join(f"push {r}" for r in to_protect)
    epilogue = "\n".join(f"pop {r}" for r in reversed(to_protect))
    return f"{prologue}\n{asm_code}\n{epilogue}\nret"

def _get_assembler():
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return Ks(KS_ARCH_X86, KS_MODE_64)
    elif machine in ("arm64", "aarch64"):
        return Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
    raise AssemblyError(f"Unsupported architecture for inline asm: {machine}")


def _alloc_executable(size: int):
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32  # type: ignore
        MEM_COMMIT, MEM_RESERVE = 0x1000, 0x2000
        PAGE_EXECUTE_READWRITE = 0x40

        kernel32.VirtualAlloc.restype = ctypes.c_void_p
        addr = kernel32.VirtualAlloc(
            None, ctypes.c_size_t(size), MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
        )
        if not addr:
            raise AllocationError("VirtualAlloc rejected the executable memory request")

        def free():
            kernel32.VirtualFree(ctypes.c_void_p(addr), 0, 0x8000)

        return addr, free

    else:
        libc = ctypes.CDLL(None)
        PROT_READ, PROT_WRITE, PROT_EXEC = 0x1, 0x2, 0x4
        MAP_PRIVATE = 0x02
        MAP_ANONYMOUS = 0x20 if sys.platform.startswith("linux") else 0x1000

        libc.mmap.restype = ctypes.c_void_p
        libc.mmap.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_long,
        ]
        addr = libc.mmap(
            None, size, PROT_READ | PROT_WRITE | PROT_EXEC,
            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0,
        )
        if addr == ctypes.c_void_p(-1).value or not addr:
            raise AllocationError(
                "mmap rejected the executable memory request "
                "(W^X policy or hardened runtime may be blocking RWX pages)"
            )

        def free():
            libc.munmap(ctypes.c_void_p(addr), size)

        return addr, free

def _arch_matches(arch):
    if arch is None:
        return True
    check = _ARCH_CHECKS.get(arch)
    if check is None:
        raise UnknownArchError(arch)
    return check()


def _unavailable_stub(name: str) -> Callable[..., Any]:
    def stub(*args: Any, **kwargs: Any) -> Any:
        raise UnsupportedArchError(name)
    return stub

class InlineAsm:
    def __init__(
        self,
        asm_code: str,
        argtypes: Optional[list] = None,
        restype: Any = ctypes.c_long,
        clobbers: Optional[list] = None,
    ):
        self._provided_asm = asm_code
        self._clobbers = list(clobbers) if clobbers else []

        full_asm = asm_code
        if clobbers:
            full_asm = _build_clobber_wrap(asm_code, clobbers)
        self._full_asm = full_asm

        ks = _get_assembler()
        try:
            encoding, _ = ks.asm(full_asm)
        except Exception as e:
            raise AssemblyError(f"Keystone failed to assemble: {e}")

        if encoding is None:
            raise AssemblyError("Assembler produced no output for the given instructions")

        self._machine_code = bytearray(encoding)

        addr, free_fn = _alloc_executable(len(self._machine_code))
        ctypes.memmove(addr, bytes(self._machine_code), len(self._machine_code))

        self._addr = addr
        self._free = free_fn
        self._fn_type = ctypes.CFUNCTYPE(restype, *(argtypes or []))
        self._callable = self._fn_type(addr)

    @property
    def assembly(self) -> str:
        """Full assembly actually fed to the assembler, prologue/epilogue included."""
        return self._full_asm

    @property
    def providedassembly(self) -> str:
        """Exactly what the user wrote, before any clobber wrapping."""
        return self._provided_asm

    @property
    def clobbers(self) -> list:
        return list(self._clobbers)

    @property
    def machinecode(self) -> bytearray:
        """Raw bytes Keystone emitted, as loaded into executable memory."""
        return bytearray(self._machine_code)

    def __call__(self, *args):
        try:
            return self._callable(*args)
        except OSError as e:
            raise ExecutionError(f"Inline asm raised an OS-level fault: {e}")

    def __del__(self):
        try:
            self._free()
        except Exception:
            pass


def inline_asm(asm_code: str, argtypes: Optional[list] = None, restype: Any = int):
    return InlineAsm(
        asm_code,
        argtypes=[_resolve_ctype(t) for t in (argtypes or [])],
        restype=_resolve_ctype(restype),
    )


# --- decorator form: docstring IS the assembly ---

def asm(argtypes=None, restype=int, clobbers=None, arch=None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    resolved_argtypes = [_resolve_ctype(t) for t in (argtypes or [])]
    resolved_restype = _resolve_ctype(restype)

    def decorator(fn):
        key = f"{fn.__module__}.{fn.__qualname__}"

        if not _arch_matches(arch):
            # Wrong platform for this variant - never touch the registry,
            # just hand back whatever's already there (or a stub if nothing matched yet).
            return _ASM_REGISTRY.get(key, _unavailable_stub(fn.__name__))

        doc = fn.__doc__
        if not doc or not doc.strip():
            raise AssemblyError(f"@asm function '{fn.__name__}' has no docstring to assemble")

        compiled = InlineAsm(doc, argtypes=resolved_argtypes, restype=resolved_restype, clobbers=clobbers)

        def wrapper(*args):
            return compiled(*args)

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        wrapper.__qualname__ = fn.__qualname__
        setattr(wrapper, "__magicalpython_asm__", compiled)
        setattr(wrapper, "assembly", compiled.assembly)
        setattr(wrapper, "providedassembly", compiled.providedassembly)
        setattr(wrapper, "clobbers", compiled.clobbers)
        setattr(wrapper, "machinecode", compiled.machinecode)

        _ASM_REGISTRY[key] = wrapper
        return wrapper

    return decorator