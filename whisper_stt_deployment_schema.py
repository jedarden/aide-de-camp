#!/usr/bin/env python3
"""
whisper-stt Deployment Data Schema Implementation

This module provides type definitions and validation for whisper-stt deployment data
matching the pbx-web format identified in previous analysis.

Schema Version: 1.0
Date: 2026-08-06
Bead ID: adc-63f3u

Usage:
    from whisper_stt_deployment_schema import (
        WhisperSTTDeploymentSchema,
        validate_deployment_data,
        schema_example
    )

    # Load and validate data
    data = json.load(open('whisper-stt-deployment-data.json'))
    schema = WhisperSTTDeploymentSchema(**data)

    # Or use standalone validation
    validation_result = validate_deployment_data(data)
    if validation_result["valid"]:
        print("✓ Schema validation passed")
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from dataclasses import dataclass, field


# ============================================================================
# Enums for Status Fields
# ============================================================================

class ReplicaStatus(str, Enum):
    """ReplicaSet status values."""
    SUCCESSFUL = "successful"
    ROLLED_OVER = "rolled_over"
    SCALED_DOWN_OR_FAILED = "scaled_down_or_failed"


class WorkflowStatus(str, Enum):
    """Argo Workflow status values."""
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    RUNNING = "Running"


class PodStatus(str, Enum):
    """Pod status values."""
    RUNNING = "Running"
    PENDING = "Pending"
    FAILED = "Failed"
    SUCCEEDED = "Succeeded"
    UNKNOWN = "Unknown"


class StorageStatus(str, Enum):
    """PVC status values."""
    BOUND = "Bound"
    PENDING = "Pending"
    LOST = "Lost"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TimestampedMixin:
    """Mixin class for timestamp validation."""

    @staticmethod
    def validate_timestamp(timestamp_str: str) -> datetime:
        """Validate ISO 8601 timestamp string."""
        if not timestamp_str:
            raise ValueError("Timestamp cannot be empty")

        try:
            # Handle various ISO formats
            ts = timestamp_str
            if ts.endswith('Z'):
                ts = ts[:-1] + '+00:00'
            return datetime.fromisoformat(ts.replace('+00:00', ''))
        except Exception as e:
            raise ValueError(f"Invalid ISO 8601 timestamp: {timestamp_str}") from e


@dataclass
class WorkflowRun(TimestampedMixin):
    """Argo Workflow run data."""
    workflow_name: str
    started_at: str
    status: WorkflowStatus
    finished_at: Optional[str] = None
    git_revision: Optional[str] = None
    image_tag: Optional[str] = None

    def __post_init__(self):
        """Validate timestamps after initialization."""
        self.validate_timestamp(self.started_at)
        if self.finished_at:
            self.validate_timestamp(self.finished_at)


@dataclass
class ArgoWorkflowData(TimestampedMixin):
    """Argo Workflow template and run data."""
    template_name: str
    template_created: str
    workflow_runs_last_30_days: int
    workflow_runs: List[WorkflowRun] = field(default_factory=list)

    def __post_init__(self):
        """Validate fields after initialization."""
        self.validate_timestamp(self.template_created)
        if self.workflow_runs_last_30_days < 0:
            raise ValueError("workflow_runs_last_30_days must be >= 0")
        if not isinstance(self.workflow_runs, list):
            raise ValueError("workflow_runs must be a list")


@dataclass
class ArgoCDApplication:
    """ArgoCD application data."""
    name: str
    namespace: str
    project: str = "default"
    sync_status: Optional[str] = None
    health_status: Optional[str] = None


@dataclass
class ArgoCDData:
    """ArgoCD application management data."""
    application_found: bool
    applications: List[ArgoCDApplication] = field(default_factory=list)

    def __post_init__(self):
        """Validate fields after initialization."""
        if not isinstance(self.applications, list):
            raise ValueError("applications must be a list")


@dataclass
class ReplicaHistoryEntry(TimestampedMixin):
    """ReplicaSet history entry."""
    name: str
    created_at: str
    image: str
    replicas: int
    status: ReplicaStatus
    days_ago: int
    available_replicas: Optional[int] = None
    ready_replicas: Optional[int] = None

    def __post_init__(self):
        """Validate fields after initialization."""
        self.validate_timestamp(self.created_at)
        if self.replicas < 0:
            raise ValueError("replicas must be >= 0")
        if self.days_ago < 0:
            raise ValueError("days_ago must be >= 0")
        # Validate status enum
        if isinstance(self.status, str):
            self.status = ReplicaStatus(self.status)


@dataclass
class ClusterDeploymentData(TimestampedMixin):
    """Kubernetes deployment data."""
    namespace: str
    deployment_name: str
    created_at: str
    current_image: str
    current_replicas: int
    replica_history: List[ReplicaHistoryEntry]
    deployments_last_30_days: int
    successful_deployments: int
    failed_deployments: int
    deployment_versions: List[str]
    all_versions_in_history: List[str]
    last_updated: Optional[str] = None

    def __post_init__(self):
        """Validate fields after initialization."""
        self.validate_timestamp(self.created_at)
        if self.last_updated:
            self.validate_timestamp(self.last_updated)
        if self.current_replicas < 0:
            raise ValueError("current_replicas must be >= 0")
        if self.deployments_last_30_days < 0:
            raise ValueError("deployments_last_30_days must be >= 0")
        if self.successful_deployments < 0:
            raise ValueError("successful_deployments must be >= 0")
        if self.failed_deployments < 0:
            raise ValueError("failed_deployments must be >= 0")


@dataclass
class PodContainer:
    """Container data within a pod."""
    name: str
    image: str
    ready: bool
    restart_count: int


@dataclass
class CurrentPod(TimestampedMixin):
    """Current pod data."""
    name: str
    created: str
    age_days: int
    status: PodStatus
    restart_count: int
    node: str
    containers: List[PodContainer] = field(default_factory=list)

    def __post_init__(self):
        """Validate fields after initialization."""
        self.validate_timestamp(self.created)
        if self.age_days < 0:
            raise ValueError("age_days must be >= 0")
        if self.restart_count < 0:
            raise ValueError("restart_count must be >= 0")
        # Validate status enum
        if isinstance(self.status, str):
            self.status = PodStatus(self.status)


@dataclass
class PodMetrics:
    """Pod health metrics."""
    total_pods: int
    running_pods: int
    total_containers: int
    total_restarts: int
    crashloops: int = 0
    oomkills: int = 0
    failed_pods: int = 0
    pending_pods: int = 0

    def __post_init__(self):
        """Validate fields after initialization."""
        if self.total_pods < 0:
            raise ValueError("total_pods must be >= 0")
        if self.running_pods < 0:
            raise ValueError("running_pods must be >= 0")
        if self.running_pods > self.total_pods:
            raise ValueError("running_pods cannot exceed total_pods")
        if self.total_restarts < 0:
            raise ValueError("total_restarts must be >= 0")


@dataclass
class StorageInfo:
    """Storage/PVC information."""
    capacity: str
    storage_class: str
    status: StorageStatus
    age_days: int

    def __post_init__(self):
        """Validate fields after initialization."""
        if self.age_days < 0:
            raise ValueError("age_days must be >= 0")
        if isinstance(self.status, str):
            self.status = StorageStatus(self.status)


@dataclass
class ErrorIncidents:
    """Error incident data."""
    total_incidents: int
    critical_incidents: int
    warning_incidents: int
    incident_details: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        """Validate fields after initialization."""
        if self.total_incidents < 0:
            raise ValueError("total_incidents must be >= 0")
        if self.critical_incidents < 0:
            raise ValueError("critical_incidents must be >= 0")
        if self.warning_incidents < 0:
            raise ValueError("warning_incidents must be >= 0")


@dataclass
class SummaryMetrics:
    """Summary metrics and statistics."""
    total_deployments_last_30_days: int
    whisper_stt_deployments: int
    successful_deployments: int
    failed_or_scaled_down: int
    data_coverage: str
    gaps_detected: bool
    largest_gap_days: int

    def __post_init__(self):
        """Validate fields after initialization."""
        if self.total_deployments_last_30_days < 0:
            raise ValueError("total_deployments_last_30_days must be >= 0")
        if self.whisper_stt_deployments < 0:
            raise ValueError("whisper_stt_deployments must be >= 0")
        if self.successful_deployments < 0:
            raise ValueError("successful_deployments must be >= 0")
        if self.failed_or_scaled_down < 0:
            raise ValueError("failed_or_scaled_down must be >= 0")
        if self.largest_gap_days < 0:
            raise ValueError("largest_gap_days must be >= 0")


@dataclass
class Metadata(TimestampedMixin):
    """Top-level metadata."""
    generated_at: str
    data_period_start: str
    data_period_end: str
    services: List[str]
    clusters: List[str]
    data_sources: List[str]

    def __post_init__(self):
        """Validate timestamps after initialization."""
        self.validate_timestamp(self.generated_at)
        self.validate_timestamp(self.data_period_start)
        self.validate_timestamp(self.data_period_end)

        # Validate timestamp ordering
        start = datetime.fromisoformat(self.data_period_start.replace('Z', '+00:00').replace('+00:00', ''))
        end = datetime.fromisoformat(self.data_period_end.replace('Z', '+00:00').replace('+00:00', ''))
        generated = datetime.fromisoformat(self.generated_at.replace('Z', '+00:00').replace('+00:00', ''))

        if start >= end:
            raise ValueError("data_period_start must be before data_period_end")
        if end > generated:
            raise ValueError("data_period_end must be before or equal to generated_at")


@dataclass
class WhisperSTTDeploymentSchema:
    """Complete schema for whisper-stt deployment data matching pbx-web format."""

    metadata: Metadata
    argo_workflows: Dict[str, ArgoWorkflowData]
    argo_cd: Dict[str, ArgoCDData]
    cluster_deployments: Dict[str, ClusterDeploymentData]
    summary: SummaryMetrics
    notes: List[str] = field(default_factory=list)

    # Optional extended fields
    pod_health: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None
    storage: Optional[Dict[str, StorageInfo]] = None
    error_incidents: Optional[ErrorIncidents] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WhisperSTTDeploymentSchema':
        """Create schema instance from dictionary, handling nested dataclass conversion."""
        # Convert metadata
        metadata = Metadata(**data["metadata"])

        # Convert argo_workflows
        argo_workflows = {}
        for key, wf_data in data.get("argo_workflows", {}).items():
            if isinstance(wf_data, dict):
                # Convert workflow runs
                workflow_runs = [WorkflowRun(**run) for run in wf_data.get("workflow_runs", [])]
                argo_workflows[key] = ArgoWorkflowData(
                    template_name=wf_data["template_name"],
                    template_created=wf_data["template_created"],
                    workflow_runs_last_30_days=wf_data["workflow_runs_last_30_days"],
                    workflow_runs=workflow_runs
                )

        # Convert argo_cd
        argo_cd = {}
        for key, cd_data in data.get("argo_cd", {}).items():
            if isinstance(cd_data, dict):
                applications = [ArgoCDApplication(**app) for app in cd_data.get("applications", [])]
                argo_cd[key] = ArgoCDData(
                    application_found=cd_data["application_found"],
                    applications=applications
                )

        # Convert cluster_deployments
        cluster_deployments = {}
        for key, deploy_data in data.get("cluster_deployments", {}).items():
            if isinstance(deploy_data, dict):
                replica_history = [ReplicaHistoryEntry(**entry) for entry in deploy_data.get("replica_history", [])]
                cluster_deployments[key] = ClusterDeploymentData(
                    namespace=deploy_data["namespace"],
                    deployment_name=deploy_data["deployment_name"],
                    created_at=deploy_data["created_at"],
                    current_image=deploy_data["current_image"],
                    current_replicas=deploy_data["current_replicas"],
                    last_updated=deploy_data.get("last_updated"),
                    replica_history=replica_history,
                    deployments_last_30_days=deploy_data["deployments_last_30_days"],
                    successful_deployments=deploy_data["successful_deployments"],
                    failed_deployments=deploy_data["failed_deployments"],
                    deployment_versions=deploy_data["deployment_versions"],
                    all_versions_in_history=deploy_data["all_versions_in_history"]
                )

        # Convert summary
        summary = SummaryMetrics(**data["summary"])

        # Convert error incidents if present
        error_incidents = None
        if "error_incidents" in data and data["error_incidents"]:
            error_incidents = ErrorIncidents(**data["error_incidents"])

        # Create the instance
        return cls(
            metadata=metadata,
            argo_workflows=argo_workflows,
            argo_cd=argo_cd,
            cluster_deployments=cluster_deployments,
            summary=summary,
            notes=data.get("notes", []),
            pod_health=data.get("pod_health"),
            resources=data.get("resources"),
            storage=data.get("storage"),
            error_incidents=error_incidents
        )

    def __post_init__(self):
        """Validate overall structure after initialization."""
        # Validate required top-level keys
        required_services = ["whisper-stt"]
        for service in required_services:
            if service not in self.metadata.services:
                raise ValueError(f"Service '{service}' must be in metadata.services")

        # Validate cluster_deployments has whisper-stt key
        if "whisper-stt" not in self.cluster_deployments:
            raise ValueError("cluster_deployments must contain 'whisper-stt' key")

        # Validate data consistency
        deployment_data = self.cluster_deployments["whisper-stt"]
        if deployment_data.successful_deployments + deployment_data.failed_deployments > deployment_data.deployments_last_30_days:
            raise ValueError("successful + failed deployments cannot exceed total deployments")


# ============================================================================
# Validation Functions
# ============================================================================

def validate_timestamp(timestamp_str: str) -> datetime:
    """Validate ISO 8601 timestamp string."""
    return TimestampedMixin.validate_timestamp(timestamp_str)


def validate_deployment_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate deployment data against the schema.

    Args:
        data: Dictionary containing deployment data

    Returns:
        Dictionary with validation results:
        {
            "valid": bool,
            "errors": List[str],
            "warnings": List[str],
            "schema": Optional[WhisperSTTDeploymentSchema]
        }
    """
    results = {
        "valid": False,
        "errors": [],
        "warnings": [],
        "schema": None
    }

    try:
        # Try to instantiate the schema using from_dict method
        schema = WhisperSTTDeploymentSchema.from_dict(data)
        results["schema"] = schema
        results["valid"] = True

    except TypeError as e:
        results["errors"].append(f"Type error: {e}")
    except ValueError as e:
        results["errors"].append(f"Validation error: {e}")
    except KeyError as e:
        results["errors"].append(f"Missing required field: {e}")
    except Exception as e:
        results["errors"].append(f"Unexpected error: {e}")

    return results


def validate_json_file(file_path: str) -> Dict[str, Any]:
    """
    Validate deployment data from a JSON file.

    Args:
        file_path: Path to JSON file containing deployment data

    Returns:
        Dictionary with validation results
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return validate_deployment_data(data)
    except FileNotFoundError:
        return {
            "valid": False,
            "errors": [f"File not found: {file_path}"],
            "warnings": [],
            "schema": None
        }
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "errors": [f"Invalid JSON: {e}"],
            "warnings": [],
            "schema": None
        }


# ============================================================================
# Schema Example
# ============================================================================

def schema_example() -> Dict[str, Any]:
    """
    Return a complete example of the schema structure.

    This can be used as a template or for testing.
    """
    return {
        "metadata": {
            "generated_at": "2026-08-06T09:30:00Z",
            "data_period_start": "2026-07-06T00:00:00Z",
            "data_period_end": "2026-08-06T09:30:00Z",
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes_replicasets", "argo_workflows", "argo_cd"]
        },
        "argo_workflows": {
            "whisper_stt_build": {
                "template_name": "whisper-stt-build",
                "template_created": "2026-05-27T02:26:47Z",
                "workflow_runs_last_30_days": 0,
                "workflow_runs": []
            }
        },
        "argo_cd": {
            "whisper-stt": {
                "application_found": False,
                "applications": []
            }
        },
        "cluster_deployments": {
            "whisper-stt": {
                "namespace": "whisper-stt",
                "deployment_name": "whisper-stt",
                "created_at": "2026-05-01T17:26:49Z",
                "current_image": "ronaldraygun/whisper-stt:1.8.6",
                "current_replicas": 1,
                "last_updated": "2026-07-12T16:54:57Z",
                "replica_history": [
                    {
                        "name": "whisper-stt-847fd8d7b9",
                        "created_at": "2026-07-12T16:53:42Z",
                        "image": "ronaldraygun/whisper-stt:1.8.6",
                        "replicas": 1,
                        "available_replicas": 1,
                        "ready_replicas": 1,
                        "status": "successful",
                        "days_ago": 25
                    },
                    {
                        "name": "whisper-stt-6c497489fb",
                        "created_at": "2026-07-08T03:26:44Z",
                        "image": "ronaldraygun/whisper-stt:1.8.6",
                        "replicas": 0,
                        "available_replicas": None,
                        "ready_replicas": None,
                        "status": "rolled_over",
                        "days_ago": 29
                    }
                ],
                "deployments_last_30_days": 4,
                "successful_deployments": 1,
                "failed_deployments": 3,
                "deployment_versions": ["1.8.6", "1.8.4", "1.8.2"],
                "all_versions_in_history": ["1.2.5", "1.3.0", "1.3.1", "1.4.1", "1.5.1", "1.6.0", "1.7.0", "1.8.2", "1.8.4", "1.8.6"]
            }
        },
        "summary": {
            "total_deployments_last_30_days": 4,
            "whisper_stt_deployments": 4,
            "successful_deployments": 1,
            "failed_or_scaled_down": 3,
            "data_coverage": "100%",
            "gaps_detected": False,
            "largest_gap_days": 0
        },
        "notes": [
            "No Argo Workflow runs found for whisper-stt in the last 30 days",
            "Deployments appear to be managed via ArgoCD or manual kubectl operations",
            "whisper-stt had multiple deployment attempts on 2026-07-08 before stabilizing on 2026-07-12",
            "Service is running on ardenone-cluster",
            "Current version: whisper-stt 1.8.6"
        ]
    }


# ============================================================================
# Main
# ============================================================================

def main():
    """Main function for testing and demonstration."""
    print("=" * 70)
    print("WHISPER-STT DEPLOYMENT SCHEMA VALIDATION")
    print("=" * 70)

    # Get example schema
    example = schema_example()

    # Validate the example
    results = validate_deployment_data(example)

    print(f"\nValidation Result: {'✓ PASSED' if results['valid'] else '✗ FAILED'}")

    if results["errors"]:
        print("\n❌ ERRORS:")
        for error in results["errors"]:
            print(f"  • {error}")

    if results["warnings"]:
        print("\n⚠️  WARNINGS:")
        for warning in results["warnings"]:
            print(f"  • {warning}")

    if results["valid"]:
        print("\n✓ Schema validation successful!")
        print(f"  - Metadata validated for period: {example['metadata']['data_period_start']} to {example['metadata']['data_period_end']}")
        print(f"  - Services: {', '.join(example['metadata']['services'])}")
        print(f"  - Clusters: {', '.join(example['metadata']['clusters'])}")

    return 0 if results["valid"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
