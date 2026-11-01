"""Stable, safe errors returned by X-Agent Manager interfaces."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class XAgentError(RuntimeError):
    code: str
    message: str
    action: str

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "action": self.action}


class UncertainOperationError(XAgentError):
    def __init__(self, message: str = "X did not confirm whether publication completed"):
        super().__init__(
            "UNCERTAIN",
            message,
            "Check the operation status and resolve it manually; do not retry blindly.",
        )


def classify_error(exc: Exception) -> XAgentError:
    if isinstance(exc, XAgentError):
        return exc
    message = str(exc)
    lowered = message.lower()
    if "not authenticated" in lowered:
        return XAgentError("AUTH_EXPIRED", message, "Refresh the local X cookie export.")
    if "selector" in lowered or "composer" in lowered or "not rendered" in lowered:
        return XAgentError("SELECTOR_CHANGED", message, "Inspect the sanitized diagnostics; do not retry automatically.")
    if "upload" in lowered or "image" in lowered:
        return XAgentError("UPLOAD_FAILED", message, "Check the image and sanitized upload diagnostics.")
    if "rate" in lowered or "too many" in lowered:
        return XAgentError("RATE_LIMITED", message, "Wait for X to allow another action, then start a new operation.")
    return XAgentError("OPERATION_FAILED", message or "Operation failed", "Inspect operation status and diagnostics.")
