# Time Range Examples - Practical Usage

This file provides practical, copy-paste examples for working with time ranges in aide-de-camp.

## Quick Reference

### 30-Day Window (Most Common)

```python
from datetime import datetime, timedelta, timezone

# Method 1: Calculate window bounds
now = datetime.now(timezone.utc)
since = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ") 
until = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

# Method 2: Unix timestamps (for API calls)
since_ts = int(now.timestamp()) - (30 * 24 * 60 * 60)
until_ts = int(now.timestamp()) + (24 * 60 * 60)

print(f"ISO 8601: {since} to {until}")
print(f"Unix timestamps: {since_ts} to {until_ts}")
```

### Other Common Windows

```python
# 24 hours (1 day)
since_24h = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

# 7 days (1 week)
since_7d = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

# 1 hour
since_1h = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

# 15 minutes
since_15m = (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
```

## Filtering Examples

### Filter Kubernetes Workflows by Date

```python
from datetime import datetime, timedelta, timezone
import json

def filter_workflows_by_date(workflows, days_back=30):
    """Filter workflows to last N days."""
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    filtered = []
    for wf in workflows:
        created = wf.get("metadata", {}).get("creationTimestamp", "")
        if since <= created < until:
            filtered.append(wf)
    
    return filtered

# Usage
all_workflows = json.loads(open("workflows.json").read())
recent_workflows = filter_workflows_by_date(all_workflows, days_back=30)
print(f"Found {len(recent_workflows)} workflows in last 30 days")
```

### Filter List of Items by Time Window

```python
from datetime import datetime, timedelta, timezone

def filter_items_by_time(items, time_field="created_at", days_back=30):
    """Filter any list of dicts with timestamp fields."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days_back)).timestamp()
    
    filtered = []
    for item in items:
        timestamp = item.get(time_field)
        if timestamp and timestamp >= cutoff:
            filtered.append(item)
    
    return filtered

# Usage with different data structures
recent_events = filter_items_by_time(kubernetes_events, "lastTimestamp", days_back=1)
recent_logs = filter_items_by_time(log_entries, "timestamp", days_back=7)
recent_deployments = filter_items_by_time(deployments, "created_at", days_back=30)
```

### Filter with Date Objects

```python
from datetime import datetime, timedelta, timezone

def filter_by_date_objects(items, start_date, end_date):
    """Filter using datetime objects instead of strings."""
    filtered = []
    for item in items:
        created_str = item.get("created")
        if created_str:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if start_date <= created <= end_date:
                filtered.append(item)
    return filtered

# Usage
now = datetime.now(timezone.utc)
start = now - timedelta(days=30)
end = now + timedelta(days=1)

filtered_items = filter_by_date_objects(all_items, start, end)
```

## API Usage Examples

### Latency Percentiles with Time Window

```bash
# Get percentiles for last hour
#!/bin/bash
SINCE=$(python3 -c "import time; print(int(time.time()-3600))")
curl "http://localhost:8000/api/v1/timings/percentiles?since=${SINCE}"

# Get percentiles for last 24 hours
SINCE=$(python3 -c "import time; print(int(time.time()-86400))")
curl "http://localhost:8000/api/v1/timings/percentiles?since=${SINCE}"
```

### Python API Usage

```python
import httpx
from datetime import datetime, timedelta, timezone

async def get_latency_percentiles(days_back=30):
    """Get latency percentiles for time window."""
    now = datetime.now(timezone.utc)
    since_ts = int((now - timedelta(days=days_back)).timestamp())
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/v1/timings/percentiles",
            params={"since": since_ts}
        )
        return response.json()

# Usage
percentiles = await get_latency_percentiles(days_back=30)
print(f"Router p50: {percentiles['router_ms']['p50']}ms")
```

## Session Store Examples

### Get Recent Feedback Signals

```python
from datetime import datetime, timedelta, timezone

async def get_recent_signals(store, session_id, hours_back=24):
    """Get feedback signals from last N hours."""
    cutoff = int((datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp())
    
    summary = await store.get_session_feedback_summary(
        session_id=session_id,
        since=cutoff
    )
    
    return summary

# Usage
recent_signals = await get_recent_signals(store, "session-123", hours_back=1)
print(f"Signal counts: {recent_signals['signal_counts']}")
```

### Get Active Topics (Time-based)

```python
from datetime import datetime, timedelta, timezone

async def get_recent_active_topics(store, hours_back=1):
    """Get topics active in last N hours."""
    cutoff = int((datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp())
    
    # Custom query would be needed - this is conceptual
    # The existing get_active_topic_ids uses 1-hour cutoff
    active_ids = await store.get_active_topic_ids()
    
    return active_ids

# Usage
recent_topics = await get_recent_active_topics(store, hours_back=2)
```

## Timezone Conversion Examples

### Convert Local Time to UTC

```python
from datetime import datetime, timezone, timedelta

def local_to_utc(local_dt):
    """Convert local datetime to UTC."""
    if local_dt.tzinfo is None:
        # Assume system local timezone
        local_dt = local_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return local_dt.astimezone(timezone.utc)

# Usage
local_time = datetime(2026, 8, 7, 14, 30)  # 2:30 PM local time
utc_time = local_to_utc(local_time)
print(f"Local: {local_time} -> UTC: {utc_time}")
```

### Parse Various Timestamp Formats

```python
from datetime import datetime, timezone

def parse_any_timestamp(ts: str) -> datetime:
    """Parse various timestamp formats to datetime with UTC."""
    
    # Format 1: ISO 8601 with Z suffix
    if ts.endswith("Z"):
        return datetime.fromisoformat(ts[:-1] + "+00:00")
    
    # Format 2: ISO 8601 with offset
    if "+" in ts or ts[-6:-5] in ("-", "+"):
        return datetime.fromisoformat(ts)
    
    # Format 3: Date only
    if "T" not in ts:
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    
    raise ValueError(f"Unknown timestamp format: {ts}")

# Test cases
timestamps = [
    "2026-08-07T14:30:00Z",
    "2026-08-07T14:30:00+00:00",
    "2026-08-07T14:30:00-05:00",
    "2026-08-07",
]

for ts in timestamps:
    dt = parse_any_timestamp(ts)
    print(f"{ts} -> {dt}")
```

## Deployment Analysis Examples

### 30-Day Deployment Coverage Check

```python
from datetime import datetime, timedelta, timezone

def check_30day_coverage(deployments):
    """Check if we have deployments for all days in 30-day window."""
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=30)).date()
    end_date = now.date()
    
    # Generate expected dates
    expected_dates = set()
    current = start_date
    while current <= end_date:
        expected_dates.add(current)
        current += timedelta(days=1)
    
    # Extract actual dates from deployments
    actual_dates = set()
    for deployment in deployments:
        created_str = deployment.get("created")
        if created_str:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            actual_dates.add(created.date())
    
    # Find missing dates
    missing_dates = expected_dates - actual_dates
    
    coverage = len(actual_dates) / len(expected_dates) * 100
    print(f"Coverage: {coverage:.1f}% ({len(actual_dates)}/{len(expected_dates)} days)")
    
    if missing_dates:
        print(f"Missing dates: {sorted(missing_dates)}")
    
    return missing_dates

# Usage
deployments = json.loads(open("deployments.json").read())
missing = check_30day_coverage(deployments)
```

### Calculate Deployment Frequency

```python
from datetime import datetime, timedelta, timezone

def calculate_deployment_frequency(deployments, days_back=30):
    """Calculate deployments per day in time window."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)
    
    # Filter deployments in window
    recent_deployments = []
    for deployment in deployments:
        created_str = deployment.get("created")
        if created_str:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created >= cutoff:
                recent_deployments.append(created)
    
    # Calculate frequency
    frequency = len(recent_deployments) / days_back
    print(f"Deployment frequency: {frequency:.2f} per day")
    print(f"Total deployments in last {days_back} days: {len(recent_deployments)}")
    
    return frequency

# Usage
frequency = calculate_deployment_frequency(deployments, days_back=30)
```

## Utility Functions

### Time Window Generator

```python
from datetime import datetime, timedelta, timezone
from typing import Tuple

def get_time_window(days_back: int = 30) -> Tuple[str, str]:
    """Get ISO 8601 time window for last N days.
    
    Returns:
        Tuple of (since, until) timestamps
    """
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return since, until

# Usage
since, until = get_time_window(days_back=30)
print(f"Window: {since} to {until}")
```

### Unix Timestamp Generator

```python
from datetime import datetime, timedelta, timezone
from typing import Tuple

def get_unix_window(days_back: int = 30) -> Tuple[int, int]:
    """Get Unix timestamp window for last N days.
    
    Returns:
        Tuple of (since_ts, until_ts) timestamps
    """
    now = datetime.now(timezone.utc)
    since_ts = int((now - timedelta(days=days_back)).timestamp())
    until_ts = int((now + timedelta(days=1)).timestamp())
    return since_ts, until_ts

# Usage
since_ts, until_ts = get_unix_window(days_back=30)
print(f"Window: {since_ts} to {until_ts}")
```

### Time Range Validator

```python
from datetime import datetime

def validate_time_range(since: str, until: str) -> bool:
    """Validate that time range is well-formed and chronological."""
    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        return since_dt < until_dt
    except ValueError:
        return False

# Usage
is_valid = validate_time_range("2026-08-07T00:00:00Z", "2026-08-08T00:00:00Z")
print(f"Valid time range: {is_valid}")
```

## Common Patterns

### Pattern 1: Filter → Process → Report

```python
from datetime import datetime, timedelta, timezone

def analyze_time_series(data, days_back=30):
    """Complete time series analysis workflow."""
    # Step 1: Calculate time window
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)
    
    # Step 2: Filter data
    filtered = [item for item in data 
                if datetime.fromisoformat(item["created"]) >= cutoff]
    
    # Step 3: Process data
    stats = {
        "count": len(filtered),
        "avg_per_day": len(filtered) / days_back,
        "latest": max(item["created"] for item in filtered),
        "earliest": min(item["created"] for item in filtered)
    }
    
    # Step 4: Report
    print(f"Analysis for last {days_back} days:")
    print(f"  Total items: {stats['count']}")
    print(f"  Average per day: {stats['avg_per_day']:.2f}")
    print(f"  Time range: {stats['earliest']} to {stats['latest']}")
    
    return stats

# Usage
stats = analyze_time_series(all_data, days_back=30)
```

### Pattern 2: Batch Processing with Progress

```python
from datetime import datetime, timedelta, timezone
import sys

def process_time_batches(data, batch_days=7):
    """Process data in time batches with progress reporting."""
    now = datetime.now(timezone.utc)
    
    # Create 30-day window in batches
    batches = []
    for i in range(0, 30, batch_days):
        batch_start = now - timedelta(days=30-i)
        batch_end = now - timedelta(days=30-(i+batch_days))
        batches.append((batch_start, batch_end))
    
    # Process each batch
    for i, (start, end) in enumerate(batches):
        print(f"Processing batch {i+1}/{len(batches)}: {start.date()} to {end.date()}")
        
        batch_data = [item for item in data 
                      if start <= datetime.fromisoformat(item["created"]) < end]
        
        print(f"  Found {len(batch_data)} items")
        # Process batch_data here...
    
# Usage
process_time_batches(all_data, batch_days=7)
```

## Troubleshooting

### Debug Time Zone Issues

```python
from datetime import datetime, timezone, timedelta

def debug_timestamp(ts: str):
    """Debug timestamp parsing and timezone issues."""
    print(f"Original: {ts}")
    
    # Try different parsing methods
    try:
        if ts.endswith("Z"):
            dt = datetime.fromisoformat(ts[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(ts)
        
        print(f"Parsed: {dt}")
        print(f"Timezone: {dt.tzinfo}")
        print(f"UTC: {dt.astimezone(timezone.utc)}")
        print(f"Unix timestamp: {int(dt.timestamp())}")
        
        return dt
    except Exception as e:
        print(f"Error: {e}")
        return None

# Usage
debug_timestamp("2026-08-07T14:30:00Z")
debug_timestamp("2026-08-07T14:30:00-05:00")
```

### Validate Time Window Coverage

```python
def validate_time_window(items, time_field, days_back=30):
    """Validate that items cover expected time window."""
    from datetime import datetime, timedelta, timezone
    
    now = datetime.now(timezone.utc)
    expected_start = now - timedelta(days=days_back)
    
    # Find earliest and latest timestamps
    timestamps = []
    for item in items:
        ts_str = item.get(time_field)
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                timestamps.append(ts)
            except:
                pass
    
    if not timestamps:
        print("ERROR: No valid timestamps found")
        return False
    
    earliest = min(timestamps)
    latest = max(timestamps)
    
    print(f"Time window validation:")
    print(f"  Expected start: {expected_start}")
    print(f"  Actual start: {earliest}")
    print(f"  Actual end: {latest}")
    print(f"  Coverage: {(latest - earliest).days} days")
    
    if earliest > expected_start:
        print("  WARNING: Data doesn't cover full expected window")
        return False
    
    return True

# Usage
validate_time_window(deployments, "created", days_back=30)
```

These examples should cover most common time range usage patterns in aide-de-camp. Adapt them to your specific needs!