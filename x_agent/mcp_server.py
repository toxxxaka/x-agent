"""Minimal dependency-free MCP stdio server for the private X agent."""
import json
import sys
from typing import Any

from .posts import create_post, create_thread, list_communities, reply_to_post, status

TOOLS = [
    {"name": "x_status", "description": "Check whether the private X browser session is authenticated. Does not publish anything.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_x_communities", "description": "List Communities available to the current X account. Read-only: does not publish or enter post text.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "create_x_post", "description": "Publish exactly this text as one X post after explicit confirmation. community omitted or null means Everyone. community='<name>' requires the exact named X Community to be selected and verified; otherwise the operation aborts and never falls back to Everyone.", "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "Final approved post text."}, "community": {"type": ["string", "null"], "description": "Optional exact Community name. null or omitted publishes to Everyone."}}, "required": ["text"], "additionalProperties": False}},
    {"name": "create_x_thread", "description": "Publish a linear X thread after explicit confirmation. community omitted or null means Everyone. community='<name>' selects and verifies that Community for the root; every next post replies to the previous post in the same context. If selection cannot be verified, it aborts without publishing the root.", "inputSchema": {"type": "object", "properties": {"posts": {"type": "array", "items": {"type": "string"}, "minItems": 1}, "community": {"type": ["string", "null"], "description": "Optional exact Community name. null or omitted publishes root to Everyone."}}, "required": ["posts"], "additionalProperties": False}},
    {"name": "reply_x_post", "description": "Publish this text as a reply to an existing X status URL. This publishes externally; call it only after explicit user confirmation. X inherits the source post context, including Community context when supported by X.", "inputSchema": {"type": "object", "properties": {"post_url": {"type": "string"}, "text": {"type": "string"}}, "required": ["post_url", "text"], "additionalProperties": False}},
]


def _result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "structuredContent": value}


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    functions = {"x_status": lambda: status(), "list_x_communities": lambda: list_communities(), "create_x_post": lambda: create_post(args["text"], community=args.get("community")), "create_x_thread": lambda: create_thread(args["posts"], community=args.get("community")), "reply_x_post": lambda: reply_to_post(args["post_url"], args["text"])}
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
