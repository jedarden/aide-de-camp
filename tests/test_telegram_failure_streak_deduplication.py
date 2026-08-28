"""
Test deduplication during consecutive failure streak.

This test verifies that multiple consecutive failures only log one WARNING,
with each subsequent failure being tracked internally but not producing
additional WARNING logs.

Acceptance Criteria:
- First failure logs exactly one WARNING
- Subsequent failures (2nd, 3rd, 4th, 5th) log NO WARNING
- No WARNING spam in logs during failure streak
- Each failure is still tracked internally (just not logged)
"""

import asyncio
import logging
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx

from src.telegram.fallback import TelegramFallback


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
    """Patch httpx.AsyncClient to use our fake client that always fails."""
    import src.telegram.fallback as fb_module
    client = None

    def _get_client(**kwargs):
        nonlocal client
        if client is None:
            # Configure client to always fail with ConnectionError
            client = FakeAsyncClient(fail_with=ConnectionError("Simulated network failure"))
        return client

    monkeypatch.setattr(fb_module.httpx, "AsyncClient", _get_client)

    def _reset():
        nonlocal client
        client = None

    _reset._orig_client = _get_client
    return _reset


@pytest.mark.asyncio
async def test_failure_streak_deduplication_five_failures(caplog, fake_httpx_client):
    """
    Test that 5 consecutive failures only produce one WARNING.

    This test validates the core deduplication behavior:
    1. Start with bridge reachable (simulated by fresh TelegramFallback instance)
    2. Trigger first failure (should log WARNING)
    3. Trigger 4 additional consecutive failures
    4. Verify that only the first failure logged a WARNING
    """
    # Create fresh TelegramFallback instance (bridge starts reachable by default)
    fallback = TelegramFallback(bot_token="test_token")

    # Verify bridge is initially reachable
    assert fallback._state_tracker.is_reachable, "Bridge should start reachable"

    # Capture all logs at WARNING level
    with caplog.at_level("WARNING"):
        # First failure - should log WARNING
        success_1 = await fallback.send_message(chat_id=12345, message="Failure 1")
        assert success_1 is False, "First send should fail"

        # Verify WARNING was logged for first failure
        warnings_after_first = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warnings_after_first) == 1, f"Expected exactly 1 WARNING after first failure, got {len(warnings_after_first)}"

        # Verify WARNING message contains expected content
        warning_msg = warnings_after_first[0].message
        assert "Telegram bridge unreachable: send failed" in warning_msg, "WARNING should mention bridge unreachable"
        assert "Error:" in warning_msg, "WARNING should include error context"

        # Store warning count for comparison
        warning_count_after_first = len(warnings_after_first)

        # Trigger 4 additional consecutive failures (failures 2-5)
        for i in range(2, 6):  # failures 2, 3, 4, 5
            success = await fallback.send_message(chat_id=12345, message=f"Failure {i}")
            assert success is False, f"Failure {i} should fail"

        # Verify NO additional WARNINGs were logged for failures 2-5
        all_warnings = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(all_warnings) == warning_count_after_first, \
            f"Expected no additional WARNINGs after first failure. Started with {warning_count_after_first}, got {len(all_warnings)}"

    # ACCEPTANCE CRITERIA: First failure logs exactly one WARNING
    assert len(all_warnings) == 1, "Acceptance criteria failed: First failure should log exactly one WARNING"

    # ACCEPTANCE CRITERIA: Subsequent failures (2nd, 3rd, 4th, 5th) log NO WARNING
    # We verified this above - warning_count_after_first equals final warning_count

    # ACCEPTANCE CRITERIA: Each failure is still tracked internally
    assert fallback._failure_count == 5, f"Expected 5 failures tracked, got {fallback._failure_count}"

    # Verify state tracker also tracks the failures
    assert fallback._state_tracker.failure_count == 5, f"Expected state tracker to count 5 failures, got {fallback._state_tracker.failure_count}"

    # Verify first failure flag is set
    assert fallback._has_logged_first_failure is True, "First failure flag should be set"

    # Verify bridge is marked as unreachable
    assert fallback._state_tracker.is_reachable is False, "Bridge should be marked unreachable after failures"

    # Verify the state tracker's last failure logged flag
    assert fallback._state_tracker._last_failure_logged is True, "State tracker should mark first failure as logged"

    print("✅ All acceptance criteria validated:")
    print(f"   - First failure logged exactly 1 WARNING")
    print(f"   - Subsequent failures (2-5) logged 0 WARNINGs")
    print(f"   - No WARNING spam during failure streak")
    print(f"   - All 5 failures tracked internally (failure_count={fallback._failure_count})")


@pytest.mark.asyncio
async def test_failure_streak_deduplication_three_failures(caplog, fake_httpx_client):
    """
    Test that 3 consecutive failures only produce one WARNING.

    This is a minimal test to verify deduplication with the minimum
    required consecutive failures (3 total per task requirements).
    """
    fallback = TelegramFallback(bot_token="test_token")

    with caplog.at_level("WARNING"):
        # First failure - should log WARNING
        await fallback.send_message(chat_id=12345, message="Failure 1")

        warnings_after_first = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warnings_after_first) == 1, "First failure should log WARNING"

        # Trigger 2 additional consecutive failures (failures 2-3)
        await fallback.send_message(chat_id=12345, message="Failure 2")
        await fallback.send_message(chat_id=12345, message="Failure 3")

        # Verify NO additional WARNINGs
        all_warnings = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(all_warnings) == 1, "Only first failure should produce WARNING"

    # Verify all failures tracked
    assert fallback._failure_count == 3, "All 3 failures should be tracked"

    print("✅ Deduplication verified with 3 consecutive failures")


@pytest.mark.asyncio
async def test_failure_streak_internal_state_tracking(caplog, fake_httpx_client):
    """
    Test that internal state is correctly maintained during failure streak.

    Verifies that while WARNING deduplication prevents log spam, all failures
    are properly tracked in internal state.
    """
    fallback = TelegramFallback(bot_token="test_token")

    # Get initial status
    status_before = fallback.get_status()
    assert status_before["failure_count"] == 0, "Should start with zero failures"
    assert status_before["has_logged_first_failure"] is False, "Should not have logged first failure yet"

    with caplog.at_level("WARNING"):
        # Trigger 5 consecutive failures
        for i in range(1, 6):
            await fallback.send_message(chat_id=12345, message=f"Failure {i}")

    # Verify internal state reflects all failures
    status_after = fallback.get_status()
    assert status_after["failure_count"] == 5, "Status should show 5 failures"
    assert status_after["has_logged_first_failure"] is True, "Should have logged first failure"
    assert status_after["first_failure_timestamp"] is not None, "Should have first failure timestamp"
    assert status_after["last_failure_timestamp"] is not None, "Should have last failure timestamp"

    # Verify state tracker internal state
    assert fallback._state_tracker.failure_count == 5, "State tracker should count 5 failures"
    assert fallback._state_tracker._last_failure_logged is True, "State tracker should mark first failure logged"
    assert fallback._state_tracker.last_failure_time is not None, "State tracker should have last failure time"

    # Verify failure summary
    summary = fallback._state_tracker.get_failure_summary()
    assert "unreachable" in summary.lower(), "Summary should indicate unreachable"
    assert "5" in summary or "five" in summary.lower(), "Summary should mention 5 failures"

    print("✅ Internal state tracking verified:")
    print(f"   - failure_count: {status_after['failure_count']}")
    print(f"   - has_logged_first_failure: {status_after['has_logged_first_failure']}")
    print(f"   - Bridge summary: {summary}")


@pytest.mark.asyncio
async def test_failure_streak_no_warning_spam(caplog, fake_httpx_client):
    """
    Test that sustained failure streak produces no WARNING spam.

    This test goes beyond the minimum 5 failures to verify that the
    deduplication holds even with many more failures (20 total).
    """
    fallback = TelegramFallback(bot_token="test_token")

    with caplog.at_level("WARNING"):
        # Trigger 20 consecutive failures
        for i in range(1, 21):
            await fallback.send_message(chat_id=12345, message=f"Failure {i}")

    # Verify only one WARNING total
    all_warnings = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
    assert len(all_warnings) == 1, f"Expected 1 WARNING for 20 failures, got {len(all_warnings)}"

    # Verify all failures tracked
    assert fallback._failure_count == 20, f"All 20 failures should be tracked, got {fallback._failure_count}"

    print("✅ No WARNING spam verified with 20 consecutive failures")


if __name__ == "__main__":
    # Run the tests standalone
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
