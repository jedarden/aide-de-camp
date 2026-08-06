"""
Test script for deployment data persistence

Verifies that the persistence module correctly writes and reads
deployment data matching the pbx-web structure.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.schemas.whisper_stt_deployment import (
    WhisperSTTDeploymentData,
    Metadata,
    TimePeriod,
    CurrentStatus,
    DeploymentCondition,
    DeploymentEvent,
    EventType,
    EventOutcome,
    DeploymentMetrics,
    CurrentPod,
    ContainerState,
    HealthIndicators,
    PodHealth,
    OperationalLogs,
    InfrastructureDetails,
    Summary,
    HealthStatus,
    calculate_success_rate,
    format_success_rate
)

from src.persistence.deployment_persistence import (
    persist_deployment_data,
    load_deployment_data,
    verify_persistence,
    get_default_path,
    DeploymentPersistenceError
)


def create_sample_data():
    """Create sample whisper-stt deployment data"""
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    # Metadata
    metadata = Metadata(
        service="whisper-stt",
        namespace="whisper-stt",
        cluster="ardenone-cluster",
        data_collected_at=now,
        time_period=TimePeriod(
            start=thirty_days_ago,
            end=now,
            description="Last 30 days"
        ),
        managed_by="ArgoCD",
        strategy="Recreate",
        data_source="kubectl read-only proxy"
    )

    # Current status
    current_status = CurrentStatus(
        deployment_name="whisper-stt",
        current_revision=32,
        current_image="ronaldraygun/whisper-stt:1.8.6",
        generation=353,
        replicas=1,
        readyReplicas=1,
        updatedReplicas=1,
        availableReplicas=1,
        current_pod="whisper-stt-847fd8d7b9-v2rs5",
        pod_created_at=now - timedelta(days=25),
        conditions=[
            DeploymentCondition(
                type="Progressing",
                status="True",
                reason="NewReplicaSetAvailable",
                message="ReplicaSet \"whisper-stt-847fd8d7b9\" has successfully progressed.",
                lastTransitionTime=now - timedelta(days=25)
            ),
            DeploymentCondition(
                type="Available",
                status="True",
                reason="MinimumReplicasAvailable",
                message="Deployment has minimum availability.",
                lastTransitionTime=now - timedelta(days=25)
            )
        ]
    )

    # Deployment events
    deployment_events = [
        DeploymentEvent(
            date=(now - timedelta(days=25)).strftime("%Y-%m-%d"),
            timestamp=now - timedelta(days=25),
            event_type=EventType.DEPLOYMENT_ROLLOUT,
            outcome=EventOutcome.SUCCESS,
            revision=32,
            replicaSet="whisper-stt-847fd8d7b9",
            image="ronaldraygun/whisper-stt:1.8.6",
            pod_name="whisper-stt-847fd8d7b9-v2rs5",
            pod_ready=True,
            restart_count=0,
            notes="Current active deployment"
        )
    ]

    # Deployment metrics
    success_rate = calculate_success_rate(1, 1)
    deployment_metrics = DeploymentMetrics(
        total_deployments_last_30_days=1,
        successful_deployments=1,
        failed_deployments=0,
        deployment_frequency_days=30.0,
        unique_images_deployed=1,
        images_used_last_30_days=["ronaldraygun/whisper-stt:1.8.6"],
        current_uptime_days=25,
        last_deployment=now - timedelta(days=25),
        days_since_last_deployment=25,
        rollbacks_last_30_days=0,
        deployment_success_rate=success_rate
    )

    # Current pod
    container = ContainerState(
        name="whisper-stt",
        ready=True,
        restart_count=0,
        image="ronaldraygun/whisper-stt:1.8.6",
        image_id="docker.io/ronaldraygun/whisper-stt@sha256:abc123",
        state="running",
        started_at=now - timedelta(days=25)
    )

    current_pod = CurrentPod(
        name="whisper-stt-847fd8d7b9-v2rs5",
        namespace="whisper-stt",
        created_at=now - timedelta(days=25),
        node_name="k3s-agent-minisforum",
        pod_ip="10.42.0.45",
        phase="Running",
        ready=True,
        restart_count=0,
        containers=[container]
    )

    health_indicators = HealthIndicators(
        total_pods=1,
        healthy_pods=1,
        unhealthy_pods=0,
        success_rate=1.0,
        total_restarts=0,
        avg_pod_age_days=25.0,
        oldest_pod_age_days=25.0
    )

    pod_health = PodHealth(
        current_pod=current_pod,
        health_indicators=health_indicators
    )

    # Operational logs
    operational_logs = OperationalLogs()

    # Infrastructure details
    infrastructure_details = InfrastructureDetails(
        resource_limits={
            "whisper-stt": {
                "cpu": {"request": "1", "limit": "8"},
                "memory": {"request": "4Gi", "limit": "8Gi"}
            }
        },
        environment_variables={
            "MODEL_SIZE": "medium",
            "WHISPER_DEVICE": "cpu"
        }
    )

    # Summary
    summary = Summary(
        overall_health=HealthStatus.EXCELLENT,
        deployment_stability="stable",
        uptime="25 days continuous",
        issues_last_30_days=0,
        rollbacks_last_30_days=0,
        deployment_success_rate=format_success_rate(success_rate),
        recommendation="Service is healthy with stable deployment pattern."
    )

    # Complete deployment data
    return WhisperSTTDeploymentData(
        metadata=metadata,
        current_status=current_status,
        deployment_events_last_30_days=deployment_events,
        historical_deployments_beyond_30_days=[],
        deployment_metrics=deployment_metrics,
        pod_health=pod_health,
        operational_logs_sample=operational_logs,
        infrastructure_details=infrastructure_details,
        summary=summary
    )


def test_basic_persistence():
    """Test basic write and read functionality"""
    print("Testing basic persistence...")

    # Create sample data
    data = create_sample_data()
    print(f"✓ Created sample deployment data")

    # Get default path
    filepath = get_default_path("whisper-stt", 30)
    print(f"✓ Default path: {filepath}")

    # Persist data
    try:
        written_path = persist_deployment_data(data, filepath)
        print(f"✓ Successfully persisted data to: {written_path}")
    except Exception as e:
        print(f"✗ Failed to persist data: {e}")
        return False

    # Load data
    try:
        loaded_data = load_deployment_data(filepath, validate=True)
        print(f"✓ Successfully loaded and validated data")
    except Exception as e:
        print(f"✗ Failed to load data: {e}")
        return False

    # Verify data integrity
    if loaded_data.metadata.service != data.metadata.service:
        print(f"✗ Data mismatch: service name")
        return False

    if loaded_data.summary.overall_health != data.summary.overall_health:
        print(f"✗ Data mismatch: overall health")
        return False

    print(f"✓ Data integrity verified")

    # Verify file structure
    try:
        with open(filepath, 'r') as f:
            json_data = json.load(f)

        # Check top-level structure matches pbx-web format
        required_keys = [
            'metadata', 'current_status', 'deployment_events_last_30_days',
            'deployment_metrics', 'pod_health', 'operational_logs_sample',
            'infrastructure_details', 'summary'
        ]

        for key in required_keys:
            if key not in json_data:
                print(f"✗ Missing required key: {key}")
                return False

        print(f"✓ JSON structure matches pbx-web format")
        print(f"✓ All required keys present: {', '.join(required_keys)}")

    except Exception as e:
        print(f"✗ Failed to verify file structure: {e}")
        return False

    return True


def test_error_handling():
    """Test error handling"""
    print("\nTesting error handling...")

    # Test invalid data
    try:
        persist_deployment_data({"invalid": "data"})
        print("✗ Should have raised validation error")
        return False
    except DeploymentPersistenceError as e:
        print(f"✓ Correctly raised DeploymentPersistenceError for invalid data")

    # Test non-existent directory (should create)
    test_path = "/tmp/test-deployment-persistence/test-file.json"
    try:
        data = create_sample_data()
        persist_deployment_data(data, test_path)
        print(f"✓ Created directory structure automatically")
    except Exception as e:
        print(f"✗ Failed to create directory: {e}")
        return False

    # Test loading non-existent file
    try:
        load_deployment_data("/non/existent/path.json")
        print("✗ Should have raised error for non-existent file")
        return False
    except DeploymentPersistenceError as e:
        print(f"✓ Correctly raised DeploymentPersistenceError for missing file")

    return True


def test_custom_paths():
    """Test custom file paths"""
    print("\nTesting custom file paths...")

    data = create_sample_data()

    # Test custom path
    custom_path = "/tmp/whisper-stt-custom-60d.json"
    try:
        persist_deployment_data(
            data,
            filepath=custom_path,
            service_name="whisper-stt",
            days=60
        )
        print(f"✓ Successfully persisted to custom path: {custom_path}")

        # Load from custom path
        loaded = load_deployment_data(custom_path)
        print(f"✓ Successfully loaded from custom path")

    except Exception as e:
        print(f"✗ Failed with custom path: {e}")
        return False

    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("Deployment Data Persistence Test Suite")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Basic Persistence", test_basic_persistence()))
    results.append(("Error Handling", test_error_handling()))
    results.append(("Custom Paths", test_custom_paths()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        symbol = "✓" if passed else "✗"
        print(f"{symbol} {test_name}: {status}")

    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)

    print(f"\n{total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total_tests - total_passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
