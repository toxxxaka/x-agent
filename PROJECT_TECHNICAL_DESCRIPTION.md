# x-agent: technical description

## Purpose

`x-agent` is a private X publishing service. It uses an existing authenticated browser session rather than the paid X API. Its primary consumer is an MCP client that drafts text conversationally and calls a publishing tool only after explicit approval.

## Layout

- `/opt/x-agent/` is the deployed runtime.
- `/home/ai/x-agent-build/` is the editable project copy.
- `x_agent/browser.py` starts Playwright Chromium and creates an authenticated browser context from `/opt/x-agent/x_cookies.json`.
- `x_agent/posts.py` contains composer, audience, post, reply, thread, and status primitives.
- `x_agent/mcp_http.py` is the bearer-protected Streamable HTTP MCP server.
- `x_agent/mcp_server.py` is the dependency-light stdio MCP alternative.
- `x_agent/cli.py` exposes operator commands.
- `x_agent/debug.py` configures sanitised diagnostics in `/var/log/x-agent/thread-debug.log`.
- `tests/test_posts.py` covers deterministic helper behaviour.

## Runtime stack

```text
MCP client or CLI
        |
        v
posts.py
        |
        v
Playwright sync API -> headless Chromium -> x.com Web UI
        |
        v
authenticated cookies in x_cookies.json
```

The browser is started with the deployed Chromium executable and uses cookies such as X session credentials. Cookie files are operational secrets and must remain mode `0600`; they are not printed by the agent.

## Publishing workflow

1. `open_composer()` opens a stable X composer using Home, the `n` shortcut, a compose link, and finally `/compose/post`.
2. `ensure_authenticated()` confirms the browser session. Cookie consent and transient overlays are dismissed.
3. The agent finds an interactive editor and its associated Post button. The element must be visible and receive pointer events.
4. Only after audience handling is complete does `_submit()` fill the post text. It listens for the `CreateTweet` response before clicking Post, recursively extracts the returned tweet ID, and returns a canonical status URL.
5. A thread publishes its root first. Every remaining entry opens the prior status URL and posts an inline reply (or uses the parent post Reply button fallback). A failure stops the thread and logs already-published URLs.

## Audience and Communities

The default audience is `Everyone`, preserving all prior callers. A caller may pass `community=<exact Community name>`. The agent opens X's `Choose audience` menu, reads visible `role=menuitem` entries, matches a single Community exactly, clicks it, and verifies that the audience button displays that Community. Any failure aborts before text is inserted or `CreateTweet` can be requested. This is deliberately fail-closed to prevent accidental public posts.

`list_x_communities()` uses the same empty composer audience picker and returns available Community names without entering text or publishing. X's displayed member count is removed from the returned name.

## MCP API

### Read-only

- `x_status()` — validates the X session.
- `list_x_communities()` — lists available Community names.

### Publishing (explicit user approval required)

- `create_x_post(text, community=None)`
- `create_x_thread(posts, community=None)`
- `reply_x_post(post_url, text)`

For the first two calls, omitted or `null` Community means `Everyone`. A string requires a verified Community and never falls back publicly. `reply_x_post` does not add an audience selector; it replies in the context X presents for the target post.

## HTTP service security

`mcp_http.py` exposes `/mcp` and a non-sensitive `/healthz` endpoint. All MCP requests require `Authorization: Bearer <X_AGENT_MCP_TOKEN>` and are compared using constant-time comparison. The deployed source currently binds to `127.0.0.1:8765`; any public exposure must be intentional and additionally restricted by firewall and a strong secret.

## Diagnostics and recovery

Diagnostics contain selectors, state transitions, response status, generated post URLs, Community selection counts, and failure screenshots. They intentionally exclude post text from Community selection messages and never log cookies or bearer tokens. Failures save screenshots beneath `/var/log/x-agent/` for visual UI diagnosis.

The code accounts for X UI variation by using several composer paths, visibility/pointer-event checks, consent dismissal, parent-post polling, response-driven URL extraction, and retries around transient overlays.

## Operational commands

```bash
# status
PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli status

# list Communities (read-only)
PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli communities

# post to Everyone
printf '%s' 'approved text' | PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli post --publish

# post to a Community
printf '%s' 'approved text' | PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli post --publish --community 'Community name'
```

Text is passed through stdin rather than a process argument to avoid exposure in process listings and shell history.

## Deployment procedure

1. Back up deployed files.
2. Test the project copy with `PYTHONPATH=/home/ai/x-agent-build`.
3. Install the tested files to `/opt/x-agent`.
4. Restart the long-running MCP systemd service so it imports the new code.
5. Verify `x_status`, `list_x_communities`, and the service health endpoint.
