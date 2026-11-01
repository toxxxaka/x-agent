# Release Review — X-Agent Manager

Date: 2026-11-01
Scope: public source tree in this repository. The deployment under `/opt/x-agent` was not modified.

## Executive result

The project is suitable for a cautious public beta: its external side effects are explicit, Community and media flows fail closed, browser actions are serialized, and secrets are intentionally outside the repository. The release branch fixes one Article preview regression and hardens two local security boundaries.

No live X action was used during this review. Static checks found no committed cookie values, bearer tokens, private keys, or AWS-style access keys in the current source tree. Historical commits were searched for secret-related identifiers without printing potential values; identifiers alone were references to cookie handling, not credentials.

## 2026-11-01 release audit addendum

The full reachable Git history was searched for common private-key, GitHub token, AWS-key and X-cookie markers. `gitleaks` was not installed in the review environment, so the check used `git log --all -G` plus a current-tree pattern scan. No credential values were found. If a credential was ever committed outside these patterns, rotate it immediately and use GitHub's secret-scanning alerts; this review does not rewrite history.

Portability issues found before this release pass were corrected: the default account handle, cookie path, log path, nginx hostname, Community example and service-specific root paths were author-specific. Public defaults now use the invoking user's state/config locations; nginx and systemd are explicitly templates. The README now starts with an offline demo and no longer claims an author deployment layout is required.

The remaining intentional limitations are documented below: live X UI compatibility cannot be established without a user-controlled account, and an `UNCERTAIN` outcome deliberately requires a human decision rather than automatic retry.

## Findings fixed in this branch

| Priority | Finding | Resolution |
| --- | --- | --- |
| High | Article preview logged an undefined variable after a successful preview check. | Replaced it with the supplied block count and covered Article helpers with unit tests. |
| Medium | Cookie loading followed symlinks and accepted any file type with restrictive permissions. | Requires a regular, non-symlinked file and mode `0600` or stricter. |
| Medium | HTTP MCP security headers were incomplete and endpoint address was hard-coded. | Applies consistent response headers and validates configurable host/port/token startup settings. |
| High | MCP SDK 1.26.0 matched four open Dependabot advisories. | Pinned the dependency to MCP 1.30.0, the first version fixing the full set. |

## Implemented release improvements

### Top 10 reliability and optimization improvements

1. Per-host browser lock prevents two operations sharing one composer context.
2. Reply chains use the URL returned by the preceding confirmed post, not guessed thread state.
3. Community picker scans X's virtualized list with normal UI scrolling.
4. Community selection is exact, visible, and confirmed before post text is entered.
5. Image uploads are staged in a Chromium-readable private directory for Snap compatibility.
6. Image publishing requires decode proof, composer preview, settled upload response, and `CreateTweet` success.
7. Article body insertion uses bounded ordered chunks and verifies the full resulting content.
8. Article preview checks title, cover, and body order before a draft can be published.
9. Sanitized diagnostics record execution evidence while removing credentials, text bodies, and upload queries.
10. CI now checks two Python versions, unit tests, compileability, lint, and dependency consistency.

### Five functional improvements

1. X Article creation with cover verification and draft-first publication.
2. Explicit publication of an existing verified Article draft through CLI, stdio MCP, and HTTP MCP.
3. Community discovery through the read-only `list_x_communities` tool.
4. Root-image support for posts and linear threads with fail-closed verification.
5. Configurable HTTP MCP host and port while preserving loopback-only defaults.

### Three differentiated design decisions

1. **Evidence-chain publishing:** UI clicks alone never define success; each publishing path requires independent X evidence.
2. **Audience fail-closed:** uncertainty about a Community is safer than silently posting to Everyone.
3. **Draft-first Articles:** a separate draft verification stage prevents an incomplete editor write becoming public content.

### Three automation improvements

1. Matrix CI for Python 3.11 and 3.12.
2. Lint, compile, test, and dependency-graph checks on every push and pull request.
3. A systemd-ready HTTP MCP deployment with restart recovery and restricted media staging.

### Ten public-facing visual/documentation improvements

There is no web UI in scope; visual work therefore focuses on a legible public repository rather than inventing a dashboard.

1. Project title and CI/Python/license badges.
2. High-level ASCII architecture diagram.
3. Capability-to-safety table.
4. MCP tool contract table.
5. Clearly separated quick-start command blocks.
6. Repository map with component roles.
7. Explicit fail-closed behaviour list.
8. Operations document with deployment sections.
9. Troubleshooting symptom/action table.
10. Linked architecture, operations, contribution, and security documentation map.

## Residual risks and release constraints

- X can change its UI or browser controls without notice. Real-account end-to-end checks remain manual by design; CI does not publish.
- Cookie exports are powerful session credentials. The server, backups, logs, and reverse proxy must be protected accordingly.
- The process lock is local to one host. Multi-host deployment needs an external coordination design before more than one writer uses the same account.
- HTTP MCP is loopback-only by default. If exposed through a proxy, TLS, a firewall/allowlist, and a strong bearer token are mandatory.

## Verification

Executed in an isolated temporary environment:

```text
27 unit tests: passed
python -m compileall -q x_agent: passed
ruff check .: passed
python -m pip check: passed
git diff --check: passed
```
