#!/usr/bin/env python3
"""
Analyze temporal alignment between resource metrics and deployment events.

This script:
1. Loads deployment events for both services
2. Checks temporal coverage of resource metrics
3. Identifies gaps and alignment issues
4. Documents coverage patterns
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

class TemporalAlignmentAnalyzer:
    """Analyze temporal alignment between metrics and deployment events."""

    def __init__(self):
        self.collection_date = datetime.now()
        self.days_period = 30
        self.start_date = self.collection_date - timedelta(days=self.days_period)

    def load_deployment_data(self, service: str) -> Dict[str, Any]:
        """Load deployment events for temporal analysis."""
        deployment_files = {
            "pbx-web": "/home/coding/aide-de-camp/data/pbx-web-deployment.json",
            "whisper-stt": "/home/coding/aide-de-camp/data/whisper-stt-deployment.json"
        }

        deployment_file = deployment_files.get(service)
        if not deployment_file:
            return {"error": "Unknown service"}

        try:
            with open(deployment_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"error": f"Deployment file not found: {deployment_file}"}
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON in deployment file: {deployment_file}"}

    def parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse various timestamp formats."""
        if not timestamp_str:
            return None

        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d"
        ]

        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue

        return None

    def analyze_deployment_coverage(self, service: str) -> Dict[str, Any]:
        """Analyze deployment event coverage over the 30-day period."""
        deployment_data = self.load_deployment_data(service)

        if "error" in deployment_data:
            return deployment_data

        analysis = {
            "service": service,
            "total_deployments": 0,
            "deployments_in_window": [],
            "deployment_frequency_days": 0.0,
            "time_coverage": {
                "first_deployment": None,
                "last_deployment": None,
                "coverage_days": 0
            },
            "coverage_status": "no_data"
        }

        items = deployment_data.get("items", [])
        analysis["total_deployments"] = len(items)

        for item in items:
            timestamp_str = item.get("metadata", {}).get("creationTimestamp", "")
            timestamp = self.parse_timestamp(timestamp_str)

            if timestamp and self.start_date <= timestamp <= self.collection_date:
                analysis["deployments_in_window"].append({
                    "timestamp": timestamp_str,
                    "name": item.get("metadata", {}).get("name", ""),
                    "namespace": item.get("metadata", {}).get("namespace", ""),
                    "generation": item.get("metadata", {}).get("generation", 0)
                })

                # Track time coverage
                if not analysis["time_coverage"]["first_deployment"]:
                    analysis["time_coverage"]["first_deployment"] = timestamp_str
                analysis["time_coverage"]["last_deployment"] = timestamp_str

        # Calculate coverage
        if analysis["deployments_in_window"]:
            first = self.parse_timestamp(analysis["time_coverage"]["first_deployment"])
            last = self.parse_timestamp(analysis["time_coverage"]["last_deployment"])

            if first and last:
                coverage_days = (last - first).days
                analysis["time_coverage"]["coverage_days"] = coverage_days
                analysis["coverage_status"] = "partial" if coverage_days < self.days_period else "full"

            # Calculate deployment frequency
            deployments_count = len(analysis["deployments_in_window"])
            if deployments_count > 1:
                time_span = max(1, (self.collection_date - self.start_date).days)
                analysis["deployment_frequency_days"] = time_span / deployments_count

        return analysis

    def identify_temporal_gaps(self) -> List[Dict[str, Any]]:
        """Identify temporal gaps in metrics coverage."""
        gaps = []

        # Resource metrics gap
        resource_gap = {
            "type": "resource_metrics_historical",
            "service": "both",
            "period": f"{self.start_date.date()} to {self.collection_date.date()}",
            "issue": "Historical resource usage metrics (CPU, memory, network) not available",
            "cause": "Prometheus integration not accessible",
            "impact": "Cannot analyze resource trends over time",
            "available_alternatives": "Current resource usage snapshot available",
            "severity": "high"
        }
        gaps.append(resource_gap)

        # Deployment data gaps
        for service in ["pbx-web", "whisper-stt"]:
            deployment_analysis = self.analyze_deployment_coverage(service)

            if deployment_analysis.get("coverage_status") == "no_data":
                gap = {
                    "type": "deployment_events",
                    "service": service,
                    "period": f"{self.start_date.date()} to {self.collection_date.date()}",
                    "issue": f"No deployment events found for {service}",
                    "cause": "Deployment data not available or parse error",
                    "impact": "Cannot correlate resource usage with deployments",
                    "available_alternatives": "Manual deployment tracking may be needed",
                    "severity": "medium"
                }
                gaps.append(gap)

            elif deployment_analysis.get("coverage_status") == "partial":
                gap = {
                    "type": "deployment_events_partial",
                    "service": service,
                    "period": f"{self.start_date.date()} to {self.collection_date.date()}",
                    "issue": f"Partial deployment coverage for {service}: {deployment_analysis['time_coverage']['coverage_days']} days",
                    "cause": "Some deployments may be outside the 30-day window",
                    "impact": "Deployment-resource correlation may be incomplete",
                    "available_alternatives": "Expand time window or check deployment history",
                    "severity": "low"
                }
                gaps.append(gap)

        return gaps

    def generate_alignment_report(self) -> Dict[str, Any]:
        """Generate comprehensive temporal alignment report."""
        services = ["pbx-web", "whisper-stt"]

        alignment_report = {
            "analysis_metadata": {
                "generated_at": self.collection_date.isoformat(),
                "period_days": self.days_period,
                "time_window_start": self.start_date.isoformat(),
                "time_window_end": self.collection_date.isoformat(),
                "services_analyzed": services
            },
            "deployment_coverage": {},
            "resource_metrics_coverage": {
                "cpu_metrics": "current_only",
                "memory_metrics": "current_only",
                "disk_metrics": "pvc_info_only",
                "network_metrics": "unavailable"
            },
            "temporal_gaps": [],
            "alignment_status": "partial",
            "recommendations": []
        }

        # Analyze deployment coverage for each service
        for service in services:
            deployment_analysis = self.analyze_deployment_coverage(service)
            alignment_report["deployment_coverage"][service] = deployment_analysis

        # Identify temporal gaps
        alignment_report["temporal_gaps"] = self.identify_temporal_gaps()

        # Generate recommendations
        if any(gap["severity"] == "high" for gap in alignment_report["temporal_gaps"]):
            alignment_report["recommendations"].append({
                "priority": "high",
                "issue": "Historical resource metrics unavailable",
                "recommendation": "Enable Prometheus integration or implement metrics collection pipeline",
                "benefit": "Would enable trend analysis and capacity planning"
            })

        # Check deployment alignment
        for service in services:
            deployment_data = alignment_report["deployment_coverage"][service]
            if deployment_data.get("coverage_status") == "no_data":
                alignment_report["recommendations"].append({
                    "priority": "medium",
                    "issue": f"Deployment events missing for {service}",
                    "recommendation": "Verify deployment data collection and storage",
                    "benefit": "Would enable deployment-resource correlation"
                })

        alignment_report["alignment_status"] = "partial" if alignment_report["temporal_gaps"] else "good"

        return alignment_report

def main():
    """Main analysis function."""
    print("=" * 80)
    print("TEMPORAL ALIGNMENT ANALYSIS")
    print("Resource Metrics vs Deployment Events (30-day period)")
    print("=" * 80)
    print()

    analyzer = TemporalAlignmentAnalyzer()

    # Generate alignment report
    report = analyzer.generate_alignment_report()

    # Save report
    output_file = "/home/coding/aide-de-camp/data/temporal_alignment_report.json"
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Alignment analysis complete. Report saved to: {output_file}")
    print()

    print("TEMPORAL ALIGNMENT SUMMARY:")
    print(f"  Analysis period: {report['analysis_metadata']['time_window_start']} to {report['analysis_metadata']['time_window_end']}")
    print(f"  Alignment status: {report['alignment_status'].upper()}")
    print()

    print("DEPLOYMENT COVERAGE:")
    for service, coverage in report["deployment_coverage"].items():
        status = coverage.get("coverage_status", "unknown")
        deployments = coverage.get("deployments_in_window", [])
        print(f"  {service}: {status}")
        print(f"    - Deployments in window: {len(deployments)}")
        if coverage.get("time_coverage", {}).get("coverage_days"):
            print(f"    - Coverage days: {coverage['time_coverage']['coverage_days']}")
    print()

    print("RESOURCE METRICS COVERAGE:")
    for metric_type, status in report["resource_metrics_coverage"].items():
        print(f"  - {metric_type}: {status}")
    print()

    if report["temporal_gaps"]:
        print("TEMPORAL GAPS DETECTED:")
        for gap in report["temporal_gaps"]:
            print(f"  [{gap['severity'].upper()}] {gap['service']}: {gap['issue']}")
            print(f"    Cause: {gap['cause']}")
            print(f"    Impact: {gap['impact']}")
        print()

    if report["recommendations"]:
        print("RECOMMENDATIONS:")
        for rec in report["recommendations"]:
            print(f"  [{rec['priority'].upper()}] {rec['issue']}")
            print(f"    Recommendation: {rec['recommendation']}")
            print(f"    Benefit: {rec['benefit']}")
        print()

    print("=" * 80)
    print("KEY FINDINGS:")
    print("1. Historical resource metrics (CPU, memory, network) require Prometheus integration")
    print("2. Current resource usage snapshot available for both services")
    print("3. Deployment event coverage varies by service")
    print("4. Temporal alignment is PARTIAL due to missing historical metrics")
    print("=" * 80)

    return 0

if __name__ == "__main__":
    sys.exit(main())