from __future__ import annotations

__magicalpython_internal__ = True # This allows any traceback frames from this file to be removed from printed tracebacks. Makes them look better.

import os
import sys
import pickle
import subprocess
import ctypes
from multiprocessing.connection import Listener
from typing import Any, Callable, Dict, Optional

from .error import Error
from .pointer import Pointer

class ElevationError(Error):
    pass

class UnpicklableHandoffError(ElevationError):
    def __init__(self, key, value):
        super().__init__(
            f"Cannot hand off payload key {key!r} ({type(value).__name__}): "
            f"Pointer and other process-specific objects can't be meaningfully "
            f"reconstructed in a different process. Pass raw data (addresses as "
            f"plain ints, pids, etc.) and re-derive anything process-specific on "
            f"the elevated side instead."
        )

# Populated by @elevated_entrypoint. The bootstrap process fills this in by
# importing the target script fresh.
_HANDLER_REGISTRY: Dict[str, Callable[[dict], Any]] = {}

def elevated_entrypoint(fn: Callable[[dict], Any]) -> Callable[[dict], Any]:
    """
    Marks a function as a valid `relaunch_elevated()` target. Registered by qualified name.

    WARNING: You must use a `if __name__ == "__main__"` guard if you plan to use the elevation system, or your entire script will re-run from the beginning after elevation.
    """
    key = fn.__qualname__
    _HANDLER_REGISTRY[key] = fn
    fn.__magicalpython_handler_name__ = key # type: ignore[attr-defined]
    return fn

def _validate_payload(payload: dict) -> None:
    for key, value in payload.items():
        if isinstance(value, Pointer):
            raise UnpicklableHandoffError(key, value)
        try:
            pickle.dumps(value)
        except Exception:
            raise ElevationError(f"Payload key {key!r} ({type(value).__name__}) is not picklable")

def is_elevated() -> bool:
    """
    Returns a boolean for whether this process is elevated.
    """
    if sys.platform == "win32":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin()) # type: ignore
        except Exception:
            return False
    return os.geteuid() == 0 # type: ignore[attr-defined]

def _bootstrap_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "elevate_bootstrap.py")

def _relaunch_windows(script_path: str, host: str, port: int, token: str) -> None:
    shell32 = ctypes.windll.shell32  # type: ignore
    params = f'"{_bootstrap_path()}" "{script_path}" "{host}" "{port}" "{token}"'
    ret = shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    if ret <= 32:
        raise ElevationError(
            f"ShellExecuteW('runas') failed (code {ret}) - the UAC prompt was "
            f"likely declined, or {sys.executable} could not be launched."
        )

def _relaunch_posix(script_path: str, host: str, port: int, token: str) -> None:
    cmd = ["sudo", sys.executable, _bootstrap_path(), script_path, host, str(port), token]
    subprocess.Popen(cmd)

def relaunch_elevated(
    handler: Callable[[dict], Any],
    payload: Optional[dict] = None,
    timeout: float = 120.0,
) -> None:
    """
    Relaunches as an elevated bootstrap process (UAC prompt on Windows, sudo
    on Linux/macOS).

    `payload` must be a plain, picklable dict - no Pointer or other process-specific objects, pass what is needed to re-derive those on the elevated side instead.

    Once the elevated process confirms it received the handoff, THIS (unprivileged) process exits immediately via os._exit(0).

    WARNING: You must use a `if __name__ == "__main__"` guard if you plan to use the elevation system, or your entire script will re-run from the beginning after elevation.
    """
    payload = payload or {}
    _validate_payload(payload)

    handler_name = getattr(handler, "__magicalpython_handler_name__", None)
    if handler_name is None or handler_name not in _HANDLER_REGISTRY:
        raise ElevationError(
            f"{getattr(handler, '__name__', handler)!r} is not registered, decorate it with @elevated_entrypoint first."
        )

    if is_elevated():
        # We're already elevated, no need to relaunch, just run the handler.
        handler(payload)
        return

    script_path = os.path.abspath(sys.argv[0])

    token = os.urandom(16).hex()
    listener = Listener(("127.0.0.1", 0), authkey=token.encode())
    host, port = listener.address
    port = int(port) # listener.address is typed as str | tuple[str, int] in typeshed, we know it's always the tuple form here.

    if sys.platform == "win32":
        _relaunch_windows(script_path, host, port, token)
    else:
        _relaunch_posix(script_path, host, port, token)

    listener._listener._socket.settimeout(timeout) # type: ignore[attr-defined]
    try:
        conn = listener.accept()
    except Exception:
        listener.close()
        raise ElevationError(
            "Elevated process never connected back, the UAC/sudo prompt was likely declined, or it timed out."
        )

    conn.send({"handler": handler_name, "payload": payload})
    ack = conn.recv()
    conn.close()
    listener.close()

    if ack != "ok":
        raise ElevationError(f"Elevated process reported a problem: {ack}")

    os._exit(0)