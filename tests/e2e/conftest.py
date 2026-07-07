"""
Pytest fixtures for end-to-end testing.

Provides browser lifecycle management and common test utilities.
"""

import asyncio
from pathlib import Path
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode

import pytest
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


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
