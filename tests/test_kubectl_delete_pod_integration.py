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
                skip_warning=False,
            )

    async def test_full_delete_pod_flow_production(self):
        """
        Test that production deletions require approval before bead creation.

        The handler must hold the request and show an approval card.
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

        # Production deletion must enter the approval path before bead creation.
        from unittest.mock import AsyncMock, MagicMock, patch

        handler.store = AsyncMock()
        handler.store.create_pending_approval.return_value = "approval-test-123"
        handler.formulate_bead_body = AsyncMock(return_value="# Delete pod request")

        validation_result = MagicMock()
        validation_result.is_valid = True
        validation_result.requires_approval = True
        validation_result.approval_requirement.reason = "Production deletion requires approval"
        validation_result.to_dict.return_value = {
            "approval_requirement": {"reason": "Production deletion requires approval"}
        }

        with (
            patch("src.escalate.handler.get_validator") as mock_validator,
            patch("src.escalate.handler.get_broadcaster") as mock_broadcaster,
            patch.object(handler, "_create_bead_with_type", new_callable=AsyncMock) as create_bead,
        ):
            mock_validator.return_value.validate_bead_body.return_value = validation_result
            mock_broadcaster.return_value.broadcast = AsyncMock()

            result = await handler.escalate_intent(request)

        assert result.status == "awaiting_approval"
        assert result.bead_id == ""
        assert result.pending_card["status"] == "awaiting_approval"
        assert result.pending_card["approval_id"] == "approval-test-123"
        create_bead.assert_not_awaited()
        handler.store.create_pending_approval.assert_awaited_once()
        mock_broadcaster.return_value.broadcast.assert_awaited_once()



if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
