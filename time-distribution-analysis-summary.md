# Time Distribution Analysis Summary

## Analysis Overview

**Generated:** 2026-08-07T06:44:41Z  
**Input:** Validated failure dataset from Child 1 (adc-4a6mb)  
**Categories Analyzed:** 6  
**Total Records:** 108,941

## Key Finding: Timestamp Availability

The validated dataset structure **does not preserve individual failure timestamps**. Most records have `timestamp: None` because:

1. The dataset was created for categorization purposes
2. Individual failure timestamps were not preserved during data aggregation
3. Only data collection timestamps are available (when data was gathered, not when failures occurred)

**Parse Statistics:**
- Total records: 108,941
- Records with valid timestamps: 23
- Records with `timestamp: None`: 108,918

This severely limits time distribution analysis - we can only analyze patterns based on data collection times, not actual failure occurrences.

## Results by Category

### 1. Uncategorized (107,279 records)
- **Valid timestamps analyzed:** 23
- **Time span:** 2026-06-14 to 2026-08-06 (53 days)
- **Time clusters found:** 8
- **Highest density cluster:** 2026-06-26T12:42:03Z to 2026-06-26T16:33:34Z
  - Duration: 3.9 hours
  - Failures: 16
  - Density: 2.67/hour

**Gap Statistics:**
- Average gap: 58.44 hours (2.4 days)
- Median gap: 0.22 hours (13 minutes)
- Min gap: 2.15 minutes
- Max gap: 25.1 days

**Weekly Distribution:**
- 2026-W24: 11 timestamps
- 2026-W26: 5 timestamps
- 2026-W27: 2 timestamps
- 2026-W28: 4 timestamps
- 2026-W32: 1 timestamp

### 2. HTTPError (1,420 records)
- **Valid timestamps analyzed:** 0
- **Status:** Cannot analyze - no timestamps available

### 3. NetworkIssue (8 records)
- **Valid timestamps analyzed:** 0
- **Status:** Cannot analyze - no timestamps available

### 4. RecordingFetchError (1 record)
- **Valid timestamps analyzed:** 0
- **Status:** Cannot analyze - no timestamps available

### 5. DependencyTimeout (12 records)
- **Valid timestamps analyzed:** 0
- **Status:** Cannot analyze - no timestamps available

### 6. DeploymentRollback (1 record)
- **Valid timestamps analyzed:** 1
- **Time span:** 2026-07-13T18:07:55Z (single occurrence)
- **Time clusters found:** 0 (insufficient data)

## Methodology

### Timestamp Parsing
Supported ISO 8601 formats:
- `2026-08-06T17:27:54Z` (basic)
- `2026-08-06T17:27:54.123Z` (with milliseconds)
- `2026-08-06T17:27:54+00:00` (with timezone)
- `2026-08-06 17:27:54` (space separator)
- `2026-08-06` (date only)

### Clustering Algorithm
- **Method:** Sliding window approach
- **Window size:** 6 hours
- **Density threshold:** 2.0 failures/hour
- **Minimum cluster size:** 2 failures

### Gap Statistics
- Calculated between consecutive sorted timestamps
- Includes mean, median, min, max, and standard deviation

## Limitations

1. **Sparse timestamp coverage:** Only 23 out of 108,941 records (0.021%) have timestamps
2. **Data collection vs. failure time:** Available timestamps reflect when data was collected, not when failures occurred
3. **Aggregate nature:** Most records represent aggregated failure counts, not individual events
4. **Category bias:** Only "uncategorized" category has sufficient timestamps for analysis

## Recommendations

To enable meaningful time distribution analysis, future data collection should:

1. **Preserve individual failure timestamps** - don't aggregate during collection
2. **Use raw log data** - analyze actual log entries with timestamps
3. **Add timestamp extraction** - parse timestamps from log message content
4. **Include timezone normalization** - ensure consistent UTC representation

## Data Quality Issues

The validated dataset structure prioritizes categorization accuracy over temporal analysis. For time-based insights, source log files (not the aggregated dataset) would be required.

## Output Files

- **Statistics:** `time-distribution-statistics.json`
- **This summary:** `time-distribution-analysis-summary.md`
- **Analysis script:** `calculate_time_distribution.py`
