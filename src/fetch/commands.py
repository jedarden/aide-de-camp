"""
Fetch command matrix: defines what to fetch per intent type.

Each intent type has a specific set of sources to query, with their
corresponding commands and timeout settings.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


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


@dataclass
class FetchCommandSpec:
    """Specification for a single fetch command."""
    source: FetchSource
    command_template: str
    timeout_seconds: int = 5
    required: bool = False
    cacheable: bool = True


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
