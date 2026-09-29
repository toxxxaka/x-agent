# X-agent

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
               x_agent.posts
                    |
          Playwright and Chromium
                    |
      authenticated X cookie session
                    |
                   x.com
```

The chat agent drafts and obtains explicit approval. The execution layer receives only final text and performs the external action. x_agent/posts.py owns browser interaction, audience selection, media verification, reply chaining, and sanitized diagnostics.

## Safety model

Publishing is an external side effect and must happen only after explicit approval of the final draft.

The implementation fails closed:

- A requested Community must be uniquely matched, selected, and confirmed. Failure never falls back to Everyone.
- A requested image must produce both an X composer preview and a successful upload response. Otherwise Post is never clicked.
- A thread stops at the first failed reply and reports already-published URLs; it never continues blindly.

## Repository layout

```text
x_agent/
  browser.py       Browser setup, cookies, authentication checks
  cookies.py       Cookie-file handling
  posts.py         Posts, replies, threads, Communities, media verification
  cli.py           stdin-based command-line interface
  mcp_server.py    Dependency-free stdio MCP server
  mcp_http.py      Streamable HTTP MCP server with bearer authentication
  debug.py         Sanitized file logging
systemd/           Example service units
tests/             Unit tests
*.env.example      Configuration templates; no secrets
```

Historical experiments, local backups, logs, screenshots, cookies, virtual environments, and environment files are deployment artefacts, not production source.

## Prerequisites

- Linux with Python 3.11+.
- Playwright and Chromium or Chrome.
- An X account authenticated in a browser session you control.
- A cookie export available only on the deployment host.

Example setup:

```bash
python3 -m venv venv
./venv/bin/pip install playwright mcp uvicorn starlette
./venv/bin/playwright install chromium
```

## Session cookies

Store the cookie export outside the repository, for example:

```text
/opt/x-agent/x_cookies.json
```

Protect it:

```bash
sudo chown root:root /opt/x-agent/x_cookies.json
sudo chmod 600 /opt/x-agent/x_cookies.json
```

Never commit cookies, tokens, browser profiles, logs, screenshots, or .env files. Refresh the cookie export from a trusted browser session when x_status reports an expired session.

## CLI

The CLI reads text from standard input rather than process arguments.

```bash
PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli status

printf '%s' 'Final approved text' |
  PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli post --publish

printf '%s' 'Final approved text' |
  PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli post --publish --image /absolute/path/to/image.png

printf '%s' '["1/2 Root", "2/2 Reply"]' |
  PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli thread --publish --image /absolute/path/to/image.png

printf '%s' 'Final approved text' |
  PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli post --publish --community 'Hacking / Ethical Hacking'

printf '%s' 'Final approved reply' |
  PYTHONPATH=/opt/x-agent /opt/x-agent/venv/bin/python3 -m x_agent.cli reply https://x.com/account/status/123 --publish
```

## MCP tools

| Tool | Side effect | Description |
| --- | --- | --- |
| x_status() | No | Check authenticated X session. |
| list_x_communities() | No | List Communities available to this account. |
| create_x_post(text, community=None, image_path=None) | Yes | Publish one approved post. community=None means Everyone. |
| create_x_thread(posts, community=None, image_path=None) | Yes | Publish a linear reply thread; image applies to root only. |
| reply_x_post(post_url, text) | Yes | Reply to an existing post. |

## HTTP MCP

The Streamable HTTP endpoint uses a bearer token and listens on 127.0.0.1:8765 by default.

Create /etc/x-agent/mcp.env with root-only permissions:

```bash
X_AGENT_MCP_TOKEN=replace-with-a-long-random-value
X_AGENT_X_USERNAME=your_x_handle
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

Before posting, the agent requires:

1. An attachment preview rendered by X in the active composer.
2. A successful media-upload response.

If either proof is missing, publication aborts without creating a post.

## Diagnostics

Runtime log:

```text
/var/log/x-agent/thread-debug.log
```

Failure screenshots are stored under /var/log/x-agent/. Diagnostics omit post bodies, cookie values, bearer tokens, and full upload URLs. They retain operation stage, selector decision, audience state, response status, post IDs, and post URLs.

## Testing

```bash
PYTHONPATH=. ./venv/bin/python3 tests/test_posts.py
./venv/bin/python3 -m py_compile x_agent/*.py
```

## Deployment notes

Keep reviewed source in a Git repository, for example /home/ai/x-agent-build, and deploy a reviewed copy to /opt/x-agent. Restart x-agent-mcp.service after changing long-running MCP code; CLI executions load fresh code every run.

## License

Licensed under the [MIT License](LICENSE).
