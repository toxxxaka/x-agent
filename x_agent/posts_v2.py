"""Reliable X publishing primitives with sanitized diagnostics."""
import os
import re
import time
from collections.abc import Iterable
from typing import Any

from playwright.sync_api import Locator, Page

from .browser import ensure_authenticated, x_page
from .debug import logger

COMPOSE_URL = "https://x.com/compose/post"
X_USERNAME = os.environ.get("X_AGENT_X_USERNAME", "pepetheshneine")
STATUS_RE = re.compile(r"https://x\.com/[^/]+/status/\d+")


def _validate_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    return text.strip()


def _visible(locator: Locator, name: str) -> Locator:
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            logger.info("selector=%s visible_index=%d matches=%d", name, index, locator.count())
            return candidate
    raise RuntimeError(f"no visible element for {name}; matches={locator.count()}")


def close_overlays(page: Page) -> None:
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)


def _editor(page: Page) -> Locator | None:
    for selector in ('[data-testid="tweetTextarea_0"][contenteditable="true"]', '[role="textbox"][contenteditable="true"]'):
        try:
            return _visible(page.locator(selector), selector)
        except RuntimeError:
            continue
    return None


def open_composer(page: Page) -> Locator:
    """Open the standard X composer without relying on the Grok-prone sidebar selector."""
    if "/home" not in page.url:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1_500)
    close_overlays(page)
    editor = _editor(page)
    if editor:
        logger.info("open_composer method=existing editor_found=true")
        return editor

    page.locator("body").click(position={"x": 10, "y": 10})
    page.keyboard.press("n")
    page.wait_for_timeout(1_500)
    editor = _editor(page)
    if editor:
        logger.info("open_composer method=shortcut_n editor_found=true")
        return editor

    links = page.locator('a[href="/compose/post"]')
    for index in range(links.count()):
        link = links.nth(index)
        if not link.is_visible():
            continue
        link.click()
        page.wait_for_timeout(1_500)
        editor = _editor(page)
        if editor:
            logger.info("open_composer method=compose_link editor_found=true")
            return editor
    logger.info("open_composer editor_found=false")
    raise RuntimeError("Could not open X composer")


def _find_tweet_result(obj: Any) -> dict[str, str] | None:
    if isinstance(obj, dict):
        typename = obj.get("__typename")
        if typename == "TweetWithVisibilityResults" and isinstance(obj.get("tweet"), dict):
            return _find_tweet_result(obj["tweet"])
        rest_id = obj.get("rest_id")
        if rest_id and (typename == "Tweet" or "legacy" in obj or "core" in obj):
            return {"id": str(rest_id)}
        for value in obj.values():
            found = _find_tweet_result(value)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_tweet_result(value)
            if found:
                return found
    return None


def extract_created_post_url(response: Any) -> str:
    logger.info("create_tweet status=%d", response.status)
    if response.status not in (200, 201):
        raise RuntimeError(f"CreateTweet HTTP {response.status}")
    try:
        result = _find_tweet_result(response.json())
    except Exception as exc:
        raise RuntimeError("CreateTweet response was not valid JSON") from exc
    if not result or not result.get("id"):
        logger.info("create_tweet tweet_id_found=false")
        raise RuntimeError("Post was submitted but tweet ID was not found in CreateTweet response")
    logger.info("create_tweet tweet_id_found=true")
    return f"https://x.com/{X_USERNAME}/status/{result['id']}"


def _submit(page: Page, editor: Locator, text: str, label: str) -> dict[str, Any]:
    editor.fill(text)
    logger.info("%s editor_found=true chars=%d", label, len(text))
    button = _visible(page.locator('[data-testid="tweetButton"]'), "tweetButton")
    if button.is_disabled():
        raise RuntimeError("X disabled the publish button")
    with page.expect_response(lambda response: "CreateTweet" in response.url, timeout=30_000) as response_info:
        button.click()
    logger.info("%s request_captured=true", label)
    url = extract_created_post_url(response_info.value)
    return {"success": True, "url": url, "text": text}


def _create_post_on_page(page: Page, text: str, label: str = "CREATE root") -> dict[str, Any]:
    close_overlays(page)
    return _submit(page, open_composer(page), _validate_text(text), label)


def _create_reply_on_page(page: Page, parent_url: str, text: str, index: int) -> dict[str, Any]:
    page.goto(parent_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1_500)
    close_overlays(page)
    reply_button = _visible(page.locator('[data-testid="reply"]'), "reply")
    reply_button.click()
    page.wait_for_timeout(500)
    editor = _editor(page)
    if not editor:
        raise RuntimeError("reply composer editor was not found")
    logger.info("REPLY %d parent_url=%s", index, parent_url)
    return _submit(page, editor, _validate_text(text), f"REPLY {index}")


def create_post(text: str) -> dict[str, Any]:
    with x_page() as page:
        return _create_post_on_page(page, text)


def reply_to_post(post_url: str, text: str) -> dict[str, Any]:
    if not isinstance(post_url, str) or not STATUS_RE.fullmatch(post_url.rstrip("/")):
        raise ValueError("post_url must be a canonical https://x.com/<user>/status/<id> URL")
    with x_page() as page:
        return _create_reply_on_page(page, post_url, text, 1)


def create_thread(posts: Iterable[str]) -> dict[str, Any]:
    items = [_validate_text(item) for item in posts]
    if not items:
        raise ValueError("Thread is empty")
    with x_page() as page:
        published = [_create_post_on_page(page, items[0])]
        parent_url = published[0]["url"]
        for index, text in enumerate(items[1:], start=2):
            time.sleep(2)
            reply = _create_reply_on_page(page, parent_url, text, index)
            published.append(reply)
            parent_url = reply["url"]
    return {"success": True, "posts": published}


def status() -> dict[str, Any]:
    with x_page() as page:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)
        ensure_authenticated(page)
        return {"authenticated": True, "url": page.url, "title": page.title()}
