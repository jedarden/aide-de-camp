#!/usr/bin/env python3
"""
Load and validate pbx-web and whisper-stt deployment datasets.
"""

import json
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class DatasetValidator:
    """Validator for deployment dataset JSON files."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.data: Dict[str, Any] = {}
        self.errors = []
        self.warnings = []

    def load(self) -> bool:
        """Load JSON file."""
        try:
            with open(self.filepath, 'r') as f:
                self.data = json.load(f)
            return True
        except json.JSONDecodeError as e:
            self.errors.append(f"JSON decode error: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Load error: {e}")
            return False

    def validate_structure(self) -> bool:
        """Validate the structure of the loaded JSON."""
        required_sections = [
            'report_metadata',
            'current_status',
            'deployment_history_30_days',
            'pod_status',
            'operational_metrics',
            'argo_cd_integration',
            'error_incidents',
            'deployment_health_assessment',
            'summary'
        ]

        for section in required_sections:
            if section not in self.data:
                self.errors.append(f"Missing required section: {section}")
            elif not isinstance(self.data[section], dict):
                self.errors.append(f"Section '{section}' is not a dict")

        # Validate metadata
        if 'report_metadata' in self.data:
            metadata = self.data['report_metadata']
            metadata_fields = [
                'generated_at', 'time_range_start', 'time_range_end',
                'cluster', 'service', 'namespace'
            ]
            for field in metadata_fields:
                if field not in metadata:
                    self.warnings.append(f"Missing metadata field: {field}")

        return len(self.errors) == 0

    def get_statistics(self) -> Dict[str, Any]:
        """Extract statistics from the dataset."""
        stats = {
            'service': self.data.get('report_metadata', {}).get('service', 'unknown'),
            'namespace': self.data.get('report_metadata', {}).get('namespace', 'unknown'),
            'cluster': self.data.get('report_metadata', {}).get('cluster', 'unknown'),
            'time_range_start': self.data.get('report_metadata', {}).get('time_range_start'),
            'time_range_end': self.data.get('report_metadata', {}).get('time_range_end'),
        }

        # Deployment count
        deployments = self.data.get('current_status', {}).get('deployments', {})
        stats['deployment_count'] = len(deployments)

        # ReplicaSet count
        replicasets = self.data.get('deployment_history_30_days', {}).get('replicasets', [])
        stats['replicaset_count'] = len(replicasets)

        # Pod metrics
        pod_metrics = self.data.get('pod_status', {}).get('pod_metrics', {})
        stats.update({
            'total_pods': pod_metrics.get('total_pods', 0),
            'running_pods': pod_metrics.get('running_pods', 0),
            'total_restarts': pod_metrics.get('total_restarts', 0),
            'crashloops': pod_metrics.get('crashloops', 0),
        })

        # Error incidents
        error_incidents = self.data.get('error_incidents', {})
        stats.update({
            'total_incidents': error_incidents.get('total_incidents', 0),
            'critical_incidents': error_incidents.get('critical_incidents', 0),
        })

        # Health assessment
        health = self.data.get('deployment_health_assessment', {})
        stats['overall_health'] = health.get('overall_health', 'unknown')

        return stats

    def print_report(self):
        """Print validation report."""
        print(f"\n{'='*70}")
        print(f"Dataset: {self.filepath.name}")
        print(f"{'='*70}")

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")

        if not self.errors and not self.warnings:
            print("\n✅ Validation passed with no errors or warnings")

        # Print statistics
        stats = self.get_statistics()
        print(f"\n📊 STATISTICS:")
        print(f"  Service: {stats['service']}")
        print(f"  Namespace: {stats['namespace']}")
        print(f"  Cluster: {stats['cluster']}")
        print(f"  Time range: {stats['time_range_start']} to {stats['time_range_end']}")
        print(f"  Deployments: {stats['deployment_count']}")
        print(f"  ReplicaSets (30d): {stats['replicaset_count']}")
        print(f"  Total pods: {stats['total_pods']} ({stats['running_pods']} running)")
        print(f"  Restarts: {stats['total_restarts']}")
        print(f"  Crashloops: {stats['crashloops']}")
        print(f"  Incidents: {stats['total_incidents']} ({stats['critical_incidents']} critical)")
        print(f"  Overall health: {stats['overall_health']}")


def main():
    """Main validation entry point."""
    base_path = Path('/home/coding/aide-de-camp/docs/research')

    datasets = [
        base_path / 'pbx-web-deployments-30d.json',
        base_path / 'whisper-stt-deployments-30d.json',
    ]

    all_data = {}
    all_valid = True

    print("\n🔍 Loading and validating deployment datasets...")
    print(f"Timestamp: {datetime.now().isoformat()}")

    for dataset_path in datasets:
        if not dataset_path.exists():
            print(f"\n❌ File not found: {dataset_path}")
            all_valid = False
            continue

        validator = DatasetValidator(dataset_path)

        if not validator.load():
            print(f"\n❌ Failed to load: {dataset_path.name}")
            all_valid = False
            continue

        if not validator.validate_structure():
            print(f"\n❌ Structure validation failed: {dataset_path.name}")
            all_valid = False

        validator.print_report()

        # Store for next step
        service_name = validator.data.get('report_metadata', {}).get('service', dataset_path.stem)
        all_data[service_name] = validator.data

    # Save combined data for next task
    output_path = Path('/tmp/deployment_datasets.pkl')
    with open(output_path, 'wb') as f:
        pickle.dump(all_data, f)

    print(f"\n💾 Combined data saved to: {output_path}")

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"  Total datasets processed: {len(datasets)}")
    print(f"  Successful: {len(all_data)}")
    print(f"  Failed: {len(datasets) - len(all_data)}")

    if all_valid:
        print(f"\n✅ All datasets loaded and validated successfully")
        return 0
    else:
        print(f"\n❌ Some datasets failed validation")
        return 1


if __name__ == '__main__':
    sys.exit(main())
