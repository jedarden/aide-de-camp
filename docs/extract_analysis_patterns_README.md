# Analysis Pattern Extraction Script

## Overview

The `extract_analysis_patterns.py` script extracts detected patterns and key timestamps from log analysis files. It processes log files and their corresponding analysis JSON files to identify error patterns, OOM kills, startup issues, and performance problems.

## Usage

### Basic Usage (with metadata file)

```bash
python extract_analysis_patterns.py --metadata data/pod-log-metadata.json --output data/analysis-results.json
```

### Process Specific Log Files

```bash
python extract_analysis_patterns.py --log-files "pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log"
```

### Print to stdout (no output file)

```bash
python extract_analysis_patterns.py --metadata data/pod-log-metadata.json
```

## Command-Line Options

- `--metadata METADATA` - Path to JSON file containing log file metadata (default: `data/pod-log-metadata.json`)
- `--output OUTPUT` - Output JSON file path (default: print to stdout)
- `--log-files LOG_FILES [LOG_FILES ...]` - Specific log files to process (alternative to using metadata file)

## Output Format

The script outputs a JSON array of dictionaries, each containing:

```json
{
  "log_file_path": "pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log",
  "pod_name": "pbx-web-5ff68464d-mkn8n",
  "namespace": "pbx-web",
  "analysis_file_path": "research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json",
  "detected_patterns": ["error"],
  "key_timestamps": {
    "analysis_date": "2026-08-06T13:40:21.580554",
    "log_file": "pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log",
    "error_first": "1785277704",
    "error_last": "1785960497"
  }
}
```

### Field Descriptions

- `log_file_path` - Path to the log file
- `pod_name` - Name of the pod (from metadata, null if not provided)
- `namespace` - Kubernetes namespace (from metadata, null if not provided)
- `analysis_file_path` - Path to corresponding analysis file (null if not found)
- `detected_patterns` - Array of pattern types detected: `startup`, `oom_kill`, `error`, `performance`
- `key_timestamps` - Object containing relevant timestamps (null if no analysis file):
  - `analysis_date` - When the analysis was performed
  - `log_file` - Name of the log file
  - `<pattern>_first` - First occurrence timestamp for each pattern type
  - `<pattern>_last` - Last occurrence timestamp for each pattern type

## Pattern Detection

The script identifies four types of patterns:

1. **startup** - Application startup issues and initialization problems
2. **oom_kill** - Out of memory kills and resource exhaustion
3. **error** - General errors and exceptions
4. **performance** - Performance degradation and slow operations

## Missing Analysis Files

When an analysis file cannot be found for a log file, the script returns:

```json
{
  "log_file_path": "...",
  "pod_name": "...",
  "namespace": "...",
  "analysis_file_path": null,
  "detected_patterns": [],
  "key_timestamps": null
}
```

## Summary Statistics

The script prints summary statistics to stderr:

- Total log files processed
- Files with corresponding analysis files
- Files with detected patterns
- Pattern breakdown (count by pattern type)

## Analysis File Location

The script searches for analysis files in the `research/` directory following the pattern:

```
research/<namespace>-30days/pod-logs/<log_file_name>-analysis.json
```

For example, a log file at `pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log` would have its analysis file at:

```
research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json
```

## Requirements

- Python 3.7+
- No external dependencies (uses only standard library)

## Examples

### Example 1: Process all logs from metadata file

```bash
python extract_analysis_patterns.py --metadata data/pod-log-metadata.json --output data/all-analysis-results.json
```

Output includes pattern detection for all 24 log files referenced in the metadata.

### Example 2: Process specific log file

```bash
python extract_analysis_patterns.py --log-files "whisper-stt-30days/pod-logs/pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log"
```

Output includes pattern detection for the specified log file only.

### Example 3: Process multiple specific log files

```bash
python extract_analysis_patterns.py --log-files \
  "pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log" \
  "whisper-stt-30days/pod-logs/pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log" \
  --output data/multiple-analysis-results.json
```

## Integration with Analysis Pipeline

This script is designed to work as part of a larger log analysis pipeline:

1. Log collection → `data/<namespace>-logs.jsonl`
2. Log analysis → `research/<namespace>-30days/pod-logs/<file>-analysis.json`
3. Pattern extraction → This script (`extract_analysis_patterns.py`)
4. Results → JSON output for further processing or visualization

## Troubleshooting

### "Analysis file not found" warnings

Ensure that:
- The `research/` directory exists in the expected location
- Analysis files follow the naming convention: `<log_file_name>-analysis.json`
- The namespace in the log path matches the namespace in the research path

### Empty detected_patterns array

This indicates either:
- No patterns were detected in the analysis (clean logs)
- The analysis file has `count: 0` for all pattern types
- The analysis file is malformed or missing

### null key_timestamps

This occurs when:
- No analysis file exists for the log file
- The analysis file is malformed or cannot be read
- The analysis file has no timestamp data

## See Also

- `data/pod-log-metadata.json` - Input metadata file
- `data/analysis-patterns-extracted.json` - Example output
- `research/` - Directory containing analysis files
