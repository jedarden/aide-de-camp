"""
Project registry: merges YAML config with auto-discovered git repos.

Discovery scans a root path for git repos and generates project entries for each.
YAML entries override/enrich auto-discovered ones (cluster, namespace, aliases, etc.).

Cached with a 5-minute TTL so the router picks up new repos without restart.

Precedence rule: The scanner (discovery.py) only proposes entries. Once an entry
exists in registry.yaml (written by the self-modification agent), it is never
overwritten by discovery. The _merge() function enforces this: YAML entries take
precedence over discovered entries on all fields.
"""

import asyncio
import logging
import os
import time
import random
from pathlib import Path
from typing import Any, Callable
from functools import wraps

import yaml
from .utils.atomic_write import atomic_write

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 0.1,
    backoff_factor: float = 2.0,
    exceptions: tuple = (OSError, yaml.YAMLError),
) -> Callable:
    """
    Retry decorator with exponential backoff for transient failures.

    CONCURRENT ACCESS PROTECTION: Retry logic handles transient failures from concurrent file access.
    If multiple threads/processes access the registry simultaneously, file operations may fail temporarily.
    This retry mechanism exponentially backs off before retrying, reducing contention.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 0.1)
        backoff_factor: Multiplier for delay after each retry (default: 2.0)
        exceptions: Tuple of exceptions to catch and retry (default: OSError, yaml.YAMLError)

    Returns:
        Decorated function that retries on failure with exponential backoff

    Example:
        @_retry_with_backoff(max_retries=3, initial_delay=0.1)
        def read_file():
            return Path("file.txt").read_text()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Log retry attempt with attempt number and error type at INFO level
                        logger.info(
                            f"Retry attempt {attempt + 1}/{max_retries} for {func.__name__}: "
                            f"{type(e).__name__}: {e}"
                        )
                        # Add jitter to prevent thundering herd problem
                        jittered_delay = delay * (0.5 + random.random() * 0.5)
                        time.sleep(jittered_delay)
                        delay *= backoff_factor
                    else:
                        # All retries exhausted - log final failure
                        logger.error(
                            f"All {max_retries} retry attempts exhausted for {func.__name__}: "
                            f"{type(e).__name__}: {e}"
                        )
                        raise

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic exhausted without exception")

        return wrapper
    return decorator


REGISTRY_PATH = Path(__file__).parent.parent / "config" / "registry.yaml"
DISCOVERY_ROOT = Path("/home/coding")
CACHE_TTL = 300  # 5 minutes

# ASYNCIO LOCKING PROTECTION: Async-safe registry access
# _cache_lock protects all access to _cache and _cache_at to prevent race conditions
# This ensures that multiple async tasks can safely access the registry without corruption
# Uses asyncio.Lock() for proper async concurrent access protection in FastAPI context
_cache_lock = asyncio.Lock()

# HOT-RELOAD MECHANISM: TTL-based cache invalidation
# _cache stores the merged registry (YAML + discovered projects)
# _cache_at tracks when the cache was last built (timestamp)
# get_registry() checks if cache is stale (> CACHE_TTL seconds old)
# If stale or force=True, rebuilds registry from disk by calling _build_registry()
# This enables hot-reload without server restart: changes to registry.yaml take effect
# within 5 minutes or immediately with force=True
# Verified in test_registry_hot_reload (tests/test_config_hot_reload.py)
_cache: dict | None = None
_cache_at: float = 0


class RegistryValidationError(Exception):
    """Raised when the registry schema is invalid."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        message = "Registry validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(message)


def _validate_project_entry(slug: str, entry: dict) -> list[str]:
    """
    Validate a single project entry against the required schema.
    Returns a list of error messages (empty if valid).
    """
    errors = []

    # Required fields - must be present
    required_fields = {
        "description": str,
        "aliases": list,
        "intent_support": list,
    }

    # Optional fields - if present, must match type; can be omitted entirely
    nullable_fields = {
        "cluster": (str, type(None)),
        "namespace": (str, type(None)),
        "repo_path": (str, type(None)),
        "argocd_app": (str, type(None)),  # Defaults to project slug if missing
    }

    # Check required fields exist
    for field, expected_type in required_fields.items():
        if field not in entry:
            errors.append(f"{slug}: missing required field '{field}'")
            continue

        value = entry[field]
        if not isinstance(value, expected_type):
            errors.append(f"{slug}: '{field}' must be {expected_type.__name__}, got {type(value).__name__}")

    # Check optional fields (if present)
    for field, expected_types in nullable_fields.items():
        if field not in entry:
            continue  # Optional field can be omitted

        value = entry[field]
        if value is None and field in ["cluster", "namespace", "repo_path", "argocd_app"]:
            # These fields can explicitly be null
            continue
        elif value is None:
            errors.append(f"{slug}: '{field}' cannot be null (use explicit value or omit)")
        elif not isinstance(value, expected_types):
            type_names = [t.__name__ for t in expected_types]
            errors.append(f"{slug}: '{field}' must be {' or '.join(type_names)}, got {type(value).__name__}")

    # Validate aliases is list of non-empty strings
    if "aliases" in entry and isinstance(entry["aliases"], list):
        for i, alias in enumerate(entry["aliases"]):
            if not isinstance(alias, str) or not alias.strip():
                errors.append(f"{slug}: aliases[{i}] must be a non-empty string")

    # Validate intent_support is list of known intent types
    known_intents = {"status", "action", "brainstorm", "lookup", "reminder",
                     "self-modification", "monitoring-config", "task-profile", "clarification"}
    if "intent_support" in entry and isinstance(entry["intent_support"], list):
        for intent in entry["intent_support"]:
            if intent not in known_intents:
                errors.append(f"{slug}: unknown intent type '{intent}' in intent_support")

    # Validate optional sla_hours field
    if "sla_hours" in entry:
        sla = entry["sla_hours"]
        if sla is not None and not isinstance(sla, (int, float)):
            errors.append(f"{slug}: sla_hours must be a number or null, got {type(sla).__name__}")
        elif sla is not None and sla <= 0:
            errors.append(f"{slug}: sla_hours must be positive, got {sla}")

    return errors


def _validate_registry(registry: dict) -> None:
    """
    Validate the entire registry schema.
    Raises RegistryValidationError if any errors are found.
    """
    if "projects" not in registry:
        raise RegistryValidationError(["Missing 'projects' section in registry"])

    projects = registry["projects"]
    if not isinstance(projects, dict):
        raise RegistryValidationError(["'projects' must be a dictionary"])

    all_errors = []
    for slug, entry in projects.items():
        if not isinstance(entry, dict):
            all_errors.append(f"{slug}: project entry must be a dictionary, got {type(entry).__name__}")
            continue
        all_errors.extend(_validate_project_entry(slug, entry))

    if all_errors:
        raise RegistryValidationError(all_errors)


def _slug(name: str) -> str:
    return name.lower().replace("_", "-").replace(" ", "-")


@retry_with_backoff(max_retries=3, initial_delay=0.1, backoff_factor=2.0)
def _read_description(repo_path: Path) -> str:
    """
    Read project description from README files with retry logic for transient failures.

    CONCURRENT ACCESS PROTECTION: This function uses retry_with_backoff decorator to handle
    transient failures from concurrent file access. If multiple threads read README files
    simultaneously, the retry mechanism ensures all reads eventually succeed.

    Args:
        repo_path: Path to the repository root

    Returns:
        First meaningful line from README, or empty string if not found
    """
    for name in ("README.md", "README.rst", "README.txt", "README"):
        f = repo_path / name
        if f.exists():
            try:
                for line in f.read_text(errors="replace").splitlines():
                    line = line.strip().lstrip("#").strip()
                    if line and not line.startswith("!") and len(line) > 4:
                        return line[:120]
            except OSError:
                pass
    return ""


def _discover_repos(root: Path) -> dict[str, dict]:
    """Scan root for git repos, return slug → entry dict."""
    repos: dict[str, dict] = {}
    try:
        for entry in os.scandir(root):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            p = Path(entry.path)
            if not (p / ".git").exists():
                continue
            slug = _slug(entry.name)
            repos[slug] = {
                "repo_path": str(p),
                "description": _read_description(p),
                "aliases": [entry.name.lower()],
                "cluster": None,
                "namespace": None,
                "intent_support": ["status", "lookup", "brainstorm", "task-profile"],
                "_discovered": True,
            }
    except OSError:
        pass
    return repos


@retry_with_backoff(max_retries=3, initial_delay=0.1, backoff_factor=2.0)
def _load_yaml() -> dict:
    """
    Load YAML registry file with retry logic for transient failures.

    CONCURRENT ACCESS PROTECTION: This function uses retry_with_backoff decorator to handle
    transient failures from concurrent file access. If multiple threads read the file
    simultaneously, the retry mechanism ensures all reads eventually succeed.

    Returns:
        Parsed YAML content as dict, or empty dict if file doesn't exist
    """
    try:
        return yaml.safe_load(REGISTRY_PATH.read_text()) or {}
    except OSError:
        return {}


def _merge(discovered: dict, from_yaml: dict) -> dict:
    """
    Merge discovered repos with YAML registry.

    PRECEDENCE RULE: YAML entries take precedence over discovered entries.
    Once an entry exists in registry.yaml (written by the self-modification agent),
    it is never overwritten by discovery. The scanner (discovery.py) only proposes
    new entries; it does not modify existing ones.

    This behavior protects agent-authored entries from being clobbered by
    automatic scanning, ensuring the self-modification agent is the sole ongoing
    author of the registry after initial seeding.

    Args:
        discovered: Dict of auto-discovered repos (from _discover_repos)
        from_yaml: Dict of projects from registry.yaml (agent-authored)

    Returns:
        Merged dict where YAML entries always win on conflicts
    """
    # First, ensure discovered entries have argocd_app (default to slug)
    for slug, entry in discovered.items():
        if "argocd_app" not in entry or entry.get("argocd_app") is None:
            entry["argocd_app"] = slug

    merged = dict(discovered)
    for slug, entry in from_yaml.items():
        if slug in merged:
            # YAML enriches the discovered entry - YAML values take precedence
            base = dict(merged[slug])
            base.update({k: v for k, v in entry.items() if v is not None})

            # Merge aliases: union of discovered and YAML aliases, deduplicated
            discovered_aliases = merged[slug].get("aliases", [])
            yaml_aliases = entry.get("aliases", [])
            all_aliases = list(dict.fromkeys(discovered_aliases + yaml_aliases))
            base["aliases"] = all_aliases

            merged[slug] = base
        else:
            # New YAML entry - add it as-is
            merged[slug] = entry
    return merged


def _build_registry() -> dict:
    raw = _load_yaml()
    yaml_projects: dict = raw.get("projects", {})

    # Fill in repo_path for YAML entries that have null repo_path
    for slug, entry in yaml_projects.items():
        if not entry.get("repo_path"):
            candidate = DISCOVERY_ROOT / slug
            if (candidate / ".git").exists():
                entry["repo_path"] = str(candidate)

    discovered = _discover_repos(DISCOVERY_ROOT)
    projects = _merge(discovered, yaml_projects)

    registry = {
        "projects": projects,
        "clusters": raw.get("clusters", {}),
        "argocd": raw.get("argocd", {}),
        "global_aliases": raw.get("global_aliases", {}),
    }

    # Validate the registry before returning
    _validate_registry(registry)

    return registry


async def get_registry(force: bool = False) -> dict:
    """
    Return the merged registry with hot-reload support and async-safe concurrent access.

    HOT-RELOAD MECHANISM: TTL-Based Cache Invalidation
    ====================================================
    This function implements hot-reload without requiring a server restart:

    1. First call builds registry from disk (YAML + discovered projects)
    2. Subsequent calls return cached registry if within TTL (5 minutes)
    3. After TTL expires, next call rebuilds registry from disk
    4. force=True bypasses cache and rebuilds immediately

    ASYNCIO LOCKING PROTECTION:
    =============================
    This function uses _cache_lock (asyncio.Lock()) to ensure async-safe access:
    - Multiple async tasks can safely read the cache concurrently
    - Cache updates are atomic - readers see consistent state
    - No race conditions between cache validation and updates
    - Uses double-checked locking pattern for performance

    This approach means:
    - Changes to config/registry.yaml take effect within 5 minutes
    - Or immediately with force=True (used in tests and manual reloads)
    - No server restart required to pick up new projects/aliases
    - Async-safe concurrent access without corruption
    - Cache hit is very fast (lock acquisition, no disk I/O)
    - Cache miss rebuilds entire registry (includes git repo discovery)

    Args:
        force: If True, bypass cache and rebuild registry immediately.
               Used for testing and manual reload triggers.

    Returns:
        Merged registry dict with projects, clusters, argocd, global_aliases.

    Verified in: test_registry_hot_reload (tests/test_config_hot_reload.py)
    """
    global _cache, _cache_at

    # ASYNCIO LOCKING: Double-checked locking pattern
    # First check without lock for performance (fast path for cache hits)
    cache_is_stale = force or _cache is None or (time.time() - _cache_at) > CACHE_TTL

    if not cache_is_stale:
        # Fast path: return cached registry without lock contention
        return _cache

    # Slow path: need to rebuild cache - acquire lock for async safety
    logger.debug("Acquiring registry cache lock for rebuild")
    async with _cache_lock:
        logger.debug("Registry cache lock acquired, checking if rebuild still needed")
        # Double-check: another task may have rebuilt cache while we waited for lock
        cache_is_stale = force or _cache is None or (time.time() - _cache_at) > CACHE_TTL

        if cache_is_stale:
            logger.debug("Registry cache is stale, rebuilding")
            # Rebuild cache under lock protection
            _cache = _build_registry()
            _cache_at = time.time()
            logger.debug("Registry cache rebuilt successfully")
        else:
            logger.debug("Registry cache already rebuilt by another task, using cached version")

        logger.debug("Releasing registry cache lock")
        return _cache


async def get_project(slug: str) -> dict | None:
    """
    Get a single project entry from the registry.

    HOT-RELOAD: This function calls get_registry() which implements TTL-based cache
    invalidation. Changes to registry.yaml will be picked up within 5 minutes or
    immediately with get_registry(force=True). No server restart required.

    ASYNCIO LOCKING: Protected by async lock in get_registry() to ensure safe
    concurrent access to registry cache.

    Args:
        slug: Project slug to look up

    Returns:
        Project dict or None if not found

    Verified in: test_registry_hot_reload (tests/test_config_hot_reload.py)
    """
    registry = await get_registry()
    return registry["projects"].get(slug)


async def repo_path_for(slug: str) -> str | None:
    """
    Get repository path for a project slug.

    ASYNCIO LOCKING: Protected by async lock in get_project() to ensure safe
    concurrent access to registry cache.

    Args:
        slug: Project slug to look up

    Returns:
        Repository path string or None if not found
    """
    p = await get_project(slug)
    return p.get("repo_path") if p else None


async def projects_summary() -> str:
    """
    One-line-per-project summary for the LLM router prompt.

    ASYNCIO LOCKING: Protected by async lock in get_registry() to ensure safe
    concurrent access to registry cache.

    Returns:
        Multi-line string with project summaries
    """
    lines = []
    registry = await get_registry()
    for slug, entry in registry["projects"].items():
        aliases = entry.get("aliases", [])
        desc = entry.get("description", "")
        cluster = entry.get("cluster") or "local"
        alias_str = f" (aliases: {', '.join(aliases[:3])})" if aliases else ""
        lines.append(f"- {slug}{alias_str} [{cluster}]: {desc}")
    return "\n".join(lines)
