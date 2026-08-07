#!/usr/bin/env python3
"""
Deployment Data Validation Script

Validates deployment JSON files against expected schema and structure.
Checks for required fields, data quality issues, and provides summary statistics.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime


class DeploymentValidator:
    """Validates deployment data files and their structure."""

    # Required fields for deployment records
    REQUIRED_BASE_FIELDS = ['timestamp', 'outcome']

    # Alternative field names that might be used instead of the standard ones
    FIELD_ALIASES = {
        'timestamp': ['timestamp', 'date', 'created', 'created_at', 'time', 'datetime'],
        'outcome': ['outcome', 'status', 'result', 'state'],
        'error_type': ['error_type', 'error', 'failure_type'],
        'phase': ['phase', 'stage', 'deployment_phase'],
        'error_message': ['error_message', 'message', 'error_message', 'failure_reason']
    }

    # Fields required when outcome indicates failure
    REQUIRED_FAILURE_FIELDS = ['error_type', 'phase', 'error_message']

    # Valid outcome values
    VALID_OUTCOMES = ['success', 'failure', 'rolled_back', 'partial', 'unknown', 'active', 'inactive']

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.validation_results = {
            'files_checked': 0,
            'files_valid': 0,
            'files_invalid': 0,
            'files_missing': 0,
            'total_records': 0,
            'valid_records': 0,
            'invalid_records': 0,
            'errors': [],
            'warnings': [],
            'file_details': []
        }

    def log(self, message: str, is_error: bool = False):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            prefix = "❌ " if is_error else "✅ "
            print(f"{prefix}{message}")

    def validate_file_exists(self, file_path: Path) -> bool:
        """Check if a file exists."""
        if not file_path.exists():
            self.validation_results['files_missing'] += 1
            error_msg = f"File not found: {file_path}"
            self.validation_results['errors'].append(error_msg)
            self.log(error_msg, is_error=True)
            return False
        return True

    def load_json_file(self, file_path: Path) -> Tuple[bool, Any]:
        """Load and parse a JSON file."""
        if not self.validate_file_exists(file_path):
            return False, None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.log(f"Successfully loaded: {file_path}")
            return True, data
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in {file_path}: {e}"
            self.validation_results['errors'].append(error_msg)
            self.validation_results['files_invalid'] += 1
            self.log(error_msg, is_error=True)
            return False, None
        except Exception as e:
            error_msg = f"Error reading {file_path}: {e}"
            self.validation_results['errors'].append(error_msg)
            self.validation_results['files_invalid'] += 1
            self.log(error_msg, is_error=True)
            return False, None

    def find_field_value(self, record: Dict, standard_field: str) -> Any:
        """Find a field value using standard name or aliases."""
        # First try the standard field name
        if standard_field in record and record[standard_field] is not None:
            return record[standard_field]
        
        # Try aliases
        if standard_field in self.FIELD_ALIASES:
            for alias in self.FIELD_ALIASES[standard_field]:
                if alias in record and record[alias] is not None:
                    return record[alias]
        
        return None

    def validate_timestamp(self, timestamp: Any, record_index: int, file_path: str) -> bool:
        """Validate timestamp format and presence."""
        if timestamp is None:
            error_msg = f"{file_path}: Record {record_index} - Missing timestamp field"
            self.validation_results['errors'].append(error_msg)
            self.log(error_msg, is_error=True)
            return False

        if not isinstance(timestamp, str):
            error_msg = f"{file_path}: Record {record_index} - Timestamp must be string, got {type(timestamp)}"
            self.validation_results['errors'].append(error_msg)
            self.log(error_msg, is_error=True)
            return False

        try:
            # Try to parse ISO 8601 timestamp
            datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return True
        except ValueError:
            warning_msg = f"{file_path}: Record {record_index} - Invalid timestamp format: {timestamp}"
            self.validation_results['warnings'].append(warning_msg)
            self.log(warning_msg)
            return True  # Not a critical error

    def validate_outcome(self, outcome: Any, record_index: int, file_path: str) -> bool:
        """Validate outcome field."""
        if outcome is None:
            error_msg = f"{file_path}: Record {record_index} - Missing outcome/status field"
            self.validation_results['errors'].append(error_msg)
            self.log(error_msg, is_error=True)
            return False

        if not isinstance(outcome, str):
            error_msg = f"{file_path}: Record {record_index} - Outcome must be string, got {type(outcome)}"
            self.validation_results['errors'].append(error_msg)
            self.log(error_msg, is_error=True)
            return False

        if outcome not in self.VALID_OUTCOMES:
            warning_msg = f"{file_path}: Record {record_index} - Unknown outcome '{outcome}', expected one of {self.VALID_OUTCOMES}"
            self.validation_results['warnings'].append(warning_msg)
            self.log(warning_msg)
            return True  # Still valid, just unexpected

        return True

    def validate_failure_fields(self, record: Dict, record_index: int, file_path: str) -> bool:
        """Validate required failure fields when outcome indicates failure."""
        outcome = self.find_field_value(record, 'outcome')

        # Check if this is a failure outcome
        failure_outcomes = ['failure', 'partial', 'error']
        if outcome not in failure_outcomes:
            return True  # No failure fields needed

        # Check required failure fields
        missing_fields = []
        for field in self.REQUIRED_FAILURE_FIELDS:
            value = self.find_field_value(record, field)
            if value is None:
                missing_fields.append(field)

        if missing_fields:
            error_msg = f"{file_path}: Record {record_index} - Missing required failure fields: {missing_fields}"
            self.validation_results['errors'].append(error_msg)
            self.log(error_msg, is_error=True)
            return False

        return True

    def validate_deployment_record(self, record: Dict, record_index: int, file_path: str) -> bool:
        """Validate a single deployment record."""
        is_valid = True

        # Find timestamp and outcome using aliases
        timestamp = self.find_field_value(record, 'timestamp')
        outcome = self.find_field_value(record, 'outcome')

        # Check required base fields
        if timestamp is None and outcome is None:
            error_msg = f"{file_path}: Record {record_index} - Missing required base fields (timestamp/status)"
            self.validation_results['errors'].append(error_msg)
            self.log(error_msg, is_error=True)
            return False

        # Validate timestamp
        if timestamp is not None:
            if not self.validate_timestamp(timestamp, record_index, file_path):
                is_valid = False
        else:
            error_msg = f"{file_path}: Record {record_index} - Missing timestamp"
            self.validation_results['errors'].append(error_msg)
            self.log(error_msg, is_error=True)
            is_valid = False

        # Validate outcome
        if outcome is not None:
            if not self.validate_outcome(outcome, record_index, file_path):
                is_valid = False
        else:
            error_msg = f"{file_path}: Record {record_index} - Missing outcome/status"
            self.validation_results['errors'].append(error_msg)
            self.log(error_msg, is_error=True)
            is_valid = False

        # Validate failure fields if needed
        if not self.validate_failure_fields(record, record_index, file_path):
            is_valid = False

        return is_valid

    def extract_deployment_records(self, data: Any, file_path: str) -> List[Dict]:
        """Extract deployment records from various data structures."""
        records = []

        # Handle different data structures
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # Check for common structures - try multiple possible field names
            possible_fields = [
                'deployment_events_last_30_days',
                'deployment_events',
                'events',
                'items',
                'deployments',
                'deployment_history_30_days'
            ]
            
            for field in possible_fields:
                if field in data:
                    field_data = data[field]
                    
                    # Handle different structures within the field
                    if isinstance(field_data, list):
                        records = field_data
                        break
                    elif isinstance(field_data, dict):
                        # Check for nested arrays like 'replicasets'
                        for nested_field in ['replicasets', 'items', 'events', 'deployments']:
                            if nested_field in field_data and isinstance(field_data[nested_field], list):
                                records = field_data[nested_field]
                                break
                        if records:
                            break
            
            # If no records found yet, check for service-specific structure
            if not records:
                for key, value in data.items():
                    if isinstance(value, dict):
                        # Check for nested deployment_events
                        for nested_field in possible_fields + ['replicasets']:
                            if nested_field in value and isinstance(value[nested_field], list):
                                records.extend(value[nested_field])

        return records

    def validate_deployment_file(self, file_path: Path) -> bool:
        """Validate a deployment data file."""
        self.validation_results['files_checked'] += 1
        file_detail = {'file': str(file_path), 'records': 0, 'valid': 0, 'invalid': 0}

        # Load the file
        success, data = self.load_json_file(file_path)
        if not success:
            return False

        # Extract deployment records
        file_path_str = str(file_path)
        records = self.extract_deployment_records(data, file_path_str)

        if not records:
            warning_msg = f"{file_path}: No deployment records found in file"
            self.validation_results['warnings'].append(warning_msg)
            self.log(warning_msg)
            # Still consider file valid, just no records
            self.validation_results['files_valid'] += 1
            return True

        self.log(f"Found {len(records)} deployment records in {file_path.name}")
        self.validation_results['total_records'] += len(records)
        file_detail['records'] = len(records)

        # Validate each record
        valid_count = 0
        for i, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                error_msg = f"{file_path}: Record {i} - Expected dict, got {type(record)}"
                self.validation_results['errors'].append(error_msg)
                self.log(error_msg, is_error=True)
                self.validation_results['invalid_records'] += 1
                file_detail['invalid'] += 1
                continue

            if self.validate_deployment_record(record, i, file_path_str):
                valid_count += 1
                file_detail['valid'] += 1
            else:
                self.validation_results['invalid_records'] += 1
                file_detail['invalid'] += 1

        self.validation_results['valid_records'] += valid_count
        self.validation_results['file_details'].append(file_detail)

        # File is considered valid if at least one record is valid
        is_valid = valid_count > 0
        if is_valid:
            self.validation_results['files_valid'] += 1
            self.log(f"✅ {file_path.name}: {valid_count}/{len(records)} records valid")
        else:
            self.validation_results['files_invalid'] += 1
            self.log(f"❌ {file_path.name}: No valid records found", is_error=True)

        return is_valid

    def print_summary(self):
        """Print validation summary."""
        print("\n" + "="*60)
        print("DEPLOYMENT DATA VALIDATION SUMMARY")
        print("="*60)

        print(f"\n📁 Files Processed:")
        print(f"  Files checked:     {self.validation_results['files_checked']}")
        print(f"  Files valid:       {self.validation_results['files_valid']}")
        print(f"  Files invalid:     {self.validation_results['files_invalid']}")
        print(f"  Files missing:     {self.validation_results['files_missing']}")

        print(f"\n📊 Records Validated:")
        print(f"  Total records:     {self.validation_results['total_records']}")
        print(f"  Valid records:     {self.validation_results['valid_records']}")
        print(f"  Invalid records:   {self.validation_results['invalid_records']}")

        if self.validation_results['total_records'] > 0:
            success_rate = (self.validation_results['valid_records'] / self.validation_results['total_records']) * 100
            print(f"  Success rate:      {success_rate:.1f}%")

        # Print file-by-file breakdown
        if self.validation_results['file_details']:
            print(f"\n📋 File-by-File Breakdown:")
            for detail in self.validation_results['file_details']:
                file_name = Path(detail['file']).name
                print(f"  {file_name}:")
                print(f"    Records: {detail['records']}, Valid: {detail['valid']}, Invalid: {detail['invalid']}")

        print(f"\n⚠️  Issues Found:")
        print(f"  Errors:            {len(self.validation_results['errors'])}")
        print(f"  Warnings:          {len(self.validation_results['warnings'])}")

        if self.validation_results['errors']:
            print(f"\n❌ Errors:")
            for error in self.validation_results['errors']:
                print(f"  - {error}")

        if self.validation_results['warnings']:
            print(f"\n⚠️  Warnings:")
            for warning in self.validation_results['warnings']:
                print(f"  - {warning}")

        print("\n" + "="*60)

        # Return exit code based on validation results
        has_errors = self.validation_results['files_invalid'] > 0 or len(self.validation_results['errors']) > 0
        return 1 if has_errors else 0


def main():
    """Main entry point for deployment data validation."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Validate deployment data JSON files'
    )
    parser.add_argument(
        'files',
        nargs='+',
        help='Deployment JSON files to validate'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Reduce output verbosity'
    )

    args = parser.parse_args()

    validator = DeploymentValidator(verbose=not args.quiet)

    print("🔍 Starting deployment data validation...")
    print(f"📁 Files to validate: {len(args.files)}\n")

    # Validate each file
    for file_path_str in args.files:
        file_path = Path(file_path_str)
        validator.validate_deployment_file(file_path)

    # Print summary and exit
    exit_code = validator.print_summary()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
