"""Bridge state tracker for monitoring Telegram bridge reachability."""

from datetime import datetime
from typing import Optional


class BridgeState:
    """Tracks the reachability state of the Telegram bridge.

    Maintains failure count, last failure timestamp, and logging state
    to provide a clean interface for health monitoring and alerting.
    """

    # Maximum failure count to prevent infinite growth
    MAX_FAILURE_COUNT = 9999

    def __init__(self) -> None:
        """Initialize a new BridgeState tracker."""
        self._is_reachable: bool = True
        self._last_failure_time: Optional[datetime] = None
        self._failure_count: int = 0
        self._last_failure_logged: bool = False

    def mark_as_reachable(self) -> None:
        """Mark the bridge as reachable and reset failure state.

        Called when a successful health check or operation completes.
        Resets the failure count and clears the last failure timestamp.
        """
        self._is_reachable = True
        self._last_failure_time = None
        self._failure_count = 0
        self._last_failure_logged = False

    def mark_as_unreachable(self, timestamp: datetime) -> None:
        """Mark the bridge as unreachable and record failure details.

        Args:
            timestamp: The timestamp when the failure occurred
        """
        self._is_reachable = False
        self._last_failure_time = timestamp
        # Cap failure count at MAX_FAILURE_COUNT to prevent infinite growth
        if self._failure_count < self.MAX_FAILURE_COUNT:
            self._failure_count += 1
        # Reset logging flag when we transition from reachable to unreachable
        # or when we're in a new failure streak
        if self._failure_count == 1:
            self._last_failure_logged = False

    def should_log_failure(self) -> bool:
        """Determine if a failure should be logged.

        Returns True only once per failure streak - the first time
        we detect a failure after being reachable. Subsequent failures
        return False until the bridge becomes reachable again.

        Returns:
            bool: True if this is a new failure streak, False otherwise
        """
        if not self._is_reachable and not self._last_failure_logged:
            self._last_failure_logged = True
            return True
        return False

    def get_state(self) -> dict:
        """Get the current state as a dictionary for debugging/monitoring.

        Returns:
            dict: Current state with all field values
        """
        return {
            "is_reachable": self._is_reachable,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
            "failure_count": self._failure_count,
            "last_failure_logged": self._last_failure_logged,
        }

    @property
    def is_reachable(self) -> bool:
        """Whether the bridge is currently reachable."""
        return self._is_reachable

    @property
    def last_failure_time(self) -> Optional[datetime]:
        """Timestamp of the most recent failure, if any."""
        return self._last_failure_time

    @property
    def failure_count(self) -> int:
        """Number of consecutive failures recorded."""
        return self._failure_count

    def reset_failure_count(self) -> None:
        """Reset the failure counter to zero.

        This can be used for manual recovery or after a threshold is reached.
        The reachability state and last failure timestamp are preserved.
        """
        self._failure_count = 0

    def get_failure_summary(self) -> str:
        """Get a human-readable summary of the bridge failure state.

        Returns:
            A human-readable status string indicating whether the bridge is
            reachable or, if unreachable, how long it has been unreachable
            and how many consecutive failures have occurred.
        """
        if self._is_reachable:
            return "Bridge reachable"

        # Bridge is unreachable - calculate time since last failure
        if self._last_failure_time is None:
            return "Bridge unreachable (no failure timestamp)"

        now = datetime.now()
        time_since_failure = now - self._last_failure_time

        # Format the time duration in a human-readable way
        total_seconds = int(time_since_failure.total_seconds())
        if total_seconds < 60:
            duration_str = f"{total_seconds} second(s)"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            duration_str = f"{minutes} minute(s)"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            duration_str = f"{hours} hour(s)"
        else:
            days = total_seconds // 86400
            duration_str = f"{days} day(s)"

        return (
            f"Bridge unreachable for {duration_str}, "
            f"{self._failure_count} consecutive failure(s)"
        )
