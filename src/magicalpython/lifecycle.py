from __future__ import annotations

__magicalpython_internal__ = True

import atexit
import sys
import traceback
from typing import Callable, List

from .error import Error

_crash_handlers: List[Callable[[BaseException], None]] = []
_defer_callbacks: List[Callable[[], None]] = []
_serious_error_occurred = False  # set True by the excepthook below when a "serious" error fires

class LifecycleError(Error):
    pass

def register_crash_handler(fn: Callable[[BaseException], None]) -> None:
    """
    Registers fn to run when an unhandled "serious" error occurs - a
    RuntimeError (or subclass), or any Python++ Error subclass, propagating
    uncaught to the top of the program. fn receives the exception instance.

    Meant for quick emergency telemetry/logging ONLY - keep it minimal. This
    runs while the program is already in a failing state; any exception
    raised inside a crash handler is caught and silently ignored so a bad
    handler can't mask or replace the real error.

    IMPORTANT LIMITATION: this only covers Python-level unhandled exceptions.
    It does NOT run on a genuine native crash (segfault/access violation) -
    those are caught by the separate native guard (see native_guard.py),
    which prints a message and terminates the process directly. Reliably
    calling back into arbitrary Python code from inside a real hardware
    fault handler is not something this project attempts, since the
    interpreter's own state may already be corrupted by that point - trying
    anyway would risk exactly the further memory corruption this feature
    exists to help avoid.
    """
    _crash_handlers.append(fn)

def unregister_crash_handler(fn: Callable[[BaseException], None]) -> None:
    if fn in _crash_handlers:
        _crash_handlers.remove(fn)

def defer(fn: Callable[[], None]) -> Callable[[], None]:
    """
    Registers fn to run on normal program exit - end of script, sys.exit(),
    or any unhandled exception that ISN'T a "serious" one (RuntimeError/Error
    subclasses - see register_crash_handler for those instead).

    Can be used as a plain call (defer(cleanup)) or as a decorator:

        @defer
        def cleanup():
            ...

    Does NOT run on os._exit(), or on a genuine native crash - both bypass
    Python's normal interpreter shutdown entirely, so there is no point in
    the program's lifecycle where this could fire for those cases.
    """
    _defer_callbacks.append(fn)
    return fn

def undefer(fn: Callable[[], None]) -> None:
    if fn in _defer_callbacks:
        _defer_callbacks.remove(fn)

def _run_crash_handlers(exc: BaseException) -> None:
    for handler in list(_crash_handlers):
        try:
            handler(exc)
        except Exception:
            pass  # a broken telemetry handler must never mask the real error or cause a second failure

def _is_serious(exc_type) -> bool:
    return issubclass(exc_type, RuntimeError) or issubclass(exc_type, Error)

def _magicalpython_lifecycle_excepthook(exc_type, exc_value, tb):
    global _serious_error_occurred
    if _is_serious(exc_type):
        _serious_error_occurred = True
        _run_crash_handlers(exc_value)

    # hand off to whatever excepthook was previously installed (e.g. the
    # styled Error traceback printer) so this doesn't change existing
    # display behavior - it only adds the crash-handler dispatch in front
    _previous_excepthook(exc_type, exc_value, tb)

_previous_excepthook = sys.excepthook
sys.excepthook = _magicalpython_lifecycle_excepthook

def _run_defer_callbacks():
    if _serious_error_occurred:
        return  # a serious error occurred - defer callbacks are specifically excluded from this case
    for fn in list(_defer_callbacks):
        try:
            fn()
        except Exception:
            traceback.print_exc()  # a defer callback failing is a normal bug in normal-exit cleanup code - show it

atexit.register(_run_defer_callbacks)