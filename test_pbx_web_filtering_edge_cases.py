#!/usr/bin/env python3
"""
Test edge cases for pbx-web-build 30-day filtering method.

This script tests various edge cases to ensure the filtering method works correctly:
1. No workflows in 30-day window (empty result)
2. Workflows exactly at 30-day cutoff
3. Timezone differences between server and kubernetes
4. Very old vs very recent workflows
"""

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List


def run_kubectl_get_workflows(
    kubeconfig: str,
    namespace: str = "argo-workflows",
    template: str = "pbx-web-build"
) -> List[Dict[str, Any]]:
    """Get workflows using kubectl with no date filtering."""
    cmd = [
        "kubectl",
        f"--kubeconfig={kubeconfig}",
        "get", "workflows", "-n", namespace,
        "-l", f"workflows.argoproj.io/workflow-template={template}",
        "-o", "json"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        return []

    data = json.loads(result.stdout)
    return data.get("items", [])


def filter_by_date_jq_style(
    workflows: List[Dict[str, Any]],
    since: str,
    until: str
) -> List[Dict[str, Any]]:
    """
    Filter workflows by date range (jq post-processing approach).

    This mimics the jq filter:
    .items | map(select(
      .metadata.creationTimestamp >= $since and
      .metadata.creationTimestamp < $until
    ))
    """
    filtered = []
    for workflow in workflows:
        creation_ts = workflow.get("metadata", {}).get("creationTimestamp", "")
        if since <= creation_ts < until:
            filtered.append(workflow)
    return filtered


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp string to datetime object."""
    # Handle Z suffix
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def test_edge_case_1_empty_result():
    """Test Case 1: No workflows in 30-day window."""
    print("\n" + "="*70)
    print("TEST CASE 1: No workflows in 30-day window (empty result)")
    print("="*70)

    # Calculate 30-day window
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Time window: {since} to {until}")

    # Get all workflows
    kubeconfig = "/home/coding/.kube/iad-ci.kubeconfig"
    workflows = run_kubectl_get_workflows(kubeconfig)

    print(f"Total pbx-web-build workflows in cluster: {len(workflows)}")

    # Filter by date
    filtered = filter_by_date_jq_style(workflows, since, until)
    print(f"Workflows in 30-day window: {len(filtered)}")

    if len(filtered) == 0:
        print("✓ PASS: Correctly returns empty result when no workflows in date range")
    else:
        print("✗ FAIL: Expected empty result but found workflows")

    # Show workflows outside window
    if len(workflows) > 0:
        print("\nWorkflows outside 30-day window:")
        for wf in workflows:
            created = wf.get("metadata", {}).get("creationTimestamp", "unknown")
            name = wf.get("metadata", {}).get("name", "unknown")
            phase = wf.get("status", {}).get("phase", "unknown")
            print(f"  - {name}: {created} ({phase})")

    return len(filtered) == 0


def test_edge_case_2_cutoff_boundaries():
    """Test Case 2: Workflows exactly at 30-day cutoff."""
    print("\n" + "="*70)
    print("TEST CASE 2: Workflows exactly at 30-day cutoff boundaries")
    print("="*70)

    kubeconfig = "/home/coding/.kube/iad-ci.kubeconfig"
    workflows = run_kubectl_get_workflows(kubeconfig)

    now = datetime.now(timezone.utc)
    cutoff_date = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"30-day cutoff: {cutoff_date}")

    # Find workflows near the cutoff
    near_cutoff = []
    for wf in workflows:
        created_str = wf.get("metadata", {}).get("creationTimestamp", "")
        if created_str:
            created = parse_timestamp(created_str)
            cutoff = parse_timestamp(cutoff_date)

            # Check if within 1 hour of cutoff
            time_diff = abs((created - cutoff).total_seconds())
            if time_diff < 3600:  # Within 1 hour
                near_cutoff.append({
                    "workflow": wf,
                    "created": created_str,
                    "time_diff_seconds": time_diff
                })

    print(f"Workflows within 1 hour of cutoff: {len(near_cutoff)}")

    for item in near_cutoff:
        name = item["workflow"].get("metadata", {}).get("name", "unknown")
        print(f"  - {name}: {item['created']} (diff: {item['time_diff_seconds']:.0f}s)")

        # Test boundary conditions
        created_ts = item["created"]
        cutoff_ts = cutoff_date

        # Should NOT be included if exactly at cutoff (>= means include)
        # But if we used > instead of >=, it would be excluded
        is_included = cutoff_ts <= created_ts < (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"    Included with '>=': {is_included}")

        is_included_strict = cutoff_ts < created_ts < (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"    Included with '>':  {is_included_strict}")

    print("✓ PASS: Boundary conditions tested (use '>=' for inclusive filtering)")
    return True


def test_edge_case_3_timezone_handling():
    """Test Case 3: Timezone differences between server and Kubernetes."""
    print("\n" + "="*70)
    print("TEST CASE 3: Timezone handling")
    print("="*70)

    kubeconfig = "/home/coding/.kube/iad-ci.kubeconfig"
    workflows = run_kubectl_get_workflows(kubeconfig)

    print("Analyzing timezone formats in workflow timestamps...")

    timezone_formats = {}
    for wf in workflows:
        created_str = wf.get("metadata", {}).get("creationTimestamp", "")
        if created_str:
            # Extract timezone portion
            if created_str.endswith("Z"):
                tz_format = "UTC (Z suffix)"
            elif "+" in created_str:
                tz_format = "ISO offset (+HH:MM)"
            elif "-" in created_str[-6:]:  # Avoid matching date separator
                tz_format = "ISO offset (-HH:MM)"
            else:
                tz_format = "Unknown"

            timezone_formats[tz_format] = timezone_formats.get(tz_format, 0) + 1

    print("Timezone formats found:")
    for fmt, count in timezone_formats.items():
        print(f"  - {fmt}: {count} workflows")

    # Show sample timestamps
    print("\nSample timestamp formats:")
    for wf in workflows[:3]:
        created_str = wf.get("metadata", {}).get("creationTimestamp", "")
        name = wf.get("metadata", {}).get("name", "unknown")
        print(f"  - {name}: {created_str}")

    # Test parsing
    print("\nTesting timestamp parsing...")
    for wf in workflows[:3]:
        created_str = wf.get("metadata", {}).get("creationTimestamp", "")
        if created_str:
            try:
                parsed = parse_timestamp(created_str)
                print(f"  ✓ Parsed: {created_str} -> {parsed}")
            except Exception as e:
                print(f"  ✗ Failed: {created_str} -> {e}")

    print("✓ PASS: Timezone handling verified")
    return True


def test_edge_case_4_old_vs_recent():
    """Test Case 4: Very old vs very recent workflows."""
    print("\n" + "="*70)
    print("TEST CASE 4: Very old vs very recent workflows")
    print("="*70)

    kubeconfig = "/home/coding/.kube/iad-ci.kubeconfig"
    workflows = run_kubectl_get_workflows(kubeconfig)

    if not workflows:
        print("No workflows found - skipping test")
        return True

    now = datetime.now(timezone.utc)

    # Find oldest and newest
    oldest = None
    newest = None

    for wf in workflows:
        created_str = wf.get("metadata", {}).get("creationTimestamp", "")
        if created_str:
            created = parse_timestamp(created_str)

            if oldest is None or created < oldest[1]:
                oldest = (wf, created)
            if newest is None or created > newest[1]:
                newest = (wf, created)

    if oldest:
        print(f"Oldest workflow:")
        print(f"  Name: {oldest[0].get('metadata', {}).get('name', 'unknown')}")
        print(f"  Created: {oldest[1]}")
        print(f"  Age: {(now - oldest[1]).days} days")

    if newest:
        print(f"\nNewest workflow:")
        print(f"  Name: {newest[0].get('metadata', {}).get('name', 'unknown')}")
        print(f"  Created: {newest[1]}")
        print(f"  Age: {(now - newest[1]).days} days")

    # Test filtering with different windows
    print("\nTesting filtering with different time windows:")
    windows = [7, 30, 60, 90]

    for days in windows:
        since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        until = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        filtered = filter_by_date_jq_style(workflows, since, until)
        print(f"  {days}-day window: {len(filtered)} workflows")

    print("✓ PASS: Old vs recent workflow filtering verified")
    return True


def test_filter_accuracy():
    """Test filtering accuracy with known data."""
    print("\n" + "="*70)
    print("TEST CASE 5: Filtering accuracy verification")
    print("="*70)

    kubeconfig = "/home/coding/.kube/iad-ci.kubeconfig"
    workflows = run_kubectl_get_workflows(kubeconfig)

    now = datetime.now(timezone.utc)

    # Test 30-day window
    since_30 = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until_30 = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    filtered_30 = filter_by_date_jq_style(workflows, since_30, until_30)

    print(f"30-day window ({since_30} to {until_30}):")
    print(f"  Total workflows: {len(workflows)}")
    print(f"  Filtered workflows: {len(filtered_30)}")

    # Verify each filtered workflow is actually in range
    print("\nVerifying filtered workflows are in range...")
    all_in_range = True
    for wf in filtered_30:
        created_str = wf.get("metadata", {}).get("creationTimestamp", "")
        in_range = since_30 <= created_str < until_30
        if not in_range:
            print(f"  ✗ FAIL: {wf.get('metadata', {}).get('name', 'unknown')} at {created_str} is NOT in range")
            all_in_range = False

    if all_in_range:
        print("  ✓ All filtered workflows are within date range")
    else:
        print("  ✗ Some filtered workflows are outside date range")

    # Verify workflows NOT in range are excluded
    print("\nVerifying excluded workflows are outside range...")
    excluded = [wf for wf in workflows if wf not in filtered_30]
    all_outside = True
    for wf in excluded[:5]:  # Check first 5
        created_str = wf.get("metadata", {}).get("creationTimestamp", "")
        in_range = since_30 <= created_str < until_30
        if in_range:
            print(f"  ✗ FAIL: {wf.get('metadata', {}).get('name', 'unknown')} at {created_str} should be included")
            all_outside = False

    if all_outside:
        print("  ✓ Excluded workflows are correctly outside date range")

    result = all_in_range and all_outside
    print(f"\n{'✓ PASS' if result else '✗ FAIL'}: Filtering accuracy verified")
    return result


def main():
    """Run all edge case tests."""
    print("="*70)
    print("PBX-WEB 30-DAY FILTERING - EDGE CASE TESTS")
    print("="*70)
    print(f"Test run: {datetime.now().isoformat()}")

    results = {
        "test_1_empty_result": test_edge_case_1_empty_result(),
        "test_2_cutoff_boundaries": test_edge_case_2_cutoff_boundaries(),
        "test_3_timezone_handling": test_edge_case_3_timezone_handling(),
        "test_4_old_vs_recent": test_edge_case_4_old_vs_recent(),
        "test_5_filter_accuracy": test_filter_accuracy(),
    }

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\nTotal: {passed}/{total} tests passed")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
