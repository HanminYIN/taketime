#!/usr/bin/env python3
"""Run TakeTime against a disposable database for browser tests."""

from __future__ import annotations

import argparse
import signal
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server import DEFAULT_DB_PATH, create_server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="taketime-playwright-") as temp_dir:
        db_path = Path(temp_dir) / "medication.db"
        if db_path.resolve() == DEFAULT_DB_PATH.resolve():
            raise RuntimeError("Browser tests must not use the application database")

        server = create_server(
            args.host,
            args.port,
            db_path,
            demo_phrase="测试演示口令",
        )

        def request_shutdown(_signum: int, _frame: object) -> None:
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGINT, request_shutdown)
        signal.signal(signal.SIGTERM, request_shutdown)
        print(
            f"TakeTime browser-test server: http://{args.host}:{server.server_port}",
            flush=True,
        )
        print(f"Disposable database: {db_path}", flush=True)
        try:
            server.serve_forever(poll_interval=0.1)
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
