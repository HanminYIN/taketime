#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from http.cookiejar import CookieJar
import json
import os
import pwd
import sqlite3
import stat
import sys
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


EXPECTED_SCHEMA_VERSION = 5
EXPECTED_PREFERENCES = ("07:00", "07:45", "12:15", "17:30", "21:00")
EXPECTED_PLAN = (
    ("示例药 A", "1份", "演示：保持相邻间隔", "wake", 0, 10),
    ("示例药 B", "1份", "演示：跟随起床作息", "wake", 0, 20),
    ("示例药 C", "1份", "演示：保持相邻间隔", "breakfast", -15, 30),
    ("示例药 D", "1份", "演示：跟随用餐", "breakfast", 0, 40),
    ("示例药 E", "1份", "演示：保持相邻间隔", "breakfast", 20, 50),
    ("示例药 C", "1份", "演示：保持相邻间隔", "lunch", -15, 60),
    ("示例药 A", "1份", "演示：保持相邻间隔", "lunch", 0, 65),
    ("示例药 E", "1份", "演示：保持相邻间隔", "lunch", 20, 70),
    ("示例药 C", "1份", "演示：保持相邻间隔", "dinner", -15, 80),
    ("示例药 A", "1份", "演示：保持相邻间隔", "dinner", 0, 85),
    ("示例药 D", "1份", "演示：跟随用餐", "dinner", 0, 90),
    ("示例药 E", "1份", "演示：保持相邻间隔", "dinner", 20, 100),
    ("示例药 F", "1份", "演示：跟随睡前作息", "bedtime", 0, 110),
)
EXPECTED_TIMING_MODES = {
    "示例药 A": "interval",
    "示例药 B": "routine",
    "示例药 C": "interval",
    "示例药 D": "meal",
    "示例药 E": "interval",
    "示例药 F": "routine",
}
HISTORY_TABLES = (
    "daily_context",
    "daily_instances",
    "intake_logs",
    "wake_events",
)
EXPECTED_TABLES = {
    "preferences",
    "daily_context",
    "wake_events",
    "medications",
    "schedule_items",
    "daily_instances",
    "intake_logs",
}
DATABASE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


class FreshDatabaseVerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FreshDatabaseVerificationError(message)


def database_identity(db_path: Path) -> str:
    path = Path(db_path).resolve(strict=True)
    file_stat = path.stat()
    identity = f"{path}\0{file_stat.st_dev}\0{file_stat.st_ino}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def validate_sidecars(db_path: Path, policy: str) -> None:
    require(policy in {"forbid", "wal"}, f"unknown sidecar policy: {policy}")
    sidecars = {
        suffix: Path(f"{db_path}{suffix}") for suffix in DATABASE_SIDECAR_SUFFIXES
    }
    present = {
        suffix: path
        for suffix, path in sidecars.items()
        if path.exists() or path.is_symlink()
    }
    if policy == "forbid":
        require(
            not present,
            "fresh database must not have WAL, SHM, or journal sidecars: "
            + ", ".join(path.name for path in present.values()),
        )
        return

    journal = present.get("-journal")
    require(journal is None, "active WAL database must not have a rollback journal")
    for suffix in ("-wal", "-shm"):
        sidecar = present.get(suffix)
        if sidecar is None:
            continue
        require(not sidecar.is_symlink(), f"database sidecar must not be a symbolic link: {sidecar.name}")
        require(sidecar.is_file(), f"database sidecar must be a regular file: {sidecar.name}")


def verify_fresh_database(
    db_path: Path,
    *,
    required_owner: str | None = None,
    required_mode: int | None = None,
    api_url: str | None = None,
    api_access_phrase: str | None = None,
    sidecar_policy: str | None = None,
) -> dict[str, Any]:
    policy = sidecar_policy or ("wal" if api_url is not None else "forbid")
    requested_path = Path(db_path)
    require(not requested_path.is_symlink(), "database path must not be a symbolic link")
    path = requested_path.resolve()
    require(path.is_file(), f"database does not exist: {path}")
    validate_sidecars(path, policy)

    file_stat = path.stat()
    initial_database_identity = database_identity(path)
    file_mode = stat.S_IMODE(file_stat.st_mode)
    if required_mode is not None:
        require(
            file_mode == required_mode,
            f"expected database mode {required_mode:04o}, got {file_mode:04o}",
        )
    if required_owner is not None:
        try:
            owner = pwd.getpwuid(file_stat.st_uid).pw_name
        except KeyError as exc:
            raise FreshDatabaseVerificationError(
                f"database owner uid is unknown: {file_stat.st_uid}"
            ) from exc
        require(
            owner == required_owner,
            f"expected database owner {required_owner}, got {owner}",
        )

    uri = f"{path.as_uri()}?mode=ro"
    if policy == "forbid":
        uri += "&immutable=1"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
            integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
            require(integrity == ["ok"], f"integrity_check failed: {integrity}")

            foreign_key_issues = db.execute("PRAGMA foreign_key_check").fetchall()
            require(
                not foreign_key_issues,
                f"foreign_key_check found {len(foreign_key_issues)} issue(s)",
            )

            schema_version = db.execute("PRAGMA user_version").fetchone()[0]
            require(
                schema_version == EXPECTED_SCHEMA_VERSION,
                f"expected schema version {EXPECTED_SCHEMA_VERSION}, got {schema_version}",
            )

            tables = {
                row[0]
                for row in db.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
            require(
                tables == EXPECTED_TABLES,
                f"unexpected database tables: {sorted(tables ^ EXPECTED_TABLES)}",
            )
            views_or_triggers = db.execute(
                """
                SELECT type, name FROM sqlite_master
                WHERE type IN ('view', 'trigger') AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
            require(
                not views_or_triggers,
                f"unexpected views or triggers: {views_or_triggers}",
            )
            freelist_count = db.execute("PRAGMA freelist_count").fetchone()[0]
            require(
                freelist_count == 0,
                f"fresh database must have an empty freelist, got {freelist_count}",
            )

            medications = tuple(
                db.execute(
                    """
                    SELECT id, name, active, revision, timing_mode,
                           adjust_after_intake, max_auto_shift_minutes
                    FROM medications ORDER BY id
                    """
                ).fetchall()
            )
            expected_medication_names = tuple(dict.fromkeys(item[0] for item in EXPECTED_PLAN))
            expected_medications = tuple(
                (
                    index,
                    name,
                    1,
                    1,
                    EXPECTED_TIMING_MODES[name],
                    int(EXPECTED_TIMING_MODES[name] == "interval"),
                    120,
                )
                for index, name in enumerate(expected_medication_names, start=1)
            )
            require(
                medications == expected_medications,
                "fresh database must contain exactly 6 initial active medications",
            )
            active_medications = len(medications)

            plan = tuple(
                db.execute(
                    """
                    SELECT s.id, s.medication_id, s.name, s.dose,
                           s.instructions, s.anchor, s.offset_minutes,
                           s.sort_order, s.active
                    FROM schedule_items AS s
                    ORDER BY s.sort_order, s.id
                    """
                ).fetchall()
            )
            medication_ids = {
                name: index for index, name in enumerate(expected_medication_names, start=1)
            }
            expected_plan = tuple(
                (index, medication_ids[item[0]], *item, 1)
                for index, item in enumerate(EXPECTED_PLAN, start=1)
            )
            require(plan == expected_plan, "active plan does not match the release default")
            active_schedules = len(plan)

            sequences = dict(
                db.execute(
                    """
                    SELECT name, seq FROM sqlite_sequence
                    WHERE name IN ('medications', 'schedule_items')
                    """
                ).fetchall()
            )
            require(
                sequences == {"medications": 6, "schedule_items": 13},
                f"unexpected initial SQLite sequences: {sequences}",
            )

            preferences = db.execute(
                """
                SELECT wake_time, breakfast_time, lunch_time, dinner_time,
                       bedtime_time
                FROM preferences
                WHERE id = 1
                """
            ).fetchone()
            preference_count = db.execute(
                "SELECT COUNT(*) FROM preferences"
            ).fetchone()[0]
            require(
                preference_count == 1 and preferences == EXPECTED_PREFERENCES,
                "fresh database preferences do not match the release default",
            )

            history_rows = {
                table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in HISTORY_TABLES
            }
            for table, count in history_rows.items():
                require(count == 0, f"{table} must be empty, found {count} row(s)")
    except sqlite3.Error as exc:
        raise FreshDatabaseVerificationError(f"database check failed: {exc}") from exc

    validate_sidecars(path, policy)
    require(
        database_identity(path) == initial_database_identity,
        "verified database file changed during direct checks",
    )

    api_verified = False
    if api_url is not None:
        base_url = api_url.rstrip("/")
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        try:
            if api_access_phrase:
                access_request = Request(
                    f"{base_url}/api/access",
                    data=json.dumps(
                        {"phrase": api_access_phrase}, ensure_ascii=False
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with opener.open(access_request, timeout=5) as response:
                    access_result = json.load(response)
                require(
                    access_result.get("authenticated") is True,
                    "API access verification did not authenticate",
                )
            with opener.open(
                f"{base_url}/api/database-status", timeout=5
            ) as response:
                api_database = json.load(response)
            with opener.open(f"{base_url}/api/medications", timeout=5) as response:
                api_plan = json.load(response)
            history_query = urlencode({"days": 7, "end": "2099-01-07"})
            with opener.open(
                f"{base_url}/api/history?{history_query}", timeout=5
            ) as response:
                api_history = json.load(response)
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise FreshDatabaseVerificationError(f"API check failed: {exc}") from exc

        require(isinstance(api_database, dict), "API database response is not an object")
        require(isinstance(api_plan, dict), "API medication response is not an object")
        require(isinstance(api_history, dict), "API history response is not an object")
        require(
            api_database.get("databaseIdentity") == initial_database_identity,
            "API is not using the verified database file",
        )
        require(
            api_database.get("schemaVersion") == schema_version,
            "API database schema does not match the verified database",
        )
        require(
            api_database.get("medicationCount") == active_medications
            and api_database.get("dailyAdministrationCount") == active_schedules,
            "API database counts do not match the verified database",
        )
        require(
            api_database.get("historyRows") == history_rows,
            "API database contains unexpected history rows",
        )
        require(
            api_plan.get("summary")
            == {"medicationCount": 6, "dailyAdministrationCount": 13},
            "API medication summary does not match 6 medications and 13 schedules",
        )
        api_medications = api_plan.get("medications")
        require(
            isinstance(api_medications, list),
            "API medications field is not an array",
        )
        target = next(
            (
                medication
                for medication in api_medications
                if isinstance(medication, dict)
                and medication.get("name") == "示例药 A"
            ),
            None,
        )
        require(target is not None, "API is missing the default target medication")
        target_schedules = target.get("schedules")
        require(
            isinstance(target_schedules, list),
            "API target medication schedules field is not an array",
        )
        require(
            [
                schedule.get("anchor") if isinstance(schedule, dict) else None
                for schedule in target_schedules
            ]
            == ["wake", "lunch", "dinner"],
            "API target medication does not contain wake, lunch, and dinner schedules",
        )
        require(
            api_history.get("summary")
            == {"trackedDays": 0, "completed": 0, "total": 0, "percent": 0},
            "API history is not empty",
        )
        require(
            database_identity(path) == initial_database_identity,
            "verified database file changed during API checks",
        )
        api_verified = True

    return {
        "status": "ok",
        "schemaVersion": schema_version,
        "medicationCount": active_medications,
        "dailyAdministrationCount": active_schedules,
        "historyRows": history_rows,
        "apiVerified": api_verified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a new TakeTime database before first VPS exposure."
    )
    parser.add_argument("database", type=Path)
    parser.add_argument("--require-owner")
    parser.add_argument(
        "--require-mode",
        type=lambda value: int(value, 8),
        metavar="OCTAL",
    )
    parser.add_argument("--api-url")
    args = parser.parse_args()

    try:
        report = verify_fresh_database(
            args.database,
            required_owner=args.require_owner,
            required_mode=args.require_mode,
            api_url=args.api_url,
            api_access_phrase=os.environ.get("TAKETIME_ACCESS_PHRASE"),
        )
    except FreshDatabaseVerificationError as exc:
        print(f"fresh database verification failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
