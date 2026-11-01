"""X Articles authoring and publication through the official web editor."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .browser import ensure_authenticated, x_page
from .debug import logger
from .posts import (
    _remove_staged_image,
    _safe_image_url,
    _stage_image_for_chromium,
    _validate_image_path,
    _verify_browser_can_decode_image,
)

ARTICLES_URL = "https://x.com/compose/articles"
ARTICLE_EDIT_RE = re.compile(r"^https://x\.com/compose/articles/edit/(?P<id>\d+)")
ARTICLE_PUBLIC_RE = re.compile(
    r"^https://x\.com/[^/]+/article/(?P<id>\d+)(?:[/?#].*)?$"
)


@dataclass(frozen=True)
class ArticleBlock:
    kind: str
    text: str | tuple[str, ...]


def _validate_title(title: str) -> str:
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    cleaned = " ".join(title.split())
    if len(cleaned) > 250:
        raise ValueError("title is too long for X Articles")
    return cleaned


def _strip_inline_markdown(text: str) -> str:
    """Keep readable text while the editor handles block-level formatting."""
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"(?<!\\)([*_]{1,2}|~~|`)", "", text)
    return text.replace("\\*", "*").replace("\\_", "_").strip()


def parse_article_markdown(body_markdown: str) -> list[ArticleBlock]:
    """Parse the conservative Markdown subset supported by the UI automation."""
    if not isinstance(body_markdown, str) or not body_markdown.strip():
        raise ValueError("body_markdown must be a non-empty string")

    lines = body_markdown.replace("\r\n", "\n").split("\n")
    blocks: list[ArticleBlock] = []
    paragraph: list[str] = []
    list_kind: str | None = None
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            value = _strip_inline_markdown(" ".join(part.strip() for part in paragraph))
            if value:
                blocks.append(ArticleBlock("body", value))
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_kind
        if list_items and list_kind:
            blocks.append(ArticleBlock(list_kind, tuple(list_items)))
        list_items.clear()
        list_kind = None

    in_fence = False
    fence_lines: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_fence:
                if fence_lines:
                    blocks.append(ArticleBlock("quote", "\n".join(fence_lines)))
                fence_lines.clear()
            in_fence = not in_fence
            continue
        if in_fence:
            fence_lines.append(raw.rstrip())
            continue
        if not stripped:
            flush_paragraph()
            flush_list()
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            blocks.append(ArticleBlock("heading", _strip_inline_markdown(stripped[3:])))
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            blocks.append(ArticleBlock("subheading", _strip_inline_markdown(stripped[4:])))
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if bullet or ordered:
            flush_paragraph()
            kind = "ul" if bullet else "ol"
            if list_kind not in (None, kind):
                flush_list()
            list_kind = kind
            value = bullet.group(1) if bullet else ordered.group(1)
            list_items.append(_strip_inline_markdown(value))
            continue
        if stripped.startswith("> "):
            flush_paragraph()
            flush_list()
            blocks.append(ArticleBlock("quote", _strip_inline_markdown(stripped[2:])))
            continue
        flush_list()
        paragraph.append(stripped)

    if in_fence and fence_lines:
        blocks.append(ArticleBlock("quote", "\n".join(fence_lines)))
    flush_paragraph()
    flush_list()
    if not blocks:
        raise ValueError("body_markdown did not contain any article content")
    return blocks


def _visible_exact_text(page: Page, text: str, timeout_ms: int = 10_000) -> Locator:
    deadline = time.monotonic() + timeout_ms / 1_000
    while time.monotonic() < deadline:
        candidates = page.get_by_text(text, exact=True)
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            if candidate.is_visible():
                return candidate
        page.wait_for_timeout(200)
    raise RuntimeError(f"visible X Articles control was not found: {text}")


def _dismiss_cookies(page: Page) -> None:
    """Dismiss Articles consent with a normal click; never force editor UI."""
    labels = (
        "Refuse non-essential cookies",
        "Reject non-essential cookies",
        "Reject all",
    )
    for label in labels:
        candidates = page.get_by_text(label, exact=True)
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            if not candidate.is_visible():
                continue
            candidate.click(timeout=5_000)
            page.wait_for_timeout(300)
            logger.info("ARTICLE cookie_consent_dismissed=true")
            return


def _wait_for_editor(page: Page) -> tuple[Locator, Locator, Locator]:
    """Wait for the actual editor, not only the surrounding Articles shell."""
    for attempt in range(2):
        try:
            title = page.locator('textarea[name="Article Title"]')
            title.wait_for(state="visible", timeout=20_000)
            body = page.locator('[data-testid="composer"][contenteditable="true"]')
            body.wait_for(state="visible", timeout=20_000)
            cover = page.locator('input[type="file"][data-testid="fileInput"]')
            cover.wait_for(state="attached", timeout=20_000)
            logger.info("ARTICLE editor_ready=true attempt=%d", attempt + 1)
            return title.first, body.first, cover.first
        except PlaywrightTimeoutError:
            logger.info("ARTICLE editor_ready=false attempt=%d", attempt + 1)
            if attempt == 0:
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(3_000)
                _dismiss_cookies(page)
    raise RuntimeError("X Articles editor did not become ready")


def _create_draft(page: Page) -> tuple[str, Locator, Locator, Locator]:
    page.goto(ARTICLES_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3_000)
    ensure_authenticated(page)
    _dismiss_cookies(page)
    write = _visible_exact_text(page, "Write")
    write.click(timeout=15_000)
    page.wait_for_url(re.compile(r"https://x\.com/compose/articles/edit/\d+"), timeout=30_000)
    title, body, cover = _wait_for_editor(page)
    match = ARTICLE_EDIT_RE.match(page.url)
    if not match:
        raise RuntimeError("X did not create a canonical Article draft URL")
    logger.info("ARTICLE draft_created=true draft_id=%s", match.group("id"))
    return page.url.split("?", 1)[0], title, body, cover


def _set_block_style(page: Page, style: str) -> None:
    labels = {"body": "Body", "heading": "Heading", "subheading": "Subheading"}
    target = labels[style]
    toolbar = None
    for label in labels.values():
        controls = page.locator("button").filter(has_text=re.compile(rf"^{re.escape(label)}$"))
        for index in range(controls.count()):
            if controls.nth(index).is_visible():
                toolbar = controls.nth(index)
                break
        if toolbar is not None:
            break
    if toolbar is None:
        raise RuntimeError("X Articles block-style control was not found")
    if " ".join(toolbar.inner_text().split()) == target:
        return
    toolbar.click(timeout=10_000)
    deadline = time.monotonic() + 10
    option: Locator | None = None
    while time.monotonic() < deadline:
        candidates = page.locator('[role="menuitem"]').filter(
            has_text=re.compile(rf"^{re.escape(target)}$")
        )
        for index in range(candidates.count()):
            if candidates.nth(index).is_visible():
                option = candidates.nth(index)
                break
        if option is not None:
            break
        page.wait_for_timeout(200)
    if option is None:
        page.keyboard.press("Escape")
        raise RuntimeError(f"X Articles style option was not found: {target}")
    option.click(timeout=10_000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)


def _toggle_toolbar(page: Page, testid: str) -> None:
    button = page.locator(f'[data-testid="{testid}"]')
    button.first.wait_for(state="visible", timeout=10_000)
    button.first.click(timeout=10_000)


def _focus_editor(page: Page, editor: Locator) -> None:
    """Focus Draft.js, retrying only when X raises its cookie layer mid-action."""
    for attempt in range(3):
        _dismiss_cookies(page)
        try:
            editor.click(timeout=2_000)
            return
        except PlaywrightTimeoutError:
            layers = page.locator("#layers")
            layer_text = layers.inner_text() if layers.count() else ""
            if "cookies" in layer_text.casefold():
                page.wait_for_timeout(300)
                _dismiss_cookies(page)
                logger.info(
                    "ARTICLE editor_focus_retry=true reason=cookie_consent attempt=%d",
                    attempt + 1,
                )
                continue
            if layers.count():
                # X first mounts an empty consent backdrop, then renders its
                # text/buttons about a second later. Let that transition finish
                # before deciding whether this is a dismissible popover.
                page.wait_for_timeout(1_200)
                layer_text = layers.inner_text() if layers.count() else ""
                if "cookies" in layer_text.casefold():
                    _dismiss_cookies(page)
                    reason = "delayed_cookie_consent"
                else:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)
                    reason = "empty_layer"
                logger.info(
                    "ARTICLE editor_focus_retry=true reason=%s attempt=%d",
                    reason,
                    attempt + 1,
                )
                continue
            raise
    raise RuntimeError("X Articles editor could not be focused")


def _article_plaintext(blocks: list[ArticleBlock]) -> str:
    """Render stable, readable blocks without relying on Draft.js selection state."""
    rendered: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            rendered.append(str(block.text).upper())
        elif block.kind == "subheading":
            rendered.append(str(block.text))
        elif block.kind in {"ul", "ol"}:
            items = tuple(block.text) if isinstance(block.text, tuple) else (block.text,)
            marker = "•" if block.kind == "ul" else "-"
            rendered.append("\n".join(f"{marker} {item}" for item in items))
        else:
            rendered.append(str(block.text))
    return "\n\n".join(rendered).strip()


def _ordered_article_parts(blocks: list[ArticleBlock]) -> list[str]:
    """Return canonical text fragments in the exact order an Article must keep."""
    return [
        " ".join(part.split())
        for part in _article_plaintext(blocks).split("\n\n")
        if part.strip()
    ]


def _text_chunks(value: str, size: int = 1_500) -> list[str]:
    """Split Article text into bounded, ordered editor insertions."""
    if size < 1:
        raise ValueError("chunk size must be positive")
    return [value[start : start + size] for start in range(0, len(value), size)]


def _assert_article_order(text: str, blocks: list[ArticleBlock], stage: str) -> None:
    """Fail closed if any body fragment is absent or occurs out of order."""
    visible = " ".join(text.split())
    offset = 0
    for part in _ordered_article_parts(blocks):
        marker = part[: min(70, len(part))]
        position = visible.find(marker, offset)
        if position < 0:
            raise RuntimeError(
                f"X Article {stage} is missing or reorders content near: {marker!r}"
            )
        offset = position + len(marker)


def _insert_blocks(page: Page, editor: Locator, blocks: list[ArticleBlock]) -> None:
    """Replace the complete Draft.js document without retaining stale blocks.

    Large one-shot ``insert_text`` calls can be dropped by Draft.js while it is
    reconciling its internal state. Small ordered chunks keep the browser and
    editor event queues in lockstep; the final full-content assertion is the
    guard against a partial Article draft.
    """
    _focus_editor(page, editor)
    body = _article_plaintext(blocks)
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    for chunk in _text_chunks(body):
        page.keyboard.insert_text(chunk)
        page.wait_for_timeout(25)
    _assert_article_order(editor.inner_text(), blocks, "editor")
    logger.info(
        "ARTICLE body_replaced=true blocks=%d chars=%d",
        len(blocks),
        len(body),
    )


def _cover_preview_count(page: Page) -> int:
    count = 0
    selectors = (
        'img[alt*="header" i]',
        'img[alt*="cover" i]',
        '[data-testid*="cover" i] img',
        '[data-testid*="header" i] img',
        'img[src^="blob:"]',
    )
    for selector in selectors:
        matches = page.locator(selector)
        for index in range(matches.count()):
            if matches.nth(index).is_visible():
                count += 1
    return count


def _article_image_count(page: Page) -> int:
    """Count visible non-profile images in the Article editor or media dialog."""
    images = page.locator("img")
    total = 0
    for index in range(images.count()):
        image = images.nth(index)
        src = image.get_attribute("src") or ""
        if image.is_visible() and "profile_images" not in src:
            total += 1
    return total


def _attach_cover(page: Page, cover_input: Locator, image_path: str) -> None:
    validated = _validate_image_path(image_path)
    assert validated is not None
    if Path(validated).suffix.lower() == ".gif":
        raise ValueError("X Article cover must be a JPG, PNG, or WEBP image")
    staged = _stage_image_for_chromium(validated)
    responses: list[int] = []
    requests = 0

    def is_cover_request(url: str) -> bool:
        lowered = _safe_image_url(url).lower()
        return any(marker in lowered for marker in ("upload", "media/upload", "article"))

    def on_request(request: Any) -> None:
        nonlocal requests
        url = _safe_image_url(request.url)
        if is_cover_request(url):
            requests += 1
            logger.info("ARTICLE cover_network_request method=%s url=%s", request.method, url)

    def on_response(response: Any) -> None:
        url = _safe_image_url(response.url)
        if is_cover_request(url):
            responses.append(response.status)
            logger.info("ARTICLE cover_network_response status=%d url=%s", response.status, url)

    page.on("request", on_request)
    page.on("response", on_response)
    try:
        _verify_browser_can_decode_image(page, str(staged))
        before = _article_image_count(page)
        logger.info(
            "ARTICLE cover_attach_start=true file=%s bytes=%d previews_before=%d",
            Path(validated).name,
            Path(validated).stat().st_size,
            before,
        )
        chooser_button = page.get_by_label("Add photos or video")
        chooser_button.first.wait_for(state="visible", timeout=10_000)
        with page.expect_file_chooser(timeout=10_000) as chooser_info:
            chooser_button.first.click(timeout=10_000)
        chooser_info.value.set_files(str(staged))
        logger.info(
            "ARTICLE cover_file_chooser_done=true filename=%s bytes=%d",
            staged.name,
            staged.stat().st_size,
        )

        apply = _visible_exact_text(page, "Apply")
        if _article_image_count(page) <= before:
            raise RuntimeError("X Article media editor did not preview the selected cover")
        logger.info("ARTICLE cover_crop_preview=true")
        apply.click(timeout=15_000)
        page.wait_for_timeout(1_000)
        logger.info("ARTICLE cover_crop_applied=true")

        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            preview = _article_image_count(page)
            upload_ok = any(status in (200, 201, 202) for status in responses)
            if preview > before and upload_ok:
                logger.info(
                    "ARTICLE cover_verified=true preview_count=%d upload_statuses=%s",
                    preview,
                    responses,
                )
                return
            page.wait_for_timeout(500)
        logger.info(
            "ARTICLE cover_verified=false preview_count=%d requests=%d responses=%s",
            _article_image_count(page),
            requests,
            responses,
        )
        raise RuntimeError("X Article cover upload could not be verified; draft was not published")
    finally:
        page.remove_listener("request", on_request)
        page.remove_listener("response", on_response)
        _remove_staged_image(staged)


def _wait_saved(page: Page) -> None:
    # Article autosave is debounced. The existing "Last saved" marker belongs
    # to the previous mutation and must not be accepted immediately.
    page.wait_for_timeout(4_000)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        text = page.locator("body").inner_text()
        if "Last saved" in text and "Saving" not in text:
            page.wait_for_timeout(1_500)
            logger.info("ARTICLE autosave_confirmed=true")
            return
        page.wait_for_timeout(500)
    raise RuntimeError("X Article autosave could not be confirmed")


def _preview_article(page: Page, title: str, blocks: list[ArticleBlock]) -> None:
    editor_url = page.url.split("/preview", 1)[0]
    _visible_exact_text(page, "Preview").click(timeout=15_000)
    page.wait_for_url(re.compile(r".*/compose/articles/edit/\d+/preview"), timeout=15_000)
    page.wait_for_timeout(2_000)
    _dismiss_cookies(page)
    visible = page.locator("body").inner_text()
    if title not in visible:
        raise RuntimeError("X Article preview did not contain the expected title")
    _assert_article_order(visible, blocks, "preview")
    if _article_image_count(page) < 1:
        raise RuntimeError("X Article preview did not contain the cover image")
    logger.info("ARTICLE preview_verified=true checked_blocks=%d", len(blocks))
    page.goto(editor_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3_000)
    _dismiss_cookies(page)
    _wait_for_editor(page)


def _find_public_url(page: Page, title: str, draft_url: str | None = None) -> str:
    if ARTICLE_PUBLIC_RE.match(page.url):
        return page.url.split("?", 1)[0]
    page.goto(ARTICLES_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3_000)
    published = page.get_by_text("Published", exact=True)
    for index in range(published.count()):
        if published.nth(index).is_visible():
            published.nth(index).click(timeout=10_000)
            page.wait_for_timeout(2_000)
            break
    target: Locator | None = None
    draft_path = None
    if draft_url:
        match = ARTICLE_EDIT_RE.match(draft_url)
        if match:
            draft_path = f"/compose/articles/edit/{match.group('id')}"
    links = page.locator('a[href*="/compose/articles/edit/"]')
    for index in range(links.count()):
        link = links.nth(index)
        href = (link.get_attribute("href") or "").split("?", 1)[0]
        if not link.is_visible():
            continue
        if (draft_path and href == draft_path) or (not draft_path and title[:80] in link.inner_text()):
            target = link
            break
    if target is not None:
        card = target.locator('xpath=ancestor::*[.//button[@aria-label="More"]][1]')
        more = card.get_by_label("More") if card.count() else page.get_by_label("More")
        for index in range(more.count()):
            if not more.nth(index).is_visible():
                continue
            before_pages = list(page.context.pages)
            more.nth(index).click(timeout=10_000)
            _visible_exact_text(page, "View Article").click(timeout=10_000)
            page.wait_for_timeout(3_000)
            new_pages = [item for item in page.context.pages if item not in before_pages]
            candidate = new_pages[-1] if new_pages else page
            focus = candidate.locator('a[aria-label="Focus mode"]')
            if focus.count() and focus.first.is_visible():
                href = focus.first.get_attribute("href") or ""
                if href.startswith("/"):
                    return f"https://x.com{href.split('?', 1)[0]}"
            if ARTICLE_PUBLIC_RE.match(candidate.url) or "/i/article/" in candidate.url:
                return candidate.url.split("?", 1)[0]
            break
    raise RuntimeError("Article was published but its public URL was not found")


def _publish_everyone(page: Page, title: str, draft_url: str | None = None) -> str:
    _visible_exact_text(page, "Publish").click(timeout=15_000)
    sheet = page.locator('[data-testid="sheetDialog"]')
    try:
        sheet.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError:
        raise RuntimeError("X Article audience dialog was not shown; article remains a draft")
    audience = sheet.locator('[data-testid="audienceControl-everyone"]')
    if audience.count() != 1:
        page.keyboard.press("Escape")
        raise RuntimeError("Everyone audience control was ambiguous; article remains a draft")
    radio = audience.locator('input[type="radio"][name="audienceControl"]')
    if radio.count() != 1:
        page.keyboard.press("Escape")
        raise RuntimeError("Everyone audience radio was missing; article remains a draft")
    if not radio.first.is_checked():
        audience.first.click(timeout=10_000)
        page.wait_for_timeout(300)
    if not radio.first.is_checked():
        page.keyboard.press("Escape")
        raise RuntimeError(
            "Everyone audience could not be confirmed; article remains a draft"
        )
    logger.info("ARTICLE audience_confirmed=Everyone")

    publish_buttons = sheet.get_by_text("Publish", exact=True)
    visible = [publish_buttons.nth(index) for index in range(publish_buttons.count()) if publish_buttons.nth(index).is_visible()]
    if len(visible) != 1:
        raise RuntimeError("X Article final Publish control was not found")
    visible[0].click(timeout=15_000)
    page.wait_for_timeout(4_000)
    url = _find_public_url(page, title, draft_url)
    logger.info("ARTICLE published=true public_url=%s", url)
    return url


def _verify_public_article(page: Page, url: str, title: str) -> None:
    # X can reject a fresh anonymous Chromium context at the edge. Audience is
    # confirmed before publication; verify the canonical public reader through
    # the active session instead of treating that anti-automation response as a
    # publication failure.
    verification_page = page.context.new_page()
    try:
        verification_page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        verification_page.wait_for_timeout(4_000)
        content = verification_page.locator("article").first.inner_text()
        if title not in content or "/i/flow/login" in verification_page.url:
            raise RuntimeError("published X Article could not be opened in the canonical reader")
        logger.info("ARTICLE public_reader_verification=true")
    finally:
        verification_page.close()


def create_article(
    title: str,
    body_markdown: str,
    cover_image_path: str,
    *,
    publish: bool = False,
) -> dict[str, Any]:
    """Create an X Article draft and optionally publish it to Everyone."""
    clean_title = _validate_title(title)
    blocks = parse_article_markdown(body_markdown)
    cover = _validate_image_path(cover_image_path)
    if cover is None:
        raise ValueError("cover_image_path is required for X Articles")
    logger.info(
        "ARTICLE start=true title_chars=%d blocks=%d publish=%s cover=%s",
        len(clean_title),
        len(blocks),
        publish,
        Path(cover).name,
    )

    with x_page() as page:
        draft_url, title_input, editor, cover_input = _create_draft(page)
        try:
            _attach_cover(page, cover_input, cover)
            title_input.fill(clean_title)
            _insert_blocks(page, editor, blocks)
            _wait_saved(page)
            _preview_article(page, clean_title, blocks)
            if not publish:
                logger.info("ARTICLE draft_complete=true")
                return {
                    "success": True,
                    "published": False,
                    "draft_url": draft_url,
                    "title": clean_title,
                }
            public_url = _publish_everyone(page, clean_title, draft_url)
            _verify_public_article(page, public_url, clean_title)
            return {
                "success": True,
                "published": True,
                "url": public_url,
                "title": clean_title,
                "audience": "Everyone",
            }
        except Exception:
            logger.exception("ARTICLE failed draft_url=%s", draft_url)
            raise


def publish_article_draft(
    draft_url: str, title: str, body_markdown: str
) -> dict[str, Any]:
    """Re-verify and publish an existing Article draft to Everyone, fail closed."""
    if not ARTICLE_EDIT_RE.match(draft_url):
        raise ValueError("draft_url must be a canonical X Article edit URL")
    clean_title = _validate_title(title)
    blocks = parse_article_markdown(body_markdown)
    with x_page() as page:
        page.goto(draft_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3_000)
        ensure_authenticated(page)
        _dismiss_cookies(page)
        _wait_for_editor(page)
        _preview_article(page, clean_title, blocks)
        public_url = _publish_everyone(page, clean_title, draft_url)
        _verify_public_article(page, public_url, clean_title)
        return {
            "success": True,
            "published": True,
            "url": public_url,
            "title": clean_title,
            "audience": "Everyone",
        }
