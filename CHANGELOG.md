# Changelog

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
