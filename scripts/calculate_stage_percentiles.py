#!/usr/bin/env python3
"""
Calculate p50/p95 latencies per pipeline stage.

Processes the consolidated latency baseline data and calculates
median (p50) and 95th percentile (p95) statistics for each stage.
"""

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List


def calculate_percentiles(values: List[float]) -> Dict[str, float]:
    """Calculate p50 and p95 for a list of values."""
    if not values:
        return {"p50": None, "p95": None, "count": 0}

    sorted_values = sorted(values)
    n = len(sorted_values)

    # p50 (median)
    if n % 2 == 0:
        p50 = (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
    else:
        p50 = sorted_values[n // 2]

    # p95 - using linear interpolation
    p95_index = 0.95 * (n - 1)
    lower = int(p95_index)
    upper = min(lower + 1, n - 1)
    fraction = p95_index - lower
    p95 = sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])

    return {
        "p50": round(p50, 2),
        "p95": round(p95, 2),
        "count": n
    }


def extract_stage_values(dispatches: List[Dict], stage_name: str) -> List[float]:
    """Extract all non-null values for a specific stage from dispatches."""
    values = []
    for dispatch in dispatches:
        stage_value = dispatch.get("stages", {}).get(stage_name)
        if stage_value is not None:
            values.append(float(stage_value))
    return values


def calculate_e2e(dispatches: List[Dict]) -> List[float]:
    """Calculate end-to-end latency as sum of all stages per dispatch."""
    e2e_values = []

    for dispatch in dispatches:
        stages = dispatch.get("stages", {})
        # Sum all available stage times
        total = sum(
            float(v) for v in stages.values()
            if v is not None and isinstance(v, (int, float))
        )
        if total > 0:
            e2e_values.append(total)

    return e2e_values


def process_shape(shape_data: Dict, shape_name: str) -> Dict[str, Any]:
    """Process a single shape and calculate statistics for all stages."""
    dispatches = shape_data.get("dispatches", [])

    # Stages to analyze (mapping from task names to data keys)
    stages_to_analyze = {
        "intent_router": "router",
        "fetch_strands": "fetch_total",
        "synthesize": "synthesize_total",
        "persist": None,  # Not available in data
        "sse_broadcast": None,  # sse_emit has count=0
        "escalate": "escalate",
    }

    results = {
        "shape": shape_name,
        "shape_description": shape_data.get("metadata", {}).get("shape_description", ""),
        "total_dispatches": len(dispatches),
        "stages": {}
    }

    # Calculate p50/p95 for each available stage
    for task_name, data_key in stages_to_analyze.items():
        if data_key is None:
            # Stage not available in data
            results["stages"][task_name] = {
                "p50": None,
                "p95": None,
                "count": 0,
                "note": "Not available in data"
            }
            continue

        values = extract_stage_values(dispatches, data_key)
        stats = calculate_percentiles(values)

        if stats["count"] == 0:
            stats["note"] = "No values found"

        results["stages"][task_name] = stats

    # Calculate e2e (end-to-end)
    e2e_values = calculate_e2e(dispatches)
    e2e_stats = calculate_percentiles(e2e_values)
    results["stages"]["e2e"] = e2e_stats

    return results


def main():
    # Load the consolidated data
    data_path = Path("/home/coding/aide-de-camp/data/parsed/latency_baseline_consolidated.json")

    with open(data_path) as f:
        data = json.load(f)

    # Process each shape
    shapes_data = data.get("shapes", {})
    all_results = {}

    for shape_name, shape_data in shapes_data.items():
        print(f"Processing {shape_name}...")
        result = process_shape(shape_data, shape_name)
        all_results[shape_name] = result

    # Create summary output
    output = {
        "metadata": {
            "source_file": str(data_path),
            "total_shapes": len(all_results),
            "calculated_at": "2026-07-23T17:59:00Z"  # Placeholder
        },
        "shapes": all_results,
        "summary": {
            "total_dispatches_processed": sum(
                r["total_dispatches"] for r in all_results.values()
            ),
            "stages_analyzed": [
                "intent_router", "fetch_strands", "synthesize",
                "escalate", "e2e"
            ]
        }
    }

    # Save results
    output_path = Path("/home/coding/aide-de-camp/data/parsed/stage_percentiles.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to {output_path}")

    # Print summary table
    print("\n" + "=" * 80)
    print("P50/P95 LATENCY SUMMARY (milliseconds)")
    print("=" * 80)

    for shape_name, result in all_results.items():
        print(f"\n{shape_name.upper()} - {result['shape_description']}")
        print("-" * 80)
        print(f"{'Stage':<20} {'Count':>8} {'p50':>10} {'p95':>10}")
        print("-" * 80)

        for stage_name in ["intent_router", "fetch_strands", "synthesize", "escalate", "e2e"]:
            stage_data = result["stages"][stage_name]
            count = stage_data["count"]
            p50 = stage_data["p50"] if stage_data["p50"] is not None else "N/A"
            p95 = stage_data["p95"] if stage_data["p95"] is not None else "N/A"

            print(f"{stage_name:<20} {count:>8} {str(p50):>10} {str(p95):>10}")

    # Print verification
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    total_dispatches = output["summary"]["total_dispatches_processed"]
    print(f"Total dispatches processed: {total_dispatches}")
    print(f"Expected: ~205 (from metadata)")

    if total_dispatches >= 200:
        print("✓ Dispatch count verification passed")
    else:
        print("⚠ Dispatch count lower than expected")


if __name__ == "__main__":
    main()
