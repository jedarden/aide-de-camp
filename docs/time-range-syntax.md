# Time Range Syntax and Usage

## Overview

Time range support in aide-de-camp is currently **limited** and **not fully implemented**. While the system handles time-based data filtering in some contexts, comprehensive time range parsing from user queries is not yet available.

## Current State

### What IS Supported

1. **Unix Timestamp Parameters**
   - Used in API endpoints like `/api/v1/timings/percentiles`
   - Format: `since=<unix_timestamp>` (integer seconds since epoch)
   - Example: `since=1723075200` (August 7, 2024 00:00:00 UTC)

2. **Hard-coded Limits**
   - Logs: `--tail=100` (last 100 lines only)
   - Events: Sorted by timestamp (`--sort-by='.lastTimestamp'`)
   - No dynamic time-based filtering

3. **Post-hoc Filtering**
   - 30-day windows calculated in Python scripts
   - Used in deployment analysis and validation scripts

### What is NOT Currently Implemented

- ❌ Time range parsing from user queries ("logs from the last 2 hours")
- ❌ `FetchContext` time range fields (`since`, `until`, `time_range_start`, `time_range_end`)
- ❌ Dynamic kubectl time parameters (`--since-time`, `--until-time`)
- ❌ Relative time expressions ("1 hour ago", "since yesterday")

## Time Range Formats

### Absolute Time Ranges

#### Unix Timestamps (Primary Current Method)
```python
# Calculate 30-day window
import time
since = int(time.time()) - 2592000  # 30 days in seconds
until = int(time.time()) + 86400    # 1 day ahead

# Usage in API calls
curl "http://localhost:8000/api/v1/timings/percentiles?since=1723075200"
```

#### ISO 8601 Timestamps
```python
# Format: YYYY-MM-DDTHH:MM:SSZ
from datetime import datetime, timedelta

now = datetime.now(timezone.utc)
since = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
until = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

# Example outputs:
# since: "2026-07-08T00:00:00Z"
# until: "2026-08-07T00:00:00Z"
```

### Relative Time Notations

**Currently NOT parsed by the system**, but referenced in documentation:

| Expression | Meaning | Implementation Status |
|------------|---------|----------------------|
| `30d` | 30 days | ❌ Not implemented |
| `24h` | 24 hours | ❌ Not implemented |
| `1h` | 1 hour | ❌ Not implemented |
| `last hour` | Previous 60 minutes | ❌ Not implemented |
| `since yesterday` | Since 00:00 yesterday | ❌ Not implemented |
| `1 hour ago` | 1 hour before now | ❌ Not implemented |

## 30-Day Window Specifications

### Method 1: Unix Timestamp Calculation
```python
import time
from datetime import datetime, timedelta

# Current time
now = int(datetime.now(timezone.utc).timestamp())

# 30-day window
since = now - (30 * 24 * 60 * 60)  # 30 days in seconds
until = now + (24 * 60 * 60)       # 1 day ahead

print(f"30-day window: {since} to {until}")
```

### Method 2: ISO 8601 Calculation
```python
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)
since = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
until = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

print(f"30-day window: {since} to {until}")
```

### Method 3: Date Filtering (Post-hoc)
```python
from datetime import datetime, timedelta, timezone

def filter_by_date_range(items, since_date, until_date):
    """
    Filter items by ISO 8601 creation timestamp.
    
    Uses inclusive lower bound and exclusive upper bound:
    since_date <= timestamp < until_date
    """
    filtered = []
    for item in items:
        creation_ts = item.get("metadata", {}).get("creationTimestamp", "")
        if since_date <= creation_ts < until_date:
            filtered.append(item)
    return filtered

# Usage
now = datetime.now(timezone.utc)
since = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
until = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

filtered_workflows = filter_by_date_range(all_workflows, since, until)
```

## Timezone Handling

### UTC Standardization

**All timestamps should use UTC** to ensure consistency across systems:

```python
# Correct: Explicit UTC
now = datetime.now(timezone.utc)

# Avoid: System local time (ambiguous)
now = datetime.now()  # ❌ Not recommended
```

### Kubernetes Timestamps

Kubernetes timestamps use ISO 8601 with 'Z' suffix (UTC):

```python
# Parse Kubernetes timestamp
def parse_kubernetes_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp with Z suffix."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"  # Convert Z to +00:00
    return datetime.fromisoformat(ts)

# Examples
ts1 = "2026-08-07T12:34:56Z"      # Kubernetes format
ts2 = "2026-08-07T12:34:56+00:00"  # ISO 8601 offset format
```

### Timezone Conversion

```python
from datetime import datetime, timezone, timedelta

# Convert any timezone to UTC
def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC."""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

# Usage
local_time = datetime.now()  # System local time
utc_time = to_utc(local_time)
```

## Current Usage Examples

### API Endpoint with Time Window
```python
# Get latency percentiles for the last hour
import time
since = int(time.time()) - 3600  # 1 hour ago

curl "http://localhost:8000/api/v1/timings/percentiles?since=${since}"
```

### Session Store Time Filtering
```python
# Get feedback signals since last hour
one_hour_ago = int(datetime.now(timezone.utc).timestamp()) - 3600
summary = await store.get_session_feedback_summary(
    session_id="abc123",
    since=one_hour_ago
)
```

### Deployment Analysis 30-Day Window
```python
# From deployment analysis scripts
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)
start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
end_date = now.strftime("%Y-%m-%d")

print(f"Analyzing deployments from {start_date} to {end_date}")
```

## Limitations and Workarounds

### Current Limitations

1. **No User Query Parsing**
   - Cannot extract "show me logs from the last 2 hours"
   - Cannot handle temporal expressions in natural language

2. **Hard-coded Command Limits**
   - `kubectl logs --tail=100` (fixed limit)
   - No `--since-time` or `--until-time` parameters

3. **Missing FetchContext Fields**
   - No time range parameters in fetch command data structures

### Workarounds

1. **Unix Timestamp Parameters**
   ```bash
   # Calculate timestamp externally
   SINCE=$(date -d '30 days ago' +%s)
   curl "http://localhost:8000/api/v1/timings/percentiles?since=${SINCE}"
   ```

2. **Post-processing Filters**
   ```python
   # Fetch all data, then filter in Python
   all_items = fetch_all_data()
   filtered = filter_by_timestamp(all_items, since, until)
   ```

3. **Script-level Time Windows**
   ```python
   # Calculate time windows in analysis scripts
   since = datetime.now(timezone.utc) - timedelta(days=30)
   filtered = [item for item in data if parse_date(item['created']) >= since]
   ```

## Future Implementation Guide

### To Add Full Time Range Support

1. **Extend FetchContext**
   ```python
   @dataclass
   class FetchContext:
       # existing fields...
       since: Optional[str] = None      # ISO 8601 or relative
       until: Optional[str] = None      # ISO 8601 or relative
   ```

2. **Add Time Range Parser**
   ```python
   def parse_time_range(expression: str) -> datetime:
       """Parse relative time expressions."""
       if expression.endswith("d"):
           days = int(expression[:-1])
           return datetime.now(timezone.utc) - timedelta(days=days)
       # Add more patterns...
   ```

3. **Update kubectl Commands**
   ```python
   # Instead of:
   command_template="kubectl logs --tail=100"
   
   # Use:
   command_template="kubectl logs --since-time={since}"
   ```

4. **Router Time Extraction**
   - Add temporal expression extraction to intent router
   - Populate FetchContext time range fields
   - Handle natural language time expressions

## Best Practices

### DO ✅

- **Always use UTC** for timestamp calculations
- **Use ISO 8601 format** for timestamp strings: `2026-08-07T12:34:56Z`
- **Include timezone info** in datetime objects
- **Use Unix timestamps** for API parameters
- **Validate timezone** before timestamp operations

### DON'T ❌

- **Don't use system local time** (ambiguous)
- **Don't mix timezones** in calculations
- **Don't assume 'Z' suffix** in all timestamps
- **Don't hardcode time ranges** (make them configurable)
- **Don't forget inclusive/exclusive bounds** (`since <= x < until`)

## Related Files

- `src/session/store.py` - Unix timestamp usage in latency tracking
- `src/validation/completeness.py` - Date parsing and validation
- `src/calculate_deployment_metrics.py` - 30-day window calculations
- `test_pbx_web_filtering_edge_cases.py` - Time filtering test cases
- `prompts/fetch/lookup-logs.md` - Time context in prompts (not implemented)

## Summary

**Current Status**: Time range support is **limited** to Unix timestamp parameters in API endpoints and post-hoc filtering in analysis scripts. Full time range parsing from user queries is **not implemented**.

**Recommended Approach**: Use Unix timestamps for API calls and ISO 8601 format for data storage. Calculate time windows in Python using `datetime.now(timezone.utc)` with explicit UTC timezone.