"""
Comprehensive tests for retry behavior, backoff, jitter, and error classification.

Tests cover:
- Error classifier with all transient error types
- Classifier rejects permanent errors (404, 403, etc.)
- Retry succeeds after 1 and 2 transient failures
- Retry fails after max retries exhausted
- Exponential backoff timing (with mocked sleep)
- Jitter randomness (statistical test)
- Non-transient errors fail immediately (no retry)
- Per-call override works
- Integration test: git push with retry
"""
import asyncio
import errno
import random
import socket
import time
from unittest.mock import Mock, patch, MagicMock
from unittest.mock import AsyncMock
import pytest
import httpx
import aiohttp
import subprocess

from src.errors.transient_errors import is_transient, get_error_category
from src.utilities.retry import (
    retry_with_exponential_backoff,
    retry_async,
    retry_sync,
    RetryContext,
    _apply_jitter,
)
from src.utils.git_retry import retry_with_exponential_backoff as git_retry_with_exponential_backoff
from src.config.retry import RetryConfig, set_retry_config, get_retry_config


class TestErrorClassifier:
    """Test error classifier with all transient and permanent error types."""

    # Test transient error types - should return True
    @pytest.mark.asyncio
    async def test_classifier_http_transient_5xx_errors(self):
        """Test classifier accepts HTTP 5xx server errors as transient."""
        # Mock httpx response with 500 status
        mock_response = Mock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError("Internal Server Error", request=Mock(), response=mock_response)
        assert is_transient(error) is True

        mock_response.status_code = 502
        error = httpx.HTTPStatusError("Bad Gateway", request=Mock(), response=mock_response)
        assert is_transient(error) is True

        mock_response.status_code = 503
        error = httpx.HTTPStatusError("Service Unavailable", request=Mock(), response=mock_response)
        assert is_transient(error) is True

        mock_response.status_code = 504
        error = httpx.HTTPStatusError("Gateway Timeout", request=Mock(), response=mock_response)
        assert is_transient(error) is True

    @pytest.mark.asyncio
    async def test_classifier_http_rate_limit_429(self):
        """Test classifier accepts HTTP 429 rate limiting as transient."""
        mock_response = Mock()
        mock_response.status_code = 429
        error = httpx.HTTPStatusError("Too Many Requests", request=Mock(), response=mock_response)
        assert is_transient(error) is True

    @pytest.mark.asyncio
    async def test_classifier_timeouts(self):
        """Test classifier accepts all timeout variants as transient."""
        # httpx timeout
        error = httpx.TimeoutException("Request timeout")
        assert is_transient(error) is True

        # aiohttp timeout
        error = aiohttp.ClientTimeout("Request timeout")
        assert is_transient(error) is True

        error = aiohttp.ServerTimeoutError("Server timeout")
        assert is_transient(error) is True

        # Python TimeoutError
        error = TimeoutError("Timeout")
        assert is_transient(error) is True

        # socket.timeout
        error = socket.timeout("Socket timeout")
        assert is_transient(error) is True

    @pytest.mark.asyncio
    async def test_classifier_connection_errors(self):
        """Test classifier accepts connection errors as transient."""
        # httpx network errors
        error = httpx.ConnectError("Connection refused")
        assert is_transient(error) is True

        error = httpx.ReadError("Network read error")
        assert is_transient(error) is True

        error = httpx.WriteError("Network write error")
        assert is_transient(error) is True

        error = httpx.RemoteProtocolError("Remote closed connection")
        assert is_transient(error) is True

        # aiohttp connection errors
        error = aiohttp.ClientConnectionError("Connection failed")
        assert is_transient(error) is True

    @pytest.mark.asyncio
    async def test_classifier_os_transient_errors(self):
        """Test classifier accepts transient OS/network errors."""
        # Connection refused
        error = OSError(errno.ECONNREFUSED, "Connection refused")
        assert is_transient(error) is True

        # Connection reset
        error = OSError(errno.ECONNRESET, "Connection reset")
        assert is_transient(error) is True

        # Timeout
        error = OSError(errno.ETIMEDOUT, "Connection timed out")
        assert is_transient(error) is True

        # Host unreachable
        error = OSError(errno.EHOSTUNREACH, "No route to host")
        assert is_transient(error) is True

        # Broken pipe
        error = OSError(errno.EPIPE, "Broken pipe")
        assert is_transient(error) is True

    # Test permanent error types - should return False
    @pytest.mark.asyncio
    async def test_classifier_rejects_permanent_http_client_errors(self):
        """Test classifier rejects permanent HTTP 4xx client errors."""
        # Mock httpx response with permanent error codes
        permanent_codes = [400, 401, 403, 404, 405, 406, 409, 410, 412, 413, 414, 415, 422, 423, 424]

        for code in permanent_codes:
            mock_response = Mock()
            mock_response.status_code = code
            error = httpx.HTTPStatusError(f"HTTP {code}", request=Mock(), response=mock_response)
            assert is_transient(error) is False, f"HTTP {code} should be permanent (not transient)"

    @pytest.mark.asyncio
    async def test_classifier_rejects_404_not_found(self):
        """Test classifier specifically rejects HTTP 404."""
        mock_response = Mock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=Mock(), response=mock_response)
        assert is_transient(error) is False

    @pytest.mark.asyncio
    async def test_classifier_rejects_403_forbidden(self):
        """Test classifier specifically rejects HTTP 403."""
        mock_response = Mock()
        mock_response.status_code = 403
        error = httpx.HTTPStatusError("Forbidden", request=Mock(), response=mock_response)
        assert is_transient(error) is False

    @pytest.mark.asyncio
    async def test_classifier_rejects_401_unauthorized(self):
        """Test classifier specifically rejects HTTP 401."""
        mock_response = Mock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError("Unauthorized", request=Mock(), response=mock_response)
        assert is_transient(error) is False

    @pytest.mark.asyncio
    async def test_classifier_rejects_unsupported_protocol(self):
        """Test classifier rejects unsupported protocol errors."""
        error = httpx.UnsupportedProtocol("Unsupported protocol")
        assert is_transient(error) is False

    @pytest.mark.asyncio
    async def test_classifier_rejects_permanent_os_errors(self):
        """Test classifier rejects permanent OS errors."""
        # Permission denied
        error = OSError(errno.EACCES, "Permission denied")
        assert is_transient(error) is False

        # Address in use
        error = OSError(errno.EADDRINUSE, "Address already in use")
        assert is_transient(error) is False

        # Invalid argument
        error = OSError(errno.EINVAL, "Invalid argument")
        assert is_transient(error) is False

        # Bad file descriptor
        error = OSError(errno.EBADF, "Bad file descriptor")
        assert is_transient(error) is False

    @pytest.mark.asyncio
    async def test_classifier_unknown_errors(self):
        """Test classifier returns False for unknown error types."""
        # Generic exception without specific classification
        error = ValueError("Unknown error")
        assert is_transient(error) is False

        error = RuntimeError("Unexpected failure")
        assert is_transient(error) is False

        # None input
        assert is_transient(None) is False


class TestExponentialBackoffTiming:
    """Test exponential backoff timing with mocked sleep for fast tests."""

    @pytest.mark.asyncio
    async def test_exponential_backoff_with_mocked_sleep(self):
        """Test exponential backoff progression using mocked sleep."""
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
            jitter_factor=0.0,  # No jitter for predictable timing
            exceptions=(ValueError,)
        )
        async def failing_operation():
            raise ValueError("Test error")

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await failing_operation()

        # Should have slept 3 times (3 retries)
        assert len(sleep_times) == 3

        # Exponential backoff: 1.0, 2.0, 4.0 (each attempt doubles)
        # Note: attempt 0 delays 1.0, attempt 1 delays 2.0, attempt 2 delays 4.0
        assert sleep_times[0] == 1.0
        assert sleep_times[1] == 2.0
        assert sleep_times[2] == 4.0

    @pytest.mark.asyncio
    async def test_max_delay_cap_with_mocked_sleep(self):
        """Test that delay is capped at max_delay."""
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_with_exponential_backoff(
            max_retries=5,
            base_delay=1.0,
            max_delay=2.0,  # Low max delay cap
            jitter_factor=0.0,
            exceptions=(ValueError,)
        )
        async def failing_operation():
            raise ValueError("Test error")

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await failing_operation()

        # Should have 5 retries
        assert len(sleep_times) == 5

        # Without cap: 1.0, 2.0, 4.0, 8.0, 16.0
        # With max_delay=2.0: 1.0, 2.0, 2.0, 2.0, 2.0
        assert sleep_times[0] == 1.0
        assert sleep_times[1] == 2.0
        assert sleep_times[2] == 2.0  # Capped
        assert sleep_times[3] == 2.0  # Capped
        assert sleep_times[4] == 2.0  # Capped

    @pytest.mark.asyncio
    async def test_no_retry_on_first_success(self):
        """Test that no sleep occurs on first attempt success."""
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
            jitter_factor=0.0,
            exceptions=(ValueError,)
        )
        async def successful_operation():
            return "success"

        with patch('asyncio.sleep', side_effect=mock_sleep):
            result = await successful_operation()

        assert result == "success"
        assert len(sleep_times) == 0  # No sleep on success

    @pytest.mark.asyncio
    async def test_exponential_backoff_formula(self):
        """Test the exact formula: min(base_delay * 2^attempt, max_delay)."""
        test_cases = [
            # (base_delay, max_delay, attempt, expected_delay)
            (1.0, 100.0, 0, 1.0),    # 1.0 * 2^0 = 1.0
            (1.0, 100.0, 1, 2.0),    # 1.0 * 2^1 = 2.0
            (1.0, 100.0, 2, 4.0),    # 1.0 * 2^2 = 4.0
            (1.0, 100.0, 3, 8.0),    # 1.0 * 2^3 = 8.0
            (2.0, 100.0, 0, 2.0),    # 2.0 * 2^0 = 2.0
            (2.0, 100.0, 1, 4.0),    # 2.0 * 2^1 = 4.0
            (5.0, 20.0, 0, 5.0),     # 5.0 * 2^0 = 5.0
            (5.0, 20.0, 1, 10.0),    # 5.0 * 2^1 = 10.0
            (5.0, 20.0, 2, 20.0),    # 5.0 * 2^2 = 20.0 (capped)
            (5.0, 15.0, 2, 15.0),    # 5.0 * 2^2 = 20.0 → capped at 15.0
        ]

        for base_delay, max_delay, attempt, expected in test_cases:
            sleep_times = []

            async def mock_sleep(duration):
                sleep_times.append(duration)

            @retry_with_exponential_backoff(
                max_retries=attempt + 1,  # Ensure we reach this attempt
                base_delay=base_delay,
                max_delay=max_delay,
                jitter_factor=0.0,
                exceptions=(ValueError,)
            )
            async def failing_operation():
                raise ValueError("Test error")

            with patch('asyncio.sleep', side_effect=mock_sleep):
                with pytest.raises(ValueError):
                    await failing_operation()

            # Check the sleep time at the specific attempt
            assert sleep_times[attempt] == expected, \
                f"base_delay={base_delay}, max_delay={max_delay}, attempt={attempt}: " \
                f"expected {expected}, got {sleep_times[attempt]}"


class TestJitterRandomness:
    """Test jitter behavior with statistical analysis."""

    def test_apply_jitter_deterministic_seed(self):
        """Test that jitter is deterministic with the same random seed."""
        random.seed(42)
        delay1 = _apply_jitter(10.0, 0.25)

        random.seed(42)
        delay2 = _apply_jitter(10.0, 0.25)

        assert delay1 == delay2, "Same seed should produce same jitter"

    def test_jitter_bounds(self):
        """Test that jitter stays within expected bounds."""
        base_delay = 10.0
        jitter_factor = 0.25

        delays = []
        for _ in range(100):
            delay = _apply_jitter(base_delay, jitter_factor)
            delays.append(delay)

        # All delays should be within ±25% of base delay
        min_delay = base_delay - (base_delay * jitter_factor)
        max_delay = base_delay + (base_delay * jitter_factor)

        assert all(min_delay <= d <= max_delay for d in delays), \
            f"All delays should be between {min_delay} and {max_delay}"

    def test_jitter_randomness_statistical(self):
        """Test that jitter introduces randomness (statistical test)."""
        base_delay = 10.0
        jitter_factor = 0.25
        sample_size = 100

        delays = [_apply_jitter(base_delay, jitter_factor) for _ in range(sample_size)]

        # Not all delays should be the same (randomness)
        unique_delays = len(set(delays))
        assert unique_delays > sample_size * 0.9, \
            "Jitter should produce highly varied delays (statistical randomness)"

        # Average should be close to base_delay (unbiased randomness)
        average = sum(delays) / len(delays)
        assert abs(average - base_delay) < 0.5, \
            f"Average delay {average} should be close to base delay {base_delay}"

    def test_jitter_zero_factor(self):
        """Test that jitter_factor=0 produces no variation."""
        base_delay = 10.0

        delays = [_apply_jitter(base_delay, 0.0) for _ in range(10)]

        # All delays should be exactly the base delay
        assert all(d == base_delay for d in delays), \
            "jitter_factor=0 should produce no variation"

    def test_full_jitter(self):
        """Test full jitter (factor=1.0) produces values between 0 and base_delay."""
        base_delay = 10.0

        delays = [_apply_jitter(base_delay, 1.0) for _ in range(100)]

        # All delays should be between 0 and base_delay
        assert all(0 <= d <= base_delay for d in delays), \
            "Full jitter should produce delays between 0 and base_delay"

        # Should have good distribution
        average = sum(delays) / len(delays)
        # Average for full jitter should be around half of base_delay
        assert 3.0 <= average <= 7.0, \
            f"Full jitter average {average} should be around half of base delay"

    def test_jitter_distribution_spread(self):
        """Test that jitter produces a good spread of values."""
        base_delay = 10.0
        jitter_factor = 0.25
        sample_size = 1000

        delays = [_apply_jitter(base_delay, jitter_factor) for _ in range(sample_size)]

        # Check spread: we should see values across the range
        min_delay = base_delay - (base_delay * jitter_factor)
        max_delay = base_delay + (base_delay * jitter_factor)
        range_size = max_delay - min_delay

        # Divide range into bins and check distribution
        bin_count = 10
        bin_size = range_size / bin_count
        bins = [0] * bin_count

        for delay in delays:
            bin_index = int((delay - min_delay) / bin_size)
            if bin_index >= bin_count:
                bin_index = bin_count - 1
            bins[bin_index] += 1

        # Most bins should have some values (good distribution)
        filled_bins = sum(1 for count in bins if count > 0)
        assert filled_bins >= bin_count * 0.8, \
            "Jitter should distribute values across the range"


class TestNonTransientErrors:
    """Test that non-transient errors fail immediately without retry."""

    @pytest.mark.asyncio
    async def test_404_fails_immediately(self):
        """Test HTTP 404 fails immediately without retry."""
        call_count = 0

        @git_retry_with_exponential_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
        )
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            mock_response = Mock()
            mock_response.status_code = 404
            raise httpx.HTTPStatusError("Not Found", request=Mock(), response=mock_response)

        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(httpx.HTTPStatusError):
                await failing_operation()

        # Should only be called once (no retries for 404)
        assert call_count == 1
        assert len(sleep_times) == 0

    @pytest.mark.asyncio
    async def test_403_fails_immediately(self):
        """Test HTTP 403 fails immediately without retry."""
        call_count = 0

        @git_retry_with_exponential_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
        )
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            mock_response = Mock()
            mock_response.status_code = 403
            raise httpx.HTTPStatusError("Forbidden", request=Mock(), response=mock_response)

        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(httpx.HTTPStatusError):
                await failing_operation()

        # Should only be called once (no retries for 403)
        assert call_count == 1
        assert len(sleep_times) == 0

    @pytest.mark.asyncio
    async def test_value_error_with_generic_exception_catching(self):
        """Test that ValueError is not retried if not in exceptions tuple."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
            exceptions=(httpx.HTTPStatusError,)  # Only catch HTTP errors
        )
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Some error")

        with pytest.raises(ValueError):
            await failing_operation()

        # Should only be called once (ValueError not in exceptions)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_permanent_os_error_fails_immediately(self):
        """Test permanent OS errors fail immediately."""
        call_count = 0

        @git_retry_with_exponential_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
        )
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise OSError(errno.EACCES, "Permission denied")

        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(OSError):
                await failing_operation()

        # Should only be called once (no retries for permanent OS errors)
        assert call_count == 1
        assert len(sleep_times) == 0


class TestRetryWithTransientErrors:
    """Test retry behavior with transient errors."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_1_transient_failure(self):
        """Test retry succeeds after 1 transient failure."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        )
        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Transient error")
            return "success"

        result = await flaky_operation()
        assert result == "success"
        assert call_count == 2  # First attempt failed, retry succeeded

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_2_transient_failures(self):
        """Test retry succeeds after 2 transient failures."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        )
        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("Transient error")
            return "success"

        result = await flaky_operation()
        assert result == "success"
        assert call_count == 3  # Two failures, third attempt succeeded

    @pytest.mark.asyncio
    async def test_retry_fails_after_max_retries_exhausted(self):
        """Test retry fails after max retries are exhausted."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        )
        async def always_failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Persistent error")

        with pytest.raises(ValueError, match="Persistent error"):
            await always_failing_operation()

        # Should attempt initial + 2 retries = 3 total
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_with_timeout_error(self):
        """Test retry with timeout errors (transient)."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(TimeoutError,)
        )
        async def timeout_operation():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise TimeoutError("Timeout")
            return "success"

        result = await timeout_operation()
        assert result == "success"
        assert call_count == 3


class TestPerCallOverride:
    """Test per-call parameter override functionality."""

    @pytest.mark.asyncio
    async def test_decorator_override_max_retries(self):
        """Test decorator with max_retries override."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=1, base_delay=0.01, max_delay=0.1)
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            await failing_operation()

        # Should attempt initial + 1 retry
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_override_base_delay(self):
        """Test decorator with base_delay override."""
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_with_exponential_backoff(
            max_retries=1,
            base_delay=0.5,
            max_delay=10.0,
            jitter_factor=0.0
        )
        async def failing_operation():
            raise ValueError("Test error")

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await failing_operation()

        # Should use custom base_delay of 0.5
        assert len(sleep_times) == 1
        assert sleep_times[0] == 0.5

    @pytest.mark.asyncio
    async def test_decorator_override_exceptions(self):
        """Test decorator with specific exception types override."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)  # Only retry on ValueError
        )
        async def selective_operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Retry this")
            elif call_count == 2:
                raise TypeError("Don't retry this")
            return "success"

        # Should retry ValueError but not TypeError
        with pytest.raises(TypeError):
            await selective_operation()

        assert call_count == 2  # First attempt (ValueError) + 1 retry

    @pytest.mark.asyncio
    async def test_retry_async_override_params(self):
        """Test retry_async helper with parameter overrides."""
        call_count = 0

        async def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            await retry_async(
                failing_function,
                max_retries=2,  # Override max retries
                base_delay=0.01,
                max_delay=0.1
            )

        assert call_count == 3  # Initial + 2 retries

    def test_retry_sync_override_params(self):
        """Test retry_sync helper with parameter overrides."""
        call_count = 0

        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            retry_sync(
                failing_function,
                max_retries=2,  # Override max retries
                base_delay=0.01,
                max_delay=0.1
            )

        assert call_count == 3  # Initial + 2 retries


class TestGitPushIntegration:
    """Integration tests for git push with retry behavior."""

    @pytest.mark.asyncio
    async def test_git_push_transient_network_error_retry(self):
        """Test git push with transient network error triggers retry."""
        call_count = 0
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        async def mock_git_push():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate transient network error
                raise httpx.ConnectError("Connection refused")
            return "Push successful"

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
            jitter_factor=0.0,
            exceptions=(httpx.ConnectError,)
        )
        async def git_push_with_retry():
            return await mock_git_push()

        with patch('asyncio.sleep', side_effect=mock_sleep):
            result = await git_push_with_retry()

        assert result == "Push successful"
        assert call_count == 2  # First attempt failed, retry succeeded
        assert len(sleep_times) == 1  # Slept once before retry
        assert sleep_times[0] == 1.0  # Used base_delay

    @pytest.mark.asyncio
    async def test_git_push_permanent_error_no_retry(self):
        """Test git push with permanent error (404) fails immediately."""
        call_count = 0
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        async def mock_git_push():
            nonlocal call_count
            call_count += 1
            # Simulate permanent error (404 - repository not found)
            mock_response = Mock()
            mock_response.status_code = 404
            raise httpx.HTTPStatusError("Repository not found", request=Mock(), response=mock_response)

        @git_retry_with_exponential_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
            jitter_factor=0.0,
        )
        async def git_push_with_retry():
            return await mock_git_push()

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(httpx.HTTPStatusError):
                await git_push_with_retry()

        # Should only attempt once (no retry on 404)
        assert call_count == 1
        assert len(sleep_times) == 0

    @pytest.mark.asyncio
    async def test_git_push_exponential_backoff_sequence(self):
        """Test git push with multiple retries uses exponential backoff."""
        call_count = 0
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        async def mock_git_push():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise httpx.ConnectError("Network unreachable")
            return "Push successful"

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
            jitter_factor=0.0,
            exceptions=(httpx.ConnectError,)
        )
        async def git_push_with_retry():
            return await mock_git_push()

        with patch('asyncio.sleep', side_effect=mock_sleep):
            result = await git_push_with_retry()

        assert result == "Push successful"
        assert call_count == 4  # 3 failures + 1 success

        # Exponential backoff: 1.0, 2.0, 4.0
        assert len(sleep_times) == 3
        assert sleep_times[0] == 1.0
        assert sleep_times[1] == 2.0
        assert sleep_times[2] == 4.0

    @pytest.mark.asyncio
    async def test_git_push_max_retries_exhausted(self):
        """Test git push fails after max retries are exhausted."""
        call_count = 0
        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        async def mock_git_push():
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("Network unreachable")

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=1.0,
            max_delay=10.0,
            jitter_factor=0.0,
            exceptions=(httpx.ConnectError,)
        )
        async def git_push_with_retry():
            return await mock_git_push()

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(httpx.ConnectError):
                await git_push_with_retry()

        # Should attempt initial + 2 retries
        assert call_count == 3

        # Should sleep twice (before each retry)
        assert len(sleep_times) == 2
        assert sleep_times[0] == 1.0
        assert sleep_times[1] == 2.0


class TestErrorCategories:
    """Test error categorization for logging and debugging."""

    @pytest.mark.asyncio
    async def test_error_category_timeout(self):
        """Test timeout error categorization."""
        error = httpx.TimeoutException("Request timeout")
        category = get_error_category(error)
        assert category == 'timeout'

    @pytest.mark.asyncio
    async def test_error_category_connection(self):
        """Test connection error categorization."""
        error = httpx.ConnectError("Connection refused")
        category = get_error_category(error)
        assert category == 'connection'

    @pytest.mark.asyncio
    async def test_error_category_rate_limit(self):
        """Test rate limit (429) error categorization."""
        mock_response = Mock()
        mock_response.status_code = 429
        error = httpx.HTTPStatusError("Too Many Requests", request=Mock(), response=mock_response)
        category = get_error_category(error)
        assert category == 'rate_limit'

    @pytest.mark.asyncio
    async def test_error_category_server_error(self):
        """Test server error (5xx) categorization."""
        mock_response = Mock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError("Internal Server Error", request=Mock(), response=mock_response)
        category = get_error_category(error)
        assert category == 'server_error'

    @pytest.mark.asyncio
    async def test_error_category_client_error(self):
        """Test client error (4xx) categorization."""
        mock_response = Mock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=Mock(), response=mock_response)
        category = get_error_category(error)
        assert category == 'client_error'

    @pytest.mark.asyncio
    async def test_error_category_unknown(self):
        """Test unknown error categorization."""
        error = ValueError("Unknown error")
        category = get_error_category(error)
        assert category == 'unknown'

    @pytest.mark.asyncio
    async def test_error_category_none_input(self):
        """Test None input categorization."""
        category = get_error_category(None)
        assert category == 'unknown'
