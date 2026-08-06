# Task adc-20tux: Parse and Filter Workflows by Last 30 Days

## Task Summary
Process raw kubectl JSON output and filter workflows to only include those from the last 30 days (2026-07-07 to 2026-08-06).

## Implementation

### Input Data
- **Source**: `/home/coding/scratch/all-workflows.json`
- **Format**: kubectl JSON output (WorkflowList API)
- **Total workflows**: 29

### Filtering Logic
```python
cutoff_date = '2026-07-07'  # 30 days before 2026-08-06
filter: metadata.creationTimestamp >= cutoff_date
```

### Results
- **Total workflows (before filtering)**: 29
- **Filtered workflows (last 30 days)**: 29
- **Workflows removed (older than 30 days)**: 0

### Date Range Verification
- **Oldest workflow**: 2026-07-27T18:59:34Z
- **Newest workflow**: 2026-08-06T11:33:53Z
- **All workflows within the 30-day window**: Yes

## Files Created
1. **filter_workflows_30days.py** - Main filtering script
   - Parses kubectl JSON output
   - Filters by creation timestamp
   - Outputs summary statistics and filtered data

2. **notes/adc-20tux-workflows-filtered.json** - Filtered results
   - Contains all 29 workflows (all within date range)
   - Includes metadata: cutoff date, counts, filtered items

## Acceptance Criteria Met
✓ Parse kubectl JSON output (list of workflows)
✓ Calculate 30-day cutoff date: 2026-07-07 (from current date 2026-08-06)
✓ Filter workflows where metadata.creationTimestamp >= cutoff date
✓ Output count of workflows before and after filtering

## Notes
The dataset contained 29 workflows, all created between 2026-07-27 and 2026-08-06, which means all workflows fall within the specified 30-day window. No workflows were removed by the filter.
