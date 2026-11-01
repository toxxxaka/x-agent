# Operations

## Secrets and permissions

Keep `x_cookies.json` and `mcp.env` outside the repository and mode `0600`. Use a dedicated service account where practical. Cookie exports are high-value session credentials; rotate them after suspected exposure or when X authentication expires.

The systemd example intentionally binds the HTTP service to loopback. If you use nginx, terminate TLS there and restrict the upstream to `127.0.0.1:8765`. Keep an allowlist or VPN/firewall boundary in front of the proxy.

## Media staging

Snap Chromium may not read arbitrary paths. Set `X_AGENT_MEDIA_STAGE_DIR` to a private directory readable by the service, for example `/root/snap/chromium/common/x-agent-media`, with mode `0700`. The unit grants access only to that directory and staged files are mode `0600`.

## Logs

`X_AGENT_DEBUG_LOG` defaults to `/var/log/x-agent/thread-debug.log`. It records operation stages, selectors, status codes, and generated post URLs. It must not contain cookie values, bearer tokens, full upload URLs, post bodies, or media bytes. Apply normal log rotation and restrict log access.

## Upgrading

Deploy a reviewed revision from Git into the runtime directory, install dependencies from `requirements.txt`, run the local test suite first, then restart the long-running MCP unit. CLI calls load source on each execution; the HTTP service does not.
