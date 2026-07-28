#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SQLITE_HEADER = b"SQLite format 3\x00"
SQLITE_WAL_HEADERS = (b"\x37\x7f\x06\x82", b"\x37\x7f\x06\x83")
SQLITE_SHM_HEADERS = (b"\x18\xe2\x2d\x00", b"\x00\x2d\xe2\x18")
SQLITE_JOURNAL_HEADER = b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7"
ARCHIVE_HEADERS = (
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
    b"\x1f\x8b",
    b"BZh",
    b"\xfd7zXZ\x00",
    b"7z\xbc\xaf\x27\x1c",
    b"Rar!\x1a\x07",
)
FORBIDDEN_PARTS = {
    "data",
    "backups",
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".pytest_cache",
}
FORBIDDEN_SUFFIXES = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".sqlite",
    ".sqlite3",
    "-journal",
    "-shm",
    "-wal",
    ".journal",
    ".shm",
    ".wal",
    ".pyc",
    ".pyo",
)
FORBIDDEN_ARCHIVE_SUFFIXES = (
    ".7z",
    ".bz2",
    ".gz",
    ".rar",
    ".tar",
    ".tgz",
    ".xz",
    ".zip",
)
REQUIRED_FILES = {
    "README.md",
    "示例计划.md",
    "DEPLOYMENT.md",
    "server.py",
    "public/app.js",
    "public/access.html",
    "public/access.js",
    "public/demo.html",
    "public/demo.js",
    "public/index.html",
    "public/styles.css",
    "public/assets/pill-organizer-480.avif",
    "public/assets/pill-organizer-480.jpg",
    "public/assets/pill-organizer-800.avif",
    "public/assets/pill-organizer-800.jpg",
    "public/assets/pill-organizer-1400.avif",
    "public/assets/pill-organizer-1400.jpg",
    "public/assets/taketime-mark.svg",
    "public/assets/taketime-slogan-serif.woff2",
    "scripts/create_fresh_database.py",
    "scripts/verify_fresh_database.py",
    "scripts/verify_release_artifact.py",
}


class ReleaseArtifactVerificationError(RuntimeError):
    pass


def verify_release_artifact(root: Path) -> dict[str, Any]:
    release_root = Path(root).resolve()
    if not release_root.is_dir():
        raise ReleaseArtifactVerificationError(
            f"release directory does not exist: {release_root}"
        )

    files: set[str] = set()
    issues: list[str] = []
    reported_forbidden_directories: set[str] = set()
    for path in release_root.rglob("*"):
        relative = path.relative_to(release_root)
        normalized_parts = tuple(part.lower() for part in relative.parts)
        forbidden_index = next(
            (
                index
                for index, part in enumerate(normalized_parts)
                if part in FORBIDDEN_PARTS
            ),
            None,
        )
        if forbidden_index is not None:
            forbidden_path = Path(*relative.parts[: forbidden_index + 1]).as_posix()
            if forbidden_path not in reported_forbidden_directories:
                issues.append(f"forbidden directory: {forbidden_path}")
                reported_forbidden_directories.add(forbidden_path)
            continue
        if path.is_symlink():
            issues.append(f"symbolic link is not allowed: {relative}")
            continue
        if not path.is_file():
            continue

        relative_name = relative.as_posix()
        files.add(relative_name)
        lower_name = path.name.lower()
        if lower_name.endswith(FORBIDDEN_SUFFIXES):
            issues.append(f"database-like file is not allowed: {relative}")
            continue
        if lower_name.endswith(FORBIDDEN_ARCHIVE_SUFFIXES):
            issues.append(f"archive file is not allowed: {relative}")
            continue
        try:
            with path.open("rb") as handle:
                header = handle.read(512)
        except OSError as exc:
            issues.append(f"cannot inspect {relative}: {exc}")
            continue
        if header.startswith(SQLITE_HEADER):
            issues.append(f"SQLite content is not allowed: {relative}")
        elif header.startswith(SQLITE_WAL_HEADERS):
            issues.append(f"SQLite WAL content is not allowed: {relative}")
        elif header.startswith(SQLITE_SHM_HEADERS):
            issues.append(f"SQLite SHM content is not allowed: {relative}")
        elif header.startswith(SQLITE_JOURNAL_HEADER):
            issues.append(f"SQLite journal content is not allowed: {relative}")
        elif header.startswith(ARCHIVE_HEADERS) or header[257:262] == b"ustar":
            issues.append(f"archive content is not allowed: {relative}")

    missing = sorted(REQUIRED_FILES - files)
    if missing:
        issues.append(f"missing required release files: {', '.join(missing)}")
    if issues:
        raise ReleaseArtifactVerificationError("; ".join(issues))

    return {
        "status": "ok",
        "releaseRoot": str(release_root),
        "fileCount": len(files),
        "databaseFiles": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject database files and SQLite content in a TakeTime release."
    )
    parser.add_argument("release_directory", type=Path)
    args = parser.parse_args()

    try:
        report = verify_release_artifact(args.release_directory)
    except ReleaseArtifactVerificationError as exc:
        print(f"release artifact verification failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
