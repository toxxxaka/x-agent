# Operations

## Secrets and permissions

Keep `x_cookies.json` and `mcp.env` outside the repository and mode `0600`. Use a dedicated service account where practical. Cookie exports are high-value session credentials; rotate them after suspected exposure or when X authentication expires.

The systemd example intentionally binds the HTTP service to loopback. If you use nginx, terminate TLS there and restrict the upstream to `127.0.0.1:8765`. Keep an allowlist or VPN/firewall boundary in front of the proxy.

## Demo before connecting an account

Set `X_AGENT_DEMO=1` and use the normal CLI/MCP entry points. The demo never starts Chromium or contacts X, but writes the same SQLite/WAL operation journal. This is the supported first-run verification for contributors and new operators.

## Media staging

Snap Chromium may not read arbitrary paths. Set `X_AGENT_MEDIA_STAGE_DIR` to a private directory readable by the service, for example `/var/lib/x-agent/media`, with mode `0700`. Staged files are mode `0600` and removed after each attempt.

## Logs

`X_AGENT_DEBUG_LOG` defaults to `~/.local/state/x-agent/x-agent.log`. It records JSON lines with operation stages, selectors, status codes, and generated post URLs. It must not contain cookie values, bearer tokens, full upload URLs, post bodies, or media bytes. Rotation is built in; use `X_AGENT_LOG_MAX_BYTES` and `X_AGENT_LOG_BACKUPS` to tune it.

## Operation recovery

Every publication is recorded before browser work begins. Reusing an idempotency key with the same payload returns the saved result; reusing it with different content errors. A stopped thread is `RESUMABLE` only after its confirmed steps are saved. A missing X confirmation is `UNCERTAIN`: inspect X, then record a manual resolution. Never retry an uncertain operation automatically.

## Upgrading

Deploy a reviewed revision from Git into the runtime directory, install dependencies from `requirements.txt`, run the local test suite first, then restart the long-running MCP unit. CLI calls load source on each execution; the HTTP service does not.
