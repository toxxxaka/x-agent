# Architecture

X-Agent Manager is a small execution layer, not a content-generation system. It accepts final approved content through CLI, stdio MCP, or HTTP MCP and drives the authenticated X web UI with a new Chromium context per action.

```text
caller -> input validation -> exclusive host lock -> Playwright context
       -> authenticated X page -> verified UI action -> sanitized result
```

`browser.py` creates the serialized browser session. `cookies.py` validates and loads the local cookie export. `posts.py` owns ordinary posts, replies, threads, Community selection, and image verification. `articles.py` owns the separate Articles editor. Both MCP transports are thin adapters over these primitives.

The lock is process-wide on one host. It prevents concurrent browser actions from selecting the wrong composer or publishing into each other's context. It is not a distributed lock; run one writer per cookie session.

## Trust boundaries

- **Caller to tool:** text, URLs, Community names, and image paths are untrusted inputs and are validated before browser interaction.
- **Local secrets:** cookie JSON and HTTP bearer token never belong in Git or logs.
- **X UI:** treated as unstable. A positive browser click is not sufficient evidence of success.
- **Network output:** returned URLs are created only from a confirmed X `CreateTweet` response.

## Evidence chain

For images, the agent verifies local readability, Chromium decoding, active-composer file assignment, X preview, and a successful upload response. For Communities, it requires a unique exact display-name match and an audience control that reflects the selected name. For Articles, the generated preview must contain the supplied title and body blocks in order.
