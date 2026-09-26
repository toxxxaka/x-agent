import json
import os
import sys

os.environ.setdefault("X_AGENT_DEBUG_LOG", "/tmp/x-agent-v4-dry-run.log")
sys.path.insert(0, "/home/ai/x-agent-build")

from x_agent.browser import ensure_authenticated, x_page
from x_agent.posts_v4 import (
    _editor,
    _load_parent_post,
    _publish_button,
    close_overlays,
    open_composer,
)


result = {"home": [], "reply": {}}

for attempt in range(1, 4):
    with x_page() as page:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)
        ensure_authenticated(page)
        editor = open_composer(page)
        editor.fill("x-agent non-publishing dry run")
        button = _publish_button(page, editor, f"DRY HOME {attempt}")
        result["home"].append(
            {
                "attempt": attempt,
                "url": page.url.split("?")[0],
                "editor_interactive": True,
                "button_testid": button.get_attribute("data-testid"),
                "button_interactive": True,
                "masks": page.locator('[data-testid="mask"]').count(),
            }
        )
        editor.fill("")

parent_url = "https://x.com/pepetheshneine/status/2103304618193170434"
with x_page() as page:
    _load_parent_post(page, parent_url, "2103304618193170434", 0)
    close_overlays(page)
    editor = _editor(page)
    if editor is None:
        raise RuntimeError("reply dry run could not find inline editor")
    editor.fill("x-agent non-publishing reply dry run")
    button = _publish_button(page, editor, "DRY REPLY")
    result["reply"] = {
        "url": page.url.split("?")[0],
        "editor_interactive": True,
        "button_testid": button.get_attribute("data-testid"),
        "button_interactive": True,
        "masks": page.locator('[data-testid="mask"]').count(),
    }
    editor.fill("")

print(json.dumps(result, indent=2))
