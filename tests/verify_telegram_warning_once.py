#!/usr/bin/env python3
"""
Test script to verify that WARNING logs appear only on the first Telegram send failure.

This simulates multiple Telegram send failures and verifies:
1. First failure produces WARNING with error context
2. Second failure does NOT produce another WARNING
3. Logs are readable and include error type/message
"""

import asyncio
import logging
import sys
import os
from io import StringIO
from datetime import datetime
from unittest.mock import AsyncMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from telegram.fallback import TelegramFallback


class LogCapture:
    """Helper to capture log output for verification."""

    def __init__(self):
        self.logs = []
        self.handler = None

    def setup(self):
        """Set up log capture."""
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.logs.append(record)
        # Set logger level to DEBUG so all messages are captured
        logging.getLogger('telegram.fallback').setLevel(logging.DEBUG)
        logging.getLogger('telegram.fallback').addHandler(self.handler)

    def teardown(self):
        """Remove log capture."""
        if self.handler:
            logging.getLogger('telegram.fallback').removeHandler(self.handler)

    def get_warning_logs(self):
        """Get only WARNING level logs."""
        return [log for log in self.logs if log.levelno == logging.WARNING]

    def get_debug_logs(self):
        """Get only DEBUG level logs."""
        return [log for log in self.logs if log.levelno == logging.DEBUG]

    def get_all_logs(self):
        """Get all captured logs."""
        return self.logs


async def test_first_failure_only_warning():
    """Test that only the first failure logs at WARNING level."""
    print("Test: First failure only produces WARNING")

    # Create TelegramFallback instance (no token/config needed for this test)
    telegram = TelegramFallback(bot_token="fake_token_for_test", chat_id=12345)

    # Set up log capture
    capture = LogCapture()
    capture.setup()

    try:
        # Simulate first failure
        await telegram._handle_send_failure(
            error=Exception("Connection timeout"),
            error_context="Test error context"
        )

        # Simulate second failure (same type)
        await telegram._handle_send_failure(
            error=Exception("Another connection timeout"),
            error_context="Second error context"
        )

        # Get logs
        warning_logs = capture.get_warning_logs()
        debug_logs = capture.get_debug_logs()

        print(f"  WARNING logs count: {len(warning_logs)}")
        print(f"  DEBUG logs count: {len(debug_logs)}")

        # Verify exactly one WARNING
        assert len(warning_logs) == 1, f"Expected 1 WARNING, got {len(warning_logs)}"

        # Verify WARNING contains error context
        warning_msg = warning_logs[0].getMessage()
        assert "Connection timeout" in warning_msg or "Test error context" in warning_msg, \
            f"WARNING missing error context: {warning_msg}"
        assert "Error type" in warning_msg, "WARNING missing error type"
        assert "Error:" in warning_msg, "WARNING missing 'Error:' label"

        print("  ✓ First failure logged with WARNING (error context present)")

        # Verify second failure did NOT produce WARNING
        # (It might produce DEBUG if rate-limit window elapses, but not WARNING)
        assert len(warning_logs) == 1, f"Second failure should not produce WARNING, got {len(warning_logs)} WARNING logs"
        print("  ✓ Second failure did NOT produce WARNING")

        # Verify failure count is 2
        assert telegram._failure_count == 2, f"Expected 2 failures, got {telegram._failure_count}"
        print("  ✓ Failure count correctly incremented")

        # Verify first failure flag is set
        assert telegram._has_logged_first_failure == True, "First failure flag should be set"
        print("  ✓ First failure flag is set")

        print("✅ Test passed: WARNING appears only on first failure\n")
        return True

    finally:
        capture.teardown()


async def test_different_failure_types():
    """Test that different failure types each get their own WARNING."""
    print("Test: Different failure types get independent WARNING logs")

    telegram = TelegramFallback(bot_token="fake_token_for_test", chat_id=12345)

    # Set up log capture
    capture = LogCapture()
    capture.setup()

    try:
        # First failure: ConnectionError
        await telegram._handle_send_failure(
            error=Exception("Connection timeout"),
            error_context="Network error"
        )

        # Second failure: HTTPError (different type)
        await telegram._handle_send_failure(
            error=None,
            error_context="HTTP 500 Internal Server Error"
        )

        # Third failure: Another ConnectionError (same as first)
        await telegram._handle_send_failure(
            error=Exception("Another timeout"),
            error_context="Network issues"
        )

        warning_logs = capture.get_warning_logs()

        print(f"  WARNING logs count: {len(warning_logs)}")

        # Should have 2 WARNINGs (one for ConnectionError, one for HTTPError)
        assert len(warning_logs) == 2, f"Expected 2 WARNINGs for different failure types, got {len(warning_logs)}"
        print("  ✓ Both failure types produced independent WARNING logs")

        # Verify failure count is 3
        assert telegram._failure_count == 3, f"Expected 3 failures, got {telegram._failure_count}"
        print("  ✓ All failures counted correctly")

        # Verify distinct failure types tracked
        assert len(telegram._seen_failure_types) == 2, \
            f"Expected 2 distinct failure types, got {len(telegram._seen_failure_types)}"
        print("  ✓ Distinct failure types tracked correctly")

        print("✅ Test passed: Different failure types get independent WARNINGs\n")
        return True

    finally:
        capture.teardown()


async def test_repeated_failure_cooldown():
    """Test that repeated failures respect the cooldown period."""
    print("Test: Repeated failures respect rate-limit cooldown")

    # Create TelegramFallback with short cooldown for testing
    telegram = TelegramFallback(
        bot_token="fake_token_for_test",
        chat_id=12345,
        failure_log_interval_seconds=0.5  # 0.5 second cooldown
    )

    # Set up log capture
    capture = LogCapture()
    capture.setup()

    try:
        # First failure - should produce WARNING
        await telegram._handle_send_failure(
            error=Exception("Error 1"),
            error_context="Context 1"
        )

        # Immediate second failure - should NOT produce DEBUG (cooldown active)
        await telegram._handle_send_failure(
            error=Exception("Error 2"),
            error_context="Context 2"
        )

        warning_logs = capture.get_warning_logs()
        debug_logs = capture.get_debug_logs()

        print(f"  WARNING logs: {len(warning_logs)}")
        print(f"  DEBUG logs: {len(debug_logs)}")

        # Only one WARNING from first failure
        assert len(warning_logs) == 1, f"Expected 1 WARNING, got {len(warning_logs)}"
        print("  ✓ Only first failure produced WARNING")

        # No DEBUG yet (cooldown active, failures counted silently)
        assert len(debug_logs) == 0, f"Expected 0 DEBUG during cooldown, got {len(debug_logs)}"
        print("  ✓ Second failure counted silently (cooldown active)")

        # Wait for cooldown to elapse
        await asyncio.sleep(0.6)

        # Third failure after cooldown - should produce DEBUG summary
        await telegram._handle_send_failure(
            error=Exception("Error 3"),
            error_context="Context 3"
        )

        debug_logs = capture.get_debug_logs()
        print(f"  DEBUG logs after cooldown: {len(debug_logs)}")

        # Now we should have a DEBUG log
        assert len(debug_logs) == 1, f"Expected 1 DEBUG after cooldown, got {len(debug_logs)}"
        debug_msg = debug_logs[0].getMessage()
        assert "Repeated Telegram send failures" in debug_msg, \
            f"DEBUG message incorrect: {debug_msg}"
        print("  ✓ DEBUG summary produced after cooldown elapsed")

        print("✅ Test passed: Repeated failures respect cooldown\n")
        return True

    finally:
        capture.teardown()


async def main():
    """Run all tests."""
    print("="*70)
    print("Telegram WARNING Log Deduplication Tests")
    print("="*70)
    print()

    # Set up basic logging configuration
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        results = []
        results.append(await test_first_failure_only_warning())
        results.append(await test_different_failure_types())
        results.append(await test_repeated_failure_cooldown())

        print("="*70)
        if all(results):
            print("✅ All tests passed!")
            print("="*70)
            return 0
        else:
            print("❌ Some tests failed!")
            print("="*70)
            return 1

    except Exception as e:
        print(f"❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
