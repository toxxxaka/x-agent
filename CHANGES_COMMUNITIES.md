# X Communities support

## Added

- `create_post(text, community=None)` and `create_thread(posts, community=None)`.
- MCP tools `create_x_post(text, community=None)`, `create_x_thread(posts, community=None)`, and read-only `list_x_communities()`.
- CLI support: `communities`, `post --community NAME`, and `thread --community NAME`.

## Behaviour

- `community=None` (or omitted) retains the existing `Everyone` audience behaviour.
- A supplied Community is matched after whitespace normalisation and case-folding against the names in X's `Choose audience` picker. The member-count suffix shown by X is ignored.
- The agent selects the one exact matching menu item and verifies that the composer audience button now displays the requested Community before any post text is entered.
- Missing, duplicated, unopened, or unconfirmed selection raises an error. The composer is closed and no fallback to `Everyone` is possible.
- For a Community thread, the Community is selected and verified only for the root post. Each later post is a normal reply to the prior post; X keeps the conversation context.
- Replies are unchanged. `reply_x_post` opens the original post and relies on X to inherit its context, including Community context when X supports it.

## Diagnostics

The log records only selection state, availability count, exact-match count, and selected Community name. It never records post text, cookies, bearer tokens, or OAuth tokens as part of Community diagnostics.

## Backups

Pre-change copies are stored in:

- `/opt/x-agent/backups/20260927-communities/`
- `backups/20260927-communities/`
