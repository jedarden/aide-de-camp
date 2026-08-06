"""
whisper-stt Deployment Data Schema

Pydantic models matching the pbx-web deployment data structure
for consistent comparative analysis between services.

Schema Version: 1.0
Last Updated: 2026-08-06
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class EventType(str, Enum):
    """Deployment event type categories"""
    DEPLOYMENT_ROLLOUT = "deployment_rollout"
    DEPLOYMENT_ROLLBACK = "deployment_rollback"
    SCALING_CHANGE = "scaling_change"
    CONFIG_CHANGE = "config_change"
    INFRASTRUCTURE_EVENT = "infrastructure_event"


class EventOutcome(str, Enum):
    """Event outcome status"""
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIAL = "partial"


class HealthStatus(str, Enum):
    """Overall service health status"""
    EXCELLENT = "excellent"
    GOOD = "good"
    DEGRADED = "degraded"
    POOR = "poor"
    CRITICAL = "critical"


class VolumeType(str, Enum):
    """Volume storage types"""
    PERSISTENT_VOLUME_CLAIM = "persistentVolumeClaim"
    EMPTY_DIR = "emptyDir"
    CONFIG_MAP = "configMap"
    SECRET = "secret"


class SecretType(str, Enum):
    """Secret management types"""
    SECRET = "Secret"
    EXTERNAL_SECRET = "ExternalSecret"
    SEALED_SECRET = "SealedSecret"


class StorageClass(str, Enum):
    """Rackspace Spot storage classes"""
    SATA = "sata"
    SATA_LARGE = "sata-large"
    SSD = "ssd"
    SSD_LARGE = "ssd-large"


# Metadata Models

class TimePeriod(BaseModel):
    """Analysis time period"""
    start: datetime = Field(..., description="Analysis window start")
    end: datetime = Field(..., description="Analysis window end")
    description: str = Field(..., description="Human-readable period")


class Metadata(BaseModel):
    """Top-level deployment metadata"""
    service: str = Field(default="whisper-stt", description="Service name")
    namespace: str = Field(default="whisper-stt", description="Kubernetes namespace")
    cluster: str = Field(default="ardenone-cluster", description="Cluster identifier")
    data_collected_at: datetime = Field(..., description="Data collection timestamp")
    time_period: TimePeriod = Field(..., description="Analysis time period")
    managed_by: str = Field(default="ArgoCD", description="Deployment management system")
    strategy: str = Field(default="Recreate", description="Deployment strategy")
    data_source: str = Field(default="kubectl read-only proxy", description="Data collection method")


# Condition Models

class DeploymentCondition(BaseModel):
    """Deployment condition status"""
    type: str = Field(..., description="Condition type (e.g., Progressing, Available)")
    status: str = Field(..., description="Condition status (True/False)")
    reason: str = Field(..., description="Human-readable reason")
    message: str = Field(..., description="Detailed condition message")
    lastTransitionTime: datetime = Field(..., description="Last state transition time")


class PodCondition(BaseModel):
    """Pod condition status"""
    type: str = Field(..., description="Condition type (e.g., Ready, PodScheduled)")
    status: str = Field(..., description="Condition status (True/False)")
    lastTransitionTime: datetime = Field(..., description="Last state transition time")


# Current Status Models

class CurrentStatus(BaseModel):
    """Current deployment status"""
    deployment_name: str = Field(default="whisper-stt", description="Deployment name")
    current_revision: int = Field(..., description="Current deployment revision")
    current_image: str = Field(..., description="Current container image")
    generation: int = Field(..., description="Kubernetes generation")
    replicas: int = Field(..., description="Desired replica count")
    readyReplicas: int = Field(..., description="Ready replica count")
    updatedReplicas: int = Field(..., description="Updated replica count")
    availableReplicas: int = Field(..., description="Available replica count")
    current_pod: str = Field(..., description="Current primary pod name")
    pod_created_at: datetime = Field(..., description="Pod creation timestamp")
    conditions: List[DeploymentCondition] = Field(default_factory=list, description="Deployment conditions")


# Deployment Event Models

class DeploymentEvent(BaseModel):
    """Deployment event record"""
    date: str = Field(..., description="Event date (YYYY-MM-DD)")
    timestamp: datetime = Field(..., description="Event timestamp (ISO 8601)")
    event_type: EventType = Field(..., description="Event category")
    outcome: EventOutcome = Field(..., description="Event outcome")
    revision: int = Field(..., description="Deployment revision")
    replicaSet: str = Field(..., description="ReplicaSet name")
    image: str = Field(..., description="Container image")
    previous_image: Optional[str] = Field(None, description="Previous image if applicable")
    pod_name: Optional[str] = Field(None, description="Created pod name")
    pod_ready: Optional[bool] = Field(None, description="Pod readiness status")
    restart_count: int = Field(default=0, description="Container restart count")
    rollback_from: Optional[str] = Field(None, description="Source revision if rollback")
    notes: Optional[str] = Field(None, description="Additional context notes")


# Container Models

class ContainerState(BaseModel):
    """Container state information"""
    name: str = Field(..., description="Container name")
    ready: bool = Field(..., description="Container readiness")
    restart_count: int = Field(default=0, description="Container restart count")
    image: str = Field(..., description="Container image")
    image_id: str = Field(..., description="Container image ID (digest)")
    state: str = Field(..., description="Container state (running, waiting, terminated)")
    started_at: Optional[datetime] = Field(None, description="Container start time")


class VolumeMount(BaseModel):
    """Volume mount information"""
    name: str = Field(..., description="Volume name")
    path: str = Field(..., description="Mount path")
    type: str = Field(..., description="Mount type")


class CurrentPod(BaseModel):
    """Current pod information"""
    name: str = Field(..., description="Pod name")
    namespace: str = Field(default="whisper-stt", description="Pod namespace")
    created_at: datetime = Field(..., description="Pod creation timestamp")
    node_name: str = Field(..., description="Node hosting the pod")
    pod_ip: str = Field(..., description="Pod IP address")
    phase: str = Field(..., description="Pod phase (Running, Pending, Failed, etc.)")
    ready: bool = Field(..., description="Pod readiness status")
    restart_count: int = Field(default=0, description="Total container restarts")
    containers: List[ContainerState] = Field(default_factory=list, description="Container states")
    conditions: List[PodCondition] = Field(default_factory=list, description="Pod conditions")
    volume_mounts: List[VolumeMount] = Field(default_factory=list, description="Volume mounts")


class HealthIndicators(BaseModel):
    """Pod health metrics"""
    total_pods: int = Field(..., description="Total pods in deployment")
    healthy_pods: int = Field(..., description="Healthy pod count")
    unhealthy_pods: int = Field(default=0, description="Unhealthy pod count")
    failed_pods: int = Field(default=0, description="Failed pod count")
    pending_pods: int = Field(default=0, description="Pending pod count")
    success_rate: float = Field(..., ge=0.0, le=1.0, description="Pod success rate (0-1)")
    total_restarts: int = Field(default=0, description="Total container restarts")
    avg_pod_age_days: float = Field(..., description="Average pod age in days")
    oldest_pod_age_days: float = Field(..., description="Oldest pod age in days")
    pvc_mount_issues: int = Field(default=0, description="PVC mounting problem count")


class PodHealth(BaseModel):
    """Pod health information"""
    current_pod: CurrentPod = Field(..., description="Current pod details")
    health_indicators: HealthIndicators = Field(..., description="Health metrics")


# Metrics Models

class DeploymentMetrics(BaseModel):
    """Deployment performance metrics"""
    total_deployments_last_30_days: int = Field(..., description="Total deployments in 30-day window")
    successful_deployments: int = Field(..., description="Successful deployment count")
    failed_deployments: int = Field(default=0, description="Failed deployment count")
    deployment_frequency_days: float = Field(..., description="Average days between deployments")
    unique_images_deployed: int = Field(..., description="Unique image versions deployed")
    images_used_last_30_days: List[str] = Field(default_factory=list, description="Image history")
    current_uptime_days: int = Field(..., description="Days since current deployment")
    last_deployment: datetime = Field(..., description="Last deployment timestamp")
    days_since_last_deployment: int = Field(..., description="Days since last deployment")
    rollbacks_last_30_days: int = Field(default=0, description="Rollback count")
    deployment_success_rate: float = Field(..., ge=0.0, le=1.0, description="Success rate (0-1)")


# Log Models

class LogEntry(BaseModel):
    """Log entry structure"""
    timestamp: datetime = Field(..., description="Log timestamp")
    pod: str = Field(..., description="Pod name")
    container: str = Field(..., description="Container name")
    level: str = Field(..., description="Log level (ERROR, WARNING, INFO)")
    message: str = Field(..., description="Log message")


class StartupEvent(BaseModel):
    """Pod startup event"""
    timestamp: datetime = Field(..., description="Event timestamp")
    pod: str = Field(..., description="Pod name")
    event: str = Field(..., description="Event description")


class OperationalLogs(BaseModel):
    """Operational log samples"""
    recent_errors: List[LogEntry] = Field(default_factory=list, description="Recent error logs")
    recent_warnings: List[LogEntry] = Field(default_factory=list, description="Recent warning logs")
    startup_events: List[StartupEvent] = Field(default_factory=list, description="Pod startup events")


# Infrastructure Models

class ResourceSpec(BaseModel):
    """Resource specification"""
    request: str = Field(..., description="Resource request (e.g., '500m', '4Gi')")
    limit: str = Field(..., description="Resource limit (e.g., '8', '8Gi')")


class ContainerResources(BaseModel):
    """Container resource requirements"""
    cpu: ResourceSpec = Field(..., description="CPU resources")
    memory: ResourceSpec = Field(..., description="Memory resources")


class VolumeConfig(BaseModel):
    """Volume configuration"""
    name: str = Field(..., description="Volume name")
    type: VolumeType = Field(..., description="Volume type")
    claim: Optional[str] = Field(None, description="PVC claim name if applicable")
    size: Optional[str] = Field(None, description="Volume size (e.g., '10Gi')")
    storage_class: Optional[StorageClass] = Field(None, description="Storage class")
    mount_path: str = Field(..., description="Mount path")
    read_only: bool = Field(default=False, description="Read-only mount")
    medium: Optional[str] = Field(None, description="EmptyDir medium (Memory, default)")
    size_limit: Optional[str] = Field(None, description="EmptyDir size limit")


class SecretReference(BaseModel):
    """Secret reference"""
    name: str = Field(..., description="Secret name")
    keys: List[str] = Field(..., description="Secret keys")
    type: SecretType = Field(..., description="Secret management type")


class ProbeConfig(BaseModel):
    """Health probe configuration"""
    enabled: bool = Field(default=True, description="Probe enabled")
    path: str = Field(..., description="Health check path")
    port: int = Field(..., description="Health check port")
    initial_delay_seconds: int = Field(..., description="Initial delay before probing")
    period_seconds: int = Field(..., description="Probe period")
    timeout_seconds: int = Field(..., description="Probe timeout")
    failure_threshold: int = Field(..., description="Failure threshold")


class NodeAffinity(BaseModel):
    """Node affinity configuration"""
    preferred_during_scheduling: Optional[dict] = Field(None, description="Preferred scheduling terms")


class InfrastructureDetails(BaseModel):
    """Infrastructure configuration details"""
    resource_limits: dict = Field(..., description="Resource requirements per container")
    volumes: List[VolumeConfig] = Field(default_factory=list, description="Volume configurations")
    environment_variables: dict = Field(default_factory=dict, description="Key environment variables")
    secrets_used: List[SecretReference] = Field(default_factory=list, description="Secret references")
    liveness_probes: dict = Field(default_factory=dict, description="Liveness probe configurations")
    readiness_probes: dict = Field(default_factory=dict, description="Readiness probe configurations")
    node_affinity: Optional[NodeAffinity] = Field(None, description="Node placement rules")


# Summary Models

class CriticalIssue(BaseModel):
    """Critical issue description"""
    issue: str = Field(..., description="Issue description")
    duration: str = Field(..., description="Issue duration")
    impact: str = Field(..., description="Business impact")


class Summary(BaseModel):
    """Executive summary"""
    overall_health: HealthStatus = Field(..., description="Overall service health")
    deployment_stability: str = Field(..., description="Deployment stability assessment")
    uptime: str = Field(..., description="Human-readable uptime")
    issues_last_30_days: int = Field(default=0, description="Total issues/incidents")
    rollbacks_last_30_days: int = Field(default=0, description="Rollback operations")
    deployment_success_rate: str = Field(..., description="Formatted success rate (e.g., '85.7%')")
    critical_issues: List[CriticalIssue] = Field(default_factory=list, description="Critical problems")
    recommendation: str = Field(..., description="Operational recommendation")


# Main Deployment Data Model

class WhisperSTTDeploymentData(BaseModel):
    """
    Complete whisper-stt deployment data structure
    matching pbx-web format for comparative analysis
    """
    metadata: Metadata = Field(..., description="Deployment metadata")
    current_status: CurrentStatus = Field(..., description="Current deployment status")
    deployment_events_last_30_days: List[DeploymentEvent] = Field(
        default_factory=list,
        description="Deployment events in 30-day window"
    )
    historical_deployments_beyond_30_days: List[DeploymentEvent] = Field(
        default_factory=list,
        description="Historical deployments beyond 30-day window"
    )
    deployment_metrics: DeploymentMetrics = Field(..., description="Deployment performance metrics")
    pod_health: PodHealth = Field(..., description="Pod health information")
    operational_logs_sample: OperationalLogs = Field(
        default_factory=OperationalLogs,
        description="Operational log samples"
    )
    infrastructure_details: InfrastructureDetails = Field(..., description="Infrastructure configuration")
    summary: Summary = Field(..., description="Executive summary")

    class Config:
        """Pydantic configuration"""
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z' if v else None
        }
        schema_extra = {
            "example": {
                "metadata": {
                    "service": "whisper-stt",
                    "namespace": "whisper-stt",
                    "cluster": "ardenone-cluster"
                }
            }
        }


# Validation Functions

def validate_deployment_data(data: dict) -> bool:
    """
    Validate deployment data structure matches schema

    Args:
        data: Dictionary containing deployment data

    Returns:
        bool: True if valid, raises ValidationError if invalid
    """
    try:
        WhisperSTTDeploymentData(**data)
        return True
    except Exception as e:
        raise ValueError(f"Schema validation failed: {e}")


def calculate_success_rate(successful: int, total: int) -> float:
    """
    Calculate deployment success rate

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
    Format success rate as percentage string

    Args:
        rate: Success rate decimal (0-1)

    Returns:
        str: Formatted percentage (e.g., '85.7%')
    """
    return f"{rate * 100:.1f}%"


# Export main model
__all__ = [
    "WhisperSTTDeploymentData",
    "validate_deployment_data",
    "calculate_success_rate",
    "format_success_rate",
    "EventType",
    "EventOutcome",
    "HealthStatus",
    "VolumeType",
    "SecretType",
    "StorageClass",
]
