"""Sanitized diagnostics for X publishing flows; never log browser cookies."""
import logging
import os

LOG_PATH = os.environ.get("X_AGENT_DEBUG_LOG", "/var/log/x-agent/thread-debug.log")

logger = logging.getLogger("x_agent")
if not logger.handlers:
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
