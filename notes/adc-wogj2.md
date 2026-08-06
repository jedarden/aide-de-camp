# adc-wogj2: Design JSONL Schema for Pod-Logs Index

## Task Completion Summary

The JSONL schema for `pod-logs-index.jsonl` has been completed through dependency bead **adc-164qp** (Write pod-logs-schema.md with examples).

## Acceptance Criteria Status

✅ **All acceptance criteria met:**

1. **Document the exact JSONL schema with all required fields** - COMPLETE
   - 28 fields across 5 categories documented
   - Located in `pod-logs-schema.md`

2. **Define data types for each field** - COMPLETE
   - All fields have explicit type definitions (string, integer, array, ISO timestamp)
   - Validation rules for each type documented

3. **Map to parent bead requirements** - COMPLETE
   - Mapped to parent bead adc-1i5hf requirements
   - All required fields included: pod_name, namespace, timestamps, paths, patterns

4. **Create schema definition document** - COMPLETE
   - `pod-logs-schema.md` created (775 lines)
   - Comprehensive documentation with examples

5. **Handle edge cases** - COMPLETE
   - 10 edge cases documented:
     - Missing analysis files
     - Empty log files
     - Deleted/terminated pods
     - Missing/invalid timestamps
     - Array consistency issues
     - Null vs empty vs omitted fields
     - Unicode and special characters
     - Cross-field constraint violations
     - Additional temporal edge cases
     - Additional data quality edge cases

## Schema Structure

The schema defines 5 main categories:

1. **Pod Identification** (8 fields)
   - pod_name, namespace, pod_phase, restart_count
   - creation_timestamp, deletion_timestamp
   - container_image, node_name

2. **Log File Metadata** (5 fields)
   - log_file_path, log_size_bytes, log_line_count
   - collection_date, log_type

3. **Analysis Metadata** (2 fields)
   - analysis_file_path, analysis_date

4. **Pattern Detection** (4 categories × 3 fields = 12)
   - startup, oom_kill, error, performance
   - Each: count, timestamps[], samples[]

5. **Temporal Boundaries** (4 fields)
   - first_log_entry, last_log_entry
   - analysis_date, collection_date

## Example Entries

The schema includes 8 comprehensive example JSONL entries:
1. Complete entry with all data
2. Entry with missing analysis file
3. Entry with empty log file
4. Entry with previous log stream (pod restart)
5. Entry with Unicode characters in error messages
6. Entry with "unknown" timestamps
7. Entry with multiple pattern types
8. Minimal entry (terminated pod, no analysis)

## Validation

Schema includes:
- Type validation rules (ISO 8601 timestamps, DNS subdomain regex, container image format)
- Cross-field constraints (temporal ordering, array length consistency)
- File path reference validation
- 10 edge case handling strategies

## Commit Reference

This work was committed in:
- Commit: `ed0919d`
- Message: "docs(adc-164qp): complete pod-logs-schema.md with full schema definition, edge cases, and 8 examples"

## Dependencies Completed

This bead depended on:
- ✅ adc-2zjyp (Scan pod-logs directory structure) - COMPLETE
- ✅ adc-164qp (Write pod-logs-schema.md with examples) - COMPLETE

Both dependencies have been satisfied, making this task complete.

## Files Delivered

- `pod-logs-schema.md` - Complete schema documentation (775 lines)

## Status

**COMPLETE** - All acceptance criteria met through successful completion of dependency beads.
