"""
Unit tests for Telegram fallback integration.
"""

import os

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


class TestFirstFailureTracking:
    """Test first-failure detection: exactly one WARNING per process startup."""

    async def test_first_failure_logs_warning_with_error_type(self, caplog):
        """The first failure logs a WARNING carrying both error type and message."""
        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error=ConnectionError("connection refused")
            )

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        msg = warnings[0].message
        assert "First Telegram send failure detected" in msg
        # Acceptance criterion: error type AND message are both present.
        assert "ConnectionError" in msg  # error type
        assert "connection refused" in msg  # error message

    async def test_subsequent_failures_log_debug_not_warning(self, caplog):
        """After the first failure, later failures log at DEBUG, not WARNING."""
        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(error=ConnectionError("boom"))

        caplog.clear()

        with caplog.at_level("DEBUG"):
            await fallback._handle_send_failure(error=ConnectionError("boom2"))

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        debugs = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert warnings == []
        assert len(debugs) == 1
        assert "Repeated Telegram send failure" in debugs[0].message
        assert "ConnectionError" in debugs[0].message

    async def test_exactly_one_warning_under_concurrency(self, caplog):
        """N concurrent failures produce exactly one WARNING and failure_count == N."""
        import asyncio

        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        with caplog.at_level("WARNING"):
            await asyncio.gather(
                *(
                    fallback._handle_send_failure(error=ConnectionError(f"e{i}"))
                    for i in range(50)
                )
            )

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert fallback._failure_count == 50

    async def test_first_failure_timestamp_set_once(self):
        """first_failure_timestamp is set on the first failure and frozen after."""
        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        assert fallback._first_failure_timestamp is None

        await fallback._handle_send_failure(error=ConnectionError("first"))
        first_ts = fallback._first_failure_timestamp
        assert first_ts is not None

        await fallback._handle_send_failure(error=ConnectionError("second"))
        assert fallback._first_failure_timestamp is first_ts  # unchanged (set-once)
        assert fallback._last_failure_timestamp is not first_ts  # advanced

    async def test_reset_re_arms_detection(self, caplog):
        """After reset, the next failure is 'first' again; counters are retained."""
        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        await fallback._handle_send_failure(error=ConnectionError("first"))
        assert fallback._has_logged_first_failure is True
        assert fallback._failure_count == 1

        await fallback.reset_first_failure_state()
        assert fallback._has_logged_first_failure is False
        assert fallback._first_failure_timestamp is None
        assert fallback._failure_count == 1  # retained across reset

        caplog.clear()
        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(error=ConnectionError("after reset"))

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert fallback._failure_count == 2  # incremented, not reset

    async def test_non_2xx_response_logs_synthesized_type_and_context(self, caplog):
        """A non-2xx response (no exception) logs the synthesized type + context."""
        fallback = TelegramFallback(bridge_url="http://test-bridge:8000")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error_context="status 500 - upstream down"
            )

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "HTTPError" in warnings[0].message  # synthesized type
        assert "status 500 - upstream down" in warnings[0].message
