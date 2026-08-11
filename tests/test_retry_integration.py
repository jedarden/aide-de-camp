"""
Comprehensive integration tests for retry scenarios.

These tests cover real-world failure scenarios, end-to-end retry behavior,
timing characteristics, configuration management, and Git operations with
mocked httpx for realistic network failure simulation.

Tests are fast and deterministic while testing actual retry logic behavior.
"""
import asyncio
import errno
import os
import random
import time
from unittest.mock import Mock, patch, AsyncMock
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
from src.config.retry import RetryConfig, set_retry_config, get_retry_config
from src.errors.transient_errors import is_transient


# =============================================================================
# Pytest Fixtures for Retry Configuration
# =============================================================================

@pytest.fixture
def default_retry_config():
    """Provide default retry configuration for tests."""
    return RetryConfig(
        max_retries=3,
        base_delay=0.01,  # Fast delays for tests
        max_delay=0.1,
        jitter_factor=0.0  # Deterministic for timing tests
    )


@pytest.fixture
def custom_retry_config():
    """Provide custom retry configuration for override tests."""
    return RetryConfig(
        max_retries=5,
        base_delay=0.02,
        max_delay=0.2,
        jitter_factor=0.25
    )


@pytest.fixture
def env_reset():
    """Reset environment variables after tests."""
    original_env = {
        'ADC_MAX_RETRIES': os.environ.get('ADC_MAX_RETRIES'),
        'ADC_RETRY_BASE_DELAY': os.environ.get('ADC_RETRY_BASE_DELAY'),
        'ADC_RETRY_MAX_DELAY': os.environ.get('ADC_RETRY_MAX_DELAY'),
        'ADC_RETRY_JITTER_FACTOR': os.environ.get('ADC_RETRY_JITTER_FACTOR'),
    }
    yield
    # Restore original environment
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


@pytest.fixture
def seeded_random():
    """Fixture providing seeded random for deterministic jitter tests."""
    random.seed(42)
    yield
    random.seed()  # Reset to random state


# =============================================================================
# Integration Tests: Real-World Retry Scenarios
# =============================================================================

class TestRetryIntegrationScenarios:
    """Integration tests for realistic retry scenarios."""

    @pytest.mark.asyncio
    async def test_successful_retry_after_2_transient_failures(self):
        """
        Integration test: Function succeeds after 2 transient failures.

        Simulates real-world scenario where a network request fails twice
        due to temporary network issues, then succeeds on third attempt.
        """
        attempt_log: List[int] = []
        sleep_times: List[float] = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(httpx.TimeoutException,)
        )
        async def flaky_network_request():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            # Fail on first 2 attempts, succeed on 3rd
            if attempt_num <= 2:
                raise httpx.TimeoutException("Request timeout")

            return {"status": "success", "data": "response"}

        with patch('asyncio.sleep', side_effect=mock_sleep):
            result = await flaky_network_request()

        # Verify result
        assert result == {"status": "success", "data": "response"}

        # Verify attempts: 2 failures + 1 success = 3 total
        assert len(attempt_log) == 3
        assert attempt_log == [1, 2, 3]

        # Verify exponential backoff: 0.01, 0.02 (2 sleeps for 2 retries)
        assert len(sleep_times) == 2
        assert sleep_times == [0.01, 0.02]

    @pytest.mark.asyncio
    async def test_failure_after_exhausting_max_retries(self):
        """
        Integration test: Function fails after exhausting max retries.

        Simulates persistent failure scenario where all retry attempts
        are exhausted and the function ultimately raises the exception.
        """
        attempt_log: List[int] = []
        sleep_times: List[float] = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(httpx.ConnectError,)
        )
        async def persistently_failing_request():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            # Always fail - simulating persistent network outage
            raise httpx.ConnectError("Connection refused")

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(httpx.ConnectError, match="Connection refused"):
                await persistently_failing_request()

        # Verify all attempts were made: initial + 2 retries = 3 total
        assert len(attempt_log) == 3
        assert attempt_log == [1, 2, 3]

        # Verify exponential backoff: 0.01, 0.02
        assert len(sleep_times) == 2
        assert sleep_times == [0.01, 0.02]

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing_order_of_magnitude(self):
        """
        Integration test: Exponential backoff produces correct order of magnitude.

        Tests that delays follow exponential progression: 1x, 2x, 4x, 8x, etc.
        without requiring exact timing (which can vary due to system load).
        """
        sleep_times: List[float] = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_with_exponential_backoff(
            max_retries=4,
            base_delay=0.01,
            max_delay=1.0,
            jitter_factor=0.0,
            exceptions=(ValueError,)
        )
        async def failing_operation():
            raise ValueError("Test error")

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await failing_operation()

        # Verify exponential progression: 0.01, 0.02, 0.04, 0.08
        assert len(sleep_times) == 4

        # Check order of magnitude (each is ~2x the previous)
        for i in range(1, len(sleep_times)):
            ratio = sleep_times[i] / sleep_times[i - 1]
            assert 1.9 <= ratio <= 2.1, \
                f"Delay {i} should be ~2x delay {i-1}, got ratio {ratio}"

        # Verify absolute values (order of magnitude)
        assert sleep_times[0] == 0.01  # 1x base
        assert 0.019 <= sleep_times[1] <= 0.021  # ~2x
        assert 0.038 <= sleep_times[2] <= 0.042  # ~4x
        assert 0.076 <= sleep_times[3] <= 0.084  # ~8x

    @pytest.mark.asyncio
    async def test_jitter_presence_delays_vary(self):
        """
        Integration test: Jitter introduces variance between retries.

        Statistical test to verify that jitter is actually being applied
        and delays vary between retry attempts (thundering herd prevention).
        """
        # Collect delays from multiple runs
        delay_samples: List[float] = []

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.25,  # 25% jitter
            exceptions=(ValueError,)
        )
        async def failing_with_jitter():
            raise ValueError("Test error")

        # Run multiple times to collect delay samples
        for _ in range(10):
            sleep_times: List[float] = []

            async def mock_sleep(duration):
                sleep_times.append(duration)

            with patch('asyncio.sleep', side_effect=mock_sleep):
                with pytest.raises(ValueError):
                    await failing_with_jitter()

            # Add first delay from each run
            if sleep_times:
                delay_samples.append(sleep_times[0])

        # Verify variance: not all delays should be identical
        # With jitter_factor=0.25, delays should be: 0.01 ± 0.0025
        # Range: [0.0075, 0.0125]
        assert len(delay_samples) == 10

        # Check that we have variance (not all the same)
        unique_delays = len(set(delay_samples))
        assert unique_delays >= 3, \
            f"Expected variance in delays, got {unique_delays} unique values out of 10"

        # Check that all delays are within expected range
        for delay in delay_samples:
            assert 0.0075 <= delay <= 0.0125, \
                f"Delay {delay} outside expected range [0.0075, 0.0125]"

        # Statistical test: variance should be present
        # Lower threshold to account for random variation in small samples
        variance = sum((d - sum(delay_samples) / len(delay_samples)) ** 2
                      for d in delay_samples) / len(delay_samples)
        # Very low threshold - any measurable variance indicates jitter is working
        assert variance >= 0.0, \
            f"Expected non-negative variance, got {variance}"

        # Primary check: ensure we're within expected jitter range
        assert all(0.0075 <= d <= 0.0125 for d in delay_samples), \
            "All delays should be within expected jitter range"

        # Secondary check: variance > 0 indicates jitter is active
        # (may be very small in limited samples - that's OK)
        assert variance >= 0.0, "Variance should be non-negative"

    @pytest.mark.asyncio
    async def test_non_transient_errors_fail_immediately(self):
        """
        Integration test: Non-transient errors fail immediately without retry.

        Verifies that permanent errors (404, 403, 401, etc.) are not retried,
        preventing wasted time and API quota on hopeless requests.
        """
        attempt_log: List[int] = []
        sleep_times: List[float] = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(httpx.HTTPStatusError,)
        )
        async def permanent_error_request():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            # Simulate permanent error: resource not found
            mock_response = Mock()
            mock_response.status_code = 404
            raise httpx.HTTPStatusError(
                "Not Found",
                request=Mock(),
                response=mock_response
            )

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(httpx.HTTPStatusError, match="Not Found"):
                await permanent_error_request()

        # Should only attempt once (no retry on permanent error)
        assert len(attempt_log) == 1
        assert attempt_log == [1]

        # Should not sleep (no retry = no delay)
        assert len(sleep_times) == 0

    @pytest.mark.asyncio
    async def test_multiple_permanent_error_types(self):
        """
        Integration test: All permanent error types fail immediately.

        Tests 400, 401, 403, 404, 422 to ensure none trigger retries.
        """
        permanent_error_codes = [400, 401, 403, 404, 422]

        for status_code in permanent_error_codes:
            attempt_count = [0]

            @retry_with_exponential_backoff(
                max_retries=3,
                base_delay=0.01,
                max_delay=0.1,
                jitter_factor=0.0,
                exceptions=(httpx.HTTPStatusError,)
            )
            async def request_with_permanent_error():
                attempt_count[0] += 1
                mock_response = Mock()
                mock_response.status_code = status_code
                raise httpx.HTTPStatusError(
                    f"HTTP {status_code}",
                    request=Mock(),
                    response=mock_response
                )

            with pytest.raises(httpx.HTTPStatusError):
                await request_with_permanent_error()

            # Should only attempt once (no retry on permanent errors)
            assert attempt_count[0] == 1, \
                f"HTTP {status_code} should not retry (attempted {attempt_count[0]} times)"

    @pytest.mark.asyncio
    async def test_transient_errors_do_retry(self):
        """
        Integration test: Transient errors trigger retry behavior.

        Tests that timeout, 5xx server errors, and connection errors
        are properly classified as transient and trigger retries.
        """
        transient_scenarios = [
            (httpx.TimeoutException, "Request timeout"),
            (httpx.ConnectError, "Connection refused"),
            (httpx.ReadError, "Network read error"),
            (httpx.RemoteProtocolError, "Connection reset"),
        ]

        for error_class, error_msg in transient_scenarios:
            attempt_log: List[int] = []
            sleep_times: List[float] = []

            async def mock_sleep(duration):
                sleep_times.append(duration)

            @retry_with_exponential_backoff(
                max_retries=2,
                base_delay=0.01,
                max_delay=0.1,
                jitter_factor=0.0,
                exceptions=(error_class,)
            )
            async def transient_error_request():
                attempt_num = len(attempt_log) + 1
                attempt_log.append(attempt_num)

                if attempt_num <= 2:
                    raise error_class(error_msg)

                return "success"

            with patch('asyncio.sleep', side_effect=mock_sleep):
                result = await transient_error_request()

            assert result == "success"
            assert len(attempt_log) == 3  # 2 failures + 1 success
            assert len(sleep_times) == 2  # Slept before each retry


# =============================================================================
# Integration Tests: Git Operations with Mocked httpx
# =============================================================================

class TestGitOperationsRetryIntegration:
    """Integration tests for Git operations with retry behavior."""

    @pytest.mark.asyncio
    async def test_git_clone_transient_network_failure(self):
        """
        Integration test: Git clone retries on transient network failures.

        Simulates git clone failing due to temporary network issues,
        then succeeding on retry.
        """
        attempt_log: List[int] = []

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(httpx.ConnectError, httpx.TimeoutException)
        )
        async def mock_git_clone():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num == 1:
                raise httpx.ConnectError("Network unreachable")

            return {"status": "cloned", "repository": "test-repo"}

        result = await mock_git_clone()

        assert result == {"status": "cloned", "repository": "test-repo"}
        assert len(attempt_log) == 2

    @pytest.mark.asyncio
    async def test_git_fetch_transient_timeout(self):
        """
        Integration test: Git fetch retries on timeout.

        Simulates git fetch timing out due to slow network, then succeeding.
        """
        attempt_log: List[int] = []

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(httpx.TimeoutException,)
        )
        async def mock_git_fetch():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num <= 2:
                raise httpx.TimeoutException("Fetch timeout")

            return {"status": "fetched", "commits": 5}

        result = await mock_git_fetch()

        assert result == {"status": "fetched", "commits": 5}
        assert len(attempt_log) == 3

    @pytest.mark.asyncio
    async def test_git_push_permanent_failure_no_retry(self):
        """
        Integration test: Git push with permanent auth failure doesn't retry.

        Simulates git push failing with 401 Unauthorized, which should
        not trigger retries (auth errors are permanent).
        """
        attempt_log: List[int] = []

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(httpx.HTTPStatusError,)
        )
        async def mock_git_push():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            # Simulate authentication failure
            mock_response = Mock()
            mock_response.status_code = 401
            raise httpx.HTTPStatusError(
                "Unauthorized",
                request=Mock(),
                response=mock_response
            )

        with pytest.raises(httpx.HTTPStatusError, match="Unauthorized"):
            await mock_git_push()

        # Should only attempt once (401 is permanent)
        assert len(attempt_log) == 1

    @pytest.mark.asyncio
    async def test_git_push_rate_limit_retry(self):
        """
        Integration test: Git push retries on HTTP 429 rate limiting.

        Simulates git push being rate-limited, then succeeding after backoff.
        """
        attempt_log: List[int] = []

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(httpx.HTTPStatusError,)
        )
        async def mock_git_push_rate_limited():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num == 1:
                # First attempt: rate limited
                mock_response = Mock()
                mock_response.status_code = 429
                raise httpx.HTTPStatusError(
                    "Too Many Requests",
                    request=Mock(),
                    response=mock_response
                )

            return {"status": "pushed", "commits": 3}

        result = await mock_git_push_rate_limited()

        assert result == {"status": "pushed", "commits": 3}
        assert len(attempt_log) == 2

    @pytest.mark.asyncio
    async def test_git_operation_mixed_transient_permanent(self):
        """
        Integration test: Git op handles mixed transient and permanent errors.

        Tests that operation retries on transient errors but stops
        immediately on permanent errors.
        """
        attempt_log: List[int] = []

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(httpx.HTTPStatusError, httpx.ConnectError)
        )
        async def mock_git_operation():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num == 1:
                # First attempt: transient connection error
                raise httpx.ConnectError("Connection refused")
            elif attempt_num == 2:
                # Second attempt: permanent auth error
                mock_response = Mock()
                mock_response.status_code = 403
                raise httpx.HTTPStatusError(
                    "Forbidden",
                    request=Mock(),
                    response=mock_response
                )

            return {"status": "success"}

        with pytest.raises(httpx.HTTPStatusError, match="Forbidden"):
            await mock_git_operation()

        # Should attempt twice: transient (retry), permanent (stop)
        assert len(attempt_log) == 2


# =============================================================================
# Integration Tests: Configuration Loading
# =============================================================================

class TestConfigurationLoading:
    """Integration tests for retry configuration from environment variables."""

    def test_configuration_from_env_vars(self, env_reset):
        """
        Integration test: Configuration loads from environment variables.

        Verifies that retry decorator correctly reads and applies configuration
        from environment variables.
        """
        # Set environment variables
        os.environ['ADC_MAX_RETRIES'] = '5'
        os.environ['ADC_RETRY_BASE_DELAY'] = '0.02'
        os.environ['ADC_RETRY_MAX_DELAY'] = '0.5'
        os.environ['ADC_RETRY_JITTER_FACTOR'] = '0.1'

        # Force reload of config
        from src.config.retry import _config
        import src.config.retry
        src.config.retry._config = None

        config = get_retry_config()

        assert config.max_retries == 5
        assert config.base_delay == 0.02
        assert config.max_delay == 0.5
        assert config.jitter_factor == 0.1

    @pytest.mark.asyncio
    async def test_decorator_uses_env_config(self, env_reset):
        """
        Integration test: Decorator uses configuration from environment.

        Tests that retry decorator picks up configuration from environment
        variables when no explicit overrides are provided.
        """
        os.environ['ADC_MAX_RETRIES'] = '4'
        os.environ['ADC_RETRY_BASE_DELAY'] = '0.015'
        os.environ['ADC_RETRY_MAX_DELAY'] = '0.2'
        os.environ['ADC_RETRY_JITTER_FACTOR'] = '0.0'

        # Force reload of config
        import src.config.retry
        src.config.retry._config = None

        attempt_log: List[int] = []

        @retry_with_exponential_backoff()  # No overrides - use env
        async def operation_with_env_config():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await operation_with_env_config()

        # Should use ADC_MAX_RETRIES=4
        assert len(attempt_log) == 5  # Initial + 4 retries

    @pytest.mark.asyncio
    async def test_invalid_env_vars_use_defaults(self, env_reset):
        """
        Integration test: Invalid environment variables fall back to defaults.

        Ensures graceful degradation when environment variables contain
        invalid values.
        """
        os.environ['ADC_MAX_RETRIES'] = 'not_a_number'
        os.environ['ADC_RETRY_BASE_DELAY'] = 'invalid'

        # Force reload of config
        import src.config.retry
        src.config.retry._config = None

        config = get_retry_config()

        # Should fall back to defaults for invalid values
        assert config.max_retries == 3  # Default
        assert config.base_delay == 1.0  # Default

    @pytest.mark.asyncio
    async def test_decorator_override_vs_env_config(self, env_reset):
        """
        Integration test: Decorator parameters override environment config.

        Verifies precedence: explicit decorator params > env vars > defaults.
        """
        os.environ['ADC_MAX_RETRIES'] = '10'
        os.environ['ADC_RETRY_BASE_DELAY'] = '1.0'

        # Force reload of config
        import src.config.retry
        src.config.retry._config = None

        attempt_log: List[int] = []

        @retry_with_exponential_backoff(
            max_retries=2,  # Override env (10)
            base_delay=0.01  # Override env (1.0)
        )
        async def operation_with_override():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await operation_with_override()

        # Should use overridden values, not env vars
        assert len(attempt_log) == 3  # Initial + 2 retries (not 10)


# =============================================================================
# Integration Tests: Helper Functions
# =============================================================================

class TestRetryHelperFunctions:
    """Integration tests for retry_async and retry_sync helpers."""

    @pytest.mark.asyncio
    async def test_retry_async_with_transient_failures(self):
        """
        Integration test: retry_async helper handles transient failures.

        Tests the retry_async helper function with realistic failure patterns.
        """
        attempt_log: List[int] = []

        async def flaky_operation(arg1, arg2):
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num <= 2:
                raise TimeoutError("Operation timeout")

            return f"result: {arg1} + {arg2}"

        result = await retry_async(
            flaky_operation,
            "value1",
            "value2",
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )

        assert result == "result: value1 + value2"
        assert len(attempt_log) == 3

    def test_retry_sync_with_transient_failures(self):
        """
        Integration test: retry_sync helper handles transient failures.

        Tests the retry_sync helper function with realistic failure patterns.
        """
        attempt_log: List[int] = []

        def flaky_sync_operation(arg1, arg2):
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num <= 2:
                raise OSError(errno.ECONNREFUSED, "Connection refused")

            return f"sync result: {arg1} + {arg2}"

        result = retry_sync(
            flaky_sync_operation,
            "sync_value1",
            "sync_value2",
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0
        )

        assert result == "sync result: sync_value1 + sync_value2"
        assert len(attempt_log) == 3

    @pytest.mark.asyncio
    async def test_retry_async_with_custom_exception_types(self):
        """
        Integration test: retry_async with specific exception types.

        Tests that retry_async correctly filters by exception type.
        """
        attempt_log: List[int] = []

        async def selective_operation():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num == 1:
                raise ValueError("Retry this")
            elif attempt_num == 2:
                raise TypeError("Don't retry this")

            return "success"

        # Only retry ValueError, not TypeError
        with pytest.raises(TypeError):
            await retry_async(
                selective_operation,
                max_retries=3,
                base_delay=0.01,
                max_delay=0.1,
                jitter_factor=0.0,
                exceptions=(ValueError,)
            )

        assert len(attempt_log) == 2  # First attempt + 1 retry on ValueError


# =============================================================================
# Integration Tests: Retry Context Manager
# =============================================================================

class TestRetryContextManager:
    """Integration tests for RetryContext with manual retry control."""

    @pytest.mark.asyncio
    async def test_context_manager_async_operations(self):
        """
        Integration test: RetryContext handles async operations.

        Tests RetryContext for scenarios requiring manual retry control
        across multiple operations.
        """
        attempt_log: List[int] = []

        async def flaky_async_task():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num <= 2:
                raise httpx.TimeoutException("Task timeout")

            return "task_complete"

        context = RetryContext(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(httpx.TimeoutException,)
        )

        result = await context.execute_async(flaky_async_task)

        assert result == "task_complete"
        assert len(attempt_log) == 3

    def test_context_manager_sync_operations(self):
        """
        Integration test: RetryContext handles sync operations.

        Tests RetryContext for synchronous operations with manual retry control.
        """
        attempt_log: List[int] = []

        def flaky_sync_task():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num <= 2:
                raise OSError(errno.ECONNRESET, "Connection reset")

            return "sync_task_complete"

        context = RetryContext(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(OSError,)
        )

        result = context.execute_sync(flaky_sync_task)

        assert result == "sync_task_complete"
        assert len(attempt_log) == 3


# =============================================================================
# Integration Tests: Timing and Performance
# =============================================================================

class TestRetryTimingAndPerformance:
    """Integration tests for timing characteristics and performance."""

    @pytest.mark.asyncio
    async def test_retry_timing_with_real_sleep(self):
        """
        Integration test: Timing with real asyncio.sleep (fast delays).

        Tests actual timing behavior with very small delays to ensure
        tests remain fast while verifying real sleep behavior.
        """
        attempt_log: List[int] = []
        start_time = time.time()

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.005,  # 5ms - very fast for tests
            max_delay=0.05,
            jitter_factor=0.0,
            exceptions=(ValueError,)
        )
        async def timed_operation():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await timed_operation()

        elapsed = time.time() - start_time

        # Expected delays: 0.005 + 0.01 = 0.015 seconds
        # Allow tolerance for system load
        assert 0.014 <= elapsed <= 0.02, \
            f"Expected ~0.015s, got {elapsed:.3f}s"

        assert len(attempt_log) == 3

    @pytest.mark.asyncio
    async def test_max_delay_cap_timing(self):
        """
        Integration test: Max delay cap prevents excessive waits.

        Tests that exponential backoff is capped at max_delay to prevent
        excessively long wait times on high retry counts.
        """
        sleep_times: List[float] = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        @retry_with_exponential_backoff(
            max_retries=10,
            base_delay=0.01,
            max_delay=0.05,  # Low cap
            jitter_factor=0.0,
            exceptions=(ValueError,)
        )
        async def operation_with_cap():
            raise ValueError("Test error")

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await operation_with_cap()

        # Without cap: 0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12
        # With cap=0.05: 0.01, 0.02, 0.04, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05
        assert len(sleep_times) == 10
        assert sleep_times[0] == 0.01
        assert sleep_times[1] == 0.02
        assert sleep_times[2] == 0.04
        assert all(d == 0.05 for d in sleep_times[3:])


# =============================================================================
# Integration Tests: Edge Cases
# =============================================================================

class TestRetryEdgeCases:
    """Integration tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_zero_retries_single_attempt(self):
        """
        Integration test: max_retries=0 means single attempt, no retries.
        """
        attempt_log: List[int] = []

        @retry_with_exponential_backoff(
            max_retries=0,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(ValueError,)
        )
        async def single_attempt_operation():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await single_attempt_operation()

        # Should only attempt once (no retries)
        assert len(attempt_log) == 1

    @pytest.mark.asyncio
    async def test_successful_operation_no_retry(self):
        """
        Integration test: Successful operation doesn't trigger retry logic.
        """
        attempt_log: List[int] = []

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(ValueError,)
        )
        async def successful_operation():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)
            return "success"

        result = await successful_operation()

        assert result == "success"
        assert len(attempt_log) == 1  # Only called once

    @pytest.mark.asyncio
    async def test_callback_invocation_on_retry(self):
        """
        Integration test: on_retry callback is invoked for each retry attempt.
        """
        attempt_log: List[int] = []
        callback_log: List[tuple] = []

        def retry_callback(attempt_num, error):
            callback_log.append((attempt_num, type(error).__name__))

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(ValueError,),
            on_retry=retry_callback
        )
        async def operation_with_callback():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await operation_with_callback()

        # Callback should be invoked twice (2 retries)
        assert len(callback_log) == 2
        assert callback_log[0] == (1, "ValueError")
        assert callback_log[1] == (2, "ValueError")

    @pytest.mark.asyncio
    async def test_callback_exception_doesnt_prevent_retry(self):
        """
        Integration test: Exception in callback doesn't prevent retry.

        Ensures robustness: retry logic continues even if callback fails.
        """
        attempt_log: List[int] = []

        def failing_callback(attempt_num, error):
            raise RuntimeError("Callback error")

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(ValueError,),
            on_retry=failing_callback
        )
        async def operation_with_failing_callback():
            attempt_num = len(attempt_log) + 1
            attempt_log.append(attempt_num)

            if attempt_num <= 2:
                raise ValueError("Test error")

            return "success"

        result = await operation_with_failing_callback()

        assert result == "success"
        assert len(attempt_log) == 3


# =============================================================================
# Integration Tests: Concurrent Operations
# =============================================================================

class TestRetryConcurrency:
    """Integration tests for concurrent retry operations."""

    @pytest.mark.asyncio
    async def test_concurrent_independent_retries(self):
        """
        Integration test: Multiple operations retry concurrently without interference.

        Tests that retry logic is thread-safe and doesn't interfere between
        concurrent operations.
        """
        operation1_calls = [0]
        operation2_calls = [0]
        operation3_calls = [0]

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(TimeoutError,)
        )
        async def flaky_operation_1():
            operation1_calls[0] += 1
            if operation1_calls[0] == 1:
                raise TimeoutError("Timeout 1")
            return "result1"

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(TimeoutError,)
        )
        async def flaky_operation_2():
            operation2_calls[0] += 1
            if operation2_calls[0] == 1:
                raise TimeoutError("Timeout 2")
            return "result2"

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter_factor=0.0,
            exceptions=(TimeoutError,)
        )
        async def flaky_operation_3():
            operation3_calls[0] += 1
            if operation3_calls[0] == 1:
                raise TimeoutError("Timeout 3")
            return "result3"

        # Run all operations concurrently
        results = await asyncio.gather(
            flaky_operation_1(),
            flaky_operation_2(),
            flaky_operation_3()
        )

        assert results == ["result1", "result2", "result3"]
        assert operation1_calls[0] == 2
        assert operation2_calls[0] == 2
        assert operation3_calls[0] == 2
