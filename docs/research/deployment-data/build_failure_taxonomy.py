#!/usr/bin/env python3
"""
Build complete failure taxonomy with frequency analysis.
Applies pattern-matching rules to categorize all failures and calculates comprehensive statistics.
"""

import json
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any

def load_pattern_matching_rules() -> Dict[str, Any]:
    """Load the pattern matching rules."""
    rules_file = Path('/home/coding/aide-de-camp/docs/research/deployment-data/failure-pattern-matching-rules.json')
    with open(rules_file, 'r') as f:
        return json.load(f)

def load_classified_failures() -> Dict[str, Any]:
    """Load the classified failures data."""
    failures_file = Path('/home/coding/aide-de-camp/docs/research/deployment-data/classified-failures.json')
    with open(failures_file, 'r') as f:
        return json.load(f)

def load_pattern_analysis() -> Dict[str, Any]:
    """Load the pattern analysis data."""
    analysis_file = Path('/home/coding/aide-de-camp/docs/research/deployment-data/failure-pattern-analysis.json')
    with open(analysis_file, 'r') as f:
        return json.load(f)

def build_taxonomy_structure() -> Dict[str, Any]:
    """Build the complete taxonomy structure with all pattern categories."""

    # Load existing data
    pattern_rules = load_pattern_matching_rules()
    classified_failures = load_classified_failures()
    pattern_analysis = load_pattern_analysis()

    # Initialize taxonomy structure
    taxonomy = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "analysis_type": "complete_failure_taxonomy_with_frequency_analysis",
            "time_period": "30 days (2026-07-07 to 2026-08-06)",
            "services_analyzed": ["pbx-web", "whisper-stt"],
            "total_pattern_categories": 14,
            "pattern_matching_rules_version": pattern_rules.get("metadata", {}).get("version", "1.0.0")
        },
        "pattern_hierarchy": {
            "level_1_critical_infrastructure": {
                "description": "Failures that prevent pod startup entirely",
                "patterns": ["ImagePullBackOff", "VolumeMountFailure", "ConfigMapMissing", "SecretMissing"]
            },
            "level_2_runtime_failures": {
                "description": "Failures during pod execution",
                "patterns": ["CrashLoopBackOff", "OOMKilled"]
            },
            "level_3_health_check_failures": {
                "description": "Failures detected by probes",
                "patterns": ["StartupProbeFailure", "ReadinessProbeFailure", "LivenessProbeFailure"]
            },
            "level_4_dependency_issues": {
                "description": "Failures related to external services",
                "patterns": ["DependencyTimeout", "DatabaseConnectionFailure", "NetworkPolicyBlocked"]
            },
            "level_5_deployment_process": {
                "description": "Issues with deployment orchestration",
                "patterns": ["DeploymentRollback", "ProgressDeadlineExceeded"]
            }
        },
        "pattern_categories": {},
        "frequency_statistics": {
            "by_pattern": {},
            "by_service": {},
            "by_severity": {},
            "by_image": {},
            "temporal_distribution": {},
            "time_span_analysis": {}
        },
        "verification": {
            "total_records_processed": 0,
            "total_categorized": 0,
            "uncategorized_count": 0,
            "coverage_percentage": 0.0
        }
    }

    # Build pattern categories with statistics
    pattern_rules_list = pattern_rules.get("pattern_matching_rules", [])

    # Create a mapping from classified failure pattern types to rule pattern IDs
    pattern_type_mapping = {
        "Deployment_rollback": "DeploymentRollback",
        "ImagePullBackOff": "ImagePullBackOff",
        "CrashLoopBackOff": "CrashLoopBackOff",
        "OOMKilled": "OOMKilled",
        "Probe_failure": "ProbeFailure",
        "Dependency_timeout": "DependencyTimeout",
        "Other": "Other"
    }

    # First, initialize all pattern categories from the rules
    for pattern_rule in pattern_rules_list:
        pattern_id = pattern_rule.get("pattern_id", "Unknown")

        # Initialize empty category
        taxonomy["pattern_categories"][pattern_id] = {
            "pattern_id": pattern_id,
            "category": pattern_rule.get("category", "Unknown"),
            "severity": pattern_rule.get("severity", "unknown"),
            "description": pattern_rule.get("description", ""),
            "level": get_pattern_level(pattern_id, pattern_rules.get("pattern_hierarchy", {})),
            "total_occurrences": 0,
            "distribution_by_service": {},
            "image_version_context": {
                "images_affected": [],
                "total_unique_images": 0
            },
            "time_distribution": {
                "frequency": 0,
                "time_span_days": 0,
                "average_frequency_per_day": 0.0
            },
            "sample_occurrences": [],
            "indicators": pattern_rule.get("example_messages", []),
            "common_causes": pattern_rule.get("common_causes", []),
            "resolution_hints": pattern_rule.get("resolution_hints", []),
            "matching_rules": {
                "primary_indicators": pattern_rule.get("matching_rules", {}).get("primary_indicators", []),
                "secondary_indicators": pattern_rule.get("matching_rules", {}).get("secondary_indicators", []),
                "log_patterns": pattern_rule.get("matching_rules", {}).get("log_patterns", [])
            }
        }

    # Now populate with actual failure data
    classified_failure_list = classified_failures.get("classified_failures", [])

    for failure in classified_failure_list:
        classified_pattern = failure.get("pattern_type", "Unknown")
        # Map the classified pattern type to the rule pattern ID
        pattern_id = pattern_type_mapping.get(classified_pattern, classified_pattern)

        if pattern_id in taxonomy["pattern_categories"]:
            category = taxonomy["pattern_categories"][pattern_id]
            category["total_occurrences"] += 1

            # Add to distribution by service
            service = failure.get("service", "unknown")
            if service not in category["distribution_by_service"]:
                category["distribution_by_service"][service] = 0
            category["distribution_by_service"][service] += 1

            # Add to image version context
            image = failure.get("image", "")
            if image and image not in category["image_version_context"]["images_affected"]:
                category["image_version_context"]["images_affected"].append(image)

            # Add sample occurrence
            category["sample_occurrences"].append({
                "timestamp": failure.get("timestamp", ""),
                "date": failure.get("date", ""),
                "service": service,
                "image": image,
                "event_type": failure.get("event_type", ""),
                "notes": failure.get("notes", "")
            })
        else:
            # Pattern not found in rules - add to Other
            if "Other" in taxonomy["pattern_categories"]:
                category = taxonomy["pattern_categories"]["Other"]
                category["total_occurrences"] += 1
                service = failure.get("service", "unknown")
                if service not in category["distribution_by_service"]:
                    category["distribution_by_service"][service] = 0
                category["distribution_by_service"][service] += 1

    # Update unique image counts
    for pattern_id, category in taxonomy["pattern_categories"].items():
        category["image_version_context"]["total_unique_images"] = len(category["image_version_context"]["images_affected"])

    # Calculate comprehensive frequency statistics
    classified_failure_list = classified_failures.get("classified_failures", [])

    # Count by pattern
    pattern_counts = defaultdict(int)
    for failure in classified_failure_list:
        pattern_type = failure.get("pattern_type", "Unknown")
        pattern_counts[pattern_type] += 1

    taxonomy["frequency_statistics"]["by_pattern"] = dict(pattern_counts)

    # Count by service
    service_counts = defaultdict(int)
    service_pattern_breakdown = defaultdict(lambda: defaultdict(int))

    for failure in classified_failure_list:
        service = failure.get("service", "unknown")
        pattern_type = failure.get("pattern_type", "Unknown")
        service_counts[service] += 1
        service_pattern_breakdown[service][pattern_type] += 1

    taxonomy["frequency_statistics"]["by_service"] = dict(service_counts)
    taxonomy["frequency_statistics"]["service_pattern_breakdown"] = {
        service: dict(patterns) for service, patterns in service_pattern_breakdown.items()
    }

    # Count by severity
    severity_counts = defaultdict(int)
    for failure in classified_failure_list:
        severity = failure.get("pattern_severity", "unknown")
        severity_counts[severity] += 1

    taxonomy["frequency_statistics"]["by_severity"] = dict(severity_counts)

    # Count by image
    image_counts = defaultdict(int)
    for failure in classified_failure_list:
        image = failure.get("image", "unknown")
        image_counts[image] += 1

    taxonomy["frequency_statistics"]["by_image"] = dict(image_counts)

    # Temporal distribution
    temporal_distribution = defaultdict(int)
    for failure in classified_failure_list:
        date = failure.get("date", "unknown")
        temporal_distribution[date] += 1

    taxonomy["frequency_statistics"]["temporal_distribution"] = dict(sorted(temporal_distribution.items()))

    # Time span analysis
    if temporal_distribution:
        dates = list(temporal_distribution.keys())
        if len(dates) > 1:
            try:
                start_date = datetime.strptime(dates[0], "%Y-%m-%d")
                end_date = datetime.strptime(dates[-1], "%Y-%m-%d")
                time_span_days = (end_date - start_date).days + 1
            except:
                time_span_days = len(dates)
        else:
            time_span_days = 1
    else:
        time_span_days = 0

    taxonomy["frequency_statistics"]["time_span_analysis"] = {
        "total_dates_with_failures": len(temporal_distribution),
        "time_span_days": time_span_days,
        "first_failure_date": dates[0] if dates else None,
        "last_failure_date": dates[-1] if dates else None,
        "failure_frequency_per_day": len(classified_failure_list) / time_span_days if time_span_days > 0 else 0
    }

    # Verification
    total_records = len(classified_failure_list)
    categorized_count = sum(1 for f in classified_failure_list if f.get("pattern_type") != "Unknown")
    uncategorized_count = total_records - categorized_count

    taxonomy["verification"] = {
        "total_records_processed": total_records,
        "total_categorized": categorized_count,
        "uncategorized_count": uncategorized_count,
        "coverage_percentage": (categorized_count / total_records * 100) if total_records > 0 else 100.0,
        "all_patterns_accounted_for": uncategorized_count == 0
    }

    # Add summary
    taxonomy["summary"] = {
        "total_pattern_types_defined": len(taxonomy["pattern_categories"]),
        "total_pattern_types_with_occurrences": len([p for p in taxonomy["pattern_categories"].values() if p["total_occurrences"] > 0]),
        "total_failures_across_all_patterns": sum(p["total_occurrences"] for p in taxonomy["pattern_categories"].values()),
        "most_common_pattern": max(taxonomy["frequency_statistics"]["by_pattern"].items(), key=lambda x: x[1]) if taxonomy["frequency_statistics"]["by_pattern"] else None,
        "most_affected_service": max(taxonomy["frequency_statistics"]["by_service"].items(), key=lambda x: x[1]) if taxonomy["frequency_statistics"]["by_service"] else None,
        "overall_assessment": "HEALTHY" if total_records == categorized_count and total_records <= 1 else "NEEDS_ATTENTION"
    }

    return taxonomy

def get_pattern_level(pattern_id: str, hierarchy: Dict[str, Any]) -> int:
    """Determine the level of a pattern based on hierarchy."""
    levels = hierarchy.get("levels", [])
    for i, level in enumerate(levels):
        if pattern_id in level.get("patterns", []):
            return i + 1
    return 6  # Default to level 6 for uncategorized

def save_taxonomy(taxonomy: Dict[str, Any]) -> Path:
    """Save the taxonomy to a file."""
    output_file = Path('/home/coding/aide-de-camp/docs/research/deployment-data/failure-taxonomy-complete.json')
    with open(output_file, 'w') as f:
        json.dump(taxonomy, f, indent=2)
    return output_file

def generate_summary_report(taxonomy: Dict[str, Any]) -> str:
    """Generate a human-readable summary report."""
    report = []
    report.append("# Failure Taxonomy with Frequency Analysis")
    report.append("")
    report.append(f"**Generated:** {taxonomy['metadata']['generated_at']}")
    report.append(f"**Analysis Period:** {taxonomy['metadata']['time_period']}")
    report.append(f"**Services Analyzed:** {', '.join(taxonomy['metadata']['services_analyzed'])}")
    report.append("")

    # Summary statistics
    summary = taxonomy['summary']
    report.append("## Executive Summary")
    report.append("")
    report.append(f"- **Total pattern types defined:** {summary['total_pattern_types_defined']}")
    report.append(f"- **Pattern types with occurrences:** {summary['total_pattern_types_with_occurrences']}")
    report.append(f"- **Total failures detected:** {summary['total_failures_across_all_patterns']}")
    report.append(f"- **Overall assessment:** {summary['overall_assessment']}")
    report.append("")

    # Frequency statistics
    freq_stats = taxonomy['frequency_statistics']
    report.append("## Frequency Statistics")
    report.append("")

    if freq_stats['by_pattern']:
        report.append("### By Pattern Type")
        for pattern, count in sorted(freq_stats['by_pattern'].items(), key=lambda x: x[1], reverse=True):
            report.append(f"- **{pattern}**: {count} occurrence(s)")
        report.append("")

    if freq_stats['by_service']:
        report.append("### By Service")
        for service, count in sorted(freq_stats['by_service'].items(), key=lambda x: x[1], reverse=True):
            report.append(f"- **{service}**: {count} failure(s)")
        report.append("")

    if freq_stats['by_image']:
        report.append("### By Image Version")
        for image, count in sorted(freq_stats['by_image'].items(), key=lambda x: x[1], reverse=True):
            report.append(f"- **{image}**: {count} failure(s)")
        report.append("")

    # Temporal distribution
    if freq_stats['temporal_distribution']:
        report.append("### Temporal Distribution")
        for date, count in freq_stats['temporal_distribution'].items():
            report.append(f"- **{date}**: {count} failure(s)")
        report.append("")

    # Verification
    verification = taxonomy['verification']
    report.append("## Verification")
    report.append("")
    report.append(f"- **Total records processed:** {verification['total_records_processed']}")
    report.append(f"- **Total categorized:** {verification['total_categorized']}")
    report.append(f"- **Uncategorized:** {verification['uncategorized_count']}")
    report.append(f"- **Coverage percentage:** {verification['coverage_percentage']:.1f}%")
    report.append(f"- **All patterns accounted for:** {'✓ Yes' if verification['all_patterns_accounted_for'] else '✗ No'}")
    report.append("")

    return "\n".join(report)

def main():
    """Main entry point."""
    print("Building complete failure taxonomy with frequency analysis...")

    # Build taxonomy
    taxonomy = build_taxonomy_structure()

    # Save taxonomy
    output_file = save_taxonomy(taxonomy)
    print(f"✓ Taxonomy saved to {output_file}")

    # Generate summary report
    report = generate_summary_report(taxonomy)
    report_file = Path('/home/coding/aide-de-camp/docs/research/deployment-data/failure-taxonomy-summary.md')
    with open(report_file, 'w') as f:
        f.write(report)
    print(f"✓ Summary report saved to {report_file}")

    # Print summary
    print("\n=== TAXONOMY SUMMARY ===")
    print(f"Pattern types defined: {taxonomy['summary']['total_pattern_types_defined']}")
    print(f"Pattern types with occurrences: {taxonomy['summary']['total_pattern_types_with_occurrences']}")
    print(f"Total failures detected: {taxonomy['summary']['total_failures_across_all_patterns']}")
    print(f"Records categorized: {taxonomy['verification']['total_categorized']}/{taxonomy['verification']['total_records_processed']}")
    print(f"Coverage: {taxonomy['verification']['coverage_percentage']:.1f}%")
    print(f"Overall assessment: {taxonomy['summary']['overall_assessment']}")

    print("\n=== FREQUENCY BY PATTERN ===")
    for pattern, count in sorted(taxonomy['frequency_statistics']['by_pattern'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {pattern}: {count}")

    print("\n=== VERIFICATION ===")
    print(f"✓ All records categorized: {taxonomy['verification']['all_patterns_accounted_for']}")
    print(f"✓ Total categorized equals total records: {taxonomy['verification']['total_categorized'] == taxonomy['verification']['total_records_processed']}")

    return taxonomy

if __name__ == '__main__':
    main()
