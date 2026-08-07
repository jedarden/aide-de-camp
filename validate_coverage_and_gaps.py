#!/usr/bin/env python3
"""
Validate coverage and detect temporal gaps in 30-day latency metrics.

This script performs detailed gap analysis on the latency metrics data,
identifying missing periods, partial data issues, and providing recommendations.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict


class CoverageValidator:
    """Validate and analyze coverage gaps in latency metrics."""

    def __init__(self, latency_metrics_file: Path):
        self.latency_metrics_file = latency_metrics_file
        with open(latency_metrics_file, 'r') as f:
            self.data = json.load(f)

        self.metadata = self.data.get("query_metadata", {})
        self.start_date = datetime.fromisoformat(self.metadata["start_date"].replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(self.metadata["end_date"].replace('Z', '+00:00'))

        self.analysis = {
            "validation_timestamp": datetime.now().isoformat(),
            "gap_analysis": {},
            "data_quality_issues": [],
            "recommendations": []
        }

    def analyze_service_gaps(self, service_name: str) -> Dict[str, Any]:
        """Analyze coverage gaps for a specific service."""
        print(f"\n{'='*60}")
        print(f"Analyzing gaps for {service_name}...")
        print(f"{'='*60}")

        service_data = self.data.get("services", {}).get(service_name, {})
        coverage_analysis = service_data.get("coverage_analysis", {})

        service_gap_analysis = {
            "service": service_name,
            "data_sources": service_data.get("data_sources", []),
            "coverage_summary": {},
            "gap_details": {},
            "issues_found": []
        }

        for data_type, coverage_info in coverage_analysis.items():
            print(f"\n  Analyzing {data_type}...")

            expected_days = coverage_info.get("expected_days", 0)
            actual_days = coverage_info.get("days_with_data", 0)
            coverage_pct = coverage_info.get("coverage_percentage", 0)
            gaps = coverage_info.get("gaps", [])
            daily_distribution = coverage_info.get("daily_distribution", {})

            # Gap classification
            gap_details = self._classify_gaps(gaps, daily_distribution, self.start_date, self.end_date)

            # Issues detection
            issues = self._detect_issues(data_type, coverage_info, service_data)

            service_gap_analysis["coverage_summary"][data_type] = {
                "expected_days": expected_days,
                "actual_days": actual_days,
                "coverage_percentage": coverage_pct,
                "gap_count": len(gaps),
                "data_quality": self._assess_data_quality(coverage_pct, len(gaps), issues)
            }

            service_gap_analysis["gap_details"][data_type] = gap_details
            service_gap_analysis["issues_found"].extend(issues)

            print(f"    Coverage: {actual_days}/{expected_days} days ({coverage_pct}%)")
            print(f"    Gaps: {len(gaps)}")
            print(f"    Quality: {service_gap_analysis['coverage_summary'][data_type]['data_quality']}")

        return service_gap_analysis

    def _classify_gaps(self, gaps: List[Dict], daily_distribution: Dict,
                      start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Classify gaps by type and severity."""
        gap_classification = {
            "total_gaps": len(gaps),
            "consecutive_gaps": [],
            "isolated_gaps": [],
            "longest_gap": 0,
            "gap_patterns": []
        }

        if not gaps:
            return gap_classification

        # Sort gaps by date
        sorted_gaps = sorted(gaps, key=lambda x: x["date"])

        # Find consecutive gaps
        consecutive_sequence = []
        for i, gap in enumerate(sorted_gaps):
            gap_date = datetime.fromisoformat(gap["date"]).date()

            if i == 0:
                consecutive_sequence.append(gap_date)
            else:
                prev_date = consecutive_sequence[-1]
                if (gap_date - prev_date).days == 1:
                    consecutive_sequence.append(gap_date)
                else:
                    if len(consecutive_sequence) > 1:
                        gap_classification["consecutive_gaps"].append({
                            "start_date": consecutive_sequence[0].isoformat(),
                            "end_date": consecutive_sequence[-1].isoformat(),
                            "duration_days": len(consecutive_sequence)
                        })
                    consecutive_sequence = [gap_date]

        # Check final sequence
        if len(consecutive_sequence) > 1:
            gap_classification["consecutive_gaps"].append({
                "start_date": consecutive_sequence[0].isoformat(),
                "end_date": consecutive_sequence[-1].isoformat(),
                "duration_days": len(consecutive_sequence)
            })

        # Find isolated gaps
        for gap in sorted_gaps:
            gap_date = datetime.fromisoformat(gap["date"]).date()
            is_isolated = True

            for consecutive_seq in gap_classification["consecutive_gaps"]:
                seq_start = datetime.fromisoformat(consecutive_seq["start_date"]).date()
                seq_end = datetime.fromisoformat(consecutive_seq["end_date"]).date()
                if seq_start <= gap_date <= seq_end:
                    is_isolated = False
                    break

            if is_isolated:
                gap_classification["isolated_gaps"].append(gap["date"])

        # Calculate longest gap
        if gap_classification["consecutive_gaps"]:
            longest = max(gap_classification["consecutive_gaps"],
                         key=lambda x: x["duration_days"])
            gap_classification["longest_gap"] = longest["duration_days"]

        return gap_classification

    def _detect_issues(self, data_type: str, coverage_info: Dict,
                      service_data: Dict) -> List[str]:
        """Detect data quality issues."""
        issues = []

        coverage_pct = coverage_info.get("coverage_percentage", 0)
        gap_count = len(coverage_info.get("gaps", []))
        days_with_data = coverage_info.get("days_with_data", 0)

        # Critical issues
        if coverage_pct < 10:
            issues.append(f"CRITICAL: Very low coverage ({coverage_pct}%) for {data_type}")

        if gap_count > 20:
            issues.append(f"CRITICAL: Extensive gaps ({gap_count} missing days) in {data_type}")

        # Warning issues
        if coverage_pct < 50 and coverage_pct >= 10:
            issues.append(f"WARNING: Low coverage ({coverage_pct}%) for {data_type}")

        if gap_count > 10 and gap_count <= 20:
            issues.append(f"WARNING: Multiple gaps ({gap_count} missing days) in {data_type}")

        # Data consistency issues
        if days_with_data == 0:
            issues.append(f"CRITICAL: No data available for {data_type}")

        # Check for data anomalies
        if "workflow_data" in data_type:
            workflows = service_data.get("raw_data", {}).get("workflow_durations", [])
            if not workflows:
                issues.append("WARNING: No workflow duration data available")
            elif len(workflows) < 5:
                issues.append(f"WARNING: Very small sample size ({len(workflows)} workflows)")

        return issues

    def _assess_data_quality(self, coverage_pct: float, gap_count: int,
                            issues: List[str]) -> str:
        """Assess overall data quality."""
        critical_issues = [i for i in issues if i.startswith("CRITICAL")]
        warning_issues = [i for i in issues if i.startswith("WARNING")]

        if critical_issues:
            return "poor"
        elif warning_issues:
            return "fair"
        elif coverage_pct > 75 and gap_count < 5:
            return "excellent"
        elif coverage_pct > 50 and gap_count < 10:
            return "good"
        else:
            return "fair"

    def generate_recommendations(self) -> List[str]:
        """Generate recommendations based on gap analysis."""
        recommendations = []

        print(f"\n{'='*60}")
        print("Generating recommendations...")
        print(f"{'='*60}")

        for service_name in ["pbx-web", "whisper-stt"]:
            service_data = self.data.get("services", {}).get(service_name, {})
            coverage_analysis = service_data.get("coverage_analysis", {})

            for data_type, coverage_info in coverage_analysis.items():
                coverage_pct = coverage_info.get("coverage_percentage", 0)
                gap_count = len(coverage_info.get("gaps", []))
                days_with_data = coverage_info.get("days_with_data", 0)

                # Coverage-based recommendations
                if coverage_pct < 10:
                    recommendations.append(
                        f"{service_name} {data_type}: CRITICAL - Less than 10% coverage. "
                        f"Consider extending data collection period or investigating missing data."
                    )

                if gap_count > 20:
                    recommendations.append(
                        f"{service_name} {data_type}: {gap_count} gaps detected. "
                        f"Review data collection pipeline and retention policies."
                    )

                # Service-specific recommendations
                if service_name == "pbx-web":
                    if "workflow" in data_type and days_with_data < 2:
                        recommendations.append(
                            f"pbx-web workflow data: Only {days_with_data} day(s) with data. "
                            f"Check Argo Workflow retention policies and query filters."
                        )

                if service_name == "whisper-stt":
                    if "deployment" in data_type and days_with_data < 5:
                        recommendations.append(
                            f"whisper-stt deployment data: Limited deployment history ({days_with_data} days). "
                            f"This may be normal if deployments are infrequent, but verify against actual deployment activity."
                        )

        # General recommendations
        all_coverage = [
            coverage_info.get("coverage_percentage", 0)
            for service_data in self.data.get("services", {}).values()
            for coverage_info in service_data.get("coverage_analysis", {}).values()
        ]

        if all_coverage and max(all_coverage) < 20:
            recommendations.append(
                "GENERAL: Overall data coverage is below 20%. Consider extending the "
                "analysis window or investigating data collection issues."
            )

        # Add positive findings
        good_coverage_services = [
            service for service in ["pbx-web", "whisper-stt"]
            if any(
                coverage_info.get("coverage_percentage", 0) > 50
                for coverage_info in self.data.get("services", {}).get(service, {}).get("coverage_analysis", {}).values()
            )
        ]

        if not good_coverage_services:
            recommendations.append(
                "NOTE: Neither service achieves 50% coverage. Results should be interpreted "
                "as preliminary and may not represent typical performance patterns."
            )

        return recommendations

    def run_validation(self) -> Dict[str, Any]:
        """Run complete validation analysis."""
        print(f"\n{'='*70}")
        print("COVERAGE VALIDATION AND GAP ANALYSIS")
        print(f"{'='*70}")
        print(f"Period: {self.start_date.date()} to {self.end_date.date()}")

        # Analyze gaps for each service
        for service_name in ["pbx-web", "whisper-stt"]:
            service_analysis = self.analyze_service_gaps(service_name)
            self.analysis["gap_analysis"][service_name] = service_analysis

        # Generate recommendations
        recommendations = self.generate_recommendations()
        self.analysis["recommendations"] = recommendations

        # Collect all issues
        all_issues = []
        for service_data in self.analysis["gap_analysis"].values():
            all_issues.extend(service_data.get("issues_found", []))
        self.analysis["data_quality_issues"] = all_issues

        return self.analysis

    def print_summary(self):
        """Print validation summary."""
        print(f"\n{'='*70}")
        print("COVERAGE VALIDATION SUMMARY")
        print(f"{'='*70}")

        for service_name, service_analysis in self.analysis["gap_analysis"].items():
            print(f"\n{service_name.upper()}:")
            print(f"  Data Sources: {', '.join(service_analysis['data_sources'])}")

            for data_type, summary in service_analysis["coverage_summary"].items():
                print(f"  {data_type}:")
                print(f"    Coverage: {summary['coverage_percentage']}% ({summary['actual_days']}/{summary['expected_days']} days)")
                print(f"    Gaps: {summary['gap_count']}")
                print(f"    Quality: {summary['data_quality']}")

            if service_analysis["issues_found"]:
                print(f"  Issues:")
                for issue in service_analysis["issues_found"]:
                    print(f"    - {issue}")
            else:
                print(f"  Issues: None detected")

        print(f"\n{'='*70}")
        print("RECOMMENDATIONS")
        print(f"{'='*70}")

        for i, recommendation in enumerate(self.analysis["recommendations"], 1):
            print(f"{i}. {recommendation}")

        print(f"\n{'='*70}")
        print("VALIDATION COMPLETE")
        print(f"{'='*70}")

    def save_results(self, output_file: Path) -> None:
        """Save validation results."""
        with open(output_file, 'w') as f:
            json.dump(self.analysis, f, indent=2, default=str)

        print(f"Validation results saved to: {output_file}")


def main():
    """Main execution."""
    latency_metrics_file = Path("/home/coding/aide-de-camp/data/latency_metrics_30d_20260806_212617.json")

    validator = CoverageValidator(latency_metrics_file)
    results = validator.run_validation()
    validator.print_summary()

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path("/home/coding/aide-de-camp/data") / f"coverage_validation_{timestamp}.json"
    validator.save_results(output_file)

    return results


if __name__ == "__main__":
    main()