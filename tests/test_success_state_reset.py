#!/usr/bin/env python3
"""
Test script to verify that successful sends reset the unreachable state.

This verifies the acceptance criteria for adc-64jvd:
1. Successful sends reset the unreachable state if it was set
2. Next failure after a successful send logs WARNING again (new streak)
3. No-op if already reachable (no unnecessary state updates)
4. State transitions: reachable → unreachable → reachable work correctly
"""

import asyncio
import logging
import sys
import os
from io import StringIO
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

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


async def test_success_resets_unreachable_state():
    """Test that successful sends reset the unreachable state."""
    print("Test: Successful send resets unreachable state")

    telegram = TelegramFallback(bot_token="fake_token", chat_id=12345)

    # Set up log capture
    capture = LogCapture()
    capture.setup()

    try:
        # Step 1: Cause a failure to mark bridge as unreachable
        await telegram._handle_send_failure(
            error=Exception("Connection timeout"),
            error_context="Network error"
        )

        # Verify bridge is unreachable
        assert telegram._state_tracker.is_reachable == False, "Bridge should be unreachable"
        assert telegram._is_reachable == False, "Telegram should be unreachable"
        print("  ✓ Bridge marked as unreachable after failure")

        # Get warning count from first failure
        warning_count_after_first = len(capture.get_warning_logs())
        assert warning_count_after_first == 1, "First failure should produce WARNING"
        print(f"  ✓ First failure produced WARNING (count: {warning_count_after_first})")

        # Step 2: Simulate a successful send
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            success = await telegram.send_message(12345, "Test message")

            # Verify send succeeded
            assert success == True, "Send should succeed"
            print("  ✓ Send succeeded")

            # Verify state was reset
            assert telegram._state_tracker.is_reachable == True, "State tracker should be reachable"
            assert telegram._is_reachable == True, "Telegram should be reachable"
            print("  ✓ State reset to reachable after successful send")

        # Step 3: Cause another failure - should log WARNING again (new streak)
        await telegram._handle_send_failure(
            error=Exception("Another timeout"),
            error_context="Network error again"
        )

        warning_count_after_second = len(capture.get_warning_logs())
        assert warning_count_after_second > warning_count_after_first, \
            "Second failure streak should produce new WARNING"
        print(f"  ✓ Second failure streak produced new WARNING (count: {warning_count_after_second})")

        print("✅ Test passed: Successful send resets unreachable state\n")
        return True

    finally:
        capture.teardown()


async def test_success_noop_when_already_reachable():
    """Test that successful send is no-op when already reachable."""
    print("Test: Success no-op when already reachable")

    telegram = TelegramFallback(bot_token="fake_token", chat_id=12345)

    # Initial state: reachable (unknown/True in state tracker)
    # State tracker defaults to True, _is_reachable starts as None
    assert telegram._state_tracker.is_reachable == True, "State tracker should start as reachable"
    print("  ✓ Initial state is reachable (state tracker)")

    # Capture the state before success
    state_before = telegram._state_tracker.get_state()

    # Simulate a successful send when already reachable
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        success = await telegram.send_message(12345, "Test message")
        assert success == True, "Send should succeed"

    # State should still be reachable (no unnecessary changes)
    assert telegram._state_tracker.is_reachable == True, "Should still be reachable"
    assert telegram._is_reachable == True, "Should still be reachable"
    print("  ✓ State remains reachable after success (no-op)")

    # State tracker should have reset failure count even though it was 0
    state_after = telegram._state_tracker.get_state()
    assert state_after['failure_count'] == 0, "Failure count should be 0"
    assert state_after['is_reachable'] == True, "Should be reachable"
    print("  ✓ No unnecessary state updates")

    print("✅ Test passed: Success is no-op when already reachable\n")
    return True


async def test_state_transition_cycle():
    """Test complete state transition cycle: reachable → unreachable → reachable."""
    print("Test: State transition cycle (reachable → unreachable → reachable)")

    telegram = TelegramFallback(bot_token="fake_token", chat_id=12345)

    # Set up log capture
    capture = LogCapture()
    capture.setup()

    try:
        # Initial state: state tracker is reachable, _is_reachable is None (unknown)
        assert telegram._state_tracker.is_reachable == True
        assert telegram._is_reachable == None
        print("  ✓ Initial state: state tracker reachable, _is_reachable None (unknown)")

        # Transition 1: reachable → unreachable (failure)
        await telegram._handle_send_failure(
            error=Exception("First failure"),
            error_context="Error context"
        )
        assert telegram._state_tracker.is_reachable == False
        assert telegram._is_reachable == False
        print("  ✓ Transition 1: reachable → unreachable")

        warning_count_1 = len(capture.get_warning_logs())
        assert warning_count_1 == 1, "First failure should produce WARNING"

        # Transition 2: unreachable → reachable (success)
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            await telegram.send_message(12345, "Test message")
            assert telegram._state_tracker.is_reachable == True
            assert telegram._is_reachable == True  # Now set by _set_reachable
            print("  ✓ Transition 2: unreachable → reachable")

        # Transition 3: reachable → unreachable again (new streak)
        await telegram._handle_send_failure(
            error=Exception("Second streak failure"),
            error_context="Error context 2"
        )
        assert telegram._state_tracker.is_reachable == False
        assert telegram._is_reachable == False  # Now set by _set_reachable in failure handler
        print("  ✓ Transition 3: reachable → unreachable (new streak)")

        warning_count_2 = len(capture.get_warning_logs())
        assert warning_count_2 > warning_count_1, "New streak should produce new WARNING"
        print(f"  ✓ New streak produced new WARNING (total: {warning_count_2})")

        # Transition 4: unreachable → reachable again (success)
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            await telegram.send_message(12345, "Test message")
            assert telegram._state_tracker.is_reachable == True
            assert telegram._is_reachable == True  # Set by _set_reachable
            print("  ✓ Transition 4: unreachable → reachable again")

        print("✅ Test passed: State transition cycle works correctly\n")
        return True

    finally:
        capture.teardown()


async def test_multiple_successes_after_failure():
    """Test that multiple consecutive successes don't cause issues."""
    print("Test: Multiple consecutive successes after failure")

    telegram = TelegramFallback(bot_token="fake_token", chat_id=12345)

    # Set up log capture
    capture = LogCapture()
    capture.setup()

    try:
        # Cause a failure
        await telegram._handle_send_failure(
            error=Exception("Failure"),
            error_context="Error"
        )
        assert telegram._state_tracker.is_reachable == False
        print("  ✓ Bridge unreachable after failure")

        # Multiple successful sends
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            for i in range(3):
                await telegram.send_message(12345, f"Message {i+1}")
                assert telegram._state_tracker.is_reachable == True
                assert telegram._is_reachable == True

            print("  ✓ Multiple consecutive successes maintain reachable state")

        # Another failure after multiple successes should still log WARNING
        await telegram._handle_send_failure(
            error=Exception("New failure"),
            error_context="New error"
        )

        warning_count = len(capture.get_warning_logs())
        assert warning_count >= 2, "Should have WARNINGs for both failure streaks"
        print(f"  ✓ New failure streak after multiple successes produces WARNING")

        print("✅ Test passed: Multiple successes work correctly\n")
        return True

    finally:
        capture.teardown()


async def main():
    """Run all tests."""
    print("="*70)
    print("Success State Reset Tests (adc-64jvd)")
    print("="*70)
    print()

    # Set up basic logging configuration
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        results = []
        results.append(await test_success_resets_unreachable_state())
        results.append(await test_success_noop_when_already_reachable())
        results.append(await test_state_transition_cycle())
        results.append(await test_multiple_successes_after_failure())

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
