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

ArithmeticError = _make_enhanced(builtins.ArithmeticError)
BufferError = _make_enhanced(builtins.BufferError)
LookupError = _make_enhanced(builtins.LookupError)
AssertionError = _make_enhanced(builtins.AssertionError)
AttributeError = _make_enhanced(builtins.AttributeError)
EOFError = _make_enhanced(builtins.EOFError)
FloatingPointError = _make_enhanced(builtins.FloatingPointError)
ImportError = _make_enhanced(builtins.ImportError)
ModuleNotFoundError = _make_enhanced(builtins.ModuleNotFoundError)
IndexError = _make_enhanced(builtins.IndexError)
KeyError = _make_enhanced(builtins.KeyError)
MemoryError = _make_enhanced(builtins.MemoryError)
NameError = _make_enhanced(builtins.NameError)
NotImplementedError = _make_enhanced(builtins.NotImplementedError)
OSError = _make_enhanced(builtins.OSError)
OverflowError = _make_enhanced(builtins.OverflowError)
RecursionError = _make_enhanced(builtins.RecursionError)
ReferenceError = _make_enhanced(builtins.ReferenceError)
RuntimeError = _make_enhanced(builtins.RuntimeError)
SyntaxError = _make_enhanced(builtins.SyntaxError)
IndentationError = _make_enhanced(builtins.IndentationError)
SystemError = _make_enhanced(builtins.SystemError)
TypeError = _make_enhanced(builtins.TypeError)
UnboundLocalError = _make_enhanced(builtins.UnboundLocalError)
UnicodeError = _make_enhanced(builtins.UnicodeError)
UnicodeEncodeError = _make_enhanced(builtins.UnicodeEncodeError)
UnicodeDecodeError = _make_enhanced(builtins.UnicodeDecodeError)
UnicodeTranslateError = _make_enhanced(builtins.UnicodeTranslateError)
ValueError = _make_enhanced(builtins.ValueError)
ZeroDivisionError = _make_enhanced(builtins.ZeroDivisionError)
EnvironmentError = _make_enhanced(builtins.EnvironmentError)
IOError = _make_enhanced(builtins.IOError)
WindowsError = _make_enhanced(builtins.WindowsError)
BlockingIOError = _make_enhanced(builtins.BlockingIOError)
ChildProcessError = _make_enhanced(builtins.ChildProcessError)
ConnectionError = _make_enhanced(builtins.ConnectionError)
BrokenPipeError = _make_enhanced(builtins.BrokenPipeError)
ConnectionAbortedError = _make_enhanced(builtins.ConnectionAbortedError)
ConnectionRefusedError = _make_enhanced(builtins.ConnectionRefusedError)
ConnectionResetError = _make_enhanced(builtins.ConnectionResetError)
FileExistsError = _make_enhanced(builtins.FileExistsError)
FileNotFoundError = _make_enhanced(builtins.FileNotFoundError)
InterruptedError = _make_enhanced(builtins.InterruptedError)
IsADirectoryError = _make_enhanced(builtins.IsADirectoryError)
NotADirectoryError = _make_enhanced(builtins.NotADirectoryError)
PermissionError = _make_enhanced(builtins.PermissionError)
ProcessLookupError = _make_enhanced(builtins.ProcessLookupError)
TimeoutError = _make_enhanced(builtins.TimeoutError)