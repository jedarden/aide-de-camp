#!/usr/bin/env python3
"""
Parse and validate all deployment data JSON files from the deployment-data directory.
Combines all records into a single structured output file.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime


def list_json_files(directory: Path) -> List[Path]:
    """List all JSON files in the given directory."""
    return sorted([f for f in directory.glob("*.json") if f.is_file()])


def parse_json_file(file_path: Path) -> Tuple[bool, Any, str]:
    """
    Parse a JSON file and return success status, data, and message.

    Returns:
        Tuple of (success: bool, data: Any, message: str)
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return True, data, f"Successfully parsed {file_path.name}"
    except json.JSONDecodeError as e:
        return False, None, f"JSON decode error in {file_path.name}: {str(e)}"
    except Exception as e:
        return False, None, f"Error reading {file_path.name}: {str(e)}"


def validate_deployment_data(data: Any, filename: str) -> Tuple[bool, str]:
    """
    Validate that the parsed JSON data has expected structure.

    Returns:
        Tuple of (is_valid: bool, message: str)
    """
    if data is None:
        return False, f"{filename}: Data is None"

    # Check if it's a list or dict with deployment-related structure
    if isinstance(data, list):
        if len(data) == 0:
            return True, f"{filename}: Empty list (valid but no data)"
        return True, f"{filename}: Valid list with {len(data)} items"

    if isinstance(data, dict):
        return True, f"{filename}: Valid dictionary with {len(data)} keys"

    return False, f"{filename}: Unexpected data type {type(data).__name__}"


def combine_deployment_data(parsed_files: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combine all parsed deployment data into a structured output.

    Returns:
        Dictionary with combined data structure
    """
    combined = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_files_parsed": len(parsed_files),
            "source_directory": str(Path(__file__).parent)
        },
        "files": {},
        "deployment_records": [],
        "metrics": {},
        "summaries": {},
        "raw_data": {}
    }

    # Categorize files based on their content
    for filename, data in parsed_files.items():
        if data is None:
            continue

        # Store raw data by filename
        combined["raw_data"][filename] = data

        # Categorize based on filename patterns
        if "deployment" in filename.lower() and "data" in filename.lower():
            combined["deployment_records"].append({
                "source": filename,
                "data": data
            })
        elif "metrics" in filename.lower():
            combined["metrics"][filename] = data
        elif "summary" in filename.lower() or "report" in filename.lower():
            combined["summaries"][filename] = data
        else:
            combined["files"][filename] = data

    return combined


def main():
    """Main execution function."""
    # Set up directory paths
    script_dir = Path(__file__).parent
    output_file = script_dir / "parsed-data.json"

    print("=" * 60)
    print("Deployment Data Parser")
    print("=" * 60)
    print(f"Directory: {script_dir}")
    print(f"Output file: {output_file}")
    print()

    # List all JSON files
    json_files = list_json_files(script_dir)
    print(f"Found {len(json_files)} JSON files:")
    for f in json_files:
        print(f"  - {f.name}")
    print()

    # Parse each JSON file
    parsed_files = {}
    parse_results = []
    parse_errors = []

    print("Parsing files...")
    for file_path in json_files:
        success, data, message = parse_json_file(file_path)
        parse_results.append(message)

        if success:
            is_valid, validation_msg = validate_deployment_data(data, file_path.name)
            print(f"  ✓ {message}")
            print(f"    {validation_msg}")
            parsed_files[file_path.name] = data
        else:
            print(f"  ✗ {message}")
            parse_errors.append(message)

    print()
    print(f"Parsed {len(parsed_files)} files successfully")
    if parse_errors:
        print(f"Encountered {len(parse_errors)} errors:")
        for error in parse_errors:
            print(f"  - {error}")
    print()

    # Combine all data
    print("Combining deployment data...")
    combined_data = combine_deployment_data(parsed_files)

    # Save to output file
    print(f"Writing combined data to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(combined_data, f, indent=2, default=str)

    print()
    print("=" * 60)
    print("Summary:")
    print(f"  Total files found: {len(json_files)}")
    print(f"  Successfully parsed: {len(parsed_files)}")
    print(f"  Parse errors: {len(parse_errors)}")
    print(f"  Output file: {output_file}")
    print(f"  Output size: {output_file.stat().st_size} bytes")
    print("=" * 60)


if __name__ == "__main__":
    main()
