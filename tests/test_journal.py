import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("X_AGENT_DEBUG_LOG", "/tmp/x-agent-test.log")

from x_agent.journal import OperationJournal
from x_agent.posts import (
    create_post,
    create_thread,
    get_operation_status,
    resolve_operation,
    resume_thread,
)


class JournalAndDemoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "operations.sqlite3")
        self.environment = patch.dict(
            os.environ,
            {"X_AGENT_DEMO": "1", "X_AGENT_DB_PATH": self.db},
            clear=False,
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_same_key_returns_saved_result_without_second_publish(self):
        first = create_post("demo post", idempotency_key="demo-key")
        second = create_post("demo post", idempotency_key="demo-key")
        self.assertTrue(first["success"])
        self.assertEqual(first["operation_id"], second["operation_id"])
        self.assertEqual(first["url"], second["url"])

    def test_same_key_with_different_payload_is_rejected(self):
        create_post("first", idempotency_key="conflict-key")
        with self.assertRaisesRegex(ValueError, "different payload"):
            create_post("second", idempotency_key="conflict-key")

    def test_interrupted_pending_operation_becomes_uncertain(self):
        journal = OperationJournal(Path(self.db))
        record, _ = journal.begin("post", "pending-key", "payload")
        journal.close()
        journal = OperationJournal(Path(self.db))
        self.assertEqual(journal.get(operation_id=record["id"])["status"], "UNCERTAIN")
        journal.close()

    def test_demo_thread_records_each_confirmed_step(self):
        result = create_thread(["one", "two", "three"], idempotency_key="thread-key")
        self.assertTrue(result["success"])
        status = get_operation_status(operation_id=result["operation_id"])
        self.assertEqual(status["status"], "COMPLETED")
        self.assertEqual(len(status["steps"]), 3)
        self.assertTrue(all(step["url"].startswith("https://demo.invalid/") for step in status["steps"]))

    def test_demo_lost_confirmation_is_uncertain(self):
        with patch.dict(os.environ, {"X_AGENT_DEMO_UNCERTAIN": "1"}, clear=False):
            result = create_post("uncertain", idempotency_key="uncertain-key")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "UNCERTAIN")
        self.assertEqual(result["error"]["code"], "UNCERTAIN")

    def test_demo_thread_resume_only_creates_missing_tail(self):
        with patch.dict(os.environ, {"X_AGENT_DEMO_FAIL_AFTER": "1"}, clear=False):
            partial = create_thread(["one", "two", "three"], idempotency_key="resume-key")
        self.assertEqual(partial["status"], "RESUMABLE")
        operation = get_operation_status(operation_id=partial["operation_id"])
        self.assertEqual(len(operation["steps"]), 1)
        resumed = resume_thread(partial["operation_id"], ["one", "two", "three"])
        self.assertTrue(resumed["success"])
        self.assertTrue(resumed["result"]["resumed"] if "result" in resumed else resumed["resumed"])
        operation = get_operation_status(operation_id=partial["operation_id"])
        self.assertEqual(len(operation["steps"]), 3)

    def test_uncertain_requires_a_human_resolution(self):
        with patch.dict(os.environ, {"X_AGENT_DEMO_UNCERTAIN": "1"}, clear=False):
            uncertain = create_post("uncertain", idempotency_key="resolve-key")
        with self.assertRaisesRegex(ValueError, "requires the confirmed"):
            resolve_operation(uncertain["operation_id"], True)
        resolved = resolve_operation(uncertain["operation_id"], True, "https://x.com/example/status/1")
        self.assertTrue(resolved["success"])
