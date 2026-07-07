"""
Headless browser automation for canvas verification using Playwright.

Provides objective, scriptable verification of visual rendering without human judgment.
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from playwright.async_api import (
    async_playwright,
    Page,
    Browser,
    BrowserContext,
    Locator,
    TimeoutError as PlaywrightTimeoutError,
)


# Configuration
CANVAS_URL = "http://localhost:8000"
API_BASE_URL = "http://localhost:8000"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True, parents=True)


class CanvasVerifier:
    """Headless browser automation for canvas verification."""

    def __init__(self, base_url: str = CANVAS_URL, api_url: str = API_BASE_URL):
        self.base_url = base_url
        self.api_url = api_url
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

    async def __aenter__(self):
        """Start browser and navigate to canvas."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            viewport={"width": 1400, "height": 1080},
            user_agent="ADC Canvas Verification Bot/1.0"
        )
        self.page = await self.context.new_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up browser resources."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def navigate_to_canvas(self, session_id: Optional[str] = None) -> str:
        """
        Navigate to the canvas URL and extract session ID.

        Args:
            session_id: Optional session ID to use. If not provided, generates new one.

        Returns:
            The session ID being used.
        """
        if session_id is None:
            session_id = f"test-session-{uuid.uuid4().hex[:16]}"

        params = urlencode({"session_id": session_id}) if session_id else ""
        url = f"{self.base_url}/?{params}" if params else self.base_url

        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.wait_for_selector("#statusDot", timeout=5000)

        return session_id

    async def take_screenshot(self, name: str) -> Path:
        """
        Take a screenshot of the current page state.

        Args:
            name: Descriptive name for the screenshot file.

        Returns:
            Path to the saved screenshot.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{name}.png"
        filepath = SCREENSHOT_DIR / filename

        await self.page.screenshot(
            path=str(filepath),
            full_page=True,
            animations="disabled"
        )

        print(f"  📸 Screenshot saved: {filepath}")
        return filepath

    async def verify_connection_status(self, expected_status: str = "Connected") -> bool:
        """
        Verify the SSE connection status indicator.

        Args:
            expected_status: Expected status text ("Connected", "Connecting...", "Disconnected")

        Returns:
            True if status matches expected, False otherwise.
        """
        status_text = await self.page.locator("#statusText").text_content(timeout=3000)
        is_connected = status_text == expected_status

        print(f"  🔌 Connection status: {status_text} {'✓' if is_connected else '✗'}")
        return is_connected

    async def inject_test_topic(
        self,
        session_id: str,
        label: str,
        topic_type: str = "project",
        summary: str = "Test result summary",
        urgency: str = "normal",
        staleness_seconds: int = 0,
    ) -> dict:
        """
        Inject a test topic via the API.

        Args:
            session_id: Session ID to inject topic into
            label: Topic label
            topic_type: Topic type (project, research, personal, exception, compound)
            summary: Result summary
            urgency: Urgency level (critical, high, normal, low)
            staleness_seconds: How old the result is (affects staleness indicator)

        Returns:
            The created topic data.
        """
        async with httpx.AsyncClient() as client:
            # Create topic via direct DB insertion (simulating fetch+synthesize result)
            response = await client.post(
                f"{self.api_url}/api/v1/test/create-topic",
                json={
                    "session_id": session_id,
                    "label": label,
                    "type": topic_type,
                    "summary": summary,
                    "urgency": urgency,
                    "staleness_seconds": staleness_seconds,
                }
            )

            if response.status_code == 200:
                data = response.json()
                print(f"  ✓ Injected topic: {label} (type: {topic_type})")
                return data
            else:
                print(f"  ✗ Failed to inject topic: {response.status_code}")
                return {}

    async def verify_topic_card_present(self, label: str) -> bool:
        """
        Verify a topic card with the given label is present in the DOM.

        Args:
            label: Topic label to search for

        Returns:
            True if card is found, False otherwise.
        """
        try:
            card = await self.page.wait_for_selector(
                f".topic-card:has-text('{label}')",
                timeout=5000
            )
            found = card is not None
            print(f"  {'✓' if found else '✗'} Topic card found: {label}")
            return found
        except PlaywrightTimeoutError:
            print(f"  ✗ Topic card NOT found: {label}")
            return False

    async def verify_card_data_attributes(self, label: str) -> dict:
        """
        Verify data attributes and content of a topic card.

        Args:
            label: Topic label to find card by

        Returns:
            Dict with verification results for various attributes.
        """
        try:
            card = await self.page.wait_for_selector(
                f".topic-card:has-text('{label}')",
                timeout=5000
            )

            # Check topic ID attribute
            topic_id = await card.get_attribute("data-topic-id")
            has_topic_id = topic_id is not None

            # Check type badge exists
            type_badge = card.locator(".topic-type")
            has_type_badge = await type_badge.count() > 0
            type_text = await type_badge.text_content() if has_type_badge else ""

            # Check stale badge class (for old topics)
            is_stale = "stale" in (await card.get_attribute("class") or "")

            # Check urgency badge
            urgency_badge = card.locator(".urgency-badge")
            has_urgency = await urgency_badge.count() > 0
            urgency_text = await urgency_badge.text_content() if has_urgency else ""

            results = {
                "found": True,
                "has_topic_id": has_topic_id,
                "topic_id": topic_id,
                "has_type_badge": has_type_badge,
                "type_text": type_text,
                "is_stale": is_stale,
                "has_urgency_badge": has_urgency,
                "urgency_text": urgency_text,
            }

            print(f"  📋 Card data attributes for '{label}':")
            print(f"     - Topic ID: {topic_id if has_topic_id else 'MISSING'}")
            print(f"     - Type badge: {type_text if has_type_badge else 'MISSING'}")
            print(f"     - Stale: {is_stale}")
            print(f"     - Urgency: {urgency_text if has_urgency else 'MISSING'}")

            return results

        except PlaywrightTimeoutError:
            print(f"  ✗ Card not found for data attribute check: {label}")
            return {"found": False}

    async def verify_staleness_indicator(self, label: str, expected_level: str) -> bool:
        """
        Verify staleness indicator renders correctly.

        Args:
            label: Topic label
            expected_level: Expected staleness level (fresh, stale, very-stale)

        Returns:
            True if staleness indicator matches expected level.
        """
        try:
            card = await self.page.wait_for_selector(
                f".topic-card:has-text('{label}')",
                timeout=5000
            )

            # Check staleness class on card
            card_classes = await card.get_attribute("class") or ""
            has_expected_class = expected_level in card_classes

            # Check staleness indicator
            staleness_indicator = card.locator(".staleness-indicator")
            has_indicator = await staleness_indicator.count() > 0

            # Check staleness dot
            staleness_dot = staleness_indicator.locator(".staleness-dot")
            has_dot = await staleness_dot.count() > 0
            dot_classes = await staleness_dot.get_attribute("class") or ""
            has_dot_class = expected_level in dot_classes

            is_correct = (
                has_expected_class and
                has_indicator and
                has_dot and
                has_dot_class
            )

            print(f"  {'✓' if is_correct else '✗'} Staleness indicator for '{label}': expected={expected_level}, actual_class={card_classes}")

            return is_correct

        except PlaywrightTimeoutError:
            print(f"  ✗ Card not found for staleness check: {label}")
            return False

    async def verify_empty_state(self) -> bool:
        """
        Verify empty state renders when no topics exist.

        Returns:
            True if empty state is visible.
        """
        try:
            empty_state = await self.page.wait_for_selector(
                ".empty-state",
                timeout=3000
            )
            has_empty_message = "No active topics" in await empty_state.text_content()

            print(f"  {'✓' if has_empty_message else '✗'} Empty state visible")
            return has_empty_message

        except PlaywrightTimeoutError:
            print(f"  ✗ Empty state not visible (topics may be present)")
            return False

    async def simulate_connection_drop(self) -> bool:
        """
        Simulate SSE connection drop and verify reconnection.

        This simulates a network interruption and verifies:
        1. Status changes to "Disconnected"
        2. Status changes back to "Connected" after reconnection

        Returns:
            True if reconnection was successful.
        """
        print("  🔌 Simulating connection drop...")

        # Simulate network offline
        await self.page.context.set_offline(True)

        # Wait for disconnected status
        try:
            await self.page.wait_for_selector(
                "#statusDot.disconnected",
                timeout=5000
            )
            status_disconnected = await self.page.locator("#statusText").text_content()
            print(f"  ✓ Disconnection detected: {status_disconnected}")
        except PlaywrightTimeoutError:
            print(f"  ✗ Disconnection not detected")
            await self.page.context.set_offline(False)
            return False

        # Simulate network recovery
        await self.page.context.set_offline(False)

        # Wait for reconnection
        try:
            await self.page.wait_for_selector(
                "#statusDot:not(.disconnected)",
                timeout=10000
            )
            status_reconnected = await self.page.locator("#statusText").text_content()
            print(f"  ✓ Reconnection detected: {status_reconnected}")
            return True
        except PlaywrightTimeoutError:
            print(f"  ✗ Reconnection failed")
            return False

    async def verify_topic_card_count(self, expected_count: int) -> bool:
        """
        Verify the number of topic cards rendered.

        Args:
            expected_count: Expected number of cards

        Returns:
            True if count matches.
        """
        cards = await self.page.locator(".topic-card").all()
        actual_count = len(cards)
        is_correct = actual_count == expected_count

        print(f"  {'✓' if is_correct else '✗'} Topic card count: {actual_count} (expected {expected_count})")
        return is_correct

    async def verify_version_badge(self) -> bool:
        """
        Verify version badge is displayed.

        Returns:
            True if version badge is visible and non-empty.
        """
        try:
            version_badge = await self.page.wait_for_selector(
                "#versionBadge",
                timeout=3000
            )
            version_text = await version_badge.text_content()
            has_version = version_text and len(version_text) > 0

            print(f"  {'✓' if has_version else '✗'} Version badge: {version_text or 'MISSING'}")
            return has_version

        except PlaywrightTimeoutError:
            print(f"  ✗ Version badge not found")
            return False


async def run_canvas_verification():
    """
    Run comprehensive canvas verification test suite.

    This is the main entry point for canvas verification automation.
    """
    print("🚀 Starting Canvas Verification")
    print("=" * 60)

    all_passed = True

    async with CanvasVerifier() as verifier:
        # Test 1: Navigate to canvas
        print("\n[Test 1] Navigate to Canvas")
        print("-" * 60)
        session_id = await verifier.navigate_to_canvas()
        await verifier.take_screenshot("01_initial_load")
        await verifier.verify_connection_status("Connecting...")

        # Wait for connection to establish
        await verifier.page.wait_for_selector("#statusDot:not(.connecting):not(.disconnected)", timeout=10000)
        await verifier.verify_connection_status("Connected")
        await verifier.verify_version_badge()

        # Additional wait to ensure SSE connection is fully registered
        await verifier.page.wait_for_timeout(2000)

        # Test 2: Verify empty state
        print("\n[Test 2] Verify Empty State")
        print("-" * 60)
        empty_visible = await verifier.verify_empty_state()
        if empty_visible:
            await verifier.take_screenshot("02_empty_state")

        # Test 3: Inject test topics
        print("\n[Test 3] Inject Test Topics")
        print("-" * 60)

        # Fresh topic (should show "just now")
        await verifier.inject_test_topic(
            session_id=session_id,
            label="Fresh Project Topic",
            topic_type="project",
            summary="This is a fresh result",
            urgency="normal",
            staleness_seconds=30,
        )

        # Stale topic (10 minutes old, should show "10m ago" with yellow indicator)
        await verifier.inject_test_topic(
            session_id=session_id,
            label="Stale Research Topic",
            topic_type="research",
            summary="This is a stale result",
            urgency="high",
            staleness_seconds=600,  # 10 minutes
        )

        # Very stale topic (2 hours old, should show "2h ago" with red indicator)
        await verifier.inject_test_topic(
            session_id=session_id,
            label="Very Stale Exception",
            topic_type="exception",
            summary="This is very stale",
            urgency="critical",
            staleness_seconds=7200,  # 2 hours
        )

        # Wait for SSE to broadcast update and canvas to reload
        await verifier.page.wait_for_timeout(3000)
        await verifier.take_screenshot("03_with_topics")

        # Test 4: Verify topic cards are present
        print("\n[Test 4] Verify Topic Cards Present")
        print("-" * 60)

        cards_present = await verifier.verify_topic_card_count(3)
        if not cards_present:
            all_passed = False

        card1_found = await verifier.verify_topic_card_present("Fresh Project Topic")
        card2_found = await verifier.verify_topic_card_present("Stale Research Topic")
        card3_found = await verifier.verify_topic_card_present("Very Stale Exception")

        if not (card1_found and card2_found and card3_found):
            all_passed = False

        # Test 5: Verify card data attributes
        print("\n[Test 5] Verify Card Data Attributes")
        print("-" * 60)

        await verifier.verify_card_data_attributes("Fresh Project Topic")
        await verifier.verify_card_data_attributes("Stale Research Topic")
        await verifier.verify_card_data_attributes("Very Stale Exception")

        # Test 6: Verify staleness indicators
        print("\n[Test 6] Verify Staleness Indicators")
        print("-" * 60)

        fresh_correct = await verifier.verify_staleness_indicator("Fresh Project Topic", "fresh")
        stale_correct = await verifier.verify_staleness_indicator("Stale Research Topic", "stale")
        very_stale_correct = await verifier.verify_staleness_indicator("Very Stale Exception", "very-stale")

        if not (fresh_correct and stale_correct and very_stale_correct):
            all_passed = False

        # Test 7: SSE reconnection test
        print("\n[Test 7] SSE Reconnection Test")
        print("-" * 60)

        reconnection_ok = await verifier.simulate_connection_drop()
        if not reconnection_ok:
            all_passed = False

        await verifier.take_screenshot("04_after_reconnection")

        # Test 8: Verify topics persist after reconnection
        print("\n[Test 8] Verify Topics Persist After Reconnection")
        print("-" * 60)

        cards_after_reconnect = await verifier.verify_topic_card_count(3)
        if not cards_after_reconnect:
            all_passed = False

    # Final result
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print(f"📸 Screenshots saved to: {SCREENSHOT_DIR}")
    else:
        print("❌ SOME TESTS FAILED")
        print(f"📸 Screenshots saved to: {SCREENSHOT_DIR}")
        print("   Review screenshots for visual debugging")

    return all_passed


if __name__ == "__main__":
    # Check if server is running
    import httpx

    print("🔍 Checking if ADC server is running...")
    try:
        response = httpx.get(f"{CANVAS_URL}/health", timeout=2)
        if response.status_code != 200:
            print(f"❌ Server health check failed: {response.status_code}")
            print("   Start the server with:")
            print("   cd /home/coding/aide-de-camp && python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000")
            exit(1)
    except Exception as e:
        print(f"❌ Cannot reach server at {CANVAS_URL}")
        print("   Error:", e)
        print("   Start the server with:")
        print("   cd /home/coding/aide-de-camp && python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000")
        exit(1)

    print("✅ Server is running")
    print()

    # Run verification
    success = asyncio.run(run_canvas_verification())
    exit(0 if success else 1)
