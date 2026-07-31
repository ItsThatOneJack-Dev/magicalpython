# (C) 2026 ItsThatOneJack (Jack Bacon)
# This Source Code Form is subject to the terms of the Zenith Public License,
# v. 1.0. If you did not receive a copy of the Zenith Public License with this
# software, you can obtain one at <https://itoj.dev/licenses/ZPL-1.0.md>.

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import ctypes
import os
import sys

_LIB = None

def install_segfault_guard():
    global _LIB
    if _LIB is not None:
        return # Already installed, do nothing.

    here = os.path.dirname(__file__)
    if sys.platform == "win32":
        path = os.path.join(here, "native", "segfault_msg.dll")
    else:
        path = os.path.join(here, "native", "segfault_msg.so")

    if not os.path.exists(path):
        raise RuntimeError(
            f"MagicalPython native guard not built for this platform: {path} not found."
        )

    _LIB = ctypes.CDLL(path)
    _LIB.magicalpython_install_segfault_handler.argtypes = []
    _LIB.magicalpython_install_segfault_handler.restype = None
    _LIB.magicalpython_install_segfault_handler()