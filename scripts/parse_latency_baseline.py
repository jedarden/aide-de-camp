#!/usr/bin/env python3
"""
Parse raw timing data files from latency baseline tests (adc-21k11).

Extracts timing data from all three shape tests and organizes them by:
- Shape (step1_multi_status, step2_lookup_logs, step3_brainstorm)
- Dispatch iteration
- Timing stage (router, fetch, synthesize, escalate)
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


def load_timing_file(file_path: Path) -> Dict[str, Any]:
    """Load a single timing JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def extract_stages(timing_record: Dict[str, Any]) -> Dict[str, float]:
    """Extract non-null timing stages from a record."""
    stages = {}
    stage_fields = [
        'router_ms',
        'fetch_first_source_ms',
        'fetch_total_ms',
        'synthesize_first_token_ms',
        'synthesize_total_ms',
        'escalate_ms',
        'sse_emit_ms',
        'stt_ms',
        'first_render_ms'
    ]

    for field in stage_fields:
        value = timing_record.get(field)
        if value is not None:
            # Store stage without _ms suffix
            stage_name = field.replace('_ms', '')
            stages[stage_name] = value

    return stages


def parse_all_shapes(data_dir: Path) -> Dict[str, Any]:
    """Parse all shape timing files and organize the data."""

    # Shape files
    shape_files = {
        'shape1': 'latency-baseline-shape1-20260723_170941.json',
        'shape2': 'latency-baseline-shape2-20260723_171458.json',
        'shape3': 'latency-baseline-shape3-20260723_172011.json'
    }

    consolidated = {
        'metadata': {
            'parser_version': '1.0.0',
            'parsed_at': datetime.now().isoformat(),
            'source_bead': 'adc-21k11',
            'total_shapes': len(shape_files),
            'shapes': {}
        },
        'shapes': {},
        'all_stages': set(),
        'summary': {
            'total_records': 0,
            'records_by_shape': {}
        }
    }

    # Process each shape
    for shape_key, filename in shape_files.items():
        file_path = data_dir / filename
        print(f"Loading {shape_key}: {filename}")

        try:
            data = load_timing_file(file_path)

            # Extract metadata
            shape_metadata = data.get('metadata', {})
            shape_name = shape_metadata.get('shape', shape_key)

            consolidated['metadata']['shapes'][shape_key] = {
                'file': filename,
                'shape': shape_name,
                'shape_description': shape_metadata.get('shape_description', ''),
                'utterance': shape_metadata.get('utterance', ''),
                'timestamp': shape_metadata.get('timestamp', ''),
                'target_runs': shape_metadata.get('target_runs', 0),
                'successful_runs': shape_metadata.get('successful_runs', 0),
                'timing_records': shape_metadata.get('timing_records', 0)
            }

            # Process raw timings
            raw_timings = data.get('raw_timings', [])
            consolidated['summary']['records_by_shape'][shape_key] = len(raw_timings)
            consolidated['summary']['total_records'] += len(raw_timings)

            shape_data = {
                'metadata': consolidated['metadata']['shapes'][shape_key],
                'analysis': data.get('analysis', {}),
                'dispatches': []
            }

            # Organize by dispatch iteration
            for idx, record in enumerate(raw_timings, start=1):
                stages = extract_stages(record)

                # Track all stages seen across all shapes
                consolidated['all_stages'].update(stages.keys())

                dispatch = {
                    'iteration': idx,
                    'intent_id': record.get('intent_id', ''),
                    'created_at': record.get('created_at', None),
                    'stages': stages
                }

                shape_data['dispatches'].append(dispatch)

            consolidated['shapes'][shape_key] = shape_data

        except FileNotFoundError:
            print(f"ERROR: File not found: {file_path}")
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in {filename}: {e}")

    # Convert set to sorted list for JSON serialization
    consolidated['all_stages'] = sorted(list(consolidated['all_stages']))

    return consolidated


def main():
    """Main entry point."""
    # Setup paths
    project_root = Path('/home/coding/aide-de-camp')
    data_dir = project_root / 'data'
    output_dir = project_root / 'data' / 'parsed'

    # Create output directory if needed
    output_dir.mkdir(exist_ok=True)

    print("Parsing latency baseline timing data...")
    print(f"Data directory: {data_dir}")
    print(f"Output directory: {output_dir}")
    print()

    # Parse all shapes
    consolidated = parse_all_shapes(data_dir)

    # Write consolidated output
    output_file = output_dir / 'latency_baseline_consolidated.json'
    print(f"Writing consolidated data to: {output_file}")

    with open(output_file, 'w') as f:
        json.dump(consolidated, f, indent=2)

    # Print summary
    print()
    print("=" * 60)
    print("PARSING COMPLETE")
    print("=" * 60)
    print(f"Total shapes processed: {consolidated['metadata']['total_shapes']}")
    print(f"Total timing records: {consolidated['summary']['total_records']}")
    print()
    print("Records by shape:")
    for shape, count in consolidated['summary']['records_by_shape'].items():
        print(f"  {shape}: {count} records")
    print()
    print("All stages identified:")
    for stage in consolidated['all_stages']:
        print(f"  - {stage}")
    print()
    print(f"Output written to: {output_file}")


if __name__ == '__main__':
    main()
