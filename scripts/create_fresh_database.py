#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_fresh_database import (  # noqa: E402
    DATABASE_SIDECAR_SUFFIXES,
    verify_fresh_database,
)
from server import MedicationStore  # noqa: E402


class FreshDatabaseCreationError(RuntimeError):
    pass


def create_fresh_database(db_path: Path) -> dict[str, Any]:
    path = Path(db_path).absolute()
    if not path.parent.is_dir():
        raise FreshDatabaseCreationError(
            f"database directory does not exist: {path.parent}"
        )

    existing_sidecars = [
        Path(f"{path}{suffix}")
        for suffix in DATABASE_SIDECAR_SUFFIXES
        if Path(f"{path}{suffix}").exists()
        or Path(f"{path}{suffix}").is_symlink()
    ]
    if existing_sidecars:
        raise FreshDatabaseCreationError(
            "refusing existing database sidecars: "
            + ", ".join(sidecar.name for sidecar in existing_sidecars)
        )

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        if exc.errno in {errno.EEXIST, errno.ELOOP}:
            raise FreshDatabaseCreationError(
                f"refusing existing database path: {path}"
            ) from exc
        raise FreshDatabaseCreationError(f"cannot create database: {exc}") from exc
    else:
        os.close(descriptor)

    try:
        MedicationStore(path)
        path.chmod(0o600)
        return verify_fresh_database(
            path, required_mode=0o600, sidecar_policy="wal"
        )
    except Exception as exc:
        raise FreshDatabaseCreationError(
            "fresh database initialization failed; leave the files in place "
            f"for investigation and do not start the service: {exc}"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exclusively create and verify a new TakeTime database."
    )
    parser.add_argument("database", type=Path)
    args = parser.parse_args()

    try:
        report = create_fresh_database(args.database)
    except FreshDatabaseCreationError as exc:
        print(f"fresh database creation failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
