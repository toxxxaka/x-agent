import os
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .cookies import load_cookies

CHROMIUM_PATH = os.environ.get("X_AGENT_CHROMIUM", "/snap/bin/chromium")
LOCK_FILE = Path(os.environ.get("X_AGENT_LOCK_FILE", "/var/lock/x-agent.lock"))


@contextmanager
def x_page():
    """Yield one authenticated headless X page, serializing browser actions."""
    import fcntl

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another X publishing action is already running") from exc
        with sync_playwright() as playwright:
            browser: Browser = playwright.chromium.launch(
                executable_path=CHROMIUM_PATH,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context: BrowserContext = browser.new_context()
            try:
                context.add_cookies(load_cookies())
                yield context.new_page()
            finally:
                context.close()
                browser.close()


def ensure_authenticated(page: Page) -> None:
    if "/i/flow/login" in page.url:
        raise RuntimeError("X session is not authenticated; refresh x_cookies.json")
