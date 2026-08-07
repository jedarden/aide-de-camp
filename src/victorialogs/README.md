# VictoriaLogs Query Infrastructure

Complete query infrastructure for latency metrics analysis using VictoriaLogs.

## Quick Start

```python
from src.victorialogs.client import VictoriaLogsClient
from src.victorialogs.queries import PrebuiltQueries
import asyncio

async def main():
    client = VictoriaLogsClient()

    # 30-day dispatch latency analysis
    query = PrebuiltQueries.dispatch_30day_latency()
    start, end = get_time_range_days_ago(30)

    result = await client.execute_range_query(
        query=query,
        start=start,
        end=end,
        step="1d"
    )

    await client.close()

asyncio.run(main())
```

## Features

✅ **VictoriaLogs Client** - HTTP client with kubectl proxy access
✅ **Query Templates** - Pre-built LogQL templates for common latency queries
✅ **Metrics Calculator** - Percentile and statistics calculation utilities
✅ **Time Range Parameterization** - Utilities for generating query time ranges
✅ **Comprehensive Testing** - Full test suite with connectivity verification

## Installation

The module is included in `src/victorialogs/`. Dependencies:

- `httpx` - Async HTTP client
- `asyncio` - Async support
- `statistics` - Statistical calculations

## Usage Examples

### 30-Day Latency Analysis

```python
from src.victorialogs.queries import PrebuiltQueries
from src.victorialogs.client import VictoriaLogsClient, get_time_range_days_ago

async def analyze_30day():
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

### Percentile Metrics Calculation

```python
from src.victorialogs.queries import LatencyQueryTemplates

query = LatencyQueryTemplates.multi_percentile_query(
    service="adc-voice",
    field="dispatch_duration_seconds",
    percentiles=[50.0, 95.0, 99.0],
    time_filter="_time >= 30d ago"
)
```

### Processing Query Results

```python
from src.victorialogs.metrics import process_query_result

report = process_query_result(query_result)
percentiles = report['percentile_metrics']

print(f"P50: {percentiles['p50_seconds']}s")
print(f"P95: {percentiles['p95_seconds']}s")
print(f"P99: {percentiles['p99_seconds']}s")
```

## Available Query Templates

- `dispatch_30day_latency()` - Dispatch latency over 30 days
- `pbx_web_build_30day_latency()` - pbx-web build workflow duration
- `whisper_stt_build_30day_latency()` - whisper-stt build workflow duration
- `api_latency_hourly_trend(service, hours)` - Hourly API latency trend
- `error_rate_with_latency_30d(service)` - Error rate with latency analysis

## Testing

Run the comprehensive test suite:

```bash
.venv/bin/python src/victorialogs/test_victorialogs.py
```

Test coverage:
- Connectivity verification
- Query template generation
- Time range parameterization
- Metrics calculation accuracy
- Sample query execution

## Documentation

See [docs/victorialogs-query-infrastructure.md](../../docs/victorialogs-query-infrastructure.md) for complete documentation.

## Access Configuration

**Service**: vlogs-server
**Namespace**: monitoring
**Cluster**: ardenone-cluster
**Access**: kubectl proxy at `http://traefik-ardenone-cluster:8001`

## Metrics Output

```json
{
  "percentile_metrics": {
    "count": 1000,
    "p50_seconds": 0.856,
    "p95_seconds": 3.456,
    "p99_seconds": 8.901,
    "min_seconds": 0.123,
    "max_seconds": 15.789
  },
  "additional_stats": {
    "mean_seconds": 1.234,
    "median_seconds": 0.856,
    "stddev_seconds": 2.345
  },
  "data_quality": {
    "total_records": 1000,
    "success_rate": 99.5
  }
}
```

## Performance Notes

- Client timeout: 30 seconds
- Step intervals: 1h (hourly), 1d (daily) recommended for large time ranges
- Query templates are optimized for VictoriaLogs LogQL syntax

## Version

v1.0 (2026-08-07)
