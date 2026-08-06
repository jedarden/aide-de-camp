"""
Whisper-STT Deployment Data Schema (Simplified, Service-Agnostic)

Pydantic models implementing the simplified, service-agnostic schema
for cross-service deployment comparison (whisper-stt, pbx-web, etc.).

Based on type definitions from: docs/research/whisper-stt-deployment-schema-types.md
Source bead: adc-5k55i

Schema Version: 1.0.0
Last Updated: 2026-08-06
"""

from datetime import datetime
from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# =============================================================================
# Enum Definitions
# =============================================================================

class HealthStatus(str, Enum):
    """Overall service health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class StabilityLevel(str, Enum):
    """Deployment stability assessment"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class DeploymentStatus(str, Enum):
    """Individual deployment status"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    ROLLBACK = "rollback"


class FailureType(str, Enum):
    """Specific deployment failure type"""
    IMAGE_PULL_ERROR = "image_pull_error"
    CRASH_LOOP_BACK_OFF = "crash_loop_back_off"
    OOM_KILLED = "oom_killed"
    PROBE_FAILURE = "probe_failure"
    PVC_MOUNT_FAILED = "pvc_mount_failed"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    UNKNOWN = "unknown"


# =============================================================================
# Metadata Section (3 fields)
# =============================================================================

class DeploymentMetadata(BaseModel):
    """
    Metadata for the deployment dataset.

    Field constraints from type definitions:
    - generated_at: ISO 8601 timestamp with timezone (required)
    - source_files: Array of file paths/URIs, max 100 elements, unique (required)
    - total_records: Non-negative integer, max 1,000,000 (required)
    """
    generated_at: str = Field(
        ...,
        description="Timestamp when dataset was generated (ISO 8601 with timezone)",
        pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$'
    )
    source_files: List[str] = Field(
        default_factory=list,
        description="List of source data files or URIs",
        max_length=100
    )
    total_records: int = Field(
        ...,
        description="Total number of deployment records",
        ge=0,
        le=1_000_000
    )

    @field_validator('generated_at')
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate ISO 8601 timestamp format."""
        from datetime import datetime
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp format: {v}")

    @field_validator('source_files')
    @classmethod
    def validate_unique_source_files(cls, v: List[str]) -> List[str]:
        """Ensure source files are unique and non-empty."""
        if len(set(v)) != len(v):
            raise ValueError("source_files must contain unique elements")
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("source_files elements must be non-empty strings")
        return v


# =============================================================================
# Service Summary Section (23 fields per service)
# =============================================================================

class ServiceSummary(BaseModel):
    """
    Service-level deployment summary for comparative analysis.

    Field constraints from type definitions:

    Identifiers (4 fields):
    - service: Kubernetes name pattern, 1-63 chars (required)
    - cluster: DNS name pattern, 1-253 chars (required)
    - namespace: Kubernetes name pattern, 1-63 chars (required)

    Deployment Counts (4 fields):
    - total_deployments: PodCount, 0-10,000 (required)
    - successful_updates: PodCount, ≤ total_deployments (required)
    - failed_rollouts: PodCount, ≤ total_deployments (required)
    - last_deployment_update: ISO 8601 timestamp (required)

    Health & Stability (3 fields):
    - overall_health: HealthStatus enum (required)
    - deployment_stability: StabilityLevel enum (required)
    - uptime_percentage: String "X%" format, 0-100 (required)
    - successful_deployment_rate: String "X%" format, 0-100 (required)

    Pod Metrics (6 fields):
    - replicas: PodCount, 0-100 (required)
    - ready_replicas: PodCount, ≤ replicas (required)
    - available_replicas: PodCount, ≤ replicas (required)
    - total_pods: PodCount, 0-200 (required)
    - running_pods: PodCount, ≤ total_pods (required)
    - total_restarts: PodCount, 0-1,000,000 (required)

    Incident Tracking (6 fields):
    - crashloops: PodCount, ≤ total_pods (required)
    - oomkills: PodCount, ≤ total_pods (required)
    - total_incidents: PodCount, 0-10,000 (required)
    - critical_incidents: PodCount, ≤ total_incidents (required)
    - warning_incidents: PodCount, ≤ total_incidents (required)
    - log_errors: PodCount, 0-1,000,000 (required)
    - rollback_events: PodCount, 0-10,000 (required)
    """

    # Identifiers (4 fields)
    service: str = Field(
        ...,
        description="Service identifier (Kubernetes name)",
        pattern=r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',
        min_length=1,
        max_length=63
    )
    cluster: str = Field(
        ...,
        description="Cluster identifier (DNS name)",
        pattern=r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$',
        min_length=1,
        max_length=253
    )
    namespace: str = Field(
        ...,
        description="Kubernetes namespace",
        pattern=r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',
        min_length=1,
        max_length=63
    )

    # Deployment Counts (4 fields)
    total_deployments: int = Field(
        ...,
        description="Total number of deployment resources",
        ge=0,
        le=10_000
    )
    successful_updates: int = Field(
        ...,
        description="Count of successful deployment updates",
        ge=0,
        le=10_000
    )
    failed_rollouts: int = Field(
        ...,
        description="Count of failed rollout attempts",
        ge=0,
        le=10_000
    )
    last_deployment_update: str = Field(
        ...,
        description="Timestamp of last deployment activity (ISO 8601)",
        pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$'
    )

    # Health & Stability (4 fields)
    overall_health: HealthStatus = Field(
        ...,
        description="Overall service health assessment"
    )
    deployment_stability: StabilityLevel = Field(
        ...,
        description="Deployment stability assessment"
    )
    uptime_percentage: str = Field(
        ...,
        description="Service uptime percentage (e.g., '99.9%')",
        pattern=r'^(100|[1-9]?\d)%$'
    )
    successful_deployment_rate: str = Field(
        ...,
        description="Percentage of successful deployments (e.g., '85.7%')",
        pattern=r'^(100|[1-9]?\d)%$'
    )

    # Pod Metrics (6 fields)
    replicas: int = Field(
        ...,
        description="Desired replica count",
        ge=0,
        le=100
    )
    ready_replicas: int = Field(
        ...,
        description="Number of ready replicas",
        ge=0,
        le=100
    )
    available_replicas: int = Field(
        ...,
        description="Number of available replicas",
        ge=0,
        le=100
    )
    total_pods: int = Field(
        ...,
        description="Total pod count across deployments",
        ge=0,
        le=200
    )
    running_pods: int = Field(
        ...,
        description="Currently running pod count",
        ge=0,
        le=200
    )
    total_restarts: int = Field(
        ...,
        description="Total container restart count",
        ge=0,
        le=1_000_000
    )

    # Incident Tracking (7 fields)
    crashloops: int = Field(
        ...,
        description="Count of pods in crash loop back-off",
        ge=0,
        le=200
    )
    oomkills: int = Field(
        ...,
        description="Count of OOM killed pods",
        ge=0,
        le=200
    )
    total_incidents: int = Field(
        ...,
        description="Total incident count",
        ge=0,
        le=10_000
    )
    critical_incidents: int = Field(
        ...,
        description="Critical incident count",
        ge=0,
        le=10_000
    )
    warning_incidents: int = Field(
        ...,
        description="Warning incident count",
        ge=0,
        le=10_000
    )
    log_errors: int = Field(
        ...,
        description="Total log error count",
        ge=0,
        le=1_000_000
    )
    rollback_events: int = Field(
        ...,
        description="Count of rollback events",
        ge=0,
        le=10_000
    )

    @field_validator('last_deployment_update')
    @classmethod
    def validate_last_deployment_timestamp(cls, v: str) -> str:
        """Validate ISO 8601 timestamp and ensure not in future."""
        from datetime import datetime, timezone
        try:
            timestamp = datetime.fromisoformat(v)
            now = datetime.now(timezone.utc)
            if timestamp > now:
                raise ValueError("last_deployment_update cannot be in the future")
            return v
        except ValueError as e:
            raise ValueError(f"Invalid timestamp: {e}")

    @field_validator('ready_replicas')
    @classmethod
    def validate_ready_replicas(cls, v: int, info) -> int:
        """Ensure ready_replicas ≤ replicas."""
        if 'replicas' in info.data and v > info.data['replicas']:
            raise ValueError(f"ready_replicas ({v}) cannot exceed replicas ({info.data['replicas']})")
        return v

    @field_validator('available_replicas')
    @classmethod
    def validate_available_replicas(cls, v: int, info) -> int:
        """Ensure available_replicas ≤ replicas."""
        if 'replicas' in info.data and v > info.data['replicas']:
            raise ValueError(f"available_replicas ({v}) cannot exceed replicas ({info.data['replicas']})")
        return v

    @field_validator('running_pods')
    @classmethod
    def validate_running_pods(cls, v: int, info) -> int:
        """Ensure running_pods ≤ total_pods."""
        if 'total_pods' in info.data and v > info.data['total_pods']:
            raise ValueError(f"running_pods ({v}) cannot exceed total_pods ({info.data['total_pods']})")
        return v

    @field_validator('crashloops')
    @classmethod
    def validate_crashloops(cls, v: int, info) -> int:
        """Ensure crashloops ≤ total_pods."""
        if 'total_pods' in info.data and v > info.data['total_pods']:
            raise ValueError(f"crashloops ({v}) cannot exceed total_pods ({info.data['total_pods']})")
        return v

    @field_validator('oomkills')
    @classmethod
    def validate_oomkills(cls, v: int, info) -> int:
        """Ensure oomkills ≤ total_pods."""
        if 'total_pods' in info.data and v > info.data['total_pods']:
            raise ValueError(f"oomkills ({v}) cannot exceed total_pods ({info.data['total_pods']})")
        return v

    @field_validator('critical_incidents', 'warning_incidents')
    @classmethod
    def validate_incident_counts(cls, v: int, info) -> int:
        """Ensure incident subtypes ≤ total_incidents."""
        if 'total_incidents' in info.data and v > info.data['total_incidents']:
            field_name = info.field_name
            raise ValueError(f"{field_name} ({v}) cannot exceed total_incidents ({info.data['total_incidents']})")
        return v

    @field_validator('successful_updates', 'failed_rollouts')
    @classmethod
    def validate_deployment_counts(cls, v: int, info) -> int:
        """Ensure deployment counts ≤ total_deployments."""
        if 'total_deployments' in info.data and v > info.data['total_deployments']:
            field_name = info.field_name
            raise ValueError(f"{field_name} ({v}) cannot exceed total_deployments ({info.data['total_deployments']})")
        return v


# =============================================================================
# Deployment Record Section (13 fields per record)
# =============================================================================

class DeploymentRecord(BaseModel):
    """
    Individual deployment record matching pbx-web format.

    Field constraints from type definitions:

    Identifiers (6 fields):
    - service: Kubernetes name pattern, 1-63 chars (required)
    - deployment_name: Kubernetes name pattern, 1-63 chars (required)
    - replicaset_name: Kubernetes name + 10-char hex hash, 12-253 chars (required)
    - image: Docker image format, max 500 chars, no :latest (required)
    - cluster: DNS name pattern, 1-253 chars (required)
    - namespace: Kubernetes name pattern, 1-63 chars (required)

    Timestamps (2 fields):
    - timestamp: ISO 8601 timestamp with timezone (required)
    - date: ISO 8601 date only (required)

    Status & Outcome (2 fields):
    - status: DeploymentStatus enum (required)
    - failure_type: FailureType enum or null (optional)

    Replica Counts (3 fields):
    - revision: Numeric string, "0"-"999999" (required)
    - replicas: PodCount, 0-100 (required)
    - ready_replicas: PodCount, ≤ replicas (required)
    - available_replicas: PodCount, ≤ replicas (required)
    """

    # Identifiers (6 fields)
    service: str = Field(
        ...,
        description="Service identifier (Kubernetes name)",
        pattern=r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',
        min_length=1,
        max_length=63
    )
    deployment_name: str = Field(
        ...,
        description="Kubernetes Deployment resource name",
        pattern=r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',
        min_length=1,
        max_length=63
    )
    replicaset_name: str = Field(
        ...,
        description="Kubernetes ReplicaSet resource name with hash suffix",
        pattern=r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?-[a-f0-9]{10}$',
        min_length=12,
        max_length=253
    )
    image: str = Field(
        ...,
        description="Container image reference (registry/repo:tag)",
        min_length=1,
        max_length=500
    )
    cluster: str = Field(
        ...,
        description="Cluster identifier (DNS name)",
        pattern=r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$',
        min_length=1,
        max_length=253
    )
    namespace: str = Field(
        ...,
        description="Kubernetes namespace",
        pattern=r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$',
        min_length=1,
        max_length=63
    )

    # Timestamps (2 fields)
    timestamp: str = Field(
        ...,
        description="Deployment creation timestamp (ISO 8601 with timezone)",
        pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$'
    )
    date: str = Field(
        ...,
        description="Deployment date (ISO 8601 date only)",
        pattern=r'^\d{4}-\d{2}-\d{2}$'
    )

    # Status & Outcome (2 fields)
    status: DeploymentStatus = Field(
        ...,
        description="Deployment status"
    )
    failure_type: Optional[FailureType] = Field(
        None,
        description="Specific failure type if status='failed'"
    )

    # Replica Counts (4 fields)
    revision: str = Field(
        ...,
        description="Deployment revision number (numeric string)",
        pattern=r'^\d+$'
    )
    replicas: int = Field(
        ...,
        description="Total replica count",
        ge=0,
        le=100
    )
    ready_replicas: int = Field(
        ...,
        description="Number of ready replicas",
        ge=0,
        le=100
    )
    available_replicas: int = Field(
        ...,
        description="Number of available replicas",
        ge=0,
        le=100
    )

    @field_validator('timestamp', 'date')
    @classmethod
    def validate_timestamps(cls, v: str, info) -> str:
        """Validate ISO 8601 timestamp/date formats."""
        from datetime import datetime
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            field_name = info.field_name
            raise ValueError(f"Invalid ISO 8601 {field_name} format: {v}")

    @field_validator('image')
    @classmethod
    def validate_docker_image(cls, v: str) -> str:
        """Validate Docker image reference format.

        Valid formats:
        - registry/repository:tag (e.g., docker.io/ronaldraygun/whisper-stt:1.8.6)
        - repository:tag (e.g., ronaldraygun/whisper-stt:1.8.6)
        - registryhost:port/repository:tag (e.g., ghcr.io/jedarden/app:1.2.3)

        Invalid formats:
        - :latest tag (not allowed per cluster rules)
        - Empty or extremely long names (>500 chars)
        """
        import re

        if not v or not isinstance(v, str):
            raise ValueError(f"Invalid Docker image format: {v}")

        if len(v) > 500:
            raise ValueError(f"Docker image reference too long (max 500 chars): {len(v)}")

        if v.endswith(':latest'):
            raise ValueError("Docker image tag ':latest' is not allowed")

        # Basic pattern: allow registry with dots/colons, repository segments, and tag
        # Pattern explanation:
        # - (?:[a-z0-9]+[._-]?)*: Registry part (optional, allows dots, dashes, underscores)
        # - /: Separator
        # - [a-z0-9]+([._-/][a-z0-9]+)*/: Repository segments
        # - :[a-zA-Z0-9._-]+$: Tag
        pattern = r'^(?:[a-z0-9]+([._-][a-z0-9]+)*)?\/[a-z0-9]+([._-][a-z0-9]+)*(\/[a-z0-9]+([._-][a-z0-9]+)*)*:[a-zA-Z0-9._-]+$'

        if not re.match(pattern, v):
            raise ValueError(f"Invalid Docker image format: {v}")

        return v

    @field_validator('revision')
    @classmethod
    def validate_revision(cls, v: str) -> str:
        """Validate revision is numeric string within range."""
        try:
            num = int(v)
            if not (0 <= num <= 999_999):
                raise ValueError(f"Revision must be between 0 and 999999, got: {num}")
            return v
        except ValueError as e:
            raise ValueError(f"Revision must be numeric string: {e}")

    @field_validator('ready_replicas', 'available_replicas')
    @classmethod
    def validate_replica_counts(cls, v: int, info) -> int:
        """Ensure replica counts ≤ replicas."""
        if 'replicas' in info.data and v > info.data['replicas']:
            field_name = info.field_name
            raise ValueError(f"{field_name} ({v}) cannot exceed replicas ({info.data['replicas']})")
        return v

    @field_validator('failure_type')
    @classmethod
    def validate_failure_type_logic(cls, v: Optional[FailureType], info) -> Optional[FailureType]:
        """Ensure failure_type is populated when status='failed'."""
        if info.data.get('status') == DeploymentStatus.FAILED and v is None:
            raise ValueError("failure_type must be specified when status='failed'")
        if info.data.get('status') == DeploymentStatus.SUCCESS and v is not None:
            raise ValueError("failure_type should be null when status='success'")
        return v


# =============================================================================
# Main Schema (Top-Level)
# =============================================================================

class WhisperSTTDeploymentSchema(BaseModel):
    """
    Complete whisper-stt deployment dataset (simplified, service-agnostic).

    This schema provides a normalized structure for cross-service deployment
    comparison between whisper-stt, pbx-web, and other services.

    Structure:
    - metadata: Dataset metadata (3 fields)
    - summaries: Service-level summaries keyed by service name (23 fields per service)
    - deployment_records: Individual deployment records (13 fields per record)

    Total fields: 39 (including nested)
    Required fields: 31 (79%)
    Optional fields: 8 (21%)
    """
    metadata: DeploymentMetadata = Field(
        ...,
        description="Dataset metadata"
    )
    summaries: Dict[str, ServiceSummary] = Field(
        ...,
        description="Service-level summaries keyed by service name",
        min_length=1,
        max_length=1000
    )
    deployment_records: List[DeploymentRecord] = Field(
        ...,
        description="Individual deployment records",
        min_length=0,
        max_length=10_000
    )

    @field_validator('summaries')
    @classmethod
    def validate_summaries_keys(cls, v: Dict[str, ServiceSummary]) -> Dict[str, ServiceSummary]:
        """Ensure summary keys match service names and are valid Kubernetes names."""
        import re
        k8s_name_pattern = r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
        for service_name in v.keys():
            if not re.match(k8s_name_pattern, service_name):
                raise ValueError(f"Invalid service name in summaries: {service_name}")
            if not (1 <= len(service_name) <= 63):
                raise ValueError(f"Service name must be 1-63 chars: {service_name}")
            # Ensure summary object's service field matches the key
            if v[service_name].service != service_name:
                raise ValueError(f"Summary service field '{v[service_name].service}' does not match key '{service_name}'")
        return v

    @field_validator('deployment_records')
    @classmethod
    def validate_deployment_records(cls, v: List[DeploymentRecord]) -> List[DeploymentRecord]:
        """Ensure deployment records are valid and reference services in summaries."""
        if len(v) > 10_000:
            raise ValueError(f"deployment_records exceeds maximum of 10,000")
        return v

    @field_validator('metadata')
    @classmethod
    def validate_metadata_consistency(cls, v: DeploymentMetadata, info) -> DeploymentMetadata:
        """Ensure metadata.total_records matches deployment_records length."""
        if 'deployment_records' in info.data:
            expected_count = len(info.data['deployment_records'])
            if v.total_records != expected_count:
                raise ValueError(f"metadata.total_records ({v.total_records}) does not match deployment_records length ({expected_count})")
        return v

    class Config:
        """Pydantic model configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z' if v else None
        }
        json_schema_extra = {
            "example": {
                "metadata": {
                    "generated_at": "2026-08-06T11:09:33+00:00",
                    "source_files": ["whisper-stt-deployments-30d.json"],
                    "total_records": 19
                },
                "summaries": {
                    "whisper-stt": {
                        "service": "whisper-stt",
                        "cluster": "ardenone-cluster",
                        "namespace": "whisper-stt",
                        "total_deployments": 19,
                        "successful_updates": 15,
                        "failed_rollouts": 4,
                        "last_deployment_update": "2026-07-12T14:23:15+00:00",
                        "overall_health": "degraded",
                        "deployment_stability": "medium",
                        "uptime_percentage": "92%",
                        "successful_deployment_rate": "79%",
                        "replicas": 3,
                        "ready_replicas": 2,
                        "available_replicas": 2,
                        "total_pods": 3,
                        "running_pods": 2,
                        "total_restarts": 0,
                        "crashloops": 0,
                        "oomkills": 1,
                        "total_incidents": 5,
                        "critical_incidents": 2,
                        "warning_incidents": 3,
                        "log_errors": 12,
                        "rollback_events": 1
                    }
                },
                "deployment_records": [
                    {
                        "service": "whisper-stt",
                        "deployment_name": "whisper-stt",
                        "replicaset_name": "whisper-stt-68966786fb",
                        "image": "docker.io/ronaldraygun/whisper-stt:1.8.6",
                        "cluster": "ardenone-cluster",
                        "namespace": "whisper-stt",
                        "timestamp": "2026-07-12T14:23:15+00:00",
                        "date": "2026-07-12",
                        "status": "success",
                        "failure_type": None,
                        "revision": "18",
                        "replicas": 3,
                        "ready_replicas": 3,
                        "available_replicas": 3
                    }
                ]
            }
        }


# =============================================================================
# Validation Utilities
# =============================================================================

def validate_deployment_data(data: dict) -> tuple[bool, list[str]]:
    """
    Validate deployment data against the schema.

    Args:
        data: Dictionary containing deployment data

    Returns:
        tuple: (is_valid, list_of_error_messages)
    """
    errors = []

    try:
        WhisperSTTDeploymentSchema(**data)
        return True, []
    except Exception as e:
        # Parse Pydantic validation errors
        if hasattr(e, 'errors'):
            for error in e.errors():
                loc = ' -> '.join(str(l) for l in error['loc'])
                msg = error['msg']
                errors.append(f"{loc}: {msg}" if loc else msg)
        else:
            errors.append(str(e))

    return False, errors


def calculate_success_rate(successful: int, total: int) -> float:
    """
    Calculate deployment success rate.

    Args:
        successful: Number of successful deployments
        total: Total number of deployments

    Returns:
        float: Success rate between 0.0 and 1.0
    """
    if total == 0:
        return 1.0
    return round(successful / total, 3)


def format_success_rate(rate: float) -> str:
    """
    Format success rate as percentage string.

    Args:
        rate: Success rate decimal (0-1)

    Returns:
        str: Formatted percentage (e.g., '85.7%')
    """
    return f"{rate * 100:.1f}%"


# =============================================================================
# Example Data
# =============================================================================

def example_whisper_stt_dataset() -> dict:
    """
    Generate example whisper-stt deployment data matching the schema.

    Returns example data structure following the simplified service-agnostic format.
    """
    return {
        "metadata": {
            "generated_at": "2026-08-06T11:09:33+00:00",
            "source_files": [
                "whisper-stt-deployments-30d.json",
                "whisper-stt-events-2026-08.json"
            ],
            "total_records": 19
        },
        "summaries": {
            "whisper-stt": {
                "service": "whisper-stt",
                "cluster": "ardenone-cluster",
                "namespace": "whisper-stt",
                "total_deployments": 19,
                "successful_updates": 15,
                "failed_rollouts": 4,
                "last_deployment_update": "2026-07-12T14:23:15+00:00",
                "overall_health": "degraded",
                "deployment_stability": "medium",
                "uptime_percentage": "92%",
                "successful_deployment_rate": "79%",
                "replicas": 3,
                "ready_replicas": 2,
                "available_replicas": 2,
                "total_pods": 3,
                "running_pods": 2,
                "total_restarts": 0,
                "crashloops": 0,
                "oomkills": 1,
                "total_incidents": 5,
                "critical_incidents": 2,
                "warning_incidents": 3,
                "log_errors": 12,
                "rollback_events": 1
            }
        },
        "deployment_records": [
            {
                "service": "whisper-stt",
                "deployment_name": "whisper-stt",
                "replicaset_name": "whisper-stt-68966786fb",
                "image": "docker.io/ronaldraygun/whisper-stt:1.8.6",
                "cluster": "ardenone-cluster",
                "namespace": "whisper-stt",
                "timestamp": "2026-07-12T14:23:15+00:00",
                "date": "2026-07-12",
                "status": "success",
                "failure_type": None,
                "revision": "18",
                "replicas": 3,
                "ready_replicas": 3,
                "available_replicas": 3
            },
            {
                "service": "whisper-stt",
                "deployment_name": "whisper-stt",
                "replicaset_name": "whisper-stt-6885fc878b",
                "image": "docker.io/ronaldraygun/whisper-stt:1.8.4",
                "cluster": "ardenone-cluster",
                "namespace": "whisper-stt",
                "timestamp": "2026-07-07T09:15:22+00:00",
                "date": "2026-07-07",
                "status": "failed",
                "failure_type": "oom_killed",
                "revision": "17",
                "replicas": 3,
                "ready_replicas": 2,
                "available_replicas": 2
            }
        ]
    }


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Main schema
    "WhisperSTTDeploymentSchema",

    # Core models
    "DeploymentMetadata",
    "ServiceSummary",
    "DeploymentRecord",

    # Enums
    "HealthStatus",
    "StabilityLevel",
    "DeploymentStatus",
    "FailureType",

    # Validation utilities
    "validate_deployment_data",
    "calculate_success_rate",
    "format_success_rate",

    # Example data
    "example_whisper_stt_dataset",
]


# =============================================================================
# Main Execution (for testing)
# =============================================================================

if __name__ == "__main__":
    # Example usage and validation
    example_data = example_whisper_stt_dataset()

    is_valid, errors = validate_deployment_data(example_data)
    print(f"Schema validation: {'PASSED ✓' if is_valid else 'FAILED ✗'}")

    if errors:
        print("\nValidation errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\nExample data structure is valid!")

        # Test Pydantic model instantiation
        schema = WhisperSTTDeploymentSchema(**example_data)
        print(f"\nSchema loaded successfully:")
        print(f"  - Services: {list(schema.summaries.keys())}")
        print(f"  - Deployment records: {len(schema.deployment_records)}")
        print(f"  - Total records in metadata: {schema.metadata.total_records}")
