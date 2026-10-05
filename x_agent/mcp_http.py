"""Public, bearer-protected Streamable HTTP MCP endpoint."""
import os
import secrets

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .posts import create_post, create_thread, list_communities, reply_to_post, status

TOKEN = os.environ.get("X_AGENT_MCP_TOKEN")


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/healthz":
            return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        expected = f"Bearer {TOKEN}"
        supplied = request.headers.get("authorization", "")
        if not TOKEN or not secrets.compare_digest(supplied, expected):
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


mcp = FastMCP(
    "x-agent",
    instructions=(
        "Private X publishing tools. Draft in chat first. Publishing tools have "
        "an external side effect and may only be called after explicit user approval."
    ),
    host="127.0.0.1",
    port=8765,
    streamable_http_path="/mcp",
    stateless_http=True,
)


@mcp.tool()
def x_status() -> dict:
    """Check X authentication. Does not publish anything."""
    return status()


@mcp.tool()
def create_x_post(
    text: str, community: str | None = None, image_path: str | None = None
) -> dict:
    """Publish final approved text. community=None publishes to Everyone; community='<name>' requires exact Community selection. image_path is an optional absolute local image path; X upload and preview must be verified or the post aborts."""
    return create_post(text, community=community, image_path=image_path)


@mcp.tool()
def create_x_thread(
    posts: list[str], community: str | None = None, image_path: str | None = None
) -> dict:
    """Publish a sequential reply thread. community=None publishes root to Everyone; community='<name>' publishes root to that verified Community. image_path attaches only to the root and must be verified before publication."""
    return create_thread(posts, community=community, image_path=image_path)


@mcp.tool()
def list_x_communities() -> dict:
    """List Communities available to the current X account. Read-only: does not enter text or publish."""
    return list_communities()


@mcp.tool()
def reply_x_post(post_url: str, text: str) -> dict:
    """Publish final approved text as a reply. Requires explicit user confirmation."""
    return reply_to_post(post_url, text)


def main() -> None:
    if not TOKEN:
        raise SystemExit("X_AGENT_MCP_TOKEN is required")
    app = mcp.streamable_http_app()
    app.add_middleware(BearerTokenMiddleware)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")


if __name__ == "__main__":
    main()
