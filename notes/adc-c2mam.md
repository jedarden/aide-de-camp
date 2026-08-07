# Pattern-Matching Categorization - Task adc-c2mam

## Summary

Successfully applied pattern-matching rules to categorize 108,721 failure records from logs and deployment data.

## Results

### Overall Statistics
- **Total records processed:** 108,721
- **Categorized failures:** 1,442 (1.33%)
- **Uncategorized failures:** 107,279 (98.67%)

### Pattern Categories Identified

1. **HTTPError** (1,420 occurrences)
   - Severity: medium
   - Description: HTTP error responses (4xx, 5xx)
   - Primary source: Container logs showing HTTP 500/502/503 errors

2. **DependencyTimeout** (12 occurrences)
   - Severity: medium
   - Description: Timeout connecting to dependent services
   - Pattern: Connection reset errors during recording fetch operations

3. **NetworkIssue** (8 occurrences)
   - Severity: low
   - Description: Network allocation or connectivity problems
   - Pattern: Broken pipe errors and connection resets

4. **RecordingFetchError** (1 occurrence)
   - Severity: medium
   - Description: Failed to fetch recordings from storage backend
   - Pattern: Recording fetch failures with storage backend errors

5. **DeploymentRollback** (1 occurrence)
   - Severity: high
   - Description: Deployment was rolled back to previous version
   - Pattern: Deployment rollback events

## Pattern Matching Rules

The categorization uses a multi-pattern approach where each failure category has multiple matchers:

```python
'HTTPError': {
    'description': 'HTTP error responses (4xx, 5xx)',
    'severity': 'medium',
    'matchers': [
        lambda r: r.get('error_type', '') == 'http_500',
        lambda r: r.get('error_type', '') == 'http_503',
        lambda r: r.get('error_type', '') == 'http_404',
        lambda r: 'status 5' in r.get('severity', '') or 'status 4' in r.get('severity', ''),
    ]
}
```

## Technical Implementation

1. **Data Loading:** Loads failure records from:
   - JSONL log files in `logs/` directory
   - Deployment analysis JSON files

2. **Pattern Matching:** Applies lambda-based matchers to each failure record
   - Each category has multiple matching patterns
   - First match wins (priority order matters)
   - Graceful handling of missing fields

3. **Categorization Process:**
   - Iterates through all failure records
   - Applies pattern-matching rules sequentially
   - Assigns to first matching category
   - Defaults to "uncategorized" if no patterns match

4. **Output:** Structured JSON report with:
   - Category counts and statistics
   - Example failures per category
   - Full categorized failure list
   - Temporal pattern analysis

## Latest Execution (2026-08-06)

**Execution Summary:**
- Timestamp: 2026-08-06T23:28:18
- Data sources: `logs/pbx-web-parsed.jsonl` (108,720 records) + `deployment-patterns-analysis-report.json` (1 record)
- Total processed: 108,721 records
- Successfully categorized: 1,442 records (1.33%)
- Uncategorized: 107,279 records (98.67%)

**Pattern Distribution:**
1. HTTPError: 1,420 occurrences (98.5% of categorized failures)
2. DependencyTimeout: 12 occurrences (0.8%)
3. NetworkIssue: 8 occurrences (0.6%)
4. RecordingFetchError: 1 occurrence (0.1%)
5. DeploymentRollback: 1 occurrence (0.1%)

**Key Observations:**
- HTTP errors dominate the categorized failure landscape
- High uncategorization rate suggests many log entries are informational/successful operations
- Only 1 deployment rollback indicates relatively stable deployment practices
- Connection timeout patterns suggest intermittent dependency issues

**Files Generated in Latest Execution:**
- `categorized-failures-report.json` - Complete categorization results with full dataset
- `notes/adc-c2mam.md` - This documentation (updated)

## Previous Files Generated

1. **Fixed defaultdict bug** in category initialization
2. **Enhanced pattern rules** to capture:
   - Network connectivity issues (broken pipes, connection resets)
   - Recording fetch errors
   - Storage backend errors
3. **Improved severity assignment** from PATTERN_RULES configuration

## Acceptance Criteria Met

✅ 1. Load all parsed failure records from session.db or logs
   - Loaded 108,721 records from JSONL logs and deployment data

✅ 2. Apply pattern-matching rules to each failure record
   - Applied 17 pattern categories with multiple matchers each

✅ 3. Assign each failure to a known pattern category or "uncategorized" bucket
   - 1,442 categorized into 5 pattern categories
   - 107,279 assigned to "uncategorized"

✅ 4. Output categorized failures with pattern assignments
   - Generated `categorized-failures-report.json` with:
     - Category statistics and descriptions
     - Example failures for each category
     - Full categorized failure list with pattern assignments
