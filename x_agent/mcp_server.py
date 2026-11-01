"""Minimal dependency-free MCP stdio server for the private X agent."""
import json
import sys
from typing import Any

from .articles import create_article, publish_article_draft
from .posts import create_post, create_thread, list_communities, reply_to_post, status

TOOLS = [
    {"name": "x_status", "description": "Check whether the private X browser session is authenticated. Does not publish anything.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_x_communities", "description": "List Communities available to the current X account. Read-only: does not publish or enter post text.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "create_x_post", "description": "Publish exactly this text as one X post after explicit confirmation. community omitted or null means Everyone. image_path is an optional absolute local image path; upload and preview must be confirmed or publication aborts.", "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "Final approved post text."}, "community": {"type": ["string", "null"], "description": "Optional exact Community name. null or omitted publishes to Everyone."}, "image_path": {"type": ["string", "null"], "description": "Optional absolute local image path."}}, "required": ["text"], "additionalProperties": False}},
    {"name": "create_x_thread", "description": "Publish a linear X thread after explicit confirmation. community omitted or null means Everyone. image_path attaches only to the root, and upload plus preview must be confirmed before publication.", "inputSchema": {"type": "object", "properties": {"posts": {"type": "array", "items": {"type": "string"}, "minItems": 1}, "community": {"type": ["string", "null"], "description": "Optional exact Community name. null or omitted publishes root to Everyone."}, "image_path": {"type": ["string", "null"], "description": "Optional absolute local image path for the root."}}, "required": ["posts"], "additionalProperties": False}},
    {"name": "reply_x_post", "description": "Publish this text as a reply to an existing X status URL. This publishes externally; call it only after explicit user confirmation. X inherits the source post context, including Community context when supported by X.", "inputSchema": {"type": "object", "properties": {"post_url": {"type": "string"}, "text": {"type": "string"}}, "required": ["post_url", "text"], "additionalProperties": False}},
    {"name": "create_x_article", "description": "Create content in X's dedicated Articles editor, never the post/thread composer. Markdown supports headings, subheadings, lists, quotes and paragraphs. cover_image_path is required. publish=false saves and verifies a draft; publish=true publishes only after the Everyone audience is explicitly confirmed, never Subscribers Only or a Community.", "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "body_markdown": {"type": "string"}, "cover_image_path": {"type": "string", "description": "Absolute local JPG, PNG, or WEBP cover path."}, "publish": {"type": "boolean", "default": False}}, "required": ["title", "body_markdown", "cover_image_path"], "additionalProperties": False}},
    {"name": "publish_x_article_draft", "description": "Re-verify then publish an existing X Article draft to Everyone after explicit confirmation. body_markdown is required so preview order is checked. Never publishes to Communities or Subscribers Only.", "inputSchema": {"type": "object", "properties": {"draft_url": {"type": "string", "description": "Canonical X Article edit URL."}, "title": {"type": "string"}, "body_markdown": {"type": "string"}}, "required": ["draft_url", "title", "body_markdown"], "additionalProperties": False}},
]


def _result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "structuredContent": value}


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    functions = {"x_status": lambda: status(), "list_x_communities": lambda: list_communities(), "create_x_post": lambda: create_post(args["text"], community=args.get("community"), image_path=args.get("image_path")), "create_x_thread": lambda: create_thread(args["posts"], community=args.get("community"), image_path=args.get("image_path")), "reply_x_post": lambda: reply_to_post(args["post_url"], args["text"]), "create_x_article": lambda: create_article(args["title"], args["body_markdown"], args["cover_image_path"], publish=args.get("publish", False)), "publish_x_article_draft": lambda: publish_article_draft(args["draft_url"], args["title"], args["body_markdown"])}
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
