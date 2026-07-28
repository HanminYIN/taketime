import io
import json
import os
import pwd
import sqlite3
import tempfile
import threading
import unittest
from collections import Counter
from contextlib import closing
from datetime import date, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from scripts.verify_fresh_database import (
    FreshDatabaseVerificationError,
    verify_fresh_database,
)
from server import ConflictError, MedicationStore, create_server, main as server_main, today_local


class AccessControlServerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        public = root / "public"
        public.mkdir()
        (public / "index.html").write_text("tracker", encoding="utf-8")
        (public / "access.html").write_text("access", encoding="utf-8")
        (public / "demo.html").write_text("demo", encoding="utf-8")
        (public / "styles.css").write_text("body {}", encoding="utf-8")
        self.server = create_server(
            port=0,
            db_path=root / "test.db",
            public_dir=public,
            access_phrase="测试访问口令",
            demo_phrase="测试演示口令",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def open(
        self,
        path,
        *,
        method="GET",
        payload=None,
        headers=None,
        authenticated=False,
        opener=None,
    ):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = dict(headers or {})
        if payload is not None:
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(
            self.base_url + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        request_opener = opener or (self.opener if authenticated else build_opener())
        return request_opener.open(request, timeout=3)

    def test_access_gate_protects_entry_and_private_apis(self):
        with self.open("/api/health") as response:
            self.assertEqual(response.status, 200)

        for path in ("/", "/index.html", "/assets/%2e%2e/index.html"):
            with self.subTest(path=path), self.open(path) as response:
                self.assertEqual(response.read().decode("utf-8"), "access")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(response.headers["Vary"], "Cookie")

        with self.assertRaises(HTTPError) as raised:
            self.open("/api/medications")
        self.assertEqual(raised.exception.code, 401)
        self.assertEqual(raised.exception.headers["X-TakeTime-Access"], "required")
        raised.exception.close()

        invalid_body = Request(
            self.base_url + "/api/intakes",
            data=b"not-json",
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            build_opener().open(invalid_body, timeout=3)
        self.assertEqual(raised.exception.code, 401)
        raised.exception.close()

    def test_correct_phrase_creates_session_and_lock_clears_it(self):
        with self.assertRaises(HTTPError) as raised:
            self.open(
                "/api/access",
                method="POST",
                payload={"phrase": "错误口令"},
                authenticated=True,
            )
        self.assertEqual(raised.exception.code, 401)
        self.assertIsNone(raised.exception.headers.get("Set-Cookie"))
        raised.exception.close()

        with self.open(
            "/api/access",
            method="POST",
            payload={"phrase": "  测试访问口令  "},
            authenticated=True,
        ) as response:
            cookie = response.headers["Set-Cookie"]
            cookie_pair = cookie.split(";", 1)[0]
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            self.assertIn("Path=/", cookie)
            self.assertNotIn("Domain=", cookie)
            self.assertNotIn("Max-Age=", cookie)
            self.assertNotIn("测试访问口令", cookie)
            self.assertNotIn("Secure", cookie)

        with self.open("/", authenticated=True) as response:
            self.assertEqual(response.read().decode("utf-8"), "tracker")
        with self.open("/api/medications", authenticated=True) as response:
            self.assertEqual(response.status, 200)

        with self.open("/api/access", method="DELETE", authenticated=True) as response:
            self.assertIn("Max-Age=0", response.headers["Set-Cookie"])
            self.assertIn("expires=Thu, 01 Jan 1970 00:00:00 GMT", response.headers["Set-Cookie"])
        with self.open("/", authenticated=True) as response:
            self.assertEqual(response.read().decode("utf-8"), "access")
        with self.assertRaises(HTTPError) as raised:
            self.open("/api/medications", headers={"Cookie": cookie_pair})
        self.assertEqual(raised.exception.code, 401)
        raised.exception.close()

    def test_demo_phrase_opens_only_the_demo_and_logout_revokes_it(self):
        demo_opener = build_opener(HTTPCookieProcessor(CookieJar()))
        for path in (
            "/demo",
            "/demo/",
            "/demo.html",
            "/assets/%2e%2e/demo.html",
        ):
            with self.subTest(path=path), self.open(path, opener=demo_opener) as response:
                self.assertEqual(response.read().decode("utf-8"), "access")

        with self.assertRaises(HTTPError) as raised:
            self.open(
                "/api/demo-access",
                method="POST",
                payload={"phrase": "错误口令"},
                opener=demo_opener,
            )
        self.assertEqual(raised.exception.code, 401)
        raised.exception.close()

        with self.open(
            "/api/demo-access",
            method="POST",
            payload={"phrase": "  测试演示口令  "},
            opener=demo_opener,
        ) as response:
            cookie = response.headers["Set-Cookie"]
            stale_cookie = cookie.split(";", 1)[0]
            self.assertTrue(stale_cookie.startswith("taketime_demo_access="))

        with self.open("/demo", opener=demo_opener) as response:
            self.assertEqual(response.read().decode("utf-8"), "demo")
        with self.assertRaises(HTTPError) as raised:
            self.open("/api/medications", opener=demo_opener)
        self.assertEqual(raised.exception.code, 401)
        raised.exception.close()

        with self.open(
            "/api/demo-access", method="DELETE", opener=demo_opener
        ) as response:
            self.assertIn("Max-Age=0", response.headers["Set-Cookie"])
        with self.open("/demo", opener=demo_opener) as response:
            self.assertEqual(response.read().decode("utf-8"), "access")
        with self.open("/demo", headers={"Cookie": stale_cookie}) as response:
            self.assertEqual(response.read().decode("utf-8"), "access")

    def test_private_session_does_not_open_the_demo(self):
        private_opener = build_opener(HTTPCookieProcessor(CookieJar()))
        with self.open(
            "/api/access",
            method="POST",
            payload={"phrase": "测试访问口令"},
            opener=private_opener,
        ):
            pass

        with self.open("/", opener=private_opener) as response:
            self.assertEqual(response.read().decode("utf-8"), "tracker")
        with self.open("/api/medications", opener=private_opener) as response:
            self.assertEqual(response.status, 200)
        with self.open("/demo", opener=private_opener) as response:
            self.assertEqual(response.read().decode("utf-8"), "access")

    def test_demo_route_is_not_published_without_a_phrase(self):
        root = Path(self.temp_dir.name)
        server = create_server(
            port=0,
            db_path=root / "disabled-demo.db",
            public_dir=root / "public",
            access_phrase="测试访问口令",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            for path in ("/demo", "/demo/", "/demo.html", "/api/demo-access"):
                with self.subTest(path=path), self.assertRaises(HTTPError) as raised:
                    urlopen(base_url + path, timeout=3)
                self.assertEqual(raised.exception.code, 404)
                raised.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_https_proxy_sets_secure_cookie(self):
        with self.open(
            "/api/access",
            method="POST",
            payload={"phrase": "测试访问口令"},
            headers={"X-Forwarded-Proto": "https"},
        ) as response:
            self.assertIn("Secure", response.headers["Set-Cookie"])

    def test_fresh_database_verifier_can_authenticate_to_the_api(self):
        report = verify_fresh_database(
            Path(self.temp_dir.name) / "test.db",
            api_url=self.base_url,
            api_access_phrase="测试访问口令",
        )
        self.assertTrue(report["apiVerified"])

    def test_command_line_server_requires_an_access_phrase(self):
        with (
            patch.dict(os.environ, {"TAKETIME_ACCESS_PHRASE": "   "}),
            patch("sys.argv", ["server.py"]),
            patch("sys.stderr", io.StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            server_main()
        self.assertEqual(raised.exception.code, 2)


class MedicationServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        root = Path(cls.temp_dir.name)
        public = root / "public"
        public.mkdir()
        (public / "index.html").write_text("tracker", encoding="utf-8")
        (public / "app.js").write_text("console.log('tracker')", encoding="utf-8")
        cls.db_path = root / "test.db"
        cls.server = create_server(
            port=0,
            db_path=cls.db_path,
            public_dir=public,
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        today = today_local()
        cls.today = today.isoformat()
        cls.tomorrow = (today + timedelta(days=1)).isoformat()
        cls.intake_day = (today + timedelta(days=2)).isoformat()
        cls.invalid_day = (today + timedelta(days=5)).isoformat()
        cls.plan_day = (today + timedelta(days=30)).isoformat()
        cls.plan_next_day = (today + timedelta(days=31)).isoformat()
        cls.history_start = today + timedelta(days=100)
        cls.empty_snapshot_day = (today + timedelta(days=200)).isoformat()
        cls.unmark_day = (today + timedelta(days=300)).isoformat()
        cls.wake_empty_snapshot_day = (today + timedelta(days=400)).isoformat()
        cls.wake_reschedule_day = (today + timedelta(days=500)).isoformat()
        cls.non_today_wake_day = (today + timedelta(days=600)).isoformat()
        cls.read_only_day = (today + timedelta(days=3650)).isoformat()
        cls.past_day = (today - timedelta(days=3650)).isoformat()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp_dir.cleanup()

    def request(self, path, method="GET", payload=None, headers=None):
        data = None
        request_headers = dict(headers or {})
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(
            self.base_url + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        with urlopen(request, timeout=3) as response:
            body = response.read().decode("utf-8")
            if response.headers.get_content_type() == "application/json":
                return response.status, json.loads(body)
            return response.status, body

    def test_health_and_static_page(self):
        status, payload = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(body, "tracker")

    def test_production_server_requires_a_real_existing_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            public = root / "public"
            public.mkdir()
            (public / "index.html").write_text("tracker", encoding="utf-8")
            db_path = root / "missing.db"

            with self.assertRaisesRegex(RuntimeError, "required database is missing"):
                create_server(
                    port=0,
                    db_path=db_path,
                    public_dir=public,
                    require_existing_db=True,
                )
            self.assertFalse(db_path.exists())

            empty_db = root / "empty.db"
            empty_db.write_bytes(b"")
            with self.assertRaisesRegex(RuntimeError, "schema version is unsupported: 0"):
                create_server(
                    port=0,
                    db_path=empty_db,
                    public_dir=public,
                    require_existing_db=True,
                )
            self.assertEqual(empty_db.read_bytes(), b"")

            corrupt_db = root / "corrupt.db"
            corrupt_db.write_bytes(b"not a SQLite database")
            with self.assertRaisesRegex(RuntimeError, "cannot be validated"):
                create_server(
                    port=0,
                    db_path=corrupt_db,
                    public_dir=public,
                    require_existing_db=True,
                )

            target = root / "target.db"
            MedicationStore(target)
            db_path.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                create_server(
                    port=0,
                    db_path=db_path,
                    public_dir=public,
                    require_existing_db=True,
                )

            server = create_server(
                port=0,
                db_path=target,
                public_dir=public,
                require_existing_db=True,
            )
            server.server_close()

    def test_static_files_support_head_and_conditional_requests(self):
        head_request = Request(self.base_url + "/app.js", method="HEAD")
        with urlopen(head_request, timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"")
            self.assertEqual(response.headers["Cache-Control"], "no-cache")
            self.assertEqual(response.headers["Content-Length"], "22")
            etag = response.headers["ETag"]
            last_modified = response.headers["Last-Modified"]

        self.assertTrue(etag.startswith('W/"'))
        self.assertTrue(last_modified.endswith("GMT"))

        weak_conditional_request = Request(
            self.base_url + "/app.js",
            headers={"If-None-Match": etag.removeprefix("W/")},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(weak_conditional_request, timeout=3)
        self.assertEqual(error.exception.code, 304)
        self.assertEqual(error.exception.headers["ETag"], etag)
        self.assertEqual(error.exception.read(), b"")
        error.exception.close()

        modified_since_request = Request(
            self.base_url + "/app.js",
            headers={"If-Modified-Since": last_modified},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(modified_since_request, timeout=3)
        self.assertEqual(error.exception.code, 304)
        error.exception.close()

        etag_precedence_request = Request(
            self.base_url + "/app.js",
            headers={
                "If-None-Match": 'W/"stale"',
                "If-Modified-Since": last_modified,
            },
        )
        with urlopen(etag_precedence_request, timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"console.log('tracker')")

        conditional_head_request = Request(
            self.base_url + "/app.js",
            headers={"If-None-Match": etag},
            method="HEAD",
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(conditional_head_request, timeout=3)
        self.assertEqual(error.exception.code, 304)
        self.assertEqual(error.exception.read(), b"")
        error.exception.close()

        api_head_request = Request(self.base_url + "/api/health", method="HEAD")
        with self.assertRaises(HTTPError) as error:
            urlopen(api_head_request, timeout=3)
        self.assertEqual(error.exception.code, 405)
        self.assertEqual(error.exception.headers["Allow"], "GET")
        error.exception.close()

    def test_default_day_contains_complete_regimen(self):
        status, day = self.request(f"/api/day?date={self.today}")
        self.assertEqual(status, 200)
        self.assertEqual(day["summary"]["total"], 13)
        self.assertTrue(day["preview"])
        self.assertFalse(day["persisted"])
        self.assertEqual(
            [item["scheduledAt"] for item in day["items"]],
            sorted(item["scheduledAt"] for item in day["items"]),
        )
        pancreatic = [
            item for item in day["items"] if item["name"] == "示例药 A"
        ]
        interval_item = next(
            item
            for item in day["items"]
            if item["name"] == "示例药 C" and item["anchor"] == "breakfast"
        )
        self.assertEqual(
            [(item["anchor"], item["scheduledTime"]) for item in pancreatic],
            [("wake", "07:00"), ("lunch", "12:15"), ("dinner", "17:30")],
        )
        self.assertEqual(interval_item["scheduledTime"], "07:30")
        meal_items = [item for item in day["items"] if item["name"] == "示例药 D"]
        self.assertEqual(len(meal_items), 2)

    def test_default_schedule_summary_separates_medications_and_administrations(self):
        status, schedule = self.request("/api/schedule-items")
        self.assertEqual(status, 200)
        self.assertEqual(len(schedule["items"]), 13)
        self.assertEqual(
            schedule["summary"],
            {"medicationCount": 6, "dailyAdministrationCount": 13},
        )

        status, medication_plan = self.request("/api/medications")
        self.assertEqual(status, 200)
        self.assertEqual(len(medication_plan["medications"]), 6)
        self.assertEqual(medication_plan["summary"], schedule["summary"])
        self.assertEqual(
            {
                medication["name"]: medication["timingMode"]
                for medication in medication_plan["medications"]
            },
            {
                "示例药 A": "interval",
                "示例药 B": "routine",
                "示例药 C": "interval",
                "示例药 D": "meal",
                "示例药 E": "interval",
                "示例药 F": "routine",
            },
        )
        self.assertTrue(
            all(
                medication["adjustAfterIntake"]
                == (medication["timingMode"] == "interval")
                and medication["maxAutoShiftMinutes"] == 120
                for medication in medication_plan["medications"]
            )
        )
        pancreatic = next(
            medication
            for medication in medication_plan["medications"]
            if medication["name"] == "示例药 A"
        )
        self.assertEqual(
            [schedule["anchor"] for schedule in pancreatic["schedules"]],
            ["wake", "lunch", "dinner"],
        )
        interval_medication = next(
            medication
            for medication in medication_plan["medications"]
            if medication["name"] == "示例药 C"
        )
        self.assertEqual(len(interval_medication["schedules"]), 3)
        self.assertEqual(interval_medication["revision"], 1)

    def test_medication_reference_matches_default_frequencies(self):
        reference = Path(__file__).resolve().parents[1] / "示例计划.md"
        checklist = Counter(
            line.removeprefix("- [ ] ")
            for line in reference.read_text(encoding="utf-8").splitlines()
            if line.startswith("- [ ] ")
        )

        self.assertEqual(
            checklist,
            Counter(
                {
                    "示例药 A 1份": 3,
                    "示例药 B 1份": 1,
                    "示例药 C 1份": 3,
                    "示例药 D 1份": 2,
                    "示例药 E 1份": 3,
                    "示例药 F 1份": 1,
                }
            ),
        )

    def test_fresh_release_database_contains_only_the_default_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "fresh-release.db"
            MedicationStore(db_path)
            report = verify_fresh_database(db_path, sidecar_policy="wal")

        self.assertEqual(
            report,
            {
                "status": "ok",
                "schemaVersion": 5,
                "medicationCount": 6,
                "dailyAdministrationCount": 13,
                "historyRows": {
                    "daily_context": 0,
                    "daily_instances": 0,
                    "intake_logs": 0,
                    "wake_events": 0,
                },
                "apiVerified": False,
            },
        )

    def test_fresh_release_database_rejects_personal_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "not-fresh-release.db"
            store = MedicationStore(db_path)
            store.update_context(
                "2099-04-01",
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "21:00",
                },
            )

            with self.assertRaisesRegex(
                FreshDatabaseVerificationError,
                "daily_context must be empty",
            ):
                verify_fresh_database(db_path, sidecar_policy="wal")

    def test_fresh_release_database_rejects_modified_defaults(self):
        cases = (
            (
                "UPDATE schedule_items SET dose = '错误剂量' WHERE id = 1",
                "active plan does not match",
            ),
            (
                "UPDATE preferences SET wake_time = '08:00' WHERE id = 1",
                "preferences do not match",
            ),
            ("PRAGMA user_version = 4", "expected schema version 5"),
        )
        for statement, message in cases:
            with self.subTest(statement=statement):
                with tempfile.TemporaryDirectory() as temp_dir:
                    db_path = Path(temp_dir) / "modified-release.db"
                    MedicationStore(db_path)
                    with closing(sqlite3.connect(db_path)) as db, db:
                        db.execute(statement)

                    with self.assertRaisesRegex(
                        FreshDatabaseVerificationError,
                        message,
                    ):
                        verify_fresh_database(db_path, sidecar_policy="wal")

    def test_fresh_release_database_rejects_orphan_schedule_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "orphan-schedule.db"
            MedicationStore(db_path)
            with closing(sqlite3.connect(db_path)) as db, db:
                db.execute(
                    """
                    INSERT INTO schedule_items (
                        id, medication_id, name, dose, instructions, anchor,
                        offset_minutes, sort_order, active, created_at, updated_at
                    ) VALUES (0, NULL, 'PRIVATE MEDICATION', '1片', '', 'wake',
                              0, 5, 1, 'x', 'x')
                    """
                )

            with self.assertRaisesRegex(
                FreshDatabaseVerificationError,
                "active plan does not match",
            ):
                verify_fresh_database(db_path, sidecar_policy="wal")

    def test_fresh_release_wal_only_plan_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "wal-plan-change.db"
            MedicationStore(db_path)
            with closing(sqlite3.connect(db_path)) as writer:
                writer.execute("PRAGMA wal_autocheckpoint = 0")
                writer.execute(
                    "UPDATE schedule_items SET dose = '错误剂量' WHERE id = 13"
                )
                writer.commit()
                self.assertTrue(Path(f"{db_path}-wal").exists())
                with self.assertRaisesRegex(
                    FreshDatabaseVerificationError,
                    "active plan does not match",
                ):
                    verify_fresh_database(db_path, sidecar_policy="wal")

    def test_fresh_release_wal_only_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "wal-history.db"
            MedicationStore(db_path)
            with closing(sqlite3.connect(db_path)) as writer:
                writer.execute("PRAGMA wal_autocheckpoint = 0")
                writer.execute(
                    """
                    INSERT INTO daily_context (
                        date, wake_time, breakfast_time, lunch_time, dinner_time,
                        bedtime_time, source, updated_at
                    ) VALUES ('2099-01-01', '07:00', '07:45', '12:15', '17:30',
                              '21:00', 'manual', '2099-01-01T07:00:00')
                    """
                )
                writer.commit()
                self.assertTrue(Path(f"{db_path}-wal").exists())
                with self.assertRaisesRegex(
                    FreshDatabaseVerificationError,
                    "daily_context must be empty",
                ):
                    verify_fresh_database(db_path, sidecar_policy="wal")

    def test_fresh_release_database_rejects_sqlite_sidecars(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "sidecar.db"
            MedicationStore(db_path)
            Path(f"{db_path}-wal").write_bytes(b"deleted private history")

            with self.assertRaisesRegex(
                FreshDatabaseVerificationError,
                "must not have WAL, SHM, or journal sidecars",
            ):
                verify_fresh_database(db_path)

    def test_fresh_release_database_checks_owner_and_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "permissions.db"
            MedicationStore(db_path)
            db_path.chmod(0o600)
            owner = pwd.getpwuid(os.getuid()).pw_name

            report = verify_fresh_database(
                db_path,
                required_owner=owner,
                required_mode=0o600,
                sidecar_policy="wal",
            )
            self.assertEqual(report["status"], "ok")

            with self.assertRaisesRegex(
                FreshDatabaseVerificationError,
                "expected database owner",
            ):
                verify_fresh_database(
                    db_path,
                    required_owner="not-the-current-owner",
                    sidecar_policy="wal",
                )

            db_path.chmod(0o640)
            with self.assertRaisesRegex(
                FreshDatabaseVerificationError,
                "expected database mode 0600, got 0640",
            ):
                verify_fresh_database(
                    db_path, required_mode=0o600, sidecar_policy="wal"
                )

            linked_db = Path(temp_dir) / "linked.db"
            linked_db.symlink_to(db_path)
            with self.assertRaisesRegex(
                FreshDatabaseVerificationError,
                "database path must not be a symbolic link",
            ):
                verify_fresh_database(linked_db)

    def test_fresh_release_api_must_use_the_verified_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            public = root / "public"
            public.mkdir()
            (public / "index.html").write_text("tracker", encoding="utf-8")
            verified_db = root / "verified.db"
            served_db = root / "served.db"
            MedicationStore(verified_db)
            served_store = MedicationStore(served_db)
            served_store.update_context(
                "2099-04-01",
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "21:00",
                },
            )
            server = create_server(port=0, db_path=served_db, public_dir=public)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaisesRegex(
                    FreshDatabaseVerificationError,
                    "API is not using the verified database file",
                ):
                    verify_fresh_database(
                        verified_db,
                        api_url=f"http://127.0.0.1:{server.server_port}",
                    )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_fresh_release_api_verifies_the_same_clean_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            public = root / "public"
            public.mkdir()
            (public / "index.html").write_text("tracker", encoding="utf-8")
            db_path = root / "verified-and-served.db"
            server = create_server(port=0, db_path=db_path, public_dir=public)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            with closing(sqlite3.connect(db_path)) as keeper:
                keeper.execute("PRAGMA journal_mode = WAL")
                keeper.execute("SELECT COUNT(*) FROM medications").fetchone()
                self.assertTrue(Path(f"{db_path}-wal").exists())
                self.assertTrue(Path(f"{db_path}-shm").exists())
                try:
                    report = verify_fresh_database(
                        db_path,
                        api_url=f"http://127.0.0.1:{server.server_port}",
                    )
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

        self.assertTrue(report["apiVerified"])

    def test_wal_policy_rejects_rollback_journal_and_sidecar_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "sidecar-policy.db"
            MedicationStore(db_path)
            journal = Path(f"{db_path}-journal")
            journal.write_bytes(b"unexpected rollback journal")
            with self.assertRaisesRegex(
                FreshDatabaseVerificationError, "rollback journal"
            ):
                verify_fresh_database(db_path, sidecar_policy="wal")
            journal.unlink()

            target = Path(temp_dir) / "unexpected-wal"
            target.write_bytes(b"unexpected WAL")
            wal = Path(f"{db_path}-wal")
            if wal.exists():
                wal.unlink()
            wal.symlink_to(target)
            with self.assertRaisesRegex(
                FreshDatabaseVerificationError, "symbolic link"
            ):
                verify_fresh_database(db_path, sidecar_policy="wal")

    def test_legacy_single_schedule_mutations_are_retired(self):
        payload = {
            "name": "旧接口测试药物",
            "dose": "1片",
            "instructions": "",
            "anchor": "lunch",
            "offsetMinutes": 0,
        }
        _, before = self.request("/api/medications")
        requests = (
            ("/api/schedule-items", "POST"),
            ("/api/schedule-items/1", "PUT"),
            ("/api/schedule-items/1", "DELETE"),
        )
        for path, method in requests:
            with self.subTest(method=method):
                with self.assertRaises(HTTPError) as raised:
                    self.request(
                        path,
                        method=method,
                        payload=payload if method != "DELETE" else None,
                    )
                self.assertEqual(raised.exception.code, 410)
                error = json.loads(raised.exception.read().decode("utf-8"))
                self.assertIn("/api/medications", error["error"])
                raised.exception.close()
        _, after = self.request("/api/medications")
        self.assertEqual(after, before)

    def test_v2_schedule_rows_are_backfilled_into_stable_medications(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "v2.db"
            with closing(sqlite3.connect(db_path)) as db, db:
                db.executescript(
                    """
                    CREATE TABLE schedule_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        dose TEXT NOT NULL,
                        instructions TEXT NOT NULL DEFAULT '',
                        anchor TEXT NOT NULL,
                        offset_minutes INTEGER NOT NULL DEFAULT 0,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO schedule_items (
                        name, dose, instructions, anchor, offset_minutes,
                        sort_order, active, created_at, updated_at
                    ) VALUES
                        ('测试甲', '1片', '', 'breakfast', 0, 10, 1, 'x', 'x'),
                        ('测试甲', '1片', '', 'dinner', 0, 20, 1, 'x', 'x'),
                        ('测试乙', '2片', '', 'wake', 0, 30, 1, 'x', 'x');
                    PRAGMA user_version = 2;
                    """
                )

            store = MedicationStore(db_path)
            plan = store.get_medication_plan()
            with closing(sqlite3.connect(db_path)) as db, db:
                schema_version = db.execute("PRAGMA user_version").fetchone()[0]
                alpha_ids = {
                    row[0]
                    for row in db.execute(
                        "SELECT medication_id FROM schedule_items WHERE name = '测试甲'"
                    )
                }

        self.assertEqual(schema_version, 5)
        self.assertEqual(len(alpha_ids), 1)
        self.assertNotIn(None, alpha_ids)
        self.assertEqual(
            plan["summary"],
            {"medicationCount": 2, "dailyAdministrationCount": 3},
        )

    def test_v2_duplicate_slots_remain_editable_but_cannot_be_extended(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "v2-duplicates.db"
            with closing(sqlite3.connect(db_path)) as db, db:
                db.executescript(
                    """
                    CREATE TABLE schedule_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        dose TEXT NOT NULL,
                        instructions TEXT NOT NULL DEFAULT '',
                        anchor TEXT NOT NULL,
                        offset_minutes INTEGER NOT NULL DEFAULT 0,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO schedule_items (
                        name, dose, instructions, anchor, offset_minutes,
                        sort_order, active, created_at, updated_at
                    ) VALUES
                        ('旧版重复药', '1片', '第一项', 'breakfast', 0, 10, 1, 'x', 'x'),
                        ('旧版重复药', '2片', '第二项', 'breakfast', 0, 20, 1, 'x', 'x');
                    PRAGMA user_version = 2;
                    """
                )

            store = MedicationStore(db_path)
            medication = store.get_medication_plan()["medications"][0]
            schedules = [
                {
                    key: schedule[key]
                    for key in (
                        "id",
                        "dose",
                        "instructions",
                        "anchor",
                        "offsetMinutes",
                    )
                }
                for schedule in medication["schedules"]
            ]
            schedules[0]["instructions"] = "已核对"
            updated = store.update_medication(
                medication["id"],
                {
                    "name": medication["name"],
                    "revision": medication["revision"],
                    "schedules": schedules,
                },
            )

            self.assertEqual(len(updated["medication"]["schedules"]), 2)
            before_invalid = store.get_medication_plan()
            with self.assertRaisesRegex(ValueError, "重复的提醒时段"):
                store.update_medication(
                    medication["id"],
                    {
                        "name": medication["name"],
                        "revision": updated["medication"]["revision"],
                        "schedules": [
                            *schedules,
                            {
                                "dose": "1片",
                                "instructions": "新增项",
                                "anchor": "breakfast",
                                "offsetMinutes": 0,
                            },
                        ],
                    },
                )
            self.assertEqual(store.get_medication_plan(), before_invalid)

    def test_medication_api_creates_atomically_and_rejects_stale_revision(self):
        payload = {
            "name": "聚合接口测试药物",
            "schedules": [
                {
                    "dose": "1片",
                    "instructions": "早餐后",
                    "anchor": "breakfast",
                    "offsetMinutes": 10,
                },
                {
                    "dose": "1片",
                    "instructions": "晚餐后",
                    "anchor": "dinner",
                    "offsetMinutes": 10,
                },
            ],
        }
        status, created = self.request(
            "/api/medications", method="POST", payload=payload
        )
        medication = created["medication"]
        cleanup_revision = medication["revision"]
        deleted = False
        try:
            self.assertEqual(status, 201)
            self.assertEqual(medication["revision"], 1)
            self.assertEqual(len(medication["schedules"]), 2)
            self.assertEqual(len(created["changes"]["createdScheduleIds"]), 2)
            self.assertEqual(created["summary"]["medicationCount"], 7)
            self.assertEqual(created["summary"]["dailyAdministrationCount"], 15)

            with self.assertRaises(HTTPError) as duplicate_error:
                self.request("/api/medications", method="POST", payload=payload)
            self.assertEqual(duplicate_error.exception.code, 409)
            duplicate_error.exception.close()

            update_payload = {
                "name": medication["name"],
                "revision": medication["revision"],
                "schedules": [
                    {
                        **schedule,
                        "instructions": f"{schedule['instructions']}，更新",
                    }
                    for schedule in medication["schedules"]
                ],
            }
            with self.assertRaises(HTTPError) as missing_update_revision_error:
                self.request(
                    f"/api/medications/{medication['id']}",
                    method="PUT",
                    payload=update_payload,
                )
            self.assertEqual(missing_update_revision_error.exception.code, 400)
            missing_update_revision_error.exception.close()

            with self.assertRaises(HTTPError) as mismatched_revision_error:
                self.request(
                    f"/api/medications/{medication['id']}",
                    method="PUT",
                    payload=update_payload,
                    headers={"If-Match": '"2"'},
                )
            self.assertEqual(mismatched_revision_error.exception.code, 409)
            mismatched_revision_error.exception.close()

            status, updated = self.request(
                f"/api/medications/{medication['id']}",
                method="PUT",
                payload=update_payload,
                headers={"If-Match": f'W/"{medication["revision"]}"'},
            )
            cleanup_revision = updated["medication"]["revision"]
            self.assertEqual(status, 200)
            self.assertEqual(updated["medication"]["revision"], 2)

            rename_conflict_payload = {
                **update_payload,
                "name": "示例药 B",
                "revision": updated["medication"]["revision"],
            }
            with self.assertRaises(HTTPError) as rename_error:
                self.request(
                    f"/api/medications/{medication['id']}",
                    method="PUT",
                    payload=rename_conflict_payload,
                    headers={
                        "If-Match": f'"{updated["medication"]["revision"]}"'
                    },
                )
            self.assertEqual(rename_error.exception.code, 409)
            rename_error.exception.close()

            with self.assertRaises(HTTPError) as stale_error:
                self.request(
                    f"/api/medications/{medication['id']}",
                    method="PUT",
                    payload=update_payload,
                    headers={"If-Match": f'"{medication["revision"]}"'},
                )
            self.assertEqual(stale_error.exception.code, 409)
            stale_error.exception.close()

            with self.assertRaises(HTTPError) as missing_revision_error:
                self.request(
                    f"/api/medications/{medication['id']}", method="DELETE"
                )
            self.assertEqual(missing_revision_error.exception.code, 400)
            missing_revision_error.exception.close()

            with self.assertRaises(HTTPError) as stale_delete_error:
                self.request(
                    f"/api/medications/{medication['id']}",
                    method="DELETE",
                    headers={"If-Match": f'"{medication["revision"]}"'},
                )
            self.assertEqual(stale_delete_error.exception.code, 409)
            stale_delete_error.exception.close()

            status, archived = self.request(
                f"/api/medications/{medication['id']}",
                method="DELETE",
                headers={"If-Match": f'W/"{cleanup_revision}"'},
            )
            self.assertEqual(status, 200)
            self.assertTrue(archived["deleted"])
            self.assertEqual(len(archived["changes"]["archivedScheduleIds"]), 2)
            deleted = True

            archived_update_payload = {
                **update_payload,
                "revision": cleanup_revision,
            }
            with self.assertRaises(HTTPError) as archived_update_error:
                self.request(
                    f"/api/medications/{medication['id']}",
                    method="PUT",
                    payload=archived_update_payload,
                    headers={"If-Match": f'"{cleanup_revision}"'},
                )
            self.assertEqual(archived_update_error.exception.code, 409)
            archived_update_error.exception.close()

            with self.assertRaises(HTTPError) as repeated_archive_error:
                self.request(
                    f"/api/medications/{medication['id']}",
                    method="DELETE",
                    headers={"If-Match": f'"{cleanup_revision}"'},
                )
            self.assertEqual(repeated_archive_error.exception.code, 409)
            repeated_archive_error.exception.close()
        finally:
            if not deleted:
                self.request(
                    f"/api/medications/{medication['id']}",
                    method="DELETE",
                    headers={"If-Match": f'"{cleanup_revision}"'},
                )

    def test_medication_http_update_expands_one_schedule_to_three(self):
        _, before = self.request("/api/medications")
        status, created = self.request(
            "/api/medications",
            method="POST",
            payload={
                "name": "每日三次接口测试药物",
                "schedules": [
                    {
                        "dose": "1片",
                        "instructions": "整片吞服",
                        "anchor": "wake",
                        "offsetMinutes": 0,
                    }
                ],
            },
        )
        medication = created["medication"]
        cleanup_revision = medication["revision"]
        try:
            self.assertEqual(status, 201)
            self.assertEqual(len(medication["schedules"]), 1)
            self.assertEqual(len(created["changes"]["createdScheduleIds"]), 1)
            self.assertEqual(
                created["summary"],
                {
                    "medicationCount": before["summary"]["medicationCount"] + 1,
                    "dailyAdministrationCount": (
                        before["summary"]["dailyAdministrationCount"] + 1
                    ),
                },
            )
            original = medication["schedules"][0]
            update_payload = {
                "name": medication["name"],
                "revision": medication["revision"],
                "schedules": [
                    {
                        key: original[key]
                        for key in (
                            "id",
                            "dose",
                            "instructions",
                            "anchor",
                            "offsetMinutes",
                        )
                    },
                    {
                        "dose": "1片",
                        "instructions": "整片吞服",
                        "anchor": "lunch",
                        "offsetMinutes": 0,
                    },
                    {
                        "dose": "1片",
                        "instructions": "整片吞服",
                        "anchor": "dinner",
                        "offsetMinutes": 0,
                    },
                ],
            }
            status, expanded = self.request(
                f"/api/medications/{medication['id']}",
                method="PUT",
                payload=update_payload,
                headers={"If-Match": f'"{medication["revision"]}"'},
            )
            cleanup_revision = expanded["medication"]["revision"]
            self.assertEqual(status, 200)
            self.assertEqual(len(expanded["medication"]["schedules"]), 3)
            self.assertEqual(expanded["changes"]["updatedScheduleIds"], [original["id"]])
            self.assertEqual(len(expanded["changes"]["createdScheduleIds"]), 2)
            self.assertEqual(expanded["changes"]["archivedScheduleIds"], [])
            self.assertEqual(
                expanded["summary"],
                {
                    "medicationCount": before["summary"]["medicationCount"] + 1,
                    "dailyAdministrationCount": (
                        before["summary"]["dailyAdministrationCount"] + 3
                    ),
                },
            )
        finally:
            self.request(
                f"/api/medications/{medication['id']}",
                method="DELETE",
                headers={"If-Match": f'"{cleanup_revision}"'},
            )

        _, after = self.request("/api/medications")
        self.assertEqual(after, before)

    def test_medication_schedule_count_boundaries_and_invalid_posts_are_atomic(self):
        _, before = self.request("/api/medications")
        created_medications = []

        def schedules(count):
            return [
                {
                    "dose": "1片",
                    "instructions": f"第 {index + 1} 次",
                    "anchor": "wake",
                    "offsetMinutes": index,
                }
                for index in range(count)
            ]

        try:
            for count in (1, 24):
                status, created = self.request(
                    "/api/medications",
                    method="POST",
                    payload={
                        "name": f"边界测试药物{count}",
                        "schedules": schedules(count),
                    },
                )
                self.assertEqual(status, 201)
                self.assertEqual(len(created["medication"]["schedules"]), count)
                created_medications.append(created["medication"])

            for count in (0, 25):
                _, before_invalid = self.request("/api/medications")
                with self.assertRaises(HTTPError) as raised:
                    self.request(
                        "/api/medications",
                        method="POST",
                        payload={
                            "name": f"非法边界测试药物{count}",
                            "schedules": schedules(count),
                        },
                    )
                self.assertEqual(raised.exception.code, 400)
                raised.exception.close()
                _, after_invalid = self.request("/api/medications")
                self.assertEqual(after_invalid, before_invalid)
        finally:
            for medication in reversed(created_medications):
                self.request(
                    f"/api/medications/{medication['id']}",
                    method="DELETE",
                    headers={"If-Match": f'"{medication["revision"]}"'},
                )

        _, after = self.request("/api/medications")
        self.assertEqual(after, before)

    def test_medication_adjustment_settings_are_strict_and_atomic(self):
        _, before = self.request("/api/medications")
        base_payload = {
            "name": "动态调整边界测试药",
            "schedules": [
                {
                    "dose": "1片",
                    "instructions": "",
                    "anchor": "wake",
                    "offsetMinutes": 0,
                }
            ],
        }
        cases = (
            ({"timingMode": "automatic"}, "时间跟随方式无效"),
            ({"timingMode": True}, "时间跟随方式无效"),
            ({"adjustAfterIntake": "true"}, "动态调整开关无效"),
            ({"maxAutoShiftMinutes": 0}, "1 到 240 分钟"),
            ({"maxAutoShiftMinutes": 241}, "1 到 240 分钟"),
            ({"maxAutoShiftMinutes": True}, "1 到 240 分钟"),
        )
        for index, (settings, message) in enumerate(cases):
            with self.subTest(settings=settings), self.assertRaises(HTTPError) as raised:
                self.request(
                    "/api/medications",
                    method="POST",
                    payload={
                        **base_payload,
                        "name": f"{base_payload['name']}{index}",
                        **settings,
                    },
                )
            self.assertEqual(raised.exception.code, 400)
            error = json.loads(raised.exception.read().decode("utf-8"))
            self.assertIn(message, error["error"])
            raised.exception.close()
        _, after = self.request("/api/medications")
        self.assertEqual(after, before)

    def test_medication_frequency_update_archives_removed_rows_and_freezes_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "frequency.db")
            frozen_day = "2099-03-01"
            future_day = "2099-03-02"
            frozen = store.update_context(
                frozen_day,
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "21:00",
                },
            )
            plan = store.get_medication_plan()
            medication = next(
                item
                for item in plan["medications"]
                if item["name"] == "示例药 B"
            )
            original = medication["schedules"][0]
            frozen = store.mark_taken(
                {
                    "date": frozen_day,
                    "scheduleItemId": original["id"],
                    "takenAt": f"{frozen_day}T07:05:00+08:00",
                }
            )
            frozen_items = frozen["items"]

            expanded = store.update_medication(
                medication["id"],
                {
                    "name": medication["name"],
                    "revision": medication["revision"],
                    "schedules": [
                        {
                            key: original[key]
                            for key in (
                                "id",
                                "dose",
                                "instructions",
                                "anchor",
                                "offsetMinutes",
                            )
                        },
                        {
                            "dose": original["dose"],
                            "instructions": original["instructions"],
                            "anchor": "lunch",
                            "offsetMinutes": 0,
                        },
                        {
                            "dose": original["dose"],
                            "instructions": original["instructions"],
                            "anchor": "dinner",
                            "offsetMinutes": 0,
                        },
                    ],
                },
            )
            new_ids = expanded["changes"]["createdScheduleIds"]
            self.assertEqual(
                expanded["summary"],
                {"medicationCount": 6, "dailyAdministrationCount": 15},
            )
            self.assertEqual(len(new_ids), 2)
            self.assertEqual(store.get_day(frozen_day)["items"], frozen_items)
            future_medication_items = [
                item
                for item in store.get_day(future_day)["items"]
                if item["name"] == medication["name"]
            ]
            self.assertEqual(len(future_medication_items), 3)
            future_items = store.get_day(future_day)["items"]
            self.assertEqual(
                [item["scheduledAt"] for item in future_items],
                sorted(item["scheduledAt"] for item in future_items),
            )

            before_invalid = store.get_medication_plan()
            with self.assertRaisesRegex(ValueError, "重复的提醒时段"):
                store.update_medication(
                    medication["id"],
                    {
                        "name": medication["name"],
                        "revision": expanded["medication"]["revision"],
                        "schedules": [
                            {
                                "dose": "2片",
                                "instructions": "",
                                "anchor": "wake",
                                "offsetMinutes": 0,
                            },
                            {
                                "dose": "2片",
                                "instructions": "",
                                "anchor": "wake",
                                "offsetMinutes": 0,
                            },
                        ],
                    },
                )
            self.assertEqual(store.get_medication_plan(), before_invalid)

            foreign_schedule_id = next(
                item["schedules"][0]["id"]
                for item in before_invalid["medications"]
                if item["id"] != medication["id"]
            )
            with self.assertRaisesRegex(ValueError, "不属于该药物"):
                store.update_medication(
                    medication["id"],
                    {
                        "name": medication["name"],
                        "revision": expanded["medication"]["revision"],
                        "schedules": [
                            {
                                "id": foreign_schedule_id,
                                "dose": "2片",
                                "instructions": "",
                                "anchor": "wake",
                                "offsetMinutes": 0,
                            }
                        ],
                    },
                )
            self.assertEqual(store.get_medication_plan(), before_invalid)

            retained = expanded["medication"]["schedules"][0]
            contracted = store.update_medication(
                medication["id"],
                {
                    "name": medication["name"],
                    "revision": expanded["medication"]["revision"],
                    "schedules": [
                        {
                            key: retained[key]
                            for key in (
                                "id",
                                "dose",
                                "instructions",
                                "anchor",
                                "offsetMinutes",
                            )
                        }
                    ],
                },
            )
            self.assertEqual(set(contracted["changes"]["archivedScheduleIds"]), set(new_ids))
            with closing(sqlite3.connect(store.db_path)) as db, db:
                archived_states = {
                    row[0]
                    for row in db.execute(
                        "SELECT active FROM schedule_items WHERE id IN (?, ?)",
                        new_ids,
                    )
                }
                intake_count = db.execute(
                    """
                    SELECT COUNT(*) FROM intake_logs
                    WHERE date = ? AND schedule_item_id = ?
                    """,
                    (frozen_day, original["id"]),
                ).fetchone()[0]

        self.assertEqual(archived_states, {0})
        self.assertEqual(intake_count, 1)
        self.assertEqual(
            contracted["summary"],
            {"medicationCount": 6, "dailyAdministrationCount": 13},
        )

    def test_medication_plan_read_uses_one_snapshot_during_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "plan-read-race.db")
            initial = store.get_medication_plan()
            target = initial["medications"][0]
            reached_schedule_read = threading.Event()
            continue_read = threading.Event()
            result = {}
            errors = []
            paused = False
            original_public_medication = MedicationStore._public_medication.__func__

            def pause_first_schedule_read(cls, db, row):
                nonlocal paused
                if not paused:
                    paused = True
                    reached_schedule_read.set()
                    if not continue_read.wait(timeout=5):
                        raise TimeoutError("聚合读取等待并发停用超时")
                return original_public_medication(cls, db, row)

            def read_plan():
                try:
                    result["plan"] = store.get_medication_plan()
                except Exception as exc:
                    errors.append(exc)

            with patch.object(
                MedicationStore,
                "_public_medication",
                new=classmethod(pause_first_schedule_read),
            ):
                thread = threading.Thread(target=read_plan)
                thread.start()
                self.assertTrue(reached_schedule_read.wait(timeout=5))
                store.archive_medication(target["id"], target["revision"])
                continue_read.set()
                thread.join(timeout=5)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            concurrent_plan = result["plan"]
            returned_target = next(
                medication
                for medication in concurrent_plan["medications"]
                if medication["id"] == target["id"]
            )
            self.assertEqual(concurrent_plan, initial)
            self.assertGreaterEqual(len(returned_target["schedules"]), 1)
            self.assertEqual(
                store.get_medication_plan()["summary"],
                {"medicationCount": 5, "dailyAdministrationCount": 10},
            )

    def test_flat_schedule_plan_read_uses_one_snapshot_during_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "flat-plan-read-race.db")
            initial = store.get_schedule_plan()
            target = store.get_medication_plan()["medications"][0]
            reached_summary_read = threading.Event()
            continue_read = threading.Event()
            result = {}
            errors = []
            paused = False
            original_schedule_summary = MedicationStore._schedule_summary

            def pause_first_summary_read(db):
                nonlocal paused
                if not paused:
                    paused = True
                    reached_summary_read.set()
                    if not continue_read.wait(timeout=5):
                        raise TimeoutError("扁平计划读取等待并发停用超时")
                return original_schedule_summary(db)

            def read_plan():
                try:
                    result["plan"] = store.get_schedule_plan()
                except Exception as exc:
                    errors.append(exc)

            with patch.object(
                MedicationStore,
                "_schedule_summary",
                new=staticmethod(pause_first_summary_read),
            ):
                thread = threading.Thread(target=read_plan)
                thread.start()
                self.assertTrue(reached_summary_read.wait(timeout=5))
                store.archive_medication(target["id"], target["revision"])
                continue_read.set()
                thread.join(timeout=5)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result["plan"], initial)
            self.assertEqual(
                store.get_schedule_plan()["summary"],
                {"medicationCount": 5, "dailyAdministrationCount": 10},
            )

    def test_concurrent_update_and_archive_have_one_winner_and_one_conflict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "medication-write-race.db")
            medication = next(
                item
                for item in store.get_medication_plan()["medications"]
                if item["name"] == "示例药 B"
            )
            schedule = medication["schedules"][0]
            update_payload = {
                "name": medication["name"],
                "revision": medication["revision"],
                "schedules": [
                    {
                        key: schedule[key]
                        for key in (
                            "id",
                            "dose",
                            "instructions",
                            "anchor",
                            "offsetMinutes",
                        )
                    }
                ],
            }
            update_payload["schedules"][0]["instructions"] = "并发更新"
            barrier = threading.Barrier(2)
            successes = []
            errors = []
            result_lock = threading.Lock()

            def run_update():
                try:
                    barrier.wait(timeout=5)
                    response = store.update_medication(medication["id"], update_payload)
                    with result_lock:
                        successes.append(("update", response))
                except Exception as exc:
                    with result_lock:
                        errors.append(exc)

            def run_archive():
                try:
                    barrier.wait(timeout=5)
                    response = store.archive_medication(
                        medication["id"], medication["revision"]
                    )
                    with result_lock:
                        successes.append(("archive", response))
                except Exception as exc:
                    with result_lock:
                        errors.append(exc)

            threads = [
                threading.Thread(target=run_update),
                threading.Thread(target=run_archive),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ConflictError)
            with closing(sqlite3.connect(store.db_path)) as db, db:
                active, revision = db.execute(
                    "SELECT active, revision FROM medications WHERE id = ?",
                    (medication["id"],),
                ).fetchone()
                active_schedule_count = db.execute(
                    """
                    SELECT COUNT(*) FROM schedule_items
                    WHERE medication_id = ? AND active = 1
                    """,
                    (medication["id"],),
                ).fetchone()[0]

        self.assertEqual(revision, 2)
        self.assertIn((active, active_schedule_count), {(1, 1), (0, 0)})

    def test_schedule_summary_tracks_group_and_occurrence_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "schedule-summary.db")
            initial = store.get_schedule_plan()

            same_medication = store.create_schedule_item(
                {
                    "name": "示例药 C",
                    "dose": "1片",
                    "instructions": "加测安排",
                    "anchor": "bedtime",
                    "offsetMinutes": 0,
                }
            )
            after_same_name = store.get_schedule_plan()

            distinct_medication = store.create_schedule_item(
                {
                    "name": "测试药物",
                    "dose": "1片",
                    "instructions": "加测安排",
                    "anchor": "bedtime",
                    "offsetMinutes": 10,
                }
            )
            after_distinct_name = store.get_schedule_plan()

            store.archive_schedule_item(same_medication["id"])
            store.archive_schedule_item(distinct_medication["id"])
            restored = store.get_schedule_plan()

            single_schedule = next(
                item for item in restored["items"] if item["name"] == "示例药 B"
            )
            store.archive_schedule_item(single_schedule["id"])
            after_last_schedule = store.get_schedule_plan()

            for item in after_last_schedule["items"]:
                store.archive_schedule_item(item["id"])
            empty = store.get_schedule_plan()

        self.assertEqual(
            initial["summary"],
            {"medicationCount": 6, "dailyAdministrationCount": 13},
        )
        self.assertEqual(
            after_same_name["summary"],
            {"medicationCount": 6, "dailyAdministrationCount": 14},
        )
        self.assertEqual(
            after_distinct_name["summary"],
            {"medicationCount": 7, "dailyAdministrationCount": 15},
        )
        self.assertEqual(
            restored["summary"],
            {"medicationCount": 6, "dailyAdministrationCount": 13},
        )
        self.assertEqual(
            after_last_schedule["summary"],
            {"medicationCount": 5, "dailyAdministrationCount": 12},
        )
        self.assertEqual(
            empty["summary"],
            {"medicationCount": 0, "dailyAdministrationCount": 0},
        )

    def test_legacy_name_normalizes_active_plan_without_rewriting_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "legacy-name.db"
            store = MedicationStore(db_path)
            store.update_context(
                "2099-02-01",
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "21:00",
                },
            )
            with closing(sqlite3.connect(db_path)) as db, db:
                db.execute(
                    "UPDATE schedule_items SET name = '旧版示例药 D' "
                    "WHERE name = '示例药 D'"
                )
                db.execute(
                    "UPDATE daily_instances SET name = '旧版示例药 D' "
                    "WHERE name = '示例药 D'"
                )
                db.execute("PRAGMA user_version = 1")

            MedicationStore(db_path)
            with closing(sqlite3.connect(db_path)) as db, db:
                schedule_names = {
                    row[0] for row in db.execute("SELECT name FROM schedule_items")
                }
                instance_names = {
                    row[0] for row in db.execute("SELECT name FROM daily_instances")
                }
                schema_version = db.execute("PRAGMA user_version").fetchone()[0]

        self.assertNotIn("旧版示例药 D", schedule_names)
        self.assertIn("旧版示例药 D", instance_names)
        self.assertIn("示例药 D", schedule_names)
        self.assertNotIn("示例药 D", instance_names)
        self.assertEqual(schema_version, 5)

    def test_context_update_recalculates_dynamic_times(self):
        payload = {
            "wakeTime": "08:10",
            "breakfastTime": "08:40",
            "lunchTime": "12:30",
            "dinnerTime": "18:20",
            "bedtimeTime": "22:30",
        }
        status, day = self.request(
            f"/api/context/{self.tomorrow}", method="PUT", payload=payload
        )
        self.assertEqual(status, 200)
        interval_item = next(
            item
            for item in day["items"]
            if item["name"] == "示例药 C" and item["anchor"] == "breakfast"
        )
        silybin = next(
            item
            for item in day["items"]
            if item["name"] == "示例药 E" and item["anchor"] == "breakfast"
        )
        self.assertEqual(interval_item["scheduledTime"], "08:25")
        self.assertEqual(silybin["scheduledTime"], "09:00")
        self.assertTrue(day["persisted"])

    def test_get_day_is_read_only(self):
        with closing(sqlite3.connect(self.db_path)) as db, db:
            before = (
                db.execute("SELECT COUNT(*) FROM daily_context").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM daily_instances").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM intake_logs").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM wake_events").fetchone()[0],
            )

        status, day = self.request(f"/api/day?date={self.read_only_day}")
        self.assertEqual(status, 200)
        self.assertEqual(day["summary"]["total"], 13)
        self.assertTrue(day["preview"])
        self.assertFalse(day["persisted"])

        with closing(sqlite3.connect(self.db_path)) as db, db:
            after = (
                db.execute("SELECT COUNT(*) FROM daily_context").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM daily_instances").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM intake_logs").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM wake_events").fetchone()[0],
            )
        self.assertEqual(after, before)

    def test_browsing_does_not_pollute_history(self):
        browse_days = [
            (self.history_start + timedelta(days=offset)).isoformat()
            for offset in range(3)
        ]
        with closing(sqlite3.connect(self.db_path)) as db, db:
            before = tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "daily_context",
                    "daily_instances",
                    "intake_logs",
                    "wake_events",
                )
            )

        for browse_day in browse_days:
            status, day = self.request(f"/api/day?date={browse_day}")
            self.assertEqual(status, 200)
            self.assertTrue(day["preview"])

        history_end = (self.history_start + timedelta(days=6)).isoformat()
        status, history = self.request(f"/api/history?days=7&end={history_end}")
        self.assertEqual(status, 200)
        self.assertEqual(history["summary"]["trackedDays"], 0)
        self.assertEqual(history["summary"]["total"], 0)

        with closing(sqlite3.connect(self.db_path)) as db, db:
            after = tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "daily_context",
                    "daily_instances",
                    "intake_logs",
                    "wake_events",
                )
            )
        self.assertEqual(after, before)

    def test_explicit_empty_snapshot_stays_frozen(self):
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute(
                """
                INSERT INTO daily_context (
                    date, wake_time, breakfast_time, lunch_time, dinner_time,
                    bedtime_time, updated_at
                ) VALUES (?, '07:00', '07:45', '12:15', '17:30', '21:00', ?)
                """,
                (self.empty_snapshot_day, "test"),
            )

        status, day = self.request(f"/api/day?date={self.empty_snapshot_day}")
        self.assertEqual(status, 200)
        self.assertTrue(day["persisted"])
        self.assertTrue(day["contextPersisted"])
        self.assertFalse(day["preview"])
        self.assertFalse(day["untracked"])
        self.assertEqual(day["items"], [])

    def test_intake_is_persisted_and_can_be_unmarked(self):
        _, day = self.request(f"/api/day?date={self.intake_day}")
        item_id = day["items"][0]["id"]
        item_total = day["summary"]["total"]
        with closing(sqlite3.connect(self.db_path)) as db, db:
            before = tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("daily_context", "daily_instances", "intake_logs")
            )
        status, updated = self.request(
            "/api/intakes",
            method="POST",
            payload={"date": self.intake_day, "scheduleItemId": item_id},
        )
        self.assertEqual(status, 201)
        self.assertTrue(updated["items"][0]["taken"])
        self.assertEqual(updated["summary"]["completed"], 1)
        with closing(sqlite3.connect(self.db_path)) as db, db:
            after_mark = tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("daily_context", "daily_instances", "intake_logs")
            )
        self.assertEqual(
            after_mark,
            (before[0] + 1, before[1] + item_total, before[2] + 1),
        )

        status, reverted = self.request(
            f"/api/intakes/{self.intake_day}/{item_id}", method="DELETE"
        )
        self.assertEqual(status, 200)
        self.assertFalse(reverted["items"][0]["taken"])

    def test_past_untracked_day_does_not_imply_missed_doses(self):
        status, day = self.request(f"/api/day?date={self.past_day}")
        self.assertEqual(status, 200)
        self.assertTrue(day["untracked"])
        self.assertFalse(day["persisted"])
        self.assertEqual(day["items"], [])
        self.assertEqual(day["summary"]["total"], 0)

    def test_plan_changes_follow_preview_then_freeze_on_explicit_save(self):
        _, existing = self.request(f"/api/day?date={self.plan_day}")
        existing_total = existing["summary"]["total"]
        status, created = self.request(
            "/api/medications",
            method="POST",
            payload={
                "name": "测试药物",
                "schedules": [
                    {
                        "dose": "1片",
                        "instructions": "测试",
                        "anchor": "lunch",
                        "offsetMinutes": 0,
                    }
                ],
            },
        )
        self.assertEqual(status, 201)
        medication = created["medication"]

        _, preview = self.request(f"/api/day?date={self.plan_day}")
        self.assertEqual(preview["summary"]["total"], existing_total + 1)
        self.assertFalse(preview["persisted"])

        context = {
            "wakeTime": "07:00",
            "breakfastTime": "07:45",
            "lunchTime": "12:15",
            "dinnerTime": "17:30",
            "bedtimeTime": "21:00",
        }
        _, frozen = self.request(
            f"/api/context/{self.plan_day}", method="PUT", payload=context
        )
        self.assertTrue(frozen["persisted"])
        self.assertEqual(frozen["summary"]["total"], existing_total + 1)

        self.request(
            f"/api/medications/{medication['id']}",
            method="DELETE",
            headers={"If-Match": f'"{medication["revision"]}"'},
        )

        _, same_day = self.request(f"/api/day?date={self.plan_day}")
        self.assertEqual(same_day["summary"]["total"], existing_total + 1)

        _, future = self.request(f"/api/day?date={self.plan_next_day}")
        self.assertEqual(future["summary"]["total"], existing_total)

    def test_unmark_on_untracked_date_is_read_only(self):
        with closing(sqlite3.connect(self.db_path)) as db, db:
            before = tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("daily_context", "daily_instances", "intake_logs")
            )

        status, day = self.request(
            f"/api/intakes/{self.unmark_day}/1", method="DELETE"
        )
        self.assertEqual(status, 200)
        self.assertFalse(day["persisted"])
        self.assertTrue(day["preview"])

        with closing(sqlite3.connect(self.db_path)) as db, db:
            after = tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("daily_context", "daily_instances", "intake_logs")
            )
        self.assertEqual(after, before)

    def test_wake_check_in_infers_schedule_and_is_idempotent(self):
        with closing(sqlite3.connect(self.db_path)) as db, db:
            before = (
                db.execute("SELECT COUNT(*) FROM daily_context").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM daily_instances").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM intake_logs").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM wake_events").fetchone()[0],
            )

        first_stamp = f"{self.today}T08:10:42+08:00"
        with patch("server.now_iso", return_value=first_stamp):
            status, day = self.request(
                "/api/wake-events",
                method="POST",
                payload={"date": self.today},
            )

        self.assertEqual(status, 201)
        self.assertFalse(day["alreadyRecorded"])
        self.assertEqual(day["wakeEvent"]["localTime"], "08:10")
        self.assertEqual(day["contextSource"], "wake_inferred")
        self.assertEqual(
            day["context"],
            {
                "wakeTime": "08:10",
                "breakfastTime": "08:55",
                "lunchTime": "13:25",
                "dinnerTime": "18:40",
                "bedtimeTime": "22:10",
            },
        )
        self.assertEqual(day["items"][0]["scheduledTime"], "08:10")
        self.assertFalse(day["items"][0]["anchorEstimated"])
        breakfast_pre = next(
            item
            for item in day["items"]
            if item["anchor"] == "breakfast" and item["offsetMinutes"] == -15
        )
        self.assertEqual(breakfast_pre["scheduledTime"], "08:40")
        self.assertTrue(breakfast_pre["anchorEstimated"])

        with closing(sqlite3.connect(self.db_path)) as db, db:
            after_first = (
                db.execute("SELECT COUNT(*) FROM daily_context").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM daily_instances").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM intake_logs").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM wake_events").fetchone()[0],
            )
        self.assertEqual(
            after_first,
            (before[0] + 1, before[1] + 13, before[2], before[3] + 1),
        )

        with patch(
            "server.now_iso", return_value=f"{self.today}T09:30:00+08:00"
        ):
            repeat_status, repeated = self.request(
                "/api/wake-events",
                method="POST",
                payload={"date": self.today},
            )
        self.assertEqual(repeat_status, 200)
        self.assertTrue(repeated["alreadyRecorded"])
        self.assertEqual(repeated["wakeEvent"]["occurredAt"], first_stamp)
        self.assertEqual(repeated["context"]["wakeTime"], "08:10")

        with closing(sqlite3.connect(self.db_path)) as db, db:
            after_repeat = (
                db.execute("SELECT COUNT(*) FROM daily_context").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM daily_instances").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM intake_logs").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM wake_events").fetchone()[0],
            )
        self.assertEqual(after_repeat, after_first)

    def test_wake_check_in_keeps_explicit_empty_snapshot_empty(self):
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute(
                """
                INSERT INTO daily_context (
                    date, wake_time, breakfast_time, lunch_time, dinner_time,
                    bedtime_time, source, updated_at
                ) VALUES (?, '07:00', '07:45', '12:15', '17:30', '21:00',
                    'manual', 'test')
                """,
                (self.wake_empty_snapshot_day,),
            )

        wake_stamp = f"{self.wake_empty_snapshot_day}T08:10:42+08:00"
        with patch("server.now_iso", return_value=wake_stamp):
            status, day = self.request(
                "/api/wake-events",
                method="POST",
                payload={"date": self.wake_empty_snapshot_day},
            )

        self.assertEqual(status, 201)
        self.assertEqual(day["items"], [])
        self.assertTrue(day["persisted"])
        self.assertFalse(day["preview"])
        self.assertEqual(day["contextSource"], "wake_inferred")
        with closing(sqlite3.connect(self.db_path)) as db, db:
            instance_count = db.execute(
                "SELECT COUNT(*) FROM daily_instances WHERE date = ?",
                (self.wake_empty_snapshot_day,),
            ).fetchone()[0]
            wake_count = db.execute(
                "SELECT COUNT(*) FROM wake_events WHERE routine_date = ?",
                (self.wake_empty_snapshot_day,),
            ).fetchone()[0]
        self.assertEqual(instance_count, 0)
        self.assertEqual(wake_count, 1)

    def test_wake_check_in_preserves_taken_schedule_and_reschedules_pending(self):
        _, preview = self.request(f"/api/day?date={self.wake_reschedule_day}")
        taken_id = preview["items"][0]["id"]
        pending_id = preview["items"][1]["id"]
        status, _ = self.request(
            "/api/intakes",
            method="POST",
            payload={
                "date": self.wake_reschedule_day,
                "scheduleItemId": taken_id,
                "takenAt": f"{self.wake_reschedule_day}T07:05:00+08:00",
            },
        )
        self.assertEqual(status, 201)

        with closing(sqlite3.connect(self.db_path)) as db, db:
            original_taken_at = db.execute(
                """
                SELECT scheduled_at FROM daily_instances
                WHERE date = ? AND schedule_item_id = ?
                """,
                (self.wake_reschedule_day, taken_id),
            ).fetchone()[0]
            original_log_at = db.execute(
                """
                SELECT scheduled_at FROM intake_logs
                WHERE date = ? AND schedule_item_id = ?
                """,
                (self.wake_reschedule_day, taken_id),
            ).fetchone()[0]
            original_pending_at = db.execute(
                """
                SELECT scheduled_at FROM daily_instances
                WHERE date = ? AND schedule_item_id = ?
                """,
                (self.wake_reschedule_day, pending_id),
            ).fetchone()[0]

        wake_stamp = f"{self.wake_reschedule_day}T08:10:42+08:00"
        with patch("server.now_iso", return_value=wake_stamp):
            wake_status, day = self.request(
                "/api/wake-events",
                method="POST",
                payload={"date": self.wake_reschedule_day},
            )
        self.assertEqual(wake_status, 201)

        with closing(sqlite3.connect(self.db_path)) as db, db:
            adjusted_taken_at = db.execute(
                """
                SELECT scheduled_at FROM daily_instances
                WHERE date = ? AND schedule_item_id = ?
                """,
                (self.wake_reschedule_day, taken_id),
            ).fetchone()[0]
            adjusted_log_at = db.execute(
                """
                SELECT scheduled_at FROM intake_logs
                WHERE date = ? AND schedule_item_id = ?
                """,
                (self.wake_reschedule_day, taken_id),
            ).fetchone()[0]
            adjusted_pending_at = db.execute(
                """
                SELECT scheduled_at FROM daily_instances
                WHERE date = ? AND schedule_item_id = ?
                """,
                (self.wake_reschedule_day, pending_id),
            ).fetchone()[0]

        self.assertEqual(adjusted_taken_at, original_taken_at)
        self.assertEqual(adjusted_log_at, original_log_at)
        self.assertNotEqual(adjusted_pending_at, original_pending_at)
        self.assertEqual(
            adjusted_pending_at,
            f"{self.wake_reschedule_day}T08:10:00+08:00",
        )
        taken_item = next(item for item in day["items"] if item["id"] == taken_id)
        pending_item = next(
            item for item in day["items"] if item["id"] == pending_id
        )
        self.assertTrue(taken_item["taken"])
        self.assertEqual(taken_item["scheduledAt"], original_taken_at)
        self.assertFalse(pending_item["taken"])
        self.assertEqual(pending_item["scheduledAt"], adjusted_pending_at)

    def test_wake_check_in_rejects_non_today_date(self):
        with patch(
            "server.now_iso", return_value=f"{self.today}T08:10:42+08:00"
        ):
            with self.assertRaises(HTTPError) as raised:
                self.request(
                    "/api/wake-events",
                    method="POST",
                    payload={"date": self.non_today_wake_day},
                )
        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read().decode("utf-8"))
        raised.exception.close()
        self.assertEqual(error["error"], "只能为今天记录起床时间")

        with closing(sqlite3.connect(self.db_path)) as db, db:
            context_count = db.execute(
                "SELECT COUNT(*) FROM daily_context WHERE date = ?",
                (self.non_today_wake_day,),
            ).fetchone()[0]
            wake_count = db.execute(
                "SELECT COUNT(*) FROM wake_events WHERE routine_date = ?",
                (self.non_today_wake_day,),
            ).fetchone()[0]
        self.assertEqual(context_count, 0)
        self.assertEqual(wake_count, 0)

    def test_wake_inference_preserves_cross_midnight_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "cross-midnight.db")
            store.update_preferences(
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "23:30",
                }
            )
            with patch(
                "server.now_iso", return_value=f"{self.today}T10:00:00+08:00"
            ):
                day, created = store.check_in_wake({"date": self.today})

        self.assertTrue(created)
        bedtime = next(item for item in day["items"] if item["anchor"] == "bedtime")
        next_day = (date.fromisoformat(self.today) + timedelta(days=1)).isoformat()
        self.assertTrue(bedtime["scheduledAt"].startswith(f"{next_day}T02:30"))
        self.assertEqual(day["contextDayOffsets"]["bedtimeTime"], 1)
        self.assertEqual(
            [item["scheduledAt"] for item in day["items"]],
            sorted(item["scheduledAt"] for item in day["items"]),
        )

    def test_manual_context_can_span_multiple_midnights(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "multiple-midnights.db")
            day = store.update_context(
                "2099-01-01",
                {
                    "wakeTime": "23:30",
                    "breakfastTime": "00:30",
                    "lunchTime": "12:00",
                    "dinnerTime": "18:00",
                    "bedtimeTime": "01:00",
                },
            )

        self.assertEqual(
            day["contextDayOffsets"],
            {
                "wakeTime": 0,
                "breakfastTime": 1,
                "lunchTime": 1,
                "dinnerTime": 1,
                "bedtimeTime": 2,
            },
        )
        self.assertEqual(
            [item["scheduledAt"] for item in day["items"]],
            sorted(item["scheduledAt"] for item in day["items"]),
        )

    def test_cross_midnight_item_is_next_day_carryover_until_taken(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "carryover.db")
            routine_day = "2099-01-10"
            next_day = "2099-01-11"
            routine = store.update_context(
                routine_day,
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "18:00",
                    "bedtimeTime": "00:30",
                },
            )
            bedtime = next(
                item for item in routine["items"] if item["anchor"] == "bedtime"
            )

            actual_day = store.get_day(next_day)
            carryover = actual_day["carryoverItems"]
            self.assertEqual(len(carryover), 1)
            self.assertEqual(carryover[0]["id"], bedtime["id"])
            self.assertEqual(carryover[0]["routineDate"], routine_day)
            self.assertEqual(carryover[0]["scheduledAt"], bedtime["scheduledAt"])
            self.assertFalse(carryover[0]["taken"])

            store.mark_taken(
                {
                    "date": carryover[0]["routineDate"],
                    "scheduleItemId": carryover[0]["id"],
                    "takenAt": f"{next_day}T00:32:00+08:00",
                }
            )
            self.assertEqual(store.get_day(next_day)["carryoverItems"], [])

    def test_concurrent_first_intakes_create_one_consistent_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "concurrent-intakes.db")
            routine_day = "2099-02-01"
            item_ids = [item["id"] for item in store.get_day(routine_day)["items"][:4]]
            barrier = threading.Barrier(len(item_ids))
            errors = []
            error_lock = threading.Lock()

            def record(item_id):
                try:
                    barrier.wait(timeout=3)
                    store.mark_taken(
                        {
                            "date": routine_day,
                            "scheduleItemId": item_id,
                            "takenAt": f"{routine_day}T08:00:00+08:00",
                        }
                    )
                except Exception as exc:
                    with error_lock:
                        errors.append(exc)

            threads = [
                threading.Thread(target=record, args=(item_id,))
                for item_id in item_ids
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            with store.connect() as db:
                context_count = db.execute(
                    "SELECT COUNT(*) FROM daily_context WHERE date = ?",
                    (routine_day,),
                ).fetchone()[0]
                instance_count = db.execute(
                    "SELECT COUNT(*) FROM daily_instances WHERE date = ?",
                    (routine_day,),
                ).fetchone()[0]
                log_count = db.execute(
                    "SELECT COUNT(*) FROM intake_logs WHERE date = ?",
                    (routine_day,),
                ).fetchone()[0]

        self.assertEqual(context_count, 1)
        self.assertEqual(instance_count, 13)
        self.assertEqual(log_count, len(item_ids))

    def test_preferences_reject_schedule_longer_than_one_day(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "invalid-preferences.db")
            original = store.get_preferences()
            with self.assertRaisesRegex(
                ValueError, "常用作息需在起床后 24 小时内结束"
            ):
                store.update_preferences(
                    {
                        "wakeTime": "07:00",
                        "breakfastTime": "06:00",
                        "lunchTime": "12:00",
                        "dinnerTime": "18:00",
                        "bedtimeTime": "21:00",
                    }
                )
            self.assertEqual(store.get_preferences(), original)

    def test_repeating_fixed_intake_timestamp_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "idempotent-intake.db")
            date_key = "2099-01-02"
            item_id = store.get_day(date_key)["items"][0]["id"]
            stamp = "2099-01-02T07:04:05+08:00"
            payload = {
                "date": date_key,
                "scheduleItemId": item_id,
                "takenAt": stamp,
            }

            first = store.mark_taken(payload)
            second = store.mark_taken(payload)
            with store.connect() as db:
                log_count = db.execute(
                    "SELECT COUNT(*) FROM intake_logs WHERE date = ? AND schedule_item_id = ?",
                    (date_key, item_id),
                ).fetchone()[0]

        first_item = next(item for item in first["items"] if item["id"] == item_id)
        second_item = next(item for item in second["items"] if item["id"] == item_id)
        self.assertEqual(log_count, 1)
        self.assertEqual(first_item["takenAt"], stamp)
        self.assertEqual(second_item["takenAt"], stamp)

    @staticmethod
    def _create_rolling_medication(
        store, name="滚动排程测试药", *, enabled=True, maximum=60
    ):
        return store.create_medication(
            {
                "name": name,
                "timingMode": "interval" if enabled else "routine",
                "maxAutoShiftMinutes": maximum,
                "schedules": [
                    {
                        "dose": "1片",
                        "instructions": "第一次",
                        "anchor": "wake",
                        "offsetMinutes": 0,
                    },
                    {
                        "dose": "1片",
                        "instructions": "第二次",
                        "anchor": "lunch",
                        "offsetMinutes": 0,
                    },
                    {
                        "dose": "1片",
                        "instructions": "第三次",
                        "anchor": "dinner",
                        "offsetMinutes": 0,
                    },
                ],
            }
        )["medication"]

    def test_rolling_adjustment_is_opt_in_and_keeps_other_medications_fixed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "rolling-opt-in.db")
            disabled = self._create_rolling_medication(
                store, "未开启滚动排程测试药", enabled=False
            )
            adaptive = self._create_rolling_medication(store)
            day = "2099-05-01"
            frozen = store.update_context(
                day,
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "21:00",
                },
            )
            initial = {item["id"]: item for item in frozen["items"]}

            disabled_result = store.mark_taken(
                {
                    "date": day,
                    "scheduleItemId": disabled["schedules"][0]["id"],
                    "takenAt": f"{day}T07:20:00+08:00",
                }
            )
            self.assertEqual(
                disabled_result["scheduleAdjustment"]["status"], "not_interval"
            )
            disabled_second = next(
                item
                for item in disabled_result["items"]
                if item["id"] == disabled["schedules"][1]["id"]
            )
            self.assertEqual(
                disabled_second["scheduledAt"],
                initial[disabled_second["id"]]["scheduledAt"],
            )

            source_id = adaptive["schedules"][0]["id"]
            result = store.mark_taken(
                {
                    "date": day,
                    "scheduleItemId": source_id,
                    "takenAt": f"{day}T07:20:00+08:00",
                }
            )
            self.assertEqual(
                result["scheduleAdjustment"],
                {
                    "status": "applied",
                    "sourceScheduleItemId": source_id,
                    "sourceTakenAt": f"{day}T07:20:00+08:00",
                    "requestedShiftMinutes": 20,
                    "shiftMinutes": 20,
                    "affectedCount": 2,
                    "maximumShiftMinutes": 60,
                    "timingMode": "interval",
                },
            )
            by_id = {item["id"]: item for item in result["items"]}
            adaptive_second = by_id[adaptive["schedules"][1]["id"]]
            adaptive_third = by_id[adaptive["schedules"][2]["id"]]
            self.assertEqual(adaptive_second["scheduledAt"], f"{day}T12:35:00+08:00")
            self.assertEqual(adaptive_third["scheduledAt"], f"{day}T17:50:00+08:00")
            self.assertEqual(adaptive_second["baseScheduledAt"], f"{day}T12:15:00+08:00")
            self.assertTrue(adaptive_second["adjusted"])
            self.assertEqual(adaptive_second["adjustmentMinutes"], 20)
            self.assertEqual(adaptive_second["adjustedByScheduleItemId"], source_id)
            self.assertEqual(
                adaptive_second["adjustedByTakenAt"], f"{day}T07:20:00+08:00"
            )

            unrelated_id = next(
                item["id"]
                for item in frozen["items"]
                if item["name"] == "示例药 D" and item["anchor"] == "dinner"
            )
            self.assertEqual(
                by_id[unrelated_id]["scheduledAt"], initial[unrelated_id]["scheduledAt"]
            )

    def test_routine_and_meal_modes_record_without_following_the_intake(self):
        for timing_mode, anchors in (
            ("routine", ("wake", "bedtime")),
            ("meal", ("breakfast", "dinner")),
        ):
            with self.subTest(timing_mode=timing_mode), tempfile.TemporaryDirectory() as temp_dir:
                store = MedicationStore(Path(temp_dir) / f"{timing_mode}.db")
                medication = store.create_medication(
                    {
                        "name": f"{timing_mode}测试药",
                        "timingMode": timing_mode,
                        "maxAutoShiftMinutes": 60,
                        "schedules": [
                            {
                                "dose": "1片",
                                "instructions": "第一次",
                                "anchor": anchors[0],
                                "offsetMinutes": 0,
                            },
                            {
                                "dose": "1片",
                                "instructions": "第二次",
                                "anchor": anchors[1],
                                "offsetMinutes": 0,
                            },
                        ],
                    }
                )["medication"]
                day = "2099-05-08"
                frozen = store.update_context(
                    day,
                    {
                        "wakeTime": "07:00",
                        "breakfastTime": "07:45",
                        "lunchTime": "12:15",
                        "dinnerTime": "17:30",
                        "bedtimeTime": "21:00",
                    },
                )
                first_id, second_id = [
                    schedule["id"] for schedule in medication["schedules"]
                ]
                initial_second = next(
                    item for item in frozen["items"] if item["id"] == second_id
                )
                result = store.mark_taken(
                    {
                        "date": day,
                        "scheduleItemId": first_id,
                        "takenAt": f"{day}T08:00:00+08:00",
                    }
                )
                current_second = next(
                    item for item in result["items"] if item["id"] == second_id
                )

                self.assertEqual(result["scheduleAdjustment"]["status"], "not_interval")
                self.assertEqual(result["scheduleAdjustment"]["timingMode"], timing_mode)
                self.assertEqual(
                    current_second["scheduledAt"], initial_second["scheduledAt"]
                )
                self.assertEqual(current_second["timingMode"], timing_mode)

    def test_rolling_adjustments_compose_without_rewriting_taken_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "rolling-compose.db")
            medication = self._create_rolling_medication(store)
            day = "2099-05-02"
            frozen = store.update_context(
                day,
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "21:00",
                },
            )
            first_id, second_id, third_id = [
                schedule["id"] for schedule in medication["schedules"]
            ]
            store.mark_taken(
                {
                    "date": day,
                    "scheduleItemId": first_id,
                    "takenAt": f"{day}T07:20:00+08:00",
                }
            )
            after_second = store.mark_taken(
                {
                    "date": day,
                    "scheduleItemId": second_id,
                    "takenAt": f"{day}T12:50:00+08:00",
                }
            )
            repeated = store.mark_taken(
                {
                    "date": day,
                    "scheduleItemId": second_id,
                    "takenAt": f"{day}T12:50:00+08:00",
                }
            )
            before_by_id = {item["id"]: item for item in frozen["items"]}
            after_by_id = {item["id"]: item for item in after_second["items"]}
            repeated_by_id = {item["id"]: item for item in repeated["items"]}

            self.assertEqual(after_second["scheduleAdjustment"]["shiftMinutes"], 15)
            self.assertEqual(after_by_id[third_id]["scheduledAt"], f"{day}T18:05:00+08:00")
            self.assertEqual(
                repeated_by_id[third_id]["scheduledAt"],
                after_by_id[third_id]["scheduledAt"],
            )
            self.assertEqual(
                after_by_id[first_id]["scheduledAt"],
                before_by_id[first_id]["scheduledAt"],
            )
            self.assertEqual(after_by_id[second_id]["scheduledAt"], f"{day}T12:35:00+08:00")
            with store.connect() as db:
                stored = db.execute(
                    """
                    SELECT schedule_item_id, scheduled_at, taken_at,
                           adjustment_minutes
                    FROM intake_logs
                    WHERE date = ? AND schedule_item_id IN (?, ?)
                    ORDER BY schedule_item_id
                    """,
                    (day, first_id, second_id),
                ).fetchall()
            self.assertEqual(len(stored), 2)
            self.assertEqual(
                {row["schedule_item_id"]: row["adjustment_minutes"] for row in stored},
                {first_id: 20, second_id: 15},
            )

    def test_rolling_adjustment_outside_limit_does_not_move_schedule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "rolling-limit.db")
            medication = self._create_rolling_medication(store, maximum=30)
            day = "2099-05-03"
            frozen = store.update_context(
                day,
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "21:00",
                },
            )
            source_id = medication["schedules"][0]["id"]
            second_id = medication["schedules"][1]["id"]
            result = store.mark_taken(
                {
                    "date": day,
                    "scheduleItemId": source_id,
                    "takenAt": f"{day}T08:01:00+08:00",
                }
            )
            initial = {item["id"]: item for item in frozen["items"]}
            current = {item["id"]: item for item in result["items"]}
            self.assertEqual(
                result["scheduleAdjustment"]["status"], "outside_window"
            )
            self.assertEqual(
                result["scheduleAdjustment"]["requestedShiftMinutes"], 61
            )
            self.assertEqual(result["scheduleAdjustment"]["shiftMinutes"], 0)
            self.assertEqual(
                current[second_id]["scheduledAt"], initial[second_id]["scheduledAt"]
            )

    def test_rolling_adjustment_handles_cross_midnight_and_undo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "rolling-midnight.db")
            medication = store.create_medication(
                {
                    "name": "跨日滚动排程测试药",
                    "timingMode": "interval",
                    "maxAutoShiftMinutes": 60,
                    "schedules": [
                        {
                            "dose": "1片",
                            "instructions": "睡前第一次",
                            "anchor": "dinner",
                            "offsetMinutes": 0,
                        },
                        {
                            "dose": "1片",
                            "instructions": "睡前第二次",
                            "anchor": "bedtime",
                            "offsetMinutes": 0,
                        },
                    ],
                }
            )["medication"]
            day = "2099-05-04"
            frozen = store.update_context(
                day,
                {
                    "wakeTime": "22:00",
                    "breakfastTime": "22:30",
                    "lunchTime": "23:00",
                    "dinnerTime": "23:30",
                    "bedtimeTime": "00:30",
                },
            )
            first_id, second_id = [
                schedule["id"] for schedule in medication["schedules"]
            ]
            result = store.mark_taken(
                {
                    "date": day,
                    "scheduleItemId": first_id,
                    "takenAt": f"{day}T23:50:00+08:00",
                }
            )
            current = {item["id"]: item for item in result["items"]}
            self.assertEqual(
                current[second_id]["scheduledAt"], "2099-05-05T00:50:00+08:00"
            )

            reverted = store.unmark_taken(day, first_id)
            reverted_items = {item["id"]: item for item in reverted["items"]}
            initial = {item["id"]: item for item in frozen["items"]}
            self.assertFalse(reverted_items[first_id]["taken"])
            self.assertEqual(
                reverted_items[second_id]["scheduledAt"],
                initial[second_id]["scheduledAt"],
            )
            self.assertFalse(reverted_items[second_id]["adjusted"])

    def test_context_change_replays_adjustments_only_for_pending_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "rolling-context.db")
            medication = self._create_rolling_medication(store)
            day = "2099-05-05"
            store.update_context(
                day,
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "21:00",
                },
            )
            first_id, second_id, third_id = [
                schedule["id"] for schedule in medication["schedules"]
            ]
            taken = store.mark_taken(
                {
                    "date": day,
                    "scheduleItemId": first_id,
                    "takenAt": f"{day}T07:20:00+08:00",
                }
            )
            taken_source = next(item for item in taken["items"] if item["id"] == first_id)
            updated = store.update_context(
                day,
                {
                    "wakeTime": "08:00",
                    "breakfastTime": "08:45",
                    "lunchTime": "13:15",
                    "dinnerTime": "18:30",
                    "bedtimeTime": "22:00",
                },
            )
            current = {item["id"]: item for item in updated["items"]}
            self.assertEqual(current[first_id]["scheduledAt"], taken_source["scheduledAt"])
            self.assertEqual(current[second_id]["baseScheduledAt"], f"{day}T13:15:00+08:00")
            self.assertEqual(current[second_id]["scheduledAt"], f"{day}T13:35:00+08:00")
            self.assertEqual(current[third_id]["scheduledAt"], f"{day}T18:50:00+08:00")

    def test_taken_at_requires_a_timezone_aware_iso_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MedicationStore(Path(temp_dir) / "rolling-timestamp.db")
            item_id = store.get_day("2099-05-06")["items"][0]["id"]
            for invalid in ("2099-05-06T07:00:00", "not-a-time"):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(
                    ValueError, "时区"
                ):
                    store.mark_taken(
                        {
                            "date": "2099-05-06",
                            "scheduleItemId": item_id,
                            "takenAt": invalid,
                        }
                    )

    def test_v3_history_migrates_to_v5_without_enabling_unknown_medications(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "v3-history.db"
            with closing(sqlite3.connect(db_path)) as db, db:
                db.executescript(
                    """
                    CREATE TABLE medications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        active INTEGER NOT NULL DEFAULT 1,
                        revision INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE schedule_items (
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
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE daily_context (
                        date TEXT PRIMARY KEY,
                        wake_time TEXT NOT NULL,
                        breakfast_time TEXT NOT NULL,
                        lunch_time TEXT NOT NULL,
                        dinner_time TEXT NOT NULL,
                        bedtime_time TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'legacy',
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE daily_instances (
                        date TEXT NOT NULL,
                        schedule_item_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        dose TEXT NOT NULL,
                        instructions TEXT NOT NULL,
                        anchor TEXT NOT NULL,
                        offset_minutes INTEGER NOT NULL,
                        scheduled_time TEXT NOT NULL,
                        scheduled_at TEXT,
                        sort_order INTEGER NOT NULL,
                        PRIMARY KEY (date, schedule_item_id)
                    );
                    CREATE TABLE intake_logs (
                        date TEXT NOT NULL,
                        schedule_item_id INTEGER NOT NULL,
                        scheduled_time TEXT NOT NULL,
                        scheduled_at TEXT,
                        taken_at TEXT NOT NULL,
                        PRIMARY KEY (date, schedule_item_id)
                    );
                    INSERT INTO medications
                        (id, name, active, revision, created_at, updated_at)
                    VALUES (1, '旧版测试药', 1, 3, 'x', 'x');
                    INSERT INTO schedule_items
                        (id, medication_id, name, dose, instructions, anchor,
                         offset_minutes, sort_order, active, created_at, updated_at)
                    VALUES (1, 1, '旧版测试药', '1片', '', 'wake', 0, 10, 1, 'x', 'x');
                    INSERT INTO daily_context
                        (date, wake_time, breakfast_time, lunch_time, dinner_time,
                         bedtime_time, source, updated_at)
                    VALUES ('2099-05-07', '07:00', '07:45', '12:15', '17:30',
                            '21:00', 'manual', 'x');
                    INSERT INTO daily_instances
                        (date, schedule_item_id, name, dose, instructions, anchor,
                         offset_minutes, scheduled_time, scheduled_at, sort_order)
                    VALUES ('2099-05-07', 1, '旧版测试药', '1片', '', 'wake', 0,
                            '07:00', '2099-05-07T07:00:00+08:00', 10);
                    INSERT INTO intake_logs
                        (date, schedule_item_id, scheduled_time, scheduled_at, taken_at)
                    VALUES ('2099-05-07', 1, '07:00',
                            '2099-05-07T07:00:00+08:00',
                            '2099-05-07T07:05:00+08:00');
                    PRAGMA user_version = 3;
                    """
                )

            store = MedicationStore(db_path)
            plan = store.get_medication_plan()
            day = store.get_day("2099-05-07")
            with store.connect() as db:
                schema_version = db.execute("PRAGMA user_version").fetchone()[0]
                migrated = db.execute(
                    """
                    SELECT medication_id, base_scheduled_at, timing_mode,
                           adjust_after_intake
                    FROM daily_instances WHERE date = '2099-05-07'
                    """
                ).fetchone()
                log = db.execute(
                    """
                    SELECT taken_at, adjustment_applied, adjustment_minutes
                    FROM intake_logs WHERE date = '2099-05-07'
                    """
                ).fetchone()

        self.assertEqual(schema_version, 5)
        self.assertFalse(plan["medications"][0]["adjustAfterIntake"])
        self.assertEqual(plan["medications"][0]["timingMode"], "routine")
        self.assertEqual(plan["medications"][0]["maxAutoShiftMinutes"], 120)
        self.assertEqual(migrated["medication_id"], 1)
        self.assertEqual(migrated["base_scheduled_at"], day["items"][0]["scheduledAt"])
        self.assertEqual(migrated["timing_mode"], "routine")
        self.assertFalse(migrated["adjust_after_intake"])
        self.assertEqual(log["taken_at"], "2099-05-07T07:05:00+08:00")
        self.assertFalse(log["adjustment_applied"])
        self.assertEqual(log["adjustment_minutes"], 0)

    def test_legacy_personal_plan_applies_confirmed_mode_to_future_snapshots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "legacy-personal-plan.db"
            with closing(sqlite3.connect(db_path)) as db, db:
                db.executescript(
                    """
                    CREATE TABLE medications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        active INTEGER NOT NULL DEFAULT 1,
                        revision INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE schedule_items (
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
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO medications
                        (id, name, active, revision, created_at, updated_at)
                    VALUES (1, '示例药 C', 1, 2, 'x', 'x');
                    INSERT INTO schedule_items
                        (id, medication_id, name, dose, instructions, anchor,
                         offset_minutes, sort_order, active, created_at, updated_at)
                    VALUES
                        (1, 1, '示例药 C', '2片', '餐前', 'breakfast', -15, 10, 1, 'x', 'x'),
                        (2, 1, '示例药 C', '2片', '餐前', 'lunch', -15, 20, 1, 'x', 'x');
                    PRAGMA user_version = 3;
                    """
                )

            store = MedicationStore(db_path)
            medication = store.get_medication_plan()["medications"][0]
            day = store.update_context(
                "2099-05-09",
                {
                    "wakeTime": "07:00",
                    "breakfastTime": "07:45",
                    "lunchTime": "12:15",
                    "dinnerTime": "17:30",
                    "bedtimeTime": "21:00",
                },
            )

        self.assertEqual(medication["timingMode"], "interval")
        self.assertTrue(medication["adjustAfterIntake"])
        self.assertTrue(all(item["timingMode"] == "interval" for item in day["items"]))

    def test_invalid_time_returns_bad_request(self):
        payload = {
            "wakeTime": "25:00",
            "breakfastTime": "08:00",
            "lunchTime": "12:00",
            "dinnerTime": "18:00",
            "bedtimeTime": "21:00",
        }
        with self.assertRaises(HTTPError) as raised:
            self.request(
                f"/api/context/{self.invalid_day}", method="PUT", payload=payload
            )
        self.assertEqual(raised.exception.code, 400)
        raised.exception.close()


if __name__ == "__main__":
    unittest.main()
