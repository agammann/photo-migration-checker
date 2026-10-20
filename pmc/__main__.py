import argparse
import os
import socket
from pathlib import Path

import uvicorn

from .api import create_app


def main():
    parser = argparse.ArgumentParser(description="Read-only local Google Takeout to Immich verification")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("PMC_DATA_DIR", ".pmc")))
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        # Reserve the endpoint before exposing a capability. Windows REUSEADDR
        # would permit another process to bind the same address.
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", args.port))
            listener.listen(128)
        except OSError:
            parser.exit(1, "The local port is unavailable. Stop the other app or choose another --port.\n")
        app = create_app(args.data_dir)
        port = listener.getsockname()[1]
        print(f"Photo Migration Checker: http://127.0.0.1:{port}/#session={app.state.token}", flush=True)
        print("Keep this private link in this account. Press Ctrl+C to stop; restarting creates a new link.", flush=True)
        config = uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="warning")
        uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    main()
