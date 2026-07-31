# (C) 2026 ItsThatOneJack (Jack Bacon)
# This Source Code Form is subject to the terms of the Zenith Public License,
# v. 1.0. If you did not receive a copy of the Zenith Public License with this
# software, you can obtain one at <https://itoj.dev/licenses/ZPL-1.0.md>.

from __future__ import annotations

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import atexit
import sys
import traceback
from typing import Callable, List

from .error import Error

_crash_handlers: List[Callable[[BaseException], None]] = []
_defer_callbacks: List[Callable[[], None]] = []
_serious_error_occurred = False # Set to True by the excepthook below when a "serious" error fires.

class LifecycleError(Error):
    pass

def register_crash_handler(fn: Callable[[BaseException], None]) -> None:
    """
    Registers fn to run when an unhandled "serious" error occurs, such as a RuntimeError (or subclass), or any MagicalPython Error subclass, propagating uncaught to the top of the program. fn receives the exception instance.

    Meant for quick emergency telemetry/logging only, keep it minimal. This runs while the program is already in a failing state, any exception raised inside a crash handler is caught and silently ignored so a bad handler can't mask or replace the real error.

    Even crash handlers only run on Python-level unhandled exceptions. They do not run on native crashes such as segfaults or access violations, to run custom code on native crashes, consider writing a Python package in C, as the C code can in fact do that.
    In future there may be a way to achieve this in Python, but as of now there is no easy way.
    """
    _crash_handlers.append(fn)

def unregister_crash_handler(fn: Callable[[BaseException], None]) -> None:
    if fn in _crash_handlers:
        _crash_handlers.remove(fn)

def defer(fn: Callable[[], None]) -> Callable[[], None]:
    """
    Registers fn to run on normal program exit, such as reaching the end of the script, sys.exit(), or any unhandled exception that is not a "serious" one.
    Can be used as a plain call (defer(cleanup)) or as a decorator:

        @defer
        def cleanup():
            ...

    Does NOT run on os._exit(), or on a genuine native crash, both bypass Python's normal interpreter shutdown entirely, so there is no point in the program's lifecycle where this could fire for those cases.
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
            pass # A broken telemetry handler must never mask the real error or cause a second failure.

def _is_serious(exc_type) -> bool:
    return issubclass(exc_type, RuntimeError) or issubclass(exc_type, Error)

def _magicalpython_lifecycle_excepthook(exc_type, exc_value, tb):
    global _serious_error_occurred
    if _is_serious(exc_type):
        _serious_error_occurred = True
        _run_crash_handlers(exc_value)

    # Hand off to whatever excepthook was previously installed, allowing other features such as the sefault crash message to display what happened.
    _previous_excepthook(exc_type, exc_value, tb)

_previous_excepthook = sys.excepthook
sys.excepthook = _magicalpython_lifecycle_excepthook

def _run_defer_callbacks():
    if _serious_error_occurred:
        return # A serious error occurred, defer callbacks are specifically excluded from this case.
    for fn in list(_defer_callbacks):
        try:
            fn()
        except Exception:
            traceback.print_exc() # A defer callback failing is a normal bug in normal-exit cleanup code, show it.

atexit.register(_run_defer_callbacks)