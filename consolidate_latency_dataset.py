#!/usr/bin/env python3
"""
Consolidate latency dataset for pbx-web and whisper-stt services.
Handles missing periods with metadata flags and validates dataset integrity.
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import sys

class LatencyDataConsolidator:
    """Handles latency data consolidation with gap filling and metadata."""

    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)
        self.consolidated_data = {
            "generated_at": datetime.utcnow().isoformat(),
            "services": {},
            "gap_handling_strategy": "flagged_placeholder",
            "metadata": {
                "total_services": 2,
                "gap_filled_periods": 0,
                "data_quality_status": []
            }
        }

    def load_deployment_data(self, csv_file: str, json_file: str) -> Tuple[pd.DataFrame, dict]:
        """Load CSV deployment events and JSON metadata."""
        try:
            df = pd.read_csv(csv_file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            with open(json_file, 'r') as f:
                metadata = json.load(f)

            return df, metadata
        except Exception as e:
            print(f"Error loading {csv_file}: {e}")
            return pd.DataFrame(), {}

    def generate_time_series(self, start: datetime, end: datetime, freq: str = 'D') -> List[datetime]:
        """Generate complete time series for gap detection."""
        return pd.date_range(start=start, end=end, freq=freq).tolist()

    def detect_gaps(self, df: pd.DataFrame, service_name: str) -> List[Dict]:
        """Detect temporal gaps in deployment data."""
        if df.empty or 'timestamp' not in df.columns:
            return []

        timestamps = sorted(df['timestamp'].dropna())
        if not timestamps:
            return []

        gaps = []
        expected_dates = pd.date_range(start=timestamps[0], end=timestamps[-1], freq='D')
        # timestamps is already a DatetimeIndex, so we use floor directly
        actual_dates = pd.to_datetime(timestamps).floor('D').unique()
        missing_dates = set(expected_dates) - set(actual_dates)

        if missing_dates:
            missing_sorted = sorted(list(missing_dates))
            gap_start = missing_sorted[0]
            gap_end = missing_sorted[0]

            for date in missing_sorted[1:]:
                if (date - gap_end).days == 1:
                    gap_end = date
                else:
                    gap_duration = (gap_end - gap_start).days + 1
                    gaps.append({
                        "start": gap_start.isoformat(),
                        "end": gap_end.isoformat(),
                        "duration_days": gap_duration,
                        "severity": "critical" if gap_duration >= 7 else "major" if gap_duration >= 3 else "minor"
                    })
                    gap_start = date
                    gap_end = date

            # Add final gap
            gap_duration = (gap_end - gap_start).days + 1
            gaps.append({
                "start": gap_start.isoformat(),
                "end": gap_end.isoformat(),
                "duration_days": gap_duration,
                "severity": "critical" if gap_duration >= 7 else "major" if gap_duration >= 3 else "minor"
            })

        return gaps

    def create_gap_placeholder_record(self, gap_date: datetime, service_name: str, severity: str) -> Dict:
        """Create a placeholder record for gap periods."""
        return {
            "timestamp": gap_date.isoformat(),
            "event_type": "gap_placeholder",
            "deployment": service_name,
            "gap_severity": severity,
            "is_interpolated": True,
            "data_quality": "missing",
            "notes": f"Gap-filled placeholder - no actual deployment data available for this period"
        }

    def consolidate_service_data(self, service_name: str, csv_file: str, json_file: str) -> Dict:
        """Consolidate data for a single service with gap handling."""
        print(f"\nProcessing {service_name}...")

        df, metadata = self.load_deployment_data(csv_file, json_file)

        if df.empty:
            print(f"  Warning: No deployment data found for {service_name}")
            return {
                "service_name": service_name,
                "status": "no_data",
                "records": [],
                "gaps_detected": [],
                "coverage": 0.0
            }

        # Detect gaps
        gaps = self.detect_gaps(df, service_name)

        # Create placeholder records for gaps
        placeholder_records = []
        for gap in gaps:
            gap_start = pd.to_datetime(gap['start'])
            gap_end = pd.to_datetime(gap['end'])
            gap_dates = pd.date_range(start=gap_start, end=gap_end, freq='D')

            for gap_date in gap_dates:
                placeholder_records.append(
                    self.create_gap_placeholder_record(gap_date, service_name, gap['severity'])
                )

        # Combine actual and placeholder records
        actual_records = df.to_dict('records')
        all_records = actual_records + placeholder_records

        # Sort by timestamp
        all_records.sort(key=lambda x: pd.to_datetime(x['timestamp']))

        # Calculate coverage
        if all_records:
            timestamps = [pd.to_datetime(r['timestamp']) for r in actual_records]
            if timestamps:
                time_span = (max(timestamps) - min(timestamps)).days + 1
                # timestamps is a list, convert to DatetimeIndex and use floor directly
                days_with_data = len(pd.to_datetime(timestamps).floor('D').unique())
                coverage = (days_with_data / time_span * 100) if time_span > 0 else 0
            else:
                coverage = 0
        else:
            coverage = 0

        return {
            "service_name": service_name,
            "status": "success",
            "total_records": len(all_records),
            "actual_records": len(actual_records),
            "gap_filled_records": len(placeholder_records),
            "gaps_detected": gaps,
            "coverage_pct": round(coverage, 2),
            "data_quality": "degraded" if len(gaps) > 0 else "good",
            "records": all_records,
            "metadata": metadata
        }

    def consolidate_all_services(self) -> Dict:
        """Consolidate data for all services."""
        services_config = {
            "pbx-web": {
                "csv": "pbx-web-deployment-events-30days.csv",
                "json": "pbx-web-deployment-data-30days.json"
            },
            "whisper-stt": {
                "csv": "whisper-stt-deployment-events-30days.csv",
                "json": "whisper-stt-deployment-data-30days.json"
            }
        }

        total_gap_filled = 0

        for service_name, files in services_config.items():
            csv_path = self.output_dir / files["csv"]
            json_path = self.output_dir / files["json"]

            if not csv_path.exists() or not json_path.exists():
                print(f"Warning: Missing files for {service_name}")
                continue

            service_data = self.consolidate_service_data(
                service_name,
                str(csv_path),
                str(json_path)
            )

            self.consolidated_data["services"][service_name] = service_data
            self.consolidated_data["metadata"]["data_quality_status"].append({
                "service": service_name,
                "quality": service_data.get("data_quality", "unknown"),
                "gaps": len(service_data.get("gaps_detected", [])),
                "coverage": service_data.get("coverage_pct", 0)
            })

            total_gap_filled += service_data.get("gap_filled_records", 0)

        self.consolidated_data["metadata"]["gap_filled_periods"] = total_gap_filled

        return self.consolidated_data

    def validate_dataset(self) -> Dict:
        """Validate the consolidated dataset for integrity."""
        validation_results = {
            "validation_timestamp": datetime.utcnow().isoformat(),
            "checks": [],
            "overall_status": "unknown"
        }

        all_passed = True

        for service_name, service_data in self.consolidated_data["services"].items():
            checks = []

            # Check 1: Records exist
            has_records = service_data.get("total_records", 0) > 0
            checks.append({
                "check": "has_records",
                "passed": has_records,
                "details": f"{service_data.get('total_records', 0)} records found"
            })
            if not has_records:
                all_passed = False

            # Check 2: Timestamps are present
            if service_data.get("records"):
                has_timestamps = all('timestamp' in r for r in service_data["records"])
                checks.append({
                    "check": "has_timestamps",
                    "passed": has_timestamps,
                    "details": "All records have timestamp field"
                })
                if not has_timestamps:
                    all_passed = False

            # Check 3: Gap records are flagged
            gap_records_flagged = True
            for record in service_data.get("records", []):
                if record.get("event_type") == "gap_placeholder":
                    if "gap_severity" not in record or "is_interpolated" not in record:
                        gap_records_flagged = False
                        break

            checks.append({
                "check": "gap_records_flagged",
                "passed": gap_records_flagged,
                "details": "All gap placeholders have metadata flags"
            })
            if not gap_records_flagged:
                all_passed = False

            # Check 4: Coverage is calculated
            coverage_calculated = service_data.get("coverage_pct") is not None
            checks.append({
                "check": "coverage_calculated",
                "passed": coverage_calculated,
                "details": f"Coverage: {service_data.get('coverage_pct', 0)}%"
            })
            if not coverage_calculated:
                all_passed = False

            validation_results["checks"].append({
                "service": service_name,
                "checks": checks,
                "service_status": "passed" if all(c["passed"] for c in checks) else "failed"
            })

        validation_results["overall_status"] = "passed" if all_passed else "failed"
        return validation_results

    def save_consolidated_dataset(self, filename: str = "consolidated_latency_dataset.json") -> str:
        """Save the consolidated dataset to file."""
        output_path = self.output_dir / filename

        with open(output_path, 'w') as f:
            json.dump(self.consolidated_data, f, indent=2, default=str)

        print(f"\n✓ Consolidated dataset saved to: {output_path}")
        return str(output_path)

    def save_validation_report(self, validation_results: Dict, filename: str = "dataset_validation_report.json") -> str:
        """Save validation report to file."""
        output_path = self.output_dir / filename

        with open(output_path, 'w') as f:
            json.dump(validation_results, f, indent=2, default=str)

        print(f"✓ Validation report saved to: {output_path}")
        return str(output_path)

    def print_summary(self):
        """Print summary of consolidated dataset."""
        print("\n" + "="*60)
        print("CONSOLIDATED LATENCY DATASET SUMMARY")
        print("="*60)

        print(f"\nGenerated: {self.consolidated_data['generated_at']}")
        print(f"Gap Handling Strategy: {self.consolidated_data['gap_handling_strategy']}")

        print("\n" + "-"*60)
        print("Service Status:")
        print("-"*60)

        for service_name, service_data in self.consolidated_data["services"].items():
            print(f"\n{service_name}:")
            print(f"  Status: {service_data.get('status', 'unknown')}")
            print(f"  Total Records: {service_data.get('total_records', 0)}")
            print(f"    - Actual: {service_data.get('actual_records', 0)}")
            print(f"    - Gap-filled: {service_data.get('gap_filled_records', 0)}")
            print(f"  Coverage: {service_data.get('coverage_pct', 0)}%")
            print(f"  Data Quality: {service_data.get('data_quality', 'unknown')}")
            print(f"  Gaps Detected: {len(service_data.get('gaps_detected', []))}")

            if service_data.get('gaps_detected'):
                print("  Gap Details:")
                for gap in service_data['gaps_detected']:
                    print(f"    - {gap['start']} to {gap['end']} ({gap['duration_days']}d, {gap['severity']})")

        print("\n" + "-"*60)
        print(f"Total Gap-Filled Periods: {self.consolidated_data['metadata']['gap_filled_periods']}")
        print("="*60)

def main():
    """Main execution function."""
    print("Latency Dataset Consolidation with Gap Handling")
    print("="*60)

    consolidator = LatencyDataConsolidator()

    # Consolidate all services
    print("\nStep 1: Consolidating service data...")
    consolidator.consolidate_all_services()

    # Validate dataset
    print("\nStep 2: Validating dataset integrity...")
    validation_results = consolidator.validate_dataset()

    # Save results
    print("\nStep 3: Saving consolidated dataset...")
    dataset_file = consolidator.save_consolidated_dataset("consolidated_latency_dataset.json")

    print("\nStep 4: Saving validation report...")
    validation_file = consolidator.save_validation_report(validation_results, "dataset_validation_report.json")

    # Print summary
    consolidator.print_summary()

    print(f"\nValidation Status: {validation_results['overall_status'].upper()}")
    print("\nFiles created:")
    print(f"  - {dataset_file}")
    print(f"  - {validation_file}")

    return 0 if validation_results['overall_status'] == 'passed' else 1

if __name__ == "__main__":
    sys.exit(main())