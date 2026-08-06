"""
Example Usage: Whisper-STT Deployment Data Persistence

This script demonstrates how to use the deployment data persistence module
to write and read whisper-stt deployment data in JSON format matching the
pbx-web structure.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.schemas.whisper_stt_deployment import (
    WhisperSTTDeploymentData,
    Metadata,
    TimePeriod,
    EventType,
    EventOutcome,
    HealthStatus
)

from src.persistence import (
    persist_deployment_data,
    load_deployment_data,
    DeploymentPersistenceError,
    get_default_path
)


def create_minimal_deployment_data():
    """
    Create minimal deployment data example.
    In production, this would be populated from kubectl queries.
    """
    now = datetime.now(tz=timedelta(hours=0))  # UTC
    thirty_days_ago = now - timedelta(days=30)

    # Build the complete deployment data structure
    # This would typically be populated from live cluster data
    # See tests/persistence/test_deployment_persistence.py for full example

    # For this demo, we'll load the test-generated file
    return None


def main():
    """Demonstrate persistence usage"""
    print("=" * 60)
    print("Whisper-STT Deployment Data Persistence Usage Example")
    print("=" * 60)

    # Example 1: Get default file path
    print("\n1. Default file path:")
    default_path = get_default_path(service_name="whisper-stt", days=30)
    print(f"   {default_path}")

    # Example 2: Load existing data
    print("\n2. Loading existing deployment data:")
    try:
        data = load_deployment_data(
            filepath=default_path,
            validate=True  # Validates against schema
        )
        print(f"   ✓ Loaded data for service: {data.metadata.service}")
        print(f"   ✓ Cluster: {data.metadata.cluster}")
        print(f"   ✓ Analysis period: {data.metadata.time_period.description}")
        print(f"   ✓ Current deployment: {data.current_status.current_image}")
        print(f"   ✓ Overall health: {data.summary.overall_health}")
    except DeploymentPersistenceError as e:
        print(f"   ✗ Error loading data: {e}")

    # Example 3: Persist with custom path
    print("\n3. Persisting to custom path:")
    custom_path = "/tmp/whisper-stt-deployments-custom.json"
    try:
        if data:
            written_path = persist_deployment_data(
                data=data,
                filepath=custom_path,
                indent=2,
                create_backup=True
            )
            print(f"   ✓ Written to: {written_path}")

            # Verify the write
            from src.persistence import verify_persistence
            is_valid = verify_persistence(data, filepath=written_path)
            print(f"   ✓ Verification passed: {is_valid}")
    except DeploymentPersistenceError as e:
        print(f"   ✗ Error persisting data: {e}")

    # Example 4: List deployment files
    print("\n4. Listing deployment files:")
    from src.persistence.deployment_persistence import list_deployment_files
    files = list_deployment_files(
        directory=str(Path.cwd()),
        pattern="*-deployments-*.json"
    )
    print(f"   Found {len(files)} deployment file(s):")
    for f in files:
        size = Path(f).stat().st_size
        print(f"   - {Path(f).name} ({size} bytes)")

    # Example 5: Using different time periods
    print("\n5. File paths for different time periods:")
    for days in [7, 30, 60, 90]:
        path = get_default_path(service_name="whisper-stt", days=days)
        print(f"   {days} days: {Path(path).name}")

    print("\n" + "=" * 60)
    print("Usage examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
