# Time Range Syntax Documentation (adc-5jt1x)

## Task Summary

Enhanced the comprehensive documentation of time range syntax used in query methods for specifying 30-day windows.

## Work Completed

### 1. Enhanced Existing Documentation

Updated `/home/coding/aide-de-camp/docs/query-patterns-and-time-ranges.md` with a comprehensive **"Time Zone Considerations"** section including:

- **UTC as Standard Time Zone**: All timestamps use UTC with explicit timezone-aware datetime objects
- **ISO 8601 UTC Timestamp Format**: Format specification with `Z` suffix for UTC timezone
- **Time Zone-Aware datetime Objects**: Correct vs incorrect patterns for handling timezones in Python
- **Parsing ISO 8601 Timestamps**: Functions for parsing timestamps with explicit UTC timezone handling
- **Timezone-Aware Comparisons**: Pattern for filtering data with timezone-aware datetime comparisons
- **Time Zone Best Practices**: 5 key best practices for working with timezones
- **Common Time Zone Pitfalls**: Examples of common mistakes and how to avoid them
- **Kubernetes Time Zone Handling**: How Kubernetes timestamps are handled
- **Time Zone Testing**: Testing procedures for timezone handling

### 2. Cross-Reference Documentation

Updated `/home/coding/aide-de-camp/docs/metrics-infrastructure-summary.md` to reference the comprehensive query patterns documentation.

## Documentation Coverage

The existing documentation already covered:

✅ **Basic Time Range Syntax Format** - ISO 8601 timestamp format with start/end dates  
✅ **Examples of 30-Day Time Range Expressions** - Fixed and relative time range construction  
✅ **Time Zone Considerations** - Enhanced with explicit timezone handling best practices  
✅ **Relative vs Absolute Time Syntax** - Method 1 (fixed) vs Method 2 (relative to current date)

## Key Files Updated

1. `docs/query-patterns-and-time-ranges.md` - Added 150+ lines of timezone documentation
2. `docs/metrics-infrastructure-summary.md` - Added cross-reference to comprehensive query patterns

## Technical Details

### Time Zone Best Practices Documented

1. **Always use UTC for storage** - Store all timestamps in UTC timezone
2. **Use timezone-aware datetime objects** - Never use naive datetime objects  
3. **Explicitly parse with timezone** - When reading timestamps, always ensure timezone info
4. **Include 'Z' suffix** - When formatting timestamps, use 'Z' to indicate UTC
5. **Validate timezone before comparisons** - Ensure both objects have timezone info before comparing

### Format Examples

```python
# ISO 8601 UTC Format
ANALYSIS_PERIOD = {
    "start": "2026-07-07T00:00:00Z",    # Start date (inclusive)
    "end": "2026-08-06T23:59:59Z",       # End date (inclusive)
    "days": 30                           # Duration in days
}

# Timezone-aware parsing
def parse_utc_timestamp(timestamp_str: str) -> datetime:
    ts_clean = timestamp_str.rstrip('Z')
    dt = datetime.fromisoformat(ts_clean)
    return dt.replace(tzinfo=timezone.utc)
```

## Commit Details

- **Commit**: `3bb442a` 
- **Message**: "docs(adc-5jt1x): enhance time range syntax documentation with timezone considerations"
- **Files Changed**: 2 files, 188 insertions(+), 1 deletion(-)

## Status

✅ **COMPLETE** - All acceptance criteria met:

1. ✅ Documented basic time range syntax format
2. ✅ Provided examples of 30-day time range expressions  
3. ✅ Documented time zone considerations
4. ✅ Explained relative vs absolute time syntax

The documentation provides comprehensive coverage of time range syntax for queries with a focus on timezone best practices and common pitfalls.
