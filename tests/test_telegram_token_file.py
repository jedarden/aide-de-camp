"""Unit tests for the TELEGRAM_BOT_TOKEN_FILE runtime-delivery resolution.

The production path delivers the bot token as a mode-600 file under the
unit's runtime directory (deploy/fetch_runtime_secrets.sh, run as
ExecStartPre) and the server reads it at startup — so no agent or human ever
needs read access to the OpenBao path (the blocker shape that stalled the
credential-provisioning beads). These tests pin the resolution order, the
mode check, and the graceful degradation when the file is absent.
"""

import logging
import os
import stat

import pytest

from src.telegram.fallback import TelegramFallback


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate every env var the token resolution reads."""
    for var in (
        "ADC_TELEGRAM_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN_FILE",
        "TELEGRAM_BOT_TOKEN_PATH",
    ):
        monkeypatch.delenv(var, raising=False)


def write_token_file(tmp_path, token="file-token-123", mode=0o600):
    token_file = tmp_path / "telegram_bot_token"
    token_file.write_text(f"{token}\n")
    os.chmod(token_file, mode)
    return token_file


class TestTokenFileResolution:
    def test_token_loaded_from_runtime_file(self, tmp_path, monkeypatch):
        token_file = write_token_file(tmp_path)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN_FILE", str(token_file))

        fallback = TelegramFallback()

        assert fallback.bot_token == "file-token-123"

    def test_surrounding_whitespace_stripped(self, tmp_path, monkeypatch):
        token_file = tmp_path / "telegram_bot_token"
        token_file.write_text("  file-token-123\n\n")
        os.chmod(token_file, 0o600)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN_FILE", str(token_file))

        fallback = TelegramFallback()

        assert fallback.bot_token == "file-token-123"

    def test_env_direct_token_wins_over_file(self, tmp_path, monkeypatch):
        token_file = write_token_file(tmp_path)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN_FILE", str(token_file))
        monkeypatch.setenv("ADC_TELEGRAM_BOT_TOKEN", "env-token-456")

        fallback = TelegramFallback()

        assert fallback.bot_token == "env-token-456"

    def test_constructor_arg_wins_over_everything(self, tmp_path, monkeypatch):
        token_file = write_token_file(tmp_path)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN_FILE", str(token_file))
        monkeypatch.setenv("ADC_TELEGRAM_BOT_TOKEN", "env-token-456")

        fallback = TelegramFallback(bot_token="constructor-token-789")

        assert fallback.bot_token == "constructor-token-789"

    def test_missing_file_falls_through_to_openbao_path(
        self, tmp_path, monkeypatch
    ):
        """No file -> the OpenBao-path branch still resolves (hvac)."""
        monkeypatch.setenv(
            "TELEGRAM_BOT_TOKEN_FILE", str(tmp_path / "does-not-exist")
        )
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN_PATH", "secret/some/path")

        from src.openbao import OpenBaoClient

        monkeypatch.setattr(
            OpenBaoClient, "get_secret", lambda self, path, field="value": "hvac-token"
        )

        fallback = TelegramFallback()

        assert fallback.bot_token == "hvac-token"

    def test_missing_file_without_fallback_is_none(self, tmp_path, monkeypatch):
        """No file and no other source -> graceful no-op, not a crash."""
        monkeypatch.setenv(
            "TELEGRAM_BOT_TOKEN_FILE", str(tmp_path / "does-not-exist")
        )

        fallback = TelegramFallback()

        assert fallback.bot_token is None

    def test_empty_file_is_none(self, tmp_path, monkeypatch, caplog):
        token_file = tmp_path / "telegram_bot_token"
        token_file.write_text("")
        os.chmod(token_file, 0o600)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN_FILE", str(token_file))

        with caplog.at_level(logging.WARNING, logger="src.telegram.fallback"):
            fallback = TelegramFallback()

        assert fallback.bot_token is None
        assert "empty" in caplog.text

    def test_permissive_mode_warns_but_still_loads(
        self, tmp_path, monkeypatch, caplog
    ):
        """A delivery that lost its 600 mode must be loud — but a working
        token is not thrown away over it."""
        token_file = write_token_file(tmp_path, mode=0o644)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN_FILE", str(token_file))

        with caplog.at_level(logging.WARNING, logger="src.telegram.fallback"):
            fallback = TelegramFallback()

        assert fallback.bot_token == "file-token-123"
        assert "mode 644" in caplog.text

    def test_directory_as_file_degrades_to_none(self, tmp_path, monkeypatch, caplog):
        token_file = tmp_path / "telegram_bot_token"
        token_file.mkdir()
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN_FILE", str(token_file))

        with caplog.at_level(logging.WARNING, logger="src.telegram.fallback"):
            fallback = TelegramFallback()

        assert fallback.bot_token is None
        assert "unreadable" in caplog.text

    def test_delivered_file_is_mode_600_in_production(self):
        """Property check on the live delivery, when present: the unit's
        ExecStartPre promises mode 600. Skipped off-box / before first
        delivery — the deployment tests assert the contract end-to-end."""
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        token_file = os.path.join(runtime_dir, "aide-de-camp", "telegram_bot_token")
        if not os.path.exists(token_file):
            pytest.skip("no runtime delivery on this machine")
        mode = stat.S_IMODE(os.stat(token_file).st_mode)
        assert mode == 0o600
