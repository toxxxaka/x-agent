"""Public, bearer-protected Streamable HTTP MCP endpoint."""
import os
import secrets
import time
from collections import defaultdict, deque

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .articles import create_article, publish_article_draft
from .doctor import doctor
from .posts import (
    create_post,
    create_thread,
    get_my_recent_posts,
    get_operation_status,
    list_communities,
    reply_to_post,
    resolve_operation,
    resume_thread,
    status,
)

TOKEN = os.environ.get("X_AGENT_MCP_TOKEN")
HOST = os.environ.get("X_AGENT_MCP_HOST", "127.0.0.1")


def _configured_port() -> int:
    raw = os.environ.get("X_AGENT_MCP_PORT", "8765")
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("X_AGENT_MCP_PORT must be an integer") from exc
    if not 1 <= port <= 65_535:
        raise RuntimeError("X_AGENT_MCP_PORT must be between 1 and 65535")
    return port


PORT = _configured_port()
MAX_REQUEST_BYTES = int(os.environ.get("X_AGENT_HTTP_MAX_BYTES", "1048576"))
RATE_LIMIT = int(os.environ.get("X_AGENT_HTTP_RATE_LIMIT", "30"))
ALLOWED_HOSTS = {item.strip() for item in os.environ.get("X_AGENT_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if item.strip()}
ALLOWED_ORIGINS = {item.strip() for item in os.environ.get("X_AGENT_ALLOWED_ORIGINS", "").split(",") if item.strip()}
_REQUESTS: dict[str, deque[float]] = defaultdict(deque)

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").split(":", 1)[0]
        if host and host not in ALLOWED_HOSTS:
            return JSONResponse({"error": "invalid_host"}, status_code=400, headers=SECURITY_HEADERS)
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"error": "invalid_origin"}, status_code=403, headers=SECURITY_HEADERS)
        if int(request.headers.get("content-length", "0") or 0) > MAX_REQUEST_BYTES:
            return JSONResponse({"error": "request_too_large"}, status_code=413, headers=SECURITY_HEADERS)
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        requests = _REQUESTS[client]
        while requests and now - requests[0] > 60:
            requests.popleft()
        if len(requests) >= RATE_LIMIT:
            return JSONResponse({"error": "rate_limited"}, status_code=429, headers=SECURITY_HEADERS)
        requests.append(now)
        if request.url.path == "/healthz":
            return JSONResponse({"ok": True}, headers=SECURITY_HEADERS)
        expected = f"Bearer {TOKEN}"
        supplied = request.headers.get("authorization", "")
        if not TOKEN or not secrets.compare_digest(supplied, expected):
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={**SECURITY_HEADERS, "WWW-Authenticate": "Bearer"},
            )
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response


mcp = FastMCP(
    "x-agent",
    instructions=(
        "Private X publishing tools. Draft in chat first. Publishing tools have "
        "an external side effect and may only be called after explicit user approval."
    ),
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
)


@mcp.tool()
def x_status() -> dict:
    """Check X authentication. Does not publish anything."""
    return status()


@mcp.tool()
def x_doctor() -> dict:
    """Read-only local configuration diagnostics. Does not contact X."""
    return doctor()


@mcp.tool()
def get_x_operation_status(operation_id: str | None = None, idempotency_key: str | None = None) -> dict:
    """Read-only status for a publication operation. UNCERTAIN requires manual resolution and is never retried automatically."""
    return get_operation_status(operation_id, idempotency_key)


@mcp.tool()
def get_my_recent_x_posts(limit: int = 10) -> dict:
    """Read locally confirmed publication URLs. Never contacts X or publishes."""
    return get_my_recent_posts(limit)


@mcp.tool()
def resolve_x_operation(operation_id: str, published: bool, url: str | None = None) -> dict:
    """Record a human decision for an UNCERTAIN operation; never retries or publishes."""
    return resolve_operation(operation_id, published, url)


@mcp.tool()
def resume_x_thread(operation_id: str, posts: list[str], community: str | None = None, image_path: str | None = None) -> dict:
    """Continue only the unconfirmed tail of a manually approved RESUMABLE thread."""
    return resume_thread(operation_id, posts, community, image_path)


@mcp.tool()
def create_x_post(
    text: str, community: str | None = None, image_path: str | None = None, idempotency_key: str | None = None
) -> dict:
    """Publish final approved text. community=None publishes to Everyone; community='<name>' requires exact Community selection. image_path is an optional absolute local image path; X upload and preview must be verified or the post aborts."""
    return create_post(text, community=community, image_path=image_path, idempotency_key=idempotency_key)


@mcp.tool()
def create_x_thread(
    posts: list[str], community: str | None = None, image_path: str | None = None, idempotency_key: str | None = None
) -> dict:
    """Publish a sequential reply thread. community=None publishes root to Everyone; community='<name>' publishes root to that verified Community. image_path attaches only to the root and must be verified before publication."""
    return create_thread(posts, community=community, image_path=image_path, idempotency_key=idempotency_key)


@mcp.tool()
def list_x_communities() -> dict:
    """List Communities available to the current X account. Read-only: does not enter text or publish."""
    return list_communities()


@mcp.tool()
def reply_x_post(post_url: str, text: str, idempotency_key: str | None = None) -> dict:
    """Publish final approved text as a reply. Requires explicit user confirmation."""
    return reply_to_post(post_url, text, idempotency_key=idempotency_key)


@mcp.tool()
def create_x_article(
    title: str,
    body_markdown: str,
    cover_image_path: str,
    publish: bool = False,
) -> dict:
    """Create an X Article in the dedicated Articles editor. Markdown supports headings, subheadings, lists, quotes and paragraphs. A cover image is required. publish=False saves and verifies a draft; publish=True publishes only after the Everyone audience is explicitly confirmed. Never publishes to Communities or Subscribers Only."""
    return create_article(
        title,
        body_markdown,
        cover_image_path,
        publish=publish,
    )


@mcp.tool()
def publish_x_article_draft(draft_url: str, title: str, body_markdown: str) -> dict:
    """Re-verify then publish an existing X Article draft to Everyone. This is external publication and requires explicit user confirmation. It never publishes to Communities or Subscribers Only."""
    return publish_article_draft(draft_url, title, body_markdown)


def main() -> None:
    if not TOKEN:
        raise SystemExit("X_AGENT_MCP_TOKEN is required")
    if len(TOKEN) < 32:
        raise SystemExit("X_AGENT_MCP_TOKEN must contain at least 32 characters")
    app = mcp.streamable_http_app()
    app.add_middleware(BearerTokenMiddleware)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
