# X-Agent Manager

[![CI](https://github.com/toxxxaka/x-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/toxxxaka/x-agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white&style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/github/license/toxxxaka/x-agent?style=flat)](LICENSE)

Private, self-hosted X publishing automation built around the authenticated X web UI.

x-agent lets an AI assistant or local operator publish reviewed posts, linear threads, replies, and Community posts through Playwright. It does not require X API credits and keeps the authenticated browser session on infrastructure you control.

> This is browser automation, not an official X API client. X may change its UI, authentication behaviour, or terms at any time. Use it only with an account you control and in accordance with X's rules.

## Capabilities

- Publish one final, approved X post.
- Publish a linear thread: root post followed by sequential replies.
- Reply to an ordinary or Community post.
- Select an X Community by exact name, with fail-closed verification.
- List Communities available to the current account without publishing.
- Attach one image to a post or to the root of a thread.
- Create and verify X Article drafts in the dedicated Articles editor.
- Publish a previously verified Article draft to Everyone after explicit approval.
- Use the project through CLI, stdio MCP, or bearer-protected Streamable HTTP MCP.

## Architecture

```text
Chat or local operator
        |
        +-- CLI
        +-- MCP stdio
        +-- Streamable HTTP MCP (Bearer token)
                    |
                    v
           x_agent.posts / articles
                    |
          Playwright and Chromium
                    |
      authenticated X cookie session
                    |
                   x.com
```

The chat agent drafts and obtains explicit approval. The execution layer receives only final text and performs the external action. `x_agent/posts.py` owns browser interaction, audience selection, media verification, reply chaining, and sanitized diagnostics. `x_agent/articles.py` owns the separate X Articles editor and verifies title, cover, and visible body order before publishing.

## Safety model

Publishing is an external side effect and must happen only after explicit approval of the final draft.

The implementation fails closed:

- A requested Community must be uniquely matched, selected, and confirmed. Failure never falls back to Everyone.
- A requested image must produce both an X composer preview and a successful upload response. Otherwise Post is never clicked.
- A thread stops at the first failed reply and reports already-published URLs; it never continues blindly.
- An Article with a missing cover or incomplete/reordered preview remains a draft.

## Repository layout

```text
x_agent/
  browser.py       Browser setup, cookies, authentication checks
  cookies.py       Cookie-file handling
  posts.py         Posts, replies, threads, Communities, media verification
  articles.py      X Article drafts, preview verification, and publication
  cli.py           stdin-based command-line interface
  mcp_server.py    Dependency-free stdio MCP server
  mcp_http.py      Streamable HTTP MCP server with bearer authentication
  debug.py         Sanitized file logging
systemd/           Example service units
tests/             Unit tests
*.env.example      Configuration templates; no secrets
```

Historical experiments, local backups, logs, screenshots, cookies, virtual environments, and environment files are deployment artefacts, not production source.

## Quickstart: safe local demo (no X account)

The demo uses the same journal, idempotency and thread-resume paths as live mode, but never starts Chromium or contacts X.

```bash
git clone https://github.com/toxxxaka/x-agent.git
cd x-agent
python3 -m venv .venv
.venv/bin/pip install .
export X_AGENT_DEMO=1
printf '%s' 'hello from demo' | .venv/bin/x-agent post --publish --idempotency-key demo-1
.venv/bin/x-agent operation --idempotency-key demo-1
```

Try a safe interrupted thread and resume it:

```bash
export X_AGENT_DEMO_FAIL_AFTER=1
printf '%s' '["root", "reply", "tail"]' | .venv/bin/x-agent thread --publish --idempotency-key demo-thread
unset X_AGENT_DEMO_FAIL_AFTER
printf '%s' '["root", "reply", "tail"]' | .venv/bin/x-agent resume-thread OPERATION_ID
```

## Prerequisites for a live account

- Linux with Python 3.11+.
- Playwright and Chromium or Chrome.
- An X account authenticated in a browser session you control.
- A cookie export available only on the deployment host.

Install from the project directory:

```bash
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/playwright install chromium
```

## Session cookies

Store the cookie export outside the repository, for example:

```text
~/.config/x-agent/x_cookies.json
```

Protect it:

```bash
chmod 600 ~/.config/x-agent/x_cookies.json
```

Never commit cookies, tokens, browser profiles, logs, screenshots, or .env files. Refresh the cookie export from a trusted browser session when x_status reports an expired session.

## CLI

The CLI reads text from standard input rather than process arguments.

```bash
.venv/bin/x-agent doctor
.venv/bin/x-agent status

printf '%s' 'Final approved text' |
  .venv/bin/x-agent post --publish

printf '%s' 'Final approved text' |
  .venv/bin/x-agent post --publish --image /absolute/path/to/image.png

printf '%s' '["1/2 Root", "2/2 Reply"]' |
  .venv/bin/x-agent thread --publish --image /absolute/path/to/image.png

printf '%s' 'Final approved text' |
  .venv/bin/x-agent post --publish --community 'Exact Community Name'

printf '%s' 'Final approved reply' |
  .venv/bin/x-agent reply https://x.com/account/status/123 --publish

printf '%s' '## Heading\n\nArticle body.' |
  .venv/bin/x-agent article \
  --title 'Article title' --cover /absolute/path/cover.png

printf '%s' '## Heading\n\nArticle body.' | \
  .venv/bin/x-agent article-publish \
  https://x.com/compose/articles/edit/123 --title 'Article title' --publish
```

## MCP tools

| Tool | Side effect | Description |
| --- | --- | --- |
| x_status() | No | Check authenticated X session. |
| list_x_communities() | No | List Communities available to this account. |
| create_x_post(text, community=None, image_path=None) | Yes | Publish one approved post. community=None means Everyone. |
| create_x_thread(posts, community=None, image_path=None) | Yes | Publish a linear reply thread; image applies to root only. |
| reply_x_post(post_url, text) | Yes | Reply to an existing post. |
| create_x_article(title, body_markdown, cover_image_path, publish=False) | Yes | Create a verified X Article draft or publish to Everyone. |
| publish_x_article_draft(draft_url, title, body_markdown) | Yes | Re-verify and publish an approved existing Article draft to Everyone. |

## HTTP MCP

The Streamable HTTP endpoint uses a bearer token and listens on 127.0.0.1:8765 by default.

Create /etc/x-agent/mcp.env with root-only permissions:

```bash
X_AGENT_MCP_TOKEN=replace-with-a-long-random-value
X_AGENT_X_USERNAME=your_x_handle
X_AGENT_MCP_HOST=127.0.0.1
X_AGENT_MCP_PORT=8765
```

Install systemd/x-agent-mcp.service as /etc/systemd/system/x-agent-mcp.service, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now x-agent-mcp.service
sudo systemctl status x-agent-mcp.service
```

If reverse-proxying externally, use TLS, bearer authentication, restrictive firewall or proxy policy, and keep cookies and logs inaccessible.

## Community publishing

Omitting community preserves X's default audience: Everyone.

With community="Exact Community Name", the agent opens the audience picker before entering text, finds a single exact normalized match, selects it, and verifies the result. Any ambiguity aborts before root publication. Thread replies follow the context created by the root post.

Use list_x_communities() before publishing when the display name is uncertain.

## Image publishing

Pass an absolute local path through image_path (MCP) or --image (CLI). Supported formats are JPG, JPEG, PNG, WEBP, and GIF. A thread can have an image on the root post. Before X receives it, x-agent copies the file byte-for-byte into Chromium's private staging directory, because Snap Chromium may not be allowed to read arbitrary source paths. The staging copy is removed after every attempt. For the provided systemd unit, create `/root/snap/chromium/common/x-agent-media` with mode `0700` before starting the service.

The service adds `Cache-Control: no-store` and `X-Content-Type-Options: nosniff` to MCP responses. Configure `X_AGENT_MEDIA_STAGE_DIR` when your Chromium sandbox cannot read the selected image; use a private, service-writable directory rather than a root-specific path. Before posting, the agent requires:

1. An attachment preview rendered by X in the active composer.
2. A successful media-upload response.

If either proof is missing, publication aborts without creating a post.

## Diagnostics

Runtime logs default to `~/.local/state/x-agent/x-agent.log` and rotate automatically. Override the location with `X_AGENT_DEBUG_LOG`.

```text
~/.local/state/x-agent/x-agent.log
```

Failure screenshots are stored under `~/.local/state/x-agent/artifacts/` by default. Diagnostics omit post bodies, cookie values, bearer tokens, and full upload URLs. They retain operation stage, selector decision, audience state, response status, post IDs, and post URLs.

## Testing

```bash
PYTHONPATH=. ./venv/bin/python3 -m unittest discover -s tests -v
./venv/bin/python3 -m compileall -q x_agent
```

## Deployment notes

Keep reviewed source in a Git repository and run it from a dedicated non-root service account. The provided systemd and nginx files are templates: replace their paths, user, and hostname before installation. Restart the long-running MCP service after changing its code; CLI executions load fresh code every run.

## Public-project documentation

- [Architecture](docs/architecture.md) describes execution paths and trust boundaries.
- [Operations](docs/operations.md) covers deployment, secrets, media staging, and logs.
- [Troubleshooting](docs/troubleshooting.md) lists safe responses to common failures.
- [Contributing](CONTRIBUTING.md) and [Security policy](SECURITY.md) define contribution and disclosure expectations.

## License

Licensed under the [MIT License](LICENSE).
