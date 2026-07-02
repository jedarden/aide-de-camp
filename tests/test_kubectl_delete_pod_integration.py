"""
Integration test demonstrating kubectl delete pod functionality.
"""

import pytest
import asyncio

from src.escalate.commands import get_kubectl_executor
from src.escalate.handler import EscalateHandler, EscalateRequest


@pytest.mark.asyncio
class TestDeletePodIntegration:
    """End-to-end integration tests for kubectl delete pod."""

    async def test_full_delete_pod_flow_staging(self):
        """
        Test full flow: utterance → escalate → auto-approve → execute.

        This demonstrates the complete end-to-end flow for kubectl delete pod
        in a staging environment where it's auto-approved.
        """
        # Create escalate handler
        handler = EscalateHandler()

        # Create request with staging environment
        request = EscalateRequest(
            intent_id="test-integration-1",
            session_id="session-test",
            utterance="kubectl delete pod crashed-pod-123",
            intent_type="action",
            project_slug="options-pipeline",
            metadata={
                "action": "kubectl_delete_pod",
                "environment": "staging",
            },
        )

        # Mock the reload manager with staging config
        from unittest.mock import MagicMock
        handler._reload_manager = MagicMock()
        handler._reload_manager.get_config.side_effect = lambda name: {
            "auto_approve": {
                "read_only": [],
                "safe_mutations": [
                    {
                        "condition": "environment == 'staging'",
                        "actions": ["kubectl_delete_pod"],
                    }
                ],
            },
            "manual_approval": [],
            "escalation_targets": {
                "action": {"bead_type": "action"},
            },
            "approval": {
                "never_auto_approve": [],
            },
        } if name == "exceptions" else {}

        # Mock store
        from unittest.mock import AsyncMock
        handler.store = AsyncMock()
        handler.store.update_intent_status = AsyncMock(return_value=None)

        # Mock the kubectl executor to avoid actual kubectl call
        from unittest.mock import AsyncMock, Mock, patch

        mock_result = {
            "status": "completed",
            "summary": "Deleted pod 'crashed-pod-123' from namespace 'optionspipeline'",
            "data": {
                "action": "kubectl_delete_pod",
                "pod_name": "crashed-pod-123",
                "namespace": "optionspipeline",
                "cluster_proxy": "http://traefik-iad-options:8001",
            },
            "urgency": "low",
        }

        with patch('src.escalate.handler.get_kubectl_executor') as mock_executor:
            mock_kubectl = Mock()
            mock_kubectl.parse_delete_pod_utterance.return_value = {
                "pod_name": "crashed-pod-123",
                "namespace": "optionspipeline",
            }
            mock_kubectl.execute_delete_pod = AsyncMock(return_value=mock_result)
            mock_executor.return_value = mock_kubectl

            # Execute the escalate
            result = await handler.escalate_intent(request)

            # Verify auto-approval (no bead created)
            assert result.status == "completed"
            assert result.bead_id == ""
            assert result.pending_card["status"] == "completed"
            assert "Deleted pod" in result.pending_card["summary"]

            # Verify kubectl executor was called correctly
            mock_kubectl.parse_delete_pod_utterance.assert_called_once()
            mock_kubectl.execute_delete_pod.assert_called_once_with(
                pod_name="crashed-pod-123",
                namespace="optionspipeline",
                project_slug="options-pipeline",
            )

    async def test_full_delete_pod_flow_production(self):
        """
        Test that production deletions are NOT auto-approved.

        In production, kubectl delete pod should require manual approval
        and create a bead instead of executing directly.
        """
        # Create escalate handler
        handler = EscalateHandler()

        # Create request with production environment
        request = EscalateRequest(
            intent_id="test-integration-2",
            session_id="session-test",
            utterance="kubectl delete pod prod-pod-456",
            intent_type="action",
            project_slug="options-pipeline",
            metadata={
                "action": "kubectl_delete_pod",
                "environment": "production",
            },
        )

        # Mock the reload manager with production config
        from unittest.mock import MagicMock
        handler._reload_manager = MagicMock()
        handler._reload_manager.get_config.side_effect = lambda name: {
            "auto_approve": {
                "read_only": [],
                "safe_mutations": [
                    {
                        "condition": "environment == 'staging'",
                        "actions": ["kubectl_delete_pod"],
                    }
                ],
            },
            "manual_approval": [
                {
                    "condition": "environment == 'production'",
                    "actions": ["kubectl_delete"],
                    "always_approve": False,
                }
            ],
            "escalation_targets": {
                "action": {"bead_type": "action"},
            },
            "approval": {
                "never_auto_approve": [],
            },
        } if name == "exceptions" else {}

        # Mock store
        from unittest.mock import AsyncMock
        handler.store = AsyncMock()
        handler.store.update_intent_status = AsyncMock(return_value=None)

        # Mock LLM bead formulation (would normally call ZAI)
        from unittest.mock import AsyncMock
        handler._zai_client = MagicMock()
        handler._zai_client.call_simple = AsyncMock(return_value="# Bead body for kubectl delete")

        # Mock br CLI (would normally create bead)
        from unittest.mock import patch
        with patch('asyncio.create_subprocess_exec') as mock_subprocess:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"adc-xyz123\n", b""))
            mock_subprocess.return_value = mock_proc

            # Execute the escalate
            result = await handler.escalate_intent(request)

            # Verify manual approval (bead created)
            assert result.status == "created"
            assert result.bead_id != ""
            assert result.pending_card["status"] == "pending"
            assert "bead_id" in result.pending_card


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
