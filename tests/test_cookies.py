import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("X_AGENT_DEBUG_LOG", "/tmp/x-agent-test.log")

from x_agent import cookies


class CookieLoadingTest(unittest.TestCase):
    def _cookie_file(self, directory: str, mode: int = 0o600) -> Path:
        path = Path(directory) / "cookies.json"
        path.write_text(json.dumps([{"name": "auth_token", "value": "redacted"}]))
        path.chmod(mode)
        return path

    def test_regular_private_cookie_file_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._cookie_file(directory)
            with patch.object(cookies, "COOKIES_FILE", path):
                self.assertEqual(cookies.load_cookies()[0]["name"], "auth_token")

    def test_group_readable_cookie_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._cookie_file(directory, 0o640)
            with patch.object(cookies, "COOKIES_FILE", path):
                with self.assertRaisesRegex(RuntimeError, "0600"):
                    cookies.load_cookies()

    def test_symlinked_cookie_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self._cookie_file(directory)
            link = Path(directory) / "cookie-link.json"
            link.symlink_to(target)
            with patch.object(cookies, "COOKIES_FILE", link):
                with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                    cookies.load_cookies()
