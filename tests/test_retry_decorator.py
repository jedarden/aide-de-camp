"""
Integration tests for retry decorator with mocked transient errors.

Tests retry logic, delay calculation, exponential backoff, jitter,
and sync/async function compatibility using mocked errors and
verified retry attempts.
"""
import asyncio
import errno
import time
from unittest.mock import Mock, patch, call
from typing import List

import pytest
import httpx
import aiohttp

from src.utilities.retry import (
    retry_with_exponential_backoff,
    retry_async,
    retry_sync,
    calculate_delay_with_backoff,
    RetryContext,
)
from src.config.retry import RetryConfig, set_retry_config


class TestCalculateDelayWithBackoff:
    """Test delay calculation with exponential backoff and jitter."""

    def test_exponential_backoff_without_jitter(self):
        """Exponential backoff increases delay by powers of 2."""
        # No jitter: deterministic delays
        delays = [
            calculate_delay_with_backoff(attempt=i, base_delay=1.0, max_delay=60.0, jitter_factor=0.0)
            for i in range(5)
        ]
        # 1.0 * 2^0, 1.0 * 2^1, 1.0 * 2^2, 1.0 * 2^3, 1.0 * 2^4
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_exponential_backoff_with_max_delay_cap(self):
        """Delay is capped at max_delay to prevent excessive waits."""
        delays = [
            calculate_delay_with_backoff(attempt=i, base_delay=1.0, max_delay=10.0, jitter_factor=0.0)
            for i in range(10)
        ]
        # Should cap at 10.0 once exponential backoff exceeds it
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0
        assert delays[3] == 8.0
        assert delays[4] == 10.0  # 16.0 capped at 10.0
        assert all(d == 10.0 for d in delays[4:])  # All subsequent attempts also capped

    def test_jitter_increases_variance(self):
        """Jitter introduces randomness in delay values."""
        # Run multiple times to check for variance
        delays_with_jitter = [
            calculate_delay_with_backoff(attempt=2, base_delay=1.0, max_delay=60.0, jitter_factor=0.25)
            for _ in range(100)
        ]
        # With jitter_factor=0.25, delay should be: 4.0 ± (4.0 * 0.25) = 4.0 ± 1.0
        # So we expect values in range [3.0, 5.0]
        assert all(3.0 <= d <= 5.0 for d in delays_with_jitter)
        # Not all delays should be identical (jitter introduces randomness)
        assert len(set(delays_with_jitter)) > 1

    def test_no_jitter_produces_deterministic_delays(self):
        """Zero jitter produces consistent, predictable delays."""
        delays = [
            calculate_delay_with_backoff(attempt=i, base_delay=2.0, max_delay=60.0, jitter_factor=0.0)
            for i in range(3)
        ]
        # Should be exactly: 2.0, 4.0, 8.0
        assert delays == [2.0, 4.0, 8.0]

    def test_full_jitter_randomizes_with_high_variance(self):
        """Full jitter (jitter_factor=1.0) produces high variance in delays."""
        delays = [
            calculate_delay_with_backoff(attempt=2, base_delay=4.0, max_delay=60.0, jitter_factor=1.0)
            for _ in range(100)
        ]
        # With full jitter_factor=1.0, the formula is: delay ± (delay * 1.0)
        # Which means: delay can range from 0 to 32.0 (16.0 ± 16.0)
        # However, the function uses max(0.0, final_delay) to prevent negative delays
        # (base_delay * 2^attempt = 4.0 * 4 = 16.0 before jitter)
        assert all(0.0 <= d <= 32.0 for d in delays)
        # Should have high variance with full jitter
        assert len(set(delays)) > 10


class TestAsyncRetryWithTransientErrors:
    """Test async function retry behavior with mocked transient errors."""

    @pytest.mark.asyncio
    async def test_successful_retry_after_transient_error(self):
        """Function succeeds after retrying on transient error."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,  # Small delay for fast tests
            max_delay=0.1,
            jitter_factor=0.0  # Deterministic delays
        )
        async def flaky_function():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                # Fail on first attempt with transient error
                raise httpx.TimeoutException("Request timeout")
            return "success"

        result = await flaky_function()
        assert result == "success"
        assert attempt_count[0] == 2  # Failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_max_retries_exhaustion(self):
        """Function fails after exhausting all retry attempts."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        async def always_failing_function():
            attempt_count[0] += 1
            raise httpx.TimeoutException("Always times out")

        with pytest.raises(httpx.TimeoutException, match="Always times out"):
            await always_failing_function()

        # Should attempt max_retries + 1 times (initial + retries)
        assert attempt_count[0] == 3

    @pytest.mark.asyncio
    async def test_non_transient_error_stops_retry_immediately(self):
        """Non-transient error (e.g., 404) fails immediately without retry."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        async def function_with_permanent_error():
            attempt_count[0] += 1
            # Create a 404 error (permanent, not transient)
            response = Mock(status_code=404)
            raise httpx.HTTPStatusError("Not found", request=Mock(), response=response)

        with pytest.raises(httpx.HTTPStatusError):
            await function_with_permanent_error()

        # Should only attempt once (no retries for permanent errors)
        assert attempt_count[0] == 1

    @pytest.mark.asyncio
    async def test_retry_attempt_logged_via_callback(self):
        """Custom on_retry callback is called for each retry attempt."""
        attempt_log: List[tuple] = []

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            on_retry=lambda attempt, error: attempt_log.append((attempt, type(error).__name__))
        )
        async def function_that_retries():
            raise httpx.TimeoutException("Timeout")

        with pytest.raises(httpx.TimeoutException):
            await function_that_retries()

        # Should have logged 2 retry attempts
        assert len(attempt_log) == 2
        assert attempt_log[0] == (1, "TimeoutException")
        assert attempt_log[1] == (2, "TimeoutException")

    @pytest.mark.asyncio
    async def test_generic_exception_always_retries(self):
        """Non-network exceptions (ValueError, etc.) are always retried."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(ValueError,)  # Only catch ValueError
        )
        async def function_with_value_error():
            attempt_count[0] += 1
            raise ValueError("Invalid value")

        with pytest.raises(ValueError):
            await function_with_value_error()

        # Should retry ValueError (it's in exceptions tuple)
        assert attempt_count[0] == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_retry_async_helper_function(self):
        """retry_async helper function works correctly."""
        attempt_count = [0]

        async def flaky_operation():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise httpx.ReadError("Connection reset")
            return "result"

        result = await retry_async(
            flaky_operation,
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )

        assert result == "result"
        assert attempt_count[0] == 2


class TestSyncRetryWithTransientErrors:
    """Test synchronous function retry behavior with mocked transient errors."""

    def test_successful_sync_retry_after_transient_error(self):
        """Sync function succeeds after retrying on transient error."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def flaky_sync_function():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise OSError(errno.ECONNREFUSED, "Connection refused")
            return "sync_success"

        result = flaky_sync_function()
        assert result == "sync_success"
        assert attempt_count[0] == 2

    def test_sync_max_retries_exhaustion(self):
        """Sync function fails after exhausting all retry attempts."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def always_failing_sync_function():
            attempt_count[0] += 1
            raise TimeoutError("Timed out")

        with pytest.raises(TimeoutError, match="Timed out"):
            always_failing_sync_function()

        assert attempt_count[0] == 3

    def test_sync_non_transient_error_stops_retry_immediately(self):
        """Non-transient error fails immediately without retry."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def sync_function_with_permanent_error():
            attempt_count[0] += 1
            # Create a 404 error (permanent, not transient)
            response = Mock(status_code=404)
            raise httpx.HTTPStatusError("Not found", request=Mock(), response=response)

        with pytest.raises(httpx.HTTPStatusError):
            sync_function_with_permanent_error()

        assert attempt_count[0] == 1  # No retries for permanent errors

    def test_retry_sync_helper_function(self):
        """retry_sync helper function works correctly."""
        attempt_count = [0]

        def flaky_sync_operation():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise TimeoutError("Timeout")
            return "sync_result"

        result = retry_sync(
            flaky_sync_operation,
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )

        assert result == "sync_result"
        assert attempt_count[0] == 2


class TestRetryContextManager:
    """Test RetryContext for manual retry control."""

    @pytest.mark.asyncio
    async def test_context_execute_async(self):
        """RetryContext.execute_async retries failed operations."""
        attempt_count = [0]

        async def flaky_operation():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise httpx.TimeoutException("Timeout")
            return "context_result"

        context = RetryContext(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )

        result = await context.execute_async(flaky_operation)
        assert result == "context_result"
        assert attempt_count[0] == 2

    def test_context_execute_sync(self):
        """RetryContext.execute_sync retries failed operations."""
        attempt_count = [0]

        def flaky_sync_operation():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise TimeoutError("Timeout")
            return "sync_context_result"

        context = RetryContext(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )

        result = context.execute_sync(flaky_sync_operation)
        assert result == "sync_context_result"
        assert attempt_count[0] == 2


class TestRetryConfiguration:
    """Test retry configuration defaults and overrides."""

    def test_uses_config_defaults_when_no_overrides(self):
        """Decorator uses config defaults when no parameters provided."""
        # Set custom config
        test_config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=30.0,
            jitter_factor=0.5
        )
        set_retry_config(test_config)

        attempt_count = [0]

        @retry_with_exponential_backoff()  # No overrides - use config
        def function_with_config_defaults():
            attempt_count[0] += 1
            if attempt_count[0] <= 4:
                raise TimeoutError("Timeout")
            return "success"

        result = function_with_config_defaults()
        assert result == "success"
        assert attempt_count[0] == 5  # Initial + 4 retries (config.max_retries=5)

    def test_explicit_overrides_override_config(self):
        """Explicit decorator parameters override config defaults."""
        # Set config with one value
        test_config = RetryConfig(
            max_retries=10,
            base_delay=5.0,
            max_delay=100.0,
            jitter_factor=0.5
        )
        set_retry_config(test_config)

        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=2,  # Override config.max_retries (10)
            base_delay=0.01,  # Override config.base_delay (5.0)
            jitter_factor=0.0  # Override config.jitter_factor (0.5)
        )
        def function_with_overrides():
            attempt_count[0] += 1
            if attempt_count[0] <= 1:
                raise TimeoutError("Timeout")
            return "success"

        result = function_with_overrides()
        assert result == "success"
        assert attempt_count[0] == 2  # Uses overridden max_retries=2


class TestRetryWithMixedErrorTypes:
    """Test retry behavior with different error types."""

    @pytest.mark.asyncio
    async def test_http_429_rate_limit_retries(self):
        """HTTP 429 (rate limit) is transient and triggers retry."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        async def rate_limited_function():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                # First attempt: rate limited
                response = Mock(status_code=429)
                raise httpx.HTTPStatusError("Rate limited", request=Mock(), response=response)
            return "success_after_rate_limit"

        result = await rate_limited_function()
        assert result == "success_after_rate_limit"
        assert attempt_count[0] == 2

    @pytest.mark.asyncio
    async def test_http_500_server_error_retries(self):
        """HTTP 500 (server error) is transient and triggers retry."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        async def server_error_function():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                response = Mock(status_code=500)
                raise httpx.HTTPStatusError("Internal server error", request=Mock(), response=response)
            return "success_after_500"

        result = await server_error_function()
        assert result == "success_after_500"
        assert attempt_count[0] == 2

    @pytest.mark.asyncio
    async def test_http_401_unauthorized_fails_immediately(self):
        """HTTP 401 (unauthorized) is permanent and fails immediately."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        async def unauthorized_function():
            attempt_count[0] += 1
            response = Mock(status_code=401)
            raise httpx.HTTPStatusError("Unauthorized", request=Mock(), response=response)

        with pytest.raises(httpx.HTTPStatusError):
            await unauthorized_function()

        assert attempt_count[0] == 1  # No retries for 401

    @pytest.mark.asyncio
    async def test_aiohttp_client_error_retries(self):
        """aiohttp client errors are transient and trigger retry."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        async def aiohttp_flaky_function():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise aiohttp.ClientConnectionError("Connection reset")
            return "aiohttp_success"

        result = await aiohttp_flaky_function()
        assert result == "aiohttp_success"
        assert attempt_count[0] == 2


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_zero_retries_attempts_once(self):
        """max_retries=0 means single attempt with no retries."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=0,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        def single_attempt_function():
            attempt_count[0] += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            single_attempt_function()

        assert attempt_count[0] == 1  # Only initial attempt, no retries

    @pytest.mark.asyncio
    async def test_callback_exception_doesnt_prevent_retry(self):
        """Exception in on_retry callback doesn't prevent retry."""
        attempt_count = [0]

        def bad_callback(attempt, error):
            attempt_count[0] += 1  # Increment to count callback invocations
            raise RuntimeError("Callback failed")

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            on_retry=bad_callback
        )
        async def function_with_bad_callback():
            if attempt_count[0] < 2:
                raise TimeoutError("Timeout")
            return "success"

        result = await function_with_bad_callback()
        assert result == "success"
        assert attempt_count[0] >= 2  # Callback was called despite errors

    @pytest.mark.asyncio
    async def test_successful_function_never_retries(self):
        """Function that succeeds immediately doesn't retry."""
        attempt_count = [0]

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        async def successful_function():
            attempt_count[0] += 1
            return "immediate_success"

        result = await successful_function()
        assert result == "immediate_success"
        assert attempt_count[0] == 1  # Only called once


class TestConcurrencyAndPerformance:
    """Test concurrent retries and performance characteristics."""

    @pytest.mark.asyncio
    async def test_concurrent_independent_retries(self):
        """Multiple functions can retry concurrently without interference."""
        function1_calls = [0]
        function2_calls = [0]

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        async def flaky_function_1():
            function1_calls[0] += 1
            if function1_calls[0] == 1:
                raise TimeoutError("Function 1 timeout")
            return "result1"

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )
        async def flaky_function_2():
            function2_calls[0] += 1
            if function2_calls[0] == 1:
                raise TimeoutError("Function 2 timeout")
            return "result2"

        # Run both functions concurrently
        results = await asyncio.gather(
            flaky_function_1(),
            flaky_function_2()
        )

        assert results == ["result1", "result2"]
        assert function1_calls[0] == 2
        assert function2_calls[0] == 2
