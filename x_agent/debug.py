"""Sanitized diagnostics for X publishing flows; never log browser cookies."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_PATH = os.environ.get(
    "X_AGENT_DEBUG_LOG",
    str(Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "x-agent" / "x-agent.log"),
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json

        return json.dumps({"timestamp": self.formatTime(record), "level": record.levelname, "message": record.getMessage()}, ensure_ascii=False)

logger = logging.getLogger("x_agent")
if not logger.handlers:
    Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=int(os.environ.get("X_AGENT_LOG_MAX_BYTES", "5242880")), backupCount=int(os.environ.get("X_AGENT_LOG_BACKUPS", "5")), encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
