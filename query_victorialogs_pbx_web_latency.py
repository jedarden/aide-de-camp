#!/usr/bin/env python3
"""
Query pbx-web latency metrics from VictoriaLogs for 30-day window

This script:
1. Queries VictoriaLogs for pbx-web latency data (30-day window)
2. Calculates p50, p95, p99 response time percentiles
3. Stores raw results in intermediate format
4. Generates query log with timestamps and result counts

Usage:
    python query_victorialogs_pbx_web_latency.py
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict
import subprocess
import urllib.parse


class VictoriaLogsLatencyQuery:
    """Query and analyze pbx-web latency metrics from VictoriaLogs."""

    def __init__(self, start_date: str, end_date: str):
        self.start_date = start_date
        self.end_date = end_date
        self.latency_data = []
        self.query_log = []
        self.error_count = 0

        # VictoriaLogs configuration
        self.vlogs_url = "http://victorialogs.ardenone-manager:24169"
        self.query_endpoint = f"{self.vlogs_url}/select/logsql/query"

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

    def construct_latency_query(self) -> str:
        """
        Construct VictoriaLogs query for pbx-web latency metrics.

        Returns MetricsQL query for extracting response times from nginx logs.
        """
        # Since the nginx logs may not have explicit request_time fields,
        # we query for successful requests and can calculate latency statistics

        query = f"""
        SELECT
            _time,
            _msg
        FROM "{self.vlogs_url}"
        WHERE
            app='pbx-web'
            AND kubernetes.container_name='nginx'
            AND _time >= '{self.start_date}'
            AND _time <= '{self.end_date}'
        """

        return query.strip()

    def construct_percentile_query(self) -> str:
        """Construct query to calculate percentiles directly in VictoriaLogs."""
        query = f"""
        SELECT
            quantile_over_time(0.50, request_time) as p50,
            quantile_over_time(0.95, request_time) as p95,
            quantile_over_time(0.99, request_time) as p99
        FROM "{self.vlogs_url}"
        WHERE
            app='pbx-web'
            AND kubernetes.container_name='nginx'
            AND _time >= '{self.start_date}'
            AND _time <= '{self.end_date}'
        """

        return query.strip()

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

    def parse_nginx_latency(self, log_entry: Dict[str, Any]) -> float:
        """
        Parse latency from nginx log entry.

        Standard nginx log format with request time:
        - request_time: total request processing time in seconds
        - upstream_response_time: upstream response time

        Returns latency in seconds, or None if not found.
        """
        msg = log_entry.get('_msg', '')

        # Try to extract request time from common nginx log formats
        # Format: ... "request_time=0.123" or "rt=0.123"
        import re

        # Look for request_time patterns
        rt_patterns = [
            r'request_time[=:](\d+\.?\d*)',
            r'rt[=:](\d+\.?\d*)',
            r'upstream_response_time[=:](\d+\.?\d*)',
            r'urt[=:](\d+\.?\d*)',
        ]

        for pattern in rt_patterns:
            match = re.search(pattern, msg)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        # If no explicit latency field, we can't calculate it from timestamps alone
        # Return None to indicate no latency data available
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
        """
        print(f"\nProcessing local VictoriaLogs file: {file_path}")

        if not file_path.exists():
            return {
                "status": "error",
                "message": f"File not found: {file_path}",
                "latency_metrics": {},
                "raw_data": [],
                "query_log": []
            }

        total_entries = 0
        entries_with_latency = 0
        time_range_data = defaultdict(int)

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
                        latency = self.parse_nginx_latency(log_entry)
                        if latency is not None and latency > 0:
                            self.latency_data.append(latency)
                            entries_with_latency += 1

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

        # Store raw data
        raw_data = [
            {
                "latency_seconds": round(latency, 3),
            }
            for latency in self.latency_data
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
                "temporal_coverage_days": len(time_range_data),
                "execution_time_ms": round(execution_time_ms, 2)
            }
        }


def main():
    """Query pbx-web latency metrics from VictoriaLogs for 30-day window."""
    print("=" * 70)
    print("Querying pbx-web Latency Metrics from VictoriaLogs")
    print("=" * 70)

    # Time range: 30 days ending today (2026-08-06)
    start_date = "2026-07-07T00:00:00Z"
    end_date = "2026-08-06T23:59:59Z"

    print(f"\nTime Range: {start_date} to {end_date} (30 days)")
    print(f"Service: pbx-web")

    # Initialize query engine
    query_engine = VictoriaLogsLatencyQuery(start_date, end_date)

    # Check for local VictoriaLogs file
    local_vlogs_file = Path("/home/coding/aide-de-camp/logs/pbx-web-victorialogs-raw.jsonl")

    results = {
        "query_metadata": {
            "timestamp": datetime.now().isoformat(),
            "time_period_days": 30,
            "start_date": start_date,
            "end_date": end_date,
            "service": "pbx-web",
            "metrics_queried": ["p50", "p95", "p99", "mean", "median", "min", "max"]
        },
        "latency_metrics": {},
        "raw_data": [],
        "query_log": [],
        "processing_stats": {}
    }

    if local_vlogs_file.exists():
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
            print(f"  Temporal coverage: {stats['temporal_coverage_days']} days")
            print(f"  Parse errors: {stats['parse_errors']}")
            print(f"  Execution time: {stats['execution_time_ms']}ms")

            if results["query_log"]:
                print(f"\nQuery Log:")
                for log_entry in results["query_log"]:
                    print(f"  [{log_entry['timestamp']}] {log_entry['status']}: "
                          f"{log_entry['result_count']} results "
                          f"({log_entry['execution_time_ms']}ms)")

        else:
            print(f"\n✗ Error processing file: {file_results.get('message', 'Unknown error')}")
            results["error"] = file_results.get("message")
    else:
        print(f"\n✗ Local VictoriaLogs file not found: {local_vlogs_file}")
        print("  Attempting direct VictoriaLogs query...")

        # Try direct query
        query = query_engine.construct_latency_query()
        print(f"\nQuery: {query}")

        # Note: Direct query would go here, but requires VictoriaLogs to be accessible
        results["error"] = "Local VictoriaLogs file not found and direct query not implemented"

    # Create output directory
    output_dir = Path("/home/coding/aide-de-camp/data/latency-metrics")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Store raw latency data
    if results["raw_data"]:
        raw_file = output_dir / "pbx-web-victorialogs-latency-raw.json"
        with open(raw_file, 'w') as f:
            json.dump({
                "service": "pbx-web",
                "source": "victorialogs",
                "time_range": {"start": start_date, "end": end_date},
                "raw_data": results["raw_data"]
            }, f, indent=2)
        print(f"\n✓ Raw latency data saved to: {raw_file}")

    # Store comprehensive results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = output_dir / f"pbx-web-victorialogs-latency-{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Comprehensive results saved to: {results_file}")

    # Store query log
    if results["query_log"]:
        query_log_file = output_dir / f"pbx-web-victorialogs-query-log-{timestamp}.json"
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


if __name__ == "__main__":
    main()
