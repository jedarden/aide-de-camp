#!/usr/bin/env python3
"""
Execute whisper-stt latency query with p50/p95/p99 percentile aggregation

Processes local whisper-stt-30day.jsonl file to calculate processing duration
percentiles over 30 days using configured time step granularity.

Acceptance Criteria:
1. Execute query using designed structure and configured time step
2. Capture p50, p95, p99 percentiles for processing duration
3. Log query execution timestamp and duration
4. Verify result count matches expectations

Task: adc-1xwwu
Created: 2026-08-07
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple
import yaml
from collections import defaultdict
import time


class PercentileQueryExecutor:
    """Execute whisper-stt latency percentile queries using local data."""

    def __init__(self, data_file: Path, step: str = "1h"):
        """
        Initialize query executor with local data file.

        Args:
            data_file: Path to whisper-stt-30day.jsonl
            step: Time step granularity (e.g., "1h", "6h")
        """
        self.data_file = data_file
        self.step = step
        self.step_hours = self._parse_step_to_hours(step)

        # Query metadata
        self.query_timestamp = datetime.now().isoformat()
        self.execution_start = None
        self.execution_end = None

        # Results storage
        self.latency_data = []
        self.time_buckets = []
        self.parse_errors = 0

        # Expected metrics (from configuration analysis)
        self.expected_data_points = 720  # 30 days × 24 hours for 1h step
        self.expected_min_samples_per_bucket = 30

    def _parse_step_to_hours(self, step: str) -> int:
        """Parse step format to hours (e.g., '1h' -> 1, '6h' -> 6)."""
        import re
        match = re.match(r'^(\d+)([smhd])$', step.lower())
        if not match:
            return 1

        value = int(match.group(1))
        unit = match.group(2)

        conversion = {'s': 1/3600, 'm': 1/60, 'h': 1, 'd': 24}
        return int(value * conversion.get(unit, 1))

    def initialize_time_buckets(self, start_date: str, end_date: str) -> List[Dict]:
        """Initialize time buckets for step-based aggregation."""
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        buckets = []
        current = start_dt
        bucket_index = 0

        while current <= end_dt:
            bucket_end = current + timedelta(hours=self.step_hours)

            buckets.append({
                "bucket_index": bucket_index,
                "window_start": current.isoformat(),
                "window_end": min(bucket_end, end_dt).isoformat(),
                "latencies": [],
                "record_count": 0
            })

            current = bucket_end
            bucket_index += 1

        return buckets

    def parse_latency_from_message(self, message: str) -> float:
        """Extract processing duration from log message in seconds."""
        import re

        # Duration patterns in seconds
        duration_patterns = [
            r'processing[_\s]?time[=:](\d+\.?\d*)\s*s',
            r'processing[_\s]?duration[=:](\d+\.?\d*)\s*s',
            r'transcription[_\s]?time[=:](\d+\.?\d*)\s*s',
            r'audio[_\s]?processing[=:](\d+\.?\d*)\s*s',
            r'took[=:](\d+\.?\d*)\s*s',
            r'completed[=:](\d+\.?\d*)\s*s',
            r'latency[=:](\d+\.?\d*)\s*s',
        ]

        for pattern in duration_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return None

    def process_local_file(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Process local file and calculate percentiles with timing."""
        self.execution_start = time.time()
        print(f"\n[{self.query_timestamp}] Executing percentile query...")
        print(f"Data file: {self.data_file}")
        print(f"Time step: {self.step} ({self.step_hours}h buckets)")
        print(f"Time range: {start_date} to {end_date}")

        # Initialize time buckets
        self.time_buckets = self.initialize_time_buckets(start_date, end_date)
        total_buckets = len(self.time_buckets)
        print(f"Initialized {total_buckets} time buckets")

        # Process file
        total_entries = 0
        entries_with_latency = 0
        temporal_coverage = defaultdict(int)

        query_start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        query_end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        try:
            with open(self.data_file, 'r') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        total_entries += 1

                        # Extract timestamp
                        timestamp_str = log_entry.get('timestamp', '')
                        if not timestamp_str:
                            continue

                        try:
                            timestamp = datetime.fromisoformat(timestamp_str)
                        except ValueError:
                            continue

                        # Check time range
                        if not (query_start_dt <= timestamp <= query_end_dt):
                            continue

                        # Parse latency
                        message = log_entry.get('message', '')
                        latency = self.parse_latency_from_message(message)

                        if latency is not None and latency > 0:
                            # Add to time bucket
                            for bucket in self.time_buckets:
                                bucket_start = datetime.fromisoformat(bucket["window_start"])
                                bucket_end = datetime.fromisoformat(bucket["window_end"])

                                if bucket_start <= timestamp < bucket_end:
                                    bucket["latencies"].append(latency)
                                    bucket["record_count"] += 1
                                    entries_with_latency += 1
                                    self.latency_data.append(latency)
                                    break

                            # Track temporal coverage
                            date_key = timestamp.date().isoformat()
                            temporal_coverage[date_key] += 1

                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        self.parse_errors += 1
                        continue

        except Exception as e:
            self.execution_end = time.time()
            return {
                "status": "error",
                "message": f"Error processing file: {e}",
                "execution_time_ms": 0
            }

        self.execution_end = time.time()
        execution_time_ms = (self.execution_end - self.execution_start) * 1000

        # Calculate percentiles
        latency_metrics = self.calculate_percentiles()

        # Calculate bucket-level metrics
        bucket_metrics = self.calculate_bucket_metrics()

        # Check expectations
        verification = self.verify_expectations(entries_with_latency, total_buckets)

        return {
            "status": "success",
            "query_metadata": {
                "timestamp": self.query_timestamp,
                "execution_time_ms": round(execution_time_ms, 2),
                "data_file": str(self.data_file),
                "time_step": self.step,
                "step_hours": self.step_hours,
                "time_range": {
                    "start": start_date,
                    "end": end_date
                }
            },
            "latency_metrics": latency_metrics,
            "bucket_metrics": bucket_metrics,
            "processing_stats": {
                "total_entries_processed": total_entries,
                "entries_with_latency": entries_with_latency,
                "parse_errors": self.parse_errors,
                "temporal_coverage_days": len(temporal_coverage),
                "execution_time_ms": round(execution_time_ms, 2)
            },
            "verification": verification
        }

    def calculate_percentiles(self) -> Dict[str, float]:
        """Calculate p50, p95, p99 percentiles from all latency data."""
        if not self.latency_data:
            return {
                "count": 0,
                "p50_seconds": None,
                "p95_seconds": None,
                "p99_seconds": None,
                "mean_seconds": None,
                "median_seconds": None,
                "min_seconds": None,
                "max_seconds": None
            }

        sorted_data = sorted(self.latency_data)
        n = len(sorted_data)

        try:
            quantiles = statistics.quantiles(sorted_data, n=100, method='inclusive')
            return {
                "count": n,
                "p50_seconds": round(quantiles[49], 3),
                "p95_seconds": round(quantiles[94], 3),
                "p99_seconds": round(quantiles[98], 3),
                "mean_seconds": round(statistics.mean(sorted_data), 3),
                "median_seconds": round(statistics.median(sorted_data), 3),
                "min_seconds": round(min(sorted_data), 3),
                "max_seconds": round(max(sorted_data), 3)
            }
        except Exception:
            # Fallback calculation
            def percentile(p: float) -> float:
                index = int(n * p / 100)
                return sorted_data[min(index, n - 1)]

            return {
                "count": n,
                "p50_seconds": round(percentile(50), 3),
                "p95_seconds": round(percentile(95), 3),
                "p99_seconds": round(percentile(99), 3),
                "mean_seconds": round(statistics.mean(sorted_data), 3),
                "median_seconds": round(statistics.median(sorted_data), 3),
                "min_seconds": round(min(sorted_data), 3),
                "max_seconds": round(max(sorted_data), 3)
            }

    def calculate_bucket_metrics(self) -> List[Dict[str, Any]]:
        """Calculate percentile metrics for each time bucket."""
        bucket_results = []

        for bucket in self.time_buckets:
            latencies = bucket["latencies"]

            if not latencies:
                bucket_results.append({
                    "bucket_index": bucket["bucket_index"],
                    "window_start": bucket["window_start"],
                    "window_end": bucket["window_end"],
                    "record_count": 0,
                    "p50_seconds": None,
                    "p95_seconds": None,
                    "p99_seconds": None
                })
                continue

            sorted_latencies = sorted(latencies)

            try:
                quantiles = statistics.quantiles(sorted_latencies, n=100, method='inclusive')
                bucket_results.append({
                    "bucket_index": bucket["bucket_index"],
                    "window_start": bucket["window_start"],
                    "window_end": bucket["window_end"],
                    "record_count": len(latencies),
                    "p50_seconds": round(quantiles[49], 3),
                    "p95_seconds": round(quantiles[94], 3),
                    "p99_seconds": round(quantiles[98], 3)
                })
            except Exception:
                bucket_results.append({
                    "bucket_index": bucket["bucket_index"],
                    "window_start": bucket["window_start"],
                    "window_end": bucket["window_end"],
                    "record_count": len(latencies),
                    "error": "Failed to calculate quantiles"
                })

        return bucket_results

    def verify_expectations(self, actual_count: int, actual_buckets: int) -> Dict[str, Any]:
        """Verify results match expected metrics."""
        buckets_with_data = sum(1 for b in self.time_buckets if b["record_count"] > 0)
        avg_samples_per_bucket = actual_count / buckets_with_data if buckets_with_data > 0 else 0

        return {
            "expected_data_points": self.expected_data_points,
            "actual_data_points": actual_buckets,
            "data_points_match": actual_buckets <= self.expected_data_points,
            "expected_min_samples_per_bucket": self.expected_min_samples_per_bucket,
            "actual_avg_samples_per_bucket": round(avg_samples_per_bucket, 1),
            "samples_per_bucket_adequate": avg_samples_per_bucket >= self.expected_min_samples_per_bucket,
            "total_latency_records": actual_count,
            "buckets_with_data": buckets_with_data,
            "empty_buckets": actual_buckets - buckets_with_data
        }


def load_step_config() -> str:
    """Load step configuration from config file."""
    config_path = Path("config/time_step_granularity.yaml")

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                return config.get('default', {}).get('step', '1h')
        except Exception:
            pass

    return "1h"


def main():
    """Execute whisper-stt latency percentile query."""
    print("=" * 70)
    print("whisper-stt Latency Percentile Query Execution")
    print("Task: adc-1xwwu")
    print("=" * 70)

    # Load configuration
    step = load_step_config()
    print(f"\n✓ Loaded step configuration: {step}")

    # Data file and time range
    data_file = Path("/home/coding/aide-de-camp/logs/whisper-stt-30day.jsonl")
    start_date = "2026-07-07T00:00:00Z"
    end_date = "2026-08-06T23:59:59Z"

    if not data_file.exists():
        print(f"\n✗ Data file not found: {data_file}")
        return

    # Initialize executor
    executor = PercentileQueryExecutor(data_file, step=step)

    # Execute query
    results = executor.process_local_file(start_date, end_date)

    # Display results
    print(f"\n{'='*70}")
    print("QUERY RESULTS")
    print(f"{'='*70}")

    if results["status"] == "success":
        query_meta = results["query_metadata"]
        metrics = results["latency_metrics"]
        stats = results["processing_stats"]
        verification = results["verification"]

        print(f"\nQuery Execution:")
        print(f"  Timestamp: {query_meta['timestamp']}")
        print(f"  Execution time: {query_meta['execution_time_ms']}ms")
        print(f"  Time step: {query_meta['time_step']} ({query_meta['step_hours']}h)")

        print(f"\nProcessing Stats:")
        print(f"  Total entries: {stats['total_entries_processed']}")
        print(f"  Entries with latency: {stats['entries_with_latency']}")
        print(f"  Parse errors: {stats['parse_errors']}")
        print(f"  Temporal coverage: {stats['temporal_coverage_days']} days")

        print(f"\nPercentile Metrics (30-day aggregation):")
        print(f"  p50 (median):  {metrics['p50_seconds']}s" if metrics['p50_seconds'] else "  p50: No data")
        print(f"  p95:          {metrics['p95_seconds']}s" if metrics['p95_seconds'] else "  p95: No data")
        print(f"  p99:          {metrics['p99_seconds']}s" if metrics['p99_seconds'] else "  p99: No data")
        print(f"  Mean:         {metrics['mean_seconds']}s" if metrics['mean_seconds'] else "  Mean: No data")
        print(f"  Min/Max:      {metrics['min_seconds']}s / {metrics['max_seconds']}s" if metrics['min_seconds'] else "  Min/Max: No data")

        print(f"\nVerification:")
        print(f"  Data points: {verification['actual_data_points']} (expected ≤ {verification['expected_data_points']}) {'✓' if verification['data_points_match'] else '✗'}")
        print(f"  Avg samples/bucket: {verification['actual_avg_samples_per_bucket']} (expected ≥ {verification['expected_min_samples_per_bucket']}) {'✓' if verification['samples_per_bucket_adequate'] else '✗'}")
        print(f"  Buckets with data: {verification['buckets_with_data']}/{verification['actual_data_points']}")
        print(f"  Total latency records: {verification['total_latency_records']}")

        # Save results
        output_dir = Path("/home/coding/aide-de-camp/data/latency-metrics")
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = output_dir / f"whisper-stt-percentile-results-{timestamp}.json"

        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n✓ Results saved to: {results_file}")

    else:
        print(f"\n✗ Query failed: {results.get('message', 'Unknown error')}")

    print(f"\n{'='*70}")
    print("QUERY COMPLETE")
    print(f"{'='*70}")

    return results


if __name__ == "__main__":
    main()
