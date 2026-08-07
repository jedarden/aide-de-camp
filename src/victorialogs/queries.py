"""
VictoriaLogs query templates for latency metrics.

Provides pre-built LogQL query templates for common latency analysis tasks,
including p50, p95, p99 percentiles and time range parameterization.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta


class LatencyQueryTemplates:
    """
    Query templates for latency metrics analysis.

    Supports querying latency data from various sources:
    - pbx-web: Web service latency metrics
    - whisper-stt: Speech-to-text processing latency
    - dispatch operations: Intent routing and orchestration
    - Generic HTTP request latency
    """

    # Service name mappings
    SERVICES = {
        "pbx-web": "pbx-web",
        "whisper-stt": "whisper-stt",
        "aide-de-camp": "adc-voice",
        "dispatch": "dispatch"
    }

    # Latency field mappings for different log sources
    LATENCY_FIELDS = {
        "duration": "duration_seconds",
        "response_time": "response_time_seconds",
        "latency": "latency_ms",
        "processing_time": "processing_time_seconds"
    }

    @staticmethod
    def duration_percentile_query(
        service: str,
        field: str = "duration_seconds",
        percentile: float = 95.0,
        time_filter: Optional[str] = None
    ) -> str:
        """
        Generate LogQL query for duration percentile calculation.

        Args:
            service: Service name (pbx-web, whisper-stt, etc.)
            field: Latency field to calculate percentile for
            percentile: Percentile value (50, 95, 99, etc.)
            time_filter: Optional time filter (e.g., '1d', '7d', '30d')

        Returns:
            LogQL query string
        """
        time_filter_str = f" | {time_filter}" if time_filter else ""

        query = f"""
        {service}{time_filter_str}
        | stats percentile({field}, {percentile}) as p{int(percentile)}
        """

        return query.strip()

    @staticmethod
    def latency_distribution_query(
        service: str,
        field: str = "duration_seconds",
        buckets: str = "0.1,0.5,1,2,5,10",
        time_filter: Optional[str] = None
    ) -> str:
        """
        Generate LogQL query for latency histogram/distribution.

        Args:
            service: Service name
            field: Latency field
            buckets: Comma-separated bucket boundaries
            time_filter: Optional time filter

        Returns:
            LogQL query string
        """
        time_filter_str = f" | {time_filter}" if time_filter else ""

        query = f"""
        {service}{time_filter_str}
        | stats histogram({field}, {buckets}) as latency_dist
        """

        return query.strip()

    @staticmethod
    def latency_time_series_query(
        service: str,
        aggregation: str = "avg",
        field: str = "duration_seconds",
        interval: str = "1h",
        time_filter: Optional[str] = None
    ) -> str:
        """
        Generate LogQL query for latency time series.

        Args:
            service: Service name
            aggregation: Aggregation function (avg, max, min, p50, p95, p99)
            field: Latency field
            interval: Time bucket interval (1m, 5m, 1h, 1d)
            time_filter: Optional time filter

        Returns:
            LogQL query string
        """
        time_filter_str = f" | {time_filter}" if time_filter else ""

        query = f"""
        {service}{time_filter_str}
        | stats {aggregation}({field}) by ({interval})
        """

        return query.strip()

    @staticmethod
    def workflow_duration_query(
        workflow_template: str,
        time_filter: Optional[str] = None
    ) -> str:
        """
        Generate LogQL query for Argo workflow duration analysis.

        Args:
            workflow_template: Workflow template name (e.g., pbx-web-build)
            time_filter: Optional time filter

        Returns:
            LogQL query string
        """
        time_filter_str = f" | {time_filter}" if time_filter else ""

        query = f"""
        {workflow_template}{time_filter_str}
        | stats avg(duration_seconds), p95(duration_seconds), p99(duration_seconds)
        """

        return query.strip()

    @staticmethod
    def multi_percentile_query(
        service: str,
        field: str = "duration_seconds",
        percentiles: List[float] = [50.0, 95.0, 99.0],
        time_filter: Optional[str] = None
    ) -> str:
        """
        Generate LogQL query for multiple percentiles at once.

        Args:
            service: Service name
            field: Latency field
            percentiles: List of percentile values to calculate
            time_filter: Optional time filter

        Returns:
            LogQL query string
        """
        time_filter_str = f" | {time_filter}" if time_filter else ""

        percentile_funcs = ", ".join([
            f"percentile({field}, {p}) as p{int(p)}"
            for p in percentiles
        ])

        query = f"""
        {service}{time_filter_str}
        | stats {percentile_funcs}
        """

        return query.strip()

    @staticmethod
    def latency_by_operation_query(
        service: str,
        operation_field: str = "operation",
        field: str = "duration_seconds",
        time_filter: Optional[str] = None
    ) -> str:
        """
        Generate LogQL query for latency breakdown by operation type.

        Args:
            service: Service name
            operation_field: Field containing operation name
            field: Latency field
            time_filter: Optional time filter

        Returns:
            LogQL query string
        """
        time_filter_str = f" | {time_filter}" if time_filter else ""

        query = f"""
        {service}{time_filter_str}
        | stats avg({field}), p95({field}), p99({field}) by ({operation_field})
        """

        return query.strip()

    @staticmethod
    def error_rate_with_latency_query(
        service: str,
        latency_field: str = "duration_seconds",
        time_filter: Optional[str] = None
    ) -> str:
        """
        Generate LogQL query combining error rate and latency analysis.

        Args:
            service: Service name
            latency_field: Latency field
            time_filter: Optional time filter

        Returns:
            LogQL query string
        """
        time_filter_str = f" | {time_filter}" if time_filter else ""

        query = f"""
        {service}{time_filter_str}
        | stats
            avg({latency_field}) as avg_latency,
            p95({latency_field}) as p95_latency,
            p99({latency_field}) as p99_latency,
            count() as total_requests,
            sum(status >= 400) as error_count
        """

        return query.strip()


class QueryParameterBuilder:
    """
    Helper class for building query parameters with time ranges.
    """

    @staticmethod
    def last_n_days(days: int) -> Dict[str, str]:
        """Get query parameters for last N days."""
        return {
            "time_filter": f"_time >= {days * 24}h ago"
        }

    @staticmethod
    def date_range(start_date: str, end_date: str) -> Dict[str, str]:
        """
        Get query parameters for custom date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        return {
            "start": f"{start_date}T00:00:00Z",
            "end": f"{end_date}T23:59:59Z"
        }

    @staticmethod
    def last_n_hours(hours: int) -> Dict[str, str]:
        """Get query parameters for last N hours."""
        return {
            "time_filter": f"_time >= {hours}h ago"
        }

    @staticmethod
    def last_n_minutes(minutes: int) -> Dict[str, str]:
        """Get query parameters for last N minutes."""
        return {
            "time_filter": f"_time >= {minutes}m ago"
        }


class PrebuiltQueries:
    """
    Pre-built queries for common latency analysis scenarios.
    """

    @staticmethod
    def dispatch_30day_latency() -> str:
        """Query for dispatch latency over 30 days."""
        return LatencyQueryTemplates.multi_percentile_query(
            service="adc-voice",
            field="dispatch_duration_seconds",
            percentiles=[50.0, 95.0, 99.0],
            time_filter="_time >= 30d ago"
        )

    @staticmethod
    def pbx_web_build_30day_latency() -> str:
        """Query for pbx-web build workflow duration over 30 days."""
        return LatencyQueryTemplates.workflow_duration_query(
            workflow_template="pbx-web-build",
            time_filter="_time >= 30d ago"
        )

    @staticmethod
    def whisper_stt_build_30day_latency() -> str:
        """Query for whisper-stt build workflow duration over 30 days."""
        return LatencyQueryTemplates.workflow_duration_query(
            workflow_template="whisper-stt-build",
            time_filter="_time >= 30d ago"
        )

    @staticmethod
    def api_latency_hourly_trend(service: str, hours: int = 24) -> str:
        """Query for hourly API latency trend."""
        return LatencyQueryTemplates.latency_time_series_query(
            service=service,
            aggregation="avg",
            field="duration_seconds",
            interval="1h",
            time_filter=f"_time >= {hours}h ago"
        )

    @staticmethod
    def error_rate_with_latency_30d(service: str) -> str:
        """Query for error rate combined with latency over 30 days."""
        return LatencyQueryTemplates.error_rate_with_latency_query(
            service=service,
            latency_field="duration_seconds",
            time_filter="_time >= 30d ago"
        )
