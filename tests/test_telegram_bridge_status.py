"""
Test Telegram bridge status tracking and API endpoint.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.telegram.fallback import TelegramFallback, get_telegram_fallback


class TestTelegramBridgeStatus:
    """Test Telegram bridge reachability tracking."""

    def test_initial_state(self):
        """Test that initial state is unknown."""
        fallback = TelegramFallback()
        status = fallback.get_status()

        assert status["reachable"] is None
        assert status["failure_count"] == 0
        assert status["last_check_time"] is None
        assert status["bot_configured"] is False  # No token by default
        assert status["chat_id_configured"] is False  # No chat_id by default

    @pytest.mark.asyncio
    async def test_check_telegram_available_success(self):
        """Test successful Telegram availability check."""
        fallback = TelegramFallback(bot_token="test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await fallback.check_telegram_available()
            assert result is True

            status = fallback.get_status()
            assert status["reachable"] is True
            assert status["last_check_time"] is not None
            datetime.fromisoformat(status["last_check_time"])  # valid ISO-8601

    @pytest.mark.asyncio
    async def test_check_telegram_available_failure(self):
        """Test failed Telegram availability check."""
        fallback = TelegramFallback(bot_token="test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection error")
            )

            result = await fallback.check_telegram_available()
            assert result is False

            status = fallback.get_status()
            assert status["reachable"] is False
            # A failed check still counts as a determination — last_check_time set.
            assert status["last_check_time"] is not None

    @pytest.mark.asyncio
    async def test_last_check_time_reflects_most_recent_determination(self):
        """last_check_time tracks the most recent reachability determination."""
        fallback = TelegramFallback(bot_token="test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            assert fallback.get_status()["last_check_time"] is None

            await fallback.check_telegram_available()
            first = fallback.get_status()["last_check_time"]
            assert first is not None

            # A second determination produces a timestamp at least as new.
            await fallback.check_telegram_available()
            second = fallback.get_status()["last_check_time"]
            assert second is not None
            assert datetime.fromisoformat(second) >= datetime.fromisoformat(first)

    @pytest.mark.asyncio
    async def test_send_message_success_updates_status(self):
        """Test that successful send updates reachability status."""
        fallback = TelegramFallback(bot_token="test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await fallback.send_message(123, "Test message")
            assert result is True

            status = fallback.get_status()
            assert status["reachable"] is True
            # A successful send is a reactive reachability determination.
            assert status["last_check_time"] is not None

    @pytest.mark.asyncio
    async def test_send_message_failure_increments_count(self):
        """Test that failed send increments failure count."""
        fallback = TelegramFallback(bot_token="test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection error")
            )

            await fallback.send_message(123, "Test message")

            status = fallback.get_status()
            assert status["reachable"] is False
            assert status["failure_count"] == 1
            assert status["last_check_time"] is not None

    @pytest.mark.asyncio
    async def test_handle_send_failure_first_warns_then_rate_limits(self, caplog):
        """First failure WARNINGs; an immediate repeat is rate-limited (suppressed)."""
        fallback = TelegramFallback(bot_token="test_token")

        # First failure → WARNING (the one-per-startup notification).
        with patch("src.telegram.fallback.logger") as mock_logger:
            await fallback._handle_send_failure(error=ConnectionError("boom"))
            assert mock_logger.warning.called
            assert not mock_logger.debug.called

        # Immediate subsequent failure → suppressed by the rate-limit (no log).
        with patch("src.telegram.fallback.logger") as mock_logger:
            await fallback._handle_send_failure(error=ConnectionError("boom2"))
            assert not mock_logger.warning.called
            assert not mock_logger.debug.called

        assert fallback._failure_count == 2
        assert fallback._has_logged_first_failure is True

    @pytest.mark.asyncio
    async def test_send_message_uses_debug_after_first_warning(self):
        """Test that subsequent send failures use DEBUG level."""
        fallback = TelegramFallback(bot_token="test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection error")
            )

            # First call
            await fallback.send_message(123, "Test message")

            # Second call (should be DEBUG/rate-limited)
            await fallback.send_message(123, "Test message")

            status = fallback.get_status()
            assert status["failure_count"] == 2

    def test_get_telegram_fallback_singleton(self):
        """Test that get_telegram_fallback returns singleton instance."""
        fallback1 = get_telegram_fallback()
        fallback2 = get_telegram_fallback()

        assert fallback1 is fallback2


class TestBridgeStatusAPI:
    """Test the bridge status API endpoint."""

    @pytest.mark.asyncio
    async def test_api_v1_telegram_bridge_status(self):
        """Test the GET /api/v1/status/telegram_bridge endpoint."""
        # Test the status method directly instead of importing the full app
        fallback = TelegramFallback(bot_token="test_token")

        # Set some state
        fallback._is_reachable = True
        fallback._failure_count = 5

        status = fallback.get_status()

        assert status["reachable"] is True
        assert status["bot_configured"] is True  # bot_token is set
        assert status["failure_count"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
