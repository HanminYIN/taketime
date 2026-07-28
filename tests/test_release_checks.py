import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.verify_release_artifact import (
    REQUIRED_FILES,
    ReleaseArtifactVerificationError,
    verify_release_artifact,
)


class ReleaseArtifactVerificationTest(unittest.TestCase):
    @staticmethod
    def create_clean_release(root: Path) -> None:
        for relative in REQUIRED_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("release fixture", encoding="utf-8")

    def test_clean_release_directory_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.create_clean_release(root)

            report = verify_release_artifact(root)

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["fileCount"], len(REQUIRED_FILES))
        self.assertEqual(report["databaseFiles"], 0)

    def test_sqlite_content_is_rejected_even_when_renamed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.create_clean_release(root)
            disguised = root / "public" / "cache.bin"
            disguised.write_bytes(b"SQLite format 3\x00" + b"private data")

            with self.assertRaisesRegex(
                ReleaseArtifactVerificationError,
                "SQLite content is not allowed",
            ):
                verify_release_artifact(root)

    def test_data_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.create_clean_release(root)
            data_file = root / "data" / "notes.txt"
            data_file.parent.mkdir()
            data_file.write_text("private data", encoding="utf-8")

            with self.assertRaisesRegex(
                ReleaseArtifactVerificationError,
                "forbidden directory",
            ):
                verify_release_artifact(root)

    def test_python_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.create_clean_release(root)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "server.cpython-312.pyc").write_bytes(b"compiled code")

            with self.assertRaisesRegex(
                ReleaseArtifactVerificationError,
                "forbidden directory: __pycache__",
            ):
                verify_release_artifact(root)

    def test_git_metadata_is_rejected_instead_of_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.create_clean_release(root)
            leaked = root / ".git" / "objects" / "private.db"
            leaked.parent.mkdir(parents=True)
            leaked.write_bytes(b"SQLite format 3\x00" + b"private data")

            with self.assertRaisesRegex(
                ReleaseArtifactVerificationError,
                "forbidden directory: \\.git",
            ):
                verify_release_artifact(root)

    def test_renamed_sqlite_sidecars_are_rejected_by_content(self):
        signatures = (
            ("wal-cache.bin", b"\x37\x7f\x06\x82"),
            ("shm-cache.bin", b"\x18\xe2\x2d\x00"),
            ("journal-cache.bin", b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7"),
        )
        for name, signature in signatures:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    self.create_clean_release(root)
                    (root / "public" / name).write_bytes(signature + b"private data")

                    with self.assertRaisesRegex(
                        ReleaseArtifactVerificationError,
                        "SQLite .* content is not allowed",
                    ):
                        verify_release_artifact(root)

    def test_archives_are_rejected_without_extracting_them(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.create_clean_release(root)
            archive = root / "public" / "assets" / "bundle.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("history.db", b"SQLite format 3\x00private data")

            with self.assertRaisesRegex(
                ReleaseArtifactVerificationError,
                "archive file is not allowed",
            ):
                verify_release_artifact(root)

    def test_symbolic_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.create_clean_release(root)
            (root / "public" / "linked-file").symlink_to(root / "server.py")

            with self.assertRaisesRegex(
                ReleaseArtifactVerificationError,
                "symbolic link is not allowed",
            ):
                verify_release_artifact(root)

    def test_missing_frontend_runtime_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.create_clean_release(root)
            (root / "public" / "app.js").unlink()

            with self.assertRaisesRegex(
                ReleaseArtifactVerificationError,
                "missing required release files: public/app.js",
            ):
                verify_release_artifact(root)


if __name__ == "__main__":
    unittest.main()
