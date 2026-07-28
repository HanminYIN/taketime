#!/usr/bin/env python3
"""Local medication tracker server using only the Python standard library."""

from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from email.utils import formatdate, parsedate_to_datetime
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import date as date_type
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "data" / "medication.db"
PUBLIC_DIR = ROOT / "public"
APP_TIMEZONE = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Shanghai"))
ACCESS_COOKIE_NAME = "taketime_access"
DEMO_ACCESS_COOKIE_NAME = "taketime_demo_access"
ACCESS_SESSION_TTL_SECONDS = 12 * 60 * 60

ANCHOR_FIELDS = {
    "wake": "wake_time",
    "breakfast": "breakfast_time",
    "lunch": "lunch_time",
    "dinner": "dinner_time",
    "bedtime": "bedtime_time",
}
ANCHOR_PUBLIC_FIELDS = {
    "wake": "wakeTime",
    "breakfast": "breakfastTime",
    "lunch": "lunchTime",
    "dinner": "dinnerTime",
    "bedtime": "bedtimeTime",
}
ANCHOR_ORDER = tuple(ANCHOR_FIELDS)
HISTORY_TABLES = (
    "daily_context",
    "daily_instances",
    "intake_logs",
    "wake_events",
)
PRODUCTION_SCHEMA_VERSIONS = {2, 3, 4, 5}
PRODUCTION_REQUIRED_TABLES = {
    "preferences",
    "daily_context",
    "schedule_items",
    "daily_instances",
    "intake_logs",
}

DEFAULT_CONTEXT = {
    "wakeTime": "07:00",
    "breakfastTime": "07:45",
    "lunchTime": "12:15",
    "dinnerTime": "17:30",
    "bedtimeTime": "21:00",
}

SEED_SCHEDULE_ITEMS = [
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
]

MEDICATION_NAME_MIGRATIONS = (
    ("旧版示例药 D", "示例药 D"),
)

TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_MAX_AUTO_SHIFT_MINUTES = 120
TIMING_MODES = {"routine", "meal", "interval"}
DEFAULT_TIMING_MODE = "routine"
MEAL_ANCHORS = {"breakfast", "lunch", "dinner"}

# Fictional defaults used only to demonstrate the three timing modes.
# They are not medication guidance and should be replaced before real use.
DEFAULT_TIMING_MODE_BY_MEDICATION = {
    "示例药 A": "interval",
    "示例药 B": "routine",
    "示例药 C": "interval",
    "示例药 D": "meal",
    "示例药 E": "interval",
    "示例药 F": "routine",
}


class ValidationError(ValueError):
    pass


class ConflictError(ValueError):
    pass


def inferred_timing_mode(
    name: str,
    anchors: list[str] | tuple[str, ...],
    *,
    legacy_adjust_after_intake: bool = False,
    use_personal_defaults: bool = False,
) -> str:
    if legacy_adjust_after_intake:
        return "interval"
    if use_personal_defaults and name in DEFAULT_TIMING_MODE_BY_MEDICATION:
        return DEFAULT_TIMING_MODE_BY_MEDICATION[name]
    anchor_set = set(anchors)
    if anchor_set and anchor_set <= MEAL_ANCHORS:
        return "meal"
    return DEFAULT_TIMING_MODE


def now_iso() -> str:
    return datetime.now(APP_TIMEZONE).isoformat(timespec="seconds")


def database_identity(db_path: Path) -> str:
    path = Path(db_path).resolve(strict=True)
    file_stat = path.stat()
    identity = f"{path}\0{file_stat.st_dev}\0{file_stat.st_ino}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def require_existing_database(db_path: Path) -> None:
    path = Path(db_path)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(
            f"required database is missing or is a symbolic link: {path}"
        )

    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
            quick_check = [row[0] for row in db.execute("PRAGMA quick_check")]
            schema_version = db.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in db.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
    except sqlite3.Error as exc:
        raise RuntimeError(f"required database cannot be validated: {path}") from exc

    if quick_check != ["ok"]:
        raise RuntimeError(f"required database failed quick_check: {path}")
    if schema_version not in PRODUCTION_SCHEMA_VERSIONS:
        raise RuntimeError(
            f"required database schema version is unsupported: {schema_version}"
        )
    missing_tables = PRODUCTION_REQUIRED_TABLES - tables
    if missing_tables:
        raise RuntimeError(
            f"required database is missing core tables: {sorted(missing_tables)}"
        )


def today_local() -> date_type:
    return datetime.now(APP_TIMEZONE).date()


def validate_date(value: str) -> str:
    if not DATE_PATTERN.fullmatch(value):
        raise ValidationError("日期格式必须为 YYYY-MM-DD")
    try:
        date_type.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("日期无效") from exc
    return value


def validate_time(value: Any, label: str = "时间") -> str:
    if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value):
        raise ValidationError(f"{label}格式必须为 HH:MM")
    return value


def validate_taken_at(value: Any) -> tuple[str, datetime]:
    if not isinstance(value, str) or len(value) > 64:
        raise ValidationError("服药记录时间必须是带时区的 ISO 时间")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("服药记录时间必须是带时区的 ISO 时间") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValidationError("服药记录时间必须是带时区的 ISO 时间")
    return value, moment


def scheduled_time(anchor_time: str, offset_minutes: int) -> str:
    base = datetime.strptime(anchor_time, "%H:%M")
    return (base + timedelta(minutes=offset_minutes)).strftime("%H:%M")


def schedule_shift_minutes(scheduled_at: str, base_scheduled_at: str) -> int:
    difference = datetime.fromisoformat(scheduled_at) - datetime.fromisoformat(
        base_scheduled_at
    )
    return int(difference.total_seconds() / 60)


def minutes_from_time(value: str) -> int:
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def context_anchor_moments(
    day: str, context: sqlite3.Row | dict[str, Any]
) -> dict[str, datetime]:
    current_date = date_type.fromisoformat(day)
    previous_minutes: int | None = None
    moments: dict[str, datetime] = {}
    for anchor in ANCHOR_ORDER:
        clock = context[ANCHOR_FIELDS[anchor]]
        clock_minutes = minutes_from_time(clock)
        if previous_minutes is not None and clock_minutes < previous_minutes:
            current_date += timedelta(days=1)
        moments[anchor] = datetime.combine(
            current_date,
            datetime.strptime(clock, "%H:%M").time(),
            tzinfo=APP_TIMEZONE,
        )
        previous_minutes = clock_minutes
    return moments


def scheduled_moment(
    day: str,
    context: sqlite3.Row | dict[str, Any],
    anchor: str,
    offset_minutes: int,
) -> datetime:
    return context_anchor_moments(day, context)[anchor] + timedelta(
        minutes=offset_minutes
    )


def context_day_offsets(
    day: str, context: sqlite3.Row | dict[str, Any]
) -> dict[str, int]:
    routine_date = date_type.fromisoformat(day)
    return {
        ANCHOR_PUBLIC_FIELDS[anchor]: (moment.date() - routine_date).days
        for anchor, moment in context_anchor_moments(day, context).items()
    }


def infer_context_from_wake(
    preferences: sqlite3.Row, wake_time: str
) -> dict[str, str]:
    baseline = context_anchor_moments("2000-01-01", preferences)
    baseline_wake = baseline["wake"]
    span = baseline["bedtime"] - baseline_wake
    if span <= timedelta(0) or span > timedelta(days=1):
        raise ValidationError("常用作息无法用于自动推算，请先检查各时段顺序")

    wake = datetime.combine(
        date_type(2000, 1, 1),
        datetime.strptime(wake_time, "%H:%M").time(),
        tzinfo=APP_TIMEZONE,
    )
    return {
        ANCHOR_PUBLIC_FIELDS[anchor]: (wake + (moment - baseline_wake)).strftime(
            "%H:%M"
        )
        for anchor, moment in baseline.items()
    }


def public_context(row: sqlite3.Row) -> dict[str, str]:
    return {
        "wakeTime": row["wake_time"],
        "breakfastTime": row["breakfast_time"],
        "lunchTime": row["lunch_time"],
        "dinnerTime": row["dinner_time"],
        "bedtimeTime": row["bedtime_time"],
    }


def validate_context(payload: dict[str, Any]) -> dict[str, str]:
    required = tuple(DEFAULT_CONTEXT)
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValidationError(f"缺少时间字段：{', '.join(missing)}")
    return {field: validate_time(payload[field], field) for field in required}


def validate_preferences(payload: dict[str, Any]) -> dict[str, str]:
    values = validate_context(payload)
    storage_context = {
        ANCHOR_FIELDS[anchor]: values[ANCHOR_PUBLIC_FIELDS[anchor]]
        for anchor in ANCHOR_ORDER
    }
    moments = context_anchor_moments("2000-01-01", storage_context)
    span = moments["bedtime"] - moments["wake"]
    if span <= timedelta(0) or span > timedelta(days=1):
        raise ValidationError(
            "常用作息需在起床后 24 小时内结束，请检查各时段顺序"
        )
    return values


class MedicationStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS preferences (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    wake_time TEXT NOT NULL,
                    breakfast_time TEXT NOT NULL,
                    lunch_time TEXT NOT NULL,
                    dinner_time TEXT NOT NULL,
                    bedtime_time TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS daily_context (
                    date TEXT PRIMARY KEY,
                    wake_time TEXT NOT NULL,
                    breakfast_time TEXT NOT NULL,
                    lunch_time TEXT NOT NULL,
                    dinner_time TEXT NOT NULL,
                    bedtime_time TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'legacy',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS wake_events (
                    routine_date TEXT PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (routine_date)
                        REFERENCES daily_context(date)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS medications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    revision INTEGER NOT NULL DEFAULT 1,
                    timing_mode TEXT NOT NULL DEFAULT 'routine',
                    adjust_after_intake INTEGER NOT NULL DEFAULT 0,
                    max_auto_shift_minutes INTEGER NOT NULL DEFAULT 120,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schedule_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medication_id INTEGER,
                    name TEXT NOT NULL,
                    dose TEXT NOT NULL,
                    instructions TEXT NOT NULL DEFAULT '',
                    anchor TEXT NOT NULL,
                    offset_minutes INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (medication_id) REFERENCES medications(id)
                );

                CREATE TABLE IF NOT EXISTS daily_instances (
                    date TEXT NOT NULL,
                    schedule_item_id INTEGER NOT NULL,
                    medication_id INTEGER,
                    name TEXT NOT NULL,
                    dose TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    anchor TEXT NOT NULL,
                    offset_minutes INTEGER NOT NULL,
                    scheduled_time TEXT NOT NULL,
                    scheduled_at TEXT,
                    base_scheduled_time TEXT,
                    base_scheduled_at TEXT,
                    timing_mode TEXT NOT NULL DEFAULT 'routine',
                    adjust_after_intake INTEGER NOT NULL DEFAULT 0,
                    max_auto_shift_minutes INTEGER NOT NULL DEFAULT 120,
                    adjusted_by_schedule_item_id INTEGER,
                    adjusted_by_taken_at TEXT,
                    sort_order INTEGER NOT NULL,
                    PRIMARY KEY (date, schedule_item_id)
                );

                CREATE TABLE IF NOT EXISTS intake_logs (
                    date TEXT NOT NULL,
                    schedule_item_id INTEGER NOT NULL,
                    scheduled_time TEXT NOT NULL,
                    scheduled_at TEXT,
                    taken_at TEXT NOT NULL,
                    adjustment_status TEXT NOT NULL DEFAULT 'legacy',
                    adjustment_applied INTEGER NOT NULL DEFAULT 0,
                    adjustment_minutes INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (date, schedule_item_id),
                    FOREIGN KEY (date, schedule_item_id)
                        REFERENCES daily_instances(date, schedule_item_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_daily_instances_date
                    ON daily_instances(date, scheduled_time);
                CREATE INDEX IF NOT EXISTS idx_intake_logs_date
                    ON intake_logs(date);
                """
            )

            context_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(daily_context)")
            }
            if "source" not in context_columns:
                db.execute(
                    "ALTER TABLE daily_context "
                    "ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy'"
                )

            medication_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(medications)")
            }
            medication_timing_mode_added = "timing_mode" not in medication_columns
            if medication_timing_mode_added:
                db.execute(
                    "ALTER TABLE medications ADD COLUMN timing_mode "
                    "TEXT NOT NULL DEFAULT 'routine'"
                )
            if "adjust_after_intake" not in medication_columns:
                db.execute(
                    "ALTER TABLE medications ADD COLUMN adjust_after_intake "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            if "max_auto_shift_minutes" not in medication_columns:
                db.execute(
                    "ALTER TABLE medications ADD COLUMN max_auto_shift_minutes "
                    f"INTEGER NOT NULL DEFAULT {DEFAULT_MAX_AUTO_SHIFT_MINUTES}"
                )

            instance_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(daily_instances)")
            }
            instance_timing_mode_added = "timing_mode" not in instance_columns
            if instance_timing_mode_added:
                db.execute(
                    "ALTER TABLE daily_instances ADD COLUMN timing_mode "
                    "TEXT NOT NULL DEFAULT 'routine'"
                )
            if "scheduled_at" not in instance_columns:
                db.execute(
                    "ALTER TABLE daily_instances ADD COLUMN scheduled_at TEXT"
                )
            if "medication_id" not in instance_columns:
                db.execute("ALTER TABLE daily_instances ADD COLUMN medication_id INTEGER")
            if "base_scheduled_time" not in instance_columns:
                db.execute(
                    "ALTER TABLE daily_instances ADD COLUMN base_scheduled_time TEXT"
                )
            if "base_scheduled_at" not in instance_columns:
                db.execute(
                    "ALTER TABLE daily_instances ADD COLUMN base_scheduled_at TEXT"
                )
            if "adjust_after_intake" not in instance_columns:
                db.execute(
                    "ALTER TABLE daily_instances ADD COLUMN adjust_after_intake "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            if "max_auto_shift_minutes" not in instance_columns:
                db.execute(
                    "ALTER TABLE daily_instances ADD COLUMN max_auto_shift_minutes "
                    f"INTEGER NOT NULL DEFAULT {DEFAULT_MAX_AUTO_SHIFT_MINUTES}"
                )
            if "adjusted_by_schedule_item_id" not in instance_columns:
                db.execute(
                    "ALTER TABLE daily_instances "
                    "ADD COLUMN adjusted_by_schedule_item_id INTEGER"
                )
            if "adjusted_by_taken_at" not in instance_columns:
                db.execute(
                    "ALTER TABLE daily_instances ADD COLUMN adjusted_by_taken_at TEXT"
                )

            log_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(intake_logs)")
            }
            if "scheduled_at" not in log_columns:
                db.execute("ALTER TABLE intake_logs ADD COLUMN scheduled_at TEXT")
            if "adjustment_status" not in log_columns:
                db.execute(
                    "ALTER TABLE intake_logs ADD COLUMN adjustment_status "
                    "TEXT NOT NULL DEFAULT 'legacy'"
                )
            if "adjustment_applied" not in log_columns:
                db.execute(
                    "ALTER TABLE intake_logs ADD COLUMN adjustment_applied "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            if "adjustment_minutes" not in log_columns:
                db.execute(
                    "ALTER TABLE intake_logs ADD COLUMN adjustment_minutes "
                    "INTEGER NOT NULL DEFAULT 0"
                )

            schedule_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(schedule_items)")
            }
            if "medication_id" not in schedule_columns:
                db.execute(
                    "ALTER TABLE schedule_items ADD COLUMN medication_id INTEGER "
                    "REFERENCES medications(id)"
                )

            db.execute(
                """
                UPDATE daily_instances
                SET scheduled_at = date || 'T' || scheduled_time || ':00'
                WHERE scheduled_at IS NULL
                """
            )
            db.execute(
                """
                UPDATE intake_logs
                SET scheduled_at = date || 'T' || scheduled_time || ':00'
                WHERE scheduled_at IS NULL
                """
            )
            db.execute(
                """
                UPDATE daily_instances
                SET base_scheduled_time = scheduled_time
                WHERE base_scheduled_time IS NULL
                """
            )
            db.execute(
                """
                UPDATE daily_instances
                SET base_scheduled_at = scheduled_at
                WHERE base_scheduled_at IS NULL
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_daily_instances_date_at
                ON daily_instances(date, scheduled_at)
                """
            )
            stamp = now_iso()
            db.execute(
                """
                INSERT OR IGNORE INTO preferences (
                    id, wake_time, breakfast_time, lunch_time, dinner_time,
                    bedtime_time, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_CONTEXT["wakeTime"],
                    DEFAULT_CONTEXT["breakfastTime"],
                    DEFAULT_CONTEXT["lunchTime"],
                    DEFAULT_CONTEXT["dinnerTime"],
                    DEFAULT_CONTEXT["bedtimeTime"],
                    stamp,
                ),
            )

            count = db.execute("SELECT COUNT(*) FROM schedule_items").fetchone()[0]
            if count == 0:
                db.executemany(
                    """
                    INSERT INTO schedule_items (
                        name, dose, instructions, anchor, offset_minutes,
                        sort_order, active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    [(*item, stamp, stamp) for item in SEED_SCHEDULE_ITEMS],
                )

            # Normalize plan definitions only; frozen daily snapshots retain their labels.
            for legacy_name, current_name in MEDICATION_NAME_MIGRATIONS:
                db.execute(
                    """
                    UPDATE schedule_items SET name = ?, updated_at = ?
                    WHERE name = ?
                    """,
                    (current_name, stamp, legacy_name),
                )
                db.execute(
                    "UPDATE medications SET name = ?, updated_at = ? WHERE name = ?",
                    (current_name, stamp, legacy_name),
                )

            self._backfill_medications(db, stamp)
            if medication_timing_mode_added:
                medication_rows = db.execute(
                    "SELECT * FROM medications ORDER BY id"
                ).fetchall()
                for medication in medication_rows:
                    anchors = [
                        row["anchor"]
                        for row in db.execute(
                            """
                            SELECT anchor FROM schedule_items
                            WHERE medication_id = ? AND active = 1
                            ORDER BY sort_order, id
                            """,
                            (medication["id"],),
                        ).fetchall()
                    ]
                    timing_mode = inferred_timing_mode(
                        medication["name"],
                        anchors,
                        legacy_adjust_after_intake=bool(
                            medication["adjust_after_intake"]
                        ),
                        use_personal_defaults=True,
                    )
                    db.execute(
                        """
                        UPDATE medications
                        SET timing_mode = ?, adjust_after_intake = ?
                        WHERE id = ?
                        """,
                        (
                            timing_mode,
                            int(timing_mode == "interval"),
                            medication["id"],
                        ),
                    )
            if instance_timing_mode_added:
                db.execute(
                    """
                    UPDATE daily_instances SET timing_mode = 'interval'
                    WHERE adjust_after_intake = 1
                    """
                )
            db.execute(
                """
                UPDATE daily_instances
                SET medication_id = (
                    SELECT s.medication_id
                    FROM schedule_items AS s
                    WHERE s.id = daily_instances.schedule_item_id
                )
                WHERE medication_id IS NULL
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_schedule_items_medication_active "
                "ON schedule_items(medication_id, active)"
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_active_medication_name "
                "ON medications(name) WHERE active = 1"
            )
            db.execute("PRAGMA user_version = 5")

    @staticmethod
    def _backfill_medications(db: sqlite3.Connection, stamp: str) -> None:
        rows = db.execute(
            """
            SELECT id, name, active, created_at, updated_at, anchor
            FROM schedule_items
            WHERE medication_id IS NULL
            ORDER BY id
            """
        ).fetchall()
        groups: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            name = row["name"].strip()
            groups.setdefault(name, []).append(row)

        for name, items in groups.items():
            active = int(any(item["active"] for item in items))
            medication = db.execute(
                """
                SELECT * FROM medications
                WHERE name = ? AND active = ?
                ORDER BY id
                LIMIT 1
                """,
                (name, active),
            ).fetchone()
            if medication is None:
                created_at = min(item["created_at"] for item in items) or stamp
                updated_at = max(item["updated_at"] for item in items) or stamp
                timing_mode = inferred_timing_mode(
                    name,
                    [item["anchor"] for item in items if item["active"]],
                    use_personal_defaults=True,
                )
                cursor = db.execute(
                    """
                    INSERT INTO medications (
                        name, active, revision, timing_mode,
                        adjust_after_intake, created_at, updated_at
                    ) VALUES (?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        active,
                        timing_mode,
                        int(timing_mode == "interval"),
                        created_at,
                        updated_at,
                    ),
                )
                medication_id = cursor.lastrowid
            else:
                medication_id = medication["id"]
            db.executemany(
                """
                UPDATE schedule_items SET medication_id = ?, name = ?
                WHERE id = ?
                """,
                [(medication_id, name, item["id"]) for item in items],
            )

    def get_preferences(self) -> dict[str, str]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM preferences WHERE id = 1").fetchone()
        return public_context(row)

    def get_database_status(self) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN")
            schema_version = db.execute("PRAGMA user_version").fetchone()[0]
            medication_count = db.execute(
                "SELECT COUNT(*) FROM medications WHERE active = 1"
            ).fetchone()[0]
            schedule_count = db.execute(
                "SELECT COUNT(*) FROM schedule_items WHERE active = 1"
            ).fetchone()[0]
            history_rows = {
                table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in HISTORY_TABLES
            }
        return {
            "status": "ok",
            "databaseIdentity": database_identity(self.db_path),
            "schemaVersion": schema_version,
            "medicationCount": medication_count,
            "dailyAdministrationCount": schedule_count,
            "historyRows": history_rows,
        }

    def update_preferences(self, payload: dict[str, Any]) -> dict[str, str]:
        values = validate_preferences(payload)
        with self.connect() as db:
            db.execute(
                """
                UPDATE preferences SET wake_time = ?, breakfast_time = ?,
                    lunch_time = ?, dinner_time = ?, bedtime_time = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    values["wakeTime"],
                    values["breakfastTime"],
                    values["lunchTime"],
                    values["dinnerTime"],
                    values["bedtimeTime"],
                    now_iso(),
                ),
            )
        return values

    def _ensure_context(
        self, db: sqlite3.Connection, day: str, source: str = "intake_default"
    ) -> tuple[sqlite3.Row, bool]:
        defaults = db.execute("SELECT * FROM preferences WHERE id = 1").fetchone()
        cursor = db.execute(
            """
            INSERT INTO daily_context (
                date, wake_time, breakfast_time, lunch_time, dinner_time,
                bedtime_time, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO NOTHING
            """,
            (
                day,
                defaults["wake_time"],
                defaults["breakfast_time"],
                defaults["lunch_time"],
                defaults["dinner_time"],
                defaults["bedtime_time"],
                source,
                now_iso(),
            ),
        )
        row = db.execute("SELECT * FROM daily_context WHERE date = ?", (day,)).fetchone()
        return row, cursor.rowcount == 1

    def _ensure_instances(self, db: sqlite3.Connection, day: str, context: sqlite3.Row) -> None:
        count = db.execute(
            "SELECT COUNT(*) FROM daily_instances WHERE date = ?", (day,)
        ).fetchone()[0]
        if count:
            return
        items = db.execute(
            """
            SELECT s.*, m.timing_mode, m.adjust_after_intake,
                   m.max_auto_shift_minutes
            FROM schedule_items AS s
            JOIN medications AS m ON m.id = s.medication_id
            WHERE s.active = 1 AND m.active = 1
            ORDER BY s.sort_order, s.id
            """
        ).fetchall()
        rows = []
        for item in items:
            moment = scheduled_moment(
                day, context, item["anchor"], item["offset_minutes"]
            )
            rows.append(
                (
                    day,
                    item["id"],
                    item["medication_id"],
                    item["name"],
                    item["dose"],
                    item["instructions"],
                    item["anchor"],
                    item["offset_minutes"],
                    moment.strftime("%H:%M"),
                    moment.isoformat(timespec="seconds"),
                    moment.strftime("%H:%M"),
                    moment.isoformat(timespec="seconds"),
                    item["timing_mode"],
                    item["adjust_after_intake"],
                    item["max_auto_shift_minutes"],
                    item["sort_order"],
                )
            )
        db.executemany(
            """
            INSERT INTO daily_instances (
                date, schedule_item_id, medication_id, name, dose, instructions,
                anchor, offset_minutes, scheduled_time, scheduled_at,
                base_scheduled_time, base_scheduled_at, timing_mode,
                adjust_after_intake, max_auto_shift_minutes, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    @staticmethod
    def _replay_intake_adjustments(
        db: sqlite3.Connection, day: str
    ) -> None:
        rows = db.execute(
            """
            SELECT i.*, l.taken_at, l.adjustment_applied,
                   l.adjustment_minutes
            FROM daily_instances AS i
            LEFT JOIN intake_logs AS l
                ON l.date = i.date AND l.schedule_item_id = i.schedule_item_id
            WHERE i.date = ?
            ORDER BY i.medication_id, i.base_scheduled_at,
                     i.sort_order, i.schedule_item_id
            """,
            (day,),
        ).fetchall()
        shifts: dict[int, int] = {}
        latest_sources: dict[int, tuple[int, str]] = {}
        for row in rows:
            medication_id = row["medication_id"]
            if medication_id is None:
                continue
            if row["taken_at"] is not None:
                if row["adjustment_applied"]:
                    shifts[medication_id] = shifts.get(medication_id, 0) + int(
                        row["adjustment_minutes"]
                    )
                    latest_sources[medication_id] = (
                        row["schedule_item_id"],
                        row["taken_at"],
                    )
                continue

            base = datetime.fromisoformat(row["base_scheduled_at"])
            shift = shifts.get(medication_id, 0)
            moment = base + timedelta(minutes=shift)
            source = latest_sources.get(medication_id) if shift else None
            db.execute(
                """
                UPDATE daily_instances
                SET scheduled_time = ?, scheduled_at = ?,
                    adjusted_by_schedule_item_id = ?, adjusted_by_taken_at = ?
                WHERE date = ? AND schedule_item_id = ?
                """,
                (
                    moment.strftime("%H:%M"),
                    moment.isoformat(timespec="seconds"),
                    source[0] if source else None,
                    source[1] if source else None,
                    day,
                    row["schedule_item_id"],
                ),
            )

    def _reschedule_pending_instances(
        self, db: sqlite3.Connection, day: str, context: sqlite3.Row
    ) -> None:
        instances = db.execute(
            """
            SELECT i.schedule_item_id, i.anchor, i.offset_minutes
            FROM daily_instances i
            LEFT JOIN intake_logs l
                ON l.date = i.date AND l.schedule_item_id = i.schedule_item_id
            WHERE i.date = ? AND l.taken_at IS NULL
            """,
            (day,),
        ).fetchall()
        for instance in instances:
            moment = scheduled_moment(
                day,
                context,
                instance["anchor"],
                instance["offset_minutes"],
            )
            db.execute(
                """
                UPDATE daily_instances
                SET scheduled_time = ?, scheduled_at = ?,
                    base_scheduled_time = ?, base_scheduled_at = ?,
                    adjusted_by_schedule_item_id = NULL,
                    adjusted_by_taken_at = NULL
                WHERE date = ? AND schedule_item_id = ?
                """,
                (
                    moment.strftime("%H:%M"),
                    moment.isoformat(timespec="seconds"),
                    moment.strftime("%H:%M"),
                    moment.isoformat(timespec="seconds"),
                    day,
                    instance["schedule_item_id"],
                ),
            )
        self._replay_intake_adjustments(db, day)

    def get_day(self, day: str) -> dict[str, Any]:
        validate_date(day)
        with self.connect() as db:
            context = db.execute(
                "SELECT * FROM daily_context WHERE date = ?", (day,)
            ).fetchone()
            context_persisted = context is not None
            context_source = context["source"] if context is not None else "default"
            if context is None:
                context = db.execute(
                    "SELECT * FROM preferences WHERE id = 1"
                ).fetchone()
            wake_event = db.execute(
                "SELECT * FROM wake_events WHERE routine_date = ?", (day,)
            ).fetchone()
            rows = db.execute(
                """
                SELECT i.*, l.taken_at
                FROM daily_instances i
                LEFT JOIN intake_logs l
                    ON l.date = i.date AND l.schedule_item_id = i.schedule_item_id
                WHERE i.date = ?
                ORDER BY i.scheduled_at, i.sort_order, i.schedule_item_id
                """,
                (day,),
            ).fetchall()
            carryover_rows = db.execute(
                """
                SELECT i.*, l.taken_at,
                    COALESCE(c.source, 'default') AS context_source
                FROM daily_instances i
                LEFT JOIN intake_logs l
                    ON l.date = i.date AND l.schedule_item_id = i.schedule_item_id
                LEFT JOIN daily_context c ON c.date = i.date
                WHERE i.date != ?
                    AND substr(i.scheduled_at, 1, 10) = ?
                    AND l.taken_at IS NULL
                ORDER BY i.scheduled_at, i.sort_order, i.schedule_item_id
                """,
                (day, day),
            ).fetchall()

            day_persisted = context_persisted or bool(rows)
            selected_date = date_type.fromisoformat(day)
            is_untracked_past = (
                not day_persisted and selected_date < today_local()
            )
            if not rows and not day_persisted and not is_untracked_past:
                schedule_rows = db.execute(
                    """
                    SELECT s.*, m.timing_mode, m.adjust_after_intake,
                           m.max_auto_shift_minutes
                    FROM schedule_items AS s
                    JOIN medications AS m ON m.id = s.medication_id
                    WHERE s.active = 1 AND m.active = 1
                    ORDER BY s.sort_order, s.id
                    """
                ).fetchall()
                rows = []
                for row in schedule_rows:
                    moment = scheduled_moment(
                        day,
                        context,
                        row["anchor"],
                        row["offset_minutes"],
                    )
                    rows.append({
                        "schedule_item_id": row["id"],
                        "medication_id": row["medication_id"],
                        "name": row["name"],
                        "dose": row["dose"],
                        "instructions": row["instructions"],
                        "anchor": row["anchor"],
                        "offset_minutes": row["offset_minutes"],
                        "scheduled_time": moment.strftime("%H:%M"),
                        "scheduled_at": moment.isoformat(timespec="seconds"),
                        "base_scheduled_time": moment.strftime("%H:%M"),
                        "base_scheduled_at": moment.isoformat(timespec="seconds"),
                        "timing_mode": row["timing_mode"],
                        "adjust_after_intake": row["adjust_after_intake"],
                        "max_auto_shift_minutes": row["max_auto_shift_minutes"],
                        "adjusted_by_schedule_item_id": None,
                        "adjusted_by_taken_at": None,
                        "sort_order": row["sort_order"],
                        "taken_at": None,
                    })
                rows.sort(
                    key=lambda row: (
                        row["scheduled_at"],
                        row["sort_order"],
                        row["schedule_item_id"],
                    )
                )

        wake_public = None
        if wake_event is not None:
            occurred_at = datetime.fromisoformat(wake_event["occurred_at"])
            wake_public = {
                "occurredAt": wake_event["occurred_at"],
                "localTime": occurred_at.astimezone(APP_TIMEZONE).strftime("%H:%M"),
            }

        items = [
            {
                "id": row["schedule_item_id"],
                "medicationId": row["medication_id"],
                "name": row["name"],
                "dose": row["dose"],
                "instructions": row["instructions"],
                "anchor": row["anchor"],
                "offsetMinutes": row["offset_minutes"],
                "scheduledTime": row["scheduled_time"],
                "scheduledAt": row["scheduled_at"],
                "baseScheduledTime": row["base_scheduled_time"],
                "baseScheduledAt": row["base_scheduled_at"],
                "timingMode": row["timing_mode"],
                "adjusted": row["scheduled_at"] != row["base_scheduled_at"],
                "adjustmentMinutes": schedule_shift_minutes(
                    row["scheduled_at"], row["base_scheduled_at"]
                ),
                "adjustedByScheduleItemId": row["adjusted_by_schedule_item_id"],
                "adjustedByTakenAt": row["adjusted_by_taken_at"],
                "anchorEstimated": (
                    context_source == "wake_inferred" and row["anchor"] != "wake"
                ),
                "taken": row["taken_at"] is not None,
                "takenAt": row["taken_at"],
            }
            for row in rows
        ]
        carryover_items = [
            {
                "id": row["schedule_item_id"],
                "medicationId": row["medication_id"],
                "routineDate": row["date"],
                "name": row["name"],
                "dose": row["dose"],
                "instructions": row["instructions"],
                "anchor": row["anchor"],
                "offsetMinutes": row["offset_minutes"],
                "scheduledTime": row["scheduled_time"],
                "scheduledAt": row["scheduled_at"],
                "baseScheduledTime": row["base_scheduled_time"],
                "baseScheduledAt": row["base_scheduled_at"],
                "timingMode": row["timing_mode"],
                "adjusted": row["scheduled_at"] != row["base_scheduled_at"],
                "adjustmentMinutes": schedule_shift_minutes(
                    row["scheduled_at"], row["base_scheduled_at"]
                ),
                "adjustedByScheduleItemId": row["adjusted_by_schedule_item_id"],
                "adjustedByTakenAt": row["adjusted_by_taken_at"],
                "anchorEstimated": (
                    row["context_source"] == "wake_inferred"
                    and row["anchor"] != "wake"
                ),
                "taken": False,
                "takenAt": None,
            }
            for row in carryover_rows
        ]
        completed = sum(item["taken"] for item in items)
        return {
            "date": day,
            "context": public_context(context),
            "contextDayOffsets": context_day_offsets(day, context),
            "contextSource": context_source,
            "wakeEvent": wake_public,
            "items": items,
            "carryoverItems": carryover_items,
            "persisted": day_persisted,
            "contextPersisted": context_persisted,
            "preview": not day_persisted and not is_untracked_past,
            "untracked": is_untracked_past,
            "summary": {
                "completed": completed,
                "total": len(items),
                "percent": round(completed / len(items) * 100) if items else 0,
            },
        }

    def update_context(self, day: str, payload: dict[str, Any]) -> dict[str, Any]:
        validate_date(day)
        values = validate_context(payload)
        stamp = now_iso()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            _, context_created = self._ensure_context(db, day, source="manual")
            db.execute(
                """
                UPDATE daily_context SET wake_time = ?, breakfast_time = ?,
                    lunch_time = ?, dinner_time = ?, bedtime_time = ?,
                    source = 'manual', updated_at = ?
                WHERE date = ?
                """,
                (
                    values["wakeTime"],
                    values["breakfastTime"],
                    values["lunchTime"],
                    values["dinnerTime"],
                    values["bedtimeTime"],
                    stamp,
                    day,
                ),
            )
            context = db.execute(
                "SELECT * FROM daily_context WHERE date = ?", (day,)
            ).fetchone()
            if context_created:
                self._ensure_instances(db, day, context)
            self._reschedule_pending_instances(db, day, context)
        return self.get_day(day)

    def check_in_wake(
        self, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        day = validate_date(str(payload.get("date", "")))
        stamp = now_iso()
        occurred_at = datetime.fromisoformat(stamp).astimezone(APP_TIMEZONE)
        if day != occurred_at.date().isoformat():
            raise ValidationError("只能为今天记录起床时间")

        created = False
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT occurred_at FROM wake_events WHERE routine_date = ?",
                (day,),
            ).fetchone()
            if existing is None:
                preferences = db.execute(
                    "SELECT * FROM preferences WHERE id = 1"
                ).fetchone()
                values = infer_context_from_wake(
                    preferences, occurred_at.strftime("%H:%M")
                )
                _, context_created = self._ensure_context(
                    db, day, source="wake_inferred"
                )
                db.execute(
                    """
                    UPDATE daily_context SET wake_time = ?, breakfast_time = ?,
                        lunch_time = ?, dinner_time = ?, bedtime_time = ?,
                        source = 'wake_inferred', updated_at = ?
                    WHERE date = ?
                    """,
                    (
                        values["wakeTime"],
                        values["breakfastTime"],
                        values["lunchTime"],
                        values["dinnerTime"],
                        values["bedtimeTime"],
                        stamp,
                        day,
                    ),
                )
                context = db.execute(
                    "SELECT * FROM daily_context WHERE date = ?", (day,)
                ).fetchone()
                if context_created:
                    self._ensure_instances(db, day, context)
                self._reschedule_pending_instances(db, day, context)
                db.execute(
                    """
                    INSERT INTO wake_events (
                        routine_date, occurred_at, recorded_at, updated_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (day, stamp, stamp, stamp),
                )
                created = True

        response = self.get_day(day)
        response["alreadyRecorded"] = not created
        return response, created

    def mark_taken(self, payload: dict[str, Any]) -> dict[str, Any]:
        day = validate_date(str(payload.get("date", "")))
        try:
            item_id = int(payload.get("scheduleItemId"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("用药项目编号无效") from exc
        taken_at, taken_moment = validate_taken_at(payload.get("takenAt") or now_iso())

        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            context, context_created = self._ensure_context(db, day)
            if context_created:
                self._ensure_instances(db, day, context)
            instance = db.execute(
                """
                SELECT * FROM daily_instances
                WHERE date = ? AND schedule_item_id = ?
                """,
                (day, item_id),
            ).fetchone()
            if not instance:
                raise ValidationError("当天不存在该用药项目")

            source_key = (
                datetime.fromisoformat(instance["base_scheduled_at"]),
                instance["sort_order"],
                instance["schedule_item_id"],
            )
            future_instances = []
            if instance["medication_id"] is not None:
                candidates = db.execute(
                    """
                    SELECT i.*, l.taken_at
                    FROM daily_instances AS i
                    LEFT JOIN intake_logs AS l
                        ON l.date = i.date
                       AND l.schedule_item_id = i.schedule_item_id
                    WHERE i.date = ? AND i.medication_id = ?
                          AND l.taken_at IS NULL
                    """,
                    (day, instance["medication_id"]),
                ).fetchall()
                future_instances = [
                    candidate
                    for candidate in candidates
                    if (
                        datetime.fromisoformat(candidate["base_scheduled_at"]),
                        candidate["sort_order"],
                        candidate["schedule_item_id"],
                    )
                    > source_key
                ]
                future_instances.sort(
                    key=lambda candidate: (
                        datetime.fromisoformat(candidate["base_scheduled_at"]),
                        candidate["sort_order"],
                        candidate["schedule_item_id"],
                    )
                )

            scheduled_moment_value = datetime.fromisoformat(instance["scheduled_at"])
            if scheduled_moment_value.tzinfo is None:
                scheduled_moment_value = scheduled_moment_value.replace(
                    tzinfo=APP_TIMEZONE
                )
            actual_minute = taken_moment.astimezone(APP_TIMEZONE).replace(
                second=0, microsecond=0
            )
            requested_shift = int(
                (actual_minute - scheduled_moment_value).total_seconds() / 60
            )
            maximum_shift = int(instance["max_auto_shift_minutes"])
            timing_mode = instance["timing_mode"]
            if timing_mode != "interval":
                adjustment_status = "not_interval"
                adjustment_applied = False
            elif not future_instances:
                adjustment_status = "no_future_items"
                adjustment_applied = False
            elif requested_shift == 0:
                adjustment_status = "no_change"
                adjustment_applied = False
            elif abs(requested_shift) > maximum_shift:
                adjustment_status = "outside_window"
                adjustment_applied = False
            else:
                adjustment_status = "applied"
                adjustment_applied = True
            applied_shift = requested_shift if adjustment_applied else 0
            db.execute(
                """
                INSERT INTO intake_logs (
                    date, schedule_item_id, scheduled_time, scheduled_at, taken_at,
                    adjustment_status, adjustment_applied, adjustment_minutes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, schedule_item_id) DO UPDATE SET
                    scheduled_time = excluded.scheduled_time,
                    scheduled_at = excluded.scheduled_at,
                    taken_at = excluded.taken_at,
                    adjustment_status = excluded.adjustment_status,
                    adjustment_applied = excluded.adjustment_applied,
                    adjustment_minutes = excluded.adjustment_minutes
                """,
                (
                    day,
                    item_id,
                    instance["scheduled_time"],
                    instance["scheduled_at"],
                    taken_at,
                    adjustment_status,
                    int(adjustment_applied),
                    applied_shift,
                ),
            )
            self._replay_intake_adjustments(db, day)
        response = self.get_day(day)
        response["scheduleAdjustment"] = {
            "status": adjustment_status,
            "sourceScheduleItemId": item_id,
            "sourceTakenAt": taken_at,
            "requestedShiftMinutes": requested_shift,
            "shiftMinutes": applied_shift,
            "affectedCount": len(future_instances),
            "maximumShiftMinutes": maximum_shift,
            "timingMode": timing_mode,
        }
        return response

    def unmark_taken(self, day: str, item_id: int) -> dict[str, Any]:
        validate_date(day)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "DELETE FROM intake_logs WHERE date = ? AND schedule_item_id = ?",
                (day, item_id),
            )
            self._replay_intake_adjustments(db, day)
        return self.get_day(day)

    def get_history(self, end_day: str, days: int) -> dict[str, Any]:
        validate_date(end_day)
        if not 1 <= days <= 90:
            raise ValidationError("历史天数必须在 1 到 90 之间")
        end = date_type.fromisoformat(end_day)
        start = end - timedelta(days=days - 1)
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT i.date, COUNT(*) AS total,
                    SUM(CASE WHEN l.taken_at IS NOT NULL THEN 1 ELSE 0 END) AS completed
                FROM daily_instances i
                LEFT JOIN intake_logs l
                    ON l.date = i.date AND l.schedule_item_id = i.schedule_item_id
                WHERE i.date BETWEEN ? AND ?
                GROUP BY i.date
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        by_date = {row["date"]: row for row in rows}
        history = []
        for index in range(days):
            current = start + timedelta(days=index)
            key = current.isoformat()
            row = by_date.get(key)
            total = int(row["total"]) if row else 0
            completed = int(row["completed"] or 0) if row else 0
            history.append(
                {
                    "date": key,
                    "completed": completed,
                    "total": total,
                    "percent": round(completed / total * 100) if total else 0,
                }
            )
        tracked = [entry for entry in history if entry["total"]]
        completed_total = sum(entry["completed"] for entry in tracked)
        item_total = sum(entry["total"] for entry in tracked)
        return {
            "days": history,
            "summary": {
                "trackedDays": len(tracked),
                "completed": completed_total,
                "total": item_total,
                "percent": round(completed_total / item_total * 100)
                if item_total
                else 0,
            },
        }

    def get_schedule_items(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT * FROM schedule_items WHERE active = 1
                ORDER BY sort_order, id
                """
            ).fetchall()
        return [self._public_schedule_item(row) for row in rows]

    @staticmethod
    def _schedule_summary(db: sqlite3.Connection) -> dict[str, int]:
        row = db.execute(
            """
            SELECT COUNT(DISTINCT medication_id) AS medication_count,
                COUNT(*) AS administration_count
            FROM schedule_items
            WHERE active = 1
            """
        ).fetchone()
        return {
            "medicationCount": row["medication_count"],
            "dailyAdministrationCount": row["administration_count"],
        }

    def get_schedule_plan(self) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN")
            rows = db.execute(
                """
                SELECT * FROM schedule_items WHERE active = 1
                ORDER BY sort_order, id
                """
            ).fetchall()
            return {
                "items": [self._public_schedule_item(row) for row in rows],
                "summary": self._schedule_summary(db),
            }

    def get_medication_plan(self) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN")
            medication_rows = db.execute(
                """
                SELECT m.*, MIN(s.sort_order) AS first_sort_order
                FROM medications m
                JOIN schedule_items s
                    ON s.medication_id = m.id AND s.active = 1
                WHERE m.active = 1
                GROUP BY m.id
                ORDER BY first_sort_order, m.id
                """
            ).fetchall()
            return {
                "medications": [
                    self._public_medication(db, row) for row in medication_rows
                ],
                "summary": self._schedule_summary(db),
            }

    @staticmethod
    def _public_schedule_item(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "medicationId": row["medication_id"],
            "name": row["name"],
            "dose": row["dose"],
            "instructions": row["instructions"],
            "anchor": row["anchor"],
            "offsetMinutes": row["offset_minutes"],
            "sortOrder": row["sort_order"],
        }

    @classmethod
    def _public_medication(
        cls, db: sqlite3.Connection, row: sqlite3.Row
    ) -> dict[str, Any]:
        schedules = db.execute(
            """
            SELECT * FROM schedule_items
            WHERE medication_id = ? AND active = 1
            ORDER BY sort_order, id
            """,
            (row["id"],),
        ).fetchall()
        return {
            "id": row["id"],
            "name": row["name"],
            "revision": row["revision"],
            "timingMode": row["timing_mode"],
            "adjustAfterIntake": row["timing_mode"] == "interval",
            "maxAutoShiftMinutes": row["max_auto_shift_minutes"],
            "schedules": [
                {
                    "id": schedule["id"],
                    "dose": schedule["dose"],
                    "instructions": schedule["instructions"],
                    "anchor": schedule["anchor"],
                    "offsetMinutes": schedule["offset_minutes"],
                    "sortOrder": schedule["sort_order"],
                }
                for schedule in schedules
            ],
        }

    @staticmethod
    def _validate_schedule_item(payload: dict[str, Any]) -> dict[str, Any]:
        raw_name = payload.get("name", "")
        raw_dose = payload.get("dose", "")
        raw_instructions = payload.get("instructions", "")
        raw_anchor = payload.get("anchor", "")
        if not isinstance(raw_name, str):
            raise ValidationError("药品名称不能为空且最多 80 个字符")
        if not isinstance(raw_dose, str):
            raise ValidationError("剂量不能为空且最多 80 个字符")
        if not isinstance(raw_instructions, str):
            raise ValidationError("用药要求最多 160 个字符")
        if not isinstance(raw_anchor, str):
            raise ValidationError("提醒时段无效")
        name = raw_name.strip()
        dose = raw_dose.strip()
        instructions = raw_instructions.strip()
        anchor = raw_anchor
        if not name or len(name) > 80:
            raise ValidationError("药品名称不能为空且最多 80 个字符")
        if not dose or len(dose) > 80:
            raise ValidationError("剂量不能为空且最多 80 个字符")
        if len(instructions) > 160:
            raise ValidationError("用药要求最多 160 个字符")
        if anchor not in ANCHOR_FIELDS:
            raise ValidationError("提醒时段无效")
        try:
            offset = int(payload.get("offsetMinutes", 0))
        except (TypeError, ValueError) as exc:
            raise ValidationError("相对时间无效") from exc
        if not -240 <= offset <= 240:
            raise ValidationError("相对时间必须在前后 240 分钟内")
        return {
            "name": name,
            "dose": dose,
            "instructions": instructions,
            "anchor": anchor,
            "offsetMinutes": offset,
        }

    @classmethod
    def _validate_medication_payload(
        cls, payload: dict[str, Any], *, require_revision: bool
    ) -> dict[str, Any]:
        raw_name = payload.get("name", "")
        if not isinstance(raw_name, str):
            raise ValidationError("药品名称不能为空且最多 80 个字符")
        name = raw_name.strip()
        if not name or len(name) > 80:
            raise ValidationError("药品名称不能为空且最多 80 个字符")

        revision = payload.get("revision")
        if require_revision and (type(revision) is not int or revision < 1):
            raise ValidationError("药物版本无效")

        timing_mode = payload.get("timingMode")
        if timing_mode is not None and (
            not isinstance(timing_mode, str) or timing_mode not in TIMING_MODES
        ):
            raise ValidationError("时间跟随方式无效")

        legacy_adjust_after_intake = payload.get("adjustAfterIntake")
        if (
            legacy_adjust_after_intake is not None
            and type(legacy_adjust_after_intake) is not bool
        ):
            raise ValidationError("动态调整开关无效")

        max_auto_shift_minutes = payload.get("maxAutoShiftMinutes")
        if max_auto_shift_minutes is None and not require_revision:
            max_auto_shift_minutes = DEFAULT_MAX_AUTO_SHIFT_MINUTES
        if max_auto_shift_minutes is not None and (
            type(max_auto_shift_minutes) is not int
            or not 1 <= max_auto_shift_minutes <= 240
        ):
            raise ValidationError("最大自动调整必须在 1 到 240 分钟之间")

        raw_schedules = payload.get("schedules")
        if not isinstance(raw_schedules, list) or not 1 <= len(raw_schedules) <= 24:
            raise ValidationError("每日安排必须包含 1 到 24 项")

        schedules = []
        schedule_ids: set[int] = set()
        slots: set[tuple[str, int]] = set()
        for raw_schedule in raw_schedules:
            if not isinstance(raw_schedule, dict):
                raise ValidationError("每日安排格式无效")
            raw_offset = raw_schedule.get("offsetMinutes", 0)
            if type(raw_offset) is not int:
                raise ValidationError("相对时间无效")
            schedule = cls._validate_schedule_item(
                {**raw_schedule, "name": name}
            )
            raw_id = raw_schedule.get("id")
            if raw_id is not None:
                if type(raw_id) is not int or raw_id < 1:
                    raise ValidationError("用药安排编号无效")
                if raw_id in schedule_ids:
                    raise ValidationError("用药安排编号不能重复")
                schedule_ids.add(raw_id)
                schedule["id"] = raw_id
            slot = (schedule["anchor"], schedule["offsetMinutes"])
            if slot in slots and not require_revision:
                raise ValidationError("同一药物不能有重复的提醒时段")
            slots.add(slot)
            schedules.append(schedule)

        if timing_mode is None:
            if legacy_adjust_after_intake is not None:
                timing_mode = inferred_timing_mode(
                    name,
                    [schedule["anchor"] for schedule in schedules],
                    legacy_adjust_after_intake=legacy_adjust_after_intake,
                )
            elif not require_revision:
                timing_mode = inferred_timing_mode(
                    name,
                    [schedule["anchor"] for schedule in schedules],
                )

        return {
            "name": name,
            "revision": revision,
            "timingMode": timing_mode,
            "maxAutoShiftMinutes": max_auto_shift_minutes,
            "schedules": schedules,
        }

    @classmethod
    def _medication_mutation_response(
        cls,
        db: sqlite3.Connection,
        medication_id: int,
        *,
        created: list[int],
        updated: list[int],
        archived: list[int],
    ) -> dict[str, Any]:
        medication = db.execute(
            "SELECT * FROM medications WHERE id = ?", (medication_id,)
        ).fetchone()
        return {
            "medication": cls._public_medication(db, medication),
            "summary": cls._schedule_summary(db),
            "changes": {
                "createdScheduleIds": created,
                "updatedScheduleIds": updated,
                "archivedScheduleIds": archived,
            },
        }

    def create_medication(self, payload: dict[str, Any]) -> dict[str, Any]:
        values = self._validate_medication_payload(payload, require_revision=False)
        if any("id" in schedule for schedule in values["schedules"]):
            raise ValidationError("新建药物时不能指定用药安排编号")
        stamp = now_iso()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id FROM medications WHERE name = ? AND active = 1",
                (values["name"],),
            ).fetchone()
            if existing is not None:
                raise ConflictError("该药物已存在，请编辑其每日安排")
            cursor = db.execute(
                """
                INSERT INTO medications (
                    name, active, revision, timing_mode, adjust_after_intake,
                    max_auto_shift_minutes, created_at, updated_at
                ) VALUES (?, 1, 1, ?, ?, ?, ?, ?)
                """,
                (
                    values["name"],
                    values["timingMode"],
                    int(values["timingMode"] == "interval"),
                    values["maxAutoShiftMinutes"],
                    stamp,
                    stamp,
                ),
            )
            medication_id = cursor.lastrowid
            next_sort = db.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM schedule_items"
            ).fetchone()[0]
            created = []
            for index, schedule in enumerate(values["schedules"]):
                item_cursor = db.execute(
                    """
                    INSERT INTO schedule_items (
                        medication_id, name, dose, instructions, anchor,
                        offset_minutes, sort_order, active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        medication_id,
                        values["name"],
                        schedule["dose"],
                        schedule["instructions"],
                        schedule["anchor"],
                        schedule["offsetMinutes"],
                        next_sort + index * 10,
                        stamp,
                        stamp,
                    ),
                )
                created.append(item_cursor.lastrowid)
            return self._medication_mutation_response(
                db,
                medication_id,
                created=created,
                updated=[],
                archived=[],
            )

    def update_medication(
        self, medication_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        values = self._validate_medication_payload(payload, require_revision=True)
        stamp = now_iso()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            medication = db.execute(
                "SELECT * FROM medications WHERE id = ?", (medication_id,)
            ).fetchone()
            if medication is None:
                raise ValidationError("未找到该药物")
            if not medication["active"]:
                raise ConflictError("该药物已停用，请刷新后重试")
            if medication["revision"] != values["revision"]:
                raise ConflictError("药物安排已被更新，请刷新后重试")
            timing_mode = (
                medication["timing_mode"]
                if values["timingMode"] is None
                else values["timingMode"]
            )
            max_auto_shift_minutes = (
                medication["max_auto_shift_minutes"]
                if values["maxAutoShiftMinutes"] is None
                else values["maxAutoShiftMinutes"]
            )
            name_conflict = db.execute(
                """
                SELECT id FROM medications
                WHERE name = ? AND active = 1 AND id != ?
                """,
                (values["name"], medication_id),
            ).fetchone()
            if name_conflict is not None:
                raise ConflictError("同名药物已存在，请使用现有药物")

            current_rows = db.execute(
                """
                SELECT * FROM schedule_items
                WHERE medication_id = ? AND active = 1
                ORDER BY sort_order, id
                """,
                (medication_id,),
            ).fetchall()
            current_by_id = {row["id"]: row for row in current_rows}
            retained_ids = {
                schedule["id"]
                for schedule in values["schedules"]
                if "id" in schedule
            }
            unknown_ids = retained_ids - current_by_id.keys()
            if unknown_ids:
                raise ValidationError("用药安排不属于该药物或已停用")

            schedules_by_slot: dict[tuple[str, int], dict[str, Any]] = {}
            for schedule in values["schedules"]:
                slot = (schedule["anchor"], schedule["offsetMinutes"])
                previous = schedules_by_slot.get(slot)
                if previous is None:
                    schedules_by_slot[slot] = schedule
                    continue
                preserves_legacy_duplicate = all(
                    "id" in candidate
                    and (
                        current_by_id[candidate["id"]]["anchor"],
                        current_by_id[candidate["id"]]["offset_minutes"],
                    )
                    == slot
                    for candidate in (previous, schedule)
                )
                if not preserves_legacy_duplicate:
                    raise ValidationError("同一药物不能有重复的提醒时段")

            archived = [
                row["id"] for row in current_rows if row["id"] not in retained_ids
            ]
            db.execute(
                """
                UPDATE schedule_items SET active = 0, updated_at = ?
                WHERE medication_id = ? AND active = 1
                """,
                (stamp, medication_id),
            )
            next_sort = db.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM schedule_items"
            ).fetchone()[0]
            created = []
            updated = []
            new_schedule_index = 0
            for schedule in values["schedules"]:
                if "id" in schedule:
                    schedule_id = schedule["id"]
                    db.execute(
                        """
                        UPDATE schedule_items SET name = ?, dose = ?,
                            instructions = ?, anchor = ?, offset_minutes = ?,
                            active = 1, updated_at = ?
                        WHERE id = ? AND medication_id = ?
                        """,
                        (
                            values["name"],
                            schedule["dose"],
                            schedule["instructions"],
                            schedule["anchor"],
                            schedule["offsetMinutes"],
                            stamp,
                            schedule_id,
                            medication_id,
                        ),
                    )
                    updated.append(schedule_id)
                else:
                    cursor = db.execute(
                        """
                        INSERT INTO schedule_items (
                            medication_id, name, dose, instructions, anchor,
                            offset_minutes, sort_order, active, created_at,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            medication_id,
                            values["name"],
                            schedule["dose"],
                            schedule["instructions"],
                            schedule["anchor"],
                            schedule["offsetMinutes"],
                            next_sort + new_schedule_index * 10,
                            stamp,
                            stamp,
                        ),
                    )
                    new_schedule_index += 1
                    created.append(cursor.lastrowid)

            db.execute(
                """
                UPDATE medications SET name = ?, timing_mode = ?,
                    adjust_after_intake = ?, max_auto_shift_minutes = ?,
                    revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (
                    values["name"],
                    timing_mode,
                    int(timing_mode == "interval"),
                    max_auto_shift_minutes,
                    stamp,
                    medication_id,
                ),
            )
            return self._medication_mutation_response(
                db,
                medication_id,
                created=created,
                updated=updated,
                archived=archived,
            )

    def archive_medication(
        self, medication_id: int, revision: int
    ) -> dict[str, Any]:
        if type(revision) is not int or revision < 1:
            raise ValidationError("药物版本无效")
        stamp = now_iso()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            medication = db.execute(
                "SELECT * FROM medications WHERE id = ?", (medication_id,)
            ).fetchone()
            if medication is None:
                raise ValidationError("未找到该药物")
            if not medication["active"]:
                raise ConflictError("该药物已停用，请刷新后重试")
            if medication["revision"] != revision:
                raise ConflictError("药物安排已被更新，请刷新后再停用")
            archived = [
                row["id"]
                for row in db.execute(
                    """
                    SELECT id FROM schedule_items
                    WHERE medication_id = ? AND active = 1
                    ORDER BY sort_order, id
                    """,
                    (medication_id,),
                ).fetchall()
            ]
            db.execute(
                """
                UPDATE schedule_items SET active = 0, updated_at = ?
                WHERE medication_id = ? AND active = 1
                """,
                (stamp, medication_id),
            )
            db.execute(
                """
                UPDATE medications SET active = 0, revision = revision + 1,
                    updated_at = ? WHERE id = ?
                """,
                (stamp, medication_id),
            )
            return {
                "deleted": True,
                "summary": self._schedule_summary(db),
                "changes": {"archivedScheduleIds": archived},
            }

    def create_schedule_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = self._validate_schedule_item(payload)
        stamp = now_iso()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            medication = db.execute(
                "SELECT * FROM medications WHERE name = ? AND active = 1",
                (item["name"],),
            ).fetchone()
            if medication is None:
                medication_cursor = db.execute(
                    """
                    INSERT INTO medications (
                        name, active, revision, created_at, updated_at
                    ) VALUES (?, 1, 1, ?, ?)
                    """,
                    (item["name"], stamp, stamp),
                )
                medication_id = medication_cursor.lastrowid
            else:
                medication_id = medication["id"]
                duplicate = db.execute(
                    """
                    SELECT id FROM schedule_items
                    WHERE medication_id = ? AND active = 1
                        AND anchor = ? AND offset_minutes = ?
                    """,
                    (medication_id, item["anchor"], item["offsetMinutes"]),
                ).fetchone()
                if duplicate is not None:
                    raise ConflictError("该药物已存在相同提醒时段")
            sort_order = db.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM schedule_items"
            ).fetchone()[0]
            cursor = db.execute(
                """
                INSERT INTO schedule_items (
                    medication_id, name, dose, instructions, anchor,
                    offset_minutes, sort_order, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    medication_id,
                    item["name"],
                    item["dose"],
                    item["instructions"],
                    item["anchor"],
                    item["offsetMinutes"],
                    sort_order,
                    stamp,
                    stamp,
                ),
            )
            if medication is not None:
                db.execute(
                    """
                    UPDATE medications SET revision = revision + 1,
                        updated_at = ? WHERE id = ?
                    """,
                    (stamp, medication_id),
                )
            row = db.execute(
                "SELECT * FROM schedule_items WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return self._public_schedule_item(row)

    def update_schedule_item(
        self, item_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        item = self._validate_schedule_item(payload)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                """
                SELECT s.*, m.name AS medication_name
                FROM schedule_items s
                JOIN medications m ON m.id = s.medication_id
                WHERE s.id = ? AND s.active = 1 AND m.active = 1
                """,
                (item_id,),
            ).fetchone()
            if existing is None:
                raise ValidationError("未找到该用药项目")
            stamp = now_iso()
            source_medication_id = existing["medication_id"]
            target_medication_id = source_medication_id
            created_target = False
            if item["name"] != existing["medication_name"]:
                target = db.execute(
                    "SELECT * FROM medications WHERE name = ? AND active = 1",
                    (item["name"],),
                ).fetchone()
                source_count = db.execute(
                    """
                    SELECT COUNT(*) FROM schedule_items
                    WHERE medication_id = ? AND active = 1
                    """,
                    (source_medication_id,),
                ).fetchone()[0]
                if target is not None:
                    target_medication_id = target["id"]
                elif source_count == 1:
                    db.execute(
                        """
                        UPDATE medications SET name = ?, revision = revision + 1,
                            updated_at = ? WHERE id = ?
                        """,
                        (item["name"], stamp, source_medication_id),
                    )
                else:
                    medication_cursor = db.execute(
                        """
                        INSERT INTO medications (
                            name, active, revision, created_at, updated_at
                        ) VALUES (?, 1, 1, ?, ?)
                        """,
                        (item["name"], stamp, stamp),
                    )
                    target_medication_id = medication_cursor.lastrowid
                    created_target = True

            duplicate = db.execute(
                """
                SELECT id FROM schedule_items
                WHERE medication_id = ? AND active = 1
                    AND anchor = ? AND offset_minutes = ? AND id != ?
                """,
                (
                    target_medication_id,
                    item["anchor"],
                    item["offsetMinutes"],
                    item_id,
                ),
            ).fetchone()
            if duplicate is not None:
                raise ConflictError("该药物已存在相同提醒时段")
            db.execute(
                """
                UPDATE schedule_items SET medication_id = ?, name = ?, dose = ?,
                    instructions = ?, anchor = ?, offset_minutes = ?, updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (
                    target_medication_id,
                    item["name"],
                    item["dose"],
                    item["instructions"],
                    item["anchor"],
                    item["offsetMinutes"],
                    stamp,
                    item_id,
                ),
            )
            if target_medication_id != source_medication_id:
                remaining = db.execute(
                    """
                    SELECT COUNT(*) FROM schedule_items
                    WHERE medication_id = ? AND active = 1
                    """,
                    (source_medication_id,),
                ).fetchone()[0]
                db.execute(
                    """
                    UPDATE medications SET active = ?, revision = revision + 1,
                        updated_at = ? WHERE id = ?
                    """,
                    (int(remaining > 0), stamp, source_medication_id),
                )
                if not created_target:
                    db.execute(
                        """
                        UPDATE medications SET revision = revision + 1,
                            updated_at = ? WHERE id = ?
                        """,
                        (stamp, target_medication_id),
                    )
            elif item["name"] == existing["medication_name"]:
                db.execute(
                    """
                    UPDATE medications SET revision = revision + 1,
                        updated_at = ? WHERE id = ?
                    """,
                    (stamp, source_medication_id),
                )
            row = db.execute(
                "SELECT * FROM schedule_items WHERE id = ?", (item_id,)
            ).fetchone()
        return self._public_schedule_item(row)

    def archive_schedule_item(self, item_id: int) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """
                SELECT medication_id FROM schedule_items
                WHERE id = ? AND active = 1
                """,
                (item_id,),
            ).fetchone()
            if row is None:
                raise ValidationError("未找到该用药项目")
            stamp = now_iso()
            cursor = db.execute(
                """
                UPDATE schedule_items SET active = 0, updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (stamp, item_id),
            )
            if cursor.rowcount == 0:
                raise ValidationError("未找到该用药项目")
            remaining = db.execute(
                """
                SELECT COUNT(*) FROM schedule_items
                WHERE medication_id = ? AND active = 1
                """,
                (row["medication_id"],),
            ).fetchone()[0]
            db.execute(
                """
                UPDATE medications SET active = ?, revision = revision + 1,
                    updated_at = ? WHERE id = ?
                """,
                (int(remaining > 0), stamp, row["medication_id"]),
            )


class MedicationHandler(SimpleHTTPRequestHandler):
    store: MedicationStore
    public_dir: Path
    access_phrase: str | None
    access_sessions: dict[str, float]
    access_sessions_lock: threading.Lock
    demo_phrase: str | None
    demo_sessions: dict[str, float]
    demo_sessions_lock: threading.Lock

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _send_json(
        self,
        payload: Any,
        status: int = HTTPStatus.OK,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _request_is_https(self) -> bool:
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "")
        return forwarded_proto.split(",", 1)[0].strip().lower() == "https"

    def _new_access_token(self) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.access_sessions_lock:
            expired_tokens = [
                session_token
                for session_token, expires_at in self.access_sessions.items()
                if expires_at <= now
            ]
            for expired_token in expired_tokens:
                self.access_sessions.pop(expired_token, None)
            self.access_sessions[token] = now + ACCESS_SESSION_TTL_SECONDS
        return token

    def _access_cookie_header(self, token: str, *, clear: bool = False) -> str:
        cookie = SimpleCookie()
        cookie[ACCESS_COOKIE_NAME] = "" if clear else token
        morsel = cookie[ACCESS_COOKIE_NAME]
        morsel["path"] = "/"
        morsel["httponly"] = True
        morsel["samesite"] = "Strict"
        if clear:
            morsel["max-age"] = "0"
            morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        if self._request_is_https():
            morsel["secure"] = True
        return morsel.OutputString()

    def _has_valid_access_session(self) -> bool:
        if self.access_phrase is None:
            return True
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return False
        morsel = cookies.get(ACCESS_COOKIE_NAME)
        if morsel is None:
            return False
        now = time.time()
        with self.access_sessions_lock:
            expires_at = self.access_sessions.get(morsel.value)
            if expires_at is None:
                return False
            if expires_at <= now:
                self.access_sessions.pop(morsel.value, None)
                return False
        return True

    def _revoke_access_session(self) -> None:
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return
        morsel = cookies.get(ACCESS_COOKIE_NAME)
        if morsel is None:
            return
        with self.access_sessions_lock:
            self.access_sessions.pop(morsel.value, None)

    def _require_access(self) -> bool:
        if self._has_valid_access_session():
            return True
        self._send_json(
            {"error": "请先完成访问验证"},
            HTTPStatus.UNAUTHORIZED,
            headers={"X-TakeTime-Access": "required"},
        )
        return False

    def _handle_access_status(self) -> None:
        self._send_json(
            {
                "required": self.access_phrase is not None,
                "authenticated": self._has_valid_access_session(),
            }
        )

    def _handle_access_verification(self, payload: dict[str, Any]) -> None:
        if self.access_phrase is None:
            self._send_json({"authenticated": True})
            return
        phrase = payload.get("phrase")
        candidate = phrase.strip() if isinstance(phrase, str) else ""
        if not candidate or len(candidate) > 200:
            self._send_json(
                {"error": "请输入访问口令"},
                HTTPStatus.BAD_REQUEST,
            )
            return
        candidate_digest = hashlib.sha256(candidate.encode("utf-8")).digest()
        expected_digest = hashlib.sha256(self.access_phrase.encode("utf-8")).digest()
        if not hmac.compare_digest(candidate_digest, expected_digest):
            self._send_json(
                {"error": "访问口令不正确，请重新输入"},
                HTTPStatus.UNAUTHORIZED,
            )
            return
        self._send_json(
            {"authenticated": True},
            headers={"Set-Cookie": self._access_cookie_header(self._new_access_token())},
        )

    def _new_demo_token(self) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.demo_sessions_lock:
            expired_tokens = [
                session_token
                for session_token, expires_at in self.demo_sessions.items()
                if expires_at <= now
            ]
            for expired_token in expired_tokens:
                self.demo_sessions.pop(expired_token, None)
            self.demo_sessions[token] = now + ACCESS_SESSION_TTL_SECONDS
        return token

    def _demo_cookie_header(self, token: str, *, clear: bool = False) -> str:
        cookie = SimpleCookie()
        cookie[DEMO_ACCESS_COOKIE_NAME] = "" if clear else token
        morsel = cookie[DEMO_ACCESS_COOKIE_NAME]
        morsel["path"] = "/"
        morsel["httponly"] = True
        morsel["samesite"] = "Strict"
        if clear:
            morsel["max-age"] = "0"
            morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        if self._request_is_https():
            morsel["secure"] = True
        return morsel.OutputString()

    def _has_valid_demo_session(self) -> bool:
        if self.demo_phrase is None:
            return False
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return False
        morsel = cookies.get(DEMO_ACCESS_COOKIE_NAME)
        if morsel is None:
            return False
        now = time.time()
        with self.demo_sessions_lock:
            expires_at = self.demo_sessions.get(morsel.value)
            if expires_at is None:
                return False
            if expires_at <= now:
                self.demo_sessions.pop(morsel.value, None)
                return False
        return True

    def _revoke_demo_session(self) -> None:
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return
        morsel = cookies.get(DEMO_ACCESS_COOKIE_NAME)
        if morsel is None:
            return
        with self.demo_sessions_lock:
            self.demo_sessions.pop(morsel.value, None)

    def _handle_demo_access_status(self) -> None:
        if self.demo_phrase is None:
            self._send_json({"error": "演示页面未启用"}, HTTPStatus.NOT_FOUND)
            return
        self._send_json(
            {
                "required": True,
                "authenticated": self._has_valid_demo_session(),
            }
        )

    def _handle_demo_access_verification(self, payload: dict[str, Any]) -> None:
        if self.demo_phrase is None:
            self._send_json({"error": "演示页面未启用"}, HTTPStatus.NOT_FOUND)
            return
        phrase = payload.get("phrase")
        candidate = phrase.strip() if isinstance(phrase, str) else ""
        if not candidate or len(candidate) > 200:
            self._send_json(
                {"error": "请输入演示访问口令"},
                HTTPStatus.BAD_REQUEST,
            )
            return
        candidate_digest = hashlib.sha256(candidate.encode("utf-8")).digest()
        expected_digest = hashlib.sha256(self.demo_phrase.encode("utf-8")).digest()
        if not hmac.compare_digest(candidate_digest, expected_digest):
            self._send_json(
                {"error": "访问口令不正确，请重新输入"},
                HTTPStatus.UNAUTHORIZED,
            )
            return
        self._send_json(
            {"authenticated": True},
            headers={"Set-Cookie": self._demo_cookie_header(self._new_demo_token())},
        )

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValidationError("请求长度无效") from exc
        if length <= 0 or length > 1_000_000:
            raise ValidationError("请求内容为空或过大")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("请求内容不是有效的 JSON") from exc
        if not isinstance(payload, dict):
            raise ValidationError("请求内容必须是对象")
        return payload

    def _read_revision_precondition(self, action: str) -> int:
        raw_revision = self.headers.get("If-Match", "").strip()
        if raw_revision.startswith("W/"):
            raw_revision = raw_revision[2:].strip()
        if (
            len(raw_revision) >= 2
            and raw_revision.startswith('"')
            and raw_revision.endswith('"')
        ):
            raw_revision = raw_revision[1:-1]
        if not raw_revision.isdigit() or int(raw_revision) < 1:
            raise ValidationError(f"{action}药物时必须提供当前版本")
        return int(raw_revision)

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, ConflictError):
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        if isinstance(exc, ValidationError):
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        print(f"Unhandled error: {exc!r}")
        self._send_json({"error": "服务器处理请求时出现问题"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _send_retired_schedule_write(self) -> None:
        self._send_json(
            {"error": "单条计划写接口已停用，请使用 /api/medications"},
            HTTPStatus.GONE,
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/access":
                self._handle_access_status()
            elif parsed.path == "/api/demo-access":
                self._handle_demo_access_status()
            elif parsed.path == "/api/health":
                self._send_json({"status": "ok", "time": now_iso()})
            elif parsed.path.startswith("/api/") and not self._require_access():
                return
            elif parsed.path == "/api/database-status":
                self._send_json(self.store.get_database_status())
            elif parsed.path == "/api/day":
                query = parse_qs(parsed.query)
                day = query.get("date", [today_local().isoformat()])[0]
                self._send_json(self.store.get_day(day))
            elif parsed.path == "/api/history":
                query = parse_qs(parsed.query)
                end_day = query.get("end", [today_local().isoformat()])[0]
                days = int(query.get("days", ["7"])[0])
                self._send_json(self.store.get_history(end_day, days))
            elif parsed.path == "/api/schedule-items":
                self._send_json(self.store.get_schedule_plan())
            elif parsed.path == "/api/medications":
                self._send_json(self.store.get_medication_plan())
            elif parsed.path == "/api/preferences":
                self._send_json(self.store.get_preferences())
            elif parsed.path.startswith("/api/"):
                self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            else:
                self._serve_static(parsed.path)
        except (ValidationError, ValueError) as exc:
            self._handle_error(
                exc if isinstance(exc, ValidationError) else ValidationError("参数无效")
            )
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self._handle_error(exc)

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
            self.send_header("Allow", "GET")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._serve_static(parsed.path, send_body=False)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/access":
                self._handle_access_verification(self._read_json())
                return
            if parsed.path == "/api/demo-access":
                self._handle_demo_access_verification(self._read_json())
                return
            if not self._require_access():
                return
            if parsed.path == "/api/schedule-items":
                self._send_retired_schedule_write()
                return
            payload = self._read_json()
            if parsed.path == "/api/intakes":
                self._send_json(self.store.mark_taken(payload), HTTPStatus.CREATED)
            elif parsed.path == "/api/wake-events":
                day, created = self.store.check_in_wake(payload)
                self._send_json(
                    day, HTTPStatus.CREATED if created else HTTPStatus.OK
                )
            elif parsed.path == "/api/medications":
                medication = self.store.create_medication(payload)
                self._send_json(medication, HTTPStatus.CREATED)
            else:
                self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        try:
            if not self._require_access():
                return
            context_match = re.fullmatch(r"/api/context/(\d{4}-\d{2}-\d{2})", parsed.path)
            item_match = re.fullmatch(r"/api/schedule-items/(\d+)", parsed.path)
            medication_match = re.fullmatch(r"/api/medications/(\d+)", parsed.path)
            if item_match:
                self._send_retired_schedule_write()
                return
            payload = self._read_json()
            if context_match:
                self._send_json(self.store.update_context(context_match.group(1), payload))
            elif parsed.path == "/api/preferences":
                self._send_json(self.store.update_preferences(payload))
            elif medication_match:
                header_revision = self._read_revision_precondition("修改")
                body_revision = payload.get("revision")
                if type(body_revision) is not int or body_revision < 1:
                    raise ValidationError("药物版本无效")
                if body_revision != header_revision:
                    raise ConflictError("If-Match 与请求内容的药物版本不一致")
                medication = self.store.update_medication(
                    int(medication_match.group(1)), payload
                )
                self._send_json(medication)
            else:
                self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/access":
                self._revoke_access_session()
                self._send_json(
                    {"authenticated": False},
                    headers={"Set-Cookie": self._access_cookie_header("", clear=True)},
                )
                return
            if parsed.path == "/api/demo-access":
                if self.demo_phrase is None:
                    self._send_json({"error": "演示页面未启用"}, HTTPStatus.NOT_FOUND)
                    return
                self._revoke_demo_session()
                self._send_json(
                    {"authenticated": False},
                    headers={"Set-Cookie": self._demo_cookie_header("", clear=True)},
                )
                return
            if not self._require_access():
                return
            intake_match = re.fullmatch(
                r"/api/intakes/(\d{4}-\d{2}-\d{2})/(\d+)", parsed.path
            )
            item_match = re.fullmatch(r"/api/schedule-items/(\d+)", parsed.path)
            medication_match = re.fullmatch(r"/api/medications/(\d+)", parsed.path)
            if intake_match:
                self._send_json(
                    self.store.unmark_taken(
                        intake_match.group(1), int(intake_match.group(2))
                    )
                )
            elif item_match:
                self._send_retired_schedule_write()
            elif medication_match:
                self._send_json(
                    self.store.archive_medication(
                        int(medication_match.group(1)),
                        self._read_revision_precondition("停用"),
                    )
                )
            else:
                self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    def _serve_static(self, request_path: str, *, send_body: bool = True) -> None:
        if request_path == "/":
            relative = "index.html"
        elif request_path in {"/demo", "/demo/"}:
            relative = "demo.html"
        else:
            relative = unquote(request_path.lstrip("/"))
        candidate = (self.public_dir / relative).resolve()
        public_root = self.public_dir.resolve()
        if public_root not in candidate.parents and candidate != public_root:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        is_private_entry_request = candidate == public_root / "index.html"
        is_demo_entry_request = candidate == public_root / "demo.html"
        if is_demo_entry_request:
            if self.demo_phrase is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not self._has_valid_demo_session():
                candidate = public_root / "access.html"
        if (
            is_private_entry_request
            and self.access_phrase is not None
            and not self._has_valid_access_session()
        ):
            candidate = public_root / "access.html"
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        stat = candidate.stat()
        etag = f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        last_modified = formatdate(stat.st_mtime, usegmt=True)
        entry_gate_enabled = (
            is_private_entry_request and self.access_phrase is not None
        ) or is_demo_entry_request
        cache_control = "no-store" if entry_gate_enabled else (
            "no-cache"
            if candidate.suffix in {".html", ".js", ".css"}
            else "public, max-age=86400"
        )

        if_none_match = self.headers.get("If-None-Match")
        current_opaque_tag = etag.removeprefix("W/")
        not_modified = bool(
            if_none_match
            and any(
                candidate == "*" or candidate.removeprefix("W/") == current_opaque_tag
                for candidate in map(str.strip, if_none_match.split(","))
            )
        )
        if not if_none_match:
            if_modified_since = self.headers.get("If-Modified-Since")
            if if_modified_since:
                try:
                    not_modified = int(stat.st_mtime) <= int(
                        parsedate_to_datetime(if_modified_since).timestamp()
                    )
                except (TypeError, ValueError, OverflowError):
                    pass

        if not_modified and cache_control != "no-store":
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("Cache-Control", cache_control)
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", last_modified)
            self.end_headers()
            return

        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Cache-Control", cache_control)
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", last_modified)
        if entry_gate_enabled:
            self.send_header("Vary", "Cookie")
        self.end_headers()
        if send_body:
            self.wfile.write(candidate.read_bytes())


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: Path = DEFAULT_DB_PATH,
    public_dir: Path = PUBLIC_DIR,
    *,
    require_existing_db: bool = False,
    access_phrase: str | None = None,
    demo_phrase: str | None = None,
) -> ThreadingHTTPServer:
    database_path = Path(db_path)
    if require_existing_db:
        require_existing_database(database_path)
    store = MedicationStore(database_path)

    class BoundHandler(MedicationHandler):
        pass

    BoundHandler.store = store
    BoundHandler.public_dir = Path(public_dir)
    normalized_phrase = access_phrase.strip() if access_phrase else ""
    BoundHandler.access_phrase = normalized_phrase or None
    BoundHandler.access_sessions = {}
    BoundHandler.access_sessions_lock = threading.Lock()
    normalized_demo_phrase = demo_phrase.strip() if demo_phrase else ""
    BoundHandler.demo_phrase = normalized_demo_phrase or None
    BoundHandler.demo_sessions = {}
    BoundHandler.demo_sessions_lock = threading.Lock()
    return ThreadingHTTPServer((host, port), BoundHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="本地用药记录与提醒服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--require-existing-db", action="store_true")
    args = parser.parse_args()
    access_phrase = os.environ.get("TAKETIME_ACCESS_PHRASE", "").strip()
    demo_phrase = os.environ.get("TAKETIME_DEMO_PHRASE", "").strip()
    if not access_phrase:
        parser.error("TAKETIME_ACCESS_PHRASE must be set")

    server = create_server(
        args.host,
        args.port,
        args.db,
        require_existing_db=args.require_existing_db,
        access_phrase=access_phrase,
        demo_phrase=demo_phrase,
    )
    print(f"用药记录服务已启动：http://{args.host}:{server.server_port}")
    print(f"数据文件：{Path(args.db).resolve()}")
    print(
        "访问验证："
        + ("已启用" if server.RequestHandlerClass.access_phrase else "未启用")
    )
    print(
        "演示入口："
        + ("已启用" if server.RequestHandlerClass.demo_phrase else "未启用")
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止服务…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
