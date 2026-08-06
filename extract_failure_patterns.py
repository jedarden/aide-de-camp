#!/usr/bin/env python3
"""
Extract and categorize failure patterns from deployment datasets.
Creates intermediate JSON file with categorized failure patterns, counts, and evidence.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import re

def load_deployment_analysis():
    """Load the existing deployment analysis data."""
    analysis_file = Path("docs/research/deployment-analysis-30d.json")
    if not analysis_file.exists():
        raise FileNotFoundError(f"Analysis file not found: {analysis_file}")

    with open(analysis_file, 'r') as f:
        return json.load(f)

def categorize_failure_patterns(analysis_data):
    """Extract and categorize failure patterns from analysis data."""

    failure_patterns = {
        "metadata": {
            "extraction_date": datetime.now().isoformat(),
            "analysis_period": analysis_data["analysis_metadata"]["analysis_period"],
            "services_analyzed": analysis_data["analysis_metadata"]["services_analyzed"],
            "cluster": analysis_data["analysis_metadata"]["cluster"]
        },
        "failure_categories": {
            "technical_failures": {
                "description": "Deployment failures due to technical issues",
                "patterns": []
            },
            "configuration_issues": {
                "description": "Failures related to configuration drift or mismatches",
                "patterns": []
            },
            "operational_patterns": {
                "description": "Deployment velocity and operational patterns",
                "patterns": []
            },
            "positive_patterns": {
                "description": "Patterns indicating stability and reliability",
                "patterns": []
            },
            "absent_failure_modes": {
                "description": "Failure types that did not occur (indicating good practices)",
                "patterns": []
            }
        }
    }

    failure_data = analysis_data.get("failure_patterns", {})
    mode_breakdown = failure_data.get("failure_mode_breakdown", {})

    # Process PBX-web failures
    pbx_web_data = mode_breakdown.get("pbx_web", {})

    # Technical failures - probe failures
    tech_failures = pbx_web_data.get("technical_deployment_failures", {})
    probe_failure = tech_failures.get("probe_failures", {})
    if probe_failure.get("count", 0) > 0:
        failure_patterns["failure_categories"]["technical_failures"]["patterns"].append({
            "type": "Health Check/Probe Failure",
            "service": "pbx-web",
            "count": probe_failure["count"],
            "severity": probe_failure["severity"],
            "description": probe_failure["description"],
            "date": probe_failure.get("date", "N/A"),
            "resolution": probe_failure.get("resolution", "N/A"),
            "root_cause": probe_failure.get("root_cause", "N/A"),
            "evidence": f"Deployment failed on {probe_failure.get('date', 'N/A')} with {probe_failure.get('severity', 'unknown')} severity. {probe_failure.get('description', '')}"
        })

    # Configuration issues - config drift
    config_drift = pbx_web_data.get("config_drift", {})
    if config_drift.get("count", 0) > 0:
        failure_patterns["failure_categories"]["configuration_issues"]["patterns"].append({
            "type": "Configuration Drift/Same-Day Rollback",
            "service": "pbx-web",
            "count": config_drift["count"],
            "severity": config_drift["severity"],
            "description": config_drift["description"],
            "date": config_drift.get("date", "N/A"),
            "resolution": config_drift.get("resolution", "N/A"),
            "root_cause": config_drift.get("root_cause", "N/A"),
            "evidence": f"Same-day rollback on {config_drift.get('date', 'N/A')} within 10 minutes, indicating {config_drift.get('severity', '')} severity configuration issue."
        })

    # Process Whisper-stt patterns
    whisper_data = mode_breakdown.get("whisper_stt", {})

    # Operational patterns - rapid deployment churn
    rapid_churn = whisper_data.get("rapid_deployment_churn", {})
    if rapid_churn.get("count", 0) > 0:
        failure_patterns["failure_categories"]["operational_patterns"]["patterns"].append({
            "type": "Rapid Deployment Churn",
            "service": "whisper-stt",
            "count": rapid_churn["count"],
            "severity": rapid_churn["severity"],
            "description": rapid_churn["description"],
            "date": rapid_churn.get("date", "N/A"),
            "versions": rapid_churn.get("versions", []),
            "root_cause": rapid_churn.get("root_cause", "N/A"),
            "evidence": f"3 deployments in 17 minutes ({' → '.join(rapid_churn.get('versions', []))}) suggesting iterative fixes or configuration tuning."
        })

    # Service-specific patterns
    service_specific = failure_data.get("service_specific_patterns", {})

    # PBX-web specific patterns
    for pattern in service_specific.get("pbx_web_specific", []):
        if pattern["severity"] in ["info", "positive"]:
            failure_patterns["failure_categories"]["operational_patterns"]["patterns"].append({
                "type": pattern["pattern"],
                "service": "pbx-web",
                "category": pattern["category"],
                "severity": pattern["severity"],
                "description": pattern["description"],
                "count": 1,  # Pattern observed once
                "evidence": pattern["description"]
            })

    # Whisper-stt specific patterns
    for pattern in service_specific.get("whisper_stt_specific", []):
        if pattern["severity"] == "positive":
            failure_patterns["failure_categories"]["positive_patterns"]["patterns"].append({
                "type": pattern["pattern"],
                "service": "whisper-stt",
                "category": pattern["category"],
                "severity": pattern["severity"],
                "description": pattern["description"],
                "count": 1,
                "evidence": pattern["description"]
            })

    # Common patterns (absent failure modes)
    common_patterns = failure_data.get("common_patterns_across_services", {})
    for pattern_name, pattern_data in common_patterns.items():
        if isinstance(pattern_data, dict) and "pattern" in pattern_data:
            failure_patterns["failure_categories"]["absent_failure_modes"]["patterns"].append({
                "type": pattern_data["pattern"],
                "services": ["pbx-web", "whisper-stt"],
                "pbx_web_count": pattern_data.get("pbx_web", 0),
                "whisper_stt_count": pattern_data.get("whisper_stt", 0),
                "analysis": pattern_data.get("analysis", "N/A"),
                "evidence": f"Across both services: pbx-web={pattern_data.get('pbx_web', 0)} events, whisper-stt={pattern_data.get('whisper_stt', 0)} events. {pattern_data.get('analysis', '')}"
            })

    # Generate rankings
    failure_patterns["rankings"] = generate_rankings(failure_patterns)

    return failure_patterns

def generate_rankings(failure_patterns):
    """Generate rankings by frequency and severity."""
    rankings = {
        "by_frequency": [],
        "by_severity": {
            "high": [],
            "medium": [],
            "low": [],
            "info": [],
            "positive": []
        }
    }

    all_patterns = []
    for category, data in failure_patterns["failure_categories"].items():
        for pattern in data["patterns"]:
            all_patterns.append({
                "category": category,
                **pattern
            })

    # Sort by count (descending)
    rankings["by_frequency"] = sorted(
        all_patterns,
        key=lambda x: x.get("count", 0),
        reverse=True
    )[:10]  # Top 10

    # Group by severity
    for pattern in all_patterns:
        severity = pattern.get("severity", "unknown")
        if severity in rankings["by_severity"]:
            rankings["by_severity"][severity].append(pattern)

    # Sort severity lists by count
    for severity in rankings["by_severity"]:
        rankings["by_severity"][severity] = sorted(
            rankings["by_severity"][severity],
            key=lambda x: x.get("count", 0),
            reverse=True
        )

    return rankings

def save_failure_patterns(failure_patterns, output_path):
    """Save failure patterns to intermediate JSON file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(failure_patterns, f, indent=2)

    print(f"✓ Failure patterns saved to {output_path}")

def print_summary(failure_patterns):
    """Print summary of extracted failure patterns."""
    print("\n" + "="*60)
    print("FAILURE PATTERN EXTRACTION SUMMARY")
    print("="*60)

    print(f"\nAnalysis Period: {failure_patterns['metadata']['analysis_period']}")
    print(f"Services: {', '.join(failure_patterns['metadata']['services_analyzed'])}")

    print("\n" + "-"*60)
    print("TOP FAILURE TYPES BY FREQUENCY")
    print("-"*60)

    for i, pattern in enumerate(failure_patterns["rankings"]["by_frequency"][:5], 1):
        print(f"\n{i}. {pattern['type']} ({pattern.get('service', 'N/A')})")
        print(f"   Count: {pattern.get('count', 0)}")
        print(f"   Severity: {pattern.get('severity', 'N/A')}")
        print(f"   Description: {pattern.get('description', 'N/A')}")

    print("\n" + "-"*60)
    print("FAILURE CATEGORIES")
    print("-"*60)

    for category_name, category_data in failure_patterns["failure_categories"].items():
        pattern_count = len(category_data["patterns"])
        if pattern_count > 0:
            print(f"\n{category_name.upper().replace('_', ' ')}: {pattern_count} patterns")
            for pattern in category_data["patterns"][:2]:  # Show first 2
                print(f"  - {pattern['type']}")

    print("\n" + "="*60)

def main():
    """Main extraction function."""
    print("Extracting failure patterns from deployment datasets...")

    try:
        # Load existing analysis
        analysis_data = load_deployment_analysis()
        print("✓ Loaded deployment analysis data")

        # Categorize failure patterns
        failure_patterns = categorize_failure_patterns(analysis_data)
        print("✓ Categorized failure patterns")

        # Save to intermediate file
        output_path = "docs/research/failure-patterns-intermediate.json"
        save_failure_patterns(failure_patterns, output_path)

        # Print summary
        print_summary(failure_patterns)

        print(f"\n✓ Failure pattern extraction complete!")
        print(f"  Output: {output_path}")

    except Exception as e:
        print(f"✗ Error: {e}")
        raise

if __name__ == "__main__":
    main()