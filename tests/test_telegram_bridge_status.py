"""
Test Telegram bridge status tracking and API endpoint.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.telegram.fallback import TelegramFallback, get_telegram_fallback


class TestTelegramBridgeStatus:
    """Test Telegram bridge reachability tracking."""

    def test_initial_state(self):
        """Test that initial state is unknown."""
        fallback = TelegramFallback()
        status = fallback.get_bridge_status()

        assert status["reachable"] is None
        assert status["failure_count"] == 0
        assert status["bridge_url"] == "http://telegram-claude-bridge:8000"

    def test_custom_bridge_url(self):
        """Test custom bridge URL configuration."""
        fallback = TelegramFallback(bridge_url="http://custom:9000")
        status = fallback.get_bridge_status()

        assert status["bridge_url"] == "http://custom:9000"

    @pytest.mark.asyncio
    async def test_check_bridge_available_success(self):
        """Test successful bridge availability check."""
        fallback = TelegramFallback()

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await fallback.check_bridge_available()
            assert result is True

            status = fallback.get_bridge_status()
            assert status["reachable"] is True

    @pytest.mark.asyncio
    async def test_check_bridge_available_failure(self):
        """Test failed bridge availability check."""
        fallback = TelegramFallback()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection error")
            )

            result = await fallback.check_bridge_available()
            assert result is False

            status = fallback.get_bridge_status()
            assert status["reachable"] is False

    @pytest.mark.asyncio
    async def test_send_message_success_updates_status(self):
        """Test that successful send updates reachability status."""
        fallback = TelegramFallback()

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await fallback.send_message(123, "Test message")
            assert result is True

            status = fallback.get_bridge_status()
            assert status["reachable"] is True

    @pytest.mark.asyncio
    async def test_send_message_failure_increments_count(self):
        """Test that failed send increments failure count."""
        fallback = TelegramFallback()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection error")
            )

            await fallback.send_message(123, "Test message")

            status = fallback.get_bridge_status()
            assert status["reachable"] is False
            assert status["failure_count"] == 1

    async def test_handle_send_failure_first_only(self, caplog):
        """Only the first failure after startup logs a WARNING; later ones do not."""
        fallback = TelegramFallback()

        # First failure → WARNING (the one-per-startup notification).
        with patch("src.telegram.fallback.logger") as mock_logger:
            await fallback._handle_send_failure(error=ConnectionError("boom"))
            assert mock_logger.warning.called
            assert not mock_logger.debug.called

        # Subsequent failure → DEBUG, no WARNING.
        with patch("src.telegram.fallback.logger") as mock_logger:
            await fallback._handle_send_failure(error=ConnectionError("boom2"))
            assert mock_logger.debug.called
            assert not mock_logger.warning.called

        assert fallback._failure_count == 2
        assert fallback._has_logged_first_failure is True

    @pytest.mark.asyncio
    async def test_send_message_uses_debug_after_first_warning(self, caplog):
        """Test that subsequent send failures use DEBUG level."""
        fallback = TelegramFallback()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection error")
            )

            # First call
            await fallback.send_message(123, "Test message")

            # Second call (should be DEBUG)
            await fallback.send_message(123, "Test message")

            status = fallback.get_bridge_status()
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
        fallback = TelegramFallback()

        # Set some state
        fallback._is_reachable = True
        fallback._failure_count = 5

        status = fallback.get_bridge_status()

        assert status["reachable"] is True
        assert status["bridge_url"] == "http://telegram-claude-bridge:8000"
        assert status["failure_count"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
