import argparse
import os
from pathlib import Path

import uvicorn

from .api import create_app


def main():
    parser = argparse.ArgumentParser(description="Read-only local Google Takeout to Immich verification")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("PMC_DATA_DIR", ".pmc")))
    args = parser.parse_args()
    print(f"Photo Migration Checker: http://127.0.0.1:{args.port}")
    print("Keep this terminal open. Press Ctrl+C to stop. No automatic startup is installed.")
    uvicorn.run(create_app(args.data_dir), host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
