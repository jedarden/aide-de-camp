#!/usr/bin/env python3
"""
Whisper-STT Latency Aggregation with Optimized Time Steps

This script aggregates whisper-stt latency metrics over a 30-day window
using optimized time steps based on data analysis.

Configuration:
- Step size: 1 hour (optimal based on analysis)
- Buckets: 720 (for 30-day window)
- Expected records per bucket: ~480
- Total results: 720 data points

Usage:
    python scripts/aggregate_whisper_stt_latency_6h.py

Output:
    data/whisper-stt-latency-aggregated-1h.json

Optimization Note:
Step size calculated by calculate_optimal_step_size.py based on:
- Event rate analysis from actual whisper-stt logs
- Target: <1000 buckets for 30-day window
- Recommendation: 1-hour steps for high granularity with good manageability
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict


class WhisperSTTLatencyAggregator:
    """
    Aggregate whisper-stt latency metrics into time-bucketed percentiles.

    Uses optimized 1-hour time steps for 30-day window:
    - 720 total buckets
    - ~480 records per bucket (average)
    - High granularity with good manageability
    """

    def __init__(
        self,
        start_date: str = "2026-07-07T00:00:00Z",
        end_date: str = "2026-08-06T23:59:59Z",
        step_hours: int = 1
    ):
        """
        Initialize aggregator with time range and step size.

        Args:
            start_date: ISO format start timestamp
            end_date: ISO format end timestamp
            step_hours: Time step in hours (default: 1, optimal from analysis)

        Step Size Rationale:
            The 1-hour step size was chosen based on analysis in calculate_optimal_step_size.py.
            See docs/notes/whisper-stt-time-step-rationale.md for detailed explanation:
            - Formula: (30 days × 24 hours) / step_hours = total_buckets
            - 1-hour steps = 720 buckets, ~480 events/bucket
            - Balances high granularity with good manageability (<1000 buckets)
        """
        self.start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        self.step_hours = step_hours
        self.step_size_str = f"{step_hours}h"

        # Calculate total buckets
        total_seconds = (self.end_date - self.start_date).total_seconds()
        self.total_buckets = int(total_seconds / (step_hours * 3600)) + 1

        # Initialize time buckets
        self.buckets = self._initialize_buckets()

        # Statistics
        self.total_records_processed = 0
        self.records_with_latency = 0
        self.records_outside_range = 0

    def _initialize_buckets(self) -> List[Dict[str, Any]]:
        """Initialize empty time buckets covering the full date range."""
        buckets = []
        current = self.start_date

        while current <= self.end_date:
            bucket_end = current + timedelta(hours=self.step_hours)

            buckets.append({
                "bucket_index": len(buckets),
                "window_start": current.isoformat(),
                "window_end": bucket_end.isoformat(),
                "latencies": [],
                "record_count": 0
            })

            current = bucket_end

        return buckets

    def parse_latency_from_log(self, log_entry: Dict[str, Any]) -> Optional[float]:
        """
        Parse latency value from a whisper-stt log entry.

        Args:
            log_entry: Log entry with timestamp and message fields

        Returns:
            Latency in seconds, or None if not found/invalid
        """
        msg = log_entry.get('message', '')

        # Try common latency patterns
        import re

        patterns = [
            r'processing[_\s]?time[=:](\d+\.?\d*)\s*s',
            r'processing[_\s]?duration[=:](\d+\.?\d*)\s*s',
            r'transcription[_\s]?time[=:](\d+\.?\d*)\s*s',
            r'latency[=:](\d+\.?\d*)\s*s',
        ]

        for pattern in patterns:
            match = re.search(pattern, msg, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return None

    def add_log_entry(self, log_entry: Dict[str, Any]) -> bool:
        """
        Process a log entry and add to appropriate bucket.

        Args:
            log_entry: Log entry with timestamp and message

        Returns:
            True if entry was added to a bucket, False otherwise
        """
        self.total_records_processed += 1

        # Parse timestamp
        timestamp_str = log_entry.get('timestamp')
        if not timestamp_str:
            return False

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            return False

        # Check if within time range
        if not (self.start_date <= timestamp <= self.end_date):
            self.records_outside_range += 1
            return False

        # Parse latency
        latency = self.parse_latency_from_log(log_entry)
        if latency is None or latency <= 0:
            return False

        self.records_with_latency += 1

        # Add to appropriate bucket
        for bucket in self.buckets:
            bucket_start = datetime.fromisoformat(bucket["window_start"])
            bucket_end = datetime.fromisoformat(bucket["window_end"])

            if bucket_start <= timestamp < bucket_end:
                bucket["latencies"].append(latency)
                bucket["record_count"] += 1
                return True

        return False

    def calculate_bucket_percentiles(self, bucket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate percentile metrics for a single bucket.

        Args:
            bucket: Bucket with latencies list

        Returns:
            Dictionary with p50, p95, p99, mean, min, max
        """
        latencies = bucket["latencies"]

        if not latencies:
            return {
                "record_count": 0,
                "p50_seconds": None,
                "p95_seconds": None,
                "p99_seconds": None,
                "mean_seconds": None,
                "min_seconds": None,
                "max_seconds": None
            }

        sorted_latencies = sorted(latencies)

        try:
            quantiles = statistics.quantiles(sorted_latencies, n=100, method='inclusive')
            return {
                "record_count": len(latencies),
                "p50_seconds": round(quantiles[49], 3),
                "p95_seconds": round(quantiles[94], 3),
                "p99_seconds": round(quantiles[98], 3),
                "mean_seconds": round(statistics.mean(sorted_latencies), 3),
                "median_seconds": round(statistics.median(sorted_latencies), 3),
                "min_seconds": round(min(sorted_latencies), 3),
                "max_seconds": round(max(sorted_latencies), 3)
            }
        except Exception as e:
            return {
                "error": str(e),
                "record_count": len(latencies)
            }

    def get_aggregated_results(self) -> Dict[str, Any]:
        """
        Get aggregated results with metrics for all buckets.

        Returns:
            Dictionary with metadata and time-bucketed metrics
        """
        time_buckets = []
        bucket_gaps = []

        for bucket in self.buckets:
            metrics = self.calculate_bucket_percentiles(bucket)

            bucket_result = {
                "bucket_index": bucket["bucket_index"],
                "window_start": bucket["window_start"],
                "window_end": bucket["window_end"],
                "window_label": self._format_window_label(bucket),
                "metrics": metrics
            }

            time_buckets.append(bucket_result)

            # Track empty buckets (temporal gaps)
            if metrics.get("record_count", 0) == 0:
                bucket_gaps.append({
                    "bucket_index": bucket["bucket_index"],
                    "window_start": bucket["window_start"],
                    "window_end": bucket["window_end"]
                })

        # Calculate coverage statistics
        filled_buckets = sum(1 for b in time_buckets if b["metrics"].get("record_count", 0) > 0)
        coverage_percentage = (filled_buckets / len(time_buckets)) * 100 if time_buckets else 0

        return {
            "aggregation_metadata": {
                "step_size": self.step_size_str,
                "step_hours": self.step_hours,
                "total_buckets": self.total_buckets,
                "time_range": {
                    "start": self.start_date.isoformat(),
                    "end": self.end_date.isoformat()
                },
                "processing_stats": {
                    "total_records_processed": self.total_records_processed,
                    "records_with_latency": self.records_with_latency,
                    "records_outside_range": self.records_outside_range,
                    "parse_success_rate": round(
                        (self.records_with_latency / self.total_records_processed * 100)
                        if self.total_records_processed > 0 else 0,
                        2
                    )
                },
                "coverage": {
                    "filled_buckets": filled_buckets,
                    "empty_buckets": len(bucket_gaps),
                    "coverage_percentage": round(coverage_percentage, 2)
                },
                "expected_records_per_bucket": round(
                    self.records_with_latency / filled_buckets,
                    0
                ) if filled_buckets > 0 else 0,
                "generated_at": datetime.now().isoformat()
            },
            "time_buckets": time_buckets,
            "temporal_gaps": bucket_gaps[:10]  # First 10 gaps
        }

    def _format_window_label(self, bucket: Dict[str, Any]) -> str:
        """Format human-readable window label."""
        start = datetime.fromisoformat(bucket["window_start"])
        return f"{start.strftime('%Y-%m-%d %H:%M')} - {self.step_hours}h"

    def process_log_file(self, log_file_path: Path) -> Dict[str, Any]:
        """
        Process a log file in JSONL format.

        Args:
            log_file_path: Path to JSONL log file

        Returns:
            Aggregated results dictionary
        """
        print(f"\nProcessing log file: {log_file_path}")
        print(f"Time range: {self.start_date.date()} to {self.end_date.date()}")
        print(f"Step size: {self.step_size_str} ({self.total_buckets} buckets)")

        if not log_file_path.exists():
            print(f"✗ File not found: {log_file_path}")
            return {"error": "File not found"}

        line_count = 0
        with open(log_file_path, 'r') as f:
            for line in f:
                line_count += 1
                if line_count % 10000 == 0:
                    print(f"  Processed {line_count:,} lines...")

                try:
                    log_entry = json.loads(line.strip())
                    self.add_log_entry(log_entry)
                except (json.JSONDecodeError, ValueError):
                    continue

        print(f"✓ Processed {line_count:,} lines")
        print(f"  Records with latency: {self.records_with_latency:,}")
        print(f"  Records outside range: {self.records_outside_range:,}")

        return self.get_aggregated_results()

    def save_results(self, output_file: Path) -> None:
        """Save aggregated results to JSON file."""
        results = self.get_aggregated_results()

        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n✓ Results saved to: {output_file}")
        print(f"  Total buckets: {results['aggregation_metadata']['total_buckets']}")
        print(f"  Filled buckets: {results['aggregation_metadata']['coverage']['filled_buckets']}")
        print(f"  Coverage: {results['aggregation_metadata']['coverage']['coverage_percentage']}%")


def main():
    """Main execution."""
    print("=" * 70)
    print("Whisper-STT Latency Aggregation with Optimized 1-Hour Steps")
    print("=" * 70)

    # Initialize aggregator with optimal 1-hour steps (from calculate_optimal_step_size.py analysis)
    aggregator = WhisperSTTLatencyAggregator(
        start_date="2026-07-07T00:00:00Z",
        end_date="2026-08-06T23:59:59Z",
        step_hours=1  # <-- OPTIMAL STEP SIZE (high granularity, good manageability)
    )

    # Process log file
    log_file = Path("/home/coding/aide-de-camp/logs/whisper-stt-raw.jsonl")
    results = aggregator.process_log_file(log_file)

    if "error" not in results:
        # Save results
        output_file = Path("/home/coding/aide-de-camp/data/whisper-stt-latency-aggregated-1h.json")
        aggregator.save_results(output_file)

        # Print summary
        metadata = results["aggregation_metadata"]
        print(f"\n{'='*70}")
        print("AGGREGATION SUMMARY")
        print(f"{'='*70}")
        print(f"Step size: {metadata['step_size']}")
        print(f"Total buckets: {metadata['total_buckets']}")
        print(f"Records processed: {metadata['processing_stats']['total_records_processed']:,}")
        print(f"Records with latency: {metadata['processing_stats']['records_with_latency']:,}")
        print(f"Coverage: {metadata['coverage']['coverage_percentage']}% "
              f"({metadata['coverage']['filled_buckets']}/{metadata['total_buckets']} buckets)")

        # Sample buckets
        print(f"\nSample time buckets:")
        for bucket in results["time_buckets"][:5]:
            metrics = bucket["metrics"]
            print(f"  [{bucket['bucket_index']}] {bucket['window_label']}: "
                  f"{metrics.get('record_count', 0)} records, "
                  f"p50={metrics.get('p50_seconds')}s, "
                  f"p95={metrics.get('p95_seconds')}s")
    else:
        print(f"\n✗ Error: {results['error']}")
        return 1

    print(f"\n{'='*70}")
    print("COMPLETE")
    print(f"{'='*70}")
    return 0


if __name__ == "__main__":
    exit(main())
