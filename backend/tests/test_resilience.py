import sqlite3
import unittest

from app.core.resilience import safe_tool_call


class ResilienceTests(unittest.TestCase):
    def test_transient_sqlite_reads_retry_with_a_small_bound(self):
        attempts = {"count": 0}

        @safe_tool_call
        def operation():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise sqlite3.OperationalError("database is locked")
            return {"status": "ok"}

        self.assertEqual(operation()["status"], "ok")
        self.assertEqual(attempts["count"], 3)

    def test_unexpected_failure_is_concise_and_does_not_leak_payload(self):
        secret = "<html>cloud protection challenge with internal details</html>"

        @safe_tool_call
        def operation():
            raise RuntimeError(secret)

        result = operation()
        self.assertEqual(result["error"]["code"], "internal_error")
        self.assertFalse(result["error"]["retryable"])
        self.assertNotIn(secret, str(result))
        self.assertTrue(result["error"]["request_id"])


if __name__ == "__main__":
    unittest.main()
