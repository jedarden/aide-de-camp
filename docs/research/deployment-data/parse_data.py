#!/usr/bin/env python3
"""
Parse and load all deployment data JSON files from the deployment-data directory.

This script:
1. Lists all JSON files in the deployment-data directory
2. Parses each JSON file and validates structure
3. Loads all files into memory
4. Outputs a summary of loaded data (file count, record count, date range)
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple
from collections import defaultdict
import sys


class DeploymentDataParser:
    """Parser for deployment data JSON files."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.loaded_data: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.file_stats = defaultdict(lambda: {
            'count': 0,
            'total_size': 0,
            'record_counts': []
        })

    def find_json_files(self) -> List[Path]:
        """Find all JSON files in the data directory."""
        try:
            json_files = list(self.data_dir.glob("*.json"))
            json_files.sort(key=lambda x: x.name)
            return json_files
        except Exception as e:
            self.errors.append(f"Failed to find JSON files: {e}")
            return []

    def parse_json_file(self, file_path: Path) -> Tuple[bool, Any]:
        """
        Parse a JSON file with error handling.

        Returns (success, parsed_data_or_none)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return True, data
        except json.JSONDecodeError as e:
            self.errors.append(f"JSON parse error in {file_path.name}: {e}")
            return False, None
        except Exception as e:
            self.errors.append(f"Error reading {file_path.name}: {e}")
            return False, None

    def validate_structure(self, file_path: Path, data: Any) -> bool:
        """
        Validate the structure of parsed JSON data.
        Returns True if structure is valid or unknown.
        """
        if not isinstance(data, dict):
            self.warnings.append(f"{file_path.name}: Root is not a dictionary")
            return False

        # Check for common metadata fields
        has_metadata = 'metadata' in data or 'search_metadata' in data
        has_summary = 'summary' in data
        has_services = 'services' in data
        has_daily_bins = 'daily_bins' in data

        # Categorize file type based on structure
        if has_metadata:
            if has_services:
                file_type = 'failure_pattern_analysis'
                return self._validate_failure_pattern_structure(data, file_path.name)
            elif has_daily_bins:
                file_type = 'temporal_distribution'
                return self._validate_temporal_structure(data, file_path.name)
            else:
                file_type = 'deployment_workflow'
                return self._validate_deployment_structure(data, file_path.name)
        elif has_summary:
            file_type = 'deployment_workflow'
            return self._validate_deployment_structure(data, file_path.name)
        else:
            # Unknown structure, but valid JSON
            self.warnings.append(f"{file_path.name}: Unknown structure, but valid JSON")
            return True

    def _validate_deployment_structure(self, data: Dict, filename: str) -> bool:
        """Validate deployment workflow data structure."""
        required_fields = ['deployment_runs', 'summary']
        for field in required_fields:
            if field not in data:
                self.warnings.append(f"{filename}: Missing '{field}' field")
        return True  # Allow flexible structures

    def _validate_failure_pattern_structure(self, data: Dict, filename: str) -> bool:
        """Validate failure pattern analysis structure."""
        if 'services' not in data:
            self.warnings.append(f"{filename}: Missing 'services' field")
            return False
        if not isinstance(data['services'], dict):
            self.warnings.append(f"{filename}: 'services' is not a dictionary")
            return False
        return True

    def _validate_temporal_structure(self, data: Dict, filename: str) -> bool:
        """Validate temporal distribution structure."""
        if 'daily_bins' not in data:
            self.warnings.append(f"{filename}: Missing 'daily_bins' field")
            return False
        if not isinstance(data['daily_bins'], dict):
            self.warnings.append(f"{filename}: 'daily_bins' is not a dictionary")
            return False
        return True

    def extract_date_range(self, data: Any, file_path: Path) -> Tuple[str, str]:
        """Extract date range from data if available."""
        dates = []

        def extract_dates_recursive(obj: Any, path: str = ""):
            """Recursively extract date fields."""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(key, str) and 'date' in key.lower():
                        if isinstance(value, str):
                            dates.append(value)
                    extract_dates_recursive(value, f"{path}.{key}" if path else key)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    extract_dates_recursive(item, f"{path}[{i}]")

        extract_dates_recursive(data)

        # Parse and sort dates
        parsed_dates = []
        for date_str in dates:
            try:
                # Try ISO format - normalize to offset-naive for consistent comparison
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                # Convert offset-aware to offset-naive for comparison
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                parsed_dates.append(dt)
            except (ValueError, AttributeError):
                try:
                    # Try other common formats (these produce offset-naive datetimes)
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                        try:
                            parsed_dates.append(datetime.strptime(date_str, fmt))
                            break
                        except ValueError:
                            continue
                except:
                    pass

        if parsed_dates:
            parsed_dates.sort()
            return parsed_dates[0].isoformat(), parsed_dates[-1].isoformat()
        return "N/A", "N/A"

    def count_records(self, data: Any, file_path: Path) -> int:
        """Count records in various data structures."""
        count = 0

        if isinstance(data, dict):
            # Count deployment runs
            if 'deployment_runs' in data and isinstance(data['deployment_runs'], list):
                count += len(data['deployment_runs'])

            # Count service events
            if 'services' in data and isinstance(data['services'], dict):
                for service_data in data['services'].values():
                    if 'failures_detected' in service_data:
                        count += len(service_data['failures_detected'])
                    if 'events_by_type' in service_data:
                        count += sum(service_data['events_by_type'].values())

            # Count daily bins
            if 'daily_bins' in data and isinstance(data['daily_bins'], dict):
                count += len(data['daily_bins'])

            # Count items in lists
            for value in data.values():
                if isinstance(value, list):
                    count += len(value)

        return count

    def load_all_files(self) -> bool:
        """Load and parse all JSON files."""
        json_files = self.find_json_files()

        if not json_files:
            self.errors.append(f"No JSON files found in {self.data_dir}")
            return False

        print(f"Found {len(json_files)} JSON files")
        print("-" * 60)

        for file_path in json_files:
            print(f"Processing: {file_path.name}")

            # Parse file
            success, data = self.parse_json_file(file_path)
            if not success:
                continue

            # Validate structure
            if not self.validate_structure(file_path, data):
                continue

            # Store data
            self.loaded_data[file_path.name] = data

            # Extract stats
            file_size = file_path.stat().st_size
            date_start, date_end = self.extract_date_range(data, file_path)
            record_count = self.count_records(data, file_path)

            self.file_stats['overall']['count'] += 1
            self.file_stats['overall']['total_size'] += file_size
            self.file_stats['overall']['record_counts'].append({
                'file': file_path.name,
                'records': record_count,
                'size': file_size,
                'date_start': date_start,
                'date_end': date_end
            })

        return len(self.loaded_data) > 0

    def generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        total_files = self.file_stats['overall']['count']
        total_size = self.file_stats['overall']['total_size']
        total_records = sum(item['records'] for item in self.file_stats['overall']['record_counts'])

        # Find overall date range
        all_dates = []
        for item in self.file_stats['overall']['record_counts']:
            if item['date_start'] != "N/A":
                all_dates.append(item['date_start'])
            if item['date_end'] != "N/A":
                all_dates.append(item['date_end'])

        if all_dates:
            all_dates.sort()
            date_range_start = all_dates[0]
            date_range_end = all_dates[-1]
        else:
            date_range_start = "N/A"
            date_range_end = "N/A"

        return {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'total_records': total_records,
            'date_range_start': date_range_start,
            'date_range_end': date_range_end,
            'errors': len(self.errors),
            'warnings': len(self.warnings)
        }

    def print_summary(self):
        """Print summary of loaded data."""
        summary = self.generate_summary()

        print("\n" + "=" * 60)
        print("DATA LOADING SUMMARY")
        print("=" * 60)
        print(f"Total files loaded:     {summary['total_files']}")
        print(f"Total size:            {summary['total_size_mb']} MB ({summary['total_size_bytes']:,} bytes)")
        print(f"Total records:         {summary['total_records']:,}")
        print(f"Date range:            {summary['date_range_start']} to {summary['date_range_end']}")
        print(f"Errors encountered:    {summary['errors']}")
        print(f"Warnings issued:       {summary['warnings']}")

        # Print individual file stats
        if self.file_stats['overall']['record_counts']:
            print("\n" + "-" * 60)
            print("Individual File Statistics:")
            print("-" * 60)
            print(f"{'Filename':<45} {'Records':<10} {'Size (KB)':<12}")
            print("-" * 60)
            for item in sorted(self.file_stats['overall']['record_counts'],
                             key=lambda x: x['file']):
                size_kb = round(item['size'] / 1024, 2)
                print(f"{item['file']:<45} {item['records']:<10} {size_kb:<12}")

        # Print errors if any
        if self.errors:
            print("\n" + "-" * 60)
            print("ERRORS:")
            print("-" * 60)
            for error in self.errors:
                print(f"  • {error}")

        # Print warnings if any
        if self.warnings:
            print("\n" + "-" * 60)
            print("WARNINGS:")
            print("-" * 60)
            for warning in self.warnings[:10]:  # Show first 10 warnings
                print(f"  • {warning}")
            if len(self.warnings) > 10:
                print(f"  ... and {len(self.warnings) - 10} more warnings")

        print("=" * 60)

    def get_loaded_data(self) -> Dict[str, Any]:
        """Return the loaded data dictionary."""
        return self.loaded_data


def main():
    """Main entry point."""
    # Determine script directory and data directory
    script_dir = Path(__file__).parent
    data_dir = script_dir

    print(f"Deployment Data Parser")
    print(f"Data directory: {data_dir}")
    print()

    # Create parser and load files
    parser = DeploymentDataParser(data_dir)
    success = parser.load_all_files()

    if not success:
        print("\n❌ Failed to load any data files")
        if parser.errors:
            print("\nErrors encountered:")
            for error in parser.errors:
                print(f"  • {error}")
        sys.exit(1)

    # Print summary
    parser.print_summary()

    # Print successful completion message
    print(f"\n✅ Successfully loaded {len(parser.get_loaded_data())} files into memory")
    print(f"Data is available in parser.get_loaded_data()")


if __name__ == "__main__":
    main()
