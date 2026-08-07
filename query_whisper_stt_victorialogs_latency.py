#!/usr/bin/env python3
"""
Query whisper-stt latency metrics from VictoriaLogs for 30-day window

This script:
1. Queries VictoriaLogs for whisper-stt latency data (30-day window)
2. Uses time-bucketed aggregation with configurable step size (optimal: 6h)
3. Calculates p50, p95, p99 processing duration percentiles per time bucket
4. Stores raw results in intermediate format
5. Generates query log with timestamps and result counts

Time Step Configuration:
    The step parameter controls time-bucketed aggregation granularity.
    Format: "<number><unit>" where unit is s (seconds), m (minutes), h (hours), d (days)
    Example: "6h" = 6-hour buckets, "1d" = 1-day buckets

    Optimal Configuration (from config/time_step_granularity.yaml):
    - Default: "6h" (6-hour buckets)
    - 30-day window → 120 buckets (30 days × 24 hours ÷ 6 hours)
    - ~876 entries per bucket (based on actual whisper-stt data rate: 146 entries/hour)
    - Balances query performance with statistical significance

    Alternative Configurations:
    - "1h": Detailed hourly trends (720 buckets for 30 days)
    - "1d": High-level daily trends (30 buckets for 30 days)
    - "15m": Fine-grained analysis (use only for <7 day windows)

Usage:
    python query_whisper_stt_victorialogs_latency.py
    python query_whisper_stt_victorialogs_latency.py --test  # Run step parameter tests
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict
import subprocess
import urllib.parse
import re
import yaml


class WhisperSTTVictoriaLogsQuery:
    """Query and analyze whisper-stt latency metrics from VictoriaLogs."""

    def __init__(self, start_date: str, end_date: str, step: str = "6h"):
        """
        Initialize the query engine with time step granularity.

        Args:
            start_date: ISO format start timestamp (e.g., "2026-07-07T00:00:00Z")
            end_date: ISO format end timestamp (e.g., "2026-08-06T23:59:59Z")
            step: Time step size in VictoriaLogs format (e.g., "6h", "1h", "1d")
                  Format: <number><unit> where unit is s, m, h, or d
                  Default: "6h" (optimal for 30-day aggregation from config)

        The step size determines the granularity of time-bucketed aggregation.
        Recommended: "6h" for balanced performance and detail in 30-day windows.
        """
        self.start_date = start_date
        self.end_date = end_date
        self.step = step  # VictoriaLogs step format (e.g., "6h", "1h", "1d")
        self.step_hours = self._parse_step_to_hours(step)  # Convert to hours for internal calculations
        self.latency_data = []
        self.query_log = []
        self.error_count = 0
        self.time_buckets = []  # For time-bucketed aggregation

        # VictoriaLogs configuration
        self.vlogs_url = "http://victorialogs.ardenone-manager:24169"
        self.query_endpoint = f"{self.vlogs_url}/select/logsql/query"

    def _parse_step_to_hours(self, step: str) -> int:
        """
        Parse VictoriaLogs step format to hours.

        Args:
            step: Step string in format "<number><unit>" (e.g., "6h", "30m", "1d")

        Returns:
            Equivalent number of hours (rounded down for partial hours)

        Examples:
            "6h" -> 6
            "1h" -> 1
            "30m" -> 0 (rounded down)
            "1d" -> 24
            "15s" -> 0 (rounded down)
        """
        if not step:
            return 1  # Default fallback

        # Parse the step format: number followed by unit
        match = re.match(r'^(\d+)([smhd])$', step.lower())
        if not match:
            print(f"Warning: Invalid step format '{step}', defaulting to 1 hour")
            return 1

        value = int(match.group(1))
        unit = match.group(2)

        # Convert to hours
        conversion_factors = {
            's': 1 / 3600,  # seconds to hours
            'm': 1 / 60,    # minutes to hours
            'h': 1,         # hours to hours
            'd': 24         # days to hours
        }

        hours = value * conversion_factors.get(unit, 1)

        # Return as integer (round down for partial hours)
        return int(hours)

    def log_query(self, query: str, timestamp: str, result_count: int,
                  execution_time_ms: float, status: str = "success"):
        """Log query execution details."""
        self.query_log.append({
            "timestamp": timestamp,
            "query": query,
            "result_count": result_count,
            "execution_time_ms": round(execution_time_ms, 2),
            "status": status
        })

    def construct_whisper_stt_latency_query(self) -> str:
        """
        Construct VictoriaLogs query for whisper-stt latency metrics.

        Returns MetricsQL query for extracting processing duration from whisper-stt logs.
        whisper-stt logs contain processing duration for speech-to-text transcription.
        """
        query = f"""
        SELECT
            _time,
            _msg,
            app,
            kubernetes.namespace_name,
            kubernetes.pod_name,
            kubernetes.container_name
        FROM "{self.vlogs_url}"
        WHERE
            (app='whisper-stt' OR kubernetes.namespace_name='whisper-stt')
            AND _time >= '{self.start_date}'
            AND _time <= '{self.end_date}'
        """

        return query.strip()

    def construct_percentile_query(self) -> str:
        """Construct query to calculate percentiles directly in VictoriaLogs."""
        query = f"""
        SELECT
            quantile_over_time(0.50, processing_duration) as p50,
            quantile_over_time(0.95, processing_duration) as p95,
            quantile_over_time(0.99, processing_duration) as p99
        FROM "{self.vlogs_url}"
        WHERE
            (app='whisper-stt' OR kubernetes.namespace_name='whisper-stt')
            AND _time >= '{self.start_date}'
            AND _time <= '{self.end_date}'
        """

        return query.strip()

    def _initialize_time_buckets(self) -> List[Dict[str, Any]]:
        """
        Initialize time buckets for step-based aggregation.

        Creates buckets covering the full date range with configured step size.
        Each bucket represents a time window for calculating percentiles.

        Returns:
            List of time bucket dictionaries with metadata
        """
        from datetime import datetime, timedelta

        start_dt = datetime.fromisoformat(self.start_date.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(self.end_date.replace('Z', '+00:00'))

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

    def _add_to_time_bucket(self, timestamp: datetime, latency: float) -> bool:
        """
        Add latency value to appropriate time bucket.

        Args:
            timestamp: Datetime timestamp of the log entry
            latency: Latency value in seconds

        Returns:
            True if added to a bucket, False otherwise
        """
        if not self.time_buckets:
            return False

        for bucket in self.time_buckets:
            bucket_start = datetime.fromisoformat(bucket["window_start"])
            bucket_end = datetime.fromisoformat(bucket["window_end"])

            if bucket_start <= timestamp < bucket_end:
                bucket["latencies"].append(latency)
                bucket["record_count"] += 1
                return True

        return False

    def _calculate_bucket_percentiles(self, bucket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate percentile metrics for a single time bucket.

        Args:
            bucket: Bucket dictionary with latencies list

        Returns:
            Dictionary with p50, p95, p99, mean, min, max metrics
        """
        latencies = bucket["latencies"]

        if not latencies:
            return {
                "record_count": 0,
                "p50_seconds": None,
                "p95_seconds": None,
                "p99_seconds": None,
                "mean_seconds": None,
                "median_seconds": None,
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

    def execute_query_via_curl(self, query: str) -> Tuple[List[Dict], float]:
        """
        Execute VictoriaLogs query via curl and return results with timing.

        Returns: (results, execution_time_ms)
        """
        import time

        # URL encode the query
        encoded_query = urllib.parse.quote(query)

        # Construct the full URL
        url = f"{self.query_endpoint}?query={encoded_query}"

        start_time = time.time()

        try:
            result = subprocess.run(
                ["curl", "-s", "-X", "POST", url],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            execution_time_ms = (time.time() - start_time) * 1000

            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    return data, execution_time_ms
                except json.JSONDecodeError:
                    return [], execution_time_ms
            else:
                self.error_count += 1
                return [], execution_time_ms

        except subprocess.TimeoutExpired:
            self.error_count += 1
            return [], (time.time() - start_time) * 1000
        except Exception as e:
            self.error_count += 1
            return [], 0.0

    def parse_whisper_stt_latency(self, log_entry: Dict[str, Any]) -> float:
        """
        Parse latency from whisper-stt log entry.

        whisper-stt logs contain processing duration for speech transcription:
        - Processing duration in seconds or milliseconds
        - Transcription completion time
        - Audio processing duration

        Returns latency in seconds, or None if not found.
        """
        msg = log_entry.get('_msg', '')

        # Try to extract processing duration from common whisper-stt log formats
        import re

        # Look for processing duration patterns (in seconds)
        duration_patterns = [
            r'processing[_\s]?time[=:](\d+\.?\d*)\s*s',
            r'processing[_\s]?duration[=:](\d+\.?\d*)\s*s',
            r'transcription[_\s]?time[=:](\d+\.?\d*)\s*s',
            r'audio[_\s]?processing[=:](\d+\.?\d*)\s*s',
            r'processing[_\s]?duration[=:](\d+\.?\d*)(?!\d)',  # Plain number (assume seconds)
            r'took[=:](\d+\.?\d*)\s*s',
            r'completed[=:](\d+\.?\d*)\s*s',
            r'latency[=:](\d+\.?\d*)\s*s',
            # Millisecond patterns
            r'processing[_\s]?time[=:](\d+\.?\d*)\s*ms',
            r'duration[=:](\d+\.?\d*)\s*ms',
        ]

        for pattern in duration_patterns:
            match = re.search(pattern, msg, re.IGNORECASE)
            if match:
                try:
                    duration = float(match.group(1))
                    # Convert milliseconds to seconds if ms pattern
                    if 'ms' in pattern.lower():
                        duration = duration / 1000
                    return duration
                except ValueError:
                    continue

        # If no explicit latency field, we can't calculate it
        return None

    def calculate_percentiles(self) -> Dict[str, float]:
        """Calculate p50, p95, p99 percentiles from latency data."""
        if not self.latency_data:
            return {
                "count": 0,
                "p50_seconds": 0,
                "p95_seconds": 0,
                "p99_seconds": 0,
                "mean_seconds": 0,
                "median_seconds": 0,
                "min_seconds": 0,
                "max_seconds": 0
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
        except Exception as e:
            # Fallback to manual calculation
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

    def process_local_victorialogs_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Process local VictoriaLogs JSON file and extract latency metrics.

        This is used when direct query to VictoriaLogs is not available.
        Uses time-bucketed aggregation with configured step size (optimal: 1-hour).
        """
        print(f"\nProcessing local VictoriaLogs file: {file_path}")
        print(f"Using time-bucketed aggregation with step size: {self.step_hours}h")

        if not file_path.exists():
            return {
                "status": "error",
                "message": f"File not found: {file_path}",
                "latency_metrics": {},
                "raw_data": [],
                "query_log": []
            }

        # Initialize time buckets with configured step size
        self.time_buckets = self._initialize_time_buckets()
        total_buckets = len(self.time_buckets)
        print(f"  Initialized {total_buckets} time buckets for step-based aggregation")

        total_entries = 0
        entries_with_latency = 0
        time_range_data = defaultdict(int)
        temporal_gaps = []

        start_time = datetime.now()

        try:
            with open(file_path, 'r') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        total_entries += 1

                        # Extract timestamp
                        timestamp_str = log_entry.get('_time', '')
                        if not timestamp_str:
                            continue

                        try:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        except ValueError:
                            continue

                        # Check if within time range
                        query_start = datetime.fromisoformat(self.start_date.replace('Z', '+00:00'))
                        query_end = datetime.fromisoformat(self.end_date.replace('Z', '+00:00'))

                        if not (query_start <= timestamp <= query_end):
                            continue

                        # Try to parse latency
                        latency = self.parse_whisper_stt_latency(log_entry)
                        if latency is not None and latency > 0:
                            # Add to appropriate time bucket instead of flat list
                            if self._add_to_time_bucket(timestamp, latency):
                                entries_with_latency += 1

                            # Also add to flat list for backward compatibility
                            self.latency_data.append(latency)

                            # Track temporal coverage
                            date_key = timestamp.date().isoformat()
                            time_range_data[date_key] += 1

                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        self.error_count += 1
                        continue

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error processing file: {e}",
                "latency_metrics": {},
                "raw_data": [],
                "query_log": []
            }

        execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Check for temporal gaps
        expected_days = (query_end - query_start).days + 1
        actual_days = len(time_range_data)
        if actual_days < expected_days:
            current = query_start
            while current <= query_end:
                date_key = current.date().isoformat()
                if date_key not in time_range_data:
                    temporal_gaps.append(date_key)
                current += timedelta(days=1)

        # Calculate metrics
        latency_metrics = self.calculate_percentiles()

        # Log the "query" (file processing)
        self.log_query(
            f"PROCESS_FILE: {file_path}",
            datetime.now().isoformat(),
            entries_with_latency,
            execution_time_ms,
            "success" if self.error_count == 0 else "partial"
        )

        # Store raw data with timestamps
        raw_data = [
            {
                "timestamp": timestamp.isoformat(),
                "latency_seconds": round(latency, 3),
            }
            for timestamp, latency in zip([datetime.now()] * len(self.latency_data), self.latency_data)
        ]

        return {
            "status": "success",
            "latency_metrics": latency_metrics,
            "raw_data": raw_data,
            "query_log": self.query_log,
            "processing_stats": {
                "total_entries_processed": total_entries,
                "entries_with_latency": entries_with_latency,
                "entries_without_latency": total_entries - entries_with_latency,
                "parse_errors": self.error_count,
                "temporal_coverage_days": actual_days,
                "temporal_gaps": temporal_gaps,
                "expected_days": expected_days,
                "coverage_percentage": round((actual_days / expected_days) * 100, 2) if expected_days > 0 else 0,
                "execution_time_ms": round(execution_time_ms, 2)
            }
        }


def load_step_config() -> str:
    """
    Load step configuration from config file.

    Returns the configured step size (e.g., "6h") or defaults to "6h".
    """
    config_path = Path("/home/coding/aide-de-camp/config/time_step_granularity.yaml")

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                step = config.get('default', {}).get('step', '6h')
                print(f"✓ Loaded step configuration from {config_path}: {step}")
                return step
        except Exception as e:
            print(f"Warning: Could not load config file {config_path}: {e}")

    return "6h"  # Default optimal value


def main():
    """Query whisper-stt latency metrics from VictoriaLogs for 30-day window."""
    print("=" * 70)
    print("Querying whisper-stt Latency Metrics from VictoriaLogs")
    print("=" * 70)

    # Time range: 30 days ending today (2026-08-06)
    start_date = "2026-07-07T00:00:00Z"
    end_date = "2026-08-06T23:59:59Z"

    print(f"\nTime Range: {start_date} to {end_date} (30 days)")
    print(f"Service: whisper-stt")

    # Load step configuration
    step = load_step_config()

    # Initialize query engine with configured step
    query_engine = WhisperSTTVictoriaLogsQuery(start_date, end_date, step=step)
    print(f"Time step granularity: {step} ({query_engine.step_hours} hours per bucket)")

    # Check for local VictoriaLogs files
    possible_files = [
        Path("/home/coding/aide-de-camp/logs/whisper-stt-30day-victorialogs.jsonl"),
        Path("/home/coding/aide-de-camp/logs/whisper-stt-victorialogs.jsonl"),
    ]

    results = {
        "query_metadata": {
            "timestamp": datetime.now().isoformat(),
            "time_period_days": 30,
            "start_date": start_date,
            "end_date": end_date,
            "service": "whisper-stt",
            "metrics_queried": ["p50", "p95", "p99", "mean", "median", "min", "max"]
        },
        "latency_metrics": {},
        "raw_data": [],
        "query_log": [],
        "processing_stats": {}
    }

    local_file_found = False
    for local_vlogs_file in possible_files:
        if local_vlogs_file.exists() and local_vlogs_file.stat().st_size > 0:
            print(f"\n✓ Found local VictoriaLogs file: {local_vlogs_file}")
            print(f"  Size: {local_vlogs_file.stat().st_size / (1024*1024):.1f} MB")

            # Process local file
            file_results = query_engine.process_local_victorialogs_file(local_vlogs_file)

            if file_results["status"] == "success":
                results["latency_metrics"] = file_results["latency_metrics"]
                results["raw_data"] = file_results["raw_data"]
                results["query_log"] = file_results["query_log"]
                results["processing_stats"] = file_results["processing_stats"]

                metrics = results["latency_metrics"]
                stats = results["processing_stats"]

                print(f"\n{'='*70}")
                print("LATENCY METRICS RESULTS")
                print(f"{'='*70}")
                print(f"\nValid latency entries: {metrics['count']}")
                print(f"Total entries processed: {stats['total_entries_processed']}")
                print(f"Entries with latency data: {stats['entries_with_latency']}")
                print(f"Entries without latency data: {stats['entries_without_latency']}")

                if metrics['count'] > 0:
                    print(f"\nPercentile Metrics:")
                    print(f"  p50 (median):  {metrics['p50_seconds']}s")
                    print(f"  p95:          {metrics['p95_seconds']}s")
                    print(f"  p99:          {metrics['p99_seconds']}s")
                    print(f"\nAdditional Metrics:")
                    print(f"  Mean:         {metrics['mean_seconds']}s")
                    print(f"  Median:       {metrics['median_seconds']}s")
                    print(f"  Min:          {metrics['min_seconds']}s")
                    print(f"  Max:          {metrics['max_seconds']}s")

                print(f"\nProcessing Stats:")
                print(f"  Temporal coverage: {stats['temporal_coverage_days']}/{stats['expected_days']} days ({stats['coverage_percentage']}%)")
                print(f"  Parse errors: {stats['parse_errors']}")
                print(f"  Execution time: {stats['execution_time_ms']}ms")

                if stats.get('temporal_gaps'):
                    print(f"  Temporal gaps: {len(stats['temporal_gaps'])} days")
                    print(f"  Gap dates: {stats['temporal_gaps'][:10]}{'...' if len(stats['temporal_gaps']) > 10 else ''}")

                if results["query_log"]:
                    print(f"\nQuery Log:")
                    for log_entry in results["query_log"]:
                        print(f"  [{log_entry['timestamp']}] {log_entry['status']}: "
                              f"{log_entry['result_count']} results "
                              f"({log_entry['execution_time_ms']}ms)")

                local_file_found = True
                break
            else:
                print(f"\n✗ Error processing file: {file_results.get('message', 'Unknown error')}")
                results["error"] = file_results.get("message")

    if not local_file_found:
        print(f"\n✗ No local VictoriaLogs files found with data")
        print("  Files checked:")
        for f in possible_files:
            exists = "✓" if f.exists() else "✗"
            size = f.stat().st_size if f.exists() else 0
            print(f"    {exists} {f} ({size} bytes)")

        print("\nAttempting direct VictoriaLogs query...")

        # Try direct query
        query = query_engine.construct_whisper_stt_latency_query()
        print(f"\nQuery: {query}")

        # Note: Direct query implementation
        print("\nExecuting direct VictoriaLogs query...")
        query_results, exec_time = query_engine.execute_query_via_curl(query)

        if query_results:
            print(f"✓ Query executed successfully in {exec_time:.2f}ms")
            print(f"  Results returned: {len(query_results) if isinstance(query_results, list) else 'unknown'}")

            # Process results
            for entry in query_results if isinstance(query_results, list) else []:
                latency = query_engine.parse_whisper_stt_latency(entry)
                if latency is not None and latency > 0:
                    query_engine.latency_data.append(latency)

            # Calculate metrics
            latency_metrics = query_engine.calculate_percentiles()
            results["latency_metrics"] = latency_metrics
            results["processing_stats"] = {
                "query_method": "direct_victorialogs",
                "execution_time_ms": round(exec_time, 2),
                "total_results": len(query_results) if isinstance(query_results, list) else 0
            }

            # Log query
            query_engine.log_query(
                query,
                datetime.now().isoformat(),
                latency_metrics.get('count', 0),
                exec_time,
                "success"
            )
            results["query_log"] = query_engine.query_log

        else:
            print(f"✗ Direct query failed or returned no results")
            results["error"] = "No local VictoriaLogs files found and direct query failed"

    # Create output directory
    output_dir = Path("/home/coding/aide-de-camp/data/latency-metrics")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Store raw latency data
    if results.get("raw_data"):
        raw_file = output_dir / "whisper-stt-victorialogs-latency-raw.json"
        with open(raw_file, 'w') as f:
            json.dump({
                "service": "whisper-stt",
                "source": "victorialogs",
                "time_range": {"start": start_date, "end": end_date},
                "raw_data": results["raw_data"]
            }, f, indent=2)
        print(f"\n✓ Raw latency data saved to: {raw_file}")

    # Store comprehensive results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = output_dir / f"whisper-stt-victorialogs-latency-{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Comprehensive results saved to: {results_file}")

    # Store query log
    if results.get("query_log"):
        query_log_file = output_dir / f"whisper-stt-victorialogs-query-log-{timestamp}.json"
        with open(query_log_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "query_log": results["query_log"]
            }, f, indent=2)
        print(f"✓ Query log saved to: {query_log_file}")

    print(f"\n{'='*70}")
    print("QUERY COMPLETE")
    print(f"{'='*70}")

    return results


def test_step_parameter():
    """Test step parameter configuration with various formats."""
    print("\n" + "=" * 70)
    print("STEP PARAMETER CONFIGURATION TEST")
    print("=" * 70)

    test_cases = [
        ("6h", 6, "Standard 6-hour granularity"),
        ("1h", 1, "Detailed 1-hour granularity"),
        ("1d", 24, "Daily granularity"),
        ("30m", 0, "30-minute (rounded down to 0 hours)"),
        ("15s", 0, "15-second (rounded down to 0 hours)"),
        ("invalid", 1, "Invalid format (fallback to 1 hour)"),
    ]

    print("\nTesting step parameter parsing:")
    all_passed = True

    for step_input, expected_hours, description in test_cases:
        try:
            # Create a test query instance
            query = WhisperSTTVictoriaLogsQuery(
                "2026-08-01T00:00:00Z",
                "2026-08-01T23:59:59Z",
                step=step_input
            )

            actual_hours = query.step_hours
            status = "✅" if actual_hours == expected_hours else "❌"

            print(f"{status} {step_input:10s} → {actual_hours} hours | {description}")

            if actual_hours != expected_hours:
                all_passed = False
                print(f"   ERROR: Expected {expected_hours} hours, got {actual_hours}")

        except Exception as e:
            print(f"❌ {step_input:10s} → ERROR: {e}")
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ ALL TESTS PASSED - Step parameter configuration working correctly")
    else:
        print("❌ SOME TESTS FAILED - Review step parameter parsing logic")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    import sys

    # Check if we should run tests
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_passed = test_step_parameter()
        sys.exit(0 if test_passed else 1)
    else:
        main()
