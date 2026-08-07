#!/usr/bin/env python3
"""
Test script for log extraction functions.

This script runs extraction functions on multiple log files and validates the results.
It supports running extraction tests from the command line with file or directory inputs.

Usage:
    # Test a single file
    python test_log_extraction.py /path/to/log.log

    # Test all log files in a directory
    python test_log_extraction.py --directory /path/to/logs/

    # Test specific extraction functions
    python test_log_extraction.py --directory logs/ --functions pod_metadata deployment_metadata

    # Output as table
    python test_log_extraction.py --directory logs/ --format table

    # Output as JSON
    python test_log_extraction.py --directory logs/ --format json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import traceback


# Add project root to path
PROJECT_ROOT = Path("/home/coding/aide-de-camp")
sys.path.insert(0, str(PROJECT_ROOT))


class ExtractionResult:
    """Result of running an extraction function on a log file."""

    def __init__(
        self,
        file_path: str,
        function_name: str,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        execution_time_ms: Optional[float] = None
    ):
        self.file_path = file_path
        self.function_name = function_name
        self.success = success
        self.data = data or {}
        self.error = error
        self.execution_time_ms = execution_time_ms


def extract_pod_metadata_safe(file_path: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Safely extract pod metadata from a log file.

    Returns:
        Tuple of (success, data, error_message)
    """
    try:
        # Import here to avoid import errors if module doesn't exist
        from extract_pod_metadata import get_file_metadata, extract_timestamps_from_log_content

        if not os.path.exists(file_path):
            return False, None, f"File not found: {file_path}"

        # Get file metadata
        file_metadata = get_file_metadata(file_path)

        # Try to extract timestamps from content
        content_timestamps = extract_timestamps_from_log_content(file_path)

        # Combine results
        result = {
            **file_metadata,
            **content_timestamps,
            'log_file_path': file_path,
            'extraction_function': 'pod_metadata'
        }

        # Filter out None values
        result = {k: v for k, v in result.items() if v is not None}

        return True, result, None

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        return False, None, error_msg


def extract_log_file_metadata_safe(file_path: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Safely extract log file metadata including timestamps and file size.

    Returns:
        Tuple of (success, data, error_message)
    """
    try:
        from extract_log_file_metadata import (
            get_file_size,
            get_file_mtime,
            extract_first_log_timestamp,
            extract_deletion_timestamp_from_log
        )

        if not os.path.exists(file_path):
            return False, None, f"File not found: {file_path}"

        result = {
            'log_file_path': file_path,
            'log_size_bytes': get_file_size(file_path),
            'creation_timestamp': get_file_mtime(file_path),
            'first_log_timestamp': extract_first_log_timestamp(file_path),
            'deletion_timestamp': extract_deletion_timestamp_from_log(file_path),
            'extraction_function': 'log_file_metadata'
        }

        # Filter out None values
        result = {k: v for k, v in result.items() if v is not None}

        return True, result, None

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        return False, None, error_msg


def extract_deployment_metadata_safe(file_path: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Safely extract deployment metadata from a JSON log file.

    Returns:
        Tuple of (success, data, error_message)
    """
    try:
        if not os.path.exists(file_path):
            return False, None, f"File not found: {file_path}"

        with open(file_path, 'r') as f:
            data = json.load(f)

        # Extract common deployment fields
        result = {
            'log_file_path': file_path,
            'extraction_function': 'deployment_metadata'
        }

        # Try to extract deployment-specific fields
        if isinstance(data, list):
            result['record_count'] = len(data)
            if data:
                first_record = data[0]
                result['first_record_keys'] = list(first_record.keys()) if isinstance(first_record, dict) else []
        elif isinstance(data, dict):
            result.update({
                k: v for k, v in data.items()
                if not isinstance(v, (dict, list)) and v is not None
            })

        # Filter out large nested structures
        result = {k: v for k, v in result.items() if not isinstance(v, (dict, list)) or k == 'first_record_keys'}

        return True, result, None

    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON: {str(e)}"
        return False, None, error_msg
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        return False, None, error_msg


def extract_failure_patterns_safe(file_path: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Safely extract failure patterns from a log file.

    Returns:
        Tuple of (success, data, error_message)
    """
    try:
        if not os.path.exists(file_path):
            return False, None, f"File not found: {file_path}"

        # Read log file and search for failure patterns
        failure_patterns = {
            'error': 0,
            'failed': 0,
            'exception': 0,
            'timeout': 0,
            'connection refused': 0,
            'oom': 0,
            'crash': 0,
            'panic': 0,
            'fatal': 0,
        }

        total_lines = 0
        with open(file_path, 'r', errors='ignore') as f:
            for line in f:
                total_lines += 1
                line_lower = line.lower()
                for pattern in failure_patterns:
                    if pattern in line_lower:
                        failure_patterns[pattern] += 1

        result = {
            'log_file_path': file_path,
            'extraction_function': 'failure_patterns',
            'total_lines': total_lines,
            **failure_patterns
        }

        # Filter out zero counts
        result = {k: v for k, v in result.items() if v != 0 or k == 'total_lines'}

        return True, result, None

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        return False, None, error_msg


# Available extraction functions
EXTRACTION_FUNCTIONS = {
    'pod_metadata': extract_pod_metadata_safe,
    'log_file_metadata': extract_log_file_metadata_safe,
    'deployment_metadata': extract_deployment_metadata_safe,
    'failure_patterns': extract_failure_patterns_safe,
}


def run_extraction_on_file(file_path: str, function_names: List[str]) -> List[ExtractionResult]:
    """
    Run specified extraction functions on a single file.

    Args:
        file_path: Path to the log file
        function_names: List of extraction function names to run

    Returns:
        List of ExtractionResult objects
    """
    results = []

    for function_name in function_names:
        if function_name not in EXTRACTION_FUNCTIONS:
            results.append(ExtractionResult(
                file_path=file_path,
                function_name=function_name,
                success=False,
                error=f"Unknown function: {function_name}"
            ))
            continue

        try:
            import time
            start_time = time.time()

            extract_func = EXTRACTION_FUNCTIONS[function_name]
            success, data, error = extract_func(file_path)

            execution_time = (time.time() - start_time) * 1000  # Convert to ms

            results.append(ExtractionResult(
                file_path=file_path,
                function_name=function_name,
                success=success,
                data=data,
                error=error,
                execution_time_ms=execution_time
            ))

        except Exception as e:
            results.append(ExtractionResult(
                file_path=file_path,
                function_name=function_name,
                success=False,
                error=f"Unexpected error: {type(e).__name__}: {str(e)}"
            ))

    return results


def run_extraction_on_directory(directory: str, function_names: List[str]) -> List[ExtractionResult]:
    """
    Run extraction functions on all log files in a directory.

    Args:
        directory: Path to directory containing log files
        function_names: List of extraction function names to run

    Returns:
        List of ExtractionResult objects
    """
    results = []

    # Find all log files
    log_extensions = ['.log', '.json', '.jsonl', '.txt']
    log_files = []

    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(file.endswith(ext) for ext in log_extensions):
                log_files.append(os.path.join(root, file))

    if not log_files:
        print(f"Warning: No log files found in {directory}")
        return results

    print(f"Found {len(log_files)} log files")

    for file_path in log_files:
        file_results = run_extraction_on_file(file_path, function_names)
        results.extend(file_results)

    return results


def format_results_as_table(results: List[ExtractionResult]) -> str:
    """Format extraction results as a readable table."""
    from collections import defaultdict

    # Group results by file
    by_file = defaultdict(list)
    for result in results:
        by_file[result.file_path].append(result)

    output_lines = []
    output_lines.append("=" * 120)
    output_lines.append(f"LOG EXTRACTION TEST RESULTS - {datetime.now().isoformat()}")
    output_lines.append("=" * 120)
    output_lines.append("")

    # Summary statistics
    total = len(results)
    successful = sum(1 for r in results if r.success)
    failed = total - successful

    output_lines.append(f"Total extractions: {total}")
    output_lines.append(f"Successful: {successful} ({successful*100//total if total > 0 else 0}%)")
    output_lines.append(f"Failed: {failed} ({failed*100//total if total > 0 else 0}%)")
    output_lines.append("")

    # Per-file results
    for file_path, file_results in by_file.items():
        filename = os.path.basename(file_path)
        output_lines.append(f"📄 {filename}")
        output_lines.append(f"   Path: {file_path}")
        output_lines.append("")

        for result in file_results:
            status = "✓" if result.success else "✗"
            time_str = f" ({result.execution_time_ms:.1f}ms)" if result.execution_time_ms else ""

            output_lines.append(f"   {status} {result.function_name}{time_str}")

            if result.success and result.data:
                # Show key fields
                for key, value in sorted(result.data.items()):
                    if key == 'log_file_path':
                        continue
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value, separators=(',', ':'))[:50]
                    output_lines.append(f"      {key}: {value}")
            elif result.error:
                output_lines.append(f"      Error: {result.error}")

            output_lines.append("")

    return "\n".join(output_lines)


def format_results_as_json(results: List[ExtractionResult]) -> str:
    """Format extraction results as JSON."""
    output = {
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_extractions': len(results),
            'successful': sum(1 for r in results if r.success),
            'failed': sum(1 for r in results if not r.success),
        },
        'results': []
    }

    for result in results:
        result_dict = {
            'file_path': result.file_path,
            'function_name': result.function_name,
            'success': result.success,
            'execution_time_ms': result.execution_time_ms,
        }

        if result.success:
            result_dict['data'] = result.data
        if result.error:
            result_dict['error'] = result.error

        output['results'].append(result_dict)

    return json.dumps(output, indent=2)


def main():
    """Main entry point for the test script."""
    parser = argparse.ArgumentParser(
        description='Test script for log extraction functions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test a single file
  python test_log_extraction.py /path/to/log.log

  # Test all log files in a directory
  python test_log_extraction.py --directory /path/to/logs/

  # Test specific extraction functions
  python test_log_extraction.py --directory logs/ --functions pod_metadata deployment_metadata

  # Output as table (default)
  python test_log_extraction.py --directory logs/ --format table

  # Output as JSON
  python test_log_extraction.py --directory logs/ --format json

Available extraction functions:
  - pod_metadata: Extract pod metadata including timestamps and file size
  - log_file_metadata: Extract log file metadata (size, timestamps, deletion info)
  - deployment_metadata: Extract deployment metadata from JSON files
  - failure_patterns: Extract failure pattern counts from log content
        """
    )

    parser.add_argument(
        'file',
        nargs='?',
        help='Path to a single log file to test'
    )

    parser.add_argument(
        '--directory', '-d',
        help='Path to directory containing log files'
    )

    parser.add_argument(
        '--functions', '-f',
        nargs='+',
        default=list(EXTRACTION_FUNCTIONS.keys()),
        choices=list(EXTRACTION_FUNCTIONS.keys()),
        help='Extraction functions to run (default: all)'
    )

    parser.add_argument(
        '--format',
        choices=['table', 'json'],
        default='table',
        help='Output format (default: table)'
    )

    parser.add_argument(
        '--output', '-o',
        help='Output file path (default: stdout)'
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.file and not args.directory:
        parser.print_help()
        print("\nError: Please specify either a file or directory")
        return 1

    if args.file and args.directory:
        print("Error: Please specify only one of --file or --directory")
        return 1

    # Run extractions
    results = []

    if args.file:
        print(f"Testing single file: {args.file}")
        results = run_extraction_on_file(args.file, args.functions)
    elif args.directory:
        print(f"Testing directory: {args.directory}")
        results = run_extraction_on_directory(args.directory, args.functions)
    else:
        parser.print_help()
        print("\nError: Please specify either a file or directory")
        return 1

    if not results:
        print("No results to report")
        return 1

    # Format output
    if args.format == 'json':
        output = format_results_as_json(results)
    else:
        output = format_results_as_table(results)

    # Write output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"\nResults written to: {args.output}")
    else:
        print(output)

    return 0 if all(r.success for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
