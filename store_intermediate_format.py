#!/usr/bin/env python3
"""
Store raw latency data in intermediate format for downstream analysis.

This script extracts and consolidates raw latency data from both services
into a standardized intermediate format suitable for further analysis and visualization.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List


class IntermediateDataFormatter:
    """Format and store raw latency data in intermediate format."""

    def __init__(self, latency_metrics_file: Path):
        self.latency_metrics_file = latency_metrics_file
        with open(latency_metrics_file, 'r') as f:
            self.latency_data = json.load(f)

        self.intermediate_format = {
            "metadata": {},
            "time_series": {},
            "raw_metrics": {},
            "data_dictionary": {}
        }

    def create_metadata(self) -> Dict[str, Any]:
        """Create comprehensive metadata section."""
        query_metadata = self.latency_data.get("query_metadata", {})

        metadata = {
            "extraction_timestamp": datetime.now().isoformat(),
            "original_query_timestamp": query_metadata.get("query_timestamp"),
            "analysis_period": {
                "start_date": query_metadata.get("start_date"),
                "end_date": query_metadata.get("end_date"),
                "period_days": query_metadata.get("period_days")
            },
            "services_analyzed": query_metadata.get("services", []),
            "data_quality_summary": self.latency_data.get("summary", {}),
            "processing_notes": [
                "Raw latency data extracted from 30-day query results",
                "All duration values are in seconds unless otherwise specified",
                "Percentile calculations use inclusive quantile method",
                "Coverage gaps identified and documented"
            ]
        }

        self.intermediate_format["metadata"] = metadata
        return metadata

    def create_time_series_data(self) -> Dict[str, Any]:
        """Create time-series data format for temporal analysis."""
        time_series = {}

        for service_name in ["pbx-web", "whisper-stt"]:
            service_data = self.latency_data.get("services", {}).get(service_name, {})
            coverage_analysis = service_data.get("coverage_analysis", {})
            raw_data = service_data.get("raw_data", {})

            service_time_series = {
                "daily_distribution": {},
                "deployment_timeline": [],
                "workflow_executions": []
            }

            # Extract daily distribution from coverage analysis
            for data_type, coverage_info in coverage_analysis.items():
                daily_dist = coverage_info.get("daily_distribution", {})
                if daily_dist:
                    service_time_series["daily_distribution"][data_type] = daily_dist

            # Extract deployment timeline
            if "deployment_samples" in raw_data:
                for sample in raw_data["deployment_samples"]:
                    service_time_series["deployment_timeline"].append({
                        "timestamp": sample.get("timestamp"),
                        "revision": sample.get("revision"),
                        "replicaset": sample.get("replicaset"),
                        "status": sample.get("status")
                    })

            # Extract workflow executions
            if "workflow_samples" in raw_data:
                for sample in raw_data["workflow_samples"]:
                    service_time_series["workflow_executions"].append({
                        "workflow_name": sample.get("workflow"),
                        "started_at": sample.get("started_at"),
                        "finished_at": sample.get("finished_at"),
                        "duration_seconds": sample.get("duration_seconds"),
                        "status": sample.get("status")
                    })

            time_series[service_name] = service_time_series

        self.intermediate_format["time_series"] = time_series
        return time_series

    def create_raw_metrics_data(self) -> Dict[str, Any]:
        """Create raw metrics section with all numeric data."""
        raw_metrics = {}

        for service_name in ["pbx-web", "whisper-stt"]:
            service_data = self.latency_data.get("services", {}).get(service_name, {})
            latency_metrics = service_data.get("latency_metrics", {})
            raw_data = service_data.get("raw_data", {})

            service_metrics = {
                "workflow_latency": {},
                "deployment_intervals": {},
                "pod_health": {}
            }

            # Extract workflow latency metrics
            if "workflow_percentiles" in latency_metrics:
                wf_metrics = latency_metrics["workflow_percentiles"]
                service_metrics["workflow_latency"] = {
                    "percentiles": {
                        "p50_seconds": wf_metrics.get("p50_seconds"),
                        "p75_seconds": wf_metrics.get("p75_seconds"),
                        "p90_seconds": wf_metrics.get("p90_seconds"),
                        "p95_seconds": wf_metrics.get("p95_seconds"),
                        "p99_seconds": wf_metrics.get("p99_seconds")
                    },
                    "statistics": {
                        "count": wf_metrics.get("count"),
                        "mean_seconds": wf_metrics.get("mean_seconds"),
                        "median_seconds": wf_metrics.get("median_seconds"),
                        "stddev_seconds": wf_metrics.get("stddev_seconds"),
                        "min_seconds": wf_metrics.get("min_seconds"),
                        "max_seconds": wf_metrics.get("max_seconds")
                    },
                    "raw_durations": raw_data.get("workflow_durations", [])
                }

            # Extract deployment interval metrics
            if "deployment_intervals" in latency_metrics:
                di_metrics = latency_metrics["deployment_intervals"]
                service_metrics["deployment_intervals"] = {
                    "statistics": {
                        "count": di_metrics.get("count"),
                        "mean_seconds": di_metrics.get("mean_seconds"),
                        "median_seconds": di_metrics.get("median_seconds"),
                        "stddev_seconds": di_metrics.get("stddev_seconds"),
                        "min_seconds": di_metrics.get("min_seconds"),
                        "max_seconds": di_metrics.get("max_seconds")
                    },
                    "raw_intervals_seconds": raw_data.get("deployment_intervals_seconds", [])
                }

            # Extract deployment frequency metrics (whisper-stt)
            if "deployment_frequency" in latency_metrics:
                df_metrics = latency_metrics["deployment_frequency"]
                service_metrics["deployment_intervals"]["frequency"] = {
                    "total_deployments": df_metrics.get("total_deployments"),
                    "deployment_count_30days": df_metrics.get("deployment_count_30days")
                }
                if "intervals_hours" in df_metrics:
                    service_metrics["deployment_intervals"]["frequency"]["intervals_hours"] = {
                        "count": df_metrics["intervals_hours"].get("count"),
                        "mean_hours": df_metrics["intervals_hours"].get("mean_hours"),
                        "median_hours": df_metrics["intervals_hours"].get("median_hours"),
                        "min_hours": df_metrics["intervals_hours"].get("min_hours"),
                        "max_hours": df_metrics["intervals_hours"].get("max_hours")
                    }
                    service_metrics["deployment_intervals"]["raw_intervals_hours"] = raw_data.get("deployment_intervals_hours", [])

            # Extract pod health metrics
            if "pod_health" in latency_metrics:
                ph_metrics = latency_metrics["pod_health"]
                service_metrics["pod_health"] = {
                    "pods_analyzed": ph_metrics.get("pods_analyzed"),
                    "restart_count": ph_metrics.get("restart_count"),
                    "startup_events": ph_metrics.get("startup_events"),
                    "error_count": ph_metrics.get("error_count")
                }

            raw_metrics[service_name] = service_metrics

        self.intermediate_format["raw_metrics"] = raw_metrics
        return raw_metrics

    def create_data_dictionary(self) -> Dict[str, Any]:
        """Create comprehensive data dictionary for downstream consumers."""
        data_dict = {
            "field_descriptions": {
                "workflow_latency.percentiles.p50_seconds": "50th percentile of workflow execution duration (median)",
                "workflow_latency.percentiles.p95_seconds": "95th percentile of workflow execution duration",
                "workflow_latency.percentiles.p99_seconds": "99th percentile of workflow execution duration",
                "workflow_latency.statistics.mean_seconds": "Average workflow execution duration",
                "workflow_latency.statistics.stddev_seconds": "Standard deviation of workflow durations",
                "deployment_intervals.statistics.mean_seconds": "Average time between deployments in seconds",
                "deployment_intervals.frequency.mean_hours": "Average time between deployments in hours",
                "pod_health.restart_count": "Number of pod restart events detected",
                "coverage_percentage": "Percentage of days with data during analysis period",
                "gap_count": "Number of days without data in analysis period"
            },
            "units": {
                "time": "seconds (unless otherwise specified)",
                "count": "integer",
                "percentage": "percent",
                "duration": "seconds"
            },
            "data_sources": {
                "pbx-web": [
                    "workflow_executions - Argo workflow history",
                    "deployment_intervals - Kubernetes deployment events"
                ],
                "whisper-stt": [
                    "deployment_events - Kubernetes deployment history",
                    "pod_health - Pod log analysis"
                ]
            },
            "limitations": [
                "Limited coverage: pbx-web workflow data only available for 1 out of 31 days",
                "Limited coverage: whisper-stt deployment data only available for 2 out of 31 days",
                "Results should be interpreted as preliminary due to sparse data coverage",
                "Workflow data may be affected by Argo retention policies",
                "Deployment intervals may not represent typical patterns due to low sample size"
            ],
            "quality_notes": {
                "pbx-web": {
                    "workflow_data_quality": "poor",
                    "sample_size": "9 workflow executions",
                    "coverage_period": "single day (2026-08-06)",
                    "notes": "All workflows analyzed show 'Failed' status"
                },
                "whisper-stt": {
                    "deployment_data_quality": "poor",
                    "sample_size": "4 deployment events",
                    "coverage_period": "2 days (2026-07-08, 2026-07-12)",
                    "notes": "Multiple rapid deployments on 2026-07-08 indicate potential issues"
                }
            }
        }

        self.intermediate_format["data_dictionary"] = data_dict
        return data_dict

    def format_intermediate_data(self) -> Dict[str, Any]:
        """Create complete intermediate format."""
        print(f"\n{'='*70}")
        print("CREATING INTERMEDIATE DATA FORMAT")
        print(f"{'='*70}")

        print("Creating metadata section...")
        self.create_metadata()

        print("Creating time-series data...")
        self.create_time_series_data()

        print("Creating raw metrics section...")
        self.create_raw_metrics_data()

        print("Creating data dictionary...")
        self.create_data_dictionary()

        return self.intermediate_format

    def save_intermediate_format(self, output_file: Path) -> None:
        """Save intermediate format to file."""
        with open(output_file, 'w') as f:
            json.dump(self.intermediate_format, f, indent=2, default=str)

        print(f"\n✓ Intermediate format saved to: {output_file}")

    def print_summary(self):
        """Print summary of intermediate format."""
        print(f"\n{'='*70}")
        print("INTERMEDIATE FORMAT SUMMARY")
        print(f"{'='*70}")

        metadata = self.intermediate_format.get("metadata", {})
        print(f"\nMetadata:")
        print(f"  Extraction timestamp: {metadata.get('extraction_timestamp')}")
        print(f"  Analysis period: {metadata.get('analysis_period', {}).get('period_days')} days")
        print(f"  Services: {', '.join(metadata.get('services_analyzed', []))}")

        time_series = self.intermediate_format.get("time_series", {})
        print(f"\nTime-series data:")
        for service, data in time_series.items():
            print(f"  {service}:")
            print(f"    Daily distribution types: {len(data.get('daily_distribution', {}))}")
            print(f"    Deployment events: {len(data.get('deployment_timeline', []))}")
            print(f"    Workflow executions: {len(data.get('workflow_executions', []))}")

        raw_metrics = self.intermediate_format.get("raw_metrics", {})
        print(f"\nRaw metrics:")
        for service, data in raw_metrics.items():
            print(f"  {service}:")
            for metric_type in ["workflow_latency", "deployment_intervals", "pod_health"]:
                if data.get(metric_type):
                    print(f"    ✓ {metric_type}")


def main():
    """Main execution."""
    print("="*70)
    print("STORE RAW LATENCY DATA IN INTERMEDIATE FORMAT")
    print("="*70)

    latency_metrics_file = Path("/home/coding/aide-de-camp/data/latency_metrics_30d_20260806_212617.json")

    formatter = IntermediateDataFormatter(latency_metrics_file)
    intermediate_data = formatter.format_intermediate_data()

    # Save intermediate format
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path("/home/coding/aide-de-camp/data") / f"latency_intermediate_format_{timestamp}.json"
    formatter.save_intermediate_format(output_file)

    # Print summary
    formatter.print_summary()

    print(f"\n{'='*70}")
    print("INTERMEDIATE FORMAT CREATION COMPLETE")
    print(f"{'='*70}")
    print(f"Output file: {output_file}")
    print(f"Data sections: {len(intermediate_data)}")

    return intermediate_data


if __name__ == "__main__":
    main()