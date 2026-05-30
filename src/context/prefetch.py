"""
Speculative pre-fetch service for common follow-up patterns.

Predicts and pre-fetches data for common follow-up questions to make
responses faster.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from logging import getLogger
from typing import Any, Optional, Callable
import re

from ..session.store import get_store
from ..fetch.executor import get_fetch_executor, FetchCommand, FetchType


logger = getLogger(__name__)


class FollowUpPattern(Enum):
    """Common follow-up question patterns."""
    HOW_LONG = "how_long"  # "how long until...", "when will..."
    WHY = "why"  # "why did...", "why is..."
    WHAT_CHANGED = "what_changed"  # "what changed...", "what's different..."
    IS_READY = "is_ready"  # "is it ready...", "is it done..."
    MORE_DETAIL = "more_detail"  # "tell me more...", "more detail..."
    STATUS_CHECK = "status_check"  # "what's the status...", "how's it going..."
    ERROR_DETAILS = "error_details"  # "what's the error...", "why failed..."


@dataclass
class PrefetchPrediction:
    """A prediction of what data might be needed next."""
    pattern: FollowUpPattern
    topic_id: str
    project_slugs: list[str]
    intent_type: str
    confidence: float
    prefetch_data: dict[str, Any]
    created_at: int
    expires_at: int


@dataclass
class PrefetchCache:
    """Cache for pre-fetched data."""
    key: str  # topic_id:pattern
    data: dict[str, Any]
    created_at: int
    expires_at: int
    hit_count: int = 0
    last_hit: int = 0

    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        return int(datetime.now(timezone.utc).timestamp()) < self.expires_at

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hit_count += 1
        self.last_hit = int(datetime.now(timezone.utc).timestamp())


class SpeculativePrefetcher:
    """
    Speculative pre-fetcher for common follow-up patterns.

    Monitors conversation patterns and pre-fetches data that's likely
    to be requested next, making follow-up responses faster.
    """

    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, PrefetchCache] = {}
        self._recent_utterances: dict[str, list[dict]] = {}  # session_id -> utterances
        self._fetch_callbacks: dict[FollowUpPattern, Callable] = {}
        self._fetch_executor = get_fetch_executor()

        # Register default fetch callbacks
        self._register_default_callbacks()

    def _register_default_callbacks(self) -> None:
        """Register default fetch callbacks for each pattern."""
        async def fetch_how_long(topic_id: str, project_slugs: list[str]) -> dict:
            """Pre-fetch: CI/build status timestamps, deployment times."""
            result = {}
            for project_slug in project_slugs:
                # Fetch CI status for timing info
                ci_cmd = FetchCommand(
                    fetch_type=FetchType.CI_STATUS,
                    project_slug=project_slug,
                    args=[],
                    timeout=30,
                )
                ci_result = await self._fetch_executor.execute(ci_cmd)
                if ci_result.success:
                    result[project_slug] = {"ci_status": ci_result.data}

                # Fetch deployment status
                deploy_cmd = FetchCommand(
                    fetch_type=FetchType.DEPLOYMENT_STATUS,
                    project_slug=project_slug,
                    args=[],
                    timeout=30,
                )
                deploy_result = await self._fetch_executor.execute(deploy_cmd)
                if deploy_result.success:
                    if project_slug not in result:
                        result[project_slug] = {}
                    result[project_slug]["deployment"] = deploy_result.data
            return result

        async def fetch_why(topic_id: str, project_slugs: list[str]) -> dict:
            """Pre-fetch: logs, error messages, recent events."""
            # For now, return recent status that might explain why something happened
            result = {}
            for project_slug in project_slugs:
                status_cmd = FetchCommand(
                    fetch_type=FetchType.KUBECTL_STATUS,
                    project_slug=project_slug,
                    args=[],
                    timeout=30,
                )
                status_result = await self._fetch_executor.execute(status_cmd)
                if status_result.success:
                    result[project_slug] = {
                        "pods": status_result.data.get("pods", []),
                        "recent_events": status_result.data.get("events", []),
                    }
            return result

        async def fetch_what_changed(topic_id: str, project_slugs: list[str]) -> dict:
            """Pre-fetch: git diff, recent commits, history."""
            result = {}
            for project_slug in project_slugs:
                git_cmd = FetchCommand(
                    fetch_type=FetchType.GIT_LOG,
                    project_slug=project_slug,
                    args=[],
                    timeout=30,
                )
                git_result = await self._fetch_executor.execute(git_cmd)
                if git_result.success:
                    result[project_slug] = git_result.data
            return result

        async def fetch_is_ready(topic_id: str, project_slugs: list[str]) -> dict:
            """Pre-fetch: health status, ready condition, completion status."""
            result = {}
            for project_slug in project_slugs:
                status_cmd = FetchCommand(
                    fetch_type=FetchType.KUBECTL_STATUS,
                    project_slug=project_slug,
                    args=[],
                    timeout=30,
                )
                status_result = await self._fetch_executor.execute(status_cmd)
                if status_result.success:
                    pods = status_result.data.get("pods", [])
                    ready_count = sum(1 for p in pods if p.get("phase") == "Running")
                    result[project_slug] = {
                        "health": "healthy" if ready_count == len(pods) and len(pods) > 0 else "degraded",
                        "ready": ready_count == len(pods) and len(pods) > 0,
                        "completion": f"{ready_count}/{len(pods)}" if pods else "0/0",
                    }
            return result

        async def fetch_more_detail(topic_id: str, project_slugs: list[str]) -> dict:
            """Pre-fetch: extended metrics, detailed status."""
            result = {}
            for project_slug in project_slugs:
                # Fetch comprehensive status
                status_cmd = FetchCommand(
                    fetch_type=FetchType.KUBECTL_STATUS,
                    project_slug=project_slug,
                    args=[],
                    timeout=30,
                )
                status_result = await self._fetch_executor.execute(status_cmd)
                if status_result.success:
                    result[project_slug] = status_result.data

                # Fetch ArgoCD status if available
                argocd_cmd = FetchCommand(
                    fetch_type=FetchType.ARGOCD_STATUS,
                    project_slug=project_slug,
                    args=[],
                    timeout=30,
                )
                argocd_result = await self._fetch_executor.execute(argocd_cmd)
                if argocd_result.success:
                    if project_slug not in result:
                        result[project_slug] = {}
                    result[project_slug]["argocd"] = argocd_result.data
            return result

        async def fetch_status_check(topic_id: str, project_slugs: list[str]) -> dict:
            """Pre-fetch: current status, phase, health."""
            result = {}
            for project_slug in project_slugs:
                status_cmd = FetchCommand(
                    fetch_type=FetchType.KUBECTL_STATUS,
                    project_slug=project_slug,
                    args=[],
                    timeout=30,
                )
                status_result = await self._fetch_executor.execute(status_cmd)
                if status_result.success:
                    pods = status_result.data.get("pods", [])
                    result[project_slug] = {
                        "status": "running" if any(p.get("phase") == "Running" for p in pods) else "not_running",
                        "phase": next((p.get("phase") for p in pods if p.get("phase") != "Succeeded"), "Unknown"),
                        "health": "healthy" if all(p.get("phase") in ("Running", "Succeeded") for p in pods) else "degraded",
                    }
            return result

        async def fetch_error_details(topic_id: str, project_slugs: list[str]) -> dict:
            """Pre-fetch: error logs, failure reasons, stack traces."""
            result = {}
            for project_slug in project_slugs:
                # Fetch CI status for error details
                ci_cmd = FetchCommand(
                    fetch_type=FetchType.CI_STATUS,
                    project_slug=project_slug,
                    args=[],
                    timeout=30,
                )
                ci_result = await self._fetch_executor.execute(ci_cmd)
                if ci_result.success:
                    workflows = ci_result.data.get("workflows", [])
                    failed_workflows = [w for w in workflows if w.get("phase") == "Failed"]
                    result[project_slug] = {
                        "error_logs": [w.get("message") for w in failed_workflows],
                        "failure_reason": failed_workflows[0].get("message") if failed_workflows else None,
                        "stack_trace": None,  # Would need full workflow fetch
                    }
            return result

        self._fetch_callbacks = {
            FollowUpPattern.HOW_LONG: fetch_how_long,
            FollowUpPattern.WHY: fetch_why,
            FollowUpPattern.WHAT_CHANGED: fetch_what_changed,
            FollowUpPattern.IS_READY: fetch_is_ready,
            FollowUpPattern.MORE_DETAIL: fetch_more_detail,
            FollowUpPattern.STATUS_CHECK: fetch_status_check,
            FollowUpPattern.ERROR_DETAILS: fetch_error_details,
        }

    def register_fetch_callback(
        self,
        pattern: FollowUpPattern,
        callback: Callable,
    ) -> None:
        """Register a custom fetch callback for a pattern."""
        self._fetch_callbacks[pattern] = callback

    async def analyze_utterance(
        self,
        session_id: str,
        utterance: str,
        topic_id: str,
        project_slugs: list[str],
        intent_type: str,
    ) -> list[PrefetchPrediction]:
        """
        Analyze an utterance and generate prefetch predictions.

        Returns a list of predictions with confidence scores.
        """
        predictions = []

        # Detect patterns in utterance
        utterance_lower = utterance.lower()

        # HOW_LONG pattern: "how long", "when", "time remaining", "ETA"
        if re.search(r"how long|when will|time remaining|eta|estimated", utterance_lower):
            predictions.append(PrefetchPrediction(
                pattern=FollowUpPattern.HOW_LONG,
                topic_id=topic_id,
                project_slugs=project_slugs,
                intent_type=intent_type,
                confidence=0.8,
                prefetch_data={},
                created_at=int(datetime.now(timezone.utc).timestamp()),
                expires_at=int(datetime.now(timezone.utc).timestamp()) + self.ttl_seconds,
            ))

        # WHY pattern: "why", "how come", "reason"
        if re.search(r"why|how come|reason for|what caused", utterance_lower):
            predictions.append(PrefetchPrediction(
                pattern=FollowUpPattern.WHY,
                topic_id=topic_id,
                project_slugs=project_slugs,
                intent_type=intent_type,
                confidence=0.7,
                prefetch_data={},
                created_at=int(datetime.now(timezone.utc).timestamp()),
                expires_at=int(datetime.now(timezone.utc).timestamp()) + self.ttl_seconds,
            ))

        # WHAT_CHANGED pattern: "what changed", "what's different", "since"
        if re.search(r"what changed|what's different|what's new|since|from before", utterance_lower):
            predictions.append(PrefetchPrediction(
                pattern=FollowUpPattern.WHAT_CHANGED,
                topic_id=topic_id,
                project_slugs=project_slugs,
                intent_type=intent_type,
                confidence=0.75,
                prefetch_data={},
                created_at=int(datetime.now(timezone.utc).timestamp()),
                expires_at=int(datetime.now(timezone.utc).timestamp()) + self.ttl_seconds,
            ))

        # IS_READY pattern: "is it ready", "is it done", "finished", "complete"
        if re.search(r"is it ready|is it done|finished|complete|ready yet", utterance_lower):
            predictions.append(PrefetchPrediction(
                pattern=FollowUpPattern.IS_READY,
                topic_id=topic_id,
                project_slugs=project_slugs,
                intent_type=intent_type,
                confidence=0.85,
                prefetch_data={},
                created_at=int(datetime.now(timezone.utc).timestamp()),
                expires_at=int(datetime.now(timezone.utc).timestamp()) + self.ttl_seconds,
            ))

        # Store utterance for context
        self._store_utterance(session_id, utterance, topic_id, intent_type)

        return predictions

    def _store_utterance(
        self,
        session_id: str,
        utterance: str,
        topic_id: str,
        intent_type: str,
    ) -> None:
        """Store utterance for pattern analysis."""
        if session_id not in self._recent_utterances:
            self._recent_utterances[session_id] = []

        self._recent_utterances[session_id].append({
            "utterance": utterance,
            "topic_id": topic_id,
            "intent_type": intent_type,
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        })

        # Keep only last 20 utterances
        if len(self._recent_utterances[session_id]) > 20:
            self._recent_utterances[session_id] = self._recent_utterances[session_id][-20:]

    async def prefetch_for_predictions(
        self,
        predictions: list[PrefetchPrediction],
    ) -> dict[str, PrefetchCache]:
        """
        Execute prefetch for a list of predictions.

        Returns a dict of cache entries keyed by pattern.
        """
        cache_entries = {}

        for prediction in predictions:
            # Skip low confidence predictions
            if prediction.confidence < 0.5:
                continue

            # Check if we already have valid cache
            cache_key = f"{prediction.topic_id}:{prediction.pattern.value}"
            if cache_key in self._cache and self._cache[cache_key].is_valid():
                logger.debug(f"Cache hit for {cache_key}")
                cache_entries[cache_key] = self._cache[cache_key]
                continue

            # Fetch data
            callback = self._fetch_callbacks.get(prediction.pattern)
            if not callback:
                logger.warning(f"No fetch callback for pattern {prediction.pattern}")
                continue

            try:
                data = await callback(
                    prediction.topic_id,
                    prediction.project_slugs,
                )

                # Create cache entry
                cache_entry = PrefetchCache(
                    key=cache_key,
                    data=data,
                    created_at=int(datetime.now(timezone.utc).timestamp()),
                    expires_at=prediction.expires_at,
                )

                self._cache[cache_key] = cache_entry
                cache_entries[cache_key] = cache_entry

                logger.info(f"Prefetched data for {cache_key}")

            except Exception as e:
                logger.error(f"Prefetch error for {prediction.pattern}: {e}", exc_info=True)

        return cache_entries

    def get_prefetch_data(
        self,
        topic_id: str,
        pattern: FollowUpPattern,
    ) -> Optional[dict]:
        """
        Get pre-fetched data for a topic and pattern.

        Returns None if no valid cache exists.
        """
        cache_key = f"{topic_id}:{pattern.value}"

        if cache_key not in self._cache:
            return None

        cache_entry = self._cache[cache_key]

        if not cache_entry.is_valid():
            # Cache expired, remove it
            del self._cache[cache_key]
            return None

        # Record cache hit
        cache_entry.record_hit()

        return cache_entry.data

    def get_all_prefetch_data(self, topic_id: str) -> dict[str, Any]:
        """Get all pre-fetched data for a topic."""
        result = {}
        prefix = f"{topic_id}:"

        for key, cache_entry in self._cache.items():
            if key.startswith(prefix) and cache_entry.is_valid():
                pattern = key[len(prefix):]
                result[pattern] = {
                    "data": cache_entry.data,
                    "hit_count": cache_entry.hit_count,
                    "expires_at": cache_entry.expires_at,
                }

        return result

    async def cleanup_expired(self) -> int:
        """Clean up expired cache entries. Returns count of cleaned entries."""
        now = int(datetime.now(timezone.utc).timestamp())
        expired_keys = [
            key for key, cache in self._cache.items()
            if cache.expires_at < now
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired prefetch entries")

        return len(expired_keys)

    def get_stats(self) -> dict:
        """Get prefetch statistics."""
        total_hits = sum(cache.hit_count for cache in self._cache.values())

        return {
            "cache_size": len(self._cache),
            "total_hits": total_hits,
            "valid_entries": sum(1 for cache in self._cache.values() if cache.is_valid()),
            "expired_entries": sum(1 for cache in self._cache.values() if not cache.is_valid()),
        }

    def clear_session(self, session_id: str) -> None:
        """Clear utterance history for a session."""
        if session_id in self._recent_utterances:
            del self._recent_utterances[session_id]


# Global prefetcher instance
_prefetcher: Optional[SpeculativePrefetcher] = None


def get_prefetcher(ttl_seconds: int = 300) -> SpeculativePrefetcher:
    """Get or create the global speculative prefetcher instance."""
    global _prefetcher
    if _prefetcher is None:
        _prefetcher = SpeculativePrefetcher(ttl_seconds=ttl_seconds)
    return _prefetcher
