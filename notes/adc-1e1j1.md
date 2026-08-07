# Time Step Granularity Configuration for 30-Day Whisper-STT Latency Aggregation

## Executive Summary

**Configured Time Step:** `6h` (6 hours)  
**Total Buckets for 30-day window:** 120  
**Estimated Records per Bucket:** ~879 (average)  
**Estimated Result Count:** 120 data points

## Data Volume Analysis

### Current Data Characteristics
Based on analysis of `logs/whisper-stt-raw.jsonl`:

```
Total Records:     96,419 records
Time Span:         27.4 days (658.1 hours)
Records per Day:   ~3,516
Records per Hour:  ~147
Records per Minute: ~2.4
```

### Hourly Distribution
Data is well-distributed across hours:
- Peak hours (14:00-17:00, 20:00): ~4,320 records each
- Average hour: ~147 records
- No significant temporal gaps

## Time Step Options Comparison

| Step Size | Buckets (30 days) | Records/Bucket | Total Results | Pros | Cons |
|-----------|-------------------|----------------|---------------|------|------|
| 1 hour    | 720               | ~147           | 720           | Fine-grained, hourly patterns | Too many data points, storage heavy |
| **6 hours** | **120**        | **~879**       | **120**       | **Balanced, daily patterns, good stats** | Slightly coarser than hourly |
| 12 hours  | 60                | ~1,758         | 60            | Compact, high-level trends | Misses intra-day variation |
| 1 day     | 30                | ~3,516         | 30            | Most compact | Too coarse for latency spikes |

## Recommended Configuration: 6-Hour Steps

### Rationale

1. **Statistical Significance**: ~879 records per bucket provides robust percentile calculations (p50, p95, p99)

2. **Temporal Resolution**: 4 data points per day captures:
   - Morning patterns (00:00-06:00)
   - Daytime patterns (06:00-12:00)
   - Afternoon patterns (12:00-18:00)
   - Evening patterns (18:00-24:00)

3. **Result Manageability**: 120 data points is:
   - Easy to visualize on time-series charts
   - Manageable for storage and processing
   - Sufficient for trend analysis and anomaly detection

4. **Storage Efficiency**: Compared to hourly (720 points), 6-hour steps reduce storage by 83% while maintaining meaningful patterns

### VictoriaLogs Query Configuration

```python
# Step parameter for VictoriaLogs aggregation
STEP_SIZE = "6h"  # 6-hour buckets

# Query construction
query = f"""
SELECT
    quantile_over_time(0.50, processing_duration) as p50,
    quantile_over_time(0.95, processing_duration) as p95,
    quantile_over_time(0.99, processing_duration) as p99
FROM "{vlogs_url}"
WHERE
    (app='whisper-stt' OR kubernetes.namespace_name='whisper-stt')
    AND _time >= '{start_date}'
    AND _time <= '{end_date}'
STEP {STEP_SIZE}
"""
```

### Expected Output Structure

```json
{
  "time_buckets": [
    {
      "timestamp": "2026-07-07T00:00:00Z",
      "window": "2026-07-07T00:00:00Z - 2026-07-07T06:00:00Z",
      "record_count": 879,
      "latency_metrics": {
        "p50_seconds": 1.234,
        "p95_seconds": 2.456,
        "p99_seconds": 3.789
      }
    },
    // ... 119 more buckets (total 120)
  ],
  "aggregation_metadata": {
    "step_size": "6h",
    "total_buckets": 120,
    "expected_records_per_bucket": 879,
    "time_range": {
      "start": "2026-07-07T00:00:00Z",
      "end": "2026-08-06T23:59:59Z"
    }
  }
}
```

## Implementation Example

```python
#!/usr/bin/env python3
"""
Whisper-STT Latency Aggregation with 6-Hour Time Steps
"""

from datetime import datetime, timedelta
import json
from collections import defaultdict

class WhisperSTTLatencyAggregator:
    """Aggregate whisper-stt latency metrics into 6-hour time buckets."""
    
    def __init__(self, start_date: str, end_date: str, step_hours: int = 6):
        self.start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        self.step_hours = step_hours
        
        # Calculate total buckets
        total_seconds = (self.end_date - self.start_date).total_seconds()
        self.total_buckets = int(total_seconds / (step_hours * 3600)) + 1
        
        # Initialize buckets
        self.buckets = []
        current = self.start_date
        while current <= self.end_date:
            bucket_end = current + timedelta(hours=step_hours)
            self.buckets.append({
                "window_start": current.isoformat(),
                "window_end": bucket_end.isoformat(),
                "latencies": []
            })
            current = bucket_end
    
    def add_record(self, timestamp: str, latency: float):
        """Add a latency record to the appropriate bucket."""
        ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        
        for bucket in self.buckets:
            bucket_start = datetime.fromisoformat(bucket["window_start"])
            bucket_end = datetime.fromisoformat(bucket["window_end"])
            
            if bucket_start <= ts < bucket_end:
                bucket["latencies"].append(latency)
                break
    
    def calculate_bucket_metrics(self, bucket: dict) -> dict:
        """Calculate latency metrics for a single bucket."""
        latencies = bucket["latencies"]
        
        if not latencies:
            return {
                "record_count": 0,
                "p50": None,
                "p95": None,
                "p99": None
            }
        
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)
        
        import statistics
        
        try:
            quantiles = statistics.quantiles(sorted_latencies, n=100, method='inclusive')
            return {
                "record_count": n,
                "p50": round(quantiles[49], 3),
                "p95": round(quantiles[94], 3),
                "p99": round(quantiles[98], 3),
                "mean": round(statistics.mean(sorted_latencies), 3),
                "min": round(min(sorted_latencies), 3),
                "max": round(max(sorted_latencies), 3)
            }
        except Exception:
            return {"error": "Insufficient data for percentiles"}
    
    def get_aggregated_results(self) -> dict:
        """Return aggregated results with metrics for all buckets."""
        results = {
            "aggregation_metadata": {
                "step_size": f"{self.step_hours}h",
                "step_hours": self.step_hours,
                "total_buckets": self.total_buckets,
                "time_range": {
                    "start": self.start_date.isoformat(),
                    "end": self.end_date.isoformat()
                },
                "expected_records_per_bucket": 879,
                "generated_at": datetime.now().isoformat()
            },
            "time_buckets": []
        }
        
        for bucket in self.buckets:
            metrics = self.calculate_bucket_metrics(bucket)
            
            results["time_buckets"].append({
                "window": f"{bucket['window_start']} - {bucket['window_end']}",
                "window_start": bucket["window_start"],
                "window_end": bucket["window_end"],
                "metrics": metrics
            })
        
        return results


# Usage example
if __name__ == "__main__":
    start_date = "2026-07-07T00:00:00Z"
    end_date = "2026-08-06T23:59:59Z"
    
    aggregator = WhisperSTTLatencyAggregator(start_date, end_date, step_hours=6)
    
    # Add sample records
    # aggregator.add_record("2026-07-07T01:00:00Z", 1.234)
    # aggregator.add_record("2026-07-07T02:00:00Z", 1.456)
    
    results = aggregator.get_aggregated_results()
    
    print(json.dumps(results, indent=2))
```

## Verification Checklist

- [x] **Step Size Configured**: 6-hour steps (`STEP_SIZE = "6h"`)
- [x] **Bucket Count Calculated**: 120 buckets for 30-day window
- [x] **Result Count Estimated**: 120 data points (manageable for visualization)
- [x] **Records per Bucket**: ~879 average (statistically significant)
- [x] **Temporal Resolution**: 4 points per day (captures daily patterns)
- [x] **Storage Efficiency**: 83% reduction vs hourly (720 buckets)
- [x] **Documentation Complete**: Rationale, examples, and configuration provided

## Next Steps

1. **Implement aggregation logic** in query scripts using 6-hour steps
2. **Test with sample data** to verify bucket distribution
3. **Validate output format** matches expected structure
4. **Update production queries** with configured step parameter
5. **Create visualizations** using 120-point time-series data

## References

- Data source: `/home/coding/aide-de-camp/logs/whisper-stt-raw.jsonl`
- VictoriaLogs endpoint: `http://victorialogs.ardenone-manager:24169`
- Analysis date: 2026-08-06
- Task: adc-1e1j1
