"""
Tests for self-modification freeze mechanism.

Tests the three-layer freeze protection:
1. Environment variable ADC_SELFMOD_FREEZE=1
2. Sentinel file data/FREEZE
3. CLI command 'adc freeze'
"""

import os
import pytest
from pathlib import Path

from src.freeze import check_frozen, ensure_unfrozen, set_frozen, get_status


class TestFreezeMechanism:
    """Test suite for freeze protection."""

    @pytest.fixture
    def clean_env(self):
        """Fixture to ensure clean environment before each test."""
        # Save original env var state
        original_env = os.environ.get("ADC_SELFMOD_FREEZE")

        # Clear env var
        if "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        # Ensure sentinel file doesn't exist
        from src.freeze import SENTINEL_PATH
        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

        yield

        # Restore original state
        if original_env is not None:
            os.environ["ADC_SELFMOD_FREEZE"] = original_env
        elif "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        # Clean up sentinel file
        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

    def test_unfrozen_by_default(self, clean_env):
        """Test that self-modification is unfrozen by default."""
        status = check_frozen()
        assert not status.is_frozen
        assert status.reason is None

    def test_env_var_freeze(self, clean_env):
        """Test that ADC_SELFMOD_FREEZE=1 freezes writes."""
        # Set env var
        os.environ["ADC_SELFMOD_FREEZE"] = "1"

        status = check_frozen()
        assert status.is_frozen
        assert "env var" in status.reason
        assert "ADC_SELFMOD_FREEZE=1" in status.reason

        # Test ensure_unfrozen raises error
        with pytest.raises(RuntimeError) as exc_info:
            ensure_unfrozen()

        assert "self-mod frozen" in str(exc_info.value)
        assert "env var" in str(exc_info.value)

    def test_sentinel_file_freeze(self, clean_env):
        """Test that data/FREEZE file freezes writes."""
        # Create sentinel file
        from src.freeze import SENTINEL_PATH
        SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_PATH.write_text("freeze test\n")

        status = check_frozen()
        assert status.is_frozen
        assert "sentinel file" in status.reason

        # Test ensure_unfrozen raises error
        with pytest.raises(RuntimeError) as exc_info:
            ensure_unfrozen()

        assert "self-mod frozen" in str(exc_info.value)
        assert "sentinel" in str(exc_info.value)

        # Clean up
        SENTINEL_PATH.unlink()

    def test_set_frozen_true(self, clean_env):
        """Test set_frozen(True) creates sentinel file."""
        from src.freeze import SENTINEL_PATH

        # Ensure sentinel doesn't exist
        assert not SENTINEL_PATH.exists()

        # Set frozen
        set_frozen(True)

        # Verify sentinel created
        assert SENTINEL_PATH.exists()
        status = check_frozen()
        assert status.is_frozen

        # Clean up
        SENTINEL_PATH.unlink()

    def test_set_frozen_false(self, clean_env):
        """Test set_frozen(False) removes sentinel file."""
        from src.freeze import SENTINEL_PATH

        # Create sentinel first
        SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_PATH.write_text("freeze test\n")
        assert SENTINEL_PATH.exists()

        # Unfreeze
        set_frozen(False)

        # Verify sentinel removed
        assert not SENTINEL_PATH.exists()
        status = check_frozen()
        assert not status.is_frozen

    def test_get_status_unfrozen(self, clean_env):
        """Test get_status() returns correct dict when unfrozen."""
        status = get_status()
        assert status == {"frozen": False, "reason": None}

    def test_get_status_frozen_env_var(self, clean_env):
        """Test get_status() returns correct dict when frozen via env var."""
        os.environ["ADC_SELFMOD_FREEZE"] = "1"

        status = get_status()
        assert status["frozen"] is True
        assert "env var" in status["reason"]

    def test_get_status_frozen_sentinel(self, clean_env):
        """Test get_status() returns correct dict when frozen via sentinel."""
        from src.freeze import SENTINEL_PATH

        SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_PATH.write_text("freeze test\n")

        status = get_status()
        assert status["frozen"] is True
        assert "sentinel file" in status["reason"]

        # Clean up
        SENTINEL_PATH.unlink()


class TestFreezeCLI:
    """Test CLI freeze command integration."""

    def test_freeze_command_toggle(self):
        """Test 'adc freeze --toggle' creates and removes sentinel."""
        from src.cli.commands import freeze_cmd
        from src.freeze import SENTINEL_PATH

        # Ensure clean state
        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

        # Toggle on
        exit_code = freeze_cmd(toggle=True)
        assert exit_code == 0
        assert SENTINEL_PATH.exists()

        # Toggle off
        exit_code = freeze_cmd(toggle=True)
        assert exit_code == 0
        assert not SENTINEL_PATH.exists()

    def test_freeze_command_status_unfrozen(self):
        """Test 'adc freeze' shows unfrozen status."""
        from src.cli.commands import freeze_cmd
        from src.freeze import SENTINEL_PATH

        # Ensure clean state
        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()
        if "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        # Get status (toggle=False)
        exit_code = freeze_cmd(toggle=False)
        assert exit_code == 0


class TestFreezeSelfModIntegration:
    """Test freeze protection in self-modification agent."""

    @pytest.fixture
    def clean_env(self):
        """Fixture to ensure clean environment before each test."""
        original_env = os.environ.get("ADC_SELFMOD_FREEZE")

        if "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        from src.freeze import SENTINEL_PATH
        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

        yield

        if original_env is not None:
            os.environ["ADC_SELFMOD_FREEZE"] = original_env
        elif "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

    def test_apply_diff_blocked_by_env_var(self, clean_env, capsys):
        """Test apply_diff blocked by env var with clear error message."""
        from src.agents.self_modification import SelfModificationAgent, ArtifactDiff, ArtifactType

        # Set env var to freeze
        os.environ["ADC_SELFMOD_FREEZE"] = "1"

        agent = SelfModificationAgent()
        diff = ArtifactDiff(
            artifact_name="test",
            artifact_type=ArtifactType.PROMPT,
            before="old",
            after="new",
            change_summary="test change",
            confidence=0.8
        )

        # Try to apply - should fail with clear error
        result = agent.apply_diff(diff)
        assert result is False

        captured = capsys.readouterr()
        assert "self-mod frozen" in captured.out
        assert "env var" in captured.out

    def test_apply_diff_blocked_by_sentinel(self, clean_env, capsys):
        """Test apply_diff blocked by sentinel file with clear error message."""
        from src.agents.self_modification import SelfModificationAgent, ArtifactDiff, ArtifactType
        from src.freeze import SENTINEL_PATH

        # Create sentinel file
        SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_PATH.write_text("freeze test\n")

        agent = SelfModificationAgent()
        diff = ArtifactDiff(
            artifact_name="test",
            artifact_type=ArtifactType.PROMPT,
            before="old",
            after="new",
            change_summary="test change",
            confidence=0.8
        )

        # Try to apply - should fail with clear error
        result = agent.apply_diff(diff)
        assert result is False

        captured = capsys.readouterr()
        assert "self-mod frozen" in captured.out
        assert "sentinel" in captured.out

        # Clean up
        SENTINEL_PATH.unlink()
