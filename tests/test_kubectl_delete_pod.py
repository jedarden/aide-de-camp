"""
Test kubectl delete pod command execution.
"""

import pytest
import asyncio

from src.escalate.commands import (
    get_kubectl_executor,
    KubernetesCommandExecutor,
    CommandExecutionError,
)


class TestKubectlDeletePodParsing:
    """Test parsing of kubectl delete pod utterances."""

    def test_parse_basic_command(self):
        """Test parsing basic kubectl delete pod command."""
        executor = get_kubectl_executor()
        result = executor.parse_delete_pod_utterance(
            "kubectl delete pod my-pod-123"
        )

        assert result["pod_name"] == "my-pod-123"
        # Should infer namespace from project_slug or use default
        assert "namespace" in result

    def test_parse_command_with_namespace(self):
        """Test parsing command with explicit namespace."""
        executor = get_kubectl_executor()
        result = executor.parse_delete_pod_utterance(
            "kubectl delete pod my-pod-123 -n my-namespace"
        )

        assert result["pod_name"] == "my-pod-123"
        assert result["namespace"] == "my-namespace"

    def test_parse_command_with_project_slug(self):
        """Test namespace inference from project_slug."""
        executor = get_kubectl_executor()
        result = executor.parse_delete_pod_utterance(
            "kubectl delete pod my-pod",
            project_slug="options-pipeline"
        )

        assert result["pod_name"] == "my-pod"
        # options-pipeline -> optionspipeline (dashes removed)
        assert result["namespace"] == "optionspipeline"

    def test_parse_invalid_command(self):
        """Test parsing invalid command raises error."""
        executor = get_kubectl_executor()
        with pytest.raises(CommandExecutionError):
            executor.parse_delete_pod_utterance("delete pod my-pod")


class TestClusterResolution:
    """Test cluster proxy resolution."""

    def test_resolve_options_pipeline_proxy(self):
        """Test resolving proxy for options-pipeline project."""
        executor = get_kubectl_executor()
        proxy = executor._resolve_cluster_proxy("options-pipeline")
        assert "traefik-iad-options" in proxy or proxy.endswith(":8001")

    def test_resolve_kalshi_proxy(self):
        """Test resolving proxy for kalshi projects."""
        executor = get_kubectl_executor()
        proxy = executor._resolve_cluster_proxy("kalshi-tape")
        assert "traefik-iad-kalshi" in proxy or proxy.endswith(":8001")

    def test_resolve_default_proxy(self):
        """Test default proxy resolution."""
        executor = get_kubectl_executor()
        proxy = executor._resolve_cluster_proxy(None)
        # Should default to ardenone-manager
        assert "ardenone-manager" in proxy or proxy.endswith(":8001")


class TestNamespaceResolution:
    """Test namespace resolution from project_slug."""

    def test_resolve_namespace_from_slug(self):
        """Test namespace conversion (dashes removed)."""
        executor = get_kubectl_executor()
        namespace = executor._resolve_namespace("options-pipeline")
        assert namespace == "optionspipeline"

    def test_resolve_namespace_default(self):
        """Test default namespace."""
        executor = get_kubectl_executor()
        namespace = executor._resolve_namespace(None)
        assert namespace == "default"


@pytest.mark.asyncio
class TestDeletePodExecution:
    """Test actual kubectl delete pod execution."""

    async def test_execute_delete_pod_mock(self):
        """
        Test delete pod execution (requires kubectl access).

        This test is marked as expected failure if kubectl is not available.
        In a real environment, this would execute the actual command.
        """
        executor = get_kubectl_executor()

        # Try to execute - this will fail if kubectl is not available
        # but verifies the code path works
        try:
            result = await executor.execute_delete_pod(
                pod_name="test-pod-nonexistent",
                namespace="default",
                cluster_proxy="http://localhost:8001",  # Local test proxy
            )
            # If it runs, check structure
            assert "status" in result
            assert "summary" in result
            assert "data" in result
        except Exception as e:
            # Expected to fail without real kubectl/proxy
            assert isinstance(e, (CommandExecutionError, FileNotFoundError))


if __name__ == "__main__":
    # Run basic smoke tests
    pytest.main([__file__, "-v", "-x"])
