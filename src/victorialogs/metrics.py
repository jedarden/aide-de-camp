"""
Latency metrics calculator for processing VictoriaLogs query results.

Provides utilities for calculating percentiles, aggregating data,
and generating latency reports from query results.
"""

import statistics
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class LatencyMetricsCalculator:
    """
    Calculate latency metrics from VictoriaLogs query results.

    Processes raw query results to calculate:
    - Percentiles (p50, p95, p99, p90)
    - Mean, median, standard deviation
    - Time series aggregations
    - Error rates combined with latency
    """

    def __init__(self):
        """Initialize metrics calculator."""
        self.reset()

    def reset(self):
        """Reset internal state."""
        self.latency_values = []
        self.timestamps = []
        self.errors = []

    def add_value(self, timestamp: str, latency: float) -> None:
        """
        Add a latency value with timestamp.

        Args:
            timestamp: ISO format timestamp
            latency: Latency value in seconds
        """
        try:
            self.latency_values.append(float(latency))
            self.timestamps.append(timestamp)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid latency value: {latency} - {e}")
            self.errors.append({
                "timestamp": timestamp,
                "value": latency,
                "error": str(e)
            })

    def calculate_percentiles(self) -> Dict[str, float]:
        """
        Calculate latency percentiles.

        Returns:
            Dictionary with p50, p75, p90, p95, p99, min, max, count
        """
        if not self.latency_values:
            return {
                "count": 0,
                "p50_seconds": 0.0,
                "p75_seconds": 0.0,
                "p90_seconds": 0.0,
                "p95_seconds": 0.0,
                "p99_seconds": 0.0,
                "min_seconds": 0.0,
                "max_seconds": 0.0
            }

        sorted_data = sorted(self.latency_values)
        n = len(sorted_data)

        try:
            quantiles = statistics.quantiles(sorted_data, n=100, method='inclusive')
            return {
                "count": n,
                "p50_seconds": round(quantiles[49], 3),
                "p75_seconds": round(quantiles[74], 3),
                "p90_seconds": round(quantiles[89], 3),
                "p95_seconds": round(quantiles[94], 3),
                "p99_seconds": round(quantiles[98], 3),
                "min_seconds": round(min(sorted_data), 3),
                "max_seconds": round(max(sorted_data), 3)
            }
        except Exception as e:
            logger.warning(f"quantiles calculation failed: {e}, using manual fallback")
            return self._manual_percentiles(sorted_data)

    def _manual_percentiles(self, sorted_data: List[float]) -> Dict[str, float]:
        """Manual percentile calculation fallback."""
        n = len(sorted_data)

        def percentile(p: float) -> float:
            index = int(n * p / 100)
            return sorted_data[min(index, n - 1)]

        return {
            "count": n,
            "p50_seconds": round(percentile(50), 3),
            "p75_seconds": round(percentile(75), 3),
            "p90_seconds": round(percentile(90), 3),
            "p95_seconds": round(percentile(95), 3),
            "p99_seconds": round(percentile(99), 3),
            "min_seconds": round(min(sorted_data), 3),
            "max_seconds": round(max(sorted_data), 3)
        }

    def calculate_stats(self) -> Dict[str, float]:
        """
        Calculate additional statistics.

        Returns:
            Dictionary with mean, median, sum, stddev
        """
        if not self.latency_values:
            return {
                "mean_seconds": 0.0,
                "median_seconds": 0.0,
                "sum_seconds": 0.0,
                "stddev_seconds": 0.0
            }

        return {
            "mean_seconds": round(statistics.mean(self.latency_values), 3),
            "median_seconds": round(statistics.median(self.latency_values), 3),
            "sum_seconds": round(sum(self.latency_values), 3),
            "stddev_seconds": round(
                statistics.stdev(self.latency_values) if len(self.latency_values) > 1 else 0.0,
                3
            )
        }

    def calculate_time_series_aggregates(
        self,
        interval: str = "1h"
    ) -> List[Dict[str, Any]]:
        """
        Calculate time-series aggregated metrics.

        Args:
            interval: Time interval for aggregation (1h, 1d, etc.)

        Returns:
            List of time-bucketed metrics
        """
        if not self.timestamps or not self.latency_values:
            return []

        # Parse timestamps and group by interval
        time_groups = defaultdict(list)

        for ts, latency in zip(self.timestamps, self.latency_values):
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))

                # Create time bucket key based on interval
                if interval == "1h":
                    bucket_key = dt.strftime("%Y-%m-%dT%H:00:00Z")
                elif interval == "1d":
                    bucket_key = dt.strftime("%Y-%m-%dT00:00:00Z")
                else:
                    bucket_key = ts  # Fallback to raw timestamp

                time_groups[bucket_key].append(latency)
            except Exception as e:
                logger.error(f"Error parsing timestamp {ts}: {e}")
                continue

        # Calculate stats for each time bucket
        aggregates = []
        for bucket, values in sorted(time_groups.items()):
            sorted_values = sorted(values)
            n = len(sorted_values)

            try:
                quantiles = statistics.quantiles(sorted_values, n=100, method='inclusive')
                aggregates.append({
                    "timestamp": bucket,
                    "count": n,
                    "p50_seconds": round(quantiles[49], 3),
                    "p95_seconds": round(quantiles[94], 3),
                    "p99_seconds": round(quantiles[98], 3),
                    "min_seconds": round(min(sorted_values), 3),
                    "max_seconds": round(max(sorted_values), 3)
                })
            except Exception as e:
                logger.warning(f"Error calculating aggregates for bucket {bucket}: {e}")
                continue

        return aggregates

    def get_comprehensive_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive latency report.

        Returns:
            Complete report with percentiles, stats, time series, and quality metrics
        """
        percentiles = self.calculate_percentiles()
        stats = self.calculate_stats()
        time_series = self.calculate_time_series_aggregates()

        return {
            "percentile_metrics": percentiles,
            "additional_stats": stats,
            "time_series": {
                "interval": "1h",
                "data_points": len(time_series),
                "aggregates": time_series
            },
            "data_quality": {
                "total_records": len(self.latency_values),
                "error_count": len(self.errors),
                "success_rate": round(
                    (1 - len(self.errors) / max(len(self.latency_values), 1)) * 100,
                    2
                ) if self.latency_values else 0.0
            },
            "generated_at": datetime.now().isoformat()
        }


def process_query_result(query_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process VictoriaLogs query result into metrics report.

    Args:
        query_result: Raw query result from VictoriaLogs client

    Returns:
        Processed metrics report
    """
    if not query_result.get("success"):
        return {
            "success": False,
            "error": query_result.get("error", "Unknown error"),
            "query": query_result.get("query", "unknown")
        }

    calculator = LatencyMetricsCalculator()

    # Extract data from query result
    result = query_result.get("result", {})

    # Handle different response formats
    if "data" in result:
        data = result["data"]
        if isinstance(data, list):
            # Process list of log entries
            for entry in data:
                if isinstance(entry, dict):
                    timestamp = entry.get("_time") or entry.get("timestamp")
                    latency = entry.get("duration_seconds") or entry.get("latency")

                    if timestamp and latency is not None:
                        calculator.add_value(timestamp, latency)

    return calculator.get_comprehensive_report()


def combine_multiple_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Combine results from multiple queries into a unified report.

    Args:
        results: List of query results from different services/time ranges

    Returns:
        Combined report with comparison metrics
    """
    combined = {
        "services": {},
        "summary": {
            "total_queries": len(results),
            "successful_queries": sum(1 for r in results if r.get("success", False)),
            "timestamp": datetime.now().isoformat()
        }
    }

    for i, result in enumerate(results):
        query_name = result.get("query", f"query_{i}")
        metrics = process_query_result(result)

        combined["services"][query_name] = {
            "metrics": metrics,
            "query_details": {
                "success": result.get("success", False),
                "error": result.get("error")
            }
        }

    return combined


def calculate_sla_compliance(
    metrics: Dict[str, Any],
    sla_p95_threshold: float = 2.0,
    sla_p99_threshold: float = 5.0
) -> Dict[str, Any]:
    """
    Calculate SLA compliance from latency metrics.

    Args:
        metrics: Metrics report from LatencyMetricsCalculator
        sla_p95_threshold: P95 SLA threshold in seconds
        sla_p99_threshold: P99 SLA threshold in seconds

    Returns:
        SLA compliance report
    """
    percentile_metrics = metrics.get("percentile_metrics", {})
    p95 = percentile_metrics.get("p95_seconds", 0)
    p99 = percentile_metrics.get("p99_seconds", 0)

    return {
        "p95_compliance": {
            "threshold": sla_p95_threshold,
            "actual": p95,
            "compliant": p95 <= sla_p95_threshold,
            "excess": max(0, p95 - sla_p95_threshold)
        },
        "p99_compliance": {
            "threshold": sla_p99_threshold,
            "actual": p99,
            "compliant": p99 <= sla_p99_threshold,
            "excess": max(0, p99 - sla_p99_threshold)
        },
        "overall_compliant": p95 <= sla_p95_threshold and p99 <= sla_p99_threshold
    }
