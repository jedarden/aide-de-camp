# Date Filter Calculation for 30-Day Window

## Task Summary
Calculate and format the date 30 days ago from 2026-08-06 for use in kubectl field selectors.

## Calculation Method

### Using GNU date command
```bash
date -d "2026-08-06 - 30 days" +"%Y-%m-%dT%H:%M:%SZ"
```

### Result
**2026-07-07T00:00:00Z**

## kubectl Field Selector Usage

The formatted date can be used in kubectl field selectors to filter resources by creation time:

```bash
# Get pods created in the last 30 days
kubectl get pods --field-selector=metadata.creationTimestamp>2026-07-07T00:00:00Z

# Get workflows created in the last 30 days  
kubectl get workflows -n argo-workflows --field-selector=metadata.creationTimestamp>2026-07-07T00:00:00Z

# Get jobs created in the last 30 days
kubectl get jobs --field-selector=metadata.creationTimestamp>2026-07-07T00:00:00Z
```

## Date Format Details

- **Format**: RFC3339 / ISO 8601
- **Pattern**: `YYYY-MM-DDTHH:MM:SSZ`
- **Example**: `2026-07-07T00:00:00Z`
- **Time component**: Set to midnight (00:00:00Z) to capture all activity from the start of that day

## Alternative Methods

### Python (datetime module)
```python
from datetime import datetime, timedelta
date_30_days_ago = (datetime(2026, 8, 6) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
print(date_30_days_ago)  # 2026-07-07T00:00:00Z
```

### Python (for current date)
```python
from datetime import datetime, timedelta
date_30_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
```

## Verification

The calculation is verified:
- Start date: 2026-08-06
- Subtract 30 days: 2026-07-07
- July has 31 days, so the calculation is straightforward
- Formatted as RFC3339: 2026-07-07T00:00:00Z
