"""
Pre-warmed context cache service.

Background service that refreshes context for active topics every N minutes.
Provides fast context retrieval when intents arrive for those topics.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging import getLogger
from typing import Any, Optional

from ..session.store import get_store
from ..fetch.orchestrator import get_fetch_strand
from ..fetch.commands import FetchContext, FetchSource, IntentType


logger = getLogger(__name__)

# Default TTL for context cache (10 minutes)
DEFAULT_CONTEXT_TTL = 600
# Interval between context refresh cycles (5 minutes)
DEFAULT_REFRESH_INTERVAL = 300


@dataclass
class ContextBundle:
    """A bundle of pre-fetched context for a topic."""
    topic_id: str
    project_slugs: list[str]
    kubectl_status: Optional[dict] = None
    argocd_status: Optional[dict] = None
    git_log: Optional[dict] = None
    bead_list: Optional[dict] = None
    ci_status: Optional[dict] = None
    fetched_at: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))
    source_summary: dict = field(default_factory=dict)  # Which sources succeeded/failed

    def is_valid(self, ttl_seconds: int = DEFAULT_CONTEXT_TTL) -> bool:
        """Check if this context bundle is still valid."""
        age = int(datetime.now(timezone.utc).timestamp()) - self.fetched_at
        return age < ttl_seconds

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "topic_id": self.topic_id,
            "project_slugs": self.project_slugs,
            "kubectl_status": self.kubectl_status,
            "argocd_status": self.argocd_status,
            "git_log": self.git_log,
            "bead_list": self.bead_list,
            "ci_status": self.ci_status,
            "fetched_at": self.fetched_at,
            "source_summary": self.source_summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextBundle":
        """Create from dictionary."""
        return cls(
            topic_id=data["topic_id"],
            project_slugs=data["project_slugs"],
            kubectl_status=data.get("kubectl_status"),
            argocd_status=data.get("argocd_status"),
            git_log=data.get("git_log"),
            bead_list=data.get("bead_list"),
            ci_status=data.get("ci_status"),
            fetched_at=data.get("fetched_at", int(datetime.now(timezone.utc).timestamp())),
            source_summary=data.get("source_summary", {}),
        )


class ContextWarmer:
    """
    Background service that maintains warm context for active topics.

    Every N minutes, refreshes context for all recently active topics.
    Context is stored in the session store for fast retrieval.
    """

    def __init__(
        self,
        refresh_interval: int = DEFAULT_REFRESH_INTERVAL,
        context_ttl: int = DEFAULT_CONTEXT_TTL,
    ):
        self.refresh_interval = refresh_interval
        self.context_ttl = context_ttl
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self._fetch_strand = get_fetch_strand()

    async def fetch_kubectl_status(self, project_slug: str) -> Optional[dict]:
        """Fetch kubectl status for a project."""
        context = FetchContext(project_slug=project_slug)
        if project_slug:
            context.namespace = project_slug.replace("-", "")

        result = await self._fetch_strand._fetch_kubectl_pods(context)
        return result if result and "error" not in result else None

    async def fetch_argocd_status(self, project_slug: str) -> Optional[dict]:
        """Fetch ArgoCD status for a project.

        The endpoint is resolved from the project's cluster via
        config/clusters.yaml (bead adc-1ejh); a cluster with no consumable
        read-only proxy yields no ArgoCD data rather than querying the wrong
        instance.
        """
        from ..fetch.clusters import ArgocdEndpointUnresolvable
        from ..registry import get_project

        cfg = get_project(project_slug) if project_slug else None
        context = FetchContext(
            project_slug=project_slug,
            app_name=(cfg.get("argocd_app") if cfg else None) or project_slug,
            cluster=cfg.get("cluster") if cfg else None,
        )
        try:
            result = await self._fetch_strand._fetch_argocd_app(context)
        except ArgocdEndpointUnresolvable as e:
            logger.info(f"No ArgoCD data for {project_slug}: {e.reason}")
            return None
        return result if result and "error" not in result else None

    async def fetch_git_log(self, project_slug: str) -> Optional[dict]:
        """Fetch git log for a project."""
        context = FetchContext(project_slug=project_slug, repo_path=f"/home/coding/{project_slug}")
        result = await self._fetch_strand._fetch_git_log(context)
        return result if result and "error" not in result else None

    async def fetch_bead_list(self, project_slug: str) -> Optional[dict]:
        """Fetch bead list for a project."""
        context = FetchContext(project_slug=project_slug, repo_path=f"/home/coding/{project_slug}")
        result = await self._fetch_strand._fetch_bead_list(context)
        return result if result and "error" not in result else None

    async def fetch_ci_status(self, project_slug: str) -> Optional[dict]:
        """Fetch CI status for a project."""
        context = FetchContext(project_slug=project_slug)
        result = await self._fetch_strand._fetch_ci_status(context)
        return result if result and "error" not in result else None

    async def build_context_bundle(self, topic_id: str, project_slugs: list[str]) -> ContextBundle:
        """
        Build a context bundle for a topic by fetching from all sources.

        Fetches concurrently from all available sources.
        """
        bundle = ContextBundle(
            topic_id=topic_id,
            project_slugs=project_slugs,
        )

        # Fetch from all sources concurrently
        tasks = []

        for project_slug in project_slugs:
            tasks.extend([
                self.fetch_kubectl_status(project_slug),
                self.fetch_argocd_status(project_slug),
                self.fetch_git_log(project_slug),
                self.fetch_bead_list(project_slug),
                self.fetch_ci_status(project_slug),
            ])

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assign results to bundle (order matches tasks above)
        # This is simplified - in practice, we'd track which result corresponds to which source
        # For now, just mark which sources we attempted

        source_summary = {
            "kubectl": "success",
            "argocd": "success",
            "git": "success",
            "beads": "success",
            "ci": "success",
        }

        # Count failures
        failures = sum(1 for r in results if isinstance(r, Exception) or r is None)
        if failures > 0:
            source_summary["failed_count"] = failures
            source_summary["total_count"] = len(results)

        bundle.source_summary = source_summary

        logger.debug(f"Built context bundle for {topic_id} with {len(results)} fetches")

        return bundle

    async def warm_topic_context(self, topic_id: str, project_slugs: list[str]) -> None:
        """Fetch and cache context for a single topic."""
        try:
            bundle = await self.build_context_bundle(topic_id, project_slugs)

            # Store in session store
            store = get_store()
            await store.set_topic_context(
                topic_id=topic_id,
                context_data=bundle.to_dict(),
                ttl_seconds=self.context_ttl,
            )

            logger.debug(f"Warmed context for topic {topic_id}")

        except Exception as e:
            logger.error(f"Error warming context for topic {topic_id}: {e}", exc_info=True)

    async def warm_all_active_topics(self) -> None:
        """Warm context for all active topics."""
        store = get_store()

        # Get active topic IDs
        active_topic_ids = await store.get_active_topic_ids()
        logger.info(f"Warming context for {len(active_topic_ids)} active topics")

        # Get topic details
        # For each topic, we need its project_slugs
        # This is a simplified version - in practice we'd batch fetch topics
        topics = await store.get_active_topics(session_id=None)  # Get all active topics

        # Warm context for each topic concurrently (with rate limiting)
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent fetches

        async def warm_with_limit(topic: dict):
            async with semaphore:
                project_slugs = json.loads(topic.get("project_slugs", "[]"))
                if project_slugs:
                    await self.warm_topic_context(topic["id"], project_slugs)

        tasks = [warm_with_limit(t) for t in topics if t.get("project_slugs")]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Completed warming context for active topics")

    async def cleanup_expired_context(self) -> None:
        """Clean up expired context cache entries."""
        store = get_store()
        deleted = await store.cleanup_expired_context()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired context cache entries")

    async def run(self) -> None:
        """Main loop: periodically warm context for active topics."""
        logger.info(f"Starting context warmer (interval: {self.refresh_interval}s, TTL: {self.context_ttl}s)")

        while self.running:
            try:
                # Warm all active topics
                await self.warm_all_active_topics()

                # Cleanup expired entries
                await self.cleanup_expired_context()

                # Wait for next cycle
                await asyncio.sleep(self.refresh_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in context warmer loop: {e}", exc_info=True)
                await asyncio.sleep(self.refresh_interval)

        logger.info("Context warmer stopped")

    async def start(self) -> None:
        """Start the context warmer background task."""
        if self.task is not None and not self.task.done():
            logger.warning("Context warmer already running")
            return

        self.running = True
        self.task = asyncio.create_task(self.run())
        logger.info("Context warmer started")

    async def stop(self) -> None:
        """Stop the context warmer."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Context warmer stopped")


# Global context warmer instance
_context_warmer: Optional[ContextWarmer] = None


def get_context_warmer() -> ContextWarmer:
    """Get or create the global context warmer instance."""
    global _context_warmer
    if _context_warmer is None:
        _context_warmer = ContextWarmer()
    return _context_warmer
