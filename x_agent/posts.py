import re
import time
from collections.abc import Iterable
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from .browser import ensure_authenticated, x_page

COMPOSE_URL = "https://x.com/compose/post"
STATUS_RE = re.compile(r"https://x\.com/[^/]+/status/\d+")


def _validate_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    return text.strip()


def _tweet_url_from_response(response: Any) -> str | None:
    """Derive a canonical status URL from the UI's successful CreateTweet response."""
    if response.status < 200 or response.status >= 300 or "CreateTweet" not in response.url:
        return None
    try:
        data = response.json()
    except Exception:
        return None
    post_id = None
    screen_name = None

    def walk(node: Any) -> None:
        nonlocal post_id, screen_name
        if isinstance(node, dict):
            if node.get("rest_id") and post_id is None:
                post_id = str(node["rest_id"])
            legacy = node.get("legacy")
            if isinstance(legacy, dict) and legacy.get("screen_name") and screen_name is None:
                screen_name = legacy["screen_name"]
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    if post_id and screen_name:
        return f"https://x.com/{screen_name}/status/{post_id}"
    return None


def _publish_from_editor(page: Page, text: str) -> str:
    editor = page.locator('[data-testid="tweetTextarea_0"]')
    editor.wait_for(state="visible", timeout=30_000)
    editor.fill(text)
    button = page.locator('[data-testid="tweetButton"]')
    button.wait_for(state="visible", timeout=30_000)
    if button.is_disabled():
        raise RuntimeError("X disabled the publish button")
    with page.expect_response(lambda r: "CreateTweet" in r.url and 200 <= r.status < 300, timeout=45_000) as response_info:
        button.click()
    url = _tweet_url_from_response(response_info.value)
    if not url:
        raise RuntimeError("X accepted the post, but its URL could not be determined")
    return url


def _post_on_page(page: Page, text: str) -> dict[str, Any]:
    url = _publish_from_editor(page, _validate_text(text))
    return {"success": True, "url": url, "text": text}


def create_post(text: str) -> dict[str, Any]:
    """Publish one post. Call only after the user explicitly confirms publication."""
    text = _validate_text(text)
    with x_page() as page:
        page.goto(COMPOSE_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)
        ensure_authenticated(page)
        return _post_on_page(page, text)


def reply_to_post(post_url: str, text: str) -> dict[str, Any]:
    """Publish a reply to a canonical X status URL."""
    text = _validate_text(text)
    if not isinstance(post_url, str) or not STATUS_RE.fullmatch(post_url.rstrip("/")):
        raise ValueError("post_url must be a canonical https://x.com/<user>/status/<id> URL")
    with x_page() as page:
        page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)
        ensure_authenticated(page)
        reply = page.locator('[data-testid="reply"]').first
        reply.wait_for(state="visible", timeout=30_000)
        reply.click()
        return _post_on_page(page, text)


def create_thread(posts: Iterable[str]) -> dict[str, Any]:
    """Publish a linear thread as a root post followed by sequential replies."""
    items = [_validate_text(text) for text in posts]
    if not items:
        raise ValueError("posts must contain at least one item")
    results = [create_post(items[0])]
    parent_url = results[0]["url"]
    for text in items[1:]:
        time.sleep(2)
        result = reply_to_post(parent_url, text)
        results.append(result)
        parent_url = result["url"]
    return {"success": True, "posts": results}


def status() -> dict[str, Any]:
    """Check that the saved cookies still provide an authenticated X session."""
    with x_page() as page:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)
        ensure_authenticated(page)
        compose = page.locator('[data-testid="SideNav_NewTweet_Button"]').count() > 0
        return {"authenticated": compose, "url": page.url, "title": page.title()}
