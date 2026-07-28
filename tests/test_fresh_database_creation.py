import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from scripts.create_fresh_database import (
    FreshDatabaseCreationError,
    create_fresh_database,
)


class FreshDatabaseCreationTest(unittest.TestCase):
    def test_exclusively_creates_verified_six_by_thirteen_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "medication.db"

            report = create_fresh_database(db_path)

            self.assertEqual(report["medicationCount"], 6)
            self.assertEqual(report["dailyAdministrationCount"], 13)
            self.assertEqual(set(report["historyRows"].values()), {0})
            self.assertEqual(stat.S_IMODE(db_path.stat().st_mode), 0o600)
            with sqlite3.connect(db_path) as db:
                self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{db_path}{suffix}")
                if sidecar.exists():
                    self.assertTrue(sidecar.is_file())
                    self.assertFalse(sidecar.is_symlink())

    def test_existing_database_is_never_opened_or_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "medication.db"
            original = b"existing private database"
            db_path.write_bytes(original)

            with self.assertRaisesRegex(
                FreshDatabaseCreationError,
                "refusing existing database path",
            ):
                create_fresh_database(db_path)

            self.assertEqual(db_path.read_bytes(), original)

    def test_existing_sidecar_blocks_creation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "medication.db"
            sidecar = Path(f"{db_path}-wal")
            sidecar.write_bytes(b"deleted private history")

            with self.assertRaisesRegex(
                FreshDatabaseCreationError,
                "refusing existing database sidecars",
            ):
                create_fresh_database(db_path)

            self.assertFalse(db_path.exists())
            self.assertEqual(sidecar.read_bytes(), b"deleted private history")

    def test_symbolic_link_database_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target.db"
            target.write_bytes(b"private database")
            linked_db = root / "medication.db"
            linked_db.symlink_to(target)

            with self.assertRaisesRegex(
                FreshDatabaseCreationError,
                "refusing existing database path",
            ):
                create_fresh_database(linked_db)

            self.assertEqual(target.read_bytes(), b"private database")


if __name__ == "__main__":
    unittest.main()
