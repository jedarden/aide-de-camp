# Registry.yaml Loading and Routing Mechanism

This document explains how `config/registry.yaml` is loaded, hot-reloaded, and used by the routing system in aide-de-camp.

## Registry.yaml Structure

`config/registry.yaml` is the central configuration file that defines:

```yaml
argocd:                    # ArgoCD read-only proxy configuration
  auth: none
  base_url: https://argocd-ro-ardenone-manager-ts.ardenone.com:8444

clusters:                  # Kubernetes cluster proxy endpoints
  cluster-name:
    proxy: http://traefik-cluster:8001
    type: proxy

global_aliases:            # Global project aliases (shortcut names)
  alias-name: project-slug

projects:                  # Project definitions
  project-slug:
    description: str
    aliases: list[str]     # Alternative names for project
    cluster: str | null    # Kubernetes cluster name
    namespace: str | null  # Kubernetes namespace
    repo_path: str | null  # Local git repo path
    argocd_app: str | null # ArgoCD application name
    intent_support: list[str]  # Supported intent types
    workflows:             # Workflow definitions
      workflow-name:
        steps: list[str]
```

### Example Project Entry

```yaml
aide-de-camp:
  aliases:
  - adc
  - aide-de-camp
  - this interface
  cluster: null
  description: aide-de-camp itself (this interface)
  intent_support:
  - status
  - self-modification
  - brainstorm
  namespace: null
  repo_path: /home/coding/aide-de-camp
  workflows:
    status:
      steps:
      - git_log
      - open_beads
```

## Loading Mechanism

### File Location
- **Path**: `config/registry.yaml` (relative to project root)
- **Constant**: `REGISTRY_PATH = Path(__file__).parent.parent / "config" / "registry.yaml"` (in `src/registry.py`)

### Two-Level Loading Strategy

The registry system uses a **merged loading strategy** that combines:

1. **YAML-defined projects** (from `registry.yaml`)
2. **Auto-discovered git repos** (scanned from `/home/coding`)

```python
def _build_registry() -> dict:
    # 1. Load YAML-defined projects
    raw = _load_yaml()
    yaml_projects = raw.get("projects", {})

    # 2. Discover git repos from root directory
    discovered = _discover_repos(DISCOVERY_ROOT)

    # 3. Merge with YAML taking precedence
    projects = _merge(discovered, yaml_projects)

    return {
        "projects": projects,
        "clusters": raw.get("clusters", {}),
        "argocd": raw.get("argocd", {}),
        "global_aliases": raw.get("global_aliases", {}),
    }
```

### Precedence Rule

**YAML entries always take precedence** over discovered entries:

```python
def _merge(discovered: dict, from_yaml: dict) -> dict:
    """
    PRECEDENCE RULE: YAML entries take precedence over discovered entries.
    Once an entry exists in registry.yaml (written by self-modification agent),
    it is never overwritten by discovery.
    """
    merged = dict(discovered)
    for slug, entry in from_yaml.items():
        if slug in merged:
            # YAML enriches the discovered entry - YAML values win
            base = dict(merged[slug])
            base.update({k: v for k, v in entry.items() if v is not None})
            # Merge aliases: union of both, deduplicated
            all_aliases = list(dict.fromkeys(
                discovered_aliases + yaml_aliases
            ))
            base["aliases"] = all_aliases
            merged[slug] = base
        else:
            # New YAML entry - add as-is
            merged[slug] = entry
    return merged
```

## Hot-Reload Mechanism

### TTL-Based Cache Invalidation

The registry uses a **5-minute TTL cache** with manual reload capability:

```python
CACHE_TTL = 300  # 5 minutes

_cache: dict | None = None      # Merged registry cache
_cache_at: float = 0            # Cache build timestamp

def get_registry(force: bool = False) -> dict:
    """
    Return merged registry with hot-reload support.

    Args:
        force: If True, bypass cache and rebuild immediately.

    Hot-reload behavior:
    - First call: builds registry from disk
    - Subsequent calls: return cached if within TTL (5 minutes)
    - After TTL: next call rebuilds from disk
    - force=True: immediate bypass and reload
    """
    global _cache, _cache_at
    if force or _cache is None or (time.time() - _cache_at) > CACHE_TTL:
        _cache = _build_registry()
        _cache_at = time.time()
    return _cache
```

### Hot-Reload Trigger Points

**Automatic (within 5 minutes):**
- Call `get_registry()` without arguments
- Cache expires after 300 seconds
- Next call rebuilds automatically

**Immediate (manual reload):**
- Call `get_registry(force=True)`
- Bypasses cache, rebuilds immediately
- Used in tests and manual reload triggers

### Alternative Mtime-Based Hot-Reload

A secondary hot-reload system exists in `src/components/hot_reload.py`:

```python
class HotReloadManager:
    CHECK_INTERVAL = 1.0  # Seconds between mtime checks

    def register_config(self, name: str, path: str):
        """Register config for mtime-based hot-reload."""
        # Tracks file modification time
        # Reloads when mtime changes

    def get_config(self, name: str) -> Any:
        """Get config, reloading if mtime changed."""
        self._check_and_reload(name)
        return self._cache[name]
```

This system is **currently used for prompts** but registry.yaml is also registered:

```python
_reload_manager = HotReloadManager()
_reload_manager.register_config('registry', 'config/registry.yaml')
```

**Note**: The TTL-based cache in `src/registry.py` is the primary mechanism for registry hot-reload.

## Usage in Routing System

### Entry Points

The routing system uses registry functions in several places:

#### 1. Project Resolution (src/intent/router.py)

```python
from ..registry import get_registry, get_project

# Resolve project slug to repo path and cluster config
registry = get_registry()
if registry and classification.project_slug:
    entry = registry.lookup(classification.project_slug)
    if entry:
        repo_path = str(entry.path)
        ssh_target = entry.ssh_target
        cluster = entry.cluster
        # ... use for fetch context
```

#### 2. Project Configuration (src/intent/router.py)

```python
# Get project config for cluster/namespace/argocd_app
project_cfg = get_project(classification.project_slug)

fetch_request = FetchRequest(
    context=FetchContext(
        cluster=project_cfg.get("cluster"),
        namespace=project_cfg.get("namespace"),
        app_name=project_cfg.get("argocd_app"),
    )
)
```

#### 3. Intent Type Support (src/fetch/commands.py)

Project's `intent_support` field determines which fetch commands to run:

```yaml
projects:
  pbx-web:
    intent_support:
    - status      # Will run STATUS fetch commands
    - lookup      # Will run LOOKUP fetch commands
    - brainstorm  # Will run BRAINSTORM fetch commands
```

#### 4. Aliases for Routing

The router uses project aliases to match user utterances to projects:

```yaml
global_aliases:
  prod: options-pipeline      # User says "check prod" → routes to options-pipeline
  staging: options-pipeline

projects:
  pbx-web:
    aliases:
    - pbx                      # User says "check pbx" → routes to pbx-web
    - phone system
    - telephony
```

### Routing Flow

1. **Utterance Classification**: Router classifies utterance into intent + project_slug
2. **Registry Lookup**: `get_project(project_slug)` retrieves project config
3. **Context Building**: Project config (cluster, namespace, repo_path) used to build fetch context
4. **Fetch Execution**: Context variables expanded into command templates
5. **Result Synthesis**: Fetched data synthesized into structured result

## Files and Functions

### Core Registry Module (`src/registry.py`)

**Functions:**
- `get_registry(force=False)` - Main entry point, returns merged registry
- `get_project(slug)` - Get single project entry from registry
- `repo_path_for(slug)` - Convenience function to get repo path
- `projects_summary()` - One-line-per-project summary for LLM prompts

**Internal Functions:**
- `_build_registry()` - Merge YAML + discovered repos
- `_load_yaml()` - Load YAML from disk
- `_discover_repos(root)` - Scan for git repos
- `_merge(discovered, from_yaml)` - Merge with YAML precedence
- `_validate_registry(registry)` - Schema validation

### Intent Router (`src/intent/router.py`)

**Usage points:**
- `process_intent()` - Calls `get_registry()` and `get_project()`
- `_fetch_and_synthesize()` - Builds fetch context from project config
- Intent classification uses project aliases for routing

### Fetch Commands (`src/fetch/commands.py`)

**Usage points:**
- `get_effective_timeout()` - Uses registry for project-specific timeouts
- Fetch context uses cluster/namespace from project config

### Hot-Reload Manager (`src/components/hot_reload.py`)

**Functions:**
- `get_reload_manager()` - Get singleton hot-reload manager
- `HotReloadManager.register_config()` - Register config for mtime tracking
- `HotReloadManager.get_config()` - Get config with auto-reload

### Validation Module (`src/registry.py`)

**Functions:**
- `_validate_registry()` - Validate entire registry schema
- `_validate_project_entry()` - Validate single project entry
- `RegistryValidationError` - Exception for schema violations

## Hot-Reload Support: YES

**Current Status**: **YES - Full hot-reload support**

The registry.yaml configuration supports hot-reload through two mechanisms:

### 1. TTL-Based Cache (Primary)

- **Cache Duration**: 5 minutes (300 seconds)
- **Trigger**: Time-based expiry or manual `force=True`
- **Verification**: `test_registry_hot_reload()` in `tests/test_config_hot_reload.py`
- **No Server Restart Required**: Changes take effect within 5 minutes or immediately with `force=True`

### 2. Mtime-Based Cache (Secondary)

- **Check Interval**: 1 second
- **Trigger**: File modification time change
- **Implementation**: `HotReloadManager` in `src/components/hot_reload.py`
- **Also Supports Hot-Reload**: Registered configs reload when mtime changes

### Test Coverage

**Test**: `test_registry_hot_reload()` (tests/test_config_hot_reload.py)

This test verifies:
1. Initial registry load and baseline state
2. Utterance routing with existing aliases
3. YAML file modification (alias rename)
4. Cache reload with `get_registry(force=True)`
5. Routing with new aliases
6. Automatic cleanup via `backup_registry` fixture

**Test Pattern**:
```python
# 1. Load initial state
initial_config = load_registry_config()

# 2. Modify registry.yaml
modify_registry_alias("old", "new")

# 3. Force reload
reloaded = get_registry(force=True)

# 4. Verify new state
assert "new" in reloaded["projects"]["project"]["aliases"]
```

## Schema Validation

The registry enforces schema validation on load:

### Required Fields
- `description: str`
- `aliases: list[str]`
- `intent_support: list[str]`

### Optional Fields (nullable)
- `cluster: str | null`
- `namespace: str | null`
- `repo_path: str | null`
- `argocd_app: str | null`

### Validation Rules
- Aliases must be non-empty strings
- Intent types must be from known set
- `sla_hours` (if present) must be positive number

### Error Handling

```python
try:
    registry = get_registry(force=True)
except RegistryValidationError as e:
    # e.errors contains list of validation messages
    for error in e.errors:
        print(f"  - {error}")
```

## Auto-Discovery Mechanism

The registry automatically discovers git repos from `/home/coding`:

```python
DISCOVERY_ROOT = Path("/home/coding")

def _discover_repos(root: Path) -> dict[str, dict]:
    """Scan root for git repos, return slug → entry dict."""
    repos = {}
    for entry in os.scandir(root):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if not (Path(entry.path) / ".git").exists():
            continue
        slug = _slug(entry.name)
        repos[slug] = {
            "repo_path": str(Path(entry.path)),
            "description": _read_description(Path(entry.path)),
            "aliases": [entry.name.lower()],
            "cluster": None,
            "namespace": None,
            "intent_support": ["status", "lookup", "brainstorm", "task-profile"],
        }
    return repos
```

**Discovery Behavior**:
- Scans `/home/coding` for `.git` directories
- Generates project slug from directory name
- Reads first line of README.md for description
- Provides default aliases and intent support
- **Never overwrites YAML-defined entries**

## Summary

**Hot-Reload Support**: ✅ YES (TTL-based + mtime-based)

**Cache Duration**: 5 minutes (TTL) or 1 second (mtime check interval)

**Manual Reload**: `get_registry(force=True)`

**No Server Restart Required**: Configuration changes take effect automatically

**Test Coverage**: `test_registry_hot_reload()` in `tests/test_config_hot_reload.py`

**Entry Points**:
- `get_registry()` - Get full merged registry
- `get_project(slug)` - Get single project entry
- `HotReloadManager.get_config('registry')` - Mtime-based reload

**Routing Integration**:
- Intent router uses `get_project()` for context building
- Project aliases used for utterance-to-project routing
- Cluster/namespace from project config used in fetch commands
