"""Minimal dependency-free MCP stdio server for the private X agent."""
import json
import sys
from typing import Any

from .posts import create_post, create_thread, reply_to_post, status

TOOLS = [
    {"name": "x_status", "description": "Check whether the private X browser session is authenticated. Does not publish anything.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "create_x_post", "description": "Publish exactly this text as one X post. This is an external side effect: call it only after the user has explicitly confirmed publication.", "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "Final approved post text."}}, "required": ["text"], "additionalProperties": False}},
    {"name": "create_x_thread", "description": "Publish a linear X thread: the first item is the root and every next item replies to the previous one. This publishes externally; call it only after explicit user confirmation.", "inputSchema": {"type": "object", "properties": {"posts": {"type": "array", "items": {"type": "string"}, "minItems": 1}}, "required": ["posts"], "additionalProperties": False}},
    {"name": "reply_x_post", "description": "Publish this text as a reply to an existing X status URL. This publishes externally; call it only after explicit user confirmation.", "inputSchema": {"type": "object", "properties": {"post_url": {"type": "string"}, "text": {"type": "string"}}, "required": ["post_url", "text"], "additionalProperties": False}},
]


def _result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "structuredContent": value}


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    functions = {"x_status": lambda: status(), "create_x_post": lambda: create_post(args["text"]), "create_x_thread": lambda: create_thread(args["posts"]), "reply_x_post": lambda: reply_to_post(args["post_url"], args["text"])}
    if name not in functions:
        raise ValueError(f"unknown tool: {name}")
    return _result(functions[name]())


def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            method = message.get("method")
            request_id = message.get("id")
            if method == "notifications/initialized":
                continue
            if method == "initialize":
                value = {"protocolVersion": message.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}}, "serverInfo": {"name": "x-agent", "version": "1.0.0"}}
            elif method == "tools/list":
                value = {"tools": TOOLS}
            elif method == "tools/call":
                params = message.get("params", {})
                value = _call(params.get("name", ""), params.get("arguments", {}))
            else:
                raise ValueError(f"unsupported method: {method}")
            if request_id is not None:
                print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": value}, ensure_ascii=False), flush=True)
        except Exception as exc:
            if 'request_id' in locals() and request_id is not None:
                print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True}}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
