import json

from x_agent.browser import ensure_authenticated, x_page
from x_agent.posts import _editor, close_overlays


def describe(locator):
    return locator.evaluate(
        """el => {
            const rect = el.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            const top = document.elementFromPoint(centerX, centerY);
            const chain = [];
            let node = el;
            while (node && chain.length < 10) {
                chain.push({
                    tag: node.tagName,
                    role: node.getAttribute && node.getAttribute('role'),
                    testid: node.getAttribute && node.getAttribute('data-testid'),
                    aria: node.getAttribute && node.getAttribute('aria-label'),
                    id: node.id || null,
                });
                node = node.parentElement;
            }
            return {
                testid: el.getAttribute('data-testid'),
                role: el.getAttribute('role'),
                aria: el.getAttribute('aria-label'),
                disabled: Boolean(el.disabled),
                rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                hit_is_self_or_child: Boolean(top && (top === el || el.contains(top))),
                hit_testid: top && top.getAttribute('data-testid'),
                hit_role: top && top.getAttribute('role'),
                hit_tag: top && top.tagName,
                chain,
            };
        }"""
    )


with x_page() as page:
    page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2_000)
    ensure_authenticated(page)
    close_overlays(page)
    before = page.locator('[data-testid="tweetTextarea_0"][contenteditable="true"]').count()
    page.locator("body").click(position={"x": 10, "y": 10})
    page.keyboard.press("n")
    page.wait_for_timeout(2_000)
    editor = _editor(page)
    if editor is None:
        raise RuntimeError("diagnostic could not find editor")
    buttons = page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]')
    visible_buttons = []
    for index in range(buttons.count()):
        button = buttons.nth(index)
        if button.is_visible():
            info = describe(button)
            info["index"] = index
            visible_buttons.append(info)
    dialogs = page.locator('[role="dialog"]')
    editor_dialog = editor.locator('xpath=ancestor::*[@role="dialog"][1]')
    result = {
        "url": page.url.split("?")[0],
        "editors_before_shortcut": before,
        "editor": describe(editor),
        "dialogs": dialogs.count(),
        "editor_dialogs": editor_dialog.count(),
        "editor_dialog_buttons": editor_dialog.locator(
            '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]'
        ).count() if editor_dialog.count() else 0,
        "visible_buttons": visible_buttons,
        "masks": page.locator('[data-testid="mask"]').count(),
    }
    page.screenshot(path="/tmp/x-agent-compose-diagnostic.png", full_page=True)
    print(json.dumps(result, indent=2))
    page.keyboard.press("Escape")
