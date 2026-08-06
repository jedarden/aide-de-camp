#!/usr/bin/env python3
"""
Load and validate deployment datasets for pbx-web and whisper-stt services.
This script validates the data structure and completeness of both datasets.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple
import sys


class DeploymentDataValidator:
    """Validator for deployment dataset structure and completeness."""

    REQUIRED_PBX_FIELDS = [
        'timestamp', 'event_type', 'outcome'
    ]

    REQUIRED_WHISPER_FIELDS = [
        'created', 'status', 'deployment', 'image'
    ]

    def __init__(self):
        self.validation_results = {
            'pbx-web': {'loaded': False, 'valid': False, 'errors': [], 'warnings': []},
            'whisper-stt': {'loaded': False, 'valid': False, 'errors': [], 'warnings': []}
        }

    def load_json_file(self, filepath: Path) -> Dict[str, Any]:
        """Load JSON file with error handling."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Data file not found: {filepath}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {filepath}: {e}")

    def validate_pbx_web_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """Validate pbx-web deployment dataset structure."""
        errors = []
        warnings = []

        # Check top-level structure
        if 'metadata' not in data:
            errors.append("Missing 'metadata' section")
        else:
            required_metadata = ['service', 'namespace', 'cluster', 'time_period']
            for field in required_metadata:
                if field not in data['metadata']:
                    errors.append(f"Missing metadata field: {field}")

        # Check deployment events
        if 'deployment_events_last_30_days' not in data:
            errors.append("Missing 'deployment_events_last_30_days' section")
        else:
            events = data['deployment_events_last_30_days']
            if not isinstance(events, list):
                errors.append("deployment_events_last_30_days must be a list")
            else:
                for i, event in enumerate(events):
                    for field in self.REQUIRED_PBX_FIELDS:
                        if field not in event:
                            errors.append(f"Event {i}: Missing required field '{field}'")

                    # Validate timestamp format
                    if 'timestamp' in event:
                        try:
                            datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                        except ValueError:
                            errors.append(f"Event {i}: Invalid timestamp format: {event['timestamp']}")

        # Check for metrics section
        if 'deployment_metrics' not in data:
            warnings.append("Missing 'deployment_metrics' section - summary data not available")

        return len(errors) == 0, errors, warnings

    def validate_whisper_stt_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """Validate whisper-stt deployment dataset structure."""
        errors = []
        warnings = []

        # Check top-level structure
        if 'report_metadata' not in data:
            errors.append("Missing 'report_metadata' section")
        else:
            required_metadata = ['cluster', 'service', 'namespace', 'time_range_start', 'time_range_end']
            for field in required_metadata:
                if field not in data['report_metadata']:
                    errors.append(f"Missing report_metadata field: {field}")

        # Check current status
        if 'current_status' not in data:
            errors.append("Missing 'current_status' section")
        else:
            if 'deployments' not in data['current_status']:
                errors.append("Missing 'deployments' in current_status")

        # Check deployment history
        if 'deployment_history_30_days' not in data:
            errors.append("Missing 'deployment_history_30_days' section")
        else:
            history = data['deployment_history_30_days']
            if 'replicasets' not in history:
                errors.append("Missing 'replicasets' in deployment_history_30_days")
            else:
                replicasets = history['replicasets']
                if not isinstance(replicasets, list):
                    errors.append("replicasets must be a list")
                else:
                    for i, rs in enumerate(replicasets):
                        for field in self.REQUIRED_WHISPER_FIELDS:
                            if field not in rs:
                                errors.append(f"ReplicaSet {i}: Missing required field '{field}'")

                        # Validate timestamp format
                        if 'created' in rs:
                            try:
                                datetime.fromisoformat(rs['created'].replace('Z', '+00:00'))
                            except ValueError:
                                errors.append(f"ReplicaSet {i}: Invalid timestamp format: {rs['created']}")

        # Check for operational metrics
        if 'operational_metrics' not in data:
            warnings.append("Missing 'operational_metrics' section - resource data not available")

        return len(errors) == 0, errors, warnings

    def validate_dataset(self, service: str, filepath: Path) -> Dict[str, Any]:
        """Load and validate a deployment dataset."""
        print(f"\n{'='*60}")
        print(f"Validating {service} deployment data")
        print(f"{'='*60}")

        try:
            # Load data
            print(f"Loading data from: {filepath}")
            data = self.load_json_file(filepath)
            self.validation_results[service]['loaded'] = True
            print("✓ Data loaded successfully")

            # Validate based on service type
            if service == 'pbx-web':
                is_valid, errors, warnings = self.validate_pbx_web_data(data)
            else:  # whisper-stt
                is_valid, errors, warnings = self.validate_whisper_stt_data(data)

            self.validation_results[service]['valid'] = is_valid
            self.validation_results[service]['errors'] = errors
            self.validation_results[service]['warnings'] = warnings

            # Report results
            if errors:
                print(f"\n❌ Validation failed with {len(errors)} error(s):")
                for error in errors:
                    print(f"  - {error}")
            else:
                print("\n✓ Structure validation passed")

            if warnings:
                print(f"\n⚠️  {len(warnings)} warning(s):")
                for warning in warnings:
                    print(f"  - {warning}")

            # Extract key metrics
            print(f"\n📊 Key Metrics:")
            if service == 'pbx-web' and 'deployment_metrics' in data:
                metrics = data['deployment_metrics']
                print(f"  Total deployments (30d): {metrics.get('total_deployments_last_30_days', 'N/A')}")
                print(f"  Success rate: {metrics.get('deployment_success_rate', 'N/A')}")
                print(f"  Last deployment: {metrics.get('last_deployment', 'N/A')}")
            elif service == 'whisper-stt' and 'summary' in data:
                summary = data['summary']
                print(f"  Total events (30d): {summary.get('total_deployment_events', 'N/A')}")
                print(f"  Availability: {summary.get('availability', 'N/A')}")
                print(f"  Overall status: {summary.get('overall_status', 'N/A')}")

            return data

        except Exception as e:
            print(f"\n❌ Failed to validate {service}: {e}")
            self.validation_results[service]['errors'].append(str(e))
            return None

    def generate_summary_report(self) -> str:
        """Generate a summary validation report."""
        report = []
        report.append("\n" + "="*60)
        report.append("DEPLOYMENT DATA VALIDATION SUMMARY")
        report.append("="*60)

        for service, results in self.validation_results.items():
            status_icon = "✓" if results['valid'] else "❌"
            loaded_status = "Loaded" if results['loaded'] else "Failed"
            valid_status = "Valid" if results['valid'] else "Invalid"

            report.append(f"\n{status_icon} {service.upper()}")
            report.append(f"  Load Status: {loaded_status}")
            report.append(f"  Validation: {valid_status}")

            if results['errors']:
                report.append(f"  Errors ({len(results['errors'])}):")
                for error in results['errors']:
                    report.append(f"    - {error}")

            if results['warnings']:
                report.append(f"  Warnings ({len(results['warnings'])}):")
                for warning in results['warnings']:
                    report.append(f"    - {warning}")

        report.append("\n" + "="*60)

        # Overall assessment
        all_loaded = all(r['loaded'] for r in self.validation_results.values())
        all_valid = all(r['valid'] for r in self.validation_results.values())

        if all_loaded and all_valid:
            report.append("✓ OVERALL: All datasets loaded and validated successfully")
            report.append("✓ Data is ready for analysis by subsequent beads")
        elif all_loaded:
            report.append("⚠️  OVERALL: All datasets loaded but validation has issues")
            report.append("⚠️  Review errors/warnings before proceeding with analysis")
        else:
            report.append("❌ OVERALL: Some datasets failed to load")
            report.append("❌ Cannot proceed with analysis until all data is loaded")

        report.append("="*60 + "\n")

        return "\n".join(report)


def main():
    """Main execution function."""
    print("Deployment Data Validation Script")
    print("=" * 60)

    # Define data paths
    workspace = Path('/home/coding/aide-de-camp')
    pbx_data_path = workspace / 'pbx-web-deployment-data-30days.json'
    whisper_data_path = workspace / 'whisper-stt-deployment-data-30days.json'

    # Initialize validator
    validator = DeploymentDataValidator()

    # Validate datasets
    pbx_data = validator.validate_dataset('pbx-web', pbx_data_path)
    whisper_data = validator.validate_dataset('whisper-stt', whisper_data_path)

    # Generate and print summary report
    summary = validator.generate_summary_report()
    print(summary)

    # Save validation report
    report_path = workspace / 'notes' / 'adc-1bnqx-validation-report.md'
    report_path.parent.mkdir(exist_ok=True)

    with open(report_path, 'w') as f:
        f.write("# Deployment Data Validation Report\n\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        f.write(summary)
        f.write("\n## Data Files Validated\n\n")
        f.write(f"- pbx-web: `{pbx_data_path}`\n")
        f.write(f"- whisper-stt: `{whisper_data_path}`\n\n")
        f.write("## Next Steps\n\n")
        f.write("Both datasets are now available for analysis by subsequent beads:\n")
        f.write("- Use `pbx-web-deployment-data-30days.json` for pbx-web analysis\n")
        f.write("- Use `whisper-stt-deployment-data-30days.json` for whisper-stt analysis\n")
        f.write("- Both datasets contain 30-day deployment history with timestamps, events, and metrics\n")

    print(f"\n✓ Validation report saved to: {report_path}")

    # Save loaded data references for subsequent beads
    metadata_path = workspace / 'notes' / 'adc-1bnqx-metadata.json'
    metadata = {
        'generated_at': datetime.now().isoformat(),
        'datasets': {
            'pbx-web': {
                'file': str(pbx_data_path),
                'loaded': validator.validation_results['pbx-web']['loaded'],
                'valid': validator.validation_results['pbx-web']['valid'],
                'record_count': len(pbx_data.get('deployment_events_last_30_days', [])) if pbx_data else 0
            },
            'whisper-stt': {
                'file': str(whisper_data_path),
                'loaded': validator.validation_results['whisper-stt']['loaded'],
                'valid': validator.validation_results['whisper-stt']['valid'],
                'record_count': len(whisper_data.get('deployment_history_30_days', {}).get('replicasets', [])) if whisper_data else 0
            }
        },
        'ready_for_analysis': all([
            validator.validation_results['pbx-web']['loaded'],
            validator.validation_results['whisper-stt']['loaded'],
            validator.validation_results['pbx-web']['valid'],
            validator.validation_results['whisper-stt']['valid']
        ])
    }

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"✓ Data metadata saved to: {metadata_path}")

    # Exit with appropriate code
    if all([validator.validation_results['pbx-web']['valid'],
            validator.validation_results['whisper-stt']['valid']]):
        print("\n✓ All validation checks passed - data is ready for analysis")
        return 0
    else:
        print("\n❌ Validation failed - review errors before proceeding")
        return 1


if __name__ == '__main__':
    sys.exit(main())
