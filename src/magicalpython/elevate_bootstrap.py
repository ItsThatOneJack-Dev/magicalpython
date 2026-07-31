# This file is the MagicalPython elevation bootstrap.
# It is not meant to be imported or run directly.
# relaunch_elevated spawns this automatically as the elevated process.

# This file imports the target script as a plain module, so the `if __name__ == <...>` guard never executes.
# This means we can wait for it to run through and all functions decorate, and then we can find the handler registered with `@elevated_entrypoint`.
# We then connect to the waiting unprivileged process, receive the designated handler name, plus a payload, then we call the handler and exit.
# This way only code stemming from the handler gets a chance to run.

import sys
import os
import importlib.util
from multiprocessing.connection import Client

def main():
    if len(sys.argv) != 5:
        print("Usage: elevate_bootstrap.py <script_path> <host> <port> <token>", file=sys.stderr)
        sys.exit(1)

    script_path, host, port_str, token = sys.argv[1:5]
    port = int(port_str)

    sys.path.insert(0, os.path.dirname(os.path.abspath(script_path)))

    spec = importlib.util.spec_from_file_location("__magicalpython_handoff_target__", script_path)
    if spec is None or spec.loader is None:
        print(f"Could not load {script_path}", file=sys.stderr)
        sys.exit(1)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module) # Runs top-level code only, __name__ != "__main__" here.

    from magicalpython.elevate import _HANDLER_REGISTRY # Same package/process, the registry is populated now.

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