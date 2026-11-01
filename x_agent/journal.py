"""Small SQLite operation journal; never stores post bodies or credentials."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


def default_db_path() -> Path:
    configured = os.environ.get("X_AGENT_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "x-agent" / "operations.sqlite3"


class OperationJournal:
    def __init__(self, path: Path | None = None):
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                operation_type TEXT NOT NULL, payload_hash TEXT NOT NULL,
                status TEXT NOT NULL, result_json TEXT, error_json TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS steps (
                operation_id TEXT NOT NULL, step_index INTEGER NOT NULL,
                kind TEXT NOT NULL, status TEXT NOT NULL, url TEXT,
                error_json TEXT, updated_at REAL NOT NULL,
                PRIMARY KEY (operation_id, step_index)
            )"""
        )
        self.reconcile_interrupted()

    def close(self) -> None:
        self.connection.close()

    def reconcile_interrupted(self) -> None:
        now = time.time()
        self.connection.execute(
            "UPDATE operations SET status='UNCERTAIN', updated_at=? "
            "WHERE status='PENDING'", (now,)
        )

    def begin(self, operation_type: str, key: str, payload_hash: str) -> tuple[dict[str, Any], bool]:
        row = self.connection.execute(
            "SELECT * FROM operations WHERE idempotency_key=?", (key,)
        ).fetchone()
        if row:
            operation = self._row(row)
            if operation["payload_hash"] != payload_hash:
                raise ValueError("idempotency key was already used with a different payload")
            return operation, False
        now = time.time()
        operation_id = str(uuid.uuid4())
        self.connection.execute(
            "INSERT INTO operations(id,idempotency_key,operation_type,payload_hash,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (operation_id, key, operation_type, payload_hash, "PENDING", now, now),
        )
        return self.get(operation_id), True

    def get(self, operation_id: str | None = None, key: str | None = None) -> dict[str, Any]:
        if not operation_id and not key:
            raise ValueError("operation_id or idempotency_key is required")
        row = self.connection.execute(
            "SELECT * FROM operations WHERE id=?" if operation_id else "SELECT * FROM operations WHERE idempotency_key=?",
            (operation_id or key,),
        ).fetchone()
        if not row:
            raise ValueError("operation was not found")
        result = self._row(row)
        result["steps"] = [dict(item) for item in self.connection.execute(
            "SELECT step_index,kind,status,url,error_json,updated_at FROM steps WHERE operation_id=? ORDER BY step_index",
            (result["id"],),
        )]
        for step in result["steps"]:
            step["error"] = json.loads(step.pop("error_json")) if step["error_json"] else None
        return result

    def step(self, operation_id: str, index: int, kind: str, status: str, url: str | None = None, error: dict[str, str] | None = None) -> None:
        self.connection.execute(
            "INSERT INTO steps(operation_id,step_index,kind,status,url,error_json,updated_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(operation_id,step_index) DO UPDATE SET status=excluded.status,url=excluded.url,error_json=excluded.error_json,updated_at=excluded.updated_at",
            (operation_id, index, kind, status, url, json.dumps(error) if error else None, time.time()),
        )

    def finish(self, operation_id: str, status: str, result: dict[str, Any] | None = None, error: dict[str, str] | None = None) -> dict[str, Any]:
        self.connection.execute(
            "UPDATE operations SET status=?, result_json=?, error_json=?, updated_at=? WHERE id=?",
            (status, json.dumps(result) if result else None, json.dumps(error) if error else None, time.time(), operation_id),
        )
        return self.get(operation_id)

    def resume(self, operation_id: str) -> dict[str, Any]:
        """Mark a human-approved resumable operation as in progress."""
        operation = self.get(operation_id)
        if operation["status"] != "RESUMABLE":
            raise ValueError("only RESUMABLE operations may be resumed; UNCERTAIN requires manual resolution")
        self.connection.execute(
            "UPDATE operations SET status='PENDING', error_json=NULL, updated_at=? WHERE id=?",
            (time.time(), operation_id),
        )
        return self.get(operation_id)

    def resolve(self, operation_id: str, published: bool, url: str | None = None) -> dict[str, Any]:
        """Record a human decision; it never performs a publish or retry."""
        operation = self.get(operation_id)
        if operation["status"] != "UNCERTAIN":
            raise ValueError("only UNCERTAIN operations require manual resolution")
        if published and not url:
            raise ValueError("published resolution requires the confirmed X post URL")
        if published:
            self.step(operation_id, 0, operation["operation_type"], "COMPLETED", url)
            return self.finish(operation_id, "COMPLETED", result={"url": url, "manually_resolved": True})
        return self.finish(operation_id, "RESUMABLE", result={"manually_resolved": True})

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["result"] = json.loads(result.pop("result_json")) if result["result_json"] else None
        result["error"] = json.loads(result.pop("error_json")) if result["error_json"] else None
        return result
