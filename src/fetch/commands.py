"""
Fetch command matrix: defines what to fetch per intent type.

Each intent type has a specific set of sources to query, with their
corresponding commands and timeout settings.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class IntentType(Enum):
    """Intent types that require fetch operations."""
    STATUS = "status"
    ACTION = "action"
    BRAINSTORM = "brainstorm"
    LOOKUP = "lookup"
    LOOKUP_LOGS = "lookup:logs"  # Lookup intent with lookup_kind=logs
    LOOKUP_CONFIG = "lookup:config"  # Lookup intent with lookup_kind=config
    LOOKUP_DOCS = "lookup:docs"  # Lookup intent with lookup_kind=docs
    REMINDER = "reminder"
    SELF_MODIFICATION = "self-modification"
    MONITORING_CONFIG = "monitoring-config"
    TASK_PROFILE = "task-profile"  # Escalate to NEEDLE bead for durable async handling
    STUCK = "stuck"  # Stuck intent - task blocked by circuit breaker


class FetchSource(Enum):
    """Data sources that can be fetched."""
    KUBECTL_PODS = "kubectl_pods"
    KUBECTL_DEPLOYMENTS = "kubectl_deployments"
    KUBECTL_WORKFLOWS = "kubectl_workflows"
    ARGOCD_APP = "argocd_app"
    GIT_LOG = "git_log"
    GIT_STATUS = "git_status"
    BEAD_LIST = "bead_list"
    BEAD_DETAILS = "bead_details"
    CI_STATUS = "ci_status"
    COMPONENTS = "components"
    LOGS = "logs"
    EVENTS = "events"
    SESSION_STATE = "session_state"
    TOPIC_CONTEXT = "topic_context"
    REMINDERS = "reminders"
    FS_EXPLORE = "fs_explore"      # list directory contents
    FS_README = "fs_readme"        # read README of a repo
    FS_HOME = "fs_home"            # overview of /home/coding/


# Kubernetes proxy endpoints by cluster
KUBECTL_PROXIES: dict[str, str] = {
    "apexalgo-iad": "http://traefik-apexalgo-iad:8001",
    "ardenone-cluster": "http://traefik-ardenone-cluster:8001",
    "ardenone-hub": "http://traefik-ardenone-hub:8001",
    "ardenone-manager": "http://traefik-ardenone-manager:8001",
    "rs-manager": "http://traefik-rs-manager:8001",
    "ord-devimprint": "http://kubectl-proxy-ord-devimprint:8001",
    "iad-kalshi": "http://kubectl-proxy-iad-kalshi:8001",
    "iad-native-ads": "http://traefik-iad-native-ads-1:8001",
    "iad-options": "http://traefik-iad-options:8001",
}

# Fetch configuration file path
FETCH_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "fetch.yaml"

# In-memory cache for fetch config
_fetch_config_cache: dict | None = None
_fetch_config_mtime: float = 0


class FetchConfigValidationError(Exception):
    """Raised when the fetch config schema is invalid."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        message = "Fetch config validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(message)


def _validate_timeout_ms(value: Any, source_name: str) -> int | None:
    """
    Validate a timeout_ms value.

    Args:
        value: The timeout value to validate
        source_name: Name of the source for error messages

    Returns:
        The validated timeout as int in seconds, or None if not specified

    Raises:
        FetchConfigValidationError: If the timeout value is invalid
    """
    if value is None:
        return None

    # Must be an integer or float that can be converted to int
    if not isinstance(value, (int, float)):
        raise FetchConfigValidationError([
            f"{source_name}: timeout_ms must be a number, got {type(value).__name__}"
        ])

    # Convert to seconds (timeout_ms is in milliseconds)
    timeout_seconds = int(value) / 1000

    # Must be positive
    if timeout_seconds <= 0:
        raise FetchConfigValidationError([
            f"{source_name}: timeout_ms must be positive, got {value}"
        ])

    return timeout_seconds


def _load_fetch_config() -> dict:
    """
    Load fetch configuration from YAML file.

    Returns:
        Dictionary with source timeouts. Empty dict if file not found or invalid.

    Raises:
        FetchConfigValidationError: If config schema is invalid
    """
    global _fetch_config_cache, _fetch_config_mtime

    # Check if we need to reload (file modified or not loaded yet)
    try:
        current_mtime = FETCH_CONFIG_PATH.stat().st_mtime
        if _fetch_config_cache is not None and current_mtime == _fetch_config_mtime:
            return _fetch_config_cache
    except OSError:
        # File doesn't exist or can't be accessed
        return {}

    # Load the YAML file
    try:
        config = yaml.safe_load(FETCH_CONFIG_PATH.read_text()) or {}
    except OSError:
        return {}  # File doesn't exist

    # Validate the config structure
    errors = []

    if "sources" in config:
        if not isinstance(config["sources"], dict):
            errors.append("'sources' must be a dictionary")
        else:
            # Validate each source timeout
            for source_name, timeout_config in config["sources"].items():
                if not isinstance(timeout_config, dict):
                    errors.append(f"sources.{source_name}: must be a dictionary, got {type(timeout_config).__name__}")
                    continue

                if "timeout_ms" in timeout_config:
                    try:
                        _validate_timeout_ms(timeout_config["timeout_ms"], f"sources.{source_name}")
                    except FetchConfigValidationError as e:
                        errors.extend(e.errors)

    if errors:
        raise FetchConfigValidationError(errors)

    # Cache the validated config
    _fetch_config_cache = config
    _fetch_config_mtime = current_mtime

    return config


def get_source_timeout_ms(source: FetchSource, project_slug: str | None = None) -> int | None:
    """
    Get the configured timeout (in seconds) for a fetch source.

    Checks the config file for timeout_ms value and converts to seconds.
    Priority order:
    1. Project-specific override (if project_slug provided)
    2. Global source-specific timeout
    3. None (use default from spec)

    Args:
        source: The fetch source to get timeout for
        project_slug: Optional project slug for project-specific overrides

    Returns:
        Timeout in seconds, or None if not configured

    Raises:
        FetchConfigValidationError: If config is invalid (on hot-reload)
    """
    try:
        config = _load_fetch_config()
    except FetchConfigValidationError:
        # On validation error, return None (use default) but log would be useful
        return None

    source_key = source.value  # Use enum value as key

    # Check for project-specific override FIRST (if provided)
    if project_slug:
        project_timeouts = config.get("project_timeouts", {})
        if project_slug in project_timeouts:
            project_config = project_timeouts[project_slug]
            if isinstance(project_config, dict) and source_key in project_config:
                source_override = project_config[source_key]
                if isinstance(source_override, dict) and "timeout_ms" in source_override:
                    timeout_ms = source_override["timeout_ms"]
                    if timeout_ms is not None:
                        return int(timeout_ms) / 1000

    # Check for global source-specific timeout
    sources_config = config.get("sources", {})
    if source_key in sources_config:
        source_config = sources_config[source_key]
        if "timeout_ms" in source_config:
            timeout_ms = source_config["timeout_ms"]
            if timeout_ms is not None:
                # Convert milliseconds to seconds
                return int(timeout_ms) / 1000

    # No timeout configured
    return None


def get_effective_timeout(spec: FetchCommandSpec, project_slug: str | None = None) -> int | float:
    """
    Get the effective timeout for a fetch command spec.

    Priority order:
    1. Project-specific timeout_ms from config file (if project_slug provided and set)
    2. Global timeout_ms from config file (if set)
    3. timeout_seconds from spec (default)
    4. No timeout (infinity) if neither is set

    Args:
        spec: The fetch command spec
        project_slug: Optional project slug for project-specific overrides

    Returns:
        Timeout in seconds, or float('inf') for no timeout
    """
    # Check config file first
    config_timeout = get_source_timeout_ms(spec.source, project_slug)
    if config_timeout is not None:
        return config_timeout

    # Fall back to spec's default
    if spec.timeout_seconds is not None:
        return spec.timeout_seconds

    # No timeout - use infinity
    return float('inf')


@dataclass
class FetchCommandSpec:
    """Specification for a single fetch command."""
    source: FetchSource
    command_template: str
    timeout_seconds: int = 5
    required: bool = False
    cacheable: bool = True
    timeout_ms: int | None = None  # Optional override from config/fetch.yaml


# Command matrix per intent type
FETCH_COMMAND_MATRIX: dict[IntentType, list[FetchCommandSpec]] = {
    IntentType.STATUS: [
        FetchCommandSpec(
            source=FetchSource.FS_EXPLORE,
            command_template="ls {repo_path}",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.FS_README,
            command_template="cat {repo_path}/README.md",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.KUBECTL_PODS,
            command_template="kubectl --server={proxy} get pods -n {namespace} -o json",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.ARGOCD_APP,
            command_template="curl -s {argocd_proxy}/api/v1/applications/{app_name}",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.GIT_LOG,
            command_template="git -C {repo_path} log -10 --oneline --pretty=format:'%h|%s|%an|%ar'",
            timeout_seconds=3,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.BEAD_LIST,
            command_template="bf list --status=open --limit=50",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.CI_STATUS,
            command_template="kubectl --server={proxy} get workflows -n argo-workflows -l project={project_slug} -o json",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
    ],

    IntentType.ACTION: [
        FetchCommandSpec(
            source=FetchSource.KUBECTL_PODS,
            command_template="kubectl --server={proxy} get pods -n {namespace} -o json",
            timeout_seconds=5,
            required=True,
            cacheable=False,  # Need fresh state for actions
        ),
        FetchCommandSpec(
            source=FetchSource.KUBECTL_DEPLOYMENTS,
            command_template="kubectl --server={proxy} get deployment {deployment} -n {namespace} -o json",
            timeout_seconds=5,
            required=True,
            cacheable=False,
        ),
        FetchCommandSpec(
            source=FetchSource.ARGOCD_APP,
            command_template="curl -s {argocd_proxy}/api/v1/applications/{app_name}",
            timeout_seconds=5,
            required=True,
            cacheable=False,
        ),
        FetchCommandSpec(
            source=FetchSource.GIT_STATUS,
            command_template="git -C {repo_path} status --short",
            timeout_seconds=3,
            required=False,
            cacheable=False,
        ),
        FetchCommandSpec(
            source=FetchSource.BEAD_LIST,
            command_template="bf list --status=open --limit=50",
            timeout_seconds=5,
            required=False,
            cacheable=False,
        ),
    ],

    IntentType.BRAINSTORM: [
        FetchCommandSpec(
            source=FetchSource.FS_EXPLORE,
            command_template="ls {repo_path}",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.FS_README,
            command_template="cat {repo_path}/README.md",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.COMPONENTS,
            command_template="components list --project {project_slug}",
            timeout_seconds=3,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.GIT_LOG,
            command_template="git -C {repo_path} log -10 --oneline",
            timeout_seconds=3,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.TOPIC_CONTEXT,
            command_template="topic context --topic {topic_id}",
            timeout_seconds=3,
            required=False,
            cacheable=True,
        ),
    ],

    IntentType.LOOKUP: [
        FetchCommandSpec(
            source=FetchSource.FS_HOME,
            command_template="ls /home/coding",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.FS_EXPLORE,
            command_template="ls {repo_path}",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.FS_README,
            command_template="cat {repo_path}/README.md",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.LOGS,
            command_template="kubectl --server={proxy} logs -n {namespace} {pod_name} --tail=100",
            timeout_seconds=10,
            required=False,
            cacheable=False,
        ),
        FetchCommandSpec(
            source=FetchSource.EVENTS,
            command_template="kubectl --server={proxy} get events -n {namespace} --sort-by='.lastTimestamp'",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.KUBECTL_PODS,
            command_template="kubectl --server={proxy} get pods -n {namespace} -o json",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
    ],

    # LOOKUP_LOGS: Recent log output and related diagnostics
    IntentType.LOOKUP_LOGS: [
        FetchCommandSpec(
            source=FetchSource.LOGS,
            command_template="kubectl --server={proxy} logs -n {namespace} {pod_name} --tail=100",
            timeout_seconds=10,
            required=False,
            cacheable=False,
        ),
        FetchCommandSpec(
            source=FetchSource.EVENTS,
            command_template="kubectl --server={proxy} get events -n {namespace} --sort-by='.lastTimestamp'",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.KUBECTL_PODS,
            command_template="kubectl --server={proxy} get pods -n {namespace} -o json",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
    ],

    # LOOKUP_CONFIG: Configuration and deployment state
    IntentType.LOOKUP_CONFIG: [
        FetchCommandSpec(
            source=FetchSource.ARGOCD_APP,
            command_template="curl -s {argocd_proxy}/api/v1/applications/{app_name}",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.KUBECTL_DEPLOYMENTS,
            command_template="kubectl --server={proxy} get deployment -n {namespace} -o json",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.KUBECTL_PODS,
            command_template="kubectl --server={proxy} get pods -n {namespace} -o json",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.GIT_LOG,
            command_template="git -C {repo_path} log -10 --oneline --pretty=format:'%h|%s|%an|%ar'",
            timeout_seconds=3,
            required=False,
            cacheable=True,
        ),
    ],

    # LOOKUP_DOCS: Documentation and project overview
    IntentType.LOOKUP_DOCS: [
        FetchCommandSpec(
            source=FetchSource.FS_HOME,
            command_template="ls /home/coding",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.FS_EXPLORE,
            command_template="ls {repo_path}",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.FS_README,
            command_template="cat {repo_path}/README.md",
            timeout_seconds=2,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.GIT_LOG,
            command_template="git -C {repo_path} log -5 --oneline --pretty=format:'%h|%s|%an|%ar'",
            timeout_seconds=3,
            required=False,
            cacheable=True,
        ),
    ],

    IntentType.REMINDER: [
        FetchCommandSpec(
            source=FetchSource.REMINDERS,
            command_template="reminders list --session {session_id}",
            timeout_seconds=3,
            required=True,
            cacheable=False,
        ),
    ],

    IntentType.SELF_MODIFICATION: [
        FetchCommandSpec(
            source=FetchSource.SESSION_STATE,
            command_template="session state --session {session_id}",
            timeout_seconds=3,
            required=True,
            cacheable=False,
        ),
        FetchCommandSpec(
            source=FetchSource.COMPONENTS,
            command_template="components list --all",
            timeout_seconds=3,
            required=False,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.GIT_LOG,
            command_template="git -C {repo_path} log -5 --oneline",
            timeout_seconds=3,
            required=False,
            cacheable=True,
        ),
    ],

    IntentType.MONITORING_CONFIG: [
        FetchCommandSpec(
            source=FetchSource.COMPONENTS,
            command_template="components list --project {project_slug}",
            timeout_seconds=3,
            required=True,
            cacheable=True,
        ),
        FetchCommandSpec(
            source=FetchSource.KUBECTL_PODS,
            command_template="kubectl --server={proxy} get pods -n {namespace} -o json",
            timeout_seconds=5,
            required=False,
            cacheable=True,
        ),
    ],
}


def get_fetch_commands(intent_type: IntentType) -> list[FetchCommandSpec]:
    """Get fetch command specs for an intent type."""
    return FETCH_COMMAND_MATRIX.get(intent_type, [])


def get_required_sources(intent_type: IntentType) -> list[FetchSource]:
    """Get required sources for an intent type."""
    commands = FETCH_COMMAND_MATRIX.get(intent_type, [])
    return [cmd.source for cmd in commands if cmd.required]


@dataclass
class FetchContext:
    """Context variables for command template expansion."""
    project_slug: str | None = None
    namespace: str | None = None
    cluster: str | None = None
    repo_path: str | None = None
    app_name: str | None = None
    deployment: str | None = None
    pod_name: str | None = None
    topic_id: str | None = None
    session_id: str | None = None
    intent_id: str | None = None

    # Remote access — set when repo lives on a different machine
    ssh_target: str | None = None  # e.g. "coding@100.81.129.38"
    host_alias: str | None = None  # e.g. "lab"

    # Proxy endpoints
    proxy: str = "http://traefik-ardenone-manager:8001"
    argocd_proxy: str = "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444"

    def expand_template(self, template: str) -> str:
        """Expand a command template with context values."""
        result = template
        for key, value in self.__dict__.items():
            if value is not None:
                placeholder = "{" + key + "}"
                result = result.replace(placeholder, str(value))
        return result


@dataclass
class FetchRequest:
    """A fetch request to be executed."""
    intent_type: IntentType
    context: FetchContext
    intent_id: str
    session_id: str


@dataclass
class SourceResult:
    """Result from a single fetch source."""
    source: FetchSource
    status: str  # "success", "timeout", "error"
    data: dict[str, Any]
    error: str | None = None
    duration_ms: int = 0
    cached: bool = False


@dataclass
class FetchCoverage:
    """Coverage report for fetch operations."""
    total_sources: int
    succeeded: list[FetchSource]
    timed_out: list[FetchSource]
    failed: list[FetchSource]
    skipped: list[FetchSource]

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        if self.total_sources == 0:
            return 0.0
        return len(self.succeeded) / self.total_sources

    @property
    def has_required_failure(self) -> bool:
        """Check if any required source failed."""
        return len(self.failed) > 0


@dataclass
class FetchResult:
    """Complete fetch result with coverage info."""
    intent_id: str
    intent_type: IntentType
    sources: dict[FetchSource, SourceResult]
    coverage: FetchCoverage
    total_duration_ms: int
    caveats: list[str] | None = None
    terminal_failure: str | None = None  # Set to "all_sources_failed" if all sources fail

    def get_source_result(self, source: FetchSource) -> SourceResult | None:
        """Get result for a specific source."""
        return self.sources.get(source)

    def get_successful_data(self) -> dict[FetchSource, dict]:
        """Get data from all successful sources."""
        return {
            source: result.data
            for source, result in self.sources.items()
            if result.status == "success"
        }

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "intent_id": self.intent_id,
            "intent_type": self.intent_type.value,
            "sources": {
                source.value: {
                    "status": result.status,
                    "data": result.data,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                    "cached": result.cached,
                }
                for source, result in self.sources.items()
            },
            "coverage": {
                "total_sources": self.coverage.total_sources,
                "succeeded": [s.value for s in self.coverage.succeeded],
                "timed_out": [s.value for s in self.coverage.timed_out],
                "failed": [s.value for s in self.coverage.failed],
                "skipped": [s.value for s in self.coverage.skipped],
                "success_rate": self.coverage.success_rate,
                "has_required_failure": self.coverage.has_required_failure,
            },
            "total_duration_ms": self.total_duration_ms,
            "caveats": self.caveats,
        }
