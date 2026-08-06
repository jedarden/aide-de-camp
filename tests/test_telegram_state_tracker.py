"""Test BridgeState state tracker for Telegram bridge reachability."""

from datetime import datetime, timedelta

import pytest

from src.telegram.state_tracker import BridgeState


class TestBridgeStateInitial:
    """Test initial state of BridgeState."""

    def test_initial_state_is_reachable(self):
        """Test that bridge starts in reachable state."""
        state = BridgeState()
        assert state.is_reachable is True
        assert state.failure_count == 0
        assert state.last_failure_time is None

    def test_initial_get_state(self):
        """Test get_state() returns proper structure initially."""
        state = BridgeState()
        result = state.get_state()

        assert result == {
            "is_reachable": True,
            "last_failure_time": None,
            "failure_count": 0,
            "last_failure_logged": False,
        }


class TestBridgeStateMarkReachable:
    """Test mark_as_reachable() method behavior."""

    def test_mark_as_reachable_resets_all_state(self):
        """Test that mark_as_reachable() resets failure state."""
        state = BridgeState()

        # Simulate some failures
        state.mark_as_unreachable(datetime.now())
        state.mark_as_unreachable(datetime.now())
        assert state.is_reachable is False
        assert state.failure_count == 2

        # Reset
        state.mark_as_reachable()

        assert state.is_reachable is True
        assert state.failure_count == 0
        assert state.last_failure_time is None

    def test_mark_as_reachable_clears_logging_flag(self):
        """Test that mark_as_reachable() resets the logging flag."""
        state = BridgeState()

        # Simulate a failure that was logged
        state.mark_as_unreachable(datetime.now())
        state.should_log_failure()  # This sets the flag

        state.mark_as_reachable()

        # After reset, should_log_failure would be true for a new failure streak
        state.mark_as_unreachable(datetime.now())
        assert state.should_log_failure() is True


class TestBridgeStateMarkUnreachable:
    """Test mark_as_unreachable() method behavior."""

    def test_mark_as_unreachable_sets_state(self):
        """Test that mark_as_unreachable() sets unreachable state."""
        state = BridgeState()
        timestamp = datetime.now()

        state.mark_as_unreachable(timestamp)

        assert state.is_reachable is False
        assert state.last_failure_time == timestamp
        assert state.failure_count == 1

    def test_mark_as_unreachable_increments_count(self):
        """Test that multiple calls increment failure count."""
        state = BridgeState()

        state.mark_as_unreachable(datetime.now())
        assert state.failure_count == 1

        state.mark_as_unreachable(datetime.now())
        assert state.failure_count == 2

        state.mark_as_unreachable(datetime.now())
        assert state.failure_count == 3

    def test_mark_as_unreachable_resets_logging_flag_on_new_streak(self):
        """Test that logging flag resets on new failure streak."""
        state = BridgeState()

        # First failure streak
        state.mark_as_unreachable(datetime.now())
        state.should_log_failure()  # Marks as logged

        # Become reachable
        state.mark_as_reachable()

        # New failure streak should reset logging flag
        state.mark_as_unreachable(datetime.now())
        assert state.should_log_failure() is True  # Should allow logging again


class TestBridgeStateShouldLogFailure:
    """Test should_log_failure() method behavior."""

    def test_should_log_failure_first_time(self):
        """Test that first failure in a streak returns True."""
        state = BridgeState()

        state.mark_as_unreachable(datetime.now())
        assert state.should_log_failure() is True

    def test_should_log_failure_only_once_per_streak(self):
        """Test that subsequent failures return False in same streak."""
        state = BridgeState()

        state.mark_as_unreachable(datetime.now())
        assert state.should_log_failure() is True
        assert state.should_log_failure() is False

    def test_should_log_failure_resets_after_recovery(self):
        """Test that should_log_failure() returns True after recovery."""
        state = BridgeState()

        # First failure streak
        state.mark_as_unreachable(datetime.now())
        assert state.should_log_failure() is True

        # Recover
        state.mark_as_reachable()

        # New failure streak should log again
        state.mark_as_unreachable(datetime.now())
        assert state.should_log_failure() is True

    def test_should_log_failure_false_when_reachable(self):
        """Test that should_log_failure() returns False when reachable."""
        state = BridgeState()

        # Initially reachable
        assert state.should_log_failure() is False

        # After recovery
        state.mark_as_unreachable(datetime.now())
        state.mark_as_reachable()
        assert state.should_log_failure() is False


class TestBridgeStateGetState:
    """Test get_state() method output."""

    def test_get_state_includes_all_fields(self):
        """Test that get_state() returns all expected fields."""
        state = BridgeState()
        timestamp = datetime.now()

        state.mark_as_unreachable(timestamp)

        result = state.get_state()

        assert "is_reachable" in result
        assert "last_failure_time" in result
        assert "failure_count" in result
        assert "last_failure_logged" in result

    def test_get_state_serializes_datetime(self):
        """Test that get_state() serializes datetime as ISO string."""
        state = BridgeState()
        timestamp = datetime(2026, 8, 6, 12, 30, 45)

        state.mark_as_unreachable(timestamp)

        result = state.get_state()

        assert result["last_failure_time"] == "2026-08-06T12:30:45"

    def test_get_state_returns_none_when_no_failure(self):
        """Test that get_state() returns None for timestamps when no failure."""
        state = BridgeState()

        result = state.get_state()

        assert result["last_failure_time"] is None

    def test_get_state_reflects_current_state(self):
        """Test that get_state() reflects current mutable state."""
        state = BridgeState()

        # Initial state
        assert state.get_state()["failure_count"] == 0

        # After failures
        state.mark_as_unreachable(datetime.now())
        state.mark_as_unreachable(datetime.now())
        assert state.get_state()["failure_count"] == 2

        # After recovery
        state.mark_as_reachable()
        assert state.get_state()["failure_count"] == 0


class TestBridgeStateProperties:
    """Test property accessors."""

    def test_is_reachable_property(self):
        """Test is_reachable property accessor."""
        state = BridgeState()

        assert state.is_reachable is True

        state.mark_as_unreachable(datetime.now())
        assert state.is_reachable is False

        state.mark_as_reachable()
        assert state.is_reachable is True

    def test_last_failure_time_property(self):
        """Test last_failure_time property accessor."""
        state = BridgeState()
        timestamp = datetime.now()

        assert state.last_failure_time is None

        state.mark_as_unreachable(timestamp)
        assert state.last_failure_time == timestamp

    def test_failure_count_property(self):
        """Test failure_count property accessor."""
        state = BridgeState()

        assert state.failure_count == 0

        state.mark_as_unreachable(datetime.now())
        assert state.failure_count == 1

        state.mark_as_unreachable(datetime.now())
        assert state.failure_count == 2

        state.mark_as_reachable()
        assert state.failure_count == 0


class TestBridgeStateTransitions:
    """Test complex state transitions and edge cases."""

    def test_full_lifecycle_reachable_to_unreachable_to_reachable(self):
        """Test complete lifecycle: reachable → unreachable → reachable."""
        state = BridgeState()

        # Start reachable
        assert state.is_reachable is True
        assert state.failure_count == 0

        # First failure
        failure_time = datetime.now()
        state.mark_as_unreachable(failure_time)
        assert state.is_reachable is False
        assert state.failure_count == 1
        assert state.last_failure_time == failure_time
        assert state.should_log_failure() is True

        # More failures
        state.mark_as_unreachable(datetime.now())
        state.mark_as_unreachable(datetime.now())
        assert state.failure_count == 3
        assert state.should_log_failure() is False  # Already logged this streak

        # Recovery
        state.mark_as_reachable()
        assert state.is_reachable is True
        assert state.failure_count == 0
        assert state.last_failure_time is None

    def test_multiple_failure_streaks(self):
        """Test multiple distinct failure streaks with recovery."""
        state = BridgeState()

        # First streak
        state.mark_as_unreachable(datetime.now())
        state.mark_as_unreachable(datetime.now())
        assert state.failure_count == 2
        first_logged = state.should_log_failure()

        # Recovery
        state.mark_as_reachable()

        # Second streak
        state.mark_as_unreachable(datetime.now())
        assert state.failure_count == 1  # Reset
        second_logged = state.should_log_failure()

        # Both streaks should have logged once
        assert first_logged is True
        assert second_logged is True

    def test_consecutive_unreachable_calls_without_recovery(self):
        """Test multiple unreachable calls without recovery in between."""
        state = BridgeState()

        for i in range(10):
            state.mark_as_unreachable(datetime.now())
            assert state.failure_count == i + 1
            assert state.is_reachable is False

        # Only first call should log
        assert state.should_log_failure() is True
        assert state.should_log_failure() is False
        assert state.should_log_failure() is False

    def test_immediate_state_changes(self):
        """Test rapid state changes (reachable/unreachable alternating)."""
        state = BridgeState()

        # Rapid cycling
        for i in range(5):
            state.mark_as_unreachable(datetime.now())
            assert state.is_reachable is False
            assert state.failure_count == 1

            state.mark_as_reachable()
            assert state.is_reachable is True
            assert state.failure_count == 0


class TestBridgeStateEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_state_tracker_with_far_future_timestamp(self):
        """Test with a datetime far in the future."""
        state = BridgeState()
        future_time = datetime(2100, 1, 1)

        state.mark_as_unreachable(future_time)
        assert state.last_failure_time == future_time

        result = state.get_state()
        assert result["last_failure_time"] == "2100-01-01T00:00:00"

    def test_state_tracker_with_past_timestamp(self):
        """Test with a datetime in the past."""
        state = BridgeState()
        past_time = datetime(2020, 1, 1)

        state.mark_as_unreachable(past_time)
        assert state.last_failure_time == past_time

    def test_multiple_get_state_calls(self):
        """Test that get_state() can be called multiple times safely."""
        state = BridgeState()
        state.mark_as_unreachable(datetime.now())

        # Multiple calls should return consistent data
        result1 = state.get_state()
        result2 = state.get_state()
        result3 = state.get_state()

        assert result1 == result2 == result3

    def test_get_state_does_not_modify_internal_state(self):
        """Test that get_state() doesn't modify internal state."""
        state = BridgeState()
        state.mark_as_unreachable(datetime.now())

        initial_count = state.failure_count
        initial_reachable = state.is_reachable

        # Calling get_state should not change anything
        for _ in range(10):
            state.get_state()

        assert state.failure_count == initial_count
        assert state.is_reachable == initial_reachable


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
