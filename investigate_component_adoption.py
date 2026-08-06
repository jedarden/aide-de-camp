#!/usr/bin/env python3
"""
Investigation script to trace component library adoption issues.

This script analyzes why component adoption is so low:
- Only 2 components exist (pod-status with 0 usage, status with 5 usage)
- Only 1 component_usage_pattern entry exists
- Yet 353 results have card_fallback=0 (supposedly component-rendered)
- 376 total results vs only 2 components suggests rendering path issues
"""

import sqlite3
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Any

# Database paths
SESSION_DB = Path("/home/coding/aide-de-camp/data/session.db")
COMPONENTS_DB = Path("/home/coding/aide-de-camp/data/components.db")


def analyze_results() -> Dict[str, Any]:
    """Analyze results table to understand rendering paths."""
    conn = sqlite3.connect(SESSION_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Total counts
    cursor.execute("SELECT COUNT(*) as total FROM results")
    total = cursor.fetchone()["total"]

    # Card_fallback distribution
    cursor.execute("""
        SELECT card_fallback, COUNT(*) as count
        FROM results
        GROUP BY card_fallback
    """)
    fallback_dist = {row["card_fallback"]: row["count"] for row in cursor.fetchall()}

    # Result type distribution with fallback status
    cursor.execute("""
        SELECT
            COALESCE(result_type, '<NULL>') as result_type,
            card_fallback,
            COUNT(*) as count
        FROM results
        GROUP BY result_type, card_fallback
        ORDER BY count DESC
    """)
    result_types = []
    for row in cursor.fetchall():
        result_types.append({
            "result_type": row["result_type"],
            "card_fallback": row["card_fallback"],
            "count": row["count"]
        })

    # Sample results for each major type
    samples = defaultdict(list)
    cursor.execute("""
        SELECT
            COALESCE(result_type, '<NULL>') as result_type,
            card_fallback,
            substr(summary, 1, 80) as summary,
            id
        FROM results
        ORDER BY created_at DESC
    """)
    for row in cursor.fetchall():
        rt = row["result_type"]
        fb = row["card_fallback"]
        key = f"{rt}|fallback={fb}"
        if len(samples[key]) < 3:  # Keep 3 samples per key
            samples[key].append({
                "id": row["id"],
                "summary": row["summary"]
            })

    conn.close()

    return {
        "total_results": total,
        "fallback_distribution": fallback_dist,
        "result_type_distribution": result_types,
        "samples": dict(samples)
    }


def analyze_components() -> Dict[str, Any]:
    """Analyze component library state."""
    conn = sqlite3.connect(COMPONENTS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Component counts
    cursor.execute("SELECT COUNT(*) as count FROM components")
    total_components = cursor.fetchone()["count"]

    # Component details
    cursor.execute("""
        SELECT id, name, description, usage_count, last_used, version
        FROM components
        ORDER BY usage_count DESC
    """)
    components = []
    for row in cursor.fetchall():
        components.append({
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "usage_count": row["usage_count"],
            "last_used": row["last_used"],
            "version": row["version"]
        })

    # Component usage patterns
    cursor.execute("SELECT COUNT(*) as count FROM component_usage_patterns")
    total_patterns = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT result_type, component_id, layout_bucket, match_score, sample_count, updated_at
        FROM component_usage_patterns
        ORDER BY match_score DESC, sample_count DESC
    """)
    patterns = []
    for row in cursor.fetchall():
        patterns.append({
            "result_type": row["result_type"],
            "component_id": row["component_id"],
            "layout_bucket": row["layout_bucket"],
            "match_score": row["match_score"],
            "sample_count": row["sample_count"],
            "updated_at": row["updated_at"]
        })

    # Card cache
    cursor.execute("SELECT COUNT(*) as count FROM card_cache")
    cache_count = cursor.fetchone()["count"]

    conn.close()

    return {
        "total_components": total_components,
        "components": components,
        "total_patterns": total_patterns,
        "patterns": patterns,
        "cache_count": cache_count
    }


def trace_rendering_anomaly() -> Dict[str, Any]:
    """Trace why card_fallback=0 results don't match patterns."""
    # Get result types with card_fallback=0 from session.db
    session_conn = sqlite3.connect(SESSION_DB)
    session_conn.row_factory = sqlite3.Row
    session_cursor = session_conn.cursor()

    session_cursor.execute("""
        SELECT
            COALESCE(result_type, '<NULL>') as result_type,
            COUNT(*) as result_count
        FROM results
        WHERE card_fallback = 0
        GROUP BY result_type
        ORDER BY result_count DESC
    """)
    fallback_zero_types = {row["result_type"]: row["result_count"] for row in session_cursor.fetchall()}
    session_conn.close()

    # Get result types that have patterns from components.db
    comp_conn = sqlite3.connect(COMPONENTS_DB)
    comp_conn.row_factory = sqlite3.Row
    comp_cursor = comp_conn.cursor()

    comp_cursor.execute("""
        SELECT DISTINCT result_type
        FROM component_usage_patterns
        WHERE layout_bucket = 'normal' AND match_score >= 0.7
    """)
    pattern_types = {row["result_type"] for row in comp_cursor.fetchall()}
    comp_conn.close()

    # Find anomaly: result types with card_fallback=0 but no pattern
    anomaly_types = []
    for result_type, count in fallback_zero_types.items():
        has_pattern = result_type in pattern_types
        anomaly_types.append({
            "result_type": result_type,
            "result_count": count,
            "has_pattern": has_pattern
        })

    return {
        "anomaly_types": anomaly_types,
        "anomaly_count": len([t for t in anomaly_types if not t["has_pattern"]]),
        "pattern_types": pattern_types
    }


def print_report():
    """Print comprehensive investigation report."""
    print("=" * 80)
    print("COMPONENT LIBRARY ADOPTION INVESTIGATION")
    print("=" * 80)
    print()

    # Results analysis
    print("## RESULTS ANALYSIS")
    results = analyze_results()
    print(f"Total results: {results['total_results']}")
    print()
    print("Card fallback distribution:")
    for fb, count in results["fallback_distribution"].items():
        percentage = (count / results["total_results"]) * 100
        print(f"  card_fallback={fb}: {count} ({percentage:.1f}%)")
    print()

    print("Top result types by count:")
    for rt in results["result_type_distribution"][:10]:
        print(f"  result_type='{rt['result_type']}': card_fallback={rt['card_fallback']}, count={rt['count']}")

    # Component analysis
    print()
    print("## COMPONENT LIBRARY STATE")
    comp = analyze_components()
    print(f"Total components: {comp['total_components']}")
    print(f"Total usage patterns: {comp['total_patterns']}")
    print(f"Card cache entries: {comp['cache_count']}")
    print()

    print("Components:")
    for c in comp["components"]:
        print(f"  {c['id']}: name='{c['name']}', usage_count={c['usage_count']}, version={c['version']}")
    print()

    print("Usage patterns:")
    for p in comp["patterns"]:
        print(f"  result_type='{p['result_type']}' -> component={p['component_id']}, match_score={p['match_score']}, sample_count={p['sample_count']}")
    print()

    # Anomaly detection
    print("## RENDERING PATH ANOMALY DETECTION")
    anomaly = trace_rendering_anomaly()
    print(f"Result types with card_fallback=0 but NO matching pattern: {anomaly['anomaly_count']}")
    print()
    print("Anomalous result types:")
    for t in anomaly["anomaly_types"][:10]:
        status = "⚠️  ANOMALY" if not t["has_pattern"] else "✓ OK"
        print(f"  {status} result_type='{t['result_type']}': {t['result_count']} results, has_pattern={t['has_pattern']}")

    # Key findings
    print()
    print("## KEY FINDINGS")
    print()

    card_fallback_0 = results["fallback_distribution"].get(0, 0)
    card_fallback_1 = results["fallback_distribution"].get(1, 0)

    print(f"1. **Component adoption is severely low**: {comp['total_components']} components for {results['total_results']} results")
    print(f"2. **Rendering path mismatch**: {card_fallback_0} results have card_fallback=0 (supposedly component-rendered)")
    print(f"   but only {comp['total_patterns']} usage pattern exists")
    print(f"3. **Cache is empty**: {comp['cache_count']} entries in card_cache despite {card_fallback_0} component-rendered results")
    print(f"4. **Anomaly count**: {anomaly['anomaly_count']} result types have card_fallback=0 WITHOUT matching patterns")
    print()
    print("## CONCLUSIONS")
    print()
    print("The data reveals THREE distinct issues:")
    print()
    print("1. **Hot-path renderer is likely NOT being invoked** for most results.")
    print("   - 353 results have card_fallback=0 but only 1 pattern exists")
    print("   - This suggests card_fallback is being set to 0 by a different code path")
    print()
    print("2. **Component usage stats are not being recorded correctly**.")
    print("   - status component has only 5 usage_count despite 88 status results")
    print("   - card_cache is completely empty (should have 88+ entries)")
    print()
    print("3. **UI-regen agent is effectively dead code on the hot path**.")
    print("   - Only 2 components ever created (one never used)")
    print("   - No new components being generated for novel result shapes")
    print("   - 158+93 results with 'default'/'empty' types get no component love")
    print()
    print("The rendering flow appears to be:")
    print("- Results get card_fallback=0 by default (not via hot-path selection)")
    print("- Canvas falls back to generic topic card rendering (lines 120-174 in canvas.js)")
    print("- Hot-path renderer and UI-regen agent are rarely/never invoked")
    print()
    print("RECOMMENDATION:")
    print("- Add logging to hot_path.py render() method to track invocations")
    print("- Add logging to canvas.js createTopicCard() to see which render path is taken")
    print("- Check if derive_result_type() is being called for all results")


if __name__ == "__main__":
    print_report()
