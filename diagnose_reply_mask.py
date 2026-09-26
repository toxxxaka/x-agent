import json
import os
import sys

os.environ.setdefault("X_AGENT_DEBUG_LOG", "/tmp/x-agent-reply-mask.log")
sys.path.insert(0, "/opt/x-agent")

from x_agent.browser import x_page
from x_agent.posts import _load_parent_post, close_overlays


PARENT_URL = "https://x.com/pepetheshneine/status/2103304618193170434"
STATUS_ID = "2103304618193170434"


def snapshot(page, elapsed_ms):
    return page.evaluate(
        """elapsed => {
            const editor = document.querySelector(
                '[data-testid="tweetTextarea_0"][contenteditable="true"]'
            );
            const rect = editor?.getBoundingClientRect();
            const hit = rect && document.elementFromPoint(
                rect.left + rect.width / 2,
                rect.top + rect.height / 2
            );
            const chain = [];
            let node = hit;
            while (node && chain.length < 6) {
                chain.push({
                    tag: node.tagName,
                    id: node.id || null,
                    role: node.getAttribute?.('role'),
                    testid: node.getAttribute?.('data-testid'),
                    aria: node.getAttribute?.('aria-label'),
                    text: (node.innerText || '').slice(0, 160),
                });
                node = node.parentElement;
            }
            return {
                elapsed_ms: elapsed,
                editor_present: Boolean(editor),
                editor_hit: Boolean(editor && hit && (hit === editor || editor.contains(hit))),
                hit_chain: chain,
                masks: [...document.querySelectorAll('[data-testid="mask"]')].map(mask => ({
                    text: (mask.parentElement?.innerText || '').slice(0, 300),
                    role: mask.parentElement?.getAttribute('role'),
                    parent_role: mask.parentElement?.parentElement?.getAttribute('role'),
                })),
                layers_text: (document.querySelector('#layers')?.innerText || '').slice(0, 500),
            };
        }""",
        elapsed_ms,
    )


results = []
for run in range(1, 4):
    with x_page() as page:
        _load_parent_post(page, PARENT_URL, STATUS_ID, run)
        close_overlays(page)
        samples = [snapshot(page, 0)]
        for elapsed in (250, 500, 750, 1000, 1500, 2000):
            page.wait_for_timeout(elapsed - samples[-1]["elapsed_ms"])
            samples.append(snapshot(page, elapsed))
        results.append({"run": run, "samples": samples})

print(json.dumps(results, ensure_ascii=False, indent=2))
