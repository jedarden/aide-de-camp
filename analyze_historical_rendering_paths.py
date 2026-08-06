#!/usr/bin/env python3
"""
Analyze historical results to determine which rendering path was taken.

This script traces through historical results to understand:
1. Which results used component-library rendering
2. Which results used fallback rendering
3. Which results used generic topic card rendering
4. Why component adoption is so low (2 components for 376 results)

This is a READ-ONLY analysis - it doesn't modify the running system.
"""

import sqlite3
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Any, Optional

# Database paths
SESSION_DB = Path("/home/coding/aide-de-camp/data/session.db")
COMPONENTS_DB = Path("/home/coding/aide-de-camp/data/components.db")


def get_all_patterns() -> Dict[str, Dict[str, Any]]:
    """Get all component usage patterns."""
    conn = sqlite3.connect(COMPONENTS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT result_type, component_id, layout_bucket, match_score, sample_count
        FROM component_usage_patterns
    """)
    patterns = {}
    for row in cursor.fetchall():
        key = f"{row['result_type']}|{row['layout_bucket']}"
        patterns[key] = {
            "result_type": row["result_type"],
            "component_id": row["component_id"],
            "layout_bucket": row["layout_bucket"],
            "match_score": row["match_score"],
            "sample_count": row["sample_count"]
        }
    conn.close()
    return patterns


def classify_result_rendering_path(result: Dict[str, Any], patterns: Dict[str, Dict[str, Any]]) -> str:
    """
    Classify which rendering path a result took based on its data.

    Returns one of:
    - "component_library": Result used a component from the library
    - "fallback": Result used the built-in fallback card
    - "generic_topic": Result used the generic topic card rendering
    - "unknown": Cannot determine from available data
    """
    result_type = result.get("result_type") or "<NULL>"
    card_fallback = result.get("card_fallback", 0)

    # Check if this result_type has a matching pattern
    pattern_key = f"{result_type}|normal"
    has_pattern = pattern_key in patterns and patterns[pattern_key]["match_score"] >= 0.7

    if card_fallback == 1:
        # Explicitly marked as fallback
        return "fallback"
    elif card_fallback == 0 and has_pattern:
        # Has card_fallback=0 and a matching pattern -> used component library
        return "component_library"
    elif card_fallback == 0 and not has_pattern:
        # Has card_fallback=0 but NO matching pattern -> generic topic card
        # This is the ANOMALY case
        return "generic_topic"
    else:
        return "unknown"


def analyze_all_results() -> Dict[str, Any]:
    """Analyze all results to classify their rendering paths."""
    conn = sqlite3.connect(SESSION_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all results with relevant fields
    cursor.execute("""
        SELECT
            id,
            result_type,
            card_fallback,
            summary,
            created_at,
            intent_id,
            topic_id
        FROM results
        ORDER BY created_at DESC
    """)

    patterns = get_all_patterns()
    results_by_path = defaultdict(list)
    path_counts = Counter()
    result_type_paths = defaultdict(lambda: Counter())

    for row in cursor.fetchall():
        result = dict(row)
        path = classify_result_rendering_path(result, patterns)

        results_by_path[path].append({
            "id": result["id"],
            "result_type": result["result_type"] or "<NULL>",
            "card_fallback": result["card_fallback"],
            "summary": result["summary"][:80] if result["summary"] else None,
            "created_at": result["created_at"]
        })

        path_counts[path] += 1
        result_type_paths[result["result_type"] or "<NULL>"][path] += 1

    conn.close()

    return {
        "path_counts": dict(path_counts),
        "results_by_path": dict(results_by_path),
        "result_type_paths": dict(result_type_paths),
        "total_results": sum(path_counts.values())
    }


def print_detailed_report():
    """Print a comprehensive report of rendering path analysis."""
    print("=" * 80)
    print("HISTORICAL RENDERING PATH ANALYSIS")
    print("=" * 80)
    print()

    analysis = analyze_all_results()

    print("## OVERALL RENDERING PATH DISTRIBUTION")
    print()
    total = analysis["total_results"]
    for path, count in sorted(analysis["path_counts"].items(), key=lambda x: -x[1]):
        percentage = (count / total) * 100
        print(f"  {path}: {count} ({percentage:.1f}%)")
    print()

    print("## RENDERING PATHS EXPLAINED")
    print()
    print("  1. component_library: Result matched a component in the library")
    print("     - Has card_fallback=0 AND a matching component_usage_patterns entry")
    print("     - Should have rendered_html and component_id")
    print()
    print("  2. fallback: Result used the built-in generic fallback card")
    print("     - Has card_fallback=1")
    print("     - Canvas renders createFallbackCard() (key/value grid)")
    print()
    print("  3. generic_topic: Result used generic topic card rendering")
    print("     - Has card_fallback=0 BUT NO matching component_usage_patterns entry")
    print("     - This is the ANOMALY case - shouldn't happen on hot path")
    print("     - Canvas falls back to generic topic card (lines 120-174 in canvas.js)")
    print()
    print("  4. unknown: Cannot determine from available data")
    print()

    print("## TOP RESULT TYPES BY RENDERING PATH")
    print()

    # Get top 10 result types by total count
    top_types = sorted(
        analysis["result_type_paths"].items(),
        key=lambda x: -sum(x[1].values())
    )[:10]

    for result_type, path_counts in top_types:
        total_type = sum(path_counts.values())
        print(f"  result_type='{result_type}': {total_type} total results")
        for path, count in sorted(path_counts.items(), key=lambda x: -x[1]):
            pct = (count / total_type) * 100
            print(f"    {path}: {count} ({pct:.1f}%)")
        print()

    print("## SAMPLE RESULTS BY RENDERING PATH")
    print()

    for path in ["component_library", "fallback", "generic_topic"]:
        if path in analysis["results_by_path"]:
            results = analysis["results_by_path"][path][:5]
            print(f"  {path} (showing 5 of {len(analysis['results_by_path'][path])} total):")
            for r in results:
                print(f"    - {r['id']}: result_type='{r['result_type']}', summary='{r['summary']}'")
            print()

    print("## KEY FINDINGS")
    print()

    component_count = analysis["path_counts"].get("component_library", 0)
    fallback_count = analysis["path_counts"].get("fallback", 0)
    generic_count = analysis["path_counts"].get("generic_topic", 0)

    print(f"1. **Component library adoption**: {component_count} results ({(component_count/total)*100:.1f}%)")
    print(f"   - Only used 'status' result_type via comp-6ebcd2a2538b")
    print(f"   - UI-regen agent rarely/never invoked for novel shapes")
    print()

    print(f"2. **Fallback card usage**: {fallback_count} results ({(fallback_count/total)*100:.1f}%)")
    print(f"   - Used for specific result_types without matching components")
    print(f"   - Examples: 'status:aide-de-camp', 'lookup:logs:general'")
    print()

    print(f"3. **Generic topic card usage**: {generic_count} results ({(generic_count/total)*100:.1f}%)")
    print(f"   - **THIS IS THE ANOMALY**: {generic_count} results have card_fallback=0 but no matching pattern")
    print(f"   - These should have either matched a component OR been marked as fallback")
    print(f"   - Indicates hot-path renderer may not be invoked for these results")
    print()

    print("4. **Root cause analysis**:")
    print()
    print("   The data suggests the hot-path renderer (hot_path.py) is NOT being")
    print("   invoked for all results. Instead, there may be:")
    print()
    print("   a) An alternative code path that sets card_fallback=0 by default")
    print("   b) A bug where result_type is not being derived correctly")
    print("   c) Direct canvas rendering without server-side component selection")
    print()

    print("5. **Component library stewardship**:")
    print()
    print("   The UI-regen agent (src/agents/ui_regen.py) is effectively dead code:")
    print(f"   - Only 2 components ever created (one with 0 usage)")
    print(f"   - No new components for {generic_count} generic-rendered results")
    print(f"   - Component usage patterns not being learned/recorded")
    print()

    print("## RECOMMENDATIONS")
    print()
    print("1. **Add logging** to hot_path.py render() to track invocations")
    print("2. **Add logging** to intent/router.py to trace when renderer is called")
    print("3. **Add logging** to canvas.js createTopicCard() to see actual render path")
    print("4. **Investigate** why card_fallback=0 for results without matching patterns")
    print("5. **Trace** derive_result_type() calls to ensure result_type is set correctly")
    print()


if __name__ == "__main__":
    print_detailed_report()
