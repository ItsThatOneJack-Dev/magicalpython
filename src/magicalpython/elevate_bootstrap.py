"""
Python++ elevation bootstrap.

Not meant to be imported or run directly by users - relaunch_elevated()
spawns this automatically as the elevated process.

Imports the target script as a plain MODULE (not as __main__), so any
`if __name__ == "__main__":` guard in it never executes here - only its
top-level defs/decorators run, which is exactly enough to register any
@elevated_entrypoint handlers. Then connects back to the waiting
unprivileged process, receives the designated handler name + payload,
calls that handler directly, and exits. Nothing else in the target
script ever runs in this process.
"""

import sys
import os
import importlib.util
from multiprocessing.connection import Client


def main():
    if len(sys.argv) != 5:
        print("usage: elevate_bootstrap.py <script_path> <host> <port> <token>", file=sys.stderr)
        sys.exit(1)

    script_path, host, port_str, token = sys.argv[1:5]
    port = int(port_str)

    # so the target script can still import its own sibling modules normally
    sys.path.insert(0, os.path.dirname(os.path.abspath(script_path)))

    spec = importlib.util.spec_from_file_location("__magicalpython_handoff_target__", script_path)
    if spec is None or spec.loader is None:
        print(f"Could not load {script_path}", file=sys.stderr)
        sys.exit(1)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # runs top-level code only; __name__ != "__main__" here

    from magicalpython.elevate import _HANDLER_REGISTRY  # same package/process, registry now populated

    conn = Client((host, port), authkey=token.encode())
    try:
        message = conn.recv()
        handler_name = message["handler"]
        payload = message["payload"]

        handler = _HANDLER_REGISTRY.get(handler_name)
        if handler is None:
            conn.send(f"unknown handler: {handler_name}")
            sys.exit(1)

        conn.send("ok")
        conn.close()

        handler(payload)
    except Exception as e:
        try:
            conn.send(f"error: {e}")
            conn.close()
        except Exception:
            pass
        raise

    sys.exit(0)


if __name__ == "__main__":
    main()