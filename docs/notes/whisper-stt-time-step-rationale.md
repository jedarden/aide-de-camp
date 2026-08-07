# Whisper-STT Time Step Size Rationale and Usage

## Overview

This document explains the rationale for the chosen 1-hour time step size used in Whisper-STT latency aggregation over 30-day windows. The step size was calculated based on actual event rate analysis from whisper-stt logs to optimize between granularity and manageability.

## Chosen Step Size: 1 Hour

**Current configuration:** `step_hours = 1` in `scripts/aggregate_whisper_stt_latency_6h.py`

### Key Metrics (30-Day Window)

- **Total buckets:** 720
- **Estimated events per bucket:** ~480
- **Granularity:** High (hourly precision)
- **Manageability:** Good (within target of <1000 buckets)
- **Coverage:** 30 days × 24 hours = 720 data points

## Rationale

### Data Analysis

The optimal step size was determined using `calculate_optimal_step_size.py`, which analyzed actual whisper-stt log data:

**Source Data (24-hour sample):**
- Total events: 11,952
- Event rate: ~480 events/hour
- Duration: 24.9 hours
- Hours with data: 26

**Calculation Methodology:**

1. Parse all timestamps from `logs/whisper-stt-raw.jsonl`
2. Calculate actual event rate (events/hour) from existing data
3. Extrapolate to 30-day window using current event rate
4. For each step size (1h, 6h, 12h, 24h):
   - Calculate total buckets: `(30 days × 24 hours) / hours_per_bucket`
   - Estimate events per bucket using current event rate
   - Evaluate manageability score
5. Recommend step size with highest granularity that meets target (<1000 buckets)

### Step Size Comparison

| Step Size | Buckets (30 days) | Events/Bucket | Granularity | Manageability | Within Target |
|-----------|-------------------|---------------|--------------|---------------|---------------|
| 1-hour    | 720               | ~480          | High         | Good          | ✅ Yes         |
| 6-hour    | 120               | ~2,880        | Medium       | Excellent     | ✅ Yes         |
| 12-hour   | 60                | ~5,760        | Medium       | Excellent     | ✅ Yes         |
| 24-hour   | 30                | ~11,520       | Low          | Excellent     | ✅ Yes         |

**Target constraint:** <1000 buckets for 30-day window

### Why 1-Hour Steps?

1. **Highest granularity** within target constraint
2. **Good manageability** (720 buckets is manageable for analysis and visualization)
3. **Sufficient data density** (~480 events per bucket ensures statistical significance)
4. **Hourly precision** enables detection of daily patterns and anomalies

### Trade-offs

**Advantages of 1-hour steps:**
- Hourly granularity reveals daily patterns (peak hours, quiet periods)
- Better anomaly detection (can isolate specific hours)
- Finer time series analysis capabilities
- Higher resolution for trend visualization

**Disadvantages of 1-hour steps:**
- Larger result set (720 vs 120 for 6-hour)
- Increased storage/processing requirements
- May be excessive for long-term trend analysis (24-hour steps suffice)

## Formula for Calculating Result Count

The number of time buckets for any step size is calculated as:

```
total_buckets = (30 days × 24 hours/day) / step_hours
total_buckets = 720 / step_hours
```

**Examples:**
- 1-hour steps: 720 / 1 = **720 buckets**
- 6-hour steps: 720 / 6 = **120 buckets**
- 12-hour steps: 720 / 12 = **60 buckets**
- 24-hour steps: 720 / 24 = **30 buckets**

## How to Adjust Step Size

### Changing Step Size

To modify the step size in the aggregation script:

**File:** `scripts/aggregate_whisper_stt_latency_6h.py`

**Line 353 (in `main()` function):**
```python
# Current: 1-hour steps
aggregator = WhisperSTTLatencyAggregator(
    start_date="2026-07-07T00:00:00Z",
    end_date="2026-08-06T23:59:59Z",
    step_hours=1  # <-- MODIFY THIS VALUE
)
```

**Line 363 (output file naming):**
```python
output_file = Path("/home/coding/aide-de-camp/data/whisper-stt-latency-aggregated-1h.json")
# Rename to reflect step size, e.g., "...-6h.json" for 6-hour steps
```

### Step Size Selection Guide

Choose step size based on your use case:

| Use Case | Recommended Step Size | Buckets | Rationale |
|----------|----------------------|---------|-----------|
| Daily pattern analysis | 1-hour | 720 | Reveals hourly trends |
| Anomaly detection | 1-hour | 720 | Precise temporal isolation |
| Weekly reporting | 6-hour | 120 | Sufficient for weekly views |
| Long-term trends | 24-hour | 30 | Best for monthly/quarterly analysis |
| Minimal storage | 24-hour | 30 | Smallest result set |
| Maximum detail | 1-hour | 720 | Highest temporal resolution |

## Example Queries with Different Step Sizes

### 1-Hour Steps (Current Configuration)

```python
aggregator = WhisperSTTLatencyAggregator(
    start_date="2026-07-07T00:00:00Z",
    end_date="2026-08-06T23:59:59Z",
    step_hours=1
)
# Expected: 720 buckets, ~480 events/bucket
```

**Output:** `data/whisper-stt-latency-aggregated-1h.json`

### 6-Hour Steps (Quarter-Day Granularity)

```python
aggregator = WhisperSTTLatencyAggregator(
    start_date="2026-07-07T00:00:00Z",
    end_date="2026-08-06T23:59:59Z",
    step_hours=6
)
# Expected: 120 buckets, ~2,880 events/bucket
```

**Output:** `data/whisper-stt-latency-aggregated-6h.json`

### 24-Hour Steps (Daily Granularity)

```python
aggregator = WhisperSTTLatencyAggregator(
    start_date="2026-07-07T00:00:00Z",
    end_date="2026-08-06T23:59:59Z",
    step_hours=24
)
# Expected: 30 buckets, ~11,520 events/bucket
```

**Output:** `data/whisper-stt-latency-aggregated-24h.json`

## Verification and Validation

To verify the chosen step size for your specific data:

```bash
# Run the step size analysis
python calculate_optimal_step_size.py

# Output: optimal-step-size-analysis.json
```

This analyzes your actual log data and provides:
- Event rate calculations
- Step size comparison table
- Manageability scoring
- Recommendation based on your data characteristics

## Re-running Analysis

If event rates change significantly (e.g., service growth or traffic pattern changes), re-run the analysis:

```bash
python calculate_optimal_step_size.py > optimal-step-size-analysis-report.txt
```

This ensures the step size remains optimal for current data volume and characteristics.

## Related Files

- `calculate_optimal_step_size.py` — Step size optimization script
- `scripts/aggregate_whisper_stt_latency_6h.py` — Aggregation implementation
- `optimal-step-size-analysis.json` — Current analysis results
- `logs/whisper-stt-raw.jsonl` — Source log data

## References

- Analysis performed on 2026-08-07
- Data source: `logs/whisper-stt-raw.jsonl` (24-hour sample)
- Event rate: 480.05 events/hour
- Target constraint: <1000 buckets for 30-day window
