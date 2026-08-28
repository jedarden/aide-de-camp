"""
Tests for OpenBao client integration with Telegram fallback.

Tests the OpenBao secret retrieval functionality and its integration
with the Telegram fallback system.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.openbao import OpenBaoClient, get_openbao_client
from src.telegram.fallback import TelegramFallback


class TestOpenBaoClient:
    """Test OpenBao client functionality."""

    def test_get_openbao_client_creates_singleton(self):
        """Verify get_openbao_client returns the same instance."""
        client1 = get_openbao_client()
        client2 = get_openbao_client()
        assert client1 is client2

    def test_openbao_client_init_with_defaults(self):
        """Test client initialization with default environment variables."""
        client = OpenBaoClient()
        assert client.url == "http://traefik-ardenone-cluster:8200"

    def test_openbao_client_init_with_custom_url(self):
        """Test client initialization with custom URL."""
        client = OpenBaoClient(url="http://custom:8200")
        assert client.url == "http://custom:8200"

    def test_openbao_client_without_token_logs_warning(self, caplog):
        """Test that initializing without token logs a warning."""
        # Ensure no OPENBAO_TOKEN is set
        token = os.environ.pop("OPENBAO_TOKEN", None)
        try:
            client = OpenBaoClient()
            assert client.token is None
            assert any("OpenBao client initialized without token" in record.message
                      for record in caplog.records)
        finally:
            if token:
                os.environ["OPENBAO_TOKEN"] = token

    @patch('src.openbao.client.hvac.Client')
    def test_get_secret_success(self, mock_hvac_client):
        """Test successful secret retrieval."""
        # Mock the hvac client response
        mock_client_instance = MagicMock()
        mock_hvac_client.return_value = mock_client_instance

        mock_response = {
            "data": {
                "data": {
                    "token": "test_bot_token_123"
                }
            }
        }
        mock_client_instance.secrets.kv.v2.read_secret_version.return_value = mock_response

        client = OpenBaoClient(token="test_token")
        value = client.get_secret("secret/test/path", field="token")

        assert value == "test_bot_token_123"
        mock_client_instance.secrets.kv.v2.read_secret_version.assert_called_once_with(
            path="secret/test/path"
        )

    @patch('src.openbao.client.hvac.Client')
    def test_get_secret_field_not_found(self, mock_hvac_client, caplog):
        """Test secret retrieval when field doesn't exist."""
        mock_client_instance = MagicMock()
        mock_hvac_client.return_value = mock_client_instance

        mock_response = {
            "data": {
                "data": {
                    "other_field": "value"
                }
            }
        }
        mock_client_instance.secrets.kv.v2.read_secret_version.return_value = mock_response

        client = OpenBaoClient(token="test_token")
        value = client.get_secret("secret/test/path", field="token")

        assert value is None
        assert any("Field 'token' not found" in record.message
                  for record in caplog.records)

    @patch('src.openbao.client.hvac.Client')
    def test_get_secret_invalid_path(self, mock_hvac_client, caplog):
        """Test secret retrieval with invalid path."""
        from hvac.exceptions import InvalidPath

        mock_client_instance = MagicMock()
        mock_hvac_client.return_value = mock_client_instance
        mock_client_instance.secrets.kv.v2.read_secret_version.side_effect = InvalidPath()

        client = OpenBaoClient(token="test_token")
        value = client.get_secret("secret/invalid/path", field="value")

        assert value is None
        assert any("Invalid OpenBao path" in record.message
                  for record in caplog.records)

    @patch('src.openbao.client.hvac.Client')
    def test_check_secret_exists_true(self, mock_hvac_client):
        """Test check_secret_exists returns True when secret exists."""
        mock_client_instance = MagicMock()
        mock_hvac_client.return_value = mock_client_instance
        mock_client_instance.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "test"}}
        }

        client = OpenBaoClient(token="test_token")
        exists = client.check_secret_exists("secret/test/path")

        assert exists is True

    @patch('src.openbao.client.hvac.Client')
    def test_check_secret_exists_false(self, mock_hvac_client):
        """Test check_secret_exists returns False when secret doesn't exist."""
        from hvac.exceptions import InvalidPath

        mock_client_instance = MagicMock()
        mock_hvac_client.return_value = mock_client_instance
        mock_client_instance.secrets.kv.v2.read_secret_version.side_effect = InvalidPath()

        client = OpenBaoClient(token="test_token")
        exists = client.check_secret_exists("secret/invalid/path")

        assert exists is False


class TestTelegramFallbackOpenBaoIntegration:
    """Test Telegram fallback integration with OpenBao."""

    def setup_method(self):
        """Clear environment before each test."""
        # Save original values
        self.original_env = {}
        for key in ["ADC_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN_PATH", "OPENBAO_TOKEN"]:
            self.original_env[key] = os.environ.get(key)
            os.environ.pop(key, None)

    def teardown_method(self):
        """Restore environment after each test."""
        for key, value in self.original_env.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

    def test_bot_token_from_direct_env_var(self):
        """Test bot token resolution from ADC_TELEGRAM_BOT_TOKEN env var."""
        os.environ["ADC_TELEGRAM_BOT_TOKEN"] = "direct_token_123"
        fallback = TelegramFallback()
        assert fallback.bot_token == "direct_token_123"

    def test_bot_token_from_constructor_arg(self):
        """Test bot token resolution from constructor argument."""
        os.environ["ADC_TELEGRAM_BOT_TOKEN"] = "env_token_123"
        fallback = TelegramFallback(bot_token="constructor_token_456")
        assert fallback.bot_token == "constructor_token_456"

    @patch('src.openbao.client.hvac.Client')
    def test_bot_token_from_openbao_path(self, mock_hvac_client_class):
        """Test bot token resolution from OpenBao path."""
        # Clear any global OpenBao client that might have been created
        from src.openbao import client
        client._openbao_client = None

        # Mock OpenBao response
        mock_client_instance = MagicMock()
        mock_hvac_client_class.return_value = mock_client_instance

        mock_response = {
            "data": {
                "data": {
                    "token": "openbao_token_789"
                }
            }
        }
        mock_client_instance.secrets.kv.v2.read_secret_version.return_value = mock_response

        # Set OpenBao path
        os.environ["TELEGRAM_BOT_TOKEN_PATH"] = "secret/ardenone-cluster/aide-de-camp/telegram_bot_token"
        os.environ["OPENBAO_TOKEN"] = "openbao_client_token"

        fallback = TelegramFallback()
        assert fallback.bot_token == "openbao_token_789"

    @patch('src.openbao.client.hvac.Client')
    def test_bot_token_openbao_failure_falls_back_to_none(self, mock_hvac_client_class, caplog):
        """Test that OpenBao retrieval failure results in no bot token."""
        # Clear any global OpenBao client that might have been created
        from src.openbao import client
        client._openbao_client = None

        mock_client_instance = MagicMock()
        mock_hvac_client_class.return_value = mock_client_instance
        mock_client_instance.secrets.kv.v2.read_secret_version.side_effect = Exception("OpenBao error")

        os.environ["TELEGRAM_BOT_TOKEN_PATH"] = "secret/invalid/path"
        os.environ["OPENBAO_TOKEN"] = "openbao_client_token"

        fallback = TelegramFallback()
        assert fallback.bot_token is None
        assert any("Failed to retrieve Telegram bot token" in record.message
                  for record in caplog.records)

    def test_bot_token_resolution_priority(self):
        """Test bot token resolution priority: constructor > env > path > None."""
        # Constructor arg should win
        os.environ["ADC_TELEGRAM_BOT_TOKEN"] = "env_token"
        os.environ["TELEGRAM_BOT_TOKEN_PATH"] = "secret/test/path"
        os.environ["OPENBAO_TOKEN"] = "openbao_token"
        fallback = TelegramFallback(bot_token="constructor_token")
        assert fallback.bot_token == "constructor_token"

        # Env var should win over path
        os.environ["ADC_TELEGRAM_BOT_TOKEN"] = "env_token_2"
        fallback2 = TelegramFallback()
        assert fallback2.bot_token == "env_token_2"

    def test_no_bot_token_when_no_config(self):
        """Test that bot_token is None when no configuration is provided."""
        fallback = TelegramFallback()
        assert fallback.bot_token is None
