"""
Project registry: merges YAML config with auto-discovered git repos.

Discovery scans a root path for git repos and generates project entries for each.
YAML entries override/enrich auto-discovered ones (cluster, namespace, aliases, etc.).

Cached with a 5-minute TTL so the router picks up new repos without restart.
"""

import os
import time
from pathlib import Path
from typing import Any

import yaml


REGISTRY_PATH = Path(__file__).parent.parent / "config" / "registry.yaml"
DISCOVERY_ROOT = Path("/home/coding")
CACHE_TTL = 300  # 5 minutes

_cache: dict | None = None
_cache_at: float = 0


def _slug(name: str) -> str:
    return name.lower().replace("_", "-").replace(" ", "-")


def _read_description(repo_path: Path) -> str:
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


def _load_yaml() -> dict:
    try:
        return yaml.safe_load(REGISTRY_PATH.read_text()) or {}
    except OSError:
        return {}


def _merge(discovered: dict, from_yaml: dict) -> dict:
    """Merge discovered repos with YAML registry. YAML wins on conflicts."""
    merged = dict(discovered)
    for slug, entry in from_yaml.items():
        if slug in merged:
            # YAML enriches the discovered entry
            base = dict(merged[slug])
            base.update({k: v for k, v in entry.items() if v is not None})
            # Merge aliases without duplicates
            all_aliases = list(dict.fromkeys(
                base.get("aliases", []) + entry.get("aliases", [])
            ))
            base["aliases"] = all_aliases
            merged[slug] = base
        else:
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

    return {
        "projects": projects,
        "clusters": raw.get("clusters", {}),
        "argocd": raw.get("argocd", {}),
        "global_aliases": raw.get("global_aliases", {}),
    }


def get_registry(force: bool = False) -> dict:
    """Return the merged registry, rebuilding if cache is stale."""
    global _cache, _cache_at
    if force or _cache is None or (time.time() - _cache_at) > CACHE_TTL:
        _cache = _build_registry()
        _cache_at = time.time()
    return _cache


def get_project(slug: str) -> dict | None:
    return get_registry()["projects"].get(slug)


def repo_path_for(slug: str) -> str | None:
    p = get_project(slug)
    return p.get("repo_path") if p else None


def projects_summary() -> str:
    """One-line-per-project summary for the LLM router prompt."""
    lines = []
    for slug, entry in get_registry()["projects"].items():
        aliases = entry.get("aliases", [])
        desc = entry.get("description", "")
        cluster = entry.get("cluster") or "local"
        alias_str = f" (aliases: {', '.join(aliases[:3])})" if aliases else ""
        lines.append(f"- {slug}{alias_str} [{cluster}]: {desc}")
    return "\n".join(lines)
