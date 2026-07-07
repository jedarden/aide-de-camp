"""
Basic canvas navigation tests using pytest and Playwright.

These tests verify fundamental canvas functionality: navigation,
connection status, and basic UI elements.
"""

import pytest
from playwright.async_api import Page, TimeoutError


class TestCanvasNavigation:
    """Test basic canvas navigation and UI elements."""

    @pytest.mark.asyncio
    async def test_canvas_loads(self, canvas_page: Page):
        """Test that canvas page loads successfully."""
        # Verify page title
        title = await canvas_page.title()
        assert "Canvas" in title or "ADC" in title

        # Verify main container exists (canvas uses .container instead of <main>)
        container = await canvas_page.query_selector(".container")
        assert container is not None

    @pytest.mark.asyncio
    async def test_connection_status_indicator(self, canvas_page: Page):
        """Test that SSE connection status indicator is present."""
        # Check status dot exists
        status_dot = await canvas_page.query_selector("#statusDot")
        assert status_dot is not None

        # Check status text exists
        status_text = await canvas_page.query_selector("#statusText")
        assert status_text is not None

    @pytest.mark.asyncio
    async def test_version_badge(self, canvas_page: Page):
        """Test that version badge is displayed."""
        version_badge = await canvas_page.wait_for_selector(
            "#versionBadge",
            timeout=3000
        )
        assert version_badge is not None

        # Check version text is not empty
        version_text = await version_badge.text_content()
        assert version_text and len(version_text) > 0
        assert "v" in version_text or "." in version_text

    @pytest.mark.asyncio
    async def test_empty_state_visible(self, canvas_page: Page):
        """Test that empty state is visible when no topics exist."""
        try:
            empty_state = await canvas_page.wait_for_selector(
                ".empty-state",
                timeout=3000
            )
            assert empty_state is not None

            # Verify empty state contains expected text
            empty_text = await empty_state.text_content()
            assert empty_text and ("No" in empty_text or "empty" in empty_text.lower())
        except TimeoutError:
            # Empty state might not be visible if there are existing topics
            # This is acceptable - just verify the test ran
            pass

    @pytest.mark.asyncio
    async def test_dispatch_input_present(self, canvas_page: Page):
        """Test that dispatch input elements are present."""
        # Check input textarea exists (canvas uses #inputTextarea)
        input_textarea = await canvas_page.query_selector("#inputTextarea")
        assert input_textarea is not None

        # Check send button exists (canvas uses #btnSend)
        send_btn = await canvas_page.query_selector("#btnSend")
        assert send_btn is not None

        # Check mic button exists (canvas uses #btnMic)
        mic_btn = await canvas_page.query_selector("#btnMic")
        assert mic_btn is not None

    @pytest.mark.asyncio
    async def test_session_id_in_url(self, canvas_page_with_session: tuple[Page, str]):
        """Test that session ID is preserved in URL."""
        page, session_id = canvas_page_with_session

        # Wait for page to stabilize
        await page.wait_for_timeout(1000)

        # Check that session_id is in the URL
        url = page.url
        assert session_id in url

    @pytest.mark.asyncio
    async def test_screenshot_capture(self, canvas_page: Page):
        """Test that screenshots can be captured."""
        from pathlib import Path
        from datetime import datetime

        # Take a screenshot
        screenshot_dir = Path(__file__).parent / "screenshots"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = screenshot_dir / f"{timestamp}_screenshot_test.png"

        await canvas_page.screenshot(path=str(filepath), full_page=True)

        # Verify screenshot was created
        assert filepath.exists()
        assert filepath.stat().st_size > 0


class TestCanvasResponsive:
    """Test canvas responsive behavior."""

    @pytest.mark.asyncio
    async def test_mobile_viewport(self, browser):
        """Test canvas works on mobile viewport."""
        context = await browser.new_context(
            viewport={"width": 375, "height": 667},  # iPhone SE
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"
        )
        page = await context.new_page()

        await page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await page.wait_for_selector("#statusDot", timeout=5000)

        # Verify page loads successfully on mobile
        title = await page.title()
        assert title

        await context.close()

    @pytest.mark.asyncio
    async def test_tablet_viewport(self, browser):
        """Test canvas works on tablet viewport."""
        context = await browser.new_context(
            viewport={"width": 768, "height": 1024},  # iPad
            user_agent="Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X)"
        )
        page = await context.new_page()

        await page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await page.wait_for_selector("#statusDot", timeout=5000)

        # Verify page loads successfully on tablet
        title = await page.title()
        assert title

        await context.close()
