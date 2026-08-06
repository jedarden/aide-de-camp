"""
Whisper-STT Deployment Data Schema

This schema defines the structure for whisper-stt deployment data,
matching the pbx-web deployment data format for consistency and comparability.

Schema matches the normalized deployment data structure from:
docs/research/deployment-data-normalized.json
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ServiceHealth(str, Enum):
    """Service health status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class DeploymentStability(str, Enum):
    """Deployment stability level enumeration"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class DeploymentStatus(str, Enum):
    """Individual deployment status enumeration"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    ROLLBACK = "rollback"


class FailureType(str, Enum):
    """Deployment failure type enumeration"""
    IMAGE_PULL_ERROR = "image_pull_error"
    CRASH_LOOP_BACK_OFF = "crash_loop_back_off"
    OOM_KILLED = "oom_killed"
    PROBE_FAILURE = "probe_failure"
    PVC_MOUNT_FAILED = "pvc_mount_failed"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    UNKNOWN = "unknown"


@dataclass
class DeploymentRecord:
    """
    Individual deployment record matching pbx-web format.

    Fields match exactly with pbx-web deployment records:
    - service: Service identifier (e.g., 'whisper-stt', 'pbx-web')
    - deployment_name: Kubernetes Deployment resource name
    - replicaset_name: Kubernetes ReplicaSet resource name
    - timestamp: Deployment creation timestamp (ISO 8601)
    - status: Deployment status (success/failed/pending/rollback)
    - failure_type: Specific failure type if status='failed'
    - revision: Deployment revision number
    - replicas: Total replica count
    - ready_replicas: Number of ready replicas
    - available_replicas: Number of available replicas
    - image: Container image tag (nullable)
    - cluster: Cluster identifier
    - namespace: Kubernetes namespace
    """
    service: str
    deployment_name: str
    replicaset_name: str
    timestamp: str  # ISO 8601 format
    status: DeploymentStatus
    failure_type: Optional[FailureType]
    revision: str
    replicas: int
    ready_replicas: int
    available_replicas: int
    image: Optional[str]
    cluster: str
    namespace: str


@dataclass
class ServiceSummary:
    """
    Service-level deployment summary matching pbx-web format.

    Fields match exactly with pbx-web service summaries:
    - service: Service identifier (e.g., 'whisper-stt', 'pbx-web')
    - total_deployments: Total number of deployment resources
    - total_replicasets: Total number of replicaset resources
    - successful_updates: Count of successful deployment updates
    - failed_rollouts: Count of failed rollout attempts
    - rollback_events: Count of rollback events
    - last_deployment_update: Timestamp of last deployment activity
    - overall_health: Overall service health assessment
    - deployment_stability: Deployment stability assessment
    - uptime_percentage: Service uptime percentage
    - zero_downtime_deployment: Whether deployments cause downtime
    - successful_deployment_rate: Percentage of successful deployments
    - total_pods: Total pod count across deployments
    - running_pods: Currently running pod count
    - total_restarts: Total container restart count
    - crashloops: Count of pods in crash loop back-off
    - oomkills: Count of OOM killed pods
    - total_incidents: Total incident count
    - critical_incidents: Critical incident count
    - warning_incidents: Warning incident count
    - log_errors: Total log error count
    """
    service: str
    total_deployments: int
    total_replicasets: int
    successful_updates: int
    failed_rollouts: int
    rollback_events: int
    last_deployment_update: str  # ISO 8601 format
    overall_health: ServiceHealth
    deployment_stability: DeploymentStability
    uptime_percentage: str  # Format: "99.9%"
    zero_downtime_deployment: bool
    successful_deployment_rate: str  # Format: "99.9%"
    total_pods: int
    running_pods: int
    total_restarts: int
    crashloops: int
    oomkills: int
    total_incidents: int
    critical_incidents: int
    warning_incidents: int
    log_errors: int


@dataclass
class DeploymentMetadata:
    """
    Metadata for the deployment dataset.

    Fields match exactly with pbx-web deployment metadata:
    - generated_at: Timestamp when dataset was generated
    - source_files: List of source data files
    - total_records: Total number of deployment records
    """
    generated_at: str  # ISO 8601 format
    source_files: List[str]
    total_records: int


@dataclass
class DeploymentDataset:
    """
    Complete deployment dataset matching pbx-web format.

    This is the top-level schema that encompasses all deployment data
    for whisper-stt in the same structure as pbx-web deployment data.

    Structure:
    - metadata: Dataset metadata
    - summaries: Service-level summary statistics keyed by service name
    - deployment_records: Individual deployment records
    """
    metadata: DeploymentMetadata
    summaries: dict[str, ServiceSummary]
    deployment_records: List[DeploymentRecord]


# Field type alignment with pbx-web format
FIELD_TYPES = {
    # DeploymentRecord fields
    "service": "string",
    "deployment_name": "string",
    "replicaset_name": "string",
    "timestamp": "string (ISO 8601 datetime)",
    "status": "enum (success/failed/pending/rollback)",
    "failure_type": "enum or null",
    "revision": "string",
    "replicas": "integer",
    "ready_replicas": "integer",
    "available_replicas": "integer",
    "image": "string or null",
    "cluster": "string",
    "namespace": "string",

    # ServiceSummary fields
    "service": "string",
    "total_deployments": "integer",
    "total_replicasets": "integer",
    "successful_updates": "integer",
    "failed_rollouts": "integer",
    "rollback_events": "integer",
    "last_deployment_update": "string (ISO 8601 datetime)",
    "overall_health": "enum (healthy/degraded/unhealthy/unknown)",
    "deployment_stability": "enum (high/medium/low/unknown)",
    "uptime_percentage": "string (percentage format)",
    "zero_downtime_deployment": "boolean",
    "successful_deployment_rate": "string (percentage format)",
    "total_pods": "integer",
    "running_pods": "integer",
    "total_restarts": "integer",
    "crashloops": "integer",
    "oomkills": "integer",
    "total_incidents": "integer",
    "critical_incidents": "integer",
    "warning_incidents": "integer",
    "log_errors": "integer",

    # Metadata fields
    "generated_at": "string (ISO 8601 datetime)",
    "source_files": "array of strings",
    "total_records": "integer"
}


# Schema validation rules
SCHEMA_CONSTRAINTS = {
    "timestamp_format": "ISO 8601 (YYYY-MM-DDTHH:MM:SS+00:00)",
    "percentage_format": "String with % suffix (e.g., '99.9%')",
    "revision_format": "String representation of integer",
    "enum_fields": {
        "status": ["success", "failed", "pending", "rollback"],
        "failure_type": ["image_pull_error", "crash_loop_back_off", "oom_killed",
                        "probe_failure", "pvc_mount_failed", "resource_limit_exceeded", "unknown"],
        "overall_health": ["healthy", "degraded", "unhealthy", "unknown"],
        "deployment_stability": ["high", "medium", "low", "unknown"]
    },
    "nullable_fields": ["failure_type", "image"],
    "required_fields": {
        "DeploymentRecord": ["service", "deployment_name", "replicaset_name",
                           "timestamp", "status", "revision", "replicas",
                           "ready_replicas", "available_replicas", "cluster", "namespace"],
        "ServiceSummary": ["service", "total_deployments", "total_replicasets",
                         "successful_updates", "failed_rollouts", "rollback_events",
                         "last_deployment_update", "overall_health", "deployment_stability",
                         "uptime_percentage", "zero_downtime_deployment",
                         "successful_deployment_rate", "total_pods", "running_pods",
                         "total_restarts", "crashloops", "oomkills", "total_incidents",
                         "critical_incidents", "warning_incidents", "log_errors"],
        "DeploymentMetadata": ["generated_at", "source_files", "total_records"]
    }
}


def validate_schema(data: dict) -> tuple[bool, list[str]]:
    """
    Validate deployment data against the schema.

    Returns:
        tuple: (is_valid, list_of_error_messages)
    """
    errors = []

    # Validate metadata presence
    if "metadata" not in data:
        errors.append("Missing required field: metadata")
        return False, errors

    # Validate required top-level structure
    required_sections = ["metadata", "summaries", "deployment_records"]
    for section in required_sections:
        if section not in data:
            errors.append(f"Missing required section: {section}")

    if errors:
        return False, errors

    # Validate metadata fields
    metadata = data["metadata"]
    required_metadata_fields = ["generated_at", "source_files", "total_records"]
    for field in required_metadata_fields:
        if field not in metadata:
            errors.append(f"Missing required metadata field: {field}")

    # Validate deployment_records structure
    if isinstance(data["deployment_records"], list):
        for i, record in enumerate(data["deployment_records"]):
            if not isinstance(record, dict):
                errors.append(f"Deployment record {i} must be a dictionary")
                continue

            required_record_fields = SCHEMA_CONSTRAINTS["required_fields"]["DeploymentRecord"]
            for field in required_record_fields:
                if field not in record:
                    errors.append(f"Deployment record {i} missing required field: {field}")

    # Validate summaries structure
    if isinstance(data["summaries"], dict):
        for service_name, summary in data["summaries"].items():
            if not isinstance(summary, dict):
                errors.append(f"Service summary for '{service_name}' must be a dictionary")
                continue

            required_summary_fields = SCHEMA_CONSTRAINTS["required_fields"]["ServiceSummary"]
            for field in required_summary_fields:
                if field not in summary:
                    errors.append(f"Service summary '{service_name}' missing required field: {field}")

    return len(errors) == 0, errors


def example_whisper_stt_dataset() -> dict:
    """
    Generate example whisper-stt deployment data matching the schema.

    Returns example data structure following the exact pbx-web format.
    """
    return {
        "metadata": {
            "generated_at": "2026-08-06T10:30:00.000000+00:00",
            "source_files": [
                "whisper-stt-deployments-30d.json"
            ],
            "total_records": 4
        },
        "summaries": {
            "whisper-stt": {
                "service": "whisper-stt",
                "total_deployments": 2,
                "total_replicasets": 4,
                "successful_updates": 3,
                "failed_rollouts": 0,
                "rollback_events": 0,
                "last_deployment_update": "2026-07-12T16:54:57+00:00",
                "overall_health": "healthy",
                "deployment_stability": "high",
                "uptime_percentage": "100%",
                "zero_downtime_deployment": True,
                "successful_deployment_rate": "100%",
                "total_pods": 2,
                "running_pods": 2,
                "total_restarts": 0,
                "crashloops": 0,
                "oomkills": 0,
                "total_incidents": 0,
                "critical_incidents": 0,
                "warning_incidents": 0,
                "log_errors": 0
            }
        },
        "deployment_records": [
            {
                "service": "whisper-stt",
                "deployment_name": "whisper-stt",
                "replicaset_name": "whisper-stt-5dbff75cbd",
                "timestamp": "2026-07-08T03:09:35+00:00",
                "status": "success",
                "failure_type": None,
                "revision": "29",
                "replicas": 0,
                "ready_replicas": 0,
                "available_replicas": 0,
                "image": "ronaldraygun/whisper-stt:1.8.2",
                "cluster": "ardenone-cluster",
                "namespace": "whisper-stt"
            },
            {
                "service": "whisper-stt",
                "deployment_name": "whisper-stt",
                "replicaset_name": "whisper-stt-5b8558f478",
                "timestamp": "2026-07-08T03:16:13+00:00",
                "status": "success",
                "failure_type": None,
                "revision": "30",
                "replicas": 0,
                "ready_replicas": 0,
                "available_replicas": 0,
                "image": "ronaldraygun/whisper-stt:1.8.4",
                "cluster": "ardenone-cluster",
                "namespace": "whisper-stt"
            },
            {
                "service": "whisper-stt",
                "deployment_name": "whisper-stt",
                "replicaset_name": "whisper-stt-6c497489fb",
                "timestamp": "2026-07-08T03:26:44+00:00",
                "status": "success",
                "failure_type": None,
                "revision": "31",
                "replicas": 0,
                "ready_replicas": 0,
                "available_replicas": 0,
                "image": "ronaldraygun/whisper-stt:1.8.6",
                "cluster": "ardenone-cluster",
                "namespace": "whisper-stt"
            },
            {
                "service": "whisper-stt",
                "deployment_name": "whisper-stt",
                "replicaset_name": "whisper-stt-847fd8d7b9",
                "timestamp": "2026-07-12T16:53:42+00:00",
                "status": "success",
                "failure_type": None,
                "revision": "32",
                "replicas": 1,
                "ready_replicas": 1,
                "available_replicas": 1,
                "image": "ronaldraygun/whisper-stt:1.8.6",
                "cluster": "ardenone-cluster",
                "namespace": "whisper-stt"
            }
        ]
    }


if __name__ == "__main__":
    # Example usage and validation
    example_data = example_whisper_stt_dataset()

    is_valid, errors = validate_schema(example_data)
    print(f"Schema validation: {'PASSED' if is_valid else 'FAILED'}")

    if errors:
        print("Validation errors:")
        for error in errors:
            print(f"  - {error}")

    print("\nField type definitions:")
    for field, field_type in FIELD_TYPES.items():
        print(f"  {field}: {field_type}")