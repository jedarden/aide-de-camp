"""
Test first-failure WARNING logging for Telegram bridge.

This test verifies that when a send failure occurs, exactly one WARNING is logged
for the first failure, including failure context (timestamp, error details).

Task: aidedeca-748194dc
Acceptance Criteria:
- WARNING log message contains details about the failure
- WARNING is logged exactly once on first failure
- Log includes failure context (timestamp, error details)
- No WARNING is logged if bridge was already unreachable before test
"""

import asyncio
import pytest
from datetime import datetime
from src.telegram.fallback import TelegramFallback


class TestFirstFailureWarningLogging:
    """Test that first-failure WARNING is logged correctly."""

    async def test_first_failure_logs_warning_with_error_details(self, caplog):
        """
        Test that exactly one WARNING is logged for the first failure after bridge was reachable.

        Scenario:
        1. Start with bridge in reachable state (default)
        2. Trigger a send failure (simulate bridge unreachable)
        3. Verify that exactly one WARNING is logged with failure details
        """
        # Create fallback instance - bridge starts as reachable by default
        fallback = TelegramFallback(bot_token="test_token")

        # Verify initial state: bridge is reachable
        assert fallback._state_tracker.is_reachable is True
        assert fallback._has_logged_first_failure is False
        assert fallback._failure_count == 0

        # Capture WARNING logs
        with caplog.at_level("WARNING"):
            # Trigger first send failure
            await fallback._handle_send_failure(
                error=ConnectionError("connection refused"),
                url="https://api.telegram.org/botTestToken/sendMessage"
            )

        # Verify exactly one WARNING was logged
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1, f"Expected 1 WARNING, got {len(warnings)}"

        # Verify WARNING message contains failure details
        warning_message = warnings[0].message
        assert "Telegram bridge unreachable" in warning_message
        assert "ConnectionError" in warning_message  # Error type
        assert "connection refused" in warning_message  # Error message
        assert "https://api.telegram.org/botTestToken/sendMessage" in warning_message  # URL context

        # Verify state was updated
        assert fallback._has_logged_first_failure is True
        assert fallback._failure_count == 1
        assert fallback._first_failure_timestamp is not None
        assert fallback._state_tracker.is_reachable is False

    async def test_no_warning_on_second_failure_of_same_type(self, caplog):
        """
        Test that no WARNING is logged for the second failure of the same type.

        This verifies rate-limiting: only the first failure in a streak logs a WARNING.
        """
        fallback = TelegramFallback(bot_token="test_token")

        # Trigger first failure
        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error=ConnectionError("first failure"),
            )

        # Clear the caplog to isolate second failure logging
        caplog.clear()

        # Trigger second failure of the same type
        with caplog.at_level("WARNING"):
            with caplog.at_level("DEBUG"):  # Also capture DEBUG to verify no summary yet
                await fallback._handle_send_failure(
                    error=ConnectionError("second failure"),
                )

        # Verify no WARNING was logged for the second failure
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 0, f"Expected 0 WARNING for second failure, got {len(warnings)}"

        # Verify failure count increased
        assert fallback._failure_count == 2

    async def test_no_warning_if_bridge_already_unreachable(self, caplog):
        """
        Test that no WARNING is logged if the bridge was already unreachable before the test.

        This ensures that the WARNING is only logged on the transition from reachable -> unreachable.
        """
        fallback = TelegramFallback(bot_token="test_token")

        # Trigger first failure to establish an unreachable state
        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error=ConnectionError("first failure"),
            )

        # Verify first failure was logged
        first_warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(first_warnings) == 1
        assert fallback._state_tracker.is_reachable is False
        assert fallback._has_logged_first_failure is True

        # Clear logs to isolate second failure
        caplog.clear()

        # Trigger second failure when bridge is already unreachable
        with caplog.at_level("WARNING"):
            with caplog.at_level("DEBUG"):
                await fallback._handle_send_failure(
                    error=ConnectionError("second failure"),
                )

        # Verify no WARNING was logged for the second failure (same type, already unreachable)
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 0, f"Expected 0 WARNING when bridge already unreachable, got {len(warnings)}: {[w.message for w in warnings]}"

        # Verify failure was still recorded
        assert fallback._failure_count == 2

    async def test_new_failure_type_logs_independent_warning(self, caplog):
        """
        Test that a different failure type logs a new WARNING even during an ongoing outage.

        This verifies per-failure-type deduplication (adc-15u0).
        """
        fallback = TelegramFallback(bot_token="test_token")

        # First failure: ConnectionError
        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error=ConnectionError("network error"),
            )

        # Second failure: different type (TimeoutError)
        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error=TimeoutError("request timed out"),
            )

        # Verify two WARNINGs were logged (one per distinct failure type)
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 2

        # Verify both error types are present in logs
        messages = [w.message for w in warnings]
        assert any("ConnectionError" in msg for msg in messages)
        assert any("TimeoutError" in msg for msg in messages)
        assert any("New Telegram send failure type" in msg for msg in messages)

    async def test_warning_includes_timestamp_context(self, caplog):
        """
        Test that the WARNING includes timestamp context for failure tracking.

        Verifies that the failure timestamp is recorded and can be retrieved.
        """
        fallback = TelegramFallback(bot_token="test_token")

        before_failure = datetime.now()

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error=ValueError("test error"),
            )

        after_failure = datetime.now()

        # Verify timestamp was recorded
        assert fallback._first_failure_timestamp is not None
        assert before_failure <= fallback._first_failure_timestamp <= after_failure

        # Verify timestamp is exposed in status
        status = fallback.get_status()
        assert status["first_failure_timestamp"] is not None
        assert "first_failure_timestamp" in status

    async def test_concurrent_failures_log_exactly_one_warning(self, caplog):
        """
        Test that concurrent failures from multiple coroutines log exactly one WARNING.

        This verifies thread safety of the first-failure claim mechanism.
        """
        fallback = TelegramFallback(bot_token="test_token")

        # Simulate 10 concurrent failures
        with caplog.at_level("WARNING"):
            await asyncio.gather(
                *(
                    fallback._handle_send_failure(error=ConnectionError(f"failure {i}"))
                    for i in range(10)
                )
            )

        # Verify exactly one WARNING was logged
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1, f"Expected 1 WARNING for 10 concurrent failures, got {len(warnings)}"

        # Verify all failures were recorded
        assert fallback._failure_count == 10

    async def test_reset_rearms_first_failure_warning(self, caplog):
        """
        Test that after reset and bridge becomes reachable, the next failure logs a WARNING again.

        Verifies that reset_first_failure_state re-arms the detection mechanism,
        and the bridge must transition from reachable -> unreachable to log a WARNING.
        """
        fallback = TelegramFallback(bot_token="test_token")

        # First failure streak
        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(error=ConnectionError("first"))

        assert fallback._has_logged_first_failure is True
        assert fallback._failure_count == 1
        assert fallback._state_tracker.is_reachable is False

        # Reset the first-failure state
        await fallback.reset_first_failure_state()

        # Verify state was cleared
        assert fallback._has_logged_first_failure is False
        assert fallback._first_failure_timestamp is None

        # Mark bridge as reachable again (simulating recovery)
        fallback._state_tracker.mark_as_reachable()
        assert fallback._state_tracker.is_reachable is True

        # Clear logs
        caplog.clear()

        # Trigger failure after reset and recovery - should log WARNING again
        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(error=ConnectionError("after reset"))

        # Verify exactly one WARNING was logged
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "Telegram bridge unreachable" in warnings[0].message

        # Verify failure count increased (counters are retained across reset)
        assert fallback._failure_count == 2

    async def test_non_exception_failure_logs_warning_with_context(self, caplog):
        """
        Test that non-exception failures (e.g., HTTP 500) log a WARNING with context.

        Verifies the error_context parameter is properly included in the log.
        """
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error_context="status 500 - Internal Server Error",
                url="https://api.telegram.org/botTestToken/sendMessage"
            )

        # Verify exactly one WARNING was logged
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1

        # Verify WARNING message contains the failure context
        warning_message = warnings[0].message
        assert "HTTPError" in warning_message  # Synthesized error type
        assert "status 500 - Internal Server Error" in warning_message
        assert "https://api.telegram.org/botTestToken/sendMessage" in warning_message


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
