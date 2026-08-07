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

class VictoriaLogsClient:
    """Client for querying VictoriaLogs for whisper-stt latency metrics."""

    def __init__(self, base_url: str = "http://vlogs-server.monitoring.svc.cluster.local:9428"):
        """
        Initialize VictoriaLogs client.

        Args:
            base_url: VictoriaLogs server URL (default: cluster-internal service)
        """
        self.base_url = base_url.rstrip('/')
        self.api_endpoint = f"{self.base_url}/select/logicql"

    async def execute_query(
        self,
        query: str,
        time_range_start: str,
        time_range_end: str,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Execute a LogicQL query against VictoriaLogs.

        Args:
            query: LogicQL query string
            time_range_start: Start time (@now()-Xh format or Unix timestamp)
            time_range_end: End time (@now() or Unix timestamp)
            timeout: Request timeout in seconds

        Returns:
            Query results as dict
        """
        params = {
            'query': query,
            'start': time_range_start,
            'end': time_range_end
        }

        async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
            response = await client.get(self.api_endpoint, params=params)
            response.raise_for_status()
            return response.json()


class WhisperLatencyQueries:
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
    def basic_latency_query(time_range_hours: int = 24) -> str:
        """
        Template 1: Basic Latency Query

        Filters for logs containing 'duration' in whisper-stt namespace.
        """
        return f'{{namespace="whisper-stt"}} |= "duration"'

    @staticmethod
    def processing_duration_analysis(time_range_days: int = 7) -> str:
        """
        Template 2: Processing Duration Analysis

        Searches for processing time measurements with numeric duration filter.
        """
        return '{namespace="whisper-stt"} |= "processing" |= "seconds" | line_duration > 0'

    @staticmethod
    def high_latency_detection(threshold_seconds: float = 5.0) -> str:
        """
        Template 3: High Latency Detection

        Identifies slow requests exceeding threshold.
        """
        return f'{{namespace="whisper-stt"}} |= "Slow" | duration > {threshold_seconds}'

    @staticmethod
    def container_specific_latency(container_name: str) -> str:
        """
        Template 4: Container-Specific Latency Comparison

        Args:
            container_name: 'whisper-stt' or 'whisper-openai'
        """
        return f'{{namespace="whisper-stt", container="{container_name}"}} |= "duration"'

    @staticmethod
    def structured_json_latency() -> str:
        """
        Template 5: JSON Field Extraction

        Parses logs as JSON for structured field access.
        """
        return '{namespace="whisper-stt"} | json | duration > 0'

    @staticmethod
    def error_related_latency() -> str:
        """
        Template 6: Error-Related Latency Events

        Searches for timeout/slow error patterns.
        """
        return '{namespace="whisper-stt"} |= "error" |= "timeout" |= "slow"'

    @staticmethod
    def performance_pattern_aggregation() -> str:
        """
        Template 7: Performance Pattern Aggregation

        Extracts performance pattern counts from analysis metadata.
        """
        return '{namespace="whisper-stt"} | json | pattern_detection.performance.count > 0'

    @staticmethod
    def pod_level_latency_aggregation() -> str:
        """
        Advanced: Pod-Level Latency Analysis

        Groups latency metrics by pod name.
        """
        return '{namespace="whisper-stt"} | json | stats avg(duration) by pod_name'

    @staticmethod
    def temporal_latency_distribution() -> str:
        """
        Advanced: Temporal Distribution Analysis

        Creates histogram of latency over time.
        """
        return '{namespace="whisper-stt"} |= "duration" | stats duration histogram by _time'


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


async def query_whisper_latency_basic(hours: int = 24) -> Dict[str, Any]:
    """
    Convenience function: Execute basic latency query.

    Args:
        hours: Number of hours to look back (default: 24)

    Returns:
        Query results as dict
    """
    client = VictoriaLogsClient()
    query = WhisperLatencyQueries.basic_latency_query(hours)
    start, end = TimeRangeHelper.last_hours(hours)

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
    client = VictoriaLogsClient()
    query = WhisperLatencyQueries.high_latency_detection(threshold_seconds)
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
    client = VictoriaLogsClient()
    start, end = TimeRangeHelper.last_hours(hours)

    results = {}
    for container in WhisperLatencyQueries.CONTAINERS:
        query = WhisperLatencyQueries.container_specific_latency(container)
        results[container] = await client.execute_query(query, start, end)

    return results


async def get_performance_pattern_summary(days: int = 7) -> Dict[str, Any]:
    """
    Convenience function: Get performance pattern analysis.

    Args:
        days: Number of days to analyze

    Returns:
        Performance pattern detection results
    """
    client = VictoriaLogsClient()
    query = WhisperLatencyQueries.performance_pattern_aggregation()
    start, end = TimeRangeHelper.last_days(days)

    return await client.execute_query(query, start, end)


# Validation helper functions
def validate_query_syntax(query: str) -> bool:
    """
    Basic query syntax validation.

    Args:
        query: LogicQL query string

    Returns:
        True if query appears valid, False otherwise
    """
    # Check for basic structure
    if not query or query.strip() == "":
        return False

    # Check for required operators
    valid_operators = ["=", "!=", "|=", "~", ">", "<", ">=", "<="]
    has_operator = any(op in query for op in valid_operators)

    # Check for field selection syntax
    has_field_selection = "{" in query and "}" in query

    # Check for pipe operations
    valid_pipes = ["| json", "| stats", "| line_duration"]
    has_valid_pipe = any(pipe in query for pipe in valid_pipes)

    return has_field_selection or has_operator or has_valid_pipe


def extract_time_range_from_params(params: Dict[str, Any]) -> tuple[str, str]:
    """
    Extract time range parameters from a params dict.

    Args:
        params: Dict with 'start' and 'end' keys

    Returns:
        Tuple of (start, end) time range strings
    """
    return params.get('start', '@now()-24h'), params.get('end', '@now()')


# CLI usage examples
if __name__ == "__main__":
    import asyncio

    async def main():
        """Example usage of VictoriaLogs query templates."""

        print("=== whisper-stt Latency Query Examples ===\n")

        # Example 1: Basic 24-hour latency query
        print("1. Basic 24-hour latency query:")
        query = WhisperLatencyQueries.basic_latency_query(24)
        start, end = TimeRangeHelper.last_hours(24)
        print(f"   Query: {query}")
        print(f"   Time range: {start} to {end}\n")

        # Example 2: High latency detection
        print("2. High latency detection (>5s):")
        query = WhisperLatencyQueries.high_latency_detection(5.0)
        print(f"   Query: {query}\n")

        # Example 3: Container comparison
        print("3. Container-specific latency queries:")
        for container in WhisperLatencyQueries.CONTAINERS:
            query = WhisperLatencyQueries.container_specific_latency(container)
            print(f"   {container}: {query}")
        print()

        # Example 4: JSON structured query
        print("4. JSON field extraction:")
        query = WhisperLatencyQueries.structured_json_latency()
        print(f"   Query: {query}\n")

        # Example 5: 30-day analysis
        print("5. 30-day performance pattern aggregation:")
        query = WhisperLatencyQueries.performance_pattern_aggregation()
        start, end = TimeRangeHelper.last_days(30)
        print(f"   Query: {query}")
        print(f"   Time range: {start} to {end}\n")

        # Query validation examples
        print("6. Query validation:")
        test_queries = [
            WhisperLatencyQueries.basic_latency_query(),
            "{namespace='whisper-stt'}",  # Invalid: wrong quote type
            "",  # Invalid: empty
        ]
        for q in test_queries:
            valid = validate_query_syntax(q)
            print(f"   '{q[:50]}...' : {'✅ Valid' if valid else '❌ Invalid'}")

        print("\n=== Examples complete ===")
        print("\nTo execute queries, ensure VictoriaLogs is accessible:")
        print("  kubectl --server=http://traefik-ardenone-cluster:8001 \\")
        print("    port-forward -n monitoring svc/vlogs-server 9428:9428")

    asyncio.run(main())