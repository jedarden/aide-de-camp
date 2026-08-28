"""
Comprehensive edge case tests for multiple streak cycles and failure logging.

This test module verifies edge cases and multiple streak cycles:
1. Multiple streak cycles: failures → success → failures → success → failures
   - Verify each new streak logs a WARNING
   - Verify deduplication within each streak

2. Startup state: First failure at startup (bridge initially reachable)
   - Verify WARNING is logged correctly on startup failure

3. Rapid state changes: failure → success → failure in quick succession
   - Verify no race conditions or missed state resets

4. Long failure streak: 10+ consecutive failures
   - Verify deduplication holds over many failures

Acceptance Criteria:
- Multiple streak cycles each log correct WARNINGs
- Startup state correctly logs first-failure WARNING
- Rapid state changes don't break state tracking
- Long streaks maintain deduplication (still only one WARNING per streak)
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


class TestMultipleStreakCyclesEdgeCases:
    """Test multiple failure streak cycles with specific patterns."""

    @pytest.mark.asyncio
    async def test_five_streak_cycles_ending_in_failures(self, fake_httpx_client, caplog):
        """
        Test 5 complete streak cycles: failures → success → failures → success → failures.

        This pattern ends in failures (not success), ensuring state tracking
        works correctly when the system is in a failed state at the end.
        """
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")
        client.set_failure(Exception("Network error"))

        streak_warnings = []

        for cycle in range(5):
            # Failure streak (3 failures per streak)
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

            # Success (except for the last cycle - we end in failures)
            if cycle < 4:
                client.set_success(status_code=200)
                await fallback.send_message(chat_id=12345, message=f"cycle {cycle} success")
                client.set_failure(Exception("Network error"))

        # Verify each streak logged exactly one WARNING
        assert streak_warnings == [1, 1, 1, 1, 1], \
            f"Each of 5 streaks should have exactly one WARNING, got {streak_warnings}"

        # Verify final state is unreachable (we ended with failures)
        assert fallback._state_tracker.is_reachable is False, \
            "Should end in unreachable state (last cycle was failures)"
        assert fallback._state_tracker.failure_count == 3, \
            f"Final failure count should be 3, got {fallback._state_tracker.failure_count}"

        print("✅ 5 streak cycles ending in failures: all verifications passed")

    @pytest.mark.asyncio
    async def test_alternating_failures_success_exact_pattern(self, fake_httpx_client, caplog):
        """
        Test exact pattern: failures → success → failures → success → failures.

        This is the minimal pattern requested in the task to verify multiple
        streak cycles work correctly.
        """
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")
        client.set_failure(Exception("Network error"))

        # First streak: 2 failures
        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="streak 1 failure 1")
            await fallback.send_message(chat_id=12345, message="streak 1 failure 2")

        first_streak_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ]
        assert len(first_streak_warnings) == 1, "First streak should have one WARNING"

        # Success
        client.set_success(status_code=200)
        caplog.clear()
        await fallback.send_message(chat_id=12345, message="success 1")

        # Second streak: 2 failures
        client.set_failure(Exception("Network error"))
        caplog.clear()
        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="streak 2 failure 1")
            await fallback.send_message(chat_id=12345, message="streak 2 failure 2")

        second_streak_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ]
        assert len(second_streak_warnings) == 1, "Second streak should have one WARNING"

        # Success
        client.set_success(status_code=200)
        caplog.clear()
        await fallback.send_message(chat_id=12345, message="success 2")

        # Third streak: 2 failures (end in failures)
        client.set_failure(Exception("Network error"))
        caplog.clear()
        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="streak 3 failure 1")
            await fallback.send_message(chat_id=12345, message="streak 3 failure 2")

        third_streak_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ]
        assert len(third_streak_warnings) == 1, "Third streak should have one WARNING"

        # Verify pattern completed successfully
        assert fallback._state_tracker.is_reachable is False
        assert fallback._state_tracker.failure_count == 2

        print("✅ Exact pattern failures→success→failures→success→failures: verified")

    @pytest.mark.asyncio
    async def test_streak_with_varying_failure_counts(self, fake_httpx_client, caplog):
        """
        Test multiple streak cycles with varying failure counts per streak.

        Verifies deduplication works regardless of how many failures occur
        in each streak (1 failure, 5 failures, 2 failures).
        """
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")
        client.set_failure(Exception("Network error"))

        # Streak 1: 1 failure
        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="streak 1 failure")

        streak1_warnings = len([
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ])
        assert streak1_warnings == 1, "Streak 1 (1 failure) should have one WARNING"

        # Success
        client.set_success(status_code=200)
        await fallback.send_message(chat_id=12345, message="success")

        # Streak 2: 5 failures
        client.set_failure(Exception("Network error"))
        caplog.clear()
        with caplog.at_level("WARNING"):
            for i in range(5):
                await fallback.send_message(chat_id=12345, message=f"streak 2 failure {i}")

        streak2_warnings = len([
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ])
        assert streak2_warnings == 1, "Streak 2 (5 failures) should have one WARNING"

        # Success
        client.set_success(status_code=200)
        await fallback.send_message(chat_id=12345, message="success")

        # Streak 3: 2 failures
        client.set_failure(Exception("Network error"))
        caplog.clear()
        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="streak 3 failure 1")
            await fallback.send_message(chat_id=12345, message="streak 3 failure 2")

        streak3_warnings = len([
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ])
        assert streak3_warnings == 1, "Streak 3 (2 failures) should have one WARNING"

        print("✅ Varying failure counts per streak: deduplication verified")


class TestStartupStateEdgeCases:
    """Test startup state and initial failure scenarios."""

    @pytest.mark.asyncio
    async def test_startup_first_failure_logs_warning_precisely(self, caplog):
        """
        Test that first failure at startup logs WARNING with precise message.

        Verifies the bridge starts reachable and the first failure logs exactly
        one WARNING with comprehensive error context.
        """
        fallback = TelegramFallback(bot_token="test_token")

        # Verify initial state
        assert fallback._state_tracker.is_reachable is True, "Bridge must start reachable"
        assert fallback._state_tracker.failure_count == 0, "Initial failure count must be 0"

        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message="first failure at startup")

        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, "First failure at startup must log exactly one WARNING"

        # Verify warning message contains error context
        warning_msg = warnings[0].message
        assert "Error:" in warning_msg or "Error type:" in warning_msg, \
            "WARNING must include error type information"
        assert "URL:" in warning_msg, "WARNING must include URL attempted"

        print("✅ Startup state: first failure logs precise WARNING")

    @pytest.mark.asyncio
    async def test_startup_multiple_failures_still_one_warning(self, caplog):
        """
        Test that multiple failures at startup still produce only one WARNING.

        Simulates the case where the bridge is down at startup and multiple
        operations fail before the first successful health check.
        """
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            # Multiple failures at startup (no successful sends yet)
            for i in range(5):
                await fallback.send_message(chat_id=12345, message=f"startup failure {i}")

        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, \
            "Multiple failures at startup must still produce only one WARNING"

        # Verify all failures tracked
        assert fallback._failure_count == 5, "All 5 failures must be tracked internally"

        print("✅ Startup state: multiple failures still deduplicated to one WARNING")


class TestRapidStateChangesEdgeCases:
    """Test rapid state changes and race condition scenarios."""

    @pytest.mark.asyncio
    async def test_rapid_failure_success_failure_no_race(self, fake_httpx_client, caplog):
        """
        Test rapid failure → success → failure transitions with no race conditions.

        Verifies that state tracking remains consistent even when states change
        very quickly in succession.
        """
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")

        for cycle in range(10):
            # Failure
            client.set_failure(Exception("Network error"))
            caplog.clear()
            with caplog.at_level("WARNING"):
                await fallback.send_message(chat_id=12345, message=f"rapid failure {cycle}")

            cycle_warnings = [
                r for r in caplog.records
                if r.levelname == "WARNING"
                and "Telegram bridge unreachable: send failed" in r.message
            ]
            assert len(cycle_warnings) == 1, \
                f"Cycle {cycle} failure should log one WARNING, got {len(cycle_warnings)}"
            assert fallback._state_tracker.is_reachable is False, \
                f"Cycle {cycle}: should be unreachable after failure"

            # Immediate success
            client.set_success(status_code=200)
            success = await fallback.send_message(chat_id=12345, message=f"rapid success {cycle}")
            assert success is True, f"Cycle {cycle}: success should return True"
            assert fallback._state_tracker.is_reachable is True, \
                f"Cycle {cycle}: should be reachable after success"
            assert fallback._state_tracker.failure_count == 0, \
                f"Cycle {cycle}: failure count should reset after success"

        print("✅ Rapid state changes: no race conditions detected over 10 cycles")

    @pytest.mark.asyncio
    async def test_concurrent_failures_during_state_transition(self, fake_httpx_client, caplog):
        """
        Test concurrent failures during state transition (reachable → unreachable).

        Verifies that even if multiple failures occur simultaneously during the
        transition, only one WARNING is logged.
        """
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")

        # Start with success (reachable state)
        client.set_success(status_code=200)
        success = await fallback.send_message(chat_id=12345, message="initial success")
        assert success is True
        assert fallback._state_tracker.is_reachable is True

        # Now trigger concurrent failures (simulating state transition)
        client.set_failure(Exception("Network error"))
        with caplog.at_level("WARNING"):
            # Trigger 10 concurrent failures
            tasks = [
                fallback.send_message(chat_id=12345, message=f"concurrent failure {i}")
                for i in range(10)
            ]
            results = await asyncio.gather(*tasks)

        # All should fail
        assert all(r is False for r in results), "All concurrent sends should fail"

        # But only one WARNING should be logged
        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, \
            "Concurrent failures during transition must deduplicate to one WARNING"

        print("✅ Concurrent failures during state transition: properly deduplicated")

    @pytest.mark.asyncio
    async def test_state_persistence_through_rapid_cycles(self, fake_httpx_client, caplog):
        """
        Test that state persists correctly through rapid cycles.

        Verifies that state counters and flags are correctly maintained
        through multiple rapid failure/success/failure cycles.
        """
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")

        for cycle in range(5):
            # Failure streak (2 failures)
            client.set_failure(Exception("Network error"))
            await fallback.send_message(chat_id=12345, message=f"cycle {cycle} fail 1")
            await fallback.send_message(chat_id=12345, message=f"cycle {cycle} fail 2")

            assert fallback._state_tracker.failure_count == 2, \
                f"Cycle {cycle}: failure count should be 2"
            assert fallback._state_tracker.is_reachable is False, \
                f"Cycle {cycle}: should be unreachable"

            # Success
            client.set_success(status_code=200)
            await fallback.send_message(chat_id=12345, message=f"cycle {cycle} success")

            assert fallback._state_tracker.failure_count == 0, \
                f"Cycle {cycle}: failure count should reset to 0"
            assert fallback._state_tracker.is_reachable is True, \
                f"Cycle {cycle}: should be reachable"

        print("✅ State persistence through rapid cycles: verified")


class TestLongFailureStreakEdgeCases:
    """Test long failure streaks and deduplication over many failures."""

    @pytest.mark.asyncio
    async def test_exactly_ten_failure_streak_deduplication(self, caplog):
        """
        Test exactly 10 consecutive failures with deduplication.

        This test specifically addresses the "10+ consecutive failures" requirement
        in the task, testing the boundary case.
        """
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            # Exactly 10 failures
            for i in range(10):
                await fallback.send_message(chat_id=12345, message=f"failure {i + 1}")

        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, \
            f"10 failures must produce exactly one WARNING, got {len(warnings)}"

        # Verify all 10 failures tracked
        assert fallback._failure_count == 10, \
            f"All 10 failures must be tracked, got {fallback._failure_count}"
        assert fallback._state_tracker.failure_count == 10, \
            f"State tracker must count 10 failures, got {fallback._state_tracker.failure_count}"

        print("✅ Exactly 10 failure streak: deduplication verified")

    @pytest.mark.asyncio
    async def test_eleven_failure_streak_deduplication(self, caplog):
        """
        Test 11 consecutive failures with deduplication.

        This tests just beyond the 10+ boundary to ensure deduplication
        holds for streaks longer than 10.
        """
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            # 11 failures (just over the 10+ boundary)
            for i in range(11):
                await fallback.send_message(chat_id=12345, message=f"failure {i + 1}")

        warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
            and "Bridge may be down or network issue" in r.message
        ]
        assert len(warnings) == 1, \
            f"11 failures must produce exactly one WARNING, got {len(warnings)}"

        # Verify all 11 failures tracked
        assert fallback._failure_count == 11, \
            f"All 11 failures must be tracked, got {fallback._failure_count}"

        print("✅ 11 failure streak: deduplication verified")

    @pytest.mark.asyncio
    async def test_long_streak_followed_by_multiple_cycles(self, fake_httpx_client, caplog):
        """
        Test long streak (15 failures) → success → another streak.

        Verifies that a long streak doesn't break the ability to recover
        and start a new streak with proper deduplication.
        """
        client = fake_httpx_client._orig_client()
        fallback = TelegramFallback(bot_token="test_token")
        client.set_failure(Exception("Network error"))

        # Long streak: 15 failures
        with caplog.at_level("WARNING"):
            for i in range(15):
                await fallback.send_message(chat_id=12345, message=f"long streak failure {i + 1}")

        long_streak_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ]
        assert len(long_streak_warnings) == 1, \
            "Long streak (15 failures) must produce only one WARNING"
        assert fallback._state_tracker.failure_count == 15, \
            "Long streak must track all 15 failures"

        # Recovery
        client.set_success(status_code=200)
        caplog.clear()
        await fallback.send_message(chat_id=12345, message="recovery success")

        assert fallback._state_tracker.is_reachable is True, \
            "Should be reachable after recovery"
        assert fallback._state_tracker.failure_count == 0, \
            "Failure count should reset after recovery"

        # New streak after long streak recovery
        client.set_failure(Exception("Network error"))
        caplog.clear()
        with caplog.at_level("WARNING"):
            for i in range(3):
                await fallback.send_message(chat_id=12345, message=f"new streak failure {i + 1}")

        new_streak_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ]
        assert len(new_streak_warnings) == 1, \
            "New streak after long streak must produce one WARNING"

        print("✅ Long streak recovery and new streak: verified")


@pytest.mark.asyncio
async def test_complete_edge_case_suite(fake_httpx_client, caplog):
    """
    Complete end-to-end test covering all edge case scenarios.

    This test validates:
    1. Startup state (first failure)
    2. Long failure streak (10+ failures)
    3. State reset after success
    4. Multiple streak cycles
    5. Rapid state changes
    """
    client = fake_httpx_client._orig_client()
    fallback = TelegramFallback(bot_token="test_token")
    client.set_failure(Exception("Network error"))

    # 1. Startup state: first failure
    assert fallback._state_tracker.is_reachable is True, "Startup: bridge must be reachable"

    with caplog.at_level("WARNING"):
        await fallback.send_message(chat_id=12345, message="startup failure")

    startup_warnings = [
        r for r in caplog.records
        if r.levelname == "WARNING"
        and "Telegram bridge unreachable: send failed" in r.message
    ]
    assert len(startup_warnings) == 1, "Startup: first failure must log WARNING"
    assert fallback._state_tracker.is_reachable is False, "Startup: should be unreachable"

    # 2. Long failure streak (exactly 10 failures)
    with caplog.at_level("WARNING"):
        for i in range(10):
            await fallback.send_message(chat_id=12345, message=f"streak failure {i}")

    long_streak_warnings = [
        r for r in caplog.records
        if r.levelname == "WARNING"
        and "Telegram bridge unreachable: send failed" in r.message
    ]
    assert len(long_streak_warnings) == 1, \
        "Long streak: 10 failures must still have only one WARNING"
    assert fallback._state_tracker.failure_count == 11, \
        "Long streak: should have 11 total failures (1 startup + 10 streak)"

    # 3. State reset after success
    client.set_success(status_code=200)
    caplog.clear()
    await fallback.send_message(chat_id=12345, message="recovery success")

    assert fallback._state_tracker.is_reachable is True, "Recovery: must be reachable"
    assert fallback._state_tracker.failure_count == 0, "Recovery: failure count must reset"

    # 4. Multiple streak cycles (3 cycles)
    for cycle in range(3):
        client.set_failure(Exception("Network error"))
        caplog.clear()

        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message=f"cycle {cycle} failure")

        cycle_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ]
        assert len(cycle_warnings) == 1, f"Cycle {cycle}: must log one WARNING"

        client.set_success(status_code=200)
        await fallback.send_message(chat_id=12345, message=f"cycle {cycle} success")

    # 5. Rapid state changes (5 rapid cycles)
    for cycle in range(5):
        client.set_failure(Exception("Network error"))
        caplog.clear()

        with caplog.at_level("WARNING"):
            await fallback.send_message(chat_id=12345, message=f"rapid {cycle} failure")

        rapid_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "Telegram bridge unreachable: send failed" in r.message
        ]
        assert len(rapid_warnings) == 1, f"Rapid cycle {cycle}: must log one WARNING"

        client.set_success(status_code=200)
        await fallback.send_message(chat_id=12345, message=f"rapid {cycle} success")

    print("✅ Complete edge case suite: all scenarios passed")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
