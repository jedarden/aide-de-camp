#!/usr/bin/env python3
"""
Integration tests for fetch and synthesis strands (bead adc-1mzt).

Tests the complete pipeline from utterance → fetch → synthesis with various
fetch source types to verify the strands execute correctly and produce
structured results.

This complements the unit tests in test_fetch_strand.py and
test_synthesize_strand.py by providing end-to-end verification of the
full pipeline with realistic scenarios.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.fetch.commands import (
    FetchContext,
    FetchCoverage,
    FetchRequest,
    FetchResult,
    FetchSource,
    IntentType,
    SourceResult,
)
from src.fetch.orchestrator import FetchOrchestrator, FetchStrand
from src.synthesize.strand import (
    SynthesizeRequest,
    SynthesizeResult,
    SynthesizeStrand,
    Urgency,
)


# ============================================================================
# Test fixtures and helpers
# ============================================================================


def _mock_kubernetes_response(component_type: str, namespace: str) -> dict:
    """Mock a successful Kubernetes API response."""
    if component_type == "pods":
        return {
            "namespace": namespace,
            "pods": [
                {"name": "web-0", "phase": "Running", "ready": "1/1", "restarts": 0},
                {"name": "web-1", "phase": "Running", "ready": "1/1", "restarts": 0},
                {"name": "db-0", "phase": "Running", "ready": "1/1", "restarts": 1},
            ],
            "pod_count": 3,
            "healthy_count": 3,
        }
    elif component_type == "deployments":
        return {
            "name": "web-app",
            "namespace": namespace,
            "replicas": 3,
            "ready_replicas": 3,
            "available_replicas": 3,
            "updated_replicas": 3,
            "conditions": [],
        }
    return {}


def _mock_git_response(response_type: str) -> dict:
    """Mock a successful Git response."""
    if response_type == "log":
        return {
            "repo": "/home/coding/test-project",
            "branch": "main",
            "commits": [
                {"hash": "abc123", "message": "Fix authentication bug", "author": "John Doe", "date": "2 hours ago"},
                {"hash": "def456", "message": "Add new feature", "author": "Jane Smith", "date": "1 day ago"},
            ],
            "count": 2,
        }
    elif response_type == "status":
        return {
            "repo": "/home/coding/test-project",
            "branch": "main",
            "last_commit": "abc123 Fix authentication bug",
            "changed_files": [
                {"status": " M", "file": "src/auth.py"},
                {"status": "M ", "file": "docs/README.md"},
            ],
            "count": 2,
            "has_changes": True,
        }
    return {}


def _mock_argocd_response(app_name: str) -> dict:
    """Mock a successful ArgoCD response."""
    return {
        "name": app_name,
        "sync_status": "Synced",
        "health_status": "Healthy",
        "revision": "abc123",
        "operation": {},
        "created_at": "2024-01-15T10:30:00Z",
    }


def _mock_bead_list_response(project: str) -> dict:
    """Mock a successful bead list response."""
    return {
        "project": project,
        "repo": "/home/coding/test-project",
        "beads": [
            {
                "id": "adc-1mzt",
                "title": "Verify fetch and synthesis strands execute",
                "status": "in-progress",
                "type": "task",
            },
            {
                "id": "adc-5qdx",
                "title": "Add comprehensive intent classification tests",
                "status": "closed",
                "type": "task",
            },
        ],
        "count": 2,
        "scope": "project_workspace",
    }


def _mock_llm_synthesis_response(
    data_type: str = "pod-status",
    urgency: str = "normal"
) -> str:
    """Mock a successful LLM synthesis response."""
    response_data = {
        "data": {
            "type": data_type,
            "items": [],
            "summary_fields": {"total": 0, "healthy": 0, "unhealthy": 0},
        },
        "summary": f"All {data_type} components are operating normally.",
        "urgency": urgency,
    }
    return json.dumps(response_data)


def create_mock_executor(response_data: dict) -> Callable:
    """Create a mock executor that returns the given data."""
    async def executor(ctx: FetchContext) -> dict:
        return response_data
    return executor


def create_mock_fetch_strand(source_responses: dict[FetchSource, dict]) -> FetchStrand:
    """Create a FetchStrand with mocked executors for specified sources."""
    strand = FetchStrand()

    # Replace executors with mocks
    for source, data in source_responses.items():
        strand._source_executors[source] = create_mock_executor(data)

    # Mock remaining sources to return empty success
    async def default_executor(ctx: FetchContext) -> dict:
        return {"mock": True}

    for source in FetchSource:
        if source not in source_responses:
            strand._source_executors[source] = default_executor

    return strand


def create_mock_synthesize_strand(raw_response: str) -> SynthesizeStrand:
    """Create a SynthesizeStrand with mocked LLM client."""
    strand = SynthesizeStrand()

    # Mock the ZAI client
    client = MagicMock()
    client.call_simple = AsyncMock(return_value=raw_response)
    strand._zai_client = client

    # Mock reload manager to avoid file system access
    strand._reload_manager = MagicMock()
    strand._reload_manager.get_prompt.return_value = ""

    return strand


# ============================================================================
# Test: Kubernetes fetch sources
# ============================================================================


class TestKubernetesFetchSources:
    """Test fetch execution for Kubernetes-based source types."""

    @pytest.mark.asyncio
    async def test_kubernetes_pods_fetch_and_synthesis(self):
        """Test complete pipeline for Kubernetes pods fetch + synthesis."""
        # Setup: Create mock fetch strand with Kubernetes pod response
        source_responses = {
            FetchSource.KUBECTL_PODS: _mock_kubernetes_response("pods", "production"),
        }
        fetch_strand = create_mock_fetch_strand(source_responses)
        orchestrator = FetchOrchestrator(fetch_strand)

        # Execute fetch
        request = FetchRequest(
            intent_type=IntentType.STATUS,
            context=FetchContext(
                project_slug="test-project",
                namespace="production",
                proxy="http://kubectl-proxy:8001",
            ),
            intent_id="test-intent-001",
            session_id="test-session",
        )

        fetch_result = await orchestrator.execute_fetch(request)

        # Verify fetch result
        assert fetch_result.intent_id == "test-intent-001"
        assert FetchSource.KUBECTL_PODS in fetch_result.sources
        assert fetch_result.sources[FetchSource.KUBECTL_PODS].status == "success"
        assert fetch_result.sources[FetchSource.KUBECTL_PODS].data["pod_count"] == 3
        assert fetch_result.coverage.success_rate > 0

        # Execute synthesis
        synthesize_strand = create_mock_synthesize_strand(
            _mock_llm_synthesis_response("pod-status", "normal")
        )
        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-001",
            intent_type=IntentType.STATUS,
            utterance="how are the pods doing?",
            project_slug="test-project",
            fetched_context=fetch_result,
            urgency="normal",
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis result
        assert isinstance(synthesize_result, SynthesizeResult)
        assert isinstance(synthesize_result.data, dict)
        assert synthesize_result.data["type"] == "pod-status"
        assert isinstance(synthesize_result.summary, str)
        assert len(synthesize_result.summary) > 0
        assert synthesize_result.urgency == Urgency.NORMAL
        assert synthesize_result.intent_id == "test-intent-001"

    @pytest.mark.asyncio
    async def test_kubernetes_deployments_fetch_and_synthesis(self):
        """Test complete pipeline for Kubernetes deployments fetch + synthesis."""
        source_responses = {
            FetchSource.KUBECTL_DEPLOYMENTS: _mock_kubernetes_response("deployments", "staging"),
        }
        fetch_strand = create_mock_fetch_strand(source_responses)
        orchestrator = FetchOrchestrator(fetch_strand)

        request = FetchRequest(
            intent_type=IntentType.ACTION,
            context=FetchContext(
                project_slug="web-app",
                namespace="staging",
                deployment="web-app",
                proxy="http://kubectl-proxy:8001",
            ),
            intent_id="test-intert-002",
            session_id="test-session",
        )

        fetch_result = await orchestrator.execute_fetch(request)

        # Verify fetch
        assert FetchSource.KUBECTL_DEPLOYMENTS in fetch_result.sources
        assert fetch_result.sources[FetchSource.KUBECTL_DEPLOYMENTS].status == "success"
        assert fetch_result.sources[FetchSource.KUBECTL_DEPLOYMENTS].data["name"] == "web-app"
        assert fetch_result.sources[FetchSource.KUBECTL_DEPLOYMENTS].data["ready_replicas"] == 3

        # Execute synthesis
        synthesize_strand = create_mock_synthesize_strand(
            _mock_llm_synthesis_response("deployment-status", "high")
        )
        synthesize_request = SynthesizeRequest(
            intent_id="test-intert-002",
            intent_type=IntentType.ACTION,
            utterance="check the deployment status",
            project_slug="web-app",
            fetched_context=fetch_result,
            urgency="high",
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis
        assert synthesize_result.urgency == Urgency.HIGH
        assert synthesize_result.data["type"] == "deployment-status"


# ============================================================================
# Test: Git fetch sources
# ============================================================================


class TestGitFetchSources:
    """Test fetch execution for Git-based source types."""

    @pytest.mark.asyncio
    async def test_git_log_fetch_and_synthesis(self):
        """Test complete pipeline for git log fetch + synthesis."""
        source_responses = {
            FetchSource.GIT_LOG: _mock_git_response("log"),
        }
        fetch_strand = create_mock_fetch_strand(source_responses)
        orchestrator = FetchOrchestrator(fetch_strand)

        request = FetchRequest(
            intent_type=IntentType.STATUS,  # STATUS includes GIT_LOG
            context=FetchContext(
                project_slug="test-project",
                repo_path="/home/coding/test-project",
            ),
            intent_id="test-intent-003",
            session_id="test-session",
        )

        fetch_result = await orchestrator.execute_fetch(request)

        # Verify fetch
        assert FetchSource.GIT_LOG in fetch_result.sources
        assert fetch_result.sources[FetchSource.GIT_LOG].status == "success"
        assert fetch_result.sources[FetchSource.GIT_LOG].data["count"] == 2
        commits = fetch_result.sources[FetchSource.GIT_LOG].data["commits"]
        assert len(commits) == 2
        assert commits[0]["message"] == "Fix authentication bug"

        # Execute synthesis
        synthesize_strand = create_mock_synthesize_strand(
            _mock_llm_synthesis_response("git-log", "normal")
        )
        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-003",
            intent_type=IntentType.STATUS,
            utterance="show me recent commits",
            project_slug="test-project",
            fetched_context=fetch_result,
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis
        assert synthesize_result.data["type"] == "git-log"
        assert isinstance(synthesize_result.summary, str)
        assert len(synthesize_result.summary) > 0

    @pytest.mark.asyncio
    async def test_git_status_fetch_and_synthesis(self):
        """Test complete pipeline for git status fetch + synthesis."""
        source_responses = {
            FetchSource.GIT_STATUS: _mock_git_response("status"),
        }
        fetch_strand = create_mock_fetch_strand(source_responses)
        orchestrator = FetchOrchestrator(fetch_strand)

        request = FetchRequest(
            intent_type=IntentType.ACTION,  # ACTION includes GIT_STATUS
            context=FetchContext(
                project_slug="test-project",
                repo_path="/home/coding/test-project",
                namespace="default",  # ACTION requires namespace
                proxy="http://kubectl-proxy:8001",  # ACTION requires proxy
            ),
            intent_id="test-intent-004",
            session_id="test-session",
        )

        fetch_result = await orchestrator.execute_fetch(request)

        # Verify fetch
        assert FetchSource.GIT_STATUS in fetch_result.sources
        assert fetch_result.sources[FetchSource.GIT_STATUS].status == "success"
        assert fetch_result.sources[FetchSource.GIT_STATUS].data["has_changes"] is True
        assert len(fetch_result.sources[FetchSource.GIT_STATUS].data["changed_files"]) == 2

        # Execute synthesis
        synthesize_strand = create_mock_synthesize_strand(
            _mock_llm_synthesis_response("git-status", "low")
        )
        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-004",
            intent_type=IntentType.ACTION,
            utterance="check git status",
            project_slug="test-project",
            fetched_context=fetch_result,
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis
        assert synthesize_result.urgency == Urgency.LOW
        assert synthesize_result.data["type"] == "git-status"
        assert isinstance(synthesize_result.summary, str)


# ============================================================================
# Test: ArgoCD fetch sources
# ============================================================================


class TestArgocdFetchSources:
    """Test fetch execution for ArgoCD-based source types."""

    @pytest.mark.asyncio
    async def test_argocd_app_fetch_and_synthesis(self):
        """Test complete pipeline for ArgoCD application fetch + synthesis."""
        source_responses = {
            FetchSource.ARGOCD_APP: _mock_argocd_response("web-app"),
        }
        fetch_strand = create_mock_fetch_strand(source_responses)
        orchestrator = FetchOrchestrator(fetch_strand)

        request = FetchRequest(
            intent_type=IntentType.ACTION,  # ACTION includes ARGOCD_APP
            context=FetchContext(
                project_slug="web-app",
                app_name="web-app",
                cluster="ardenone-manager",
            ),
            intent_id="test-intent-005",
            session_id="test-session",
        )

        fetch_result = await orchestrator.execute_fetch(request)

        # Verify fetch
        assert FetchSource.ARGOCD_APP in fetch_result.sources
        assert fetch_result.sources[FetchSource.ARGOCD_APP].status == "success"
        assert fetch_result.sources[FetchSource.ARGOCD_APP].data["sync_status"] == "Synced"
        assert fetch_result.sources[FetchSource.ARGOCD_APP].data["health_status"] == "Healthy"

        # Execute synthesis
        synthesize_strand = create_mock_synthesize_strand(
            _mock_llm_synthesis_response("argocd-status", "normal")
        )
        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-005",
            intent_type=IntentType.ACTION,
            utterance="check the application sync status",
            project_slug="web-app",
            fetched_context=fetch_result,
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis
        assert synthesize_result.data["type"] == "argocd-status"
        assert isinstance(synthesize_result.summary, str)
        assert len(synthesize_result.summary) > 0


# ============================================================================
# Test: Bead fetch sources
# ============================================================================


class TestBeadFetchSources:
    """Test fetch execution for Bead-based source types."""

    @pytest.mark.asyncio
    async def test_bead_list_fetch_and_synthesis(self):
        """Test complete pipeline for bead list fetch + synthesis."""
        source_responses = {
            FetchSource.BEAD_LIST: _mock_bead_list_response("test-project"),
        }
        fetch_strand = create_mock_fetch_strand(source_responses)
        orchestrator = FetchOrchestrator(fetch_strand)

        request = FetchRequest(
            intent_type=IntentType.STATUS,  # STATUS includes BEAD_LIST
            context=FetchContext(
                project_slug="test-project",
                repo_path="/home/coding/test-project",
            ),
            intent_id="test-intent-006",
            session_id="test-session",
        )

        fetch_result = await orchestrator.execute_fetch(request)

        # Verify fetch
        assert FetchSource.BEAD_LIST in fetch_result.sources
        assert fetch_result.sources[FetchSource.BEAD_LIST].status == "success"
        assert fetch_result.sources[FetchSource.BEAD_LIST].data["count"] == 2
        beads = fetch_result.sources[FetchSource.BEAD_LIST].data["beads"]
        assert len(beads) == 2
        assert beads[0]["id"] == "adc-1mzt"
        assert beads[0]["status"] == "in-progress"

        # Execute synthesis
        synthesize_strand = create_mock_synthesize_strand(
            _mock_llm_synthesis_response("bead-list", "normal")
        )
        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-006",
            intent_type=IntentType.STATUS,
            utterance="show me the beads for this project",
            project_slug="test-project",
            fetched_context=fetch_result,
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis
        assert synthesize_result.data["type"] == "bead-list"
        assert isinstance(synthesize_result.summary, str)
        assert len(synthesize_result.summary) > 0


# ============================================================================
# Test: Multi-source fetch scenarios
# ============================================================================


class TestMultiSourceFetchScenarios:
    """Test scenarios with multiple fetch sources."""

    @pytest.mark.asyncio
    async def test_multiple_fetch_sources_single_synthesis(self):
        """Test pipeline with multiple successful fetch sources."""
        source_responses = {
            FetchSource.KUBECTL_PODS: _mock_kubernetes_response("pods", "production"),
            FetchSource.GIT_STATUS: _mock_git_response("status"),  # ACTION includes GIT_STATUS, not GIT_LOG
            FetchSource.ARGOCD_APP: _mock_argocd_response("web-app"),
        }
        fetch_strand = create_mock_fetch_strand(source_responses)
        orchestrator = FetchOrchestrator(fetch_strand)

        request = FetchRequest(
            intent_type=IntentType.ACTION,  # ACTION includes all three sources
            context=FetchContext(
                project_slug="web-app",
                namespace="production",
                repo_path="/home/coding/web-app",
                proxy="http://kubectl-proxy:8001",
                app_name="web-app",
                cluster="ardenone-manager",
                deployment="web-app",  # ACTION requires deployment
            ),
            intent_id="test-intent-007",
            session_id="test-session",
        )

        fetch_result = await orchestrator.execute_fetch(request)

        # Verify all sources executed
        assert FetchSource.KUBECTL_PODS in fetch_result.sources
        assert FetchSource.GIT_STATUS in fetch_result.sources
        assert FetchSource.ARGOCD_APP in fetch_result.sources

        # All should be successful
        assert all(s.status == "success" for s in fetch_result.sources.values())

        # Execute synthesis with multi-source context
        synthesize_strand = create_mock_synthesize_strand(
            _mock_llm_synthesis_response("multi-source-status", "normal")
        )
        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-007",
            intent_type=IntentType.ACTION,
            utterance="check overall application health",
            project_slug="web-app",
            fetched_context=fetch_result,
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis incorporates multiple sources
        assert synthesize_result.data["type"] == "multi-source-status"
        assert synthesize_result.coverage is not None
        assert synthesize_result.coverage["total_sources"] >= 3
        assert synthesize_result.coverage["succeeded"] >= 3

    @pytest.mark.asyncio
    async def test_mixed_success_failure_fetch_with_synthesis(self):
        """Test pipeline with mixed successful and failed fetch sources."""

        # Mock successful response
        async def success_executor(ctx: FetchContext) -> dict:
            return {"mock": "success"}

        # Mock failed response
        async def failure_executor(ctx: FetchContext) -> dict:
            raise RuntimeError("Connection failed")

        fetch_strand = FetchStrand()
        fetch_strand._source_executors[FetchSource.KUBECTL_PODS] = success_executor
        fetch_strand._source_executors[FetchSource.GIT_LOG] = success_executor
        fetch_strand._source_executors[FetchSource.ARGOCD_APP] = failure_executor

        orchestrator = FetchOrchestrator(fetch_strand)

        request = FetchRequest(
            intent_type=IntentType.STATUS,
            context=FetchContext(
                project_slug="test-project",
                namespace="production",
                proxy="http://kubectl-proxy:8001",
            ),
            intent_id="test-intent-008",
            session_id="test-session",
        )

        fetch_result = await orchestrator.execute_fetch(request)

        # Verify mixed outcomes
        assert fetch_result.sources[FetchSource.KUBECTL_PODS].status == "success"
        assert fetch_result.sources[FetchSource.GIT_LOG].status == "success"
        assert fetch_result.sources[FetchSource.ARGOCD_APP].status == "error"

        # Verify coverage tracking
        assert len(fetch_result.coverage.succeeded) >= 2
        assert len(fetch_result.coverage.failed) >= 1
        assert fetch_result.coverage.success_rate < 1.0

        # Execute synthesis with degraded context
        synthesize_strand = create_mock_synthesize_strand(
            _mock_llm_synthesis_response("degraded-status", "high")
        )
        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-008",
            intent_type=IntentType.STATUS,
            utterance="check status despite partial failures",
            project_slug="test-project",
            fetched_context=fetch_result,
            urgency="high",
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis handles partial failure gracefully
        assert synthesize_result.urgency == Urgency.HIGH
        assert synthesize_result.caveats is not None
        assert len(synthesize_result.caveats) > 0
        assert synthesize_result.coverage["succeeded"] >= 2


# ============================================================================
# Test: Synthesis special cases
# ============================================================================


class TestSynthesisSpecialCases:
    """Test synthesis edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_synthesis_with_no_fetched_context(self):
        """Test synthesis when no fetch context is available."""
        synthesize_strand = create_mock_synthesize_strand(
            _mock_llm_synthesis_response("fallback", "normal")
        )

        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-009",
            intent_type=IntentType.BRAINSTORM,
            utterance="brainstorm ideas for the new feature",
            project_slug="test-project",
            fetched_context=None,  # No fetch context
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis handles missing context gracefully
        assert synthesize_result.data["type"] == "fallback"
        assert synthesize_result.coverage is None
        assert synthesize_result.caveats is None

    @pytest.mark.asyncio
    async def test_synthesis_with_malformed_llm_response(self):
        """Test synthesis handles malformed LLM responses gracefully."""
        synthesize_strand = create_mock_synthesize_strand("not valid json at all")

        fetch_result = FetchResult(
            intent_id="test-intent-010",
            intent_type=IntentType.LOOKUP,
            sources={},
            coverage=FetchCoverage(total_sources=0, succeeded=[], timed_out=[], failed=[], skipped=[]),
            total_duration_ms=100,
        )

        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-010",
            intent_type=IntentType.LOOKUP,
            utterance="lookup something",
            project_slug="test-project",
            fetched_context=fetch_result,
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis returns error result instead of raising
        assert synthesize_result.data["type"] == "error"
        assert "parse" in synthesize_result.data["error"].lower()
        assert synthesize_result.urgency == Urgency.NORMAL
        assert isinstance(synthesize_result.summary, str)

    @pytest.mark.asyncio
    async def test_synthesis_with_markdown_fenced_json(self):
        """Test synthesis handles GLM-style fenced JSON responses."""
        fenced_response = '''```json
{
    "data": {"type": "test"},
    "summary": "Test result",
    "urgency": "normal"
}
```'''
        synthesize_strand = create_mock_synthesize_strand(fenced_response)

        fetch_result = FetchResult(
            intent_id="test-intent-011",
            intent_type=IntentType.LOOKUP,
            sources={},
            coverage=FetchCoverage(total_sources=0, succeeded=[], timed_out=[], failed=[], skipped=[]),
            total_duration_ms=100,
        )

        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-011",
            intent_type=IntentType.LOOKUP,
            utterance="test fence stripping",
            project_slug="test-project",
            fetched_context=fetch_result,
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify synthesis strips fences and parses JSON correctly
        assert synthesize_result.data["type"] == "test"
        assert synthesize_result.summary == "Test result"
        assert synthesize_result.urgency == Urgency.NORMAL


# ============================================================================
# Test: Urgency classification
# ============================================================================


class TestUrgencyClassification:
    """Test urgency classification through synthesis."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("urgency_level,expected_enum", [
        ("critical", Urgency.CRITICAL),
        ("high", Urgency.HIGH),
        ("normal", Urgency.NORMAL),
        ("low", Urgency.LOW),
    ])
    async def test_urgency_classification_levels(self, urgency_level, expected_enum):
        """Test that all urgency levels are correctly classified."""
        response_data = {
            "data": {"type": "test"},
            "summary": f"Test with {urgency_level} urgency",
            "urgency": urgency_level,
        }
        synthesize_strand = create_mock_synthesize_strand(json.dumps(response_data))

        fetch_result = FetchResult(
            intent_id="test-intent-urgency",
            intent_type=IntentType.STATUS,
            sources={},
            coverage=FetchCoverage(total_sources=0, succeeded=[], timed_out=[], failed=[], skipped=[]),
            total_duration_ms=100,
        )

        synthesize_request = SynthesizeRequest(
            intent_id="test-intent-urgency",
            intent_type=IntentType.STATUS,
            utterance="test urgency classification",
            project_slug="test-project",
            fetched_context=fetch_result,
        )

        synthesize_result = await synthesize_strand.synthesize(synthesize_request)

        # Verify urgency enum mapping
        assert synthesize_result.urgency == expected_enum
        assert urgency_level in synthesize_result.summary.lower()


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
