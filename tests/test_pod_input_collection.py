"""
Test pod name input collection and validation.

Tests the interactive pod input collector functionality for validating
user input against available pod lists.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.escalate.pod_input import (
    PodInputCollector,
    get_pod_input_collector,
    collect_pod_name_interactive,
)


class TestPodInputCollector:
    """Test pod input collector basic functionality."""

    def test_collector_initialization(self):
        """Test collector initializes with empty state."""
        collector = PodInputCollector()

        assert collector.get_selected_pod() is None
        assert collector.get_available_pod_names() == []

    def test_set_available_pods(self):
        """Test setting available pods list."""
        collector = PodInputCollector()
        pods = [
            {"name": "pod-1", "namespace": "default", "status": "Running"},
            {"name": "pod-2", "namespace": "default", "status": "Running"},
        ]

        collector.set_available_pods(pods)

        assert collector.get_available_pod_names() == ["pod-1", "pod-2"]

    def test_set_available_pods_filters_invalid(self):
        """Test that pods without names are filtered out."""
        collector = PodInputCollector()
        pods = [
            {"name": "pod-1", "namespace": "default"},
            {"namespace": "default"},  # No name
            {"name": "", "namespace": "default"},  # Empty name
            {"name": "pod-2", "namespace": "default"},
        ]

        collector.set_available_pods(pods)

        assert collector.get_available_pod_names() == ["pod-1", "pod-2"]


class TestPodNameValidation:
    """Test pod name validation logic."""

    @pytest.fixture
    def collector(self):
        """Create collector with sample pods."""
        collector = PodInputCollector()
        collector.set_available_pods([
            {"name": "pod-1", "namespace": "default"},
            {"name": "pod-2", "namespace": "default"},
            {"name": "pod-3", "namespace": "default"},
        ])
        return collector

    def test_validate_valid_pod_name(self, collector):
        """Test validation of valid pod name."""
        is_valid, error_msg = collector.validate_pod_name("pod-1")

        assert is_valid is True
        assert error_msg is None

    def test_validate_invalid_pod_name(self, collector):
        """Test validation of invalid pod name."""
        is_valid, error_msg = collector.validate_pod_name("nonexistent-pod")

        assert is_valid is False
        assert "not found in available pods" in error_msg
        assert "nonexistent-pod" in error_msg

    def test_validate_empty_pod_name(self, collector):
        """Test validation rejects empty pod name."""
        is_valid, error_msg = collector.validate_pod_name("")

        assert is_valid is False
        assert "cannot be empty" in error_msg

    def test_validate_whitespace_pod_name(self, collector):
        """Test validation rejects whitespace-only pod name."""
        is_valid, error_msg = collector.validate_pod_name("   ")

        assert is_valid is False
        assert "cannot be empty" in error_msg

    def test_validate_case_sensitive(self, collector):
        """Test validation is case-sensitive."""
        is_valid, _ = collector.validate_pod_name("POD-1")
        assert is_valid is False

        is_valid, _ = collector.validate_pod_name("Pod-1")
        assert is_valid is False


class TestInteractiveCollection:
    """Test interactive pod name collection."""

    @pytest.fixture
    def sample_pods(self):
        """Sample pod list for testing."""
        return [
            {
                "name": "pbx-web-5ff68464d-mkn8n",
                "namespace": "default",
                "status": "Running",
                "ready": "2/2",
                "age": "8d",
            },
            {
                "name": "pbx-rebuild-relay-588d79c5b9-vmmlz",
                "namespace": "default",
                "status": "Running",
                "ready": "1/1",
                "age": "22d",
            },
            {
                "name": "whisper-stt-847fd8d7b9-v2rs5",
                "namespace": "default",
                "status": "Running",
                "ready": "1/1",
                "age": "24d",
            },
        ]

    def test_collect_valid_pod_name(self, sample_pods):
        """Test collecting a valid pod name from user."""
        collector = PodInputCollector()
        collector.set_available_pods(sample_pods)

        with patch('builtins.input', return_value='pbx-web-5ff68464d-mkn8n'):
            result = collector.collect_pod_name()

        assert result == "pbx-web-5ff68464d-mkn8n"
        assert collector.get_selected_pod() == "pbx-web-5ff68464d-mkn8n"

    def test_collect_invalid_then_valid_pod_name(self, sample_pods):
        """Test collection with invalid input first, then valid."""
        collector = PodInputCollector()
        collector.set_available_pods(sample_pods)

        with patch('builtins.input', side_effect=['invalid-pod', 'pbx-web-5ff68464d-mkn8n']):
            result = collector.collect_pod_name()

        assert result == "pbx-web-5ff68464d-mkn8n"

    def test_collect_cancels_with_empty_input(self, sample_pods):
        """Test cancellation with empty input."""
        collector = PodInputCollector()
        collector.set_available_pods(sample_pods)

        with patch('builtins.input', return_value=''):
            result = collector.collect_pod_name()

        assert result is None
        assert collector.get_selected_pod() is None

    def test_collect_cancels_with_cancel_keyword(self, sample_pods):
        """Test cancellation with 'cancel' keyword."""
        collector = PodInputCollector()
        collector.set_available_pods(sample_pods)

        with patch('builtins.input', return_value='cancel'):
            result = collector.collect_pod_name()

        assert result is None

    def test_collect_handles_keyboard_interrupt(self, sample_pods):
        """Test handling of keyboard interrupt (Ctrl+C)."""
        collector = PodInputCollector()
        collector.set_available_pods(sample_pods)

        with patch('builtins.input', side_effect=KeyboardInterrupt):
            result = collector.collect_pod_name()

        assert result is None

    def test_collect_handles_eof(self, sample_pods):
        """Test handling of EOF (Ctrl+D)."""
        collector = PodInputCollector()
        collector.set_available_pods(sample_pods)

        with patch('builtins.input', side_effect=EOFError):
            result = collector.collect_pod_name()

        assert result is None

    def test_collect_with_no_available_pods(self):
        """Test collection fails when no pods available."""
        collector = PodInputCollector()
        # No pods set

        with patch('builtins.input', return_value='any-pod'):
            result = collector.collect_pod_name()

        assert result is None

    def test_collect_with_custom_prompt(self, sample_pods):
        """Test collection with custom prompt message."""
        collector = PodInputCollector()
        collector.set_available_pods(sample_pods)

        custom_prompt = "Custom prompt for testing"

        with patch('builtins.input', return_value='pbx-web-5ff68464d-mkn8n'):
            result = collector.collect_pod_name(prompt_message=custom_prompt)

        assert result == "pbx-web-5ff68464d-mkn8n"


class TestCollectorReset:
    """Test collector reset functionality."""

    def test_reset_clears_state(self):
        """Test that reset clears all state."""
        collector = PodInputCollector()
        collector.set_available_pods([{"name": "pod-1"}])

        # Simulate selection
        with patch('builtins.input', return_value='pod-1'):
            collector.collect_pod_name()

        assert collector.get_selected_pod() == "pod-1"

        # Reset
        collector.reset()

        assert collector.get_selected_pod() is None
        assert collector.get_available_pod_names() == []


class TestGlobalCollector:
    """Test global collector instance."""

    def test_get_pod_input_collector_singleton(self):
        """Test that global collector is a singleton."""
        collector1 = get_pod_input_collector()
        collector2 = get_pod_input_collector()

        assert collector1 is collector2


class TestConvenienceFunction:
    """Test convenience function for pod collection."""

    def test_collect_pod_name_interactive(self):
        """Test convenience function for collection."""
        sample_pods = [
            {"name": "test-pod", "namespace": "default", "status": "Running"},
        ]

        with patch('builtins.input', return_value='test-pod'):
            result = collect_pod_name_interactive(sample_pods)

        assert result == "test-pod"


class TestPromptBuilding:
    """Test default prompt message building."""

    def test_build_default_prompt_with_namespace_grouping(self):
        """Test prompt groups pods by namespace."""
        collector = PodInputCollector()
        collector.set_available_pods([
            {"name": "pod-1", "namespace": "default", "status": "Running", "ready": "1/1", "age": "1d"},
            {"name": "pod-2", "namespace": "default", "status": "Running", "ready": "1/1", "age": "2d"},
            {"name": "pod-3", "namespace": "kube-system", "status": "Running", "ready": "1/1", "age": "3d"},
        ])

        prompt = collector._build_default_prompt()

        assert "Namespace: default" in prompt
        assert "Namespace: kube-system" in prompt
        assert "pod-1" in prompt
        assert "pod-2" in prompt
        assert "pod-3" in prompt
        assert "Which pod would you like to delete?" in prompt

    def test_build_default_prompt_shows_pod_metadata(self):
        """Test prompt includes pod metadata."""
        collector = PodInputCollector()
        collector.set_available_pods([
            {
                "name": "test-pod",
                "namespace": "default",
                "status": "Running",
                "ready": "2/2",
                "age": "5d",
            },
        ])

        prompt = collector._build_default_prompt()

        assert "test-pod" in prompt
        assert "Running" in prompt
        assert "2/2" in prompt
        assert "5d" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
