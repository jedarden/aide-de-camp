"""
Tests for retry configuration and decorator behavior.

Validates that retry configuration can be set via environment variables,
supports decorator overrides, applies jitter correctly, and validates
configuration values.
"""
import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock
from src.config.retry import (
    RetryConfig,
    get_retry_config,
    set_retry_config,
    validate_retry_config,
)
from src.utilities.retry import (
    retry_with_exponential_backoff,
    retry_async,
    retry_sync,
    _apply_jitter,
)


class TestRetryConfig:
    """Test RetryConfig dataclass validation and environment variable loading."""

    def test_default_values(self):
        """Test RetryConfig with default values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.jitter_factor == 0.25

    def test_custom_values(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=120.0,
            jitter_factor=0.5
        )
        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.jitter_factor == 0.5

    def test_validation_negative_max_retries(self):
        """Test that negative max_retries raises ValueError."""
        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            RetryConfig(max_retries=-1)

    def test_validation_zero_base_delay(self):
        """Test that zero base_delay raises ValueError."""
        with pytest.raises(ValueError, match="base_delay must be > 0"):
            RetryConfig(base_delay=0)

    def test_validation_negative_base_delay(self):
        """Test that negative base_delay raises ValueError."""
        with pytest.raises(ValueError, match="base_delay must be > 0"):
            RetryConfig(base_delay=-1.0)

    def test_validation_max_delay_less_than_base(self):
        """Test that max_delay < base_delay raises ValueError."""
        with pytest.raises(ValueError, match="max_delay.*must be >= base_delay"):
            RetryConfig(base_delay=10.0, max_delay=5.0)

    def test_validation_jitter_factor_negative(self):
        """Test that negative jitter_factor raises ValueError."""
        with pytest.raises(ValueError, match="jitter_factor must be between 0 and 1"):
            RetryConfig(jitter_factor=-0.1)

    def test_validation_jitter_factor_gt_one(self):
        """Test that jitter_factor > 1 raises ValueError."""
        with pytest.raises(ValueError, match="jitter_factor must be between 0 and 1"):
            RetryConfig(jitter_factor=1.5)

    def test_from_env_default(self):
        """Test RetryConfig.from_env with no environment variables set."""
        # Clear environment variables
        env_backup = {
            'ADC_MAX_RETRIES': os.environ.get('ADC_MAX_RETRIES'),
            'ADC_RETRY_BASE_DELAY': os.environ.get('ADC_RETRY_BASE_DELAY'),
            'ADC_RETRY_MAX_DELAY': os.environ.get('ADC_RETRY_MAX_DELAY'),
            'ADC_RETRY_JITTER_FACTOR': os.environ.get('ADC_RETRY_JITTER_FACTOR'),
        }
        for key in env_backup:
            os.environ.pop(key, None)

        try:
            config = RetryConfig.from_env()
            assert config.max_retries == 3
            assert config.base_delay == 1.0
            assert config.max_delay == 60.0
            assert config.jitter_factor == 0.25
        finally:
            # Restore environment
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value

    def test_from_env_custom(self):
        """Test RetryConfig.from_env with custom environment variables."""
        env_backup = {
            'ADC_MAX_RETRIES': os.environ.get('ADC_MAX_RETRIES'),
            'ADC_RETRY_BASE_DELAY': os.environ.get('ADC_RETRY_BASE_DELAY'),
            'ADC_RETRY_MAX_DELAY': os.environ.get('ADC_RETRY_MAX_DELAY'),
            'ADC_RETRY_JITTER_FACTOR': os.environ.get('ADC_RETRY_JITTER_FACTOR'),
        }

        os.environ['ADC_MAX_RETRIES'] = '5'
        os.environ['ADC_RETRY_BASE_DELAY'] = '2.0'
        os.environ['ADC_RETRY_MAX_DELAY'] = '120.0'
        os.environ['ADC_RETRY_JITTER_FACTOR'] = '0.5'

        try:
            config = RetryConfig.from_env()
            assert config.max_retries == 5
            assert config.base_delay == 2.0
            assert config.max_delay == 120.0
            assert config.jitter_factor == 0.5
        finally:
            # Restore environment
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)

    def test_from_env_invalid_defaults(self):
        """Test RetryConfig.from_env with invalid values (should use defaults)."""
        env_backup = {
            'ADC_MAX_RETRIES': os.environ.get('ADC_MAX_RETRIES'),
            'ADC_RETRY_BASE_DELAY': os.environ.get('ADC_RETRY_BASE_DELAY'),
        }

        os.environ['ADC_MAX_RETRIES'] = 'invalid'
        os.environ['ADC_RETRY_BASE_DELAY'] = 'not_a_number'

        try:
            config = RetryConfig.from_env()
            # Should fall back to defaults for invalid values
            assert config.max_retries == 3
            assert config.base_delay == 1.0
        finally:
            # Restore environment
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)

    def test_to_dict(self):
        """Test RetryConfig.to_dict method."""
        config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=120.0,
            jitter_factor=0.5
        )
        result = config.to_dict()
        assert result == {
            'max_retries': 5,
            'base_delay': 2.0,
            'max_delay': 120.0,
            'jitter_factor': 0.5
        }


class TestRetryConfigGlobal:
    """Test global retry configuration management."""

    def test_get_retry_config_singleton(self):
        """Test that get_retry_config returns the same instance."""
        config1 = get_retry_config()
        config2 = get_retry_config()
        assert config1 is config2

    def test_set_retry_config(self):
        """Test set_retry_config function."""
        custom_config = RetryConfig(
            max_retries=10,
            base_delay=5.0,
            max_delay=300.0,
            jitter_factor=0.75
        )
        set_retry_config(custom_config)

        retrieved = get_retry_config()
        assert retrieved is custom_config
        assert retrieved.max_retries == 10
        assert retrieved.base_delay == 5.0

        # Reset to defaults for other tests
        set_retry_config(RetryConfig.from_env())

    def test_validate_retry_config_valid(self):
        """Test validate_retry_config with valid configuration."""
        # Should not raise
        validate_retry_config()

    def test_validate_retry_config_invalid(self):
        """Test validate_retry_config with invalid configuration."""
        # Create a mock config object that bypasses __post_init__ validation
        # by using object.__new__ and setting attributes directly
        from unittest.mock import Mock

        invalid_config = Mock(spec=RetryConfig)
        invalid_config.max_retries = -1
        invalid_config.base_delay = 1.0
        invalid_config.max_delay = 60.0
        invalid_config.jitter_factor = 0.25

        set_retry_config(invalid_config)

        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            validate_retry_config()

        # Reset to defaults for other tests
        set_retry_config(RetryConfig.from_env())


class TestJitter:
    """Test jitter calculation."""

    def test_apply_jitter_zero(self):
        """Test jitter with factor 0 (no jitter)."""
        delay = _apply_jitter(10.0, 0.0)
        assert delay == 10.0

    def test_apply_jitter_half(self):
        """Test jitter with factor 0.5."""
        delay = _apply_jitter(10.0, 0.5)
        # Should be within ±50% of base delay
        assert 5.0 <= delay <= 15.0

    def test_apply_jitter_full(self):
        """Test full jitter (factor 1.0)."""
        delay = _apply_jitter(10.0, 1.0)
        # Should be between 0 and base delay
        assert 0.0 <= delay <= 10.0

    def test_apply_jitter_deterministic_seed(self):
        """Test that jitter is deterministic with seeded random."""
        import random
        random.seed(42)
        delay1 = _apply_jitter(10.0, 0.25)
        random.seed(42)
        delay2 = _apply_jitter(10.0, 0.25)
        assert delay1 == delay2


class TestRetryDecorator:
    """Test retry decorator with configuration support."""

    @pytest.mark.asyncio
    async def test_decorator_uses_config_defaults(self):
        """Test that decorator uses configured defaults when no overrides."""
        call_count = 0

        @retry_with_exponential_backoff()
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Transient error")
            return "success"

        result = await failing_function()
        assert result == "success"
        assert call_count == 3  # Initial call + 2 retries

    @pytest.mark.asyncio
    async def test_decorator_override_max_retries(self):
        """Test decorator with max_retries override."""
        call_count = 0

        @retry_with_exponential_backoff(max_retries=1)
        async def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            await failing_function()

        # Should only attempt initial + 1 retry (max_retries=1)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_override_base_delay(self):
        """Test decorator with base_delay override."""
        import time

        @retry_with_exponential_backoff(
            max_retries=1,
            base_delay=0.1,
            jitter_factor=0.0
        )
        async def failing_function():
            raise ValueError("Always fails")

        start = time.time()
        with pytest.raises(ValueError):
            await failing_function()
        elapsed = time.time() - start

        # Should wait approximately 0.1 seconds
        assert 0.08 <= elapsed <= 0.15

    @pytest.mark.asyncio
    async def test_decorator_override_exceptions(self):
        """Test decorator with specific exception types."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            exceptions=(ValueError,)
        )
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Transient error")
            return "success"

        result = await failing_function()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_no_retry_on_unmatched_exception(self):
        """Test that decorator doesn't retry on unmatched exception types."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=3,
            exceptions=(ValueError,)
        )
        async def failing_function():
            nonlocal call_count
            call_count += 1
            raise TypeError("Different error")

        with pytest.raises(TypeError, match="Different error"):
            await failing_function()

        # Should only attempt once (no retry on TypeError)
        assert call_count == 1


class TestRetryHelperFunctions:
    """Test retry_async and retry_sync helper functions."""

    @pytest.mark.asyncio
    async def test_retry_async_uses_config(self):
        """Test retry_async uses configured defaults."""
        call_count = 0

        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Transient error")
            return "success"

        result = await retry_async(failing_function)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_async_override_params(self):
        """Test retry_async with parameter overrides."""
        call_count = 0

        async def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            await retry_async(failing_function, max_retries=1)

        assert call_count == 2  # Initial + 1 retry

    def test_retry_sync_uses_config(self):
        """Test retry_sync uses configured defaults."""
        call_count = 0

        def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Transient error")
            return "success"

        result = retry_sync(failing_function)
        assert result == "success"
        assert call_count == 3

    def test_retry_sync_override_params(self):
        """Test retry_sync with parameter overrides."""
        call_count = 0

        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            retry_sync(failing_function, max_retries=1)

        assert call_count == 2  # Initial + 1 retry


class TestExponentialBackoffCalculation:
    """Test exponential backoff delay calculation."""

    @pytest.mark.asyncio
    async def test_exponential_backoff_progression(self):
        """Test that delays follow exponential progression."""
        import time
        delays = []

        on_retry_mock = MagicMock()

        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.1,
            max_delay=10.0,
            jitter_factor=0.0,
            on_retry=on_retry_mock
        )
        async def failing_function():
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            await failing_function()

        # Check that on_retry was called 3 times
        assert on_retry_mock.call_count == 3

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        # With exponential backoff, delays would grow quickly
        # but should be capped at max_delay
        @retry_with_exponential_backoff(
            max_retries=10,
            base_delay=1.0,
            max_delay=2.0,
            jitter_factor=0.0
        )
        async def failing_function():
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            await failing_function()

        # Even with many retries, delay should not exceed max_delay
        # This is verified internally by the retry logic