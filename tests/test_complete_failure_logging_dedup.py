"""
Complete failure logging and deduplication verification tests.

This test module verifies the end-to-end failure logging system with proper
deduplication and state reset, including:
1. First-failure WARNING when bridge is reachable
2. Deduplication (no duplicate WARNINGs within a streak)
3. State reset after successful sends
4. Multiple streak cycles (failures → success → failures)
5. Edge cases including startup state
"""

import asyncio
import logging
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx

from src.telegram.fallback import TelegramFallback
from src.telegram.state_tracker import BridgeState


class FakeAsyncClient:
    """Mock httpx.AsyncClient that simulates network failures and successes."""

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

    def set_failure(self, fail_with: Exception | None = None):
        """Set the failure mode for subsequent calls."""
        self.fail_with = fail_with

    def set_success(self, status_code: int = 200):
        """Set success mode for subsequent calls."""
        self.fail_with = None
        self.status_code = status_code


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


class TestFirstFailureLogging:
    """Test first-failure WARNING when bridge is initially reachable."""

    @pytest.mark.asyncio
    async def test_first_failure_logs_warning_when_reachable(self, caplog):
        """Test that first failure logs WARNING when bridge starts reachable."""
        fallback = TelegramFallback(bot_token="test_token")

        # Initially reachable
        assert fallback._state_tracker.is_reachable is True

        with caplog.at_level("WARNING"):
            # Trigger first failure
            success = await fallback.send_message(chat_id=12345, message="test")

        assert success is False, "Send should fail"

        # Verify exactly one WARNING from state tracker
        state_tracker_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(state_tracker_warnings) == 1, \
            "Should have exactly one first-failure WARNING from state tracker"

    @pytest.mark.asyncio
    async def test_warning_contains_error_context(self, caplog):
        """Test that WARNING includes comprehensive error context."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            success = await fallback.send_message(chat_id=12345, message="test")

        assert success is False

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1

        warning_msg = warnings[0].message
        # Verify error context is preserved
        assert "Error:" in warning_msg or "Error type:" in warning_msg
        assert "URL:" in warning_msg


class TestDeduplication:
    """Test deduplication - no duplicate WARNINGs within a streak."""

    @pytest.mark.asyncio
    async def test_multiple_failures_single_warning(self, caplog):
        """Test that multiple consecutive failures produce only one WARNING."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            # First failure - should log WARNING
            await fallback.send_message(chat_id=12345, message="test 1")

            # Get WARNING count after first failure
            warnings_after_first = len([r for r in caplog.records if r.levelname == "WARNING"])
            assert warnings_after_first >= 1, "First failure should produce WARNING"

            # Subsequent failures - should NOT log additional WARNINGs
            for i in range(2, 11):
                await fallback.send_message(chat_id=12345, message=f"test {i}")

        # Verify no additional WARNINGs from repeated failures
        warnings_after_all = [r for r in caplog.records if r.levelname == "WARNING"]
        # Filter to state tracker warnings (not startup warnings)
        state_tracker_warnings = [
            r for r in warnings_after_all
            if "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(state_tracker_warnings) == 1, \
            f"Should still have exactly one state tracker WARNING, got {len(state_tracker_warnings)}"

    @pytest.mark.asyncio
    async def test_no_warning_spam_on_sustained_outage(self, caplog):
        """Test that sustained outage does not produce log spam."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("DEBUG"):
            # First failure
            await fallback.send_message(chat_id=12345, message="first")

            # Sustained failures
            for i in range(50):
                await fallback.send_message(chat_id=12345, message=f"failure {i}")

        # Filter telegram.fallback logs only
        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "telegram.fallback" in r.name
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        debugs = [
            r for r in caplog.records
            if r.levelname == "DEBUG"
            and "telegram.fallback" in r.name
        ]

        assert len(warnings) == 1, "Should have exactly one WARNING for first failure"
        assert len(debugs) == 0, "Should have no DEBUG spam within cooldown window"

    @pytest.mark.asyncio
    async def test_failure_count_increments_despite_deduplication(self, caplog):
        """Test that failure count increments correctly even when WARNINGs are deduped."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            # Trigger multiple failures
            for i in range(5):
                await fallback.send_message(chat_id=12345, message=f"test {i}")

        # Verify failure count
        assert fallback._failure_count == 5, \
            f"Failure count should be 5, got {fallback._failure_count}"
        assert fallback._state_tracker.failure_count == 5, \
            f"State tracker failure count should be 5, got {fallback._state_tracker.failure_count}"

        # Verify only one WARNING
        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, "Should have exactly one WARNING despite 5 failures"


class TestStateReset:
    """Test state reset after successful sends."""

    @pytest.mark.asyncio
    async def test_successful_send_resets_state(self, fake_httpx_client, caplog):
        """Test that successful send calls mark_as_reachable() and resets state."""
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")

        # First, trigger failures
        with caplog.at_level("WARNING"):
            for i in range(3):
                await fallback.send_message(chat_id=12345, message=f"failure {i}")

        assert fallback._state_tracker.is_reachable is False
        assert fallback._state_tracker.failure_count == 3
        first_streak_warning_count = len([
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ])

        # Now simulate successful send
        client.set_success(status_code=200)
        caplog.clear()

        with caplog.at_level("INFO"):
            success = await fallback.send_message(chat_id=12345, message="success")

        assert success is True, "Send should succeed"
        assert fallback._state_tracker.is_reachable is True, \
            "State tracker should be marked reachable after success"
        assert fallback._state_tracker.failure_count == 0, \
            "Failure count should be reset to 0"

        # Verify that a subsequent failure logs a new WARNING
        client.set_failure(Exception("Network error"))
        caplog.clear()

        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="failure after success")

        new_streak_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(new_streak_warnings) == 1, \
            "Should log a new WARNING for the new failure streak"

    @pytest.mark.asyncio
    async def test_mark_as_reachable_clears_all_failure_state(self):
        """Test that mark_as_reachable() clears all failure state."""
        fallback = TelegramFallback(bot_token="test_token")

        # Trigger failures
        for i in range(3):
            await fallback.send_message(chat_id=12345, message=f"failure {i}")

        assert fallback._state_tracker.is_reachable is False
        assert fallback._state_tracker.failure_count == 3
        assert fallback._state_tracker.last_failure_time is not None

        # Manually call mark_as_reachable
        fallback._state_tracker.mark_as_reachable()

        # Verify all state is cleared
        assert fallback._state_tracker.is_reachable is True
        assert fallback._state_tracker.failure_count == 0
        assert fallback._state_tracker.last_failure_time is None
        assert fallback._state_tracker._last_failure_logged is False

    @pytest.mark.asyncio
    async def test_state_tracker_should_log_failure_resets_after_recovery(self):
        """Test that should_log_failure() returns True again after recovery."""
        state = BridgeState()

        # First streak
        state.mark_as_unreachable(datetime.now())
        assert state.should_log_failure() is True
        assert state.should_log_failure() is False  # Second call returns False

        # Recovery
        state.mark_as_reachable()

        # Second streak
        state.mark_as_unreachable(datetime.now())
        assert state.should_log_failure() is True, \
            "should_log_failure() should return True for new streak after recovery"


class TestMultipleStreakCycles:
    """Test multiple failure streak cycles with recovery in between."""

    @pytest.mark.asyncio
    async def test_multiple_failures_success_failures_cycle(self, fake_httpx_client, caplog):
        """Test complete cycle: failures → success → failures again."""
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")

        client.set_failure(Exception("Network error"))

        # First streak: 5 failures
        with caplog.at_level("WARNING"):
            for i in range(5):
                await fallback.send_message(chat_id=12345, message=f"failure streak 1-{i}")

        first_streak_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(first_streak_warnings) == 1, "First streak should have one WARNING"

        # Success
        client.set_success(status_code=200)
        caplog.clear()

        with caplog.at_level("INFO"):
            success = await fallback.send_message(chat_id=12345, message="success")
        assert success is True

        # Second streak: 3 failures
        client.set_failure(Exception("Network error"))
        caplog.clear()

        with caplog.at_level("WARNING"):
            for i in range(3):
                await fallback.send_message(chat_id=12345, message=f"failure streak 2-{i}")

        second_streak_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(second_streak_warnings) == 1, "Second streak should have one WARNING"

    @pytest.mark.asyncio
    async def test_three_streak_cycles(self, fake_httpx_client, caplog):
        """Test three complete failure streak cycles."""
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")
        client.set_failure(Exception("Network error"))

        streak_warnings = []

        for cycle in range(3):
            # Failure streak
            caplog.clear()
            with caplog.at_level("WARNING"):
                for i in range(3):
                    await fallback.send_message(chat_id=12345, message=f"cycle {cycle} failure {i}")

            cycle_warnings = [
                r for r in caplog.records
                if r.levelname == "WARNING"
                and "Telegram bridge unreachable: send failed" in r.message
                and "Bridge may be down or network issue" in r.message
            ]
            streak_warnings.append(len(cycle_warnings))

            # Success
            client.set_success(status_code=200)
            await fallback.send_message(chat_id=12345, message=f"cycle {cycle} success")
            client.set_failure(Exception("Network error"))

        assert streak_warnings == [1, 1, 1], \
            f"Each streak should have exactly one WARNING, got {streak_warnings}"

    @pytest.mark.asyncio
    async def test_rapid_cycles(self, fake_httpx_client, caplog):
        """Test rapid failure/success/failure cycles."""
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")

        for cycle in range(5):
            # Failure
            client.set_failure(Exception("Network error"))
            caplog.clear()

            with caplog.at_level("WARNING"):
                await fallback.send_message(chat_id=12345, message=f"cycle {cycle} failure")

            cycle_warnings = [
                r for r in caplog.records
                if r.levelname == "WARNING"
                and "Telegram bridge unreachable: send failed" in r.message
                and "Bridge may be down or network issue" in r.message
            ]
            assert len(cycle_warnings) == 1, \
                f"Cycle {cycle} should have one WARNING, got {len(cycle_warnings)}"

            # Success
            client.set_success(status_code=200)
            await fallback.send_message(chat_id=12345, message=f"cycle {cycle} success")


class TestEdgeCases:
    """Test edge cases including startup state and boundary conditions."""

    @pytest.mark.asyncio
    async def test_startup_state_first_failure_logs_warning(self, caplog):
        """Test that first failure at startup logs WARNING when bridge was reachable."""
        fallback = TelegramFallback(bot_token="test_token")

        # Verify initial state
        assert fallback._state_tracker.is_reachable is True, "Bridge should start reachable"

        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="first failure")

        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, "First failure at startup should log WARNING"

    @pytest.mark.asyncio
    async def test_single_failure_no_success(self, caplog):
        """Test a single failure with no intervening success."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="only failure")

        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, "Single failure should log WARNING"

        # Verify state
        assert fallback._state_tracker.is_reachable is False
        assert fallback._state_tracker.failure_count == 1

    @pytest.mark.asyncio
    async def test_immediate_success_after_failure(self, fake_httpx_client, caplog):
        """Test immediate success after a failure."""
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")

        client.set_failure(Exception("Network error"))

        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="failure")

        # Immediate success
        client.set_success(status_code=200)
        success = await fallback.send_message(chat_id=12345, message="success")

        assert success is True
        assert fallback._state_tracker.is_reachable is True
        assert fallback._state_tracker.failure_count == 0

    @pytest.mark.asyncio
    async def test_long_failure_streak_then_success(self, fake_httpx_client, caplog):
        """Test a long failure streak followed by success."""
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")

        client.set_failure(Exception("Network error"))

        with caplog.at_level("WARNING"):
            # Long streak
            for i in range(100):
                await fallback.send_message(chat_id=12345, message=f"failure {i}")

        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, "Long streak should still have only one WARNING"
        assert fallback._state_tracker.failure_count == 100

        # Success after long streak
        client.set_success(status_code=200)
        success = await fallback.send_message(chat_id=12345, message="success")

        assert success is True
        assert fallback._state_tracker.failure_count == 0

    @pytest.mark.asyncio
    async def test_concurrent_failures_deduplicated(self, caplog):
        """Test that concurrent failures are properly deduplicated."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            # Trigger concurrent failures
            tasks = [
                fallback.send_message(chat_id=12345, message=f"concurrent {i}")
                for i in range(10)
            ]
            results = await asyncio.gather(*tasks)

        # All should fail
        assert all(r is False for r in results)

        # But only one WARNING should be logged
        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, "Concurrent failures should be deduplicated to one WARNING"


class TestIntegrationWithStatusAPI:
    """Test that status API reflects the correct failure state."""

    @pytest.mark.asyncio
    async def test_status_shows_failure_state(self, fake_httpx_client):
        """Test that status endpoint shows correct failure state."""
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")

        client.set_failure(Exception("Network error"))

        # Trigger failures
        await fallback.send_message(chat_id=12345, message="failure 1")
        await fallback.send_message(chat_id=12345, message="failure 2")

        status = fallback.get_status()

        assert status["failure_count"] == 2
        assert status["reachable"] is False
        assert status["bridge_failure_summary"] != "Bridge reachable"

        # Success
        client.set_success(status_code=200)
        await fallback.send_message(chat_id=12345, message="success")

        status = fallback.get_status()

        assert status["failure_count"] == 0
        assert status["reachable"] is True
        assert status["bridge_failure_summary"] == "Bridge reachable"


@pytest.mark.asyncio
async def test_complete_end_to_end_flow(fake_httpx_client, caplog):
    """
    Complete end-to-end simulation of multiple failure streak cycles:
    1. Bridge reachable initially
    2. First failure streak → single WARNING
    3. Recovery → state reset
    4. Second failure streak → new WARNING
    5. Verify state tracker properly resets
    6. Verify no duplicate WARNINGs within streaks
    """
    client = fake_httpx_client._orig_client()
    fallback = TelegramFallback(bot_token="test_token")

    # Step 1: Verify initial state
    assert fallback._state_tracker.is_reachable is True
    assert fallback._state_tracker.failure_count == 0

    client.set_failure(Exception("Network error"))

    # Step 2: First failure streak
    with caplog.at_level("WARNING"):
        for i in range(5):
            await fallback.send_message(chat_id=12345, message=f"streak1 failure {i}")

    first_streak_warnings = [
        r for r in caplog.records
        if r.levelname == "WARNING"
        and "Telegram bridge unreachable: send failed" in r.message
        and "Bridge may be down or network issue" in r.message
    ]
    assert len(first_streak_warnings) == 1, \
        f"Step 2 failed: Expected 1 WARNING, got {len(first_streak_warnings)}"
    assert fallback._state_tracker.failure_count == 5

    # Step 3: Recovery
    client.set_success(status_code=200)
    caplog.clear()

    success = await fallback.send_message(chat_id=12345, message="recovery success")
    assert success is True, "Step 3 failed: Recovery send should succeed"
    assert fallback._state_tracker.is_reachable is True, \
        "Step 3 failed: State should be reachable"
    assert fallback._state_tracker.failure_count == 0, \
        "Step 3 failed: Failure count should be reset"

    # Step 4: Second failure streak
    client.set_failure(Exception("Network error"))
    caplog.clear()

    with caplog.at_level("WARNING"):
        for i in range(3):
            await fallback.send_message(chat_id=12345, message=f"streak2 failure {i}")

    second_streak_warnings = [
        r for r in caplog.records
        if r.levelname == "WARNING"
        and "Telegram bridge unreachable: send failed" in r.message
        and "Bridge may be down or network issue" in r.message
    ]
    assert len(second_streak_warnings) == 1, \
        f"Step 4 failed: Expected 1 WARNING, got {len(second_streak_warnings)}"
    assert fallback._state_tracker.failure_count == 3

    # Step 5: Verify no cross-contamination between streaks
    assert fallback._state_tracker.is_reachable is False

    # Step 6: Verify status reflects current state
    status = fallback.get_status()
    assert status["failure_count"] == 3
    assert status["reachable"] is False
    assert "3 consecutive failure" in status["bridge_failure_summary"]

    print("✅ Complete end-to-end flow passed: All verification steps successful")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
