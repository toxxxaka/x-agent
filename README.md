# Private X agent

This project automates the authenticated X web UI with Playwright. It never sends cookie values to stdout or logs.

## Commands

Run as root or another account that can read `/opt/x-agent/x_cookies.json`:

```bash
printf '%s' 'Final approved text' | /opt/x-agent/venv/bin/python3 -m x_agent.cli post --publish
printf '%s' '["1/2 Root", "2/2 Reply"]' | /opt/x-agent/venv/bin/python3 -m x_agent.cli thread --publish
printf '%s' 'Final reply' | /opt/x-agent/venv/bin/python3 -m x_agent.cli reply https://x.com/user/status/123 --publish
/opt/x-agent/venv/bin/python3 -m x_agent.cli status
```

Text is accepted through stdin, not process arguments.

## Loopback service

Create `/etc/x-agent/service.env`, owned by root with mode `0600`:

```bash
X_AGENT_SERVICE_TOKEN=replace-with-a-long-random-secret
```

Install `systemd/x-agent.service` as `/etc/systemd/system/x-agent.service`, then enable it. Every HTTP request needs `Authorization: Bearer <token>`. The service listens only on `127.0.0.1:8765`.

## MCP

The MCP server uses stdio and has no new Python dependency:

```json
{
  "mcpServers": {
    "x-agent": {
      "command": "sudo",
      "args": ["-n", "/opt/x-agent/venv/bin/python3", "-m", "x_agent.mcp_server"]
    }
  }
}
```

It exposes `x_status`, `create_x_post`, `create_x_thread`, and `reply_x_post`. The publishing tool descriptions require an explicit user confirmation before they are called; drafting remains the chat agent's responsibility.

## Operational notes

Cookie sessions expire. Refresh `/opt/x-agent/x_cookies.json` from a trusted browser session whenever `x_status` says unauthenticated. Keep it `0600` and do not commit it.
