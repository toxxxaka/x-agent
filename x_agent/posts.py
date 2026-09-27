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
AUDIENCE_BUTTON_LABEL = "Choose audience"
EVERYONE_AUDIENCE = "Everyone"
MEMBER_COUNT_SUFFIX_RE = re.compile(
    r"\s+\d+(?:\.\d+)?(?:[KMB])?\s+Members$",
    re.IGNORECASE,
)


def _validate_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    return text.strip()


def _validate_image_path(image_path: str | None) -> str | None:
    """Return a safe local image path or reject before opening the composer."""
    if image_path is None:
        return None
    if not isinstance(image_path, str) or not image_path:
        raise ValueError("image_path must be an absolute path when supplied")
    if not os.path.isabs(image_path):
        raise ValueError("image_path must be an absolute path")
    if not os.path.isfile(image_path):
        raise ValueError("image_path must reference a regular file")
    if os.path.getsize(image_path) <= 0:
        raise ValueError("image_path must not be empty")
    extension = os.path.splitext(image_path)[1].lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise ValueError("image_path must be a JPG, PNG, WEBP, or GIF image")
    return image_path


def _normalise_community_name(value: str) -> str:
    """Use a presentation-independent form for exact Community matching."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("community must be a non-empty string when supplied")
    return " ".join(value.split()).casefold()


def _community_name_from_menuitem(item_text: str) -> str | None:
    """Return the Community name shown by the audience picker, never its member count."""
    cleaned = " ".join(item_text.split())
    if not cleaned or cleaned.casefold() == EVERYONE_AUDIENCE.casefold():
        return None
    return MEMBER_COUNT_SUFFIX_RE.sub("", cleaned).strip() or None


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
        locator.scroll_into_view_if_needed(timeout=5_000)
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
        editor = _wait_for_interactive_editor(page, f"REPLY {index}")
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


def _wait_for_audience_button(page: Page, editor: Locator) -> Locator:
    for _ in range(6):
        dismiss_cookie_consent(page)
        try:
            return _audience_button(page, editor)
        except RuntimeError:
            page.wait_for_timeout(500)
    raise RuntimeError("X Community audience control was not interactive")


def _composer_with_audience(page: Page, editor: Locator) -> Locator:
    """Return a composer which exposes X's audience control, or fail before text."""
    try:
        _wait_for_audience_button(page, editor)
        return editor
    except RuntimeError:
        logger.info("audience composer_fallback=direct_url")
    page.goto(COMPOSE_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1_500)
    ensure_authenticated(page)
    dismiss_cookie_consent(page)
    direct_editor = _editor(page)
    if direct_editor is None:
        raise RuntimeError("X Community composer editor was not found")
    _wait_for_audience_button(page, direct_editor)
    return direct_editor


def _audience_button(page: Page, editor: Locator) -> Locator:
    scope, _ = _composer_scope(editor)
    # Playwright's normal click below waits for event delivery. Do not reject this
    # control merely because a transient X layer is still animating over it.
    return _visible(
        scope.get_by_label(AUDIENCE_BUTTON_LABEL),
        "audience_button",
    )


def _community_menu_items(page: Page) -> list[tuple[Locator, str]]:
    items: list[tuple[Locator, str]] = []
    candidates = page.locator('[role=menuitem]')
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        if not candidate.is_visible():
            continue
        name = _community_name_from_menuitem(candidate.inner_text())
        if name:
            items.append((candidate, name))
    return items


def _open_community_picker(page: Page, editor: Locator) -> Locator:
    button = _wait_for_audience_button(page, editor)
    # A stale aria-expanded value can survive an X overlay transition. Reset it,
    # then require actual visible menu items rather than trusting the attribute.
    if button.get_attribute("aria-expanded") == "true":
        button.click(timeout=15_000)
        page.wait_for_timeout(250)
    button.click(timeout=15_000)
    for _ in range(10):
        if _community_menu_items(page):
            return button
        page.wait_for_timeout(250)
    close_overlays(page)
    raise RuntimeError("X Community audience picker did not expose selectable Communities")


def select_community(page: Page, editor: Locator, community: str) -> str:
    """Select and verify a Community before text is entered. Never falls back."""
    requested = _normalise_community_name(community)
    button = _open_community_picker(page, editor)
    matches = [
        (item, name)
        for item, name in _community_menu_items(page)
        if _normalise_community_name(name) == requested
    ]
    logger.info(
        "audience selection requested=true available_count=%d exact_matches=%d",
        len(_community_menu_items(page)),
        len(matches),
    )
    if len(matches) != 1:
        close_overlays(page)
        raise RuntimeError("requested X Community was not found uniquely; post aborted")
    item, selected_name = matches[0]
    item.click(timeout=15_000)
    page.wait_for_timeout(500)
    visible_audience = " ".join(button.inner_text().split())
    if (
        button.get_attribute("aria-expanded") == "true"
        or _normalise_community_name(visible_audience) != requested
    ):
        close_overlays(page)
        raise RuntimeError("requested X Community could not be confirmed; post aborted")
    logger.info("audience community_selected=true name=%s", selected_name)
    return selected_name


def list_communities() -> dict[str, Any]:
    """Return Communities offered by X's audience picker without publishing."""
    with x_page() as page:
        close_overlays(page)
        editor = _composer_with_audience(page, open_composer(page))
        try:
            _open_community_picker(page, editor)
            communities = [name for _, name in _community_menu_items(page)]
            logger.info("audience communities_listed=true count=%d", len(communities))
            return {"communities": communities}
        finally:
            close_overlays(page)


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


def _media_preview_count(page: Page) -> int:
    """Count X composer attachment widgets; profile/timeline images do not match."""
    selectors = (
        '[data-testid="attachments"]',
        '[data-testid="attachment"]',
        '[data-testid="tweetPhoto"]',
        '[data-testid="mediaPreview"]',
    )
    total = 0
    for selector in selectors:
        locator = page.locator(selector)
        for index in range(locator.count()):
            if locator.nth(index).is_visible():
                total += 1
    return total


def _attach_image(page: Page, image_path: str, label: str) -> None:
    """Attach one image and prove X accepted it before a post can be submitted."""
    image_path = _validate_image_path(image_path)
    assert image_path is not None
    inputs = page.locator('input[type="file"][data-testid="fileInput"]')
    if inputs.count() == 0:
        inputs = page.locator('input[type="file"]')
    if inputs.count() != 1:
        raise RuntimeError("X composer media input was missing or ambiguous; post aborted")

    preview_before = _media_preview_count(page)
    upload_responses: list[int] = []

    def record_upload(response: Any) -> None:
        safe_url = response.url.split("?", 1)[0].lower()
        if "upload" in safe_url and ("media" in safe_url or "video" in safe_url):
            upload_responses.append(response.status)

    logger.info(
        "%s media_attach_start=true file=%s bytes=%d",
        label,
        os.path.basename(image_path),
        os.path.getsize(image_path),
    )
    page.on("response", record_upload)
    try:
        inputs.first.set_input_files(image_path, timeout=30_000)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            preview_after = _media_preview_count(page)
            upload_ok = any(status in (200, 201, 202) for status in upload_responses)
            if preview_after > preview_before and upload_ok:
                logger.info(
                    "%s media_attached=true preview_count=%d upload_status=%d",
                    label,
                    preview_after,
                    upload_responses[-1],
                )
                return
            page.wait_for_timeout(500)
    finally:
        page.remove_listener("response", record_upload)

    logger.info(
        "%s media_attached=false preview_before=%d upload_responses=%s",
        label,
        preview_before,
        upload_responses,
    )
    raise RuntimeError("X image upload could not be verified; post aborted")


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


def _submit(
    page: Page, editor: Locator, text: str, label: str, image_path: str | None = None
) -> dict[str, Any]:
    if image_path is not None:
        _attach_image(page, image_path, label)
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
    community: str | None = None,
    image_path: str | None = None,
) -> dict[str, Any]:
    logger.info("%s start", label)
    try:
        close_overlays(page)
        editor = open_composer(page)
        audience = EVERYONE_AUDIENCE
        if community is not None:
            editor = _composer_with_audience(page, editor)
            audience = select_community(page, editor, community)
        else:
            logger.info("audience everyone_selected=true")
        result = _submit(page, editor, _validate_text(text), label, image_path)
        result["audience"] = audience
        return result
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


def _wait_for_interactive_editor(
    page: Page,
    label: str,
    *,
    attempts: int = 5,
) -> Locator | None:
    """Wait out transient X layers after navigation or consent dismissal."""
    for attempt in range(1, attempts + 1):
        dismiss_cookie_consent(page)
        editor = _editor(page)
        if editor:
            logger.info("%s editor_interactive=true attempt=%d", label, attempt)
            return editor
        logger.info("%s editor_interactive=false attempt=%d", label, attempt)
        page.wait_for_timeout(500)
    return None


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

        editor = _wait_for_interactive_editor(page, f"REPLY {index}")
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
            editor = _wait_for_interactive_editor(
                page,
                f"REPLY {index} modal",
            )
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


def create_post(
    text: str, community: str | None = None, image_path: str | None = None
) -> dict[str, Any]:
    image_path = _validate_image_path(image_path)
    with x_page() as page:
        return _create_post_on_page(
            page, text, community=community, image_path=image_path
        )


def reply_to_post(post_url: str, text: str) -> dict[str, Any]:
    canonical_url, _ = _canonical_status_url(post_url)
    with x_page() as page:
        return _create_reply_on_page(page, canonical_url, text, 1)


def create_thread(
    posts: Iterable[str],
    community: str | None = None,
    image_path: str | None = None,
) -> dict[str, Any]:
    items = [_validate_text(item) for item in posts]
    if not items:
        raise ValueError("Thread is empty")
    image_path = _validate_image_path(image_path)
    logger.info(
        "THREAD start posts=%d community_requested=%s",
        len(items),
        community is not None,
    )
    published: list[dict[str, Any]] = []
    try:
        with x_page() as page:
            logger.info("THREAD x_page_entered=true")
            root = _create_post_on_page(
                page, items[0], community=community, image_path=image_path
            )
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
