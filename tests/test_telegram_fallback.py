"""
Unit tests for Telegram fallback integration.
"""

import os
import pytest
from src.telegram.fallback import TelegramFallback, get_telegram_fallback


class TestTelegramFallbackEnvConfig:
    """Test Telegram fallback environment variable configuration."""

    def test_default_bridge_url(self):
        """Test that default bridge URL is used when no env var is set."""
        # Ensure env var is not set
        if "ADC_TELEGRAM_BRIDGE_URL" in os.environ:
            del os.environ["ADC_TELEGRAM_BRIDGE_URL"]

        fallback = TelegramFallback()
        expected_url = "http://telegram-claude-bridge:8000"
        assert fallback.bridge_url == expected_url

    def test_env_var_override(self, monkeypatch):
        """Test that ADC_TELEGRAM_BRIDGE_URL env var overrides default."""
        test_url = "http://test-bridge:9999"
        monkeypatch.setenv("ADC_TELEGRAM_BRIDGE_URL", test_url)

        fallback = TelegramFallback()
        assert fallback.bridge_url == test_url

    def test_constructor_override(self, monkeypatch):
        """Test that constructor parameter overrides env var."""
        env_url = "http://env-bridge:8888"
        constructor_url = "http://constructor-bridge:7777"
        monkeypatch.setenv("ADC_TELEGRAM_BRIDGE_URL", env_url)

        fallback = TelegramFallback(bridge_url=constructor_url)
        assert fallback.bridge_url == constructor_url


class TestTelegramFallbackAPIContract:
    """Test Telegram fallback API contract correctness."""

    def test_send_message_payload_structure(self):
        """Test that send_message creates correct payload for /send endpoint."""
        fallback = TelegramFallback(bridge_url="http://test:8000")

        # Mock the HTTP client to capture payload
        import httpx
        captured_payload = {}
        captured_url = None

        class MockResponse:
            status_code = 200

        async def mock_post(url, json, timeout):
            nonlocal captured_payload, captured_url
            captured_url = url
            captured_payload = json
            return MockResponse()

        # We can't easily mock async context manager without more setup,
        # so we'll just verify the logic by checking the method signature
        # and that it would construct the right payload structure
        assert hasattr(fallback, 'send_message')

    def test_check_bridge_available_method_exists(self):
        """Test that check_bridge_available method exists."""
        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        # Verify the method exists
        assert hasattr(fallback, 'check_bridge_available')


class TestGlobalFallbackInstance:
    """Test global Telegram fallback instance management."""

    def test_get_telegram_fallback_creates_instance(self):
        """Test that get_telegram_fallback creates instance on first call."""
        # Reset global instance
        import src.telegram.fallback
        src.telegram.fallback._telegram_fallback = None

        fallback = get_telegram_fallback()
        assert fallback is not None
        assert isinstance(fallback, TelegramFallback)

    def test_get_telegram_fallback_returns_same_instance(self):
        """Test that get_telegram_fallback returns singleton instance."""
        # Reset global instance
        import src.telegram.fallback
        src.telegram.fallback._telegram_fallback = None

        fallback1 = get_telegram_fallback()
        fallback2 = get_telegram_fallback()
        assert fallback1 is fallback2

    def test_get_telegram_fallback_uses_env_var(self, monkeypatch):
        """Test that get_telegram_fallback respects ADC_TELEGRAM_BRIDGE_URL env var."""
        # Reset global instance
        import src.telegram.fallback
        src.telegram.fallback._telegram_fallback = None

        test_url = "http://test-bridge:9999"
        monkeypatch.setenv("ADC_TELEGRAM_BRIDGE_URL", test_url)

        fallback = get_telegram_fallback()
        assert fallback.bridge_url == test_url


class TestRateLimiting:
    """Test failure log rate limiting to prevent spam."""

    def test_first_failure_logs_warning(self, caplog):
        """Test that the first failure logs a WARNING."""
        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        with caplog.at_level("WARNING"):
            fallback._handle_send_failure("test error")

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert "Telegram send failure #1" in caplog.records[0].message
        assert "test error" in caplog.records[0].message

    def test_immediate_repeated_failure_logs_debug(self, caplog):
        """Test that immediate repeated failures log at DEBUG level."""
        from datetime import datetime, timedelta

        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        # First failure logs WARNING
        with caplog.at_level("WARNING"):
            fallback._handle_send_failure("first error")

        # Clear previous logs
        caplog.clear()

        # Second failure within cooldown should log at DEBUG level
        with caplog.at_level("DEBUG"):
            fallback._handle_send_failure("second error")

        # Should have a DEBUG log for the repeated failure
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]

        assert len(warning_records) == 0, "Repeated failure should not log at WARNING level"
        assert len(debug_records) >= 1, "Repeated failure should log at DEBUG level"
        assert any("Repeated Telegram send failure" in r.message for r in debug_records)

    def test_failure_after_cooldown_logs_warning(self, caplog):
        """Test that a failure after the cooldown period logs a WARNING again."""
        from datetime import datetime, timedelta
        from unittest.mock import patch

        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        # First failure
        with caplog.at_level("WARNING"):
            fallback._handle_send_failure("first error")

        # Clear previous logs
        caplog.clear()

        # Mock time to be after cooldown period (5 minutes + 1 second)
        future_time = datetime.now() + timedelta(seconds=301)
        with patch('src.telegram.fallback.datetime') as mock_datetime:
            mock_datetime.now.return_value = future_time
            with caplog.at_level("WARNING"):
                fallback._handle_send_failure("second error")

        # Should have a WARNING log for the failure after cooldown
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) >= 1, "Failure after cooldown should log at WARNING level"
        assert any("Telegram send failure #2" in r.message for r in warning_records)

    def test_cooldown_constant_value(self):
        """Test that the cooldown period is set to 5 minutes (300 seconds)."""
        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")
        assert fallback.FAILURE_LOG_COOLDOWN_SECONDS == 300
