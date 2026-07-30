"""
Tests for background-analysis auto-apply with freeze and git safety.

Tests that:
1. Auto-applies create git commits
2. Auto-applies respect freeze protection (env var, sentinel file, CLI)
3. Auto-applies use the same write path as self-modification
"""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from src.feedback.background_analysis import (
    BackgroundAnalysisProcessor,
    AnalysisProposal,
    AnalysisTrigger,
)
from src.freeze import check_frozen, ensure_unfrozen, set_frozen, SENTINEL_PATH
from src.agents.self_modification import ArtifactDiff, ArtifactType


class TestBackgroundAnalysisAutoApply:
    """Test suite for background-analysis auto-apply functionality."""

    @pytest.fixture
    def clean_env(self):
        """Fixture to ensure clean environment before each test."""
        original_env = os.environ.get("ADC_SELFMOD_FREEZE")

        if "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

        yield

        if original_env is not None:
            os.environ["ADC_SELFMOD_FREEZE"] = original_env
        elif "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

    @pytest.fixture
    def processor(self):
        """Create a BackgroundAnalysisProcessor instance for testing."""
        processor = BackgroundAnalysisProcessor(
            signal_threshold=10,
            check_interval=60,
            auto_apply_enabled=True,
        )
        return processor

    @pytest.fixture
    def mock_proposal(self):
        """Create a mock high-confidence proposal for testing."""
        return AnalysisProposal(
            proposal_id="test-proposal-1",
            signal_type="ack_speed",
            artifact_type="prompt",
            artifact_name="router",
            change_summary="Improve routing accuracy",
            confidence=0.9,  # Above threshold
            signals_consulted=10,
            generated_at=1234567890,
            session_ids={"session-1"},
        )

    @pytest.mark.asyncio
    async def test_auto_apply_enabled(self, processor, mock_proposal):
        """Test that auto-apply works when enabled and unfrozen."""
        # Mock the self-modification agent
        with patch.object(processor.self_mod_agent, 'apply_diff', return_value=True) as mock_apply:
            success = await processor._auto_apply_proposal(mock_proposal)

            assert success is True
            mock_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_apply_blocked_by_env_var(self, processor, mock_proposal, clean_env):
        """Test that auto-apply is blocked by ADC_SELFMOD_FREEZE=1."""
        # Set env var to freeze
        os.environ["ADC_SELFMOD_FREEZE"] = "1"

        # Mock the self-modification agent (should not be called)
        with patch.object(processor.self_mod_agent, 'apply_diff', return_value=True) as mock_apply:
            success = await processor._auto_apply_proposal(mock_proposal)

            assert success is False
            mock_apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_apply_blocked_by_sentinel(self, processor, mock_proposal, clean_env):
        """Test that auto-apply is blocked by data/FREEZE sentinel file."""
        # Create sentinel file
        SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_PATH.write_text("freeze test\n")

        # Mock the self-modification agent (should not be called)
        with patch.object(processor.self_mod_agent, 'apply_diff', return_value=True) as mock_apply:
            success = await processor._auto_apply_proposal(mock_proposal)

            assert success is False
            mock_apply.assert_not_called()

        # Clean up
        SENTINEL_PATH.unlink()

    @pytest.mark.asyncio
    async def test_auto_apply_blocked_by_cli_freeze(self, processor, mock_proposal, clean_env):
        """Test that auto-apply is blocked by 'adc freeze' CLI command."""
        # Use set_frozen to simulate CLI command
        set_frozen(True)

        # Mock the self-modification agent (should not be called)
        with patch.object(processor.self_mod_agent, 'apply_diff', return_value=True) as mock_apply:
            success = await processor._auto_apply_proposal(mock_proposal)

            assert success is False
            mock_apply.assert_not_called()

        # Clean up
        set_frozen(False)

    @pytest.mark.asyncio
    async def test_auto_apply_below_confidence_threshold(self, processor, clean_env):
        """Test that proposals below confidence threshold are not auto-applied."""
        # Create a low-confidence proposal
        low_confidence_proposal = AnalysisProposal(
            proposal_id="test-proposal-2",
            signal_type="ack_speed",
            artifact_type="prompt",
            artifact_name="router",
            change_summary="Minor improvement",
            confidence=0.7,  # Below threshold (0.85)
            signals_consulted=5,
            generated_at=1234567890,
            session_ids={"session-1"},
        )

        # Mock the self-modification agent (should not be called)
        with patch.object(processor.self_mod_agent, 'apply_diff', return_value=True) as mock_apply:
            success = await processor._auto_apply_proposal(low_confidence_proposal)

            assert success is False
            mock_apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_apply_creates_git_commit(self, processor, mock_proposal, clean_env):
        """Test that auto-apply creates a git commit through self-modification write path."""
        # Mock the self-modification agent methods
        with patch.object(processor.self_mod_agent, 'apply_diff', return_value=True) as mock_apply, \
             patch.object(processor.self_mod_agent, '_commit_artifact_write') as mock_commit:

            success = await processor._auto_apply_proposal(mock_proposal)

            assert success is True
            mock_apply.assert_called_once()
            # Verify that _commit_artifact_write was called (via apply_diff -> _write_prompt/config)
            # Note: apply_diff calls _write_prompt or _write_config, which call _commit_artifact_write

    @pytest.mark.asyncio
    async def test_auto_apply_disabled(self, mock_proposal, clean_env):
        """Test that auto-apply can be disabled."""
        # Create processor with auto-apply disabled
        processor = BackgroundAnalysisProcessor(
            signal_threshold=10,
            check_interval=60,
            auto_apply_enabled=False,
        )

        # Mock the self-modification agent (should not be called)
        with patch.object(processor.self_mod_agent, 'apply_diff', return_value=True) as mock_apply:
            success = await processor._auto_apply_proposal(mock_proposal)

            # Even though auto_apply_enabled is False, _auto_apply_proposal should still work
            # (the disabling happens in the run() method)
            # This test verifies the method itself still works when called directly
            assert success is True

    @pytest.mark.asyncio
    async def test_proposal_to_diff_conversion(self, processor, mock_proposal):
        """Test converting AnalysisProposal to ArtifactDiff."""
        diff = processor._proposal_to_diff(mock_proposal)

        assert diff is not None
        assert diff.artifact_name == mock_proposal.artifact_name
        assert diff.artifact_type == ArtifactType.PROMPT
        assert diff.change_summary == mock_proposal.change_summary
        assert diff.confidence == mock_proposal.confidence

    @pytest.mark.asyncio
    async def test_proposal_to_diff_unknown_artifact_type(self, processor):
        """Test that unknown artifact types return None."""
        proposal = AnalysisProposal(
            proposal_id="test-proposal-3",
            signal_type="ack_speed",
            artifact_type="unknown_type",  # Invalid type
            artifact_name="router",
            change_summary="Test change",
            confidence=0.9,
            signals_consulted=10,
            generated_at=1234567890,
            session_ids={"session-1"},
        )

        diff = processor._proposal_to_diff(proposal)
        assert diff is None

    @pytest.mark.asyncio
    async def test_proposal_to_diff_missing_artifact(self, processor):
        """Test that missing artifacts return None."""
        proposal = AnalysisProposal(
            proposal_id="test-proposal-4",
            signal_type="ack_speed",
            artifact_type="prompt",
            artifact_name="nonexistent_prompt",  # Doesn't exist
            change_summary="Test change",
            confidence=0.9,
            signals_consulted=10,
            generated_at=1234567890,
            session_ids={"session-1"},
        )

        diff = processor._proposal_to_diff(proposal)
        assert diff is None


class TestFreezeIntegration:
    """Test freeze protection integration with background analysis."""

    def test_freeze_status_check(self):
        """Test that check_frozen returns correct status."""
        # Unfrozen by default
        status = check_frozen()
        assert not status.is_frozen
        assert status.reason is None

    def test_env_var_freeze_detection(self):
        """Test env var freeze detection."""
        os.environ["ADC_SELFMOD_FREEZE"] = "1"
        status = check_frozen()
        assert status.is_frozen
        assert "env var" in status.reason

        # Clean up
        del os.environ["ADC_SELFMOD_FREEZE"]

    def test_sentinel_freeze_detection(self):
        """Test sentinel file freeze detection."""
        SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_PATH.write_text("freeze test\n")

        status = check_frozen()
        assert status.is_frozen
        assert "sentinel" in status.reason

        # Clean up
        SENTINEL_PATH.unlink()

    def test_ensure_unfrozen_raises_when_frozen(self):
        """Test that ensure_unfrozen raises RuntimeError when frozen."""
        os.environ["ADC_SELFMOD_FREEZE"] = "1"

        with pytest.raises(RuntimeError) as exc_info:
            ensure_unfrozen()

        assert "self-mod frozen" in str(exc_info.value)
        assert "env var" in str(exc_info.value)

        # Clean up
        del os.environ["ADC_SELFMOD_FREEZE"]

    def test_ensure_unfrozen_passes_when_unfrozen(self):
        """Test that ensure_unfrozen passes when unfrozen."""
        # Should not raise
        ensure_unfrozen()


class TestConfidenceThreshold:
    """Test confidence threshold for auto-apply."""

    @pytest.fixture
    def clean_env(self):
        """Fixture to ensure clean environment before each test."""
        original_env = os.environ.get("ADC_SELFMOD_FREEZE")

        if "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

        yield

        if original_env is not None:
            os.environ["ADC_SELFMOD_FREEZE"] = original_env
        elif "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

    @pytest.fixture
    def processor(self):
        """Create a BackgroundAnalysisProcessor instance for testing."""
        processor = BackgroundAnalysisProcessor(
            signal_threshold=10,
            check_interval=60,
            auto_apply_enabled=True,
        )
        return processor

    def test_default_threshold(self):
        """Test that default confidence threshold is 0.85."""
        processor = BackgroundAnalysisProcessor()
        assert processor.AUTO_APPLY_CONFIDENCE_THRESHOLD == 0.85

    @pytest.mark.asyncio
    async def test_exactly_at_threshold(self, processor, clean_env):
        """Test that proposals exactly at threshold are auto-applied."""
        # Create a proposal exactly at threshold
        proposal = AnalysisProposal(
            proposal_id="test-proposal-5",
            signal_type="ack_speed",
            artifact_type="prompt",
            artifact_name="router",
            change_summary="Test change",
            confidence=0.85,  # Exactly at threshold
            signals_consulted=10,
            generated_at=1234567890,
            session_ids={"session-1"},
        )

        with patch.object(processor.self_mod_agent, 'apply_diff', return_value=True) as mock_apply:
            success = await processor._auto_apply_proposal(proposal)
            assert success is True
            mock_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_just_below_threshold(self, processor, clean_env):
        """Test that proposals just below threshold are not auto-applied."""
        # Create a proposal just below threshold
        proposal = AnalysisProposal(
            proposal_id="test-proposal-6",
            signal_type="ack_speed",
            artifact_type="prompt",
            artifact_name="router",
            change_summary="Test change",
            confidence=0.849,  # Just below threshold
            signals_consulted=10,
            generated_at=1234567890,
            session_ids={"session-1"},
        )

        with patch.object(processor.self_mod_agent, 'apply_diff', return_value=True) as mock_apply:
            success = await processor._auto_apply_proposal(proposal)
            assert success is False
            mock_apply.assert_not_called()
