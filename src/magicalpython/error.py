__magicalpython_internal__ = True # Hide from tracebacks.

import os
import sys
import builtins
import linecache
from colorama import Fore, Style, just_fix_windows_console
just_fix_windows_console()

class Error(BaseException):
    def __init__(self, message: str = "An undefined error has occurred!", *, errortype: str = ""):
        self.errortype = errortype or type(self).__name__
        self.message = message
        super().__init__(self.message)

    def __unwrap__(self):
        raise self

    def __str__(self) -> str:
        return self.message

def _is_internal_frame(frame) -> bool:
    return bool(frame.f_globals.get("__magicalpython_internal__", False))

def _iter_kept_frames(tb):
    """Yield (frame, lineno) for every tb frame not marked internal."""
    node = tb
    while node is not None:
        if not _is_internal_frame(node.tb_frame):
            yield node.tb_frame, node.tb_lineno
        node = node.tb_next

def _format_frame(frame, lineno: int) -> str:
    filename = frame.f_code.co_filename
    func_name = frame.f_code.co_name
    source = linecache.getline(filename, lineno).strip()
    short_path = os.path.relpath(filename)

    lines = [
        f"{Style.DIM}{Fore.RED}    File {Style.NORMAL}\"{short_path}\"{Style.DIM}, "
        f"line {Style.NORMAL}{lineno}{Style.DIM}, in {Style.NORMAL}{Style.BRIGHT}{func_name}{Style.RESET_ALL}"
    ]
    if source:
        lines.append(f"{Fore.RED}        {Style.BRIGHT}{source}{Style.RESET_ALL}")
    return "\n".join(lines)

def _format_traceback(tb) -> str:
    frames = list(_iter_kept_frames(tb))
    if not frames:
        return ""
    header = f"{Fore.RED}{Style.DIM}Error traceback (most recent call last):{Style.RESET_ALL}"
    body = "\n".join(_format_frame(frame, lineno) for frame, lineno in frames)
    return f"{header}\n{body}"

def _magicalpython_excepthook(exc_type, exc_value, tb):
    if not issubclass(exc_type, Error):
        sys.__excepthook__(exc_type, exc_value, tb)
        return

    formatted_tb = _format_traceback(tb)
    errortype = getattr(exc_value, "errortype", exc_type.__name__)
    message = getattr(exc_value, "message", str(exc_value))

    if formatted_tb:
        sys.stderr.write(f"{Fore.RED}{Style.BRIGHT}This Python++ file has encountered a fatal error and exited.\nYou can see the traceback details below.{Style.RESET_ALL}\n\n")
        sys.stderr.write(formatted_tb + "\n")
    sys.stderr.write(
        "\n"
        f"{Fore.RED}{Style.BRIGHT}[ERROR] {errortype}:{Style.RESET_ALL}"
        f"{Fore.RED} {message}{Style.RESET_ALL}\n"
    )
    sys.exit(1)

sys.excepthook = _magicalpython_excepthook

def _make_enhanced(builtin_exc_type):
    class Enhanced(Error, builtin_exc_type):
        def __init__(self, message: str = "", *, errortype: str = ""):
            Error.__init__(self, message, errortype=errortype)
    Enhanced.__name__ = builtin_exc_type.__name__
    Enhanced.__qualname__ = builtin_exc_type.__name__
    return Enhanced

ValueError = _make_enhanced(builtins.ValueError)
TypeError = _make_enhanced(builtins.TypeError)
RuntimeError = _make_enhanced(builtins.RuntimeError)
KeyError = _make_enhanced(builtins.KeyError)
IndexError = _make_enhanced(builtins.IndexError)
Error

"""
ArithmeticError
BufferError
LookupError
AssertionError
AttributeError
EOFError
FloatingPointError
GeneratorExit # NOT THIS ONE
ImportError
ModuleNotFoundError
IndexError
KeyError
KeyboardInterrupt # NOT THIS ONE
MemoryError
NameError
NotImplementedError
OSError
OverflowError
PythonFinalizationError
RecursionError
ReferenceError
RuntimeError
StopIteration
StopAsyncIteration
SyntaxError
IndentationError
SystemError
SystemExit # NOT THIS ONE
TypeError
UnboundLocalError
UnicodeError
UnicodeEncodeError
UnicodeDecodeError
UnicodeTranslateError
ValueError
ZeroDivisionError
EnvironmentError
IOError
WindowsError
BlockingIOError
ChildProcessError
ConnectionError
BrokenPipeError
ConnectionAbortedError
ConnectionRefusedError
ConnectionResetError
FileExistsError
FileNotFoundError
InterruptedError
IsADirectoryError
NotADirectoryError
PermissionError
ProcessLookupError
TimeoutError
"""