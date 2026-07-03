"""
Fetch executor - backward compatibility layer.

This module provides a compatibility shim between the old executor API
and the canonical fetch implementation in orchestrator.py and commands.py.

DEPRECATED: Use orchestrator.execute_fetch() and FetchRequest directly.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Any, Optional
import asyncio

from .commands import (
    FetchContext,
    FetchSource,
    IntentType,
    FetchRequest as CanonicalRequest,
    SourceResult as CanonicalSourceResult,
    FetchResult as CanonicalFetchResult,
    FetchCoverage,
)
from .orchestrator import get_fetch_strand


class FetchType(Enum):
    """
    Fetch type enum - maps to FetchSource.

    DEPRECATED: Use FetchSource from commands.py instead.
    """
    KUBECTL_STATUS = "kubectl_pods"
    POD_STATUS = "kubectl_pods"  # Alias for KUBECTL_STATUS
    ARGOCD_STATUS = "argocd_app"
    GIT_LOG = "git_log"
    BEAD_LIST = "bead_list"
    CI_STATUS = "ci_status"
    DEPLOYMENT_STATUS = "kubectl_deployments"


# Map FetchType to FetchSource
_FETCH_TYPE_TO_SOURCE = {
    FetchType.KUBECTL_STATUS: FetchSource.KUBECTL_PODS,
    FetchType.POD_STATUS: FetchSource.KUBECTL_PODS,
    FetchType.ARGOCD_STATUS: FetchSource.ARGOCD_APP,
    FetchType.GIT_LOG: FetchSource.GIT_LOG,
    FetchType.BEAD_LIST: FetchSource.BEAD_LIST,
    FetchType.CI_STATUS: FetchSource.CI_STATUS,
    FetchType.DEPLOYMENT_STATUS: FetchSource.KUBECTL_DEPLOYMENTS,
}

# Map FetchType to IntentType (for creating proper FetchRequest)
_FETCH_TYPE_TO_INTENT = {
    FetchType.KUBECTL_STATUS: IntentType.STATUS,
    FetchType.POD_STATUS: IntentType.STATUS,
    FetchType.ARGOCD_STATUS: IntentType.STATUS,
    FetchType.GIT_LOG: IntentType.STATUS,
    FetchType.BEAD_LIST: IntentType.STATUS,
    FetchType.CI_STATUS: IntentType.STATUS,
    FetchType.DEPLOYMENT_STATUS: IntentType.ACTION,
}


@dataclass
class FetchCommand:
    """
    Fetch command - compatibility wrapper.

    DEPRECATED: Use FetchRequest from commands.py instead.
    """
    fetch_type: FetchType
    project_slug: str
    args: list[str]
    timeout: int

    def to_canonical(self) -> CanonicalRequest:
        """Convert to canonical FetchRequest."""
        fetch_source = _FETCH_TYPE_TO_SOURCE.get(self.fetch_type, FetchSource.KUBECTL_PODS)
        intent_type = _FETCH_TYPE_TO_INTENT.get(self.fetch_type, IntentType.STATUS)

        # Create FetchContext
        context = FetchContext(
            project_slug=self.project_slug,
        )

        # Derive namespace from project_slug
        if context.project_slug:
            context.namespace = context.project_slug.replace("-", "")

        return CanonicalRequest(
            intent_type=intent_type,
            context=context,
            intent_id=f"compat-{self.fetch_type.value}-{self.project_slug}",
            session_id="compat-session",
        )


@dataclass
class FetchResult:
    """
    Fetch result - compatibility wrapper.

    DEPRECATED: Use SourceResult from commands.py instead.
    """
    success: bool
    data: dict[str, Any]
    error: Optional[str] = None
    duration_ms: int = 0

    @classmethod
    def from_canonical(cls, source: FetchSource, result: CanonicalSourceResult) -> "FetchResult":
        """Convert from canonical SourceResult."""
        # Extract the specific field we want based on the source type
        data = result.data

        # For certain sources, we might want to extract specific fields
        if source == FetchSource.KUBECTL_PODS and "pods" in data:
            return cls(
                success=result.status == "success",
                data={"pods": data.get("pods", []), "namespace": data.get("namespace")},
                error=result.error,
                duration_ms=result.duration_ms,
            )
        elif source == FetchSource.ARGOCD_APP:
            return cls(
                success=result.status == "success",
                data=data,
                error=result.error,
                duration_ms=result.duration_ms,
            )
        elif source == FetchSource.GIT_LOG:
            return cls(
                success=result.status == "success",
                data={"commits": data.get("commits", []), "repo": data.get("repo")},
                error=result.error,
                duration_ms=result.duration_ms,
            )
        elif source == FetchSource.BEAD_LIST:
            return cls(
                success=result.status == "success",
                data={"beads": data.get("beads", []), "project": data.get("project")},
                error=result.error,
                duration_ms=result.duration_ms,
            )
        elif source == FetchSource.CI_STATUS:
            return cls(
                success=result.status == "success",
                data={"workflows": data.get("workflows", [])},
                error=result.error,
                duration_ms=result.duration_ms,
            )
        elif source == FetchSource.KUBECTL_DEPLOYMENTS:
            return cls(
                success=result.status == "success",
                data=data,
                error=result.error,
                duration_ms=result.duration_ms,
            )

        return cls(
            success=result.status == "success",
            data=data,
            error=result.error,
            duration_ms=result.duration_ms,
        )


class FetchExecutor:
    """
    Fetch executor - compatibility wrapper.

    DEPRECATED: Use get_orchestrator().execute_fetch() instead.
    """

    def __init__(self):
        self._strand = get_fetch_strand()

    async def execute(self, command: FetchCommand) -> FetchResult:
        """
        Execute a fetch command.

        DEPRECATED: Use get_orchestrator().execute_fetch() instead.
        """
        canonical_request = command.to_canonical()

        # Execute the fetch
        result = await self._strand.fetch(canonical_request)

        # Get the specific source result we care about
        fetch_source = _FETCH_TYPE_TO_SOURCE.get(command.fetch_type)
        if fetch_source and fetch_source in result.sources:
            source_result = result.sources[fetch_source]
            return FetchResult.from_canonical(fetch_source, source_result)

        # If we couldn't find the specific source, return a failure
        return FetchResult(
            success=False,
            data={},
            error=f"Source {command.fetch_type.value} not found in fetch results",
        )


# Global executor instance
_executor: Optional[FetchExecutor] = None


def get_fetch_executor() -> FetchExecutor:
    """
    Get or create the global fetch executor instance.

    DEPRECATED: Use get_orchestrator() instead.
    """
    global _executor
    if _executor is None:
        _executor = FetchExecutor()
    return _executor
