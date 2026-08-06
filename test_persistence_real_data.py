#!/usr/bin/env python3
"""
Test script to convert existing whisper-stt data to the new schema format
and persist it using the persistence module.
"""

import json
from datetime import datetime, timedelta
from persist_whisper_stt_deployment import persist_deployment_data, load_deployment_data, verify_json_file

def convert_existing_data():
    """Convert existing whisper-stt data to the new schema format."""

    # Load the existing whisper-stt deployment data
    with open('whisper-stt-deployment-data-30days.json', 'r') as f:
        existing_data = json.load(f)

    # Transform to the new schema format
    schema_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat() + 'Z',
            "data_period_start": existing_data["report_metadata"]["time_range_start"],
            "data_period_end": existing_data["report_metadata"]["time_range_end"],
            "services": ["whisper-stt", "whisper-openai"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes_replicasets", "argo_cd"]
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
                "application_found": True,
                "applications": [
                    {
                        "name": "whisper-stt",
                        "namespace": "whisper-stt",
                        "project": "default",
                        "sync_status": "Synced",
                        "health_status": "Healthy"
                    },
                    {
                        "name": "whisper-openai",
                        "namespace": "whisper-stt",
                        "project": "default",
                        "sync_status": "Synced",
                        "health_status": "Healthy"
                    }
                ]
            }
        },
        "cluster_deployments": {
            "whisper-stt": {
                "namespace": "whisper-stt",
                "deployment_name": "whisper-stt",
                "created_at": existing_data["current_status"]["deployments"]["whisper-stt"]["creationTimestamp"],
                "current_image": existing_data["current_status"]["deployments"]["whisper-stt"]["images"]["whisper-stt"],
                "current_replicas": existing_data["current_status"]["deployments"]["whisper-stt"]["replicas"],
                "last_updated": "2026-07-12T16:54:57Z",
                "replica_history": [],
                "deployments_last_30_days": existing_data["deployment_history_30_days"]["deployment_events_summary"]["total_deployments"],
                "successful_deployments": existing_data["deployment_history_30_days"]["deployment_events_summary"].get("successful_rollouts", existing_data["deployment_history_30_days"]["deployment_events_summary"]["total_deployments"]),
                "failed_deployments": existing_data["deployment_history_30_days"]["deployment_events_summary"].get("failed_rollouts", 0),
                "deployment_versions": ["1.8.6"],
                "all_versions_in_history": ["1.8.6"]
            }
        },
        "summary": {
            "total_deployments_last_30_days": existing_data["deployment_history_30_days"]["deployment_events_summary"]["total_deployments"],
            "whisper_stt_deployments": 1,
            "successful_deployments": existing_data["deployment_history_30_days"]["deployment_events_summary"].get("successful_rollouts", existing_data["deployment_history_30_days"]["deployment_events_summary"]["total_deployments"]),
            "failed_or_scaled_down": existing_data["deployment_history_30_days"]["deployment_events_summary"].get("failed_rollouts", 0),
            "data_coverage": "100%",
            "gaps_detected": False,
            "largest_gap_days": 0
        },
        "pod_health": {
            "current_pods": existing_data["pod_status"]["current_pods"],
            "pod_metrics": existing_data["pod_status"]["pod_metrics"]
        },
        "resources": {
            "whisper-stt": existing_data["current_status"]["deployments"]["whisper-stt"]["resources"]
        },
        "storage": {
            "whisper-model-cache": {
                "capacity": "10Gi",
                "storage_class": "longhorn",
                "status": "Bound",
                "age_days": 84
            }
        },
        "error_incidents": existing_data["error_incidents"],
        "notes": [
            "Converted from existing deployment data format",
            "Service running on ardenone-cluster",
            "Current version: whisper-stt 1.8.6",
            "Zero incidents, zero downtime, zero restarts"
        ]
    }

    return schema_data

def main():
    """Main function to test conversion and persistence."""
    print("=" * 70)
    print("CONVERTING EXISTING WHISPER-STT DATA TO NEW SCHEMA FORMAT")
    print("=" * 70)

    try:
        # Convert existing data
        print("\nConverting existing data...")
        schema_data = convert_existing_data()
        print("✓ Data converted successfully")

        # Persist to default file path
        output_file = "whisper-stt-deployments-30d.json"
        print(f"\nPersisting to {output_file}...")

        success = persist_deployment_data(schema_data, output_file)

        if success:
            print(f"✓ Successfully persisted to {output_file}")

            # Verify the file
            verification = verify_json_file(output_file)
            print(f"\nFile Verification:")
            print(f"  Valid: {verification['valid']}")
            print(f"  Size: {verification['size_bytes']} bytes")
            print(f"  Structure OK: {verification['structure_ok']}")

            # Load and verify
            loaded_data = load_deployment_data(output_file)
            if loaded_data:
                print(f"\n✓ Successfully loaded and validated data")
                print(f"  - Metadata period: {loaded_data['metadata']['data_period_start']} to {loaded_data['metadata']['data_period_end']}")
                print(f"  - Services: {', '.join(loaded_data['metadata']['services'])}")
                print(f"  - Clusters: {', '.join(loaded_data['metadata']['clusters'])}")
                print(f"  - Total deployments: {loaded_data['summary']['total_deployments_last_30_days']}")

            return 0
        else:
            print("✗ Persistence failed")
            return 1

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
