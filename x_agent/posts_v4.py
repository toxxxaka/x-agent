"""Reliable X publishing primitives with sanitized diagnostics."""

import os
import re
import time
from collections.abc import Iterable
from typing import Any

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from .browser import ensure_authenticated, x_page
from .debug import logger

HOME_URL = "https://x.com/home"
COMPOSE_URL = "https://x.com/compose/post"
X_USERNAME = os.environ.get("X_AGENT_X_USERNAME", "pepetheshneine")
STATUS_RE = re.compile(
    r"^https://(?:www\.)?x\.com/(?P<user>[^/?#]+)/status/(?P<id>\d+)"
    r"(?:[/?#].*)?$"
)
EDITOR_SELECTORS = (
    '[data-testid="tweetTextarea_0"][contenteditable="true"]',
    '[role="textbox"][contenteditable="true"]',
)
PUBLISH_SELECTOR = (
    '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]'
)


def _validate_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    return text.strip()


def _canonical_status_url(post_url: str) -> tuple[str, str]:
    if not isinstance(post_url, str):
        raise ValueError("post_url must be a canonical X status URL")
    match = STATUS_RE.fullmatch(post_url.strip())
    if not match:
        raise ValueError("post_url must be an https://x.com/<user>/status/<id> URL")
    return (
        f"https://x.com/{match.group('user')}/status/{match.group('id')}",
        match.group("id"),
    )


def _receives_pointer_events(locator: Locator) -> bool:
    try:
        return bool(
            locator.evaluate(
                """el => {
                    const rect = el.getBoundingClientRect();
                    if (!rect.width || !rect.height) return false;
                    const hit = document.elementFromPoint(
                        rect.left + rect.width / 2,
                        rect.top + rect.height / 2
                    );
                    return Boolean(hit && (hit === el || el.contains(hit)));
                }"""
            )
        )
    except Exception:
        return False


def _visible(
    locator: Locator,
    name: str,
    *,
    require_pointer_events: bool = False,
) -> Locator:
    matches = locator.count()
    for index in range(matches):
        candidate = locator.nth(index)
        if not candidate.is_visible():
            continue
        if require_pointer_events and not _receives_pointer_events(candidate):
            logger.info(
                "selector=%s rejected_index=%d reason=covered matches=%d",
                name,
                index,
                matches,
            )
            continue
        logger.info(
            "selector=%s visible_index=%d matches=%d",
            name,
            index,
            matches,
        )
        return candidate
    qualifier = " visible and uncovered" if require_pointer_events else " visible"
    raise RuntimeError(f"no{qualifier} element for {name}; matches={matches}")


def dismiss_cookie_consent(page: Page) -> bool:
    """Dismiss X's blocking consent layer without accepting optional cookies."""
    labels = (
        "Refuse non-essential cookies",
        "Reject non-essential cookies",
        "Reject all",
    )
    for label in labels:
        buttons = page.locator("button, [role=button]").filter(has_text=label)
        for index in range(buttons.count()):
            button = buttons.nth(index)
            visible_text = " ".join(button.inner_text().split())
            if not button.is_visible() or visible_text != label:
                continue
            try:
                button.click(timeout=3_000)
            except PlaywrightTimeoutError:
                logger.info("cookie_consent normal_click=false force_fallback=true")
                button.click(force=True, timeout=5_000)
            page.wait_for_timeout(500)
            logger.info("cookie_consent dismissed=true choice=reject")
            return True
    return False


def close_overlays(page: Page) -> None:
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    dismiss_cookie_consent(page)


def _editor(page: Page, scope: Locator | None = None) -> Locator | None:
    root: Page | Locator = scope if scope is not None else page
    for selector in EDITOR_SELECTORS:
        try:
            return _visible(
                root.locator(selector),
                selector,
                require_pointer_events=True,
            )
        except RuntimeError:
            continue
    return None


def open_composer(page: Page) -> Locator:
    if "/home" not in page.url:
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2_000)
    ensure_authenticated(page)
    close_overlays(page)

    editor = _editor(page)
    if editor:
        logger.info("OPEN_COMPOSER method=existing editor_found=true")
        return editor

    page.locator("body").click(position={"x": 10, "y": 10})
    page.keyboard.press("n")
    page.wait_for_timeout(1_500)
    dismiss_cookie_consent(page)
    editor = _editor(page)
    if editor:
        logger.info("OPEN_COMPOSER method=shortcut_n editor_found=true")
        return editor

    links = page.locator('a[href="/compose/post"]')
    for index in range(links.count()):
        link = links.nth(index)
        if not link.is_visible() or not _receives_pointer_events(link):
            continue
        link.click(timeout=10_000)
        page.wait_for_timeout(1_500)
        dismiss_cookie_consent(page)
        editor = _editor(page)
        if editor:
            logger.info("OPEN_COMPOSER method=compose_link editor_found=true")
            return editor

    page.goto(COMPOSE_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2_000)
    ensure_authenticated(page)
    dismiss_cookie_consent(page)
    editor = _editor(page)
    if editor:
        logger.info("OPEN_COMPOSER method=direct_url editor_found=true")
        return editor

    logger.info("OPEN_COMPOSER editor_found=false")
    raise RuntimeError("Could not open an interactive X composer")


def _is_tweet_result(obj: dict[str, Any]) -> bool:
    if not obj.get("rest_id"):
        return False
    if obj.get("__typename") == "Tweet":
        return True
    legacy = obj.get("legacy")
    if not isinstance(legacy, dict):
        return False
    return any(
        key in legacy
        for key in (
            "full_text",
            "conversation_id_str",
            "in_reply_to_status_id_str",
            "retweet_count",
        )
    )


def _find_tweet_result(obj: Any) -> dict[str, str] | None:
    if isinstance(obj, dict):
        if obj.get("__typename") == "TweetWithVisibilityResults":
            wrapped = obj.get("tweet")
            if isinstance(wrapped, dict):
                found = _find_tweet_result(wrapped)
                if found:
                    return found
        if _is_tweet_result(obj):
            return {"id": str(obj["rest_id"])}
        for preferred_key in (
            "create_tweet",
            "tweet_results",
            "result",
            "tweet",
            "data",
        ):
            if preferred_key in obj:
                found = _find_tweet_result(obj[preferred_key])
                if found:
                    return found
        for key, value in obj.items():
            if key in {
                "create_tweet",
                "tweet_results",
                "result",
                "tweet",
                "data",
            }:
                continue
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
        raise RuntimeError(
            "Post was submitted but a Tweet rest_id was not found in CreateTweet response"
        )
    logger.info("create_tweet tweet_id_found=true")
    return f"https://x.com/{X_USERNAME}/status/{result['id']}"


def _composer_scope(editor: Locator) -> tuple[Locator, str]:
    dialog = editor.locator('xpath=ancestor::*[@role="dialog"][1]')
    if dialog.count() and dialog.first.is_visible():
        return dialog.first, "dialog"

    shared = editor.locator(
        "xpath=ancestor::*[descendant::*["
        "@data-testid='tweetButton' or @data-testid='tweetButtonInline'"
        "]][1]"
    )
    if shared.count():
        return shared.first, "nearest_common_ancestor"
    raise RuntimeError("Could not associate the editor with its publish controls")


def _publish_button(page: Page, editor: Locator, label: str) -> Locator:
    scope, method = _composer_scope(editor)
    candidates = scope.locator(PUBLISH_SELECTOR)
    deadline = time.monotonic() + 5
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            button = _visible(
                candidates,
                f"{label} publish_button",
                require_pointer_events=True,
            )
            if not button.is_disabled():
                logger.info(
                    "%s button_found=true scope=%s testid=%s",
                    label,
                    method,
                    button.get_attribute("data-testid"),
                )
                return button
        except RuntimeError as exc:
            last_error = exc
        page.wait_for_timeout(200)
    if last_error:
        raise RuntimeError(f"Publish button is not interactive: {last_error}")
    raise RuntimeError("X disabled the publish button")


def _submit(page: Page, editor: Locator, text: str, label: str) -> dict[str, Any]:
    editor.fill(text)
    logger.info("%s editor_found=true chars=%d", label, len(text))
    button = _publish_button(page, editor, label)
    with page.expect_response(
        lambda response: "CreateTweet" in response.url,
        timeout=30_000,
    ) as response_info:
        button.click(timeout=15_000)
    logger.info("%s request_captured=true", label)
    url = extract_created_post_url(response_info.value)
    logger.info("%s complete=true url=%s", label, url)
    return {"success": True, "url": url, "text": text}


def _save_failure_screenshot(page: Page, name: str) -> None:
    safe_name = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    try:
        page.screenshot(
            path=f"/var/log/x-agent/{safe_name}-failure.png",
            full_page=True,
        )
        logger.info("%s failure_screenshot_saved=true", name)
    except Exception:
        logger.exception("%s failure_screenshot_failed", name)


def _create_post_on_page(
    page: Page,
    text: str,
    label: str = "CREATE root",
) -> dict[str, Any]:
    logger.info("%s start", label)
    try:
        close_overlays(page)
        editor = open_composer(page)
        return _submit(page, editor, _validate_text(text), label)
    except Exception:
        logger.exception("%s failed", label)
        _save_failure_screenshot(page, label)
        raise


def _parent_article(page: Page, status_id: str) -> Locator | None:
    matches = page.locator(
        f'article[data-testid="tweet"]:has(a[href*="/status/{status_id}"])'
    )
    logger.info("parent_article status_id=%s matches=%d", status_id, matches.count())
    for index in range(matches.count()):
        article = matches.nth(index)
        if article.is_visible():
            return article
    return None


def _load_parent_post(page: Page, parent_url: str, status_id: str, index: int) -> None:
    for attempt in range(1, 4):
        page.goto(parent_url, wait_until="domcontentloaded", timeout=60_000)
        ensure_authenticated(page)
        for poll in range(1, 17):
            page.wait_for_timeout(500)
            dismiss_cookie_consent(page)
            if _parent_article(page, status_id) is not None:
                logger.info(
                    "REPLY %d parent_loaded=true attempt=%d poll=%d url=%s",
                    index,
                    attempt,
                    poll,
                    page.url.split("?")[0],
                )
                return
        logger.info("REPLY %d parent_loaded=false attempt=%d", index, attempt)
        page.wait_for_timeout(1_500)
    raise RuntimeError(f"parent post {status_id} was not rendered by X")


def _create_reply_on_page(
    page: Page,
    parent_url: str,
    text: str,
    index: int,
) -> dict[str, Any]:
    canonical_url, status_id = _canonical_status_url(parent_url)
    logger.info("REPLY %d start parent_url=%s", index, canonical_url)
    try:
        _load_parent_post(page, canonical_url, status_id, index)
        close_overlays(page)

        editor = _editor(page)
        if editor:
            logger.info("REPLY %d editor_found=true method=inline", index)
        else:
            logger.info("REPLY %d inline_editor_found=false", index)
            article = _parent_article(page, status_id)
            reply_locator = (
                article.locator('[data-testid="reply"]')
                if article is not None
                else page.locator('[data-testid="reply"]')
            )
            reply_button = _visible(
                reply_locator,
                f"REPLY {index} reply_button",
                require_pointer_events=True,
            )
            logger.info("REPLY %d reply_button_found=true", index)
            reply_button.click(timeout=15_000)
            page.wait_for_timeout(1_000)
            dismiss_cookie_consent(page)
            editor = _editor(page)
            if not editor:
                raise RuntimeError("reply composer editor was not found")
            logger.info("REPLY %d editor_found=true method=reply_button", index)

        return _submit(
            page,
            editor,
            _validate_text(text),
            f"REPLY {index}",
        )
    except Exception:
        logger.exception("REPLY %d failed parent_url=%s", index, canonical_url)
        _save_failure_screenshot(page, f"reply-{index}")
        raise


def create_post(text: str) -> dict[str, Any]:
    with x_page() as page:
        return _create_post_on_page(page, text)


def reply_to_post(post_url: str, text: str) -> dict[str, Any]:
    canonical_url, _ = _canonical_status_url(post_url)
    with x_page() as page:
        return _create_reply_on_page(page, canonical_url, text, 1)


def create_thread(posts: Iterable[str]) -> dict[str, Any]:
    items = [_validate_text(item) for item in posts]
    if not items:
        raise ValueError("Thread is empty")
    logger.info("THREAD start posts=%d", len(items))
    published: list[dict[str, Any]] = []
    try:
        with x_page() as page:
            logger.info("THREAD x_page_entered=true")
            root = _create_post_on_page(page, items[0])
            published.append(root)
            parent_url = root["url"]
            logger.info("THREAD root_complete=true parent_url=%s", parent_url)

            for index, text in enumerate(items[1:], start=1):
                logger.info(
                    "THREAD starting_reply=%d parent_url=%s",
                    index,
                    parent_url,
                )
                time.sleep(2)
                reply = _create_reply_on_page(
                    page,
                    parent_url,
                    text,
                    index,
                )
                published.append(reply)
                parent_url = reply["url"]
                logger.info(
                    "THREAD reply_complete=%d new_parent_url=%s",
                    index,
                    parent_url,
                )

            logger.info("THREAD complete posts=%d", len(published))
            return {"success": True, "posts": published}
    except Exception:
        logger.exception(
            "THREAD failed published_count=%d published_urls=%s",
            len(published),
            [item["url"] for item in published],
        )
        raise


def status() -> dict[str, Any]:
    with x_page() as page:
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)
        ensure_authenticated(page)
        dismiss_cookie_consent(page)
        account = page.locator('[data-testid="SideNav_AccountSwitcher_Button"]')
        authenticated = any(
            account.nth(index).is_visible() for index in range(account.count())
        )
        if not authenticated:
            raise RuntimeError("X home loaded but the authenticated account control is missing")
        return {"authenticated": True, "url": page.url, "title": page.title()}
