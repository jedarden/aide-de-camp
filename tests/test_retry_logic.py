"""
Tests for retry logic with exponential backoff.

Verifies that the retry utility correctly handles transient failures with
exponential backoff and proper logging.
"""
import asyncio
import logging
import time
from unittest.mock import Mock, patch
import pytest

from src.utilities.retry import (
    retry_with_exponential_backoff,
    retry_async,
    retry_sync,
    RetryContext,
)


class TestRetryDecorator:
    """Tests for the retry_with_exponential_backoff decorator."""

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
    async def test_async_retry_success_after_retries(self):
        """Test that retry eventually succeeds after transient failures."""
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
            if call_count < 3:
                raise ValueError("Transient error")
            return "success"

        result = await flaky_operation()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_exhausted(self):
        """Test that retry raises exception after all retries are exhausted."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        )
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Persistent error")

        with pytest.raises(ValueError, match="Persistent error"):
            await failing_operation()

        assert call_count == 3  # Initial attempt + 2 retries

    @pytest.mark.asyncio
    async def test_async_retry_logging(self):
        """Test that retry attempts are logged at WARNING level."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        )
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Test error")

        with patch('src.utilities.retry.logger') as mock_logger:
            with pytest.raises(ValueError):
                await failing_operation()

            # Verify warning logs for retry attempts
            assert mock_logger.warning.call_count >= 2
            # Verify error log for final failure
            assert mock_logger.error.call_count >= 1

    @pytest.mark.asyncio
    async def test_async_retry_exponential_backoff_timing(self):
        """Test that exponential backoff delays increase exponentially."""
        call_times = []

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.1,
            max_delay=1.0,
            exceptions=(ValueError,)
        )
        async def timed_failing_operation():
            call_times.append(time.time())
            raise ValueError("Test error")

        start_time = time.time()
        with pytest.raises(ValueError):
            await timed_failing_operation()

        # Verify exponential backoff timing
        # Delay sequence should be: 0.1s, 0.2s, 0.4s (capped at max_delay)
        assert len(call_times) == 4  # Initial + 3 retries

        # Calculate actual delays between attempts
        delays = [call_times[i] - call_times[i-1] for i in range(1, len(call_times))]

        # First delay should be ~0.1s
        assert delays[0] >= 0.08  # Allow some tolerance
        # Second delay should be ~0.2s (0.1 * 2)
        assert delays[1] >= 0.18
        # Third delay should be ~0.4s (0.1 * 2^2)
        assert delays[2] >= 0.35

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
    async def test_sync_retry_success_after_retries(self):
        """Test that retry eventually succeeds for sync functions after transient failures."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        )
        def flaky_sync_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Transient error")
            return "success"

        result = flaky_sync_operation()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_sync_retry_exhausted(self):
        """Test that retry raises exception for sync functions after all retries."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        )
        def failing_sync_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Persistent error")

        with pytest.raises(ValueError, match="Persistent error"):
            failing_sync_operation()

        assert call_count == 3  # Initial attempt + 2 retries

    @pytest.mark.asyncio
    async def test_retry_with_custom_exception_types(self):
        """Test that retry only catches specified exception types."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)  # Only catch ValueError
        )
        async def selective_operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Retriable error")
            elif call_count == 2:
                raise TypeError("Non-retriable error")
            return "success"

        # Should retry ValueError but fail immediately on TypeError
        with pytest.raises(TypeError, match="Non-retriable error"):
            await selective_operation()

        assert call_count == 2  # First attempt failed with ValueError (retried), second failed with TypeError

    @pytest.mark.asyncio
    async def test_retry_with_on_retry_callback(self):
        """Test that custom retry callback is invoked on each retry attempt."""
        call_count = 0
        retry_attempts = []

        def retry_callback(attempt, exception):
            retry_attempts.append((attempt, exception))

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,),
            on_retry=retry_callback
        )
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await failing_operation()

        # Verify callback was called for each retry
        assert len(retry_attempts) == 3
        # Verify attempt numbers (should be 1, 2, 3)
        assert retry_attempts[0][0] == 1
        assert retry_attempts[1][0] == 2
        assert retry_attempts[2][0] == 3
        # Verify exception was passed
        assert all(isinstance(exc, ValueError) for _, exc in retry_attempts)


class TestRetryHelpers:
    """Tests for retry_async and retry_sync helper functions."""

    @pytest.mark.asyncio
    async def test_retry_async_helper(self):
        """Test retry_async helper function."""
        call_count = 0

        async def flaky_func(x, y):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Transient error")
            return x + y

        result = await retry_async(
            flaky_func,
            5,
            3,
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        )

        assert result == 8
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_sync_helper(self):
        """Test retry_sync helper function."""
        call_count = 0

        def flaky_func(x, y):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Transient error")
            return x + y

        result = retry_sync(
            flaky_func,
            5,
            3,
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        )

        assert result == 8
        assert call_count == 2


class TestRetryContext:
    """Tests for RetryContext manager."""

    @pytest.mark.asyncio
    async def test_retry_context_async_execute(self):
        """Test RetryContext.execute_async method."""
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Transient error")
            return "success"

        async with RetryContext(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        ) as ctx:
            result = await ctx.execute_async(flaky_func)

        assert result == "success"
        assert call_count == 2
        assert ctx.attempt_count == 1  # Should be set to last successful attempt
        assert ctx.last_exception is None

    @pytest.mark.asyncio
    async def test_retry_context_sync_execute(self):
        """Test RetryContext.execute_sync method."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Transient error")
            return "success"

        with RetryContext(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        ) as ctx:
            result = ctx.execute_sync(flaky_func)

        assert result == "success"
        assert call_count == 2
        assert ctx.attempt_count == 1
        assert ctx.last_exception is None

    @pytest.mark.asyncio
    async def test_retry_context_exhausted(self):
        """Test RetryContext when retries are exhausted."""
        call_count = 0

        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Persistent error")

        async with RetryContext(
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(ValueError,)
        ) as ctx:
            with pytest.raises(ValueError):
                await ctx.execute_async(failing_func)

        assert call_count == 3  # Initial + 2 retries
        assert ctx.attempt_count == 2  # Last attempt number
        assert ctx.last_exception is not None


class TestRealWorldScenarios:
    """Test retry logic with real-world scenarios."""

    @pytest.mark.asyncio
    async def test_file_io_retry_simulation(self):
        """Test retry logic with simulated file I/O failures."""
        attempt_count = 0
        file_contents = ["content1", "content2", "content3"]

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            exceptions=(IOError, OSError)
        )
        async def read_file_with_transient_locks():
            nonlocal attempt_count
            attempt_count += 1
            # Simulate file lock on first two attempts
            if attempt_count <= 2:
                raise IOError("File temporarily locked")
            return file_contents[attempt_count - 1]

        result = await read_file_with_transient_locks()
        assert result == "content3"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_database_connection_retry_simulation(self):
        """Test retry logic with simulated database connection issues."""
        attempt_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.1,
            max_delay=1.0,
            exceptions=(ConnectionError, TimeoutError)
        )
        async def connect_to_database():
            nonlocal attempt_count
            attempt_count += 1
            # Simulate connection issues
            if attempt_count == 1:
                raise ConnectionError("Connection refused")
            elif attempt_count == 2:
                raise TimeoutError("Connection timeout")
            return "database_connection"

        result = await connect_to_database()
        assert result == "database_connection"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_network_request_retry_simulation(self):
        """Test retry logic with simulated network failures."""
        attempt_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.05,
            max_delay=0.5,
            exceptions=(ConnectionError,)
        )
        async def fetch_data():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError("Network unreachable")
            return {"status": "success", "data": "sample"}

        result = await fetch_data()
        assert result == {"status": "success", "data": "sample"}
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_maximum_delay_cap(self):
        """Test that maximum delay cap is respected during exponential backoff."""
        attempt_count = 0

        @retry_with_exponential_backoff(
            max_retries=5,
            base_delay=0.1,
            max_delay=0.3,  # Cap at 0.3s
            exceptions=(ValueError,)
        )
        async def operation_with_delays():
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError("Test error")

        start_time = time.time()
        with pytest.raises(ValueError):
            await operation_with_delays()

        total_time = time.time() - start_time

        # With base_delay=0.1 and max_delay=0.3, the delay sequence should be:
        # 0.1, 0.2, 0.3, 0.3, 0.3 (capped at max_delay)
        # Total should be approximately 1.2s (allowing for test execution time)
        assert total_time >= 0.8  # At least 0.8s of delays
        assert total_time <= 2.0  # But not excessively long
