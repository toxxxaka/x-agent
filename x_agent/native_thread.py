"""Native X composer thread publisher with sanitized diagnostics."""
from collections.abc import Iterable

from playwright.sync_api import Locator, Page

from .browser import ensure_authenticated, x_page
from .debug import logger

COMPOSE_URL = "https://x.com/compose/post"
FAILURE_SCREENSHOT = "/var/log/x-agent/native-thread-failure.png"


def _visible(locator: Locator, name: str) -> Locator:
    count = locator.count()
    logger.info("native_thread selector=%s matches=%d", name, count)
    for index in range(count):
        candidate = locator.nth(index)
        if candidate.is_visible():
            logger.info("native_thread selector=%s visible_index=%d", name, index)
            return candidate
    raise RuntimeError(f"no visible element for {name}; {count} matches")


def create_native_thread(posts: Iterable[str]) -> dict:
    items = list(posts)
    if not items or any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError("posts must contain non-empty strings")

    with x_page() as page:
        responses: list[str] = []

        def record_response(response) -> None:
            if "CreateTweet" in response.url:
                responses.append(str(response.status))
                logger.info("native_thread CreateTweet status=%d", response.status)

        page.on("response", record_response)
        try:
            page.goto(COMPOSE_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3_000)
            ensure_authenticated(page)
            logger.info("native_thread start posts=%d page=%s", len(items), page.url.split("?")[0])

            for index, text in enumerate(items):
                editor = _visible(
                    page.locator(f'[data-testid="tweetTextarea_{index}"][contenteditable="true"]'),
                    f"tweetTextarea_{index}",
                )
                editor.fill(text)
                logger.info("native_thread editor_filled index=%d chars=%d", index, len(text))
                if index < len(items) - 1:
                    add_button = _visible(page.locator('[data-testid="addButton"]'), "addButton")
                    logger.info("native_thread add_button disabled=%s", add_button.is_disabled())
                    add_button.click()
                    page.wait_for_timeout(1_000)

            publish = _visible(page.locator('[data-testid="tweetButton"]'), "tweetButton")
            logger.info(
                "native_thread publish_button disabled=%s label=%s",
                publish.is_disabled(),
                publish.inner_text().strip(),
            )
            if publish.is_disabled():
                raise RuntimeError("X disabled the Post all button")
            publish.click()
            logger.info("native_thread publish_clicked")
            page.wait_for_timeout(8_000)
            logger.info("native_thread complete create_tweet_responses=%s", ",".join(responses) or "none")
            if len(responses) < len(items):
                raise RuntimeError(f"X returned {len(responses)} CreateTweet responses for {len(items)} posts")
            return {"success": True, "posts": len(items), "create_tweet_responses": len(responses)}
        except Exception:
            logger.exception("native_thread failed")
            try:
                page.screenshot(path=FAILURE_SCREENSHOT, full_page=True)
                logger.info("native_thread failure_screenshot=%s", FAILURE_SCREENSHOT)
            except Exception:
                logger.exception("native_thread failure screenshot could not be saved")
            raise
