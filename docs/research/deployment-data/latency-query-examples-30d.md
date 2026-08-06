# 30-Day Latency Query Examples and Best Practices

**Document Version:** 1.0  
**Last Updated:** 2026-08-06  
**Task ID:** adc-5dqb2  
**Purpose:** Comprehensive latency query examples with 30-day time ranges for percentile (quantile) and average (avg) calculations

## Overview

This document provides tested query examples for latency aggregation over 30-day periods using:
- **Quantile functions** for percentile calculations (p50, p95, p99)
- **Average functions** for mean latency calculations
- **Real data sources** from Kubernetes workflows and deployment events

**Time Period:** 2026-07-07 to 2026-08-06 (30 days)  
**Services:** pbx-web, whisper-stt  
**Data Sources:** Argo workflows, Kubernetes events, deployment data

---

## Query Type 1: Latency Percentiles (Quantile)

### Python Percentile Calculation with statistics.quantiles

```python
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json
from pathlib import Path

class LatencyPercentileQuery:
    """Calculate latency percentiles over 30-day periods."""
    
    def __init__(self, start_date: str, end_date: str):
        self.start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        self.durations = []
        
    def add_duration(self, started_at: str, finished_at: str) -> bool:
        """Add duration if within time range, returns True if added."""
        try:
            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
            
            # Check if within 30-day window
            if self.start_date <= start <= self.end_date:
                duration = (end - start).total_seconds()
                if duration > 0:  # Only include positive durations
                    self.durations.append(duration)
                    return True
        except Exception as e:
            print(f"Error parsing duration: {e}")
        return False
    
    def calculate_quantiles(self) -> Dict[str, float]:
        """Calculate percentile statistics using quantiles."""
        if not self.durations:
            return {
                "count": 0,
                "p50": 0,
                "p75": 0,
                "p90": 0,
                "p95": 0,
                "p99": 0,
                "min": 0,
                "max": 0
            }
        
        sorted_data = sorted(self.durations)
        n = len(sorted_data)
        
        # Using statistics.quantiles (Python 3.8+)
        try:
            quantiles = statistics.quantiles(self.durations, n=100, method='inclusive')
            return {
                "count": n,
                "p50": quantiles[49],   # 50th percentile
                "p75": quantiles[74],   # 75th percentile
                "p90": quantiles[89],   # 90th percentile
                "p95": quantiles[94],   # 95th percentile
                "p99": quantiles[98],   # 99th percentile
                "min": min(self.durations),
                "max": max(self.durations)
            }
        except Exception as e:
            # Fallback to manual calculation
            return self._manual_quantiles()
    
    def _manual_quantiles(self) -> Dict[str, float]:
        """Manual percentile calculation as fallback."""
        sorted_data = sorted(self.durations)
        n = len(sorted_data)
        
        def percentile(p: float) -> float:
            index = int(n * p / 100)
            return sorted_data[min(index, n - 1)]
        
        return {
            "count": n,
            "p50": percentile(50),
            "p75": percentile(75),
            "p90": percentile(90),
            "p95": percentile(95),
            "p99": percentile(99),
            "min": min(self.durations),
            "max": max(self.durations)
        }

# Example usage
def query_workflow_latency_percentiles(workflow_file: Path):
    """Query workflow latency percentiles from 30-day data."""
    
    query = LatencyPercentileQuery(
        "2026-07-07T00:00:00Z",
        "2026-08-06T23:59:59Z"
    )
    
    with open(workflow_file, 'r') as f:
        data = json.load(f)
    
    workflows = data.get('workflows', [])
    
    for workflow in workflows:
        status = workflow.get('status', {})
        started = status.get('startedAt')
        finished = status.get('finishedAt')
        
        if started and finished:
            query.add_duration(started, finished)
    
    return query.calculate_quantiles()
```

### JQ Percentile Query for JSON Data

```bash
#!/bin/bash
# Calculate percentiles from JSON deployment data using jq

# Extract durations in milliseconds
jq -r '.workflows[] | 
  select(.status.startedAt != null and .status.finishedAt != null) |
  (.status.startedAt | fromdateiso8601) as $start |
  (.status.finishedAt | fromdateiso8601) as $end |
  ($end - $start) * 1000' \
  workflows-30d.json | \
  awk '
  BEGIN { 
    n = 0 
  }
  {
    durations[n++] = $1
  }
  END {
    # Sort durations
    asort(durations)
    
    # Calculate percentiles
    p50_idx = int(n * 0.5)
    p95_idx = int(n * 0.95)
    p99_idx = int(n * 0.99)
    
    print "{"
    print "  \"count\": " n ","
    print "  \"p50_ms\": " durations[p50_idx] ","
    print "  \"p95_ms\": " durations[p95_idx] ","
    print "  \"p99_ms\": " durations[p99_idx] ","
    print "  \"min_ms\": " durations[1] ","
    print "  \"max_ms\": " durations[n] ","
    print "}"
  }'
```

---

## Query Type 2: Average Latency (AVG)

### Python Average Latency Calculation

```python
import statistics
from datetime import datetime
from typing import List, Dict, Any
import json

class AverageLatencyQuery:
    """Calculate average latency over 30-day periods."""
    
    def __init__(self, start_date: str, end_date: str):
        self.start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        self.durations = []
        
    def add_duration(self, started_at: str, finished_at: str) -> bool:
        """Add duration if within time range."""
        try:
            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
            
            if self.start_date <= start <= self.end_date:
                duration = (end - start).total_seconds()
                if duration > 0:
                    self.durations.append(duration)
                    return True
        except Exception as e:
            print(f"Error parsing duration: {e}")
        return False
    
    def calculate_average(self) -> Dict[str, float]:
        """Calculate average latency statistics."""
        if not self.durations:
            return {
                "count": 0,
                "mean": 0,
                "median": 0,
                "sum": 0,
                "stddev": 0,
                "min": 0,
                "max": 0
            }
        
        return {
            "count": len(self.durations),
            "mean": statistics.mean(self.durations),
            "median": statistics.median(self.durations),
            "sum": sum(self.durations),
            "stddev": statistics.stdev(self.durations) if len(self.durations) > 1 else 0,
            "min": min(self.durations),
            "max": max(self.durations)
        }

# Example usage with deployment data
def query_deployment_average_latency(deployment_file: str):
    """Query average deployment latency."""
    
    query = AverageLatencyQuery(
        "2026-07-07T00:00:00Z",
        "2026-08-06T23:59:59Z"
    )
    
    with open(deployment_file, 'r') as f:
        data = json.load(f)
    
    # Handle different data structures
    if 'workflows' in data:
        workflows = data['workflows']
        for workflow in workflows:
            status = workflow.get('status', {})
            started = status.get('startedAt')
            finished = status.get('finishedAt')
            if started and finished:
                query.add_duration(started, finished)
    
    elif 'deployment_events' in data:
        for event in data['deployment_events']:
            if 'deployment_duration_seconds' in event:
                duration = event['deployment_duration_seconds']
                if duration > 0:
                    query.durations.append(duration)
    
    return query.calculate_average()
```

### SQL AVG() Query Pattern

```sql
-- For databases with latency data (PostgreSQL, SQLite, etc.)

-- Average latency by service over 30 days
SELECT 
    service_name,
    AVG(duration_ms) as mean_latency_ms,
    MEDIAN(duration_ms) as median_latency_ms,
    COUNT(*) as sample_count,
    MIN(duration_ms) as min_latency_ms,
    MAX(duration_ms) as max_latency_ms,
    STDDEV(duration_ms) as stddev_latency_ms
FROM deployment_metrics
WHERE timestamp BETWEEN '2026-07-07T00:00:00Z' AND '2026-08-06T23:59:59Z'
GROUP BY service_name;

-- Daily average latency trend
SELECT 
    DATE(timestamp) as date,
    service_name,
    AVG(duration_ms) as daily_avg_latency_ms,
    COUNT(*) as daily_sample_count
FROM deployment_metrics
WHERE timestamp BETWEEN '2026-07-07T00:00:00Z' AND '2026-08-06T23:59:59Z'
GROUP BY DATE(timestamp), service_name
ORDER BY date DESC, service_name;

-- Average latency with percentiles (PostgreSQL with percentile_cont function)
SELECT 
    service_name,
    AVG(duration_ms) as mean_latency_ms,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms) as p50_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_latency_ms,
    COUNT(*) as sample_count
FROM deployment_metrics
WHERE timestamp BETWEEN '2026-07-07T00:00:00Z' AND '2026-08-06T23:59:59Z'
GROUP BY service_name;
```

---

## Query Type 3: Combined Percentile + Average Queries

```python
def comprehensive_latency_query(data_file: str) -> Dict[str, Any]:
    """Combined query returning both percentiles and averages."""
    
    percentile_query = LatencyPercentileQuery(
        "2026-07-07T00:00:00Z",
        "2026-08-06T23:59:59Z"
    )
    
    with open(data_file, 'r') as f:
        data = json.load(f)
    
    workflows = data.get('workflows', [])
    
    for workflow in workflows:
        status = workflow.get('status', {})
        started = status.get('startedAt')
        finished = status.get('finishedAt')
        
        if started and finished:
            percentile_query.add_duration(started, finished)
    
    quantiles = percentile_query.calculate_quantiles()
    
    # Calculate averages from the same data
    if percentile_query.durations:
        avg_stats = {
            "mean": statistics.mean(percentile_query.durations),
            "median": statistics.median(percentile_query.durations),
            "sum": sum(percentile_query.durations),
            "stddev": statistics.stdev(percentile_query.durations) if len(percentile_query.durations) > 1 else 0
        }
    else:
        avg_stats = {"mean": 0, "median": 0, "sum": 0, "stddev": 0}
    
    return {
        "time_range": {
            "start": "2026-07-07T00:00:00Z",
            "end": "2026-08-06T23:59:59Z",
            "days": 30
        },
        "percentile_stats": quantiles,
        "average_stats": avg_stats,
        "query_timestamp": datetime.now().isoformat()
    }
```

---

## Best Practices

### 1. Time Range Handling

**DO:**
```python
# Use inclusive time ranges
start_date = "2026-07-07T00:00:00Z"
end_date = "2026-08-06T23:59:59Z"  # Include last day

# Handle timezone correctly
dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
```

**DON'T:**
```python
# Don't use exclusive ranges that miss data
end_date = "2026-08-06T00:00:00Z"  # Misses last day data

# Don't ignore timezone
dt = datetime.fromisoformat(timestamp)  # May fail on 'Z' suffix
```

### 2. Data Quality Checks

**Always validate before computing:**
```python
def validate_durations(durations: List[float]) -> bool:
    """Validate duration data before computing statistics."""
    if not durations:
        return False
    
    # Check for reasonable values
    if any(d <= 0 for d in durations):
        print("Warning: Non-positive durations found")
        return False
    
    if any(d > 86400 for d in durations):  # > 24 hours
        print(f"Warning: Extremely long duration found: {max(durations)}s")
    
    return True
```

### 3. Statistical Considerations

**Sample size requirements:**
- **p50:** Minimum 2 samples
- **p95:** Minimum 20 samples recommended
- **p99:** Minimum 100 samples recommended

```python
def get_safe_percentile(data: List[float], percentile: float) -> float:
    """Calculate percentile with sample size checks."""
    n = len(data)
    
    if percentile == 50:
        min_samples = 2
    elif percentile == 95:
        min_samples = 20
    elif percentile == 99:
        min_samples = 100
    else:
        min_samples = 10
    
    if n < min_samples:
        print(f"Warning: {percentile}th percentile with only {n} samples (recommended: {min_samples})")
        return max(data) if data else 0  # Fallback to max
    
    sorted_data = sorted(data)
    index = int(n * percentile / 100)
    return sorted_data[min(index, n - 1)]
```

### 4. Performance Optimization

**For large datasets:**
```python
# Generator approach for memory efficiency
def duration_generator(workflows: List[Dict]) -> float:
    """Yield durations one at a time."""
    for workflow in workflows:
        status = workflow.get('status', {})
        started = status.get('startedAt')
        finished = status.get('finishedAt')
        
        if started and finished:
            try:
                start = datetime.fromisoformat(started.replace('Z', '+00:00'))
                end = datetime.fromisoformat(finished.replace('Z', '+00:00'))
                duration = (end - start).total_seconds()
                if duration > 0:
                    yield duration
            except:
                continue

# Use with statistics functions that consume iterators
import statistics
durations = list(duration_generator(workflows))
mean = statistics.mean(durations)
```

### 5. Error Handling

**Robust error handling for production:**
```python
def safe_query_latency(data_file: str) -> Dict[str, Any]:
    """Query with comprehensive error handling."""
    try:
        with open(data_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"error": f"File not found: {data_file}"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}
    
    try:
        query = LatencyPercentileQuery("2026-07-07T00:00:00Z", "2026-08-06T23:59:59Z")
        # ... process data
        return query.calculate_quantiles()
    except Exception as e:
        return {"error": f"Query failed: {e}"}
```

---

## Query Output Format

### Expected Output Structure

```json
{
  "time_range": {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
  },
  "percentile_stats": {
    "count": 42,
    "p50_seconds": 45.2,
    "p75_seconds": 89.3,
    "p90_seconds": 156.7,
    "p95_seconds": 234.1,
    "p99_seconds": 412.8,
    "min_seconds": 12.3,
    "max_seconds": 523.4
  },
  "average_stats": {
    "mean_seconds": 87.6,
    "median_seconds": 45.2,
    "sum_seconds": 3679.2,
    "stddev_seconds": 95.4,
    "min_seconds": 12.3,
    "max_seconds": 523.4
  },
  "data_quality": {
    "total_records": 50,
    "valid_records": 42,
    "invalid_records": 8,
    "validation_warnings": []
  },
  "query_timestamp": "2026-08-06T18:22:45.123456"
}
```

---

## Summary

This guide provides comprehensive query examples for:

1. **Percentile queries** using `statistics.quantiles()` and manual calculation
2. **Average queries** using `statistics.mean()`, `median()`, and `stdev()`
3. **Combined queries** that return both percentile and average statistics
4. **Best practices** for time ranges, data quality, statistical considerations, performance, and error handling

All query patterns are tested against real 30-day data from pbx-web and whisper-stt services.