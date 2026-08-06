"""
End-to-end tests for Telegram send failure logging behavior.

This test module verifies the complete flow from HTTP send failure through
logging system, ensuring:
1. First send failure produces a WARNING with error context
2. Repeated failures are rate-limited (no log spam)
3. Logs are visible at WARNING level (not DEBUG-only)
4. Different failure types get independent WARNINGs
"""

import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

import httpx

from src.telegram.fallback import TelegramFallback, get_telegram_fallback


class FakeAsyncClient:
    """Mock httpx.AsyncClient that simulates network failures."""

    def __init__(self, fail_with: Exception | None = None, status_code: int = 200):
        self.fail_with = fail_with
        self.status_code = status_code
        self.call_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, timeout=None):
        self.call_count += 1
        if self.fail_with:
            raise self.fail_with
        return FakeResponse(self.status_code, "ok" if self.status_code == 200 else "error")


class FakeResponse:
    """Mock httpx.Response."""
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def fake_httpx_client(monkeypatch):
    """Patch httpx.AsyncClient to use our fake client."""
    import src.telegram.fallback as fb_module
    client = None

    def _get_client(**kwargs):
        nonlocal client
        if client is None:
            client = FakeAsyncClient(**kwargs)
        return client

    monkeypatch.setattr(fb_module.httpx, "AsyncClient", _get_client)

    def _reset():
        nonlocal client
        client = None

    _reset._orig_client = _get_client
    return _reset


class TestE2EFirstFailureLogging:
    """End-to-end test: first HTTP send failure produces visible WARNING."""

    @pytest.mark.asyncio
    async def test_first_http_failure_logs_warning_with_context(self, caplog):
        """Simulate first send_message HTTP failure → verify WARNING with error context."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            success = await fallback.send_message(chat_id=12345, message="test")

        assert success is False, "Send should fail with bad token"

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1, "Should have at least one WARNING log"

        # Find the first failure WARNING
        first_failure_warnings = [
            r for r in warnings
            if "First Telegram send failure detected" in r.message
        ]
        assert len(first_failure_warnings) == 1, "Should have exactly one first-failure WARNING"

        warning_msg = first_failure_warnings[0].message
        assert "Error type:" in warning_msg, "WARNING should include error type label"
        assert "Error:" in warning_msg, "WARNING should include error message label"
        assert "rate-limited" in warning_msg, "WARNING should mention rate-limiting"

    @pytest.mark.asyncio
    async def test_repeated_http_failures_rate_limited(self, caplog):
        """Simulate multiple HTTP failures → verify only one WARNING, rest rate-limited."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            # First failure
            await fallback.send_message(chat_id=12345, message="test 1")

        warning_count_before = len([r for r in caplog.records if r.levelname == "WARNING"])
        assert warning_count_before >= 1, "First failure should produce WARNING"

        caplog.clear()

        with caplog.at_level("DEBUG"):
            # Immediate repeated failures - should be rate-limited
            for i in range(2, 11):
                await fallback.send_message(chat_id=12345, message=f"test {i}")

        # Verify no additional WARNINGs from repeated failures
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 0, "Repeated failures should not produce additional WARNINGs"

        # Verify failure count incremented correctly
        assert fallback._failure_count == 10, f"Should have 10 failures, got {fallback._failure_count}"

    @pytest.mark.asyncio
    async def test_different_failure_types_logged_independently(self, caplog):
        """Simulate different HTTP error types → verify independent WARNINGs."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            # First failure type
            success1 = await fallback.send_message(chat_id=12345, message="test 1")
            assert success1 is False

        first_warning_count = len([r for r in caplog.records if r.levelname == "WARNING"])

        caplog.clear()

        with caplog.at_level("WARNING"):
            # Simulate a different failure by manually calling _handle_send_failure
            # with a different error type
            await fallback._handle_send_failure(
                error=TimeoutError("Request timeout"),
                error_context="Network timeout"
            )

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1, "Different failure type should produce new WARNING"

        # Verify one of the warnings mentions the new failure type
        new_type_warnings = [r for r in warnings if "New Telegram send failure type" in r.message]
        assert len(new_type_warnings) >= 1, "Should have WARNING for new failure type"

        # Verify distinct failure types tracked
        assert len(fallback._seen_failure_types) >= 2, \
            f"Should track at least 2 failure types, got {len(fallback._seen_failure_types)}"


class TestE2EVisibilityAtWarningLevel:
    """Verify logs are visible at WARNING level, not hidden in DEBUG."""

    @pytest.mark.asyncio
    async def test_warning_visible_at_warning_level(self, caplog):
        """First failure WARNING must be visible when capturing at WARNING level."""
        fallback = TelegramFallback(bot_token="test_token")

        # Capture only WARNING and above (no DEBUG)
        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="test")

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1, "WARNING must be visible at WARNING level"

    @pytest.mark.asyncio
    async def test_no_debug_spam_from_sustained_failures(self, caplog):
        """Sustained outage should not produce DEBUG spam."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("DEBUG"):
            # First failure → WARNING
            await fallback.send_message(chat_id=12345, message="first")

            # Sustained failures → rate-limited (no DEBUG until cooldown elapses)
            for i in range(50):
                await fallback.send_message(chat_id=12345, message=f"failure {i}")

        # Filter only telegram.fallback logs (exclude httpcore/httpx DEBUG logs)
        warnings = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        debugs = [r for r in caplog.records if r.levelname == "DEBUG" and "telegram.fallback" in r.name]

        assert len(warnings) == 1, "Only one WARNING for first failure"
        assert len(debugs) == 0, "No DEBUG spam within cooldown window"


class TestE2ESendMethodsFailureLogging:
    """Verify all send methods properly log failures."""

    @pytest.mark.asyncio
    async def test_send_message_failure_logged(self, caplog):
        """send_message failure should log WARNING."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            success = await fallback.send_message(chat_id=12345, message="test")

        assert success is False
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1

    @pytest.mark.asyncio
    async def test_send_exception_failure_logged(self, caplog, monkeypatch):
        """send_exception failure should log WARNING when chat_id configured."""
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", "12345")
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            success = await fallback.send_exception(
                session_id="test-session",
                exception={"title": "Test exception", "urgency": "high"}
            )

        assert success is False
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1

    @pytest.mark.asyncio
    async def test_send_workload_summary_failure_logged(self, caplog, monkeypatch):
        """send_workload_summary failure should log WARNING when chat_id configured."""
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", "12345")
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            success = await fallback.send_workload_summary(
                session_id="test-session",
                summary={"pending_intents": 1}
            )

        assert success is False
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1


class TestE2EStatusAPIExposure:
    """Verify status endpoint exposes failure logging state."""

    @pytest.mark.asyncio
    async def test_status_shows_failure_count(self):
        """Status should include failure_count."""
        fallback = TelegramFallback(bot_token="test_token")

        await fallback.send_message(chat_id=12345, message="test")
        await fallback.send_message(chat_id=12345, message="test2")

        status = fallback.get_status()
        assert status["failure_count"] == 2
        assert status["has_logged_first_failure"] is True
        assert status["first_failure_timestamp"] is not None
        assert status["last_failure_timestamp"] is not None

    @pytest.mark.asyncio
    async def test_status_shows_distinct_failure_types(self):
        """Status should track distinct failure types."""
        fallback = TelegramFallback(bot_token="test_token")

        await fallback._handle_send_failure(error=ConnectionError("conn error"))
        await fallback._handle_send_failure(error=TimeoutError("timeout"))

        status = fallback.get_status()
        assert status["distinct_failure_types"] == 2
        assert "ConnectionError" in status["seen_failure_types"]
        assert "TimeoutError" in status["seen_failure_types"]


@pytest.mark.asyncio
async def test_end_to_end_failure_flow(caplog):
    """
    Complete end-to-end simulation of a Telegram outage:
    1. Service starts, first send fails → WARNING
    2. Continued sends fail → rate-limited (no spam)
    3. Different error appears → independent WARNING
    4. Status endpoint reflects all failures
    """
    # Create fallback instance
    fallback = TelegramFallback(bot_token="bad_token", chat_id=12345)

    with caplog.at_level("DEBUG"):
        # Step 1: First send failure → WARNING
        await fallback.send_message(chat_id=12345, message="test 1")
        warning_logs = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warning_logs) >= 1, "Step 1 failed: No WARNING logged"

        # Step 2: Repeated failures → rate-limited
        warnings_count_before = len(warning_logs)
        for i in range(2, 11):
            await fallback.send_message(chat_id=12345, message=f"test {i}")

        # Check that we didn't get additional WARNINGs from repeats
        warning_logs = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warning_logs) == warnings_count_before, "Step 2 failed: Repeated failures produced additional WARNINGs"

        # Step 3: Different failure type → independent WARNING
        warnings_before_step3 = len([r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name])
        await fallback._handle_send_failure(error=TimeoutError("network timeout"))

        new_warnings = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(new_warnings) > warnings_before_step3, "Step 3 failed: New type didn't produce WARNING"

        # Step 4: Verify status endpoint
        status = fallback.get_status()
        assert status["failure_count"] == 11, f"Step 4 failed: Expected 11 failures, got {status['failure_count']}"
        assert status["has_logged_first_failure"] is True
        assert status["distinct_failure_types"] >= 2

        print("✅ End-to-end test passed: All failure logging steps verified")


if __name__ == "__main__":
    # Run the end-to-end test standalone
    import asyncio
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
