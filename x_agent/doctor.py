"""Read-only installation diagnostics with actionable remediation."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

from .journal import default_db_path


def _check(name: str, ok: bool, message: str, action: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "message": message, "action": action}


def doctor() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(_check("python", sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}", "Install Python 3.11 or newer."))
    chromium = os.environ.get("X_AGENT_CHROMIUM") or shutil.which("chromium") or shutil.which("google-chrome")
    checks.append(_check("chromium", bool(chromium), chromium or "Chromium not found", "Set X_AGENT_CHROMIUM to a Chromium or Chrome executable."))
    if os.environ.get("X_AGENT_DEMO") == "1":
        checks.append(_check("demo", True, "Demo mode is enabled; X is not contacted.", "Unset X_AGENT_DEMO after validating the demo."))
    else:
        cookie_path = Path(os.environ.get("X_AGENT_COOKIES_FILE", Path.home() / ".config/x-agent/x_cookies.json"))
        try:
            mode = stat.S_IMODE(cookie_path.lstat().st_mode)
            checks.append(_check("cookies", cookie_path.is_file() and not cookie_path.is_symlink() and not mode & 0o077, str(cookie_path), "Create a private cookie export with chmod 600."))
        except FileNotFoundError:
            checks.append(_check("cookies", False, f"Missing {cookie_path}", "Export your X session and set X_AGENT_COOKIES_FILE."))
    token = os.environ.get("X_AGENT_MCP_TOKEN", "")
    placeholder = "replace-with-a-unique-32-character-or-longer-secret"
    checks.append(_check("mcp_token", len(token) >= 32 and token != placeholder, "Token configured" if token else "Token missing", "Set a unique X_AGENT_MCP_TOKEN of at least 32 characters."))
    database = default_db_path()
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
        checks.append(_check("journal", os.access(database.parent, os.W_OK), str(database), "Set X_AGENT_DB_PATH to a writable private directory."))
    except OSError as exc:
        checks.append(_check("journal", False, str(exc), "Set X_AGENT_DB_PATH to a writable private directory."))
    log_path = Path(os.environ.get("X_AGENT_DEBUG_LOG", database.parent / "x-agent.log"))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        checks.append(_check("logs", os.access(log_path.parent, os.W_OK), str(log_path.parent), "Set X_AGENT_DEBUG_LOG to a writable private directory."))
    except OSError as exc:
        checks.append(_check("logs", False, str(exc), "Set X_AGENT_DEBUG_LOG to a writable private directory."))
    return {"ok": all(item["ok"] for item in checks), "checks": checks}
