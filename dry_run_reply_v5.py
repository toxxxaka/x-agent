import json
import os
import sys

os.environ.setdefault("X_AGENT_DEBUG_LOG", "/tmp/x-agent-reply-v5-dry-run.log")
sys.path.insert(0, "/home/ai/x-agent-build")

from x_agent.browser import x_page
from x_agent.posts_v5 import (
    _load_parent_post,
    _publish_button,
    _wait_for_interactive_editor,
    close_overlays,
)


PARENT_URL = "https://x.com/pepetheshneine/status/2103304618193170434"
STATUS_ID = "2103304618193170434"
results = []

for run in range(1, 6):
    with x_page() as page:
        _load_parent_post(page, PARENT_URL, STATUS_ID, run)
        close_overlays(page)
        editor = _wait_for_interactive_editor(page, f"DRY REPLY {run}")
        if editor is None:
            raise RuntimeError(f"run {run}: no interactive reply editor")
        editor.fill("x-agent non-publishing reply dry run")
        button = _publish_button(page, editor, f"DRY REPLY {run}")
        results.append(
            {
                "run": run,
                "editor_box": editor.bounding_box(),
                "button": button.get_attribute("data-testid"),
                "button_disabled": button.is_disabled(),
                "masks": page.locator('[data-testid="mask"]').count(),
            }
        )
        editor.fill("")

print(json.dumps(results, ensure_ascii=False, indent=2))
