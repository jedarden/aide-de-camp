"""
Test state reset after successful send.

This test verifies that after a successful send, the failure state resets properly.
When the bridge becomes reachable after being unreachable, the internal state
should reset and a new failure streak should log a new WARNING.

Acceptance Criteria:
- Successful send calls `mark_as_reachable()`
- Internal failure state is cleared/reset
- New failure after success logs a new WARNING (proves state reset)
- State machine transitions: failure streak → success → new failure streak
"""

import asyncio
import logging
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.telegram.fallback import TelegramFallback


class MockAsyncClient:
    """Mock httpx.AsyncClient that can simulate success or failure."""

    def __init__(self, should_succeed: bool = False, status_code: int = 200):
        self.should_succeed = should_succeed
        self.status_code = status_code
        self.call_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, timeout=None):
        self.call_count += 1
        if not self.should_succeed:
            raise ConnectionError("Simulated network failure")
        return MockResponse(self.status_code, "ok")


class MockResponse:
    """Mock httpx.Response."""
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def mock_httpx_client(monkeypatch):
    """Patch httpx.AsyncClient to use our controllable mock client."""
    import src.telegram.fallback as fb_module

    client_instance = None

    def _get_client(**kwargs):
        nonlocal client_instance
        if client_instance is None:
            # Start with failing client (will be updated later)
            client_instance = MockAsyncClient(should_succeed=False)
        return client_instance

    monkeypatch.setattr(fb_module.httpx, "AsyncClient", _get_client)

    def set_should_succeed(should_succeed: bool):
        """Update whether the mock client should succeed or fail."""
        nonlocal client_instance
        if client_instance:
            client_instance.should_succeed = should_succeed

    return set_should_succeed


@pytest.mark.asyncio
async def test_state_reset_after_successful_send(caplog, mock_httpx_client):
    """
    Test that state resets properly after a successful send.

    This test verifies the complete lifecycle:
    1. Start with bridge reachable
    2. Trigger failures (creates failure streak)
    3. Verify WARNING is logged for first failure
    4. Simulate successful send (bridge becomes reachable)
    5. Verify `mark_as_reachable()` is called and state is reset
    6. Trigger a new failure
    7. Verify a new WARNING is logged (proves state was reset)
    """
    # Create fresh TelegramFallback instance
    fallback = TelegramFallback(bot_token="test_token", chat_id=12345)

    # ACCEPTANCE CRITERIA: Bridge starts reachable
    assert fallback._state_tracker.is_reachable is True, "Bridge should start reachable"
    assert fallback._state_tracker.failure_count == 0, "Should start with zero failures"

    with caplog.at_level("WARNING"):
        # STEP 1: Create initial failure streak
        mock_httpx_client(False)  # Make client fail
        success_1 = await fallback.send_message(chat_id=12345, message="Failure 1")
        assert success_1 is False, "First send should fail"

        # Verify WARNING was logged for first failure
        warnings_after_first = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warnings_after_first) == 1, f"Expected 1 WARNING after first failure, got {len(warnings_after_first)}"
        assert "Telegram bridge unreachable" in warnings_after_first[0].message

        # Verify state after first failure
        assert fallback._state_tracker.is_reachable is False, "Bridge should be unreachable after failure"
        assert fallback._state_tracker.failure_count == 1, "Should have 1 failure"
        assert fallback._state_tracker._last_failure_logged is True, "Should mark first failure as logged"

        # STEP 2: Add more failures to the streak (these should NOT log WARNING)
        await fallback.send_message(chat_id=12345, message="Failure 2")
        await fallback.send_message(chat_id=12345, message="Failure 3")

        # Verify no additional WARNINGs (still only 1 total)
        warnings_before_recovery = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warnings_before_recovery) == 1, "Should still have only 1 WARNING (deduplication working)"

        # Verify all failures tracked
        assert fallback._state_tracker.failure_count == 3, "Should have 3 failures tracked"

        # Store state before recovery for comparison
        failure_count_before = fallback._state_tracker.failure_count
        last_failure_time_before = fallback._state_tracker.last_failure_time

        # STEP 3: Simulate successful send (bridge becomes reachable)
        mock_httpx_client(True)  # Make client succeed

        # Mock mark_as_reachable to verify it's called
        original_mark_as_reachable = fallback._state_tracker.mark_as_reachable
        mark_as_reachable_called = False

        def mock_mark_as_reachable():
            nonlocal mark_as_reachable_called
            mark_as_reachable_called = True
            return original_mark_as_reachable()

        with patch.object(fallback._state_tracker, 'mark_as_reachable', side_effect=mock_mark_as_reachable):
            success_recovery = await fallback.send_message(chat_id=12345, message="Success after recovery")
            assert success_recovery is True, "Send should succeed after recovery"

        # ACCEPTANCE CRITERIA: Successful send calls `mark_as_reachable()`
        assert mark_as_reachable_called is True, "mark_as_reachable() should be called on successful send"

        # ACCEPTANCE CRITERIA: Internal failure state is cleared/reset
        assert fallback._state_tracker.is_reachable is True, "Bridge should be reachable after success"
        assert fallback._state_tracker.failure_count == 0, "Failure count should be reset to 0"
        assert fallback._state_tracker.last_failure_time is None, "Last failure time should be cleared"
        assert fallback._state_tracker._last_failure_logged is False, "Last failure logged flag should be cleared"

        # Verify the state actually changed (not just that it's in the correct state)
        assert failure_count_before == 3, "Should have had 3 failures before recovery"
        assert last_failure_time_before is not None, "Should have had a failure time before recovery"
        assert fallback._state_tracker.failure_count == 0, "Failure count reset to 0"
        assert fallback._state_tracker.last_failure_time is None, "Failure time cleared"

        # STEP 4: Trigger a new failure after recovery
        mock_httpx_client(False)  # Make client fail again
        success_after_recovery = await fallback.send_message(chat_id=12345, message="New failure after recovery")
        assert success_after_recovery is False, "Send should fail"

        # ACCEPTANCE CRITERIA: New failure after success logs a new WARNING (proves state reset)
        warnings_after_new_failure = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warnings_after_new_failure) == 2, f"Expected 2 WARNINGs total (1 before recovery + 1 after), got {len(warnings_after_new_failure)}"

        # Verify the new WARNING message
        new_warning = warnings_after_new_failure[-1]  # Get the last WARNING
        assert "Telegram bridge unreachable" in new_warning.message, "New WARNING should mention bridge unreachable"

        # ACCEPTANCE CRITERIA: State machine transitions verified
        # Verify the new failure streak started properly
        assert fallback._state_tracker.is_reachable is False, "Bridge should be unreachable after new failure"
        assert fallback._state_tracker.failure_count == 1, "New streak should start with 1 failure"
        assert fallback._state_tracker._last_failure_logged is True, "New failure should be marked as logged"

        print("✅ All acceptance criteria validated:")
        print(f"   - Successful send called mark_as_reachable(): {mark_as_reachable_called}")
        print(f"   - Internal state reset: failure_count={fallback._state_tracker.failure_count}, is_reachable={fallback._state_tracker.is_reachable}")
        print(f"   - New failure logged WARNING: total WARNINGs={len(warnings_after_new_failure)}")
        print(f"   - State machine transition: failure streak (3 failures) → success → new failure streak (1 failure)")


@pytest.mark.asyncio
async def test_state_reset_clears_all_internal_state(caplog, mock_httpx_client):
    """
    Test that all internal state fields are properly reset after successful send.

    This is a detailed verification that every internal state field is cleared,
    not just the failure_count.
    """
    fallback = TelegramFallback(bot_token="test_token", chat_id=12345)

    # Create a failure streak with multiple failures
    mock_httpx_client(False)
    for i in range(5):
        await fallback.send_message(chat_id=12345, message=f"Failure {i+1}")

    with caplog.at_level("WARNING"):
        # Verify state before recovery
        assert fallback._state_tracker.is_reachable is False
        assert fallback._state_tracker.failure_count == 5
        assert fallback._state_tracker.last_failure_time is not None
        assert fallback._state_tracker._last_failure_logged is True

        # Trigger successful send
        mock_httpx_client(True)
        success = await fallback.send_message(chat_id=12345, message="Success")
        assert success is True

    # Verify ALL internal state is reset
    assert fallback._state_tracker.is_reachable is True, "is_reachable should be True"
    assert fallback._state_tracker.failure_count == 0, "failure_count should be 0"
    assert fallback._state_tracker.last_failure_time is None, "last_failure_time should be None"
    assert fallback._state_tracker._last_failure_logged is False, "last_failure_logged should be False"

    # Verify the failure summary also reflects the reset
    summary = fallback._state_tracker.get_failure_summary()
    assert "reachable" in summary.lower(), "Summary should say bridge is reachable"
    assert "unreachable" not in summary.lower(), "Summary should not say unreachable"

    print("✅ All internal state fields properly reset")


@pytest.mark.asyncio
async def test_multiple_recovery_cycles_with_new_warnings(caplog, mock_httpx_client):
    """
    Test multiple recovery cycles to verify state reset works repeatedly.

    This tests:
    - Failure streak 1 → Recovery → Failure streak 2 → Recovery → Failure streak 3
    - Each new failure streak should log a new WARNING
    """
    fallback = TelegramFallback(bot_token="test_token", chat_id=12345)

    with caplog.at_level("WARNING"):
        # CYCLE 1: First failure streak
        mock_httpx_client(False)
        await fallback.send_message(chat_id=12345, message="Failure 1.1")
        await fallback.send_message(chat_id=12345, message="Failure 1.2")

        warnings_after_cycle1 = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warnings_after_cycle1) == 1, "Cycle 1: Should have 1 WARNING"

        # Recovery 1
        mock_httpx_client(True)
        await fallback.send_message(chat_id=12345, message="Success 1")

        # CYCLE 2: Second failure streak
        mock_httpx_client(False)
        await fallback.send_message(chat_id=12345, message="Failure 2.1")
        await fallback.send_message(chat_id=12345, message="Failure 2.2")
        await fallback.send_message(chat_id=12345, message="Failure 2.3")

        warnings_after_cycle2 = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warnings_after_cycle2) == 2, "Cycle 2: Should have 2 WARNINGs (1 from cycle 1, 1 new)"

        # Recovery 2
        mock_httpx_client(True)
        await fallback.send_message(chat_id=12345, message="Success 2")

        # CYCLE 3: Third failure streak
        mock_httpx_client(False)
        await fallback.send_message(chat_id=12345, message="Failure 3.1")

        warnings_after_cycle3 = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warnings_after_cycle3) == 3, "Cycle 3: Should have 3 WARNINGs (1 from each cycle)"

    # Verify final state reflects the third failure streak
    assert fallback._state_tracker.is_reachable is False
    assert fallback._state_tracker.failure_count == 1

    print("✅ Multiple recovery cycles validated:")
    print(f"   - 3 failure streaks, each with a new WARNING")
    print(f"   - Total WARNINGs logged: {len(warnings_after_cycle3)}")
    print(f"   - State reset works repeatedly across cycles")


@pytest.mark.asyncio
async def test_immediate_recovery_after_single_failure(caplog, mock_httpx_client):
    """
    Test immediate recovery after a single failure.

    This edge case verifies that even with just 1 failure before recovery,
    the state still resets properly and a new failure logs a new WARNING.
    """
    fallback = TelegramFallback(bot_token="test_token", chat_id=12345)

    with caplog.at_level("WARNING"):
        # Single failure
        mock_httpx_client(False)
        await fallback.send_message(chat_id=12345, message="Failure")
        assert fallback._state_tracker.failure_count == 1

        # Immediate recovery
        mock_httpx_client(True)
        success = await fallback.send_message(chat_id=12345, message="Success")
        assert success is True
        assert fallback._state_tracker.failure_count == 0

        # New failure should log WARNING
        mock_httpx_client(False)
        await fallback.send_message(chat_id=12345, message="New failure")

        warnings = [r for r in caplog.records if r.levelname == "WARNING" and "telegram.fallback" in r.name]
        assert len(warnings) == 2, "Should have 2 WARNINGs (1 initial + 1 after recovery)"

    print("✅ Immediate recovery after single failure validated")


if __name__ == "__main__":
    # Run the tests standalone
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
