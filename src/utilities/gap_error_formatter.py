#!/usr/bin/env python3
"""
Gap Error Message Formatter

Provides actionable error messages for deployment coverage gaps.
Messages reference deployment intervals, explain expected patterns,
and suggest specific remediation steps.

This module formats gap errors consistently with schema validation errors,
providing clear, actionable guidance for operators.

Usage:
    from src.utilities.gap_error_formatter import (
        format_gap_error,
        format_gap_errors_batch,
        generate_actionable_guidance
    )

    error = format_gap_error(gap_period, context)
    messages = format_gap_errors_batch(gap_periods, context)
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from src.utilities.gap_calculator import GapPeriod, classify_gap_by_size


@dataclass
class GapContext:
    """Context information for gap error formatting."""
    service_name: str
    cluster: str = "unknown"
    expected_days: int = 30
    coverage_threshold: float = 95.0
    last_deployment_date: Optional[str] = None
    analysis_period_start: Optional[str] = None
    analysis_period_end: Optional[str] = None


def format_gap_error(
    gap: GapPeriod,
    context: GapContext
) -> str:
    """
    Format a single gap as an actionable error message.

    The message includes:
    - Gap size and date range
    - Deployment interval reference
    - Expected coverage pattern
    - Specific remediation guidance

    Args:
        gap: The gap period to format
        context: Context information (service name, cluster, etc.)

    Returns:
        Formatted error message with actionable guidance
    """
    size_class = classify_gap_by_size(gap)
    gap_type = "consecutive sequence" if gap.is_consecutive else "isolated gap"

    # Build the error message
    parts = []

    # Header with service and gap info
    parts.append(
        f"[{context.service_name}] {gap.size_days}-day {gap_type} "
        f"from {gap.start_day} to {gap.end_day} ({size_class} severity)"
    )

    # Deployment interval reference
    parts.append(
        f"  Deployment interval reference: Expected deployments on days 1-{context.expected_days} "
        f"of analysis period ({context.analysis_period_start or 'N/A'} to {context.analysis_period_end or 'N/A'})"
    )

    # Expected coverage pattern
    parts.append(
        f"  Expected coverage pattern: Continuous deployment history across {context.expected_days}-day period "
        f"with {context.coverage_threshold}% minimum coverage threshold"
    )

    # Specific remediation guidance
    guidance = _generate_specific_remediation(gap, context)
    parts.append(f"  Action: {guidance}")

    return "\n".join(parts)


def format_gap_errors_batch(
    gaps: List[GapPeriod],
    context: GapContext,
    max_errors: int = 10
) -> List[str]:
    """
    Format multiple gap errors into a list of actionable messages.

    Args:
        gaps: List of gap periods to format
        context: Context information
        max_errors: Maximum number of errors to return (default: 10)

    Returns:
        List of formatted error messages
    """
    if not gaps:
        return []

    # Sort gaps by size (largest first) and severity
    sorted_gaps = sorted(gaps, key=lambda g: (g.size_days, g.start_day), reverse=True)

    # Format top N gaps
    formatted_errors = []
    for gap in sorted_gaps[:max_errors]:
        formatted_errors.append(format_gap_error(gap, context))

    # Add summary if there are more gaps than shown
    if len(sorted_gaps) > max_errors:
        formatted_errors.append(
            f"[{context.service_name}] ... and {len(sorted_gaps) - max_errors} additional gap(s) "
            f"(not shown for brevity)"
        )

    return formatted_errors


def generate_actionable_guidance(
    gaps: List[GapPeriod],
    context: GapContext
) -> List[str]:
    """
    Generate comprehensive actionable guidance for fixing gaps.

    This analyzes all gaps and provides prioritized, specific guidance
    for resolving coverage issues.

    Args:
        gaps: List of gap periods
        context: Context information

    Returns:
        List of actionable guidance messages
    """
    if not gaps:
        return []

    guidance = []

    # Categorize gaps
    consecutive_gaps = [g for g in gaps if g.is_consecutive]
    isolated_gaps = [g for g in gaps if not g.is_consecutive]

    # Priority 1: Critical gaps (>14 days)
    critical_gaps = [g for g in gaps if g.size_days > 14]
    if critical_gaps:
        max_gap = max(critical_gaps, key=lambda g: g.size_days)
        guidance.append(
            f"CRITICAL: {len(critical_gaps)} gap(s) exceed 14 days. "
            f"Longest gap: {max_gap.size_days} days ({max_gap.start_day} to {max_gap.end_day}). "
            f"Review infrastructure logs during this period. Check for service downtime, "
            f"data collection failures, or retention policy issues that may have deleted deployment records."
        )

    # Priority 2: High severity gaps (>7 days)
    high_gaps = [g for g in gaps if 7 < g.size_days <= 14]
    if high_gaps:
        guidance.append(
            f"HIGH: {len(high_gaps)} gap(s) exceed 7 days. "
            f"For service '{context.service_name}', verify ArgoCD sync history and "
            f"Kubernetes ReplicaSet API is capturing deployments correctly."
        )

    # Priority 3: Consecutive gap sequences
    if consecutive_gaps:
        sequences = _group_consecutive_sequences(consecutive_gaps)
        for seq in sequences:
            guidance.append(
                f"Consecutive gap sequence: {len(seq)} days from {seq[0].start_day} to {seq[-1].end_day}. "
                f"This indicates extended data collection failure. Check: (1) Deployment pipeline operational, "
                f"(2) No service downtime during this period, (3) No log retention policies expired."
            )

    # Priority 4: Isolated gaps
    if isolated_gaps:
        guidance.append(
            f"Isolated gaps: {len(isolated_gaps)} day(s) missing. "
            f"May indicate intermittent data collection issues or skipped deployments. "
            f"Review deployment logs for each missing date to identify root cause."
        )

    # Priority 5: General deployment interval guidance
    if context.last_deployment_date:
        guidance.append(
            f"Deployment interval context: Last deployment recorded on {context.last_deployment_date}. "
            f"Ensure deployments occur at least once every 24 hours to maintain {context.coverage_threshold}% coverage threshold."
        )

    # Priority 6: Specific remediation steps
    guidance.extend(_generate_remediation_steps(gaps, context))

    return guidance


def format_validation_summary(
    gaps: List[GapPeriod],
    coverage_percentage: float,
    context: GapContext
) -> str:
    """
    Format a comprehensive validation summary with actionable guidance.

    This formats the complete validation result consistently with schema
    validation errors, providing operators with clear next steps.

    Args:
        gaps: List of gap periods
        coverage_percentage: Actual coverage percentage
        context: Context information

    Returns:
        Formatted validation summary
    """
    lines = []

    # Header (consistent with schema validation errors)
    lines.append(f"{'='*70}")
    lines.append(f"❌ Coverage Validation Failed: {context.service_name}")
    lines.append(f"{'='*70}")

    # Coverage summary
    lines.append(f"\n📊 Coverage Metrics:")
    lines.append(f"   Service:              {context.service_name}")
    lines.append(f"   Cluster:              {context.cluster}")
    lines.append(f"   Coverage:             {coverage_percentage:.1f}% (threshold: {context.coverage_threshold}%)")
    lines.append(f"   Expected days:        {context.expected_days}")
    lines.append(f"   Actual days:          {context.expected_days - len(gaps)}")
    lines.append(f"   Gaps detected:         {len(gaps)}")

    # Deployment interval reference
    lines.append(f"\n📅 Deployment Interval Reference:")
    lines.append(f"   Analysis period:      {context.analysis_period_start or 'N/A'} to {context.analysis_period_end or 'N/A'}")
    lines.append(f"   Expected coverage:     Days 1-{context.expected_days} of analysis period")
    lines.append(f"   Pattern expectation:   Continuous deployment history, maximum 24h interval between deployments")
    if context.last_deployment_date:
        lines.append(f"   Last deployment:       {context.last_deployment_date}")

    # Gap breakdown
    if gaps:
        consecutive = [g for g in gaps if g.is_consecutive]
        isolated = [g for g in gaps if not g.is_consecutive]

        lines.append(f"\n🚫 Gap Breakdown:")
        lines.append(f"   Consecutive sequences: {len(set((g.start_day, g.end_day) for g in consecutive))}")
        lines.append(f"   Isolated gaps:         {len(isolated)}")

        size_dist = {}
        for gap in gaps:
            size = classify_gap_by_size(gap)
            size_dist[size] = size_dist.get(size, 0) + 1

        lines.append(f"   Size distribution:")
        for size in ['tiny', 'small', 'medium', 'large', 'extended']:
            if size in size_dist:
                lines.append(f"     - {size}: {size_dist[size]}")

    # Actionable guidance
    guidance = generate_actionable_guidance(gaps, context)
    if guidance:
        lines.append(f"\n💡 Actionable Guidance:")
        for i, item in enumerate(guidance, 1):
            lines.append(f"   {i}. {item}")

    # Expected coverage requirements
    lines.append(f"\n📐 Expected Coverage Requirements:")
    lines.append(f"   Deployment interval: Days 1-{context.expected_days} of analysis period")
    lines.append(f"   Minimum threshold: {context.coverage_threshold}% coverage for reliable analysis")
    lines.append(f"   Acceptable gaps: Isolated gaps ≤3 days (tiny/small)")
    lines.append(f"   Critical gaps: Consecutive gaps >7 days (large/extended)")
    lines.append(f"   Expected pattern: At least one deployment every 24 hours")

    # Footer
    lines.append(f"\n{'='*70}")

    return "\n".join(lines)


def _generate_specific_remediation(gap: GapPeriod, context: GapContext) -> str:
    """Generate specific remediation guidance for a single gap."""
    size_class = classify_gap_by_size(gap)

    # Cluster-specific guidance
    if context.cluster != "unknown":
        cluster_guidance = f" on cluster '{context.cluster}'"
    else:
        cluster_guidance = ""

    if size_class == "extended":
        return (
            f"CRITICAL: Deploy to {context.service_name}{cluster_guidance} within 24 hours to begin recovery. "
            f"Review infrastructure logs from {gap.start_day} to {gap.end_day} for root cause. "
            f"Check for extended downtime, data collection failures, or retention policy issues."
        )
    elif size_class == "large":
        return (
            f"Deploy to {context.service_name}{cluster_guidance} within 24 hours. "
            f"Investigate {gap.size_days}-day gap period for service availability issues. "
            f"Verify deployment pipeline and data collection systems were operational."
        )
    elif size_class == "medium":
        return (
            f"Deploy to {context.service_name}{cluster_guidance} within 24 hours. "
            f"Review {gap.size_days}-day gap for intermittent data collection issues."
        )
    elif gap.is_consecutive and size_class in ("small", "tiny"):
        return (
            f"Deploy to {context.service_name}{cluster_guidance} within 24 hours to address consecutive gaps. "
            f"Check for deployment pipeline interruptions."
        )
    else:
        return (
            f"Deploy to {context.service_name}{cluster_guidance} within 24 hours to fill isolated gap."
        )


def _generate_remediation_steps(gaps: List[GapPeriod], context: GapContext) -> List[str]:
    """Generate specific remediation steps for resolving gaps."""
    steps = []

    # Step 1: Immediate action
    steps.append(
        f"Immediate: Deploy to {context.service_name} on {context.cluster if context.cluster != 'unknown' else 'target cluster'} "
        f"within 24 hours to halt gap expansion."
    )

    # Step 2: Data recovery
    if any(g.size_days > 7 for g in gaps):
        steps.append(
            f"Data recovery: For gaps >7 days, check backup sources: ArgoCD sync history, "
            f"Kubernetes event logs, CI/CD deployment records. Recover missing deployment data if available."
        )

    # Step 3: Prevention
    steps.append(
        f"Prevention: Set up automated deployment monitoring to alert when >24 hours elapses "
        f"without a deployment event. Configure alerts for {context.service_name}."
    )

    # Step 4: Verification
    steps.append(
        f"Verification: After filling gaps, re-run validation to confirm coverage meets {context.coverage_threshold}% threshold. "
        f"Expected: deployments on days 1-{context.expected_days}."
    )

    return steps


def _group_consecutive_sequences(gaps: List[GapPeriod]) -> List[List[GapPeriod]]:
    """Group consecutive gaps by their sequence (start_day, end_day)."""
    sequences = {}
    for gap in gaps:
        key = (gap.start_day, gap.end_day)
        if key not in sequences:
            sequences[key] = []
        sequences[key].append(gap)

    # Return sorted by start day
    return sorted(sequences.values(), key=lambda x: x[0].start_day)


__all__ = [
    "format_gap_error",
    "format_gap_errors_batch",
    "generate_actionable_guidance",
    "format_validation_summary",
    "GapContext"
]
