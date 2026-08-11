"""
Tests for git_retry exponential backoff decorator.

Verifies that the retry_with_exponential_backoff decorator correctly:
- Uses is_transient classifier from src.errors
- Implements exponential backoff with formula: min(base_delay * 2^attempt, max_delay)
- Adds jitter (±25%) to prevent thundering herd
- Logs retry attempts with delay and attempt number
- Supports both async and sync functions
- Stops on first non-transient error
"""

import asyncio
import time
from unittest.mock import Mock, patch
import pytest
import httpx
import aiohttp

from src.utils.git_retry import retry_with_exponential_backoff
from src.errors import is_transient


class TestExponentialBackoffDecorator:
    """Tests for retry_with_exponential_backoff decorator."""

    @pytest.mark.asyncio
    async def test_async_retry_success_on_first_attempt(self):
        """Test that successful async function returns immediately without retries."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        async def successful_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_operation()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_success_after_transient_errors(self):
        """Test that retry eventually succeeds after transient failures."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Simulate transient timeout error
                raise TimeoutError("Connection timeout")
            return "success"

        result = await flaky_operation()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_exhausted_on_transient_errors(self):
        """Test that retry raises exception after all retries exhausted for transient errors."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=2, base_delay=0.01, max_delay=0.1)
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Persistent timeout")

        with pytest.raises(TimeoutError, match="Persistent timeout"):
            await failing_operation()

        assert call_count == 3  # Initial attempt + 2 retries

    @pytest.mark.asyncio
    async def test_async_retry_stops_on_non_transient_error(self):
        """Test that retry stops immediately on non-transient errors (e.g., 404)."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        async def not_found_operation():
            nonlocal call_count
            call_count += 1
            # Simulate HTTP 404 - not a transient error
            raise httpx.HTTPStatusError(
                "Not Found",
                request=Mock(spec=httpx.Request),
                response=Mock(status_code=404)
            )

        with pytest.raises(httpx.HTTPStatusError):
            await not_found_operation()

        # Should only be called once - 404 is not transient
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_with_http_429_rate_limit(self):
        """Test that HTTP 429 (rate limit) is considered transient and retried."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=2, base_delay=0.01, max_delay=0.1)
        async def rate_limited_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                # Simulate HTTP 429 - transient rate limit error
                raise httpx.HTTPStatusError(
                    "Too Many Requests",
                    request=Mock(spec=httpx.Request),
                    response=Mock(status_code=429)
                )
            return "success"

        result = await rate_limited_operation()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_retry_with_http_500_server_error(self):
        """Test that HTTP 500 (server error) is considered transient and retried."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        async def server_error_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                # Simulate HTTP 500 - transient server error
                raise httpx.HTTPStatusError(
                    "Internal Server Error",
                    request=Mock(spec=httpx.Request),
                    response=Mock(status_code=500)
                )
            return "success"

        result = await server_error_operation()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_sync_retry_success_on_first_attempt(self):
        """Test that successful sync function returns immediately without retries."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        def successful_sync_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_sync_operation()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_sync_retry_success_after_transient_errors(self):
        """Test that retry eventually succeeds for sync functions after transient failures."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        def flaky_sync_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("Transient timeout")
            return "success"

        result = flaky_sync_operation()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_sync_retry_stops_on_non_transient_error(self):
        """Test that sync retry stops immediately on non-transient errors."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        def unauthorized_operation():
            nonlocal call_count
            call_count += 1
            # Simulate HTTP 401 - not a transient error
            raise httpx.HTTPStatusError(
                "Unauthorized",
                request=Mock(spec=httpx.Request),
                response=Mock(status_code=401)
            )

        with pytest.raises(httpx.HTTPStatusError):
            unauthorized_operation()

        # Should only be called once - 401 is not transient
        assert call_count == 1


class TestExponentialBackoffTiming:
    """Tests for exponential backoff timing and jitter."""

    @pytest.mark.asyncio
    async def test_exponential_backoff_delay_sequence(self):
        """Test that delays follow exponential backoff formula: min(base_delay * 2^attempt, max_delay)."""
        call_times = []

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.1,
            max_delay=1.0,
            jitter_factor=0.0  # Disable jitter for predictable timing
        )
        async def timed_failing_operation():
            call_times.append(time.time())
            raise TimeoutError("Test error")

        # Mock random to return 0 for consistent jitter calculation
        with patch('src.utils.git_retry.random.uniform', return_value=0.0):
            with pytest.raises(TimeoutError):
                await timed_failing_operation()

        assert len(call_times) == 4  # Initial + 3 retries

        # Calculate actual delays between attempts
        delays = [call_times[i] - call_times[i-1] for i in range(1, len(call_times))]

        # Expected delays with base_delay=0.1, max_delay=1.0:
        # attempt 0: 0.1 * 2^0 = 0.1s
        # attempt 1: 0.1 * 2^1 = 0.2s
        # attempt 2: 0.1 * 2^2 = 0.4s
        # All below max_delay (1.0s), so no capping

        assert delays[0] >= 0.08  # ~0.1s with tolerance
        assert delays[1] >= 0.18  # ~0.2s
        assert delays[2] >= 0.35  # ~0.4s

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Test that delays are capped at max_delay."""
        call_times = []

        @retry_with_exponential_backoff(
            max_retries=5,
            base_delay=0.2,
            max_delay=0.5,  # Cap at 0.5s
            jitter_factor=0.0
        )
        async def operation_with_cap():
            call_times.append(time.time())
            raise TimeoutError("Test error")

        with patch('src.utils.git_retry.random.uniform', return_value=0.0):
            with pytest.raises(TimeoutError):
                await operation_with_cap()

        delays = [call_times[i] - call_times[i-1] for i in range(1, len(call_times))]

        # Expected with base_delay=0.2, max_delay=0.5:
        # 0.2, 0.4, 0.5, 0.5, 0.5 (capped at 0.5s)
        # So we should see delays approaching but not exceeding 0.5s
        for delay in delays:
            assert delay <= 0.6  # Allow some tolerance for cap

    @pytest.mark.asyncio
    async def test_jitter_is_applied(self):
        """Test that jitter (±25%) is applied to delays."""
        call_count = 0
        recorded_delays = []

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.1,
            max_delay=1.0,
            jitter_factor=0.25
        )
        async def operation_with_jitter():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise TimeoutError("Test error")
            return "success"

        # Patch sleep to capture the delays being used
        original_sleep = asyncio.sleep
        sleep_delays = []

        async def mock_sleep(delay):
            sleep_delays.append(delay)
            await original_sleep(0)  # Don't actually sleep in test

        with patch('asyncio.sleep', side_effect=mock_sleep):
            result = await operation_with_jitter()

        assert result == "success"
        assert len(sleep_delays) == 3  # 3 retries before success

        # Verify that jitter was applied (delays should vary from pure exponential)
        # Expected pure exponential: 0.1, 0.2, 0.4
        # With jitter: should have variation
        base_delays = [0.1, 0.2, 0.4]
        for actual_delay, base_delay in zip(sleep_delays, base_delays):
            # Jitter should be within ±25% of base delay
            min_expected = base_delay * 0.75
            max_expected = base_delay * 1.25
            assert min_expected <= actual_delay <= max_expected


class TestRetryLogging:
    """Tests for retry logging functionality."""

    @pytest.mark.asyncio
    async def test_retry_logging_with_delay_and_attempt(self):
        """Test that retry attempts log delay and attempt number."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1
        )
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Test error")

        with patch('src.utils.git_retry.logger') as mock_logger:
            with pytest.raises(TimeoutError):
                await failing_operation()

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

    @pytest.mark.asyncio
    async def test_non_transient_error_logging(self):
        """Test that non-transient errors are logged with 'no retry' message."""
        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        async def non_transient_operation():
            raise httpx.HTTPStatusError(
                "Not Found",
                request=Mock(spec=httpx.Request),
                response=Mock(status_code=404)
            )

        with patch('src.utils.git_retry.logger') as mock_logger:
            with pytest.raises(httpx.HTTPStatusError):
                await non_transient_operation()

            # Should log error with "no retry" message
            error_calls = [str(call) for call in mock_logger.error.call_args_list]
            assert any("no retry" in call.lower() for call in error_calls)

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_logging(self):
        """Test that max retries exceeded is logged appropriately."""
        @retry_with_exponential_backoff(max_retries=2, base_delay=0.01, max_delay=0.1)
        async def failing_operation():
            raise TimeoutError("Persistent error")

        with patch('src.utils.git_retry.logger') as mock_logger:
            with pytest.raises(TimeoutError):
                await failing_operation()

            # Should log "max retries exceeded" message
            error_calls = [str(call) for call in mock_logger.error.call_args_list]
            assert any("max retries" in call.lower() for call in error_calls)
            assert any("exceeded" in call.lower() for call in error_calls)


class TestTransientErrorClassifier:
    """Tests that verify is_transient classifier from src.errors is used."""

    @pytest.mark.asyncio
    async def test_uses_is_transient_for_connection_errors(self):
        """Test that connection errors are identified as transient by is_transient."""
        @retry_with_exponential_backoff(max_retries=2, base_delay=0.01, max_delay=0.1)
        async def connection_error_operation():
            raise httpx.ConnectError("Connection refused")

        # Should retry because is_transient identifies connection errors as transient
        with patch('src.utils.git_retry.logger') as mock_logger:
            with pytest.raises(httpx.ConnectError):
                await connection_error_operation()

            # Verify that retry warnings were logged (proving retries occurred)
            warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
            # Should have at least 2 retry attempts (max_retries=2)
            assert len(warning_calls) >= 2
            # Verify the log mentions retries
            assert any("attempt" in call.lower() and "retrying" in call.lower() for call in warning_calls)

    @pytest.mark.asyncio
    async def test_uses_is_transient_for_timeout_errors(self):
        """Test that timeout errors are identified as transient by is_transient."""
        @retry_with_exponential_backoff(max_retries=2, base_delay=0.01, max_delay=0.1)
        async def timeout_operation():
            raise TimeoutError("Operation timed out")

        # Should retry because is_transient identifies timeouts as transient
        with pytest.raises(TimeoutError):
            await timeout_operation()

    @pytest.mark.asyncio
    async def test_respects_is_transient_for_401_unauthorized(self):
        """Test that 401 errors are not retried because is_transient returns False."""
        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        async def unauthorized_operation():
            raise httpx.HTTPStatusError(
                "Unauthorized",
                request=Mock(spec=httpx.Request),
                response=Mock(status_code=401)
            )

        # Should NOT retry - 401 is not transient
        with pytest.raises(httpx.HTTPStatusError):
            await unauthorized_operation()

    @pytest.mark.asyncio
    async def test_respects_is_transient_for_403_forbidden(self):
        """Test that 403 errors are not retried because is_transient returns False."""
        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        async def forbidden_operation():
            raise httpx.HTTPStatusError(
                "Forbidden",
                request=Mock(spec=httpx.Request),
                response=Mock(status_code=403)
            )

        # Should NOT retry - 403 is not transient
        with pytest.raises(httpx.HTTPStatusError):
            await forbidden_operation()

    @pytest.mark.asyncio
    async def test_retries_git_network_error(self):
        """Test that GitNetworkError is retried because is_transient returns True."""
        from src.action.steps.git_validation import GitNetworkError

        call_count = 0

        @retry_with_exponential_backoff(max_retries=2, base_delay=0.01, max_delay=0.1)
        async def git_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise GitNetworkError("git fetch: connection timeout")
            return "success"

        result = await git_operation()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_git_authentication_error(self):
        """Test that GitAuthenticationError is not retried because is_transient returns False."""
        from src.action.steps.git_validation import GitAuthenticationError

        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        async def git_auth_operation():
            nonlocal call_count
            call_count += 1
            raise GitAuthenticationError("git push: authentication failed")

        with pytest.raises(GitAuthenticationError):
            await git_auth_operation()

        # Should only be called once (no retries for auth errors)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_git_conflict_error(self):
        """Test that GitConflictError is not retried because is_transient returns False."""
        from src.action.steps.git_validation import GitConflictError

        call_count = 0

        @retry_with_exponential_backoff(max_retries=3, base_delay=0.01, max_delay=0.1)
        async def git_merge_operation():
            nonlocal call_count
            call_count += 1
            raise GitConflictError("git merge: conflict in main.py")

        with pytest.raises(GitConflictError):
            await git_merge_operation()

        # Should only be called once (no retries for conflict errors)
        assert call_count == 1


class TestRealWorldScenarios:
    """Test retry decorator with realistic scenarios."""

    @pytest.mark.asyncio
    async def test_git_operation_with_transient_network_error(self):
        """Test retry logic for git operations with transient network errors."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1
        )
        async def git_push():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("git push: connection timeout")
            return "push successful"

        result = await git_push()
        assert result == "push successful"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_network_request_with_intermittent_failures(self):
        """Test retry logic for network requests with intermittent failures."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=5,
            base_delay=0.05,
            max_delay=2.0
        )
        async def fetch_url():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise httpx.ConnectError("Connection reset by peer")
            if call_count == 3:
                raise httpx.RemoteProtocolError("Server closed connection")
            return {"status": "200 OK", "data": "response"}

        result = await fetch_url()
        assert result == {"status": "200 OK", "data": "response"}
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_database_connection_with_rate_limiting(self):
        """Test retry logic for database connection with rate limiting."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=4,
            base_delay=1.0,
            max_delay=10.0,
            jitter_factor=0.25
        )
        async def db_query():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise aiohttp.ClientResponseError(
                    request_info=Mock(),
                    history=(),
                    status=429,
                    message="Too many requests"
                )
            return {"rows": 10}

        result = await db_query()
        assert result == {"rows": 10}
        assert call_count == 3


class TestIsTransientErrorPatternMatching:
    """Test is_transient_error function with pattern matching."""

    def test_transient_error_pattern_timeout(self):
        """Test that timeout patterns are detected as transient."""
        from src.utils.git_retry import is_transient_error

        error = TimeoutError("Connection timeout")
        assert is_transient_error(error) is True

        error = Exception("Operation timed out")
        assert is_transient_error(error) is True

    def test_transient_error_pattern_connection(self):
        """Test that connection patterns are detected as transient."""
        from src.utils.git_retry import is_transient_error

        error = Exception("Connection refused")
        assert is_transient_error(error) is True

        error = Exception("Network unreachable")
        assert is_transient_error(error) is True

        error = Exception("Connection reset by peer")
        assert is_transient_error(error) is True

    def test_transient_error_pattern_dns(self):
        """Test that DNS patterns are detected as transient."""
        from src.utils.git_retry import is_transient_error

        error = Exception("DNS resolution failed")
        assert is_transient_error(error) is True

        error = Exception("Temporary DNS error")
        assert is_transient_error(error) is True

    def test_transient_error_subprocess_timeout(self):
        """Test that subprocess.TimeoutExpired is detected as transient."""
        from src.utils.git_retry import is_transient_error
        import subprocess

        error = subprocess.TimeoutExpired("git", 5)
        assert is_transient_error(error) is True

    def test_transient_error_subprocess_with_transient_stderr(self):
        """Test that CalledProcessError with transient stderr is detected."""
        from src.utils.git_retry import is_transient_error
        import subprocess

        error = subprocess.CalledProcessError(1, "git", stderr="Connection timed out")
        assert is_transient_error(error) is True

    def test_non_transient_error_patterns(self):
        """Test that non-transient patterns are not detected as transient."""
        from src.utils.git_retry import is_transient_error

        error = Exception("Permission denied")
        assert is_transient_error(error) is False

        error = Exception("Invalid argument")
        assert is_transient_error(error) is False

    def test_git_network_error_is_transient(self):
        """Test that GitNetworkError is always detected as transient."""
        from src.utils.git_retry import is_transient_error
        from src.action.steps.git_validation import GitNetworkError

        error = GitNetworkError("Network error")
        assert is_transient_error(error) is True


class TestRetryOnTransientErrorDecorator:
    """Test retry_on_transient_error decorator."""

    def test_retry_on_transient_error_success_after_retries(self):
        """Test that retry succeeds after transient errors."""
        from src.utils.git_retry import retry_on_transient_error

        call_count = 0

        @retry_on_transient_error(max_retries=3, initial_delay=0.01)
        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection timeout")
            return "success"

        result = flaky_operation()
        assert result == "success"
        assert call_count == 3

    def test_retry_on_transient_error_exhausted(self):
        """Test that retry fails after max retries exhausted."""
        from src.utils.git_retry import retry_on_transient_error

        call_count = 0

        @retry_on_transient_error(max_retries=2, initial_delay=0.01)
        def failing_operation():
            nonlocal call_count
            call_count += 1
            raise Exception("Connection timeout")

        with pytest.raises(Exception, match="Connection timeout"):
            failing_operation()

        assert call_count == 3  # Initial + 2 retries

    def test_retry_on_transient_error_no_retry_on_permanent(self):
        """Test that permanent errors are not retried."""
        from src.utils.git_retry import retry_on_transient_error

        call_count = 0

        @retry_on_transient_error(max_retries=3, initial_delay=0.01)
        def permanent_error_operation():
            nonlocal call_count
            call_count += 1
            raise Exception("Permission denied")

        with pytest.raises(Exception, match="Permission denied"):
            permanent_error_operation()

        # Should only be called once (no retries for permanent errors)
        assert call_count == 1

    def test_retry_on_transient_error_with_specific_exception_types(self):
        """Test retry with specific exception types."""
        from src.utils.git_retry import retry_on_transient_error

        call_count = 0

        @retry_on_transient_error(
            max_retries=3,
            retry_on=(ValueError,),
            initial_delay=0.01
        )
        def selective_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Retry this")
            return "success"

        result = selective_operation()
        assert result == "success"
        assert call_count == 2

    def test_retry_on_transient_error_exponential_backoff(self):
        """Test exponential backoff with custom backoff_factor."""
        from src.utils.git_retry import retry_on_transient_error
        import time

        call_times = []

        @retry_on_transient_error(
            max_retries=3,
            backoff_factor=2.0,
            initial_delay=0.05
        )
        def timed_operation():
            call_times.append(time.time())
            raise Exception("Connection timeout")

        with pytest.raises(Exception):
            timed_operation()

        # Verify exponential backoff timing
        delays = [call_times[i] - call_times[i-1] for i in range(1, len(call_times))]
        # With backoff_factor=2.0: 0.05, 0.1, 0.2
        assert delays[0] >= 0.04  # ~0.05s
        assert delays[1] >= 0.08  # ~0.1s

    def test_retry_on_transient_error_no_retry_git_auth_error(self):
        """Test that GitAuthenticationError is not retried."""
        from src.utils.git_retry import retry_on_transient_error
        from src.action.steps.git_validation import GitAuthenticationError

        call_count = 0

        @retry_on_transient_error(max_retries=3, initial_delay=0.01)
        def auth_error_operation():
            nonlocal call_count
            call_count += 1
            raise GitAuthenticationError("Authentication failed")

        with pytest.raises(GitAuthenticationError):
            auth_error_operation()

        # Should only be called once (no retries for auth errors)
        assert call_count == 1

    def test_retry_on_transient_error_no_retry_git_conflict_error(self):
        """Test that GitConflictError is not retried."""
        from src.utils.git_retry import retry_on_transient_error
        from src.action.steps.git_validation import GitConflictError

        call_count = 0

        @retry_on_transient_error(max_retries=3, initial_delay=0.01)
        def conflict_error_operation():
            nonlocal call_count
            call_count += 1
            raise GitConflictError("Merge conflict")

        with pytest.raises(GitConflictError):
            conflict_error_operation()

        # Should only be called once (no retries for conflict errors)
        assert call_count == 1


class TestRetryOnTransientErrorAsync:
    """Test retry_on_transient_error_async decorator."""

    @pytest.mark.asyncio
    async def test_async_retry_on_transient_error_success(self):
        """Test async retry succeeds after transient errors."""
        from src.utils.git_retry import retry_on_transient_error_async

        call_count = 0

        @retry_on_transient_error_async(max_retries=3, initial_delay=0.01)
        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection timeout")
            return "success"

        result = await flaky_operation()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_exhausted(self):
        """Test async retry fails after max retries exhausted."""
        from src.utils.git_retry import retry_on_transient_error_async

        call_count = 0

        @retry_on_transient_error_async(max_retries=2, initial_delay=0.01)
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise Exception("Connection timeout")

        with pytest.raises(Exception, match="Connection timeout"):
            await failing_operation()

        assert call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_async_retry_no_retry_on_permanent(self):
        """Test async retry doesn't retry permanent errors."""
        from src.utils.git_retry import retry_on_transient_error_async

        call_count = 0

        @retry_on_transient_error_async(max_retries=3, initial_delay=0.01)
        async def permanent_error_operation():
            nonlocal call_count
            call_count += 1
            raise Exception("Permission denied")

        with pytest.raises(Exception, match="Permission denied"):
            await permanent_error_operation()

        # Should only be called once (no retries for permanent errors)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_exponential_backoff(self):
        """Test async exponential backoff with mocked sleep."""
        from src.utils.git_retry import retry_on_transient_error_async
        from unittest.mock import patch

        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_on_transient_error_async(
            max_retries=3,
            backoff_factor=2.0,
            initial_delay=0.1
        )
        async def failing_operation():
            raise Exception("Connection timeout")

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(Exception):
                await failing_operation()

        # Should have slept 3 times (3 retries)
        assert len(sleep_times) == 3

        # Exponential backoff: 0.1, 0.2, 0.4 (backoff_factor=2.0)
        assert sleep_times[0] == 0.1
        assert sleep_times[1] == 0.2
        assert sleep_times[2] == 0.4


class TestRetryTracker:
    """Test RetryTracker class for statistics tracking."""

    def test_retry_tracker_initialization(self):
        """Test RetryTracker initializes with zero values."""
        from src.utils.git_retry import RetryTracker

        tracker = RetryTracker()

        assert tracker.total_attempts == 0
        assert tracker.total_retries == 0
        assert tracker.failed_operations == 0
        assert tracker.successful_operations == 0
        assert tracker.operation_history == []

    def test_retry_tracker_record_attempt_success(self):
        """Test recording a successful operation attempt."""
        from src.utils.git_retry import RetryTracker

        tracker = RetryTracker()
        tracker.record_attempt("git_push", attempt=0, success=True)

        assert tracker.total_attempts == 1
        assert tracker.total_retries == 0
        assert tracker.successful_operations == 1
        assert tracker.failed_operations == 0
        assert len(tracker.operation_history) == 1

        history = tracker.operation_history[0]
        assert history["operation"] == "git_push"
        assert history["attempt"] == 0
        assert history["success"] is True
        assert history["error"] is None

    def test_retry_tracker_record_retry(self):
        """Test recording a retry attempt."""
        from src.utils.git_retry import RetryTracker

        tracker = RetryTracker()
        tracker.record_attempt("git_push", attempt=1, success=False, error="Connection timeout")

        assert tracker.total_attempts == 1
        assert tracker.total_retries == 1  # attempt > 0 counts as retry
        assert tracker.successful_operations == 0
        assert tracker.failed_operations == 1

        history = tracker.operation_history[0]
        assert history["attempt"] == 1
        assert history["success"] is False
        assert history["error"] == "Connection timeout"

    def test_retry_tracker_multiple_attempts(self):
        """Test recording multiple attempts."""
        from src.utils.git_retry import RetryTracker

        tracker = RetryTracker()
        tracker.record_attempt("git_push", attempt=0, success=False, error="Network error")
        tracker.record_attempt("git_push", attempt=1, success=False, error="Network error")
        tracker.record_attempt("git_push", attempt=2, success=True)

        assert tracker.total_attempts == 3
        assert tracker.total_retries == 2  # attempts 1 and 2
        assert tracker.successful_operations == 1
        assert tracker.failed_operations == 2
        assert len(tracker.operation_history) == 3

    def test_retry_tracker_get_statistics(self):
        """Test getting retry statistics."""
        from src.utils.git_retry import RetryTracker

        tracker = RetryTracker()
        tracker.record_attempt("git_push", attempt=0, success=False, error="Network error")
        tracker.record_attempt("git_push", attempt=1, success=False, error="Network error")
        tracker.record_attempt("git_push", attempt=2, success=True)

        stats = tracker.get_statistics()

        assert stats["total_attempts"] == 3
        assert stats["total_retries"] == 2
        assert stats["successful_operations"] == 1
        assert stats["failed_operations"] == 2
        assert stats["retry_rate"] == 2/3

    def test_retry_tracker_zero_attempts_statistics(self):
        """Test statistics with zero attempts."""
        from src.utils.git_retry import RetryTracker

        tracker = RetryTracker()
        stats = tracker.get_statistics()

        assert stats["retry_rate"] == 0  # No division by zero

    def test_retry_tracker_reset(self):
        """Test resetting tracker statistics."""
        from src.utils.git_retry import RetryTracker

        tracker = RetryTracker()
        tracker.record_attempt("git_push", attempt=0, success=True)
        tracker.record_attempt("git_push", attempt=1, success=False, error="Network error")

        tracker.reset()

        assert tracker.total_attempts == 0
        assert tracker.total_retries == 0
        assert tracker.successful_operations == 0
        assert tracker.failed_operations == 0
        assert tracker.operation_history == []

    def test_global_retry_tracker(self):
        """Test global retry tracker instance."""
        from src.utils.git_retry import get_retry_tracker, RetryTracker

        tracker = get_retry_tracker()
        assert isinstance(tracker, RetryTracker)

        # Should return the same instance
        tracker2 = get_retry_tracker()
        assert tracker is tracker2

    def test_retry_tracker_multiple_operations(self):
        """Test tracking different operation types."""
        from src.utils.git_retry import RetryTracker

        tracker = RetryTracker()
        tracker.record_attempt("git_push", attempt=0, success=True)
        tracker.record_attempt("git_fetch", attempt=0, success=False, error="Network error")
        tracker.record_attempt("git_clone", attempt=1, success=True)

        assert tracker.total_attempts == 3
        assert tracker.total_retries == 1
        assert tracker.successful_operations == 2
        assert tracker.failed_operations == 1

        # Verify operation names are preserved
        operations = [h["operation"] for h in tracker.operation_history]
        assert "git_push" in operations
        assert "git_fetch" in operations
        assert "git_clone" in operations
