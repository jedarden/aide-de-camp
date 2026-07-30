"""
Cluster → ArgoCD endpoint resolution (bead adc-1ejh).

There is no single ArgoCD API: which instance holds a project's Application
depends on the cluster the project lives on. This module maps each cluster to
its ArgoCD API base URL and an `access` mode, loaded from
``config/clusters.yaml`` and hot-reloaded via an mtime-checked cache — the same
strategy every hot-reloaded config artifact uses (stat the file each call,
re-read only when its mtime changed).

The fetch strand holds no ArgoCD credentials, so it can only *consume*
``read-only-proxy`` endpoints. Any cluster that is unmapped, or mapped to an
access mode the strand cannot satisfy (``authenticated`` with no credential
path), resolves as **unsatisfiable** — the ArgoCD source then fails with an
honest ``fetch_coverage`` caveat. This is what makes querying the wrong
instance impossible: a wrong-instance query would otherwise return not-found
(indistinguishable from "app doesn't exist") and silently drop the sync row.

See docs/plan/plan.md → Fetch Strand → Cluster→ArgoCD Endpoint Resolution.
"""

from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Optional

import yaml

logger = getLogger(__name__)

# config/clusters.yaml lives at the repo root under config/; this file is
# src/fetch/clusters.py, so the repo root is three parents up.
CLUSTERS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "clusters.yaml"

# The only access mode the fetch strand can satisfy: no credentials needed,
# a proxy injects a read-only token.
CONSUMABLE_ACCESS = "read-only-proxy"

# mtime-checked cache (mirrors src/components/hot_reload.py's pattern).
_cache: Optional[dict] = None
_cache_mtime: Optional[float] = None


def _read_clusters_file(path: Path = CLUSTERS_PATH) -> dict:
    """Parse the raw YAML, returning the ``clusters:`` mapping (or {})."""
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        logger.warning(f"clusters config not found at {path}; all clusters unmapped")
        return {}
    except (yaml.YAMLError, OSError) as e:
        logger.error(f"Failed to parse clusters config {path}: {e}")
        # Preserve the previously-known-good cache rather than poisoning it:
        # return whatever is cached (possibly empty) so a malformed edit does
        # not flip every mapped cluster to unmapped mid-flight.
        return _cache or {}
    if not isinstance(raw, dict):
        logger.error(f"clusters config {path} is not a mapping (got {type(raw).__name__})")
        return _cache or {}
    clusters = raw.get("clusters", {})
    if not isinstance(clusters, dict):
        logger.error(f"'clusters' in {path} is not a mapping (got {type(clusters).__name__})")
        return _cache or {}
    return clusters


def get_clusters(force: bool = False) -> dict:
    """
    Return the parsed ``clusters`` mapping, reloading only when the file's
    mtime has changed (or when ``force`` is set, for tests).

    A benign parse failure returns the last good cache instead of an empty
    dict, so a transiently-malformed edit never silently unmaps everything.
    """
    global _cache, _cache_mtime
    try:
        mtime = CLUSTERS_PATH.stat().st_mtime
    except OSError:
        # File vanished: keep the last-known-good cache (best effort).
        return _cache or {}

    if force or _cache is None or mtime != _cache_mtime:
        parsed = _read_clusters_file()
        # Don't poison the cache on a parse failure: _read_clusters_file
        # already returns the prior cache in that case, so this is a no-op
        # when parsing failed — but guard explicitly for clarity.
        _cache = parsed
        _cache_mtime = mtime
        logger.debug(f"Reloaded clusters config ({len(parsed)} clusters) from {CLUSTERS_PATH}")
    return _cache


def reset_cache() -> None:
    """Clear the mtime cache (test hook)."""
    global _cache, _cache_mtime
    _cache = None
    _cache_mtime = None


@dataclass(frozen=True)
class ArgocdResolution:
    """Result of resolving a cluster to an ArgoCD endpoint.

    ``satisfiable`` is True only when the strand can actually issue the query —
    i.e. the cluster is mapped AND its access mode is consumable without
    credentials. When False, ``reason`` explains why (for the caveat strip).
    """

    cluster: Optional[str]
    argocd_api: Optional[str]
    access: Optional[str]
    satisfiable: bool
    reason: Optional[str] = None


def resolve_argocd_endpoint(cluster: Optional[str]) -> ArgocdResolution:
    """
    Resolve a cluster name to a consumable ArgoCD API base URL.

    Resolution rules (every unsatisfiable case carries a human-readable
    ``reason`` for the fetch_coverage caveat):

    * ``cluster`` is None/empty → unsatisfiable ("no cluster configured …")
    * cluster absent from clusters.yaml → unsatisfiable ("no ArgoCD mapping …")
    * access == ``read-only-proxy`` → satisfiable, argocd_api set
    * access == ``authenticated`` → unsatisfiable ("requires authentication …")
    * any other/unknown access mode → unsatisfiable ("unsupported access mode …")
    """
    if not cluster:
        return ArgocdResolution(
            cluster=None,
            argocd_api=None,
            access=None,
            satisfiable=False,
            reason="No cluster configured for this project; ArgoCD endpoint cannot be resolved",
        )

    entry = get_clusters().get(cluster)
    if entry is None:
        return ArgocdResolution(
            cluster=cluster,
            argocd_api=None,
            access=None,
            satisfiable=False,
            reason=(
                f"Cluster '{cluster}' has no ArgoCD mapping in config/clusters.yaml; "
                f"ArgoCD source omitted to avoid querying the wrong instance"
            ),
        )

    access = entry.get("access")
    argocd_api = entry.get("argocd_api")

    if access == CONSUMABLE_ACCESS:
        if not argocd_api:
            return ArgocdResolution(
                cluster=cluster,
                argocd_api=None,
                access=access,
                satisfiable=False,
                reason=f"Cluster '{cluster}' is read-only-proxy but defines no argocd_api",
            )
        return ArgocdResolution(
            cluster=cluster,
            argocd_api=argocd_api,
            access=access,
            satisfiable=True,
        )

    if access == "authenticated":
        return ArgocdResolution(
            cluster=cluster,
            argocd_api=argocd_api,
            access=access,
            satisfiable=False,
            reason=(
                f"Cluster '{cluster}' ArgoCD requires authentication "
                f"(no no-auth read-only proxy available); ArgoCD source omitted"
            ),
        )

    return ArgocdResolution(
        cluster=cluster,
        argocd_api=argocd_api,
        access=access,
        satisfiable=False,
        reason=(
            f"Cluster '{cluster}' uses unsupported ArgoCD access mode '{access}' "
            f"(fetch strand can only consume '{CONSUMABLE_ACCESS}')"
        ),
    )


class ArgocdEndpointUnresolvable(Exception):
    """Raised when an ArgoCD query cannot be issued without risking the wrong instance.

    Carries the human-readable resolution ``reason`` so the orchestrator can
    surface it as a fetch_coverage caveat. Raising (rather than returning an
    error dict) integrates with the orchestrator's existing failure path: the
    source is bucketed as failed and a caveat is emitted, never a silent
    wrong-instance query.
    """

    def __init__(self, reason: str, cluster: Optional[str] = None):
        self.reason = reason
        self.cluster = cluster
        super().__init__(reason)
