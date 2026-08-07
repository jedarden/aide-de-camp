#!/usr/bin/env python3
"""
VictoriaLogs Query Templates for whisper-stt Latency Analysis

Provides ready-to-use query templates and execution functions for analyzing
whisper-stt latency metrics via VictoriaLogs.

Task: adc-1skwa
Created: 2026-08-06
"""

import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json

class VictoriaLogsLatencyClient:
    """Client for querying VictoriaLogs for whisper-stt latency metrics."""

    def __init__(self, base_url: str = "http://victorialogs.ardenone-manager:24169"):
        """
        Initialize VictoriaLogs client.

        Args:
            base_url: VictoriaLogs server URL (default: cluster-internal service)
        """
        self.base_url = base_url.rstrip('/')
        self.api_endpoint = f"{self.base_url}/select/logsql/query"

    async def execute_query(
        self,
        query: str,
        time_range_start: str = None,
        time_range_end: str = None,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Execute a LogQL query against VictoriaLogs.

        Args:
            query: LogQL query string
            time_range_start: Start time (@now()-Xh format or Unix timestamp)
            time_range_end: End time (@now() or Unix timestamp)
            timeout: Request timeout in seconds

        Returns:
            Query results as dict
        """
        params = {'query': query}

        if time_range_start:
            params['start'] = time_range_start
        if time_range_end:
            params['end'] = time_range_end

        async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
            response = await client.get(self.api_endpoint, params=params)
            response.raise_for_status()
            return response.json()


class WhisperLatencyQueryTemplates:
    """Query templates for whisper-stt latency analysis."""

    # Service identification fields
    NAMESPACE = "whisper-stt"
    CONTAINERS = ["whisper-stt", "whisper-openai"]

    # Latency-related field names (from pod-logs schema analysis)
    LATENCY_FIELDS = [
        "duration",
        "processing_time",
        "transcription_duration",
        "request_duration",
        "model_load_time",
        "queue_time"
    ]

    @staticmethod
    def basic_latency_query(time_range_days: int = 30) -> str:
        """
        Template 1: Basic Latency Query

        Filters for logs containing 'duration' in whisper-stt namespace.

        Args:
            time_range_days: Number of days to look back (default: 30)

        Returns:
            LogQL query string
        """
        return f'{{namespace="whisper-stt"}} |= "duration" @now()-{time_range_days}d -> @now()'

    @staticmethod
    def processing_duration_analysis(time_range_days: int = 7) -> str:
        """
        Template 2: Processing Duration Analysis

        Searches for processing time measurements with numeric duration filter.

        Args:
            time_range_days: Number of days to look back (default: 7)

        Returns:
            LogQL query string
        """
        return f'{{namespace="whisper-stt"}} |= "processing" |= "seconds" | line_duration > 0 @now()-{time_range_days}d -> @now()'

    @staticmethod
    def high_latency_detection(threshold_seconds: float = 5.0, time_range_hours: int = 24) -> str:
        """
        Template 3: High Latency Detection

        Identifies slow requests exceeding threshold.

        Args:
            threshold_seconds: Latency threshold in seconds (default: 5.0)
            time_range_hours: Number of hours to look back (default: 24)

        Returns:
            LogQL query string
        """
        return f'{{namespace="whisper-stt"}} |= "Slow" | duration > {threshold_seconds} @now()-{time_range_hours}h -> @now()'

    @staticmethod
    def container_specific_latency(container_name: str, time_range_hours: int = 24) -> str:
        """
        Template 4: Container-Specific Latency Comparison

        Args:
            container_name: Container name ('whisper-stt' or 'whisper-openai')
            time_range_hours: Number of hours to look back (default: 24)

        Returns:
            LogQL query string
        """
        return f'{{namespace="whisper-stt", container="{container_name}"}} |= "duration" @now()-{time_range_hours}h -> @now()'

    @staticmethod
    def structured_json_latency(time_range_days: int = 30) -> str:
        """
        Template 5: JSON Field Extraction

        Parses logs as JSON for structured field access.

        Args:
            time_range_days: Number of days to look back (default: 30)

        Returns:
            LogQL query string
        """
        return f'{{namespace="whisper-stt"}} | json | duration > 0 @now()-{time_range_days}d -> @now()'

    @staticmethod
    def error_related_latency(time_range_days: int = 7) -> str:
        """
        Template 6: Error-Related Latency Events

        Searches for timeout/slow error patterns.

        Args:
            time_range_days: Number of days to look back (default: 7)

        Returns:
            LogQL query string
        """
        return f'{{namespace="whisper-stt"}} |= "error" |= "timeout" |= "slow" @now()-{time_range_days}d -> @now()'

    @staticmethod
    def performance_pattern_aggregation(time_range_days: int = 30) -> str:
        """
        Template 7: Performance Pattern Aggregation

        Extracts performance pattern counts from analysis metadata.

        Args:
            time_range_days: Number of days to look back (default: 30)

        Returns:
            LogQL query string
        """
        return f'{{namespace="whisper-stt"}} | json | pattern_detection.performance.count > 0 @now()-{time_range_days}d -> @now()'

    @staticmethod
    def pod_level_latency_aggregation(time_range_days: int = 7) -> str:
        """
        Advanced: Pod-Level Latency Analysis

        Groups latency metrics by pod name.

        Args:
            time_range_days: Number of days to look back (default: 7)

        Returns:
            LogQL query string
        """
        return f'{{namespace="whisper-stt"}} | json | stats avg(duration) by pod_name @now()-{time_range_days}d -> @now()'

    @staticmethod
    def temporal_latency_distribution(time_range_days: int = 30) -> str:
        """
        Advanced: Temporal Distribution Analysis

        Creates histogram of latency over time.

        Args:
            time_range_days: Number of days to look back (default: 30)

        Returns:
            LogQL query string
        """
        return f'{{namespace="whisper-stt"}} |= "duration" | stats duration histogram by _time @now()-{time_range_days}d -> @now()'

    @staticmethod
    def percentile_calculation_query(time_range_days: int = 30) -> str:
        """
        Advanced: Percentile Calculation Query

        Calculates p50, p95, p99 percentiles.

        Args:
            time_range_days: Number of days to look back (default: 30)

        Returns:
            LogQL query string
        """
        return f'''{{namespace="whisper-stt"}} | json | quantile_over_time(0.50, duration) as p50, quantile_over_time(0.95, duration) as p95, quantile_over_time(0.99, duration) as p99 @now()-{time_range_days}d -> @now()'''


class TimeRangeHelper:
    """Helper for constructing VictoriaLogs time range expressions."""

    @staticmethod
    def last_hours(hours: int) -> tuple[str, str]:
        """Last N hours: ('@now()-Nh', '@now()')"""
        return f'@now()-{hours}h', '@now()'

    @staticmethod
    def last_days(days: int) -> tuple[str, str]:
        """Last N days: ('@now()-Nd', '@now()')"""
        return f'@now()-{days}d', '@now()'

    @staticmethod
    def last_minutes(minutes: int) -> tuple[str, str]:
        """Last N minutes: ('@now()-Nm', '@now()')"""
        return f'@now()-{minutes}m', '@now()'

    @staticmethod
    def absolute_range(start_timestamp: int, end_timestamp: int) -> tuple[str, str]:
        """Absolute Unix timestamps: (start, end)"""
        return str(start_timestamp), str(end_timestamp)

    @staticmethod
    def today() -> tuple[str, str]:
        """Today: ('@startOfDay()', '@now()')"""
        return '@startOfDay()', '@now()'

    @staticmethod
    def this_month() -> tuple[str, str]:
        """This month: ('@startOfMonth()', '@now()')"""
        return '@startOfMonth()', '@now()'

    @staticmethod
    def iso8601_range(start_date: str, end_date: str) -> tuple[str, str]:
        """
        ISO 8601 date range: (start_timestamp, end_timestamp)

        Args:
            start_date: ISO 8601 start date (e.g., "2026-07-07T00:00:00Z")
            end_date: ISO 8601 end date (e.g., "2026-08-06T23:59:59Z")

        Returns:
            Tuple of Unix timestamp strings
        """
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        return str(start_ts), str(end_ts)


async def query_whisper_latency_basic(days: int = 30) -> Dict[str, Any]:
    """
    Convenience function: Execute basic latency query.

    Args:
        days: Number of days to look back (default: 30)

    Returns:
        Query results as dict
    """
    client = VictoriaLogsLatencyClient()
    query = WhisperLatencyQueryTemplates.basic_latency_query(days)
    start, end = TimeRangeHelper.last_days(days)

    return await client.execute_query(query, start, end)


async def query_high_latency_events(threshold_seconds: float = 5.0, hours: int = 24) -> Dict[str, Any]:
    """
    Convenience function: Find high latency events.

    Args:
        threshold_seconds: Latency threshold in seconds
        hours: Number of hours to look back

    Returns:
        Query results with slow events
    """
    client = VictoriaLogsLatencyClient()
    query = WhisperLatencyQueryTemplates.high_latency_detection(threshold_seconds, hours)
    start, end = TimeRangeHelper.last_hours(hours)

    return await client.execute_query(query, start, end)


async def compare_container_latency(hours: int = 24) -> Dict[str, Any]:
    """
    Convenience function: Compare latency between containers.

    Args:
        hours: Number of hours to look back

    Returns:
        Dict with results from both containers
    """
    client = VictoriaLogsLatencyClient()
    start, end = TimeRangeHelper.last_hours(hours)

    results = {}
    for container in WhisperLatencyQueryTemplates.CONTAINERS:
        query = WhisperLatencyQueryTemplates.container_specific_latency(container, hours)
        results[container] = await client.execute_query(query, start, end)

    return results


async def get_latency_percentiles(days: int = 30) -> Dict[str, Any]:
    """
    Convenience function: Calculate latency percentiles.

    Args:
        days: Number of days to analyze

    Returns:
        Percentile calculation results (p50, p95, p99)
    """
    client = VictoriaLogsLatencyClient()
    query = WhisperLatencyQueryTemplates.percentile_calculation_query(days)
    start, end = TimeRangeHelper.last_days(days)

    return await client.execute_query(query, start, end)


async def get_performance_pattern_summary(days: int = 7) -> Dict[str, Any]:
    """
    Convenience function: Get performance pattern analysis.

    Args:
        days: Number of days to analyze

    Returns:
        Performance pattern detection results
    """
    client = VictoriaLogsLatencyClient()
    query = WhisperLatencyQueryTemplates.performance_pattern_aggregation(days)
    start, end = TimeRangeHelper.last_days(days)

    return await client.execute_query(query, start, end)


def validate_query_syntax(query: str) -> Dict[str, Any]:
    """
    Basic query syntax validation.

    Args:
        query: LogQL query string

    Returns:
        Validation results dict
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": []
    }

    # Check 1: Non-empty
    if not query or query.strip() == "":
        result["valid"] = False
        result["errors"].append("Query is empty")
        return result

    # Check 2: Field selection syntax
    if "{" not in query or "}" not in query:
        result["warnings"].append("Missing field selection syntax {namespace=...}")

    # Check 3: Valid operators
    valid_operators = ["=", "!=", "|=", "~", ">", "<", ">=", "<="]
    has_operator = any(op in query for op in valid_operators)
    if not has_operator:
        result["warnings"].append("No recognized operators found")

    # Check 4: Valid pipe operations
    valid_pipes = ["| json", "| stats", "| line_duration", "| unwrap"]
    has_valid_pipe = any(pipe in query for pipe in valid_pipes)
    if "|" in query and not has_valid_pipe:
        result["warnings"].append("Unrecognized pipe operation")

    # Check 5: Time range syntax
    time_range_indicators = ["@now()", "@startOfDay()", "@startOfMonth()"]
    has_time_range = any(indicator in query for indicator in time_range_indicators)
    if not has_time_range:
        result["warnings"].append("No time range specified")

    return result


def extract_time_range_from_params(params: Dict[str, Any]) -> tuple[str, str]:
    """
    Extract time range parameters from a params dict.

    Args:
        params: Dict with 'start' and 'end' keys

    Returns:
        Tuple of (start, end) time range strings
    """
    return params.get('start', '@now()-24h'), params.get('end', '@now()')


def build_latency_query(
    namespace: str = "whisper-stt",
    keyword: str = "duration",
    time_range_start: str = "@now()-30d",
    time_range_end: str = "@now()",
    filter_condition: str = "line_duration > 0"
) -> str:
    """
    Build a VictoriaLogs latency query with placeholders.

    Args:
        namespace: Kubernetes namespace (default: whisper-stt)
        keyword: Search keyword for logs (default: duration)
        time_range_start: Query start time (default: 30 days ago)
        time_range_end: Query end time (default: now)
        filter_condition: Additional filter condition (default: positive duration)

    Returns:
        Complete VictoriaLogs query string
    """
    return f'{{namespace="{namespace}"}} |= "{keyword}" | {filter_condition} @{time_range_start} -> @{time_range_end}'


# CLI usage examples
if __name__ == "__main__":
    import asyncio

    async def main():
        """Example usage of VictoriaLogs query templates."""

        print("=== whisper-stt Latency Query Examples ===\n")

        # Example 1: Basic 30-day latency query
        print("1. Basic 30-day latency query:")
        query = WhisperLatencyQueryTemplates.basic_latency_query(30)
        start, end = TimeRangeHelper.last_days(30)
        print(f"   Query: {query}")
        print(f"   Time range: {start} to {end}\n")

        # Example 2: High latency detection
        print("2. High latency detection (>5s):")
        query = WhisperLatencyQueryTemplates.high_latency_detection(5.0)
        print(f"   Query: {query}\n")

        # Example 3: Container comparison
        print("3. Container-specific latency queries:")
        for container in WhisperLatencyQueryTemplates.CONTAINERS:
            query = WhisperLatencyQueryTemplates.container_specific_latency(container)
            print(f"   {container}: {query}")
        print()

        # Example 4: JSON structured query
        print("4. JSON field extraction:")
        query = WhisperLatencyQueryTemplates.structured_json_latency()
        print(f"   Query: {query}\n")

        # Example 5: 30-day analysis
        print("5. 30-day performance pattern aggregation:")
        query = WhisperLatencyQueryTemplates.performance_pattern_aggregation()
        start, end = TimeRangeHelper.last_days(30)
        print(f"   Query: {query}")
        print(f"   Time range: {start} to {end}\n")

        # Example 6: Percentile calculation
        print("6. Latency percentile calculation:")
        query = WhisperLatencyQueryTemplates.percentile_calculation_query()
        print(f"   Query: {query}\n")

        # Query validation examples
        print("7. Query validation:")
        test_queries = [
            WhisperLatencyQueryTemplates.basic_latency_query(),
            "{namespace='whisper-stt'}",  # Invalid: wrong quote type
            "",  # Invalid: empty
        ]
        for q in test_queries:
            valid = validate_query_syntax(q)
            status = "✅ Valid" if valid['valid'] else "❌ Invalid"
            print(f"   {status}: '{q[:50]}...'")

        print("\n=== Examples complete ===")
        print("\nTo execute queries, ensure VictoriaLogs is accessible:")
        print("  kubectl --server=http://traefik-ardenone-cluster:8001 \\")
        print("    port-forward -n monitoring svc/victorialogs 24169:24169")

    asyncio.run(main())