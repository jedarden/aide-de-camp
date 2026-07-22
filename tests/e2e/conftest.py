"""
Pytest fixtures for end-to-end testing.

Provides browser lifecycle management and common test utilities.
"""

import asyncio
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urlencode

import pytest

# Make Playwright importable + its bundled browser launchable on NixOS BEFORE we
# import playwright below. On NixOS the greenlet C-ext can't load libstdc++.so.6
# (so `import playwright` fails outright) and the chromium subprocess is missing
# ~22 FHS libs. This preloads libstdc++ (RTLD_GLOBAL) and dynamically resolves
# the rest from /nix/store into LD_LIBRARY_PATH. See nixos_browser_bootstrap.py.
from tests.e2e.nixos_browser_bootstrap import bootstrap as _bootstrap_browser_env

_bootstrap_browser_env()

try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright
    _HAS_PLAYWRIGHT = True
except Exception:  # playwright is optional — only browser tests need it
    # Catch broadly (not just ModuleNotFoundError): a partial/broken install can
    # raise ImportError instead — e.g. its `greenlet` C-extension failing to
    # load libstdc++.so.6 on NixOS. In any such case playwright is unusable, so
    # treat it as absent: the `browser` fixture skips, and the hermetic (non-
    # browser) e2e tests keep running instead of crashing collection.
    async_playwright = None  # type: ignore[assignment]
    Browser = BrowserContext = Page = None  # type: ignore[assignment]
    _HAS_PLAYWRIGHT = False


# Configuration
CANVAS_URL = "http://localhost:8000"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True, parents=True)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def browser() -> AsyncGenerator[Browser, None]:
    """Launch Playwright browser instance."""
    if not _HAS_PLAYWRIGHT:
        pytest.skip("playwright not installed — install with: pip install playwright && playwright install chromium")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest.fixture(scope="function")
async def browser_context(browser: Browser) -> AsyncGenerator[BrowserContext, None]:
    """Create browser context with custom viewport."""
    context = await browser.new_context(
        viewport={"width": 1400, "height": 1080},
        user_agent="ADC Canvas Test/1.0"
    )
    yield context
    await context.close()


@pytest.fixture(scope="function")
async def page(browser_context: BrowserContext) -> AsyncGenerator[Page, None]:
    """Create new browser page."""
    page = await browser_context.new_page()
    yield page
    await page.close()


@pytest.fixture(scope="function")
async def canvas_page(page: Page) -> AsyncGenerator[Page, None]:
    """
    Navigate to canvas and return page instance.

    This fixture waits for the page to load and the SSE connection
    status indicator to be present before yielding the page.
    """
    # Navigate to canvas
    await page.goto(CANVAS_URL, wait_until="domcontentloaded")

    # Wait for key elements to be present
    await page.wait_for_selector("#statusDot", timeout=5000)

    yield page


@pytest.fixture(scope="function")
async def canvas_page_with_session(page: Page) -> AsyncGenerator[tuple[Page, str], None]:
    """
    Navigate to canvas with a test session ID and return page with session_id.

    This is useful for tests that need to know the session ID for API calls.
    """
    import uuid

    session_id = f"test-session-{uuid.uuid4().hex[:16]}"
    params = urlencode({"session_id": session_id})
    url = f"{CANVAS_URL}/?{params}"

    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_selector("#statusDot", timeout=5000)

    yield page, session_id


@pytest.fixture(scope="function")
async def injector():
    """A live TestDataInjector against the running server, with teardown.

    Every session it creates is deleted on exit, so browser tests can inject
    topics freely without polluting the real session.db. Yields None (and skips)
    if the server isn't reachable.
    """
    if not is_server_running():
        pytest.skip("ADC server is not running on localhost:8000")
    from tests.e2e.inject import TestDataInjector

    async with TestDataInjector(base_url=CANVAS_URL) as inj:
        yield inj


@pytest.fixture(scope="function")
async def canvas_session(page: Page, injector):
    """Canvas pointed at a freshly-injected session: yields (page, session_id, injector).

    Combines :func:`canvas_page_with_session`'s navigation with the live
    :fixture:`injector`, using the injector's own (trackable, teardown-safe)
    session id as the URL param. Use this for browser tests that inject topics
    via the API and then assert on the rendered DOM.
    """
    import uuid

    session_id = f"test-inject-e2e-{uuid.uuid4().hex[:12]}"
    await injector.create_session(session_id)

    params = urlencode({"session_id": session_id})
    await page.goto(f"{CANVAS_URL}/?{params}", wait_until="domcontentloaded")
    # Wait until SSE has opened (status flips off "Connecting...") so injected
    # cards are delivered over a live push channel, not a stale fetch.
    await page.wait_for_selector("#statusDot", timeout=5000)
    try:
        await page.wait_for_function(
            "() => document.getElementById('statusText').textContent !== 'Connecting...'",
            timeout=5000,
        )
    except Exception:
        pass  # connecting-then-connected is racy on slow CI; #statusDot is enough

    yield page, session_id, injector


def take_screenshot(page: Page, name: str) -> Path:
    """
    Take a screenshot of the current page state.

    Args:
        page: Playwright page instance
        name: Descriptive name for the screenshot file

    Returns:
        Path to the saved screenshot
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{name}.png"
    filepath = SCREENSHOT_DIR / filename

    # Synchronously save screenshot (we're in sync context)
    asyncio.create_task(
        page.screenshot(path=str(filepath), full_page=True, animations="disabled")
    )

    return filepath


async def screenshot(page: Page, name: str, *, full_page: bool = True) -> Path:
    """Awaited screenshot helper for async tests.

    The legacy ``take_screenshot`` fires ``asyncio.create_task`` from a sync
    context and never awaits it, so the file may not be written before the test
    reads it. Tests that assert on the screenshot existing should use this
    awaited version instead. Returns the saved file path.
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = SCREENSHOT_DIR / f"{timestamp}_{name}.png"
    await page.screenshot(
        path=str(filepath), full_page=full_page, animations="disabled"
    )
    return filepath


# Health check helper
def is_server_running() -> bool:
    """Check if the ADC server is running."""
    import httpx

    try:
        response = httpx.get(f"{CANVAS_URL}/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


# Skip tests if server is not running
pytestmark = pytest.mark.skipif(
    not is_server_running(),
    reason="ADC server is not running on localhost:8000"
)
