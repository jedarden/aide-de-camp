"""
Environment discovery: scans /home/coding/ for git repos and bead workspaces.

Builds a live registry at startup covering both the local machine and
known remote hosts (lab server). Automatically reflects whatever is
actually deployed, no config file required.
"""
import asyncio
import re
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path
from typing import Optional

logger = getLogger(__name__)

HOME = Path("/home/coding")

# Remote hosts to scan in addition to localhost
REMOTE_HOSTS: list[dict] = [
    {"alias": "lab", "host": "100.81.129.38", "user": "coding", "home": "/home/coding"},
]


@dataclass
class RepoEntry:
    """A discovered git repository."""
    path: Path
    name: str           # directory name, preserved case
    slug: str           # normalized: lowercase, underscores → hyphens
    has_beads: bool     # .beads/issues.jsonl exists
    host: str | None = None        # None = local; "lab" = remote lab server
    ssh_target: str | None = None  # e.g. "coding@100.81.129.38" for remote
    remote_url: str | None = None
    remote_name: str | None = None
    aliases: list[str] = field(default_factory=list)

    @property
    def is_remote(self) -> bool:
        return self.host is not None

    @property
    def display_path(self) -> str:
        if self.host:
            return f"{self.ssh_target}:{self.path}"
        return str(self.path)

    def __repr__(self) -> str:
        loc = f"@{self.host}" if self.host else "local"
        beads = " [beads]" if self.has_beads else ""
        return f"RepoEntry({self.slug}{beads} {loc}:{self.path})"


class EnvironmentRegistry:
    """
    Registry of all git repos discovered across local and remote machines.

    Keyed by normalized slug with alias support so project_slug values
    from LLM classification (e.g. "options-pipeline", "needle", "NEEDLE")
    all resolve to the right entry regardless of where it lives.
    """

    def __init__(self, repos: dict[str, RepoEntry]):
        self._repos = repos
        self._entries = list({id(e): e for e in repos.values()}.values())

    def lookup(self, project_slug: str) -> RepoEntry | None:
        """
        Resolve a project slug to a repo entry.

        Matching order:
        1. Exact slug match
        2. Prefix / suffix match
        3. Significant word overlap (≥1 non-stopword)
        """
        if not project_slug:
            return None

        normalized = _normalize(project_slug)

        if normalized in self._repos:
            return self._repos[normalized]

        for slug, entry in self._repos.items():
            if slug.startswith(normalized) or normalized.startswith(slug):
                return entry

        query_words = set(normalized.split("-")) - {"the", "a", "an", "of", "for"}
        best: tuple[int, RepoEntry | None] = (0, None)
        for slug, entry in self._repos.items():
            overlap = len(query_words & set(slug.split("-")))
            if overlap > best[0]:
                best = (overlap, entry)
        if best[0] >= 1:
            return best[1]

        return None

    def all_entries(self) -> list[RepoEntry]:
        return self._entries

    def local_entries(self) -> list[RepoEntry]:
        return [e for e in self._entries if not e.is_remote]

    def remote_entries(self) -> list[RepoEntry]:
        return [e for e in self._entries if e.is_remote]

    def beaded_entries(self) -> list[RepoEntry]:
        return [e for e in self._entries if e.has_beads]

    def summary(self) -> dict:
        local = self.local_entries()
        remote = self.remote_entries()
        hosts = sorted({e.host for e in remote if e.host})
        return {
            "total_repos": len(self._entries),
            "beaded_repos": len(self.beaded_entries()),
            "local_repos": len(local),
            "remote_repos": len(remote),
            "remote_hosts": hosts,
            "slugs": sorted(e.slug for e in self._entries),
        }


async def scan_environment(base: Path = HOME) -> EnvironmentRegistry:
    """
    Scan local home directory and all configured remote hosts.
    Merges results into a single registry. Remote-only repos are added
    without overwriting local entries with the same slug.
    """
    # Local scan
    local_task = _scan_local(base)
    # Remote scans (run concurrently, failures are non-fatal)
    remote_tasks = [_scan_remote(**h) for h in REMOTE_HOSTS]

    local_repos, *remote_results = await asyncio.gather(
        local_task, *remote_tasks, return_exceptions=True
    )

    repos: dict[str, RepoEntry] = {}

    # Register local repos first (they take priority over remote on slug conflicts)
    if isinstance(local_repos, dict):
        repos.update(local_repos)
        local_count = len({id(e) for e in local_repos.values()})
    else:
        logger.error(f"Local scan failed: {local_repos}")
        local_count = 0

    remote_count = 0
    for result in remote_results:
        if isinstance(result, Exception):
            logger.warning(f"Remote scan failed: {result}")
            continue
        for slug, entry in result.items():
            if slug not in repos:   # don't shadow a local repo with the same slug
                repos[slug] = entry
                remote_count += 1

    registry = EnvironmentRegistry(repos)
    s = registry.summary()
    logger.info(
        f"Environment scan complete: {s['total_repos']} repos total "
        f"({s['local_repos']} local, {s['remote_repos']} remote across {s['remote_hosts']}), "
        f"{s['beaded_repos']} with beads"
    )
    return registry


async def _scan_local(base: Path) -> dict[str, RepoEntry]:
    """Scan local home directory for git repos."""
    logger.info(f"Scanning local {base}...")
    tasks = []
    try:
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and not entry.name.startswith(".") and (entry / ".git").is_dir():
                tasks.append(_build_local_entry(entry))
    except PermissionError as e:
        logger.warning(f"Cannot read {base}: {e}")
        return {}

    results = await asyncio.gather(*tasks, return_exceptions=True)
    repos: dict[str, RepoEntry] = {}
    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"Error building local entry: {result}")
            continue
        for alias in result.aliases:
            if alias not in repos:
                repos[alias] = result
    return repos


async def _scan_remote(alias: str, host: str, user: str, home: str) -> dict[str, RepoEntry]:
    """
    Scan a remote host via SSH. Runs a single compound command to list
    git repos and check for .beads workspaces — one SSH connection total.
    """
    logger.info(f"Scanning remote {alias} ({user}@{host})...")
    ssh_target = f"{user}@{host}"

    # One SSH call: print "path|has_beads|remote_url" for each git repo
    script = (
        'for d in ' + home + '/*/; do '
        '  if [ -d "$d/.git" ]; then '
        '    beads=0; [ -f "$d/.beads/issues.jsonl" ] && beads=1; '
        '    url=$(git -C "$d" remote get-url origin 2>/dev/null || echo ""); '
        '    printf "%s|%s|%s\\n" "$d" "$beads" "$url"; '
        '  fi; '
        'done'
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
            ssh_target, script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
    except asyncio.TimeoutError:
        logger.warning(f"SSH scan of {alias} timed out")
        return {}
    except Exception as e:
        logger.warning(f"SSH scan of {alias} failed: {e}")
        return {}

    if proc.returncode != 0:
        logger.warning(f"SSH scan of {alias} returned {proc.returncode}: {stderr.decode()[:200]}")
        return {}

    repos: dict[str, RepoEntry] = {}
    for line in stdout.decode().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        raw_path = parts[0].rstrip("/")
        has_beads = parts[1] == "1"
        remote_url = parts[2].strip() if len(parts) > 2 else None

        name = raw_path.split("/")[-1]
        slug = _normalize(name)
        remote_name = None
        if remote_url:
            remote_name = _normalize(remote_url.rstrip("/").split("/")[-1].replace(".git", ""))

        aliases = list({slug, remote_name} - {None, ""})
        entry = RepoEntry(
            path=Path(raw_path),
            name=name,
            slug=slug,
            has_beads=has_beads,
            host=alias,
            ssh_target=ssh_target,
            remote_url=remote_url or None,
            remote_name=remote_name,
            aliases=aliases,
        )
        for a in aliases:
            if a not in repos:
                repos[a] = entry

    logger.info(f"Remote {alias}: found {len({id(e) for e in repos.values()})} repos")
    return repos


async def _build_local_entry(path: Path) -> RepoEntry:
    name = path.name
    slug = _normalize(name)
    has_beads = (path / ".beads" / "issues.jsonl").exists()
    remote_url = await _get_local_remote_url(path)

    remote_name = None
    if remote_url:
        remote_name = _normalize(remote_url.rstrip("/").split("/")[-1].replace(".git", ""))

    aliases = list({slug, remote_name} - {None, ""})
    return RepoEntry(
        path=path,
        name=name,
        slug=slug,
        has_beads=has_beads,
        host=None,
        ssh_target=None,
        remote_url=remote_url,
        remote_name=remote_name,
        aliases=aliases,
    )


async def _get_local_remote_url(path: Path) -> str | None:
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
    return re.sub(r"[_\s]+", "-", s.strip().lower())


# Global registry — populated at startup
_registry: Optional[EnvironmentRegistry] = None


def get_registry() -> Optional[EnvironmentRegistry]:
    return _registry


def set_registry(registry: EnvironmentRegistry) -> None:
    global _registry
    _registry = registry
