# Changelog

## 0.3.0 — 2026-11-01

- Added an SQLite/WAL operation journal, idempotency keys, explicit `UNCERTAIN` handling and safe thread resume.
- Added an offline `X_AGENT_DEMO=1` quickstart that exercises the same operation journal without starting a browser or contacting X.
- Added `doctor`, operation status, local recent-post history, structured errors and rotating JSON diagnostics.
- Made public defaults portable and replaced author-specific deployment examples with templates.

## Unreleased

### Added

- Dedicated X Articles workflow with cover upload verification, ordered preview checks, draft creation, and explicit draft publication.
- Community picker support for virtualized lists, so a Community can be found after normal UI scrolling rather than falling back to public posting.
- `publish_x_article_draft` in CLI, stdio MCP, and HTTP MCP; it re-checks the supplied Markdown against preview before publication.
- Public-release documentation, contribution guidance, architecture and operations guides, automated linting, and expanded unit tests.

### Changed

- Article text is inserted in bounded ordered chunks and verified before preview, preventing partial Draft.js writes from being mistaken for complete content.
- HTTP MCP responses consistently carry no-store, anti-framing, no-referrer, and restrictive permissions headers.
- HTTP bind address and port are configurable; loopback remains the default.

### Security

- Cookie loading rejects symbolic links and non-regular files in addition to permissive modes.
- HTTP MCP refuses a missing or shorter-than-32-character bearer token at startup.
- Upgraded the MCP SDK from 1.26.0 to 1.30.0 to address four published HTTP transport and task-handling advisories.

## 2026-09-29 - Snap Chromium media upload staging

### Fixed

- Fixed image uploads failing when Snap Chromium could not access source files under `/tmp` or `/home/ai`.
- Media is now staged byte-for-byte in a private Chromium-accessible directory before attachment.
- Added image decode preflight before publishing.
- Publishing now waits for all media upload requests to complete before submitting the post.
- The MCP systemd service is granted access only to the dedicated staging directory.
- Staged media files are cleaned up after use.

### Verified

- 1672x941 PNG decoded successfully during preflight.
- Media upload sequence completed with HTTP `202 -> 204 -> 201`.
- Composer preview was detected before publishing.
- `CreateTweet` completed with HTTP 200.
- Published status contained `tweetPhoto` and `/photo/1`.

## 2026-09-27 - X Communities

- Added optional community support to posts and thread roots.
- Added the read-only list_x_communities() MCP and CLI operation.
- Community matching is whitespace-tolerant and case-insensitive; X member-count suffixes are ignored.
- Community selection is verified before text is entered. Missing, ambiguous, or unconfirmed selection aborts without falling back to Everyone.

## 2026-09-27 - Verified image publishing and reliable 7-post threads

### Added

- Optional image_path support in create_post() and create_thread(). For a thread, the image is attached only to its root post.
- CLI support: post --image /absolute/path/image.png and thread --image /absolute/path/image.png.
- image_path support in both MCP transports: Streamable HTTP and stdio.
- Image validation: absolute, regular, non-empty JPG, JPEG, PNG, WEBP, or GIF files only.
- Sanitized media diagnostics that record only basename, byte size, preview count, and HTTP status.

### Changed

- Image publishing is fail-closed. X must render an attachment preview and return a successful upload response before the agent clicks Post.
- The uploader targets X's dedicated data-testid="fileInput" control and aborts if it is missing or ambiguous. This replaces the earlier global-selector behaviour that could complete without associating the image with the active composer.
- Text-only publishing remains backward compatible. community=None still means Everyone; reply behaviour is unchanged.

### Verified

- Published a linear seven-post thread with an image on the root post.
- Media preview and upload were confirmed before root publication.
- All seven CreateTweet operations completed successfully, each reply linked to the preceding post.
- Existing unit tests passed (9/9), and all changed Python modules passed compilation checks.

### Files changed

- x_agent/posts.py
- x_agent/cli.py
- x_agent/mcp_http.py
- x_agent/mcp_server.py
- README.md
