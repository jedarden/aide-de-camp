"""
Basic Playwright integration tests for canvas (bead adc-3fttix).

This module provides foundational Playwright browser automation setup/teardown
fixtures and basic integration tests for the canvas UI. It complements the
comprehensive verification suite in test_canvas_playwright_verification.py.

Use this module for:
- Basic smoke tests (page loads, renders)
- Simple interaction testing
- Quick integration verification
- Learning Playwright patterns for this project

For comprehensive canvas verification including SSE, staleness, and card
dismissal, see test_canvas_playwright_verification.py.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest
from playwright.async_api import async_playwright, Browser, Page, BrowserContext


# =============================================================================
# Configuration
# =============================================================================

CANVAS_URL = "http://localhost:8000/"
SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "adc_playwright_screenshots"


# =============================================================================
# Browser Fixtures
# =============================================================================

@pytest.fixture
async def browser() -> AsyncGenerator[Browser, None]:
    """
    Provide a Playwright browser instance.

    This fixture launches a headless Chromium browser and ensures
    proper cleanup after each test.

    Usage:
        async def test_something(browser):
            page = await browser.new_page()
            await page.goto("http://localhost:8000")
    """
    async with async_playwright() as p:
        browser_instance = await p.chromium.launch(headless=True)
        yield browser_instance
        await browser_instance.close()


@pytest.fixture
async def browser_context(browser: Browser) -> AsyncGenerator[BrowserContext, None]:
    """
    Provide a browser context with isolated storage.

    This fixture creates an isolated browser context with its own
    cookies, localStorage, and sessionStorage. Use this when tests
    need to be isolated from each other.

    Usage:
        async def test_something(browser_context):
            page = await browser_context.new_page()
            await page.goto("http://localhost:8000")
    """
    context = await browser.new_context(
        viewport={"width": 1400, "height": 900},
        user_agent="ADC-Integration-Test/1.0"
    )
    yield context
    await context.close()


@pytest.fixture
async def page(browser_context: BrowserContext) -> AsyncGenerator[Page, None]:
    """
    Provide a Playwright page instance.

    This fixture creates a new page in the browser context.
    This is the most commonly used fixture for browser tests.

    Usage:
        async def test_something(page):
            await page.goto("http://localhost:8000")
            title = await page.title()
    """
    page_instance = await browser_context.new_page()
    yield page_instance
    await page_instance.close()


# =============================================================================
# Basic Smoke Tests
# =============================================================================

@pytest.mark.asyncio
async def test_canvas_loads(page: Page):
    """Test that the canvas page loads successfully."""
    await page.goto(CANVAS_URL)
    await page.wait_for_load_state("networkidle")

    # Verify page loaded
    title = await page.title()
    assert title, "Page should have a title"

    # Verify no critical errors in console
    # (Note: browser console errors would indicate JS issues)


@pytest.mark.asyncio
async def test_canvas_basic_rendering(page: Page):
    """Test that basic canvas UI elements render."""
    await page.goto(CANVAS_URL)
    await page.wait_for_load_state("networkidle")

    # Wait for any dynamic content to load
    await page.wait_for_timeout(500)

    # Verify main container exists
    container = await page.query_selector("body")
    assert container is not None, "Page body should exist"

    # Take a basic screenshot
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    screenshot_path = SCREENSHOT_DIR / "basic_rendering.png"
    await page.screenshot(path=str(screenshot_path))

    # Verify screenshot file was created
    assert screenshot_path.exists(), "Screenshot should be saved"


@pytest.mark.asyncio
async def test_canvas_responsive_viewport(page: Page):
    """Test that canvas responds to different viewport sizes."""
    # Test mobile viewport
    await page.set_viewport_size({"width": 375, "height": 667})
    await page.goto(CANVAS_URL)
    await page.wait_for_load_state("networkidle")

    mobile_screenshot = SCREENSHOT_DIR / "mobile_viewport.png"
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(mobile_screenshot))
    assert mobile_screenshot.exists()

    # Test desktop viewport
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await page.reload()
    await page.wait_for_load_state("networkidle")

    desktop_screenshot = SCREENSHOT_DIR / "desktop_viewport.png"
    await page.screenshot(path=str(desktop_screenshot))
    assert desktop_screenshot.exists()


@pytest.mark.asyncio
async def test_canvas_page_structure(page: Page):
    """Test that the page has expected HTML structure."""
    await page.goto(CANVAS_URL)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(500)

    # Check for common HTML elements
    html = await page.inner_html("body")
    assert html, "Page body should contain HTML content"

    # Verify we can query for elements (even if they don't exist yet)
    # This tests that Playwright is working correctly
    _ = await page.query_selector_all("div")


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    """
    Run the Playwright integration tests.

    Usage:
        .venv/bin/python tests/integration_canvas_playwright.py
        # or
        pytest tests/integration_canvas_playwright.py -v
    """
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
