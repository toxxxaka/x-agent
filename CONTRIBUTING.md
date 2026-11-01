# Contributing

Thanks for improving X-Agent Manager. Changes affect an external publishing action, so correctness and conservative failure behaviour matter more than clever selectors.

## Ground rules

- Never commit cookies, MCP tokens, browser profiles, screenshots, logs, or real post text.
- Keep publishing fail-closed: an uncertain audience, media attachment, or created-post URL must abort rather than guess.
- Do not add browser automation that bypasses access controls or X safeguards.
- Keep the public source tree separate from a deployment's `/opt/x-agent` runtime directory.

## Local checks

```bash
python -m pip install -r requirements-dev.txt
PYTHONPATH=. python -m unittest discover -s tests -v
python -m compileall -q x_agent
ruff check .
```

## Pull requests

1. Branch from `dev` and keep commits focused.
2. Add or update unit tests for deterministic helpers and validation paths.
3. Explain UI assumptions, failure behaviour, and any new environment variable.
4. Do not use a real X account for automated CI.

If a selector must change, prefer an accessible or stable X test ID and add diagnostics that contain no post text, cookies, tokens, or query strings.
