# VictoriaLogs Query Infrastructure for Latency Metrics

## Overview

This module provides a comprehensive query infrastructure for accessing and analyzing latency metrics from VictoriaLogs. It includes:

- **VictoriaLogs Client**: HTTP client for querying VictoriaLogs through kubectl proxy
- **Query Templates**: Pre-built LogQL query templates for common latency analysis tasks
- **Metrics Calculator**: Utilities for calculating percentiles, statistics, and generating reports
- **Time Range Parameterization**: Utilities for generating time ranges for queries

## Architecture

```
VictoriaLogs Cluster (ardenone-cluster)
    ↓ kubectl proxy
http://traefik-ardenone-cluster:8001/api/v1/namespaces/monitoring/services/vlogs-server:9428/proxy/
    ↓
VictoriaLogsClient
    ↓
Query Templates → Metrics Calculator → Reports
```

## Installation

The module is located in `src/victorialogs/` and includes:

- `client.py` - VictoriaLogs HTTP client
- `queries.py` - Query template builders
- `metrics.py` - Metrics calculation utilities
- `test_victorialogs.py` - Test suite

## Usage

### Basic Client Usage

```python
from src.victorialogs.client import VictoriaLogsClient
import asyncio

async def main():
    client = VictoriaLogsClient()

    # Health check
    health = await client.health_check()
    print(f"Status: {health['status']}")

    # Execute instant query
    result = await client.execute_query(
        query="adc-voice | stats avg(duration_seconds)",
        time="2026-08-06T12:00:00Z"
    )

    # Execute range query
    start, end = get_time_range_days_ago(30)
    range_result = await client.execute_range_query(
        query="adc-voice | stats p95(duration_seconds)",
        start=start,
        end=end,
        step="1h"
    )

    await client.close()

asyncio.run(main())
```

### Using Prebuilt Queries

```python
from src.victorialogs.queries import PrebuiltQueries
from src.victorialogs.client import VictoriaLogsClient
import asyncio

async def main():
    client = VictoriaLogsClient()

    # 30-day dispatch latency
    query = PrebuiltQueries.dispatch_30day_latency()
    result = await client.execute_range_query(
        query=query,
        *get_time_range_days_ago(30),
        step="1d"
    )

    # Hourly API latency trend
    query = PrebuiltQueries.api_latency_hourly_trend("adc-voice", 24)
    result = await client.execute_range_query(
        query=query,
        *get_time_range_days_ago(1),
        step="1h"
    )

    await client.close()

asyncio.run(main())
```

### Custom Query Templates

```python
from src.victorialogs.queries import LatencyQueryTemplates

# Multi-percentile query
query = LatencyQueryTemplates.multi_percentile_query(
    service="adc-voice",
    field="dispatch_duration_seconds",
    percentiles=[50.0, 95.0, 99.0],
    time_filter="_time >= 30d ago"
)

# Time series query
query = LatencyQueryTemplates.latency_time_series_query(
    service="adc-voice",
    aggregation="p95",
    field="duration_seconds",
    interval="1h",
    time_filter="_time >= 7d ago"
)
```

### Processing Query Results

```python
from src.victorialogs.metrics import process_query_result

# Process query result into metrics
report = process_query_result(query_result)

# Access metrics
percentiles = report['percentile_metrics']
print(f"P50: {percentiles['p50_seconds']}s")
print(f"P95: {percentiles['p95_seconds']}s")
print(f"P99: {percentiles['p99_seconds']}s")

# Access time series data
time_series = report['time_series']['aggregates']
for bucket in time_series:
    print(f"{bucket['timestamp']}: P95={bucket['p95_seconds']}s")
```

## Query Templates

### Available Prebuilt Queries

- `dispatch_30day_latency()` - Dispatch latency over 30 days
- `pbx_web_build_30day_latency()` - pbx-web build workflow duration (30 days)
- `whisper_stt_build_30day_latency()` - whisper-stt build workflow duration (30 days)
- `api_latency_hourly_trend(service, hours)` - Hourly API latency trend
- `error_rate_with_latency_30d(service)` - Error rate combined with latency (30 days)

### Query Template Types

1. **Percentile Queries**: Calculate p50, p95, p99 percentiles
2. **Distribution Queries**: Histogram/distribution analysis
3. **Time Series Queries**: Aggregated metrics over time
4. **Workflow Queries**: Argo workflow duration analysis
5. **Multi-percentile Queries**: Multiple percentiles in single query
6. **Operation Breakdown**: Latency by operation type
7. **Error Rate Queries**: Combined error rate and latency

## Time Range Parameters

### Utility Functions

```python
from src.victorialogs.client import get_time_range_days_ago, get_time_range_custom

# Last N days
start, end = get_time_range_days_ago(30)

# Custom date range
start, end = get_time_range_custom("2026-07-01", "2026-07-31")

# QueryParameterBuilder
from src.victorialogs.queries import QueryParameterBuilder

params = QueryParameterBuilder.last_n_days(30)
params = QueryParameterBuilder.last_n_hours(24)
params = QueryParameterBuilder.last_n_minutes(60)
```

## Authentication and Access

### Access Method

VictoriaLogs is accessed through the kubectl proxy on ardenone-cluster:

```
http://traefik-ardenone-cluster:8001/api/v1/namespaces/monitoring/services/vlogs-server:9428/proxy/
```

### Prerequisites

- Access to `traefik-ardenone-cluster:8001` (Tailscale VPN required)
- kubectl configured with read-only proxy access
- VictoriaLogs service running in `monitoring` namespace

### Service Details

- **Service Name**: vlogs-server
- **Namespace**: monitoring
- **Port**: 9428
- **Access Type**: ClusterIP (via kubectl proxy)

## Metrics Output

### Percentile Metrics

```json
{
  "count": 1000,
  "p50_seconds": 0.856,
  "p75_seconds": 1.234,
  "p90_seconds": 2.1,
  "p95_seconds": 3.456,
  "p99_seconds": 8.901,
  "min_seconds": 0.123,
  "max_seconds": 15.789
}
```

### Time Series Output

```json
{
  "interval": "1h",
  "data_points": 24,
  "aggregates": [
    {
      "timestamp": "2026-08-06T00:00:00Z",
      "count": 45,
      "p50_seconds": 0.823,
      "p95_seconds": 2.1,
      "p99_seconds": 5.6
    }
  ]
}
```

### Comprehensive Report

```json
{
  "percentile_metrics": { ... },
  "additional_stats": {
    "mean_seconds": 1.234,
    "median_seconds": 0.856,
    "sum_seconds": 1234.567,
    "stddev_seconds": 2.345
  },
  "time_series": { ... },
  "data_quality": {
    "total_records": 1000,
    "error_count": 5,
    "success_rate": 99.5
  },
  "generated_at": "2026-08-06T12:34:56Z"
}
```

## Testing

Run the test suite to verify installation and connectivity:

```bash
.venv/bin/python src/victorialogs/test_victorialogs.py
```

### Test Coverage

1. **Connectivity Test**: VictoriaLogs health check
2. **Query Templates Test**: Verify all query templates generate valid LogQL
3. **Time Range Parameters Test**: Test time range generation
4. **Metrics Calculator Test**: Test percentile and statistics calculation
5. **Sample Query Test**: Execute a small test query against VictoriaLogs

## Common Use Cases

### 1. 30-Day Latency Analysis

```python
from src.victorialogs.queries import PrebuiltQueries
from src.victorialogs.client import VictoriaLogsClient, get_time_range_days_ago

async def analyze_30day_latency():
    client = VictoriaLogsClient()
    query = PrebuiltQueries.dispatch_30day_latency()
    start, end = get_time_range_days_ago(30)

    result = await client.execute_range_query(
        query=query,
        start=start,
        end=end,
        step="1d"
    )

    await client.close()
    return result
```

### 2. Hourly Latency Monitoring

```python
from src.victorialogs.queries import PrebuiltQueries

query = PrebuiltQueries.api_latency_hourly_trend("adc-voice", 24)
```

### 3. Error Rate Analysis

```python
from src.victorialogs.queries import LatencyQueryTemplates

query = LatencyQueryTemplates.error_rate_with_latency_query(
    service="adc-voice",
    latency_field="duration_seconds",
    time_filter="_time >= 7d ago"
)
```

### 4. Workflow Duration Analysis

```python
from src.victorialogs.queries import LatencyQueryTemplates

query = LatencyQueryTemplates.workflow_duration_query(
    workflow_template="pbx-web-build",
    time_filter="_time >= 30d ago"
)
```

## Performance Considerations

- **Query Timeouts**: Client timeout is set to 30 seconds
- **Rate Limits**: VictoriaLogs may have rate limits for high-frequency queries
- **Data Volume**: Large time ranges (30+ days) may return significant data
- **Step Interval**: Larger step intervals (1h, 1d) reduce data volume for range queries

## Troubleshooting

### Connection Issues

```python
# Test connectivity
health = await client.health_check()
if health['status'] != 'healthy':
    print(f"Connection issue: {health.get('error')}")
```

### Query Returns No Data

- Verify service name matches actual log entries
- Check time range parameters
- Ensure VictoriaLogs has data for the specified period
- Test with shorter time ranges first

### Percentile Calculation Issues

- Ensure latency field exists in log data
- Check data types (should be numeric)
- Verify data quality metrics in report

## Future Enhancements

Potential improvements to the infrastructure:

1. **Caching**: Add query result caching for repeated queries
2. **Batch Queries**: Support for executing multiple queries in parallel
3. **Alerting**: SLA compliance checking and alerting
4. **Export**: CSV/JSON export functionality
5. **Visualization**: Integration with dashboard systems
6. **Real-time Monitoring**: WebSocket support for real-time metrics

## Related Documentation

- [VictoriaLogs Documentation](https://docs.victoriametrics.com/VictoriaLogs/)
- [LogQL Reference](https://docs.victoriametrics.com/VictoriaLogs/LogQL/)
- [Kubectl Proxy Access](../CLAUDE.md#kubernetes-access)

## Maintenance

- **Module Location**: `src/victorialogs/`
- **Test Script**: `src/victorialogs/test_victorialogs.py`
- **Documentation**: `docs/victorialogs-query-infrastructure.md`
- **Dependencies**: httpx, asyncio, statistics

## Version History

- **v1.0** (2026-08-07): Initial implementation
  - VictoriaLogs client with kubectl proxy access
  - Query templates for common latency analysis
  - Metrics calculator with percentile support
  - Time range parameterization utilities
  - Comprehensive test suite
