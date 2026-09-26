import json
import os
import stat
from pathlib import Path

COOKIES_FILE = Path(os.environ.get("X_AGENT_COOKIES_FILE", "/opt/x-agent/x_cookies.json"))


def load_cookies() -> list[dict]:
    """Load X browser cookies without exposing their values in logs or errors."""
    try:
        mode = stat.S_IMODE(COOKIES_FILE.stat().st_mode)
    except FileNotFoundError as exc:
        raise RuntimeError("X cookie file is missing; refresh the browser session first") from exc
    if mode & 0o077:
        raise RuntimeError("X cookie file permissions must be 0600 or stricter")
    try:
        cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("X cookie file is not valid JSON") from exc
    if not isinstance(cookies, list) or not any(c.get("name") == "auth_token" for c in cookies):
        raise RuntimeError("X cookie file has no auth_token cookie")
    return cookies
