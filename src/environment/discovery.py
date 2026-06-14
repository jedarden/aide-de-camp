"""
Environment discovery: scans /home/coding/ for git repos and bead workspaces.

Builds a live registry at startup so the fetch strand can resolve project slugs
to local paths without a static config file. Automatically reflects whatever is
actually deployed on this machine.
"""
import asyncio
import re
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path
from typing import Optional

logger = getLogger(__name__)

HOME = Path("/home/coding")


@dataclass
class RepoEntry:
    """A discovered git repository."""
    path: Path
    name: str           # directory name, preserved case
    slug: str           # normalized: lowercase, underscores → hyphens
    has_beads: bool     # .beads/issues.jsonl exists
    remote_url: str | None = None
    remote_name: str | None = None   # basename of remote URL, normalized
    aliases: list[str] = field(default_factory=list)  # all slugs that resolve here

    def __repr__(self) -> str:
        beads = " [beads]" if self.has_beads else ""
        return f"RepoEntry({self.slug}{beads} @ {self.path})"


class EnvironmentRegistry:
    """
    Registry of all git repos discovered on this machine.

    Keyed by normalized slug with alias support so project_slug values
    from LLM classification (e.g. "options-pipeline", "needle", "NEEDLE")
    all resolve to the right entry.
    """

    def __init__(self, repos: dict[str, RepoEntry]):
        self._repos = repos   # slug → entry (may have multiple keys per entry)
        self._entries = list({id(e): e for e in repos.values()}.values())

    def lookup(self, project_slug: str) -> RepoEntry | None:
        """
        Resolve a project slug to a repo entry.

        Matching order:
        1. Exact slug match
        2. Exact lowercase match
        3. Normalized (underscores → hyphens) match
        4. Prefix / suffix match
        5. Significant word overlap
        """
        if not project_slug:
            return None

        normalized = _normalize(project_slug)

        # 1. Exact
        if normalized in self._repos:
            return self._repos[normalized]

        # 2 & 3. Already normalized above — check aliases too
        for slug, entry in self._repos.items():
            if slug == normalized:
                return entry

        # 4. Prefix / suffix
        for slug, entry in self._repos.items():
            if slug.startswith(normalized) or normalized.startswith(slug):
                return entry

        # 5. Word overlap — split on hyphens, require ≥1 significant word match
        query_words = set(normalized.split("-")) - {"the", "a", "an", "of", "for"}
        best: tuple[int, RepoEntry | None] = (0, None)
        for slug, entry in self._repos.items():
            slug_words = set(slug.split("-"))
            overlap = len(query_words & slug_words)
            if overlap > best[0]:
                best = (overlap, entry)
        if best[0] >= 1:
            return best[1]

        return None

    def all_entries(self) -> list[RepoEntry]:
        return self._entries

    def beaded_entries(self) -> list[RepoEntry]:
        return [e for e in self._entries if e.has_beads]

    def summary(self) -> dict:
        return {
            "total_repos": len(self._entries),
            "beaded_repos": len(self.beaded_entries()),
            "slugs": sorted(e.slug for e in self._entries),
        }


async def scan_environment(base: Path = HOME) -> EnvironmentRegistry:
    """
    Scan base directory for git repos and build registry.

    Only looks one level deep — repos live directly under /home/coding/.
    """
    logger.info(f"Scanning {base} for git repos...")

    tasks = []
    try:
        entries = sorted(base.iterdir())
    except PermissionError:
        logger.warning(f"Cannot read {base}")
        return EnvironmentRegistry({})

    for entry in entries:
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if (entry / ".git").is_dir():
            tasks.append(_build_entry(entry))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    repos: dict[str, RepoEntry] = {}
    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"Error scanning repo: {result}")
            continue
        repo: RepoEntry = result
        # Register under slug and all aliases
        for alias in repo.aliases:
            if alias not in repos:
                repos[alias] = repo

    registry = EnvironmentRegistry(repos)
    summary = registry.summary()
    logger.info(
        f"Environment scan complete: {summary['total_repos']} repos, "
        f"{summary['beaded_repos']} with beads"
    )
    return registry


async def _build_entry(path: Path) -> RepoEntry:
    name = path.name
    slug = _normalize(name)
    has_beads = (path / ".beads" / "issues.jsonl").exists()
    remote_url = await _get_remote_url(path)

    remote_name = None
    if remote_url:
        # Extract basename: github.com/jedarden/NEEDLE → needle
        remote_name = _normalize(remote_url.rstrip("/").split("/")[-1].replace(".git", ""))

    aliases = list({slug, remote_name} - {None})  # deduplicated, no None

    return RepoEntry(
        path=path,
        name=name,
        slug=slug,
        has_beads=has_beads,
        remote_url=remote_url,
        remote_name=remote_name,
        aliases=aliases,
    )


async def _get_remote_url(path: Path) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(path), "remote", "get-url", "origin",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode().strip() or None
    except Exception:
        pass
    return None


def _normalize(s: str) -> str:
    """Lowercase and replace underscores/spaces with hyphens."""
    return re.sub(r"[_\s]+", "-", s.strip().lower())


# Global registry — populated at startup
_registry: Optional[EnvironmentRegistry] = None


def get_registry() -> Optional[EnvironmentRegistry]:
    return _registry


def set_registry(registry: EnvironmentRegistry) -> None:
    global _registry
    _registry = registry
