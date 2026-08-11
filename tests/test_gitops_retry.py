"""
Tests for gitops.py retry logic with exponential backoff.

Verifies that the retry_with_exponential_backoff decorator in gitops.py:
- Retries GitNetworkError with exponential backoff and jitter
- Does NOT retry GitAuthenticationError (permanent error)
- Does NOT retry GitConflictError (permanent error)
- Logs retry attempts with delay and attempt information
- Uses configurable max retries, base delay, max delay, and jitter factor
"""

import time
import random
from unittest.mock import Mock, patch
import pytest

from src.action.steps.gitops import retry_with_exponential_backoff
from src.action.steps.git_validation import (
    GitNetworkError,
    GitAuthenticationError,
    GitConflictError,
)


class TestGitOpsRetryDecorator:
    """Tests for gitops retry_with_exponential_backoff decorator."""

    def test_retry_on_git_network_error_success_after_retries(self):
        """Test that retry eventually succeeds after transient network failures."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def git_push_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise GitNetworkError("Connection timeout")
            return "push successful"

        result = git_push_operation()
        assert result == "push successful"
        assert call_count == 2

    def test_retry_exhausted_on_persistent_network_error(self):
        """Test that retry raises exception after all retries exhausted."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def failing_git_operation():
            nonlocal call_count
            call_count += 1
            raise GitNetworkError("Persistent network error")

        with pytest.raises(GitNetworkError, match="Persistent network error"):
            failing_git_operation()

        assert call_count == 3  # Initial attempt + 2 retries

    def test_no_retry_on_git_authentication_error(self):
        """Test that GitAuthenticationError is NOT retried (permanent error)."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1
        )
        def git_auth_operation():
            nonlocal call_count
            call_count += 1
            raise GitAuthenticationError("Authentication failed")

        with pytest.raises(GitAuthenticationError, match="Authentication failed"):
            git_auth_operation()

        # Should only be called once - auth errors are not retried
        assert call_count == 1

    def test_no_retry_on_git_conflict_error(self):
        """Test that GitConflictError is NOT retried (permanent error)."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1
        )
        def git_conflict_operation():
            nonlocal call_count
            call_count += 1
            raise GitConflictError("Merge conflict detected")

        with pytest.raises(GitConflictError, match="Merge conflict detected"):
            git_conflict_operation()

        # Should only be called once - conflict errors are not retried
        assert call_count == 1

    def test_exponential_backoff_with_jitter(self):
        """Test that exponential backoff with jitter is applied correctly."""
        call_count = 0
        sleep_times = []

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.1,
            max_delay=1.0,
            jitter_factor=0.25
        )
        def git_operation_with_jitter():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise GitNetworkError("Network error")
            return "success"

        # Patch time.sleep to capture delays
        original_sleep = time.sleep
        def mock_sleep(duration):
            sleep_times.append(duration)
            # Don't actually sleep in test

        with patch('time.sleep', side_effect=mock_sleep):
            result = git_operation_with_jitter()

        assert result == "success"
        assert call_count == 4
        assert len(sleep_times) == 3  # 3 retries before success

        # Verify exponential backoff: 0.1, 0.2, 0.4 (before jitter)
        # With jitter_factor=0.25: each should have ±25% variation
        base_delays = [0.1, 0.2, 0.4]
        for actual_delay, base_delay in zip(sleep_times, base_delays):
            # Jitter should be within ±25% of base delay
            min_expected = base_delay * 0.75
            max_expected = base_delay * 1.25
            assert min_expected <= actual_delay <= max_expected

    def test_max_delay_cap(self):
        """Test that delays are capped at max_delay."""
        sleep_times = []

        @retry_with_exponential_backoff(
            max_retries=5,
            base_delay=1.0,
            max_delay=2.0,  # Cap at 2.0s
            jitter_factor=0.0
        )
        def git_operation_with_cap():
            raise GitNetworkError("Test error")

        def mock_sleep(duration):
            sleep_times.append(duration)

        with patch('time.sleep', side_effect=mock_sleep):
            with pytest.raises(GitNetworkError):
                git_operation_with_cap()

        # Expected with base_delay=1.0, max_delay=2.0:
        # 1.0, 2.0, 2.0, 2.0, 2.0 (capped at 2.0s)
        for delay in sleep_times:
            assert delay <= 2.0  # Should never exceed max_delay

    def test_retry_logging_with_delay_and_attempt(self):
        """Test that retry attempts log delay and attempt information."""
        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def failing_operation():
            raise GitNetworkError("Test error")

        with patch('src.action.steps.gitops.logger') as mock_logger:
            with pytest.raises(GitNetworkError):
                failing_operation()

            # Verify warning logs for retry attempts
            assert mock_logger.warning.call_count >= 2
            # Verify error log for final failure
            assert mock_logger.error.call_count >= 1

            # Check that log messages include delay and attempt info
            warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
            for call in warning_calls:
                assert "attempt" in call.lower()
                assert "retrying in" in call.lower()
                # Should show base delay and jitter
                assert "base:" in call.lower()

    def test_no_retry_logging_for_permanent_errors(self):
        """Test that permanent errors are logged with 'no retry' message."""
        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1
        )
        def auth_operation():
            raise GitAuthenticationError("Auth failed")

        with patch('src.action.steps.gitops.logger') as mock_logger:
            with pytest.raises(GitAuthenticationError):
                auth_operation()

            # Should log error with "no retry" message
            error_calls = [str(call) for call in mock_logger.error.call_args_list]
            assert any("no retry" in call.lower() for call in error_calls)

    def test_max_retries_exceeded_logging(self):
        """Test that max retries exceeded is logged appropriately."""
        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def failing_operation():
            raise GitNetworkError("Persistent error")

        with patch('src.action.steps.gitops.logger') as mock_logger:
            with pytest.raises(GitNetworkError):
                failing_operation()

            # Should log "max retries exceeded" message
            error_calls = [str(call) for call in mock_logger.error.call_args_list]
            assert any("max retries" in call.lower() for call in error_calls)
            assert any("exceeded" in call.lower() for call in error_calls)

    def test_default_parameters(self):
        """Test retry decorator with default parameters."""
        call_count = 0

        @retry_with_exponential_backoff()
        def git_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise GitNetworkError("Network error")
            return "success"

        result = git_operation()
        assert result == "success"
        assert call_count == 2


class TestGitOpsRetryRealWorldScenarios:
    """Test retry decorator with realistic git operation scenarios."""

    def test_git_push_with_connection_timeout(self):
        """Test retry logic for git push with connection timeout."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def git_push():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise GitNetworkError("git push: connection timeout")
            return "push successful"

        result = git_push()
        assert result == "push successful"
        assert call_count == 2

    def test_git_push_with_dns_failure(self):
        """Test retry logic for git push with DNS resolution failure."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def git_push():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise GitNetworkError("git push: dns resolution failed")
            return "push successful"

        result = git_push()
        assert result == "push successful"
        assert call_count == 2

    def test_git_push_with_intermittent_network_failures(self):
        """Test retry logic with multiple intermittent network failures."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=5,
            base_delay=0.01,
            max_delay=0.5,
            jitter_factor=0.1
        )
        def git_push():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                # Simulate different types of network errors
                errors = [
                    "Connection timeout",
                    "Network unreachable",
                    "Connection reset by peer"
                ]
                raise GitNetworkError(f"git push: {errors[call_count - 1]}")
            return "push successful"

        result = git_push()
        assert result == "push successful"
        assert call_count == 4

    def test_git_push_does_not_retry_auth_error(self):
        """Test that authentication errors are not retried."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1
        )
        def git_push():
            nonlocal call_count
            call_count += 1
            raise GitAuthenticationError(
                "git push: authentication failed"
            )

        with pytest.raises(GitAuthenticationError):
            git_push()

        # Should only be called once (no retries for auth errors)
        assert call_count == 1

    def test_git_push_does_not_retry_conflict_error(self):
        """Test that conflict errors are not retried."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1
        )
        def git_push():
            nonlocal call_count
            call_count += 1
            raise GitConflictError(
                "git push: non-fast-forward - remote has new commits"
            )

        with pytest.raises(GitConflictError):
            git_push()

        # Should only be called once (no retries for conflict errors)
        assert call_count == 1

    def test_retry_with_configurable_max_retries(self):
        """Test retry with custom max retries configuration."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=5,  # Allow up to 5 retries
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def git_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 4:  # Succeeds on 4th attempt (3 retries)
                raise GitNetworkError("Network error")
            return "success"

        result = git_operation()
        assert result == "success"
        assert call_count == 4
