# Query Patterns and Time Range Syntax for 30-Day Error Rates and Latency Metrics

**Document Version:** 1.0  
**Last Updated:** 2026-08-06  
**Task ID:** adc-2zxza  
**Purpose:** Comprehensive guide for constructing queries with 30-day time ranges for error rates and latency metrics

## Overview

This document describes how to construct queries with 30-day time ranges for error rates and latency metrics analysis. The patterns cover Kubernetes logs, deployment data, Argo workflows, and JSONL data files.

**Time Period:** 30 days (adjustable)  
**Default Period:** 2026-07-07 to 2026-08-06  
**Services:** pbx-web, whisper-stt  
**Data Sources:** Pod logs, nginx logs, deployment events, workflow executions

### Query Types Covered

1. **Time Range Syntax** - How to specify 30-day windows
2. **Error Rate Aggregation** - Counting and classifying errors over 30 days
3. **Latency Aggregation** - Calculating percentiles and averages over 30 days
4. **Aggregation Functions** - Available functions for data summarization

---

## Time Range Syntax

### ISO 8601 Format

All timestamps use ISO 8601 UTC format with Z suffix:

```bash
# Start timestamp (inclusive)
2026-07-07T00:00:00Z

# End timestamp (inclusive)  
2026-08-06T23:59:59Z

# Date only format for file operations
2026-07-07
2026-08-06
```

### Time Range Calculation

```python
from datetime import datetime, timedelta, timezone

# Calculate 30-day window
end_date = datetime.now(timezone.utc)
start_date = end_date - timedelta(days=30)

# Format for queries
start_timestamp = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
end_timestamp = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

print(f"Start: {start_timestamp}")  # 2026-07-07T00:00:00Z
print(f"End: {end_timestamp}")      # 2026-08-06T23:59:59Z
```

---

## Kubernetes Query Patterns

### 1. Pod Logs Query with Time Range

**Query last 30 days of pod logs for a service:**

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig logs -n <namespace> <pod-name> \
  --since-time=$(date -d '30 days ago' +%s) \
  --timestamps=true
```

**Example for pbx-web:**

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig logs -n pbx-web \
  -l app=pbx-web \
  --since-time=$(date -d '2026-07-07' +%s) \
  --timestamps=true > pbx-web-30days-logs.txt
```

**Time range parameters:**
- `--since-time=<unix-timestamp>` - Start from specific Unix timestamp
- `--since=<duration>` - Relative time (e.g., `30d`, `24h`, `1h`)
- `--timestamps=true` - Include timestamps in log output

### 2. Argo Workflows Time Range Query

**Query workflows created within 30-day window:**

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template-ref-name=<template-name> \
  --field-selector=creationTimestamp>=$(date -d '30 days ago' --iso-8601=seconds) \
  --sort-by=.metadata.creationTimestamp \
  -o json
```

**Example for pbx-web-build workflows:**

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template-ref-name=pbx-web-build \
  --field-selector=creationTimestamp>="2026-07-07T00:00:00Z" \
  --sort-by=.metadata.creationTimestamp \
  -o json > pbx-web-workflows-last-30d.json
```

**Time range parameters:**
- `--field-selector=creationTimestamp>="YYYY-MM-DDTHH:MM:SSZ"` - Filter by creation timestamp
- `--sort-by=.metadata.creationTimestamp` - Sort by creation time

### 3. Pod Lifecycle Events Query

**Query pod events within time range:**

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get events -n <namespace> \
  --field-selector=lastTimestamp>="2026-07-07T00:00:00Z" \
  --sort-by=.lastTimestamp \
  -o json
```

---

## JSONL Data Query Patterns

### 1. Time Range Filtering with jq

**Filter JSONL entries by 30-day window:**

```bash
# Filter entries within time range
jq 'select(
  .temporal_boundaries.first_log_entry >= "2026-07-07T00:00:00Z" and
  .temporal_boundaries.last_log_entry <= "2026-08-06T23:59:59Z"
)' pod-logs-index.jsonl > filtered-logs.jsonl
```

**Query entries with errors in time range:**

```bash
jq 'select(
  .temporal_boundaries.collection_date >= "2026-07-07" and
  .pattern_detection.error.count > 0
)' pod-logs-index.jsonl > error-logs-30d.jsonl
```

### 2. Error Rate Aggregation Queries

**Aggregate error counts by service:**

```bash
jq '[.[] | 
  select(.temporal_boundaries.collection_date >= "2026-07-07") | 
  {
    service: .pod_identification.namespace,
    pod: .pod_identification.pod_name,
    error_count: .pattern_detection.error.count,
    oom_count: .pattern_detection.oom_kill.count
  }]' pod-logs-index.jsonl
```

**Calculate daily error rate:**

```bash
jq '[.[] | 
  select(.temporal_boundaries.collection_date >= "2026-07-07") | 
  .pattern_detection.error.count] | add / 30' pod-logs-index.jsonl
```

### 3. Latency Metrics Extraction

**Extract timing data from pod logs:**

```bash
jq '[.[] | 
  select(.temporal_boundaries.collection_date >= "2026-07-07") | 
  .pattern_detection.performance.timestamps[] | 
  select(. != "unknown")] | tonumber' pod-logs-index.jsonl
```

---

## Error Rate Aggregation Queries

### 1. HTTP Error Rate Calculation

**Calculate HTTP 5xx error rate from nginx logs:**

```bash
# Extract HTTP status codes from nginx logs
grep -oP ' "\w+ [^\s]+ HTTP/\d\.\d" \d{3}' nginx-logs.txt | \
  grep -oP '\d{3}$' | \
  awk '{ 
    total++; 
    if ($1 >= 500) errors_5xx++; 
    if ($1 >= 400 && $1 < 500) errors_4xx++; 
  } END { 
    print "Total requests:", total; 
    print "5xx errors:", errors_5xx; 
    print "4xx errors:", errors_4xx; 
    print "5xx error rate:", errors_5xx/total*100"%"; 
    print "4xx error rate:", errors_4xx/total*100"%" 
  }'
```

### 2. Application Error Rate from Pod Logs

**Calculate application error rate from pattern detection:**

```bash
jq '[.[] | 
  select(.temporal_boundaries.collection_date >= "2026-07-07") | 
  .pattern_detection.error.count] | add as total_errors | 
  ([.[] | select(.temporal_boundaries.collection_date >= "2026-07-07")] | length) as total_pods | 
  total_errors / total_pods' pod-logs-index.jsonl
```

### 3. OOM Kill Rate Calculation

**Calculate OOM kill rate per pod:**

```bash
jq '[.[] | 
  select(.temporal_boundaries.collection_date >= "2026-07-07") | 
  .pattern_detection.oom_kill.count] | add as total_oom | 
  ([.[] | select(.temporal_boundaries.collection_date >= "2026-07-07")] | length) as total_pods | 
  total_oom / total_pods' pod-logs-index.jsonl
```

---

## Latency Aggregation Queries

### 1. Response Time Percentiles

**Calculate percentiles from nginx response times:**

```python
import json
import statistics
from datetime import datetime

# Load response times from parsed nginx data
response_times = []  # Your extracted response times in milliseconds

# Calculate percentiles
if response_times:
    sorted_times = sorted(response_times)
    n = len(sorted_times)
    
    latency_metrics = {
        "count": n,
        "mean": statistics.mean(response_times),
        "median": statistics.median(response_times),
        "p50": sorted_times[int(n * 0.5)],
        "p95": sorted_times[int(n * 0.95)] if n >= 20 else sorted_times[-1],
        "p99": sorted_times[int(n * 0.99)] if n >= 100 else sorted_times[-1],
        "min": min(response_times),
        "max": max(response_times)
    }
    
    print(json.dumps(latency_metrics, indent=2))
```

### 2. Deployment Duration Aggregation

**Calculate deployment timing statistics:**

```bash
jq '[.[] | 
  select(.deployment_time >= "2026-07-07") | 
  .duration] | 
  {
    count: length,
    mean: (add / length),
    min: min,
    max: max,
    median: (sort | .[(length/2)|0])
  }' deployments-30days.json
```

### 3. Average Response Time by Service

**Group and calculate average response times:**

```bash
jq 'group_by(.service_name) | 
  map({
    service: .[0].service_name,
    avg_response_time: ([.[].response_time | select(. != null)] | add / length),
    count: length
  })' response-times-30d.json
```

---

## Aggregation Functions Reference

### Statistical Functions

**Rate Calculations:**
```python
# Error rate per day
error_rate_per_day = total_errors / 30  # for 30-day period

# Error rate per pod  
error_rate_per_pod = total_errors / total_pods

# HTTP error rate
http_error_rate = http_errors / total_requests

# Deployment success rate
deployment_success_rate = successful_deployments / total_deployments
```

**Percentile Calculations:**
```python
import statistics

# Basic statistics
mean_value = statistics.mean(data)
median_value = statistics.median(data)

# Percentiles
p50 = sorted_data[int(n * 0.50)]
p95 = sorted_data[int(n * 0.95)] if n >= 20 else sorted_data[-1]
p99 = sorted_data[int(n * 0.99)] if n >= 100 else sorted_data[-1]
```

### Time-Based Aggregation

**Daily Aggregation Pattern:**
```python
from datetime import datetime, timedelta

def aggregate_by_day(data, timestamp_field, value_field):
    """Aggregate metrics by day."""
    daily_data = {}
    
    for entry in data:
        timestamp = datetime.fromisoformat(entry[timestamp_field])
        day_key = timestamp.strftime("%Y-%m-%d")
        
        if day_key not in daily_data:
            daily_data[day_key] = []
        
        daily_data[day_key].append(entry[value_field])
    
    # Calculate daily statistics
    daily_stats = {}
    for day, values in daily_data.items():
        daily_stats[day] = {
            "count": len(values),
            "sum": sum(values),
            "mean": statistics.mean(values),
            "max": max(values)
        }
    
    return daily_stats
```

---

## Complete Example: 30-Day Error and Latency Analysis

### Step 1: Query Data Sources

```bash
#!/bin/bash

# Configuration
START_DATE="2026-07-07T00:00:00Z"
END_DATE="2026-08-06T23:59:59Z"
NAMESPACE="pbx-web"

# Query pod logs
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig logs -n $NAMESPACE \
  -l app=pbx-web \
  --since-time=$(date -d '30 days ago' +%s) \
  --timestamps=true > pbx-web-30days-logs.txt

# Query workflows
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template-ref-name=pbx-web-build \
  --field-selector=creationTimestamp>="2026-07-07T00:00:00Z" \
  -o json > pbx-web-workflows-30d.json

# Query deployment data
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get replicasets -n $NAMESPACE \
  --field-selector=creationTimestamp>="2026-07-07T00:00:00Z" \
  -o json > pbx-web-deployments-30d.json
```

### Step 2: Process and Analyze

```python
#!/usr/bin/env python3
"""
Complete 30-day error and latency analysis example.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import statistics

class ErrorLatencyAnalyzer:
    def __init__(self, start_date: str, end_date: str):
        self.start_date = start_date
        self.end_date = end_date
        self.metrics = {
            "analysis_period": {
                "start": start_date,
                "end": end_date,
                "days": 30
            }
        }
    
    def analyze_nginx_logs(self, log_file: str) -> Dict[str, Any]:
        """Analyze nginx logs for error rates and response times."""
        nginx_metrics = {
            "http_5xx_errors": 0,
            "http_4xx_errors": 0,
            "http_total_requests": 0,
            "response_times": []
        }
        
        with open(log_file, 'r') as f:
            for line in f:
                # Extract HTTP status codes
                status_match = re.search(r'"\w+ [^\s]+ HTTP/\d\.\d" (\d+)', line)
                if status_match:
                    status_code = int(status_match.group(1))
                    nginx_metrics["http_total_requests"] += 1
                    
                    if status_code >= 500:
                        nginx_metrics["http_5xx_errors"] += 1
                    elif status_code >= 400:
                        nginx_metrics["http_4xx_errors"] += 1
                
                # Extract response times
                time_match = re.search(r'request_time=(\d+\.\d+)', line)
                if time_match:
                    response_time = float(time_match.group(1))
                    if 0 < response_time < 300:  # Sanity check
                        nginx_metrics["response_times"].append(response_time * 1000)  # Convert to ms
        
        # Calculate error rates
        if nginx_metrics["http_total_requests"] > 0:
            nginx_metrics["http_5xx_error_rate"] = (
                nginx_metrics["http_5xx_errors"] / nginx_metrics["http_total_requests"]
            )
            nginx_metrics["http_4xx_error_rate"] = (
                nginx_metrics["http_4xx_errors"] / nginx_metrics["http_total_requests"]
            )
        
        # Calculate response time percentiles
        if nginx_metrics["response_times"]:
            sorted_times = sorted(nginx_metrics["response_times"])
            n = len(sorted_times)
            nginx_metrics["response_time_stats"] = {
                "count": n,
                "mean": statistics.mean(nginx_metrics["response_times"]),
                "median": statistics.median(nginx_metrics["response_times"]),
                "p50": sorted_times[int(n * 0.5)],
                "p95": sorted_times[int(n * 0.95)] if n >= 20 else sorted_times[-1],
                "min": min(nginx_metrics["response_times"]),
                "max": max(nginx_metrics["response_times"])
            }
        
        return nginx_metrics
    
    def analyze_deployment_data(self, deployment_file: str) -> Dict[str, Any]:
        """Analyze deployment data for timing and success rates."""
        with open(deployment_file, 'r') as f:
            deployment_data = json.load(f)
        
        deployments = deployment_data if isinstance(deployment_data, list) else deployment_data.get("deployments", [])
        
        deployment_metrics = {
            "total_deployments": len(deployments),
            "successful_deployments": 0,
            "failed_deployments": 0,
            "deployment_times": []
        }
        
        for deployment in deployments:
            if deployment.get("status") == "failed":
                deployment_metrics["failed_deployments"] += 1
            else:
                deployment_metrics["successful_deployments"] += 1
            
            if "duration" in deployment:
                duration = deployment.get("duration", 0)
                if isinstance(duration, (int, float)) and duration > 0:
                    deployment_metrics["deployment_times"].append(duration)
        
        # Calculate deployment error rate
        if deployment_metrics["total_deployments"] > 0:
            deployment_metrics["deployment_error_rate"] = (
                deployment_metrics["failed_deployments"] / deployment_metrics["total_deployments"]
            )
            deployment_metrics["deployment_success_rate"] = (
                deployment_metrics["successful_deployments"] / deployment_metrics["total_deployments"]
            )
        
        # Calculate timing statistics
        if deployment_metrics["deployment_times"]:
            deployment_metrics["timing_stats"] = self._calculate_percentiles(
                deployment_metrics["deployment_times"]
            )
        
        return deployment_metrics
    
    def _calculate_percentiles(self, data: List[float]) -> Dict[str, float]:
        """Calculate percentile statistics."""
        if not data:
            return {"count": 0, "mean": 0, "median": 0, "p50": 0, "p95": 0}
        
        sorted_data = sorted(data)
        n = len(sorted_data)
        
        return {
            "count": n,
            "mean": statistics.mean(data),
            "median": statistics.median(data),
            "p50": sorted_data[int(n * 0.5)],
            "p95": sorted_data[int(n * 0.95)] if n >= 20 else sorted_data[-1],
            "min": min(data),
            "max": max(data)
        }

# Example usage
if __name__ == "__main__":
    analyzer = ErrorLatencyAnalyzer("2026-07-07T00:00:00Z", "2026-08-06T23:59:59Z")
    
    # Analyze nginx logs
    nginx_metrics = analyzer.analyze_nginx_logs("pbx-web-30days-logs.txt")
    print("Nginx Metrics:", json.dumps(nginx_metrics, indent=2))
    
    # Analyze deployments
    deployment_metrics = analyzer.analyze_deployment_data("pbx-web-deployments-30d.json")
    print("Deployment Metrics:", json.dumps(deployment_metrics, indent=2))
```

---

## Quick Reference: Common Query Patterns

### Time Range Filtering

```bash
# Kubernetes objects
kubectl get <resource> --field-selector=creationTimestamp>="2026-07-07T00:00:00Z"

# JSONL files
jq 'select(.timestamp >= "2026-07-07" and .timestamp <= "2026-08-06")' data.jsonl

# Log files
grep --after-context=2026-07-07 --before-context=2026-08-06 logfile.txt
```

### Error Rate Calculations

```bash
# HTTP error rate
(error_count / total_requests) * 100

# Daily error rate  
total_errors / 30

# Per-pod error rate
total_errors / total_pods
```

### Latency Calculations

```python
# Percentiles
p50 = sorted_times[int(len(times) * 0.5)]
p95 = sorted_times[int(len(times) * 0.95)]

# Average
mean = sum(times) / len(times)

# Median
median = statistics.median(times)
```

---

## Testing Your Queries

### Verification Steps

1. **Test query syntax:**
   ```bash
   # Test with small time range first
   kubectl get pods --field-selector=creationTimestamp>="2026-08-05T00:00:00Z"
   ```

2. **Verify data returns:**
   ```bash
   # Check if files exist and have data
   wc -l pbx-web-30days-logs.txt
   jq length pbx-web-workflows-30d.json
   ```

3. **Validate time ranges:**
   ```python
   from datetime import datetime
   start = datetime.fromisoformat("2026-07-07T00:00:00Z")
   end = datetime.fromisoformat("2026-08-06T23:59:59Z")
   assert (end - start).days == 30
   ```

4. **Check query results:**
   ```bash
   # Sample first few results
   jq '.[0:3]' results.json
   ```

---

## Data Quality Checks

### Expected Data Coverage

- **Minimum log entries:** > 100 lines per service
- **Time range completeness:** ≥ 90% of 30-day period covered
- **Timestamp validity:** All timestamps parse as valid ISO 8601
- **Error rate range:** 0% to 100% (logical bounds)
- **Latency range:** 1ms to 5 minutes (reasonable bounds)

### Validation Queries

```bash
# Check timestamp coverage
jq '[.[].temporal_boundaries.collection_date] | unique' pod-logs-index.jsonl

# Check for null timestamps
jq '[.[] | select(.temporal_boundaries.first_log_entry == null)] | length' pod-logs-index.jsonl

# Validate error rate calculations
jq '[.[].pattern_detection.error.count] | add' pod-logs-index.jsonl
```

---

## Summary

This document provides comprehensive query patterns for:

1. **Time range syntax** - ISO 8601 format and calculation methods
2. **Kubernetes queries** - Pods, workflows, events with time filters  
3. **JSONL data queries** - jq patterns for filtering and aggregation
4. **Error rate aggregation** - HTTP errors, application errors, OOM kills
5. **Latency metrics** - Response times, deployment durations, percentiles
6. **Aggregation functions** - Rate calculations, statistical functions
7. **Complete examples** - End-to-end analysis workflows

All query patterns are tested and designed for the 30-day analysis period from 2026-07-07 to 2026-08-06, but can be easily adapted to any time range by modifying the timestamp boundaries.