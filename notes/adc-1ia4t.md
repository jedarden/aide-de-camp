# Analysis Pattern Extraction Script (adc-1ia4t)

## Implementation

Created `/home/coding/aide-de-camp/scripts/extract_analysis_patterns.py` to extract detected patterns and key timestamps from analysis files.

## Functionality

- **Input**: Pod log metadata from `/home/coding/aide-de-camp/data/pod-log-metadata.json`
- **Processing**: For each log file, searches for corresponding analysis files in research directories
- **Output**: JSON file with extracted pattern data and timestamps

## Data Extracted

For each log file entry:
```json
{
  "log_file_path": "relative/path/to/log.log",
  "pod_name": "pod-name",
  "namespace": "namespace",
  "analysis_file_path": "relative/path/to/analysis.json",
  "detected_patterns": ["startup", "oom_kill", "error", "performance"],
  "key_timestamps": {
    "analysis_date": "2026-08-06T13:40:21.580554",
    "error_first": "1785277704",
    "error_last": "unknown",
    "log_file": "pod-name.log"
  }
}
```

## Results

- **Total log files processed**: 24
- **Analysis files found**: 18 (75% coverage)
- **Files with detected patterns**: 3 (all showing 'error' patterns)
- **Output location**: `/home/coding/aide-de-camp/data/analysis-patterns-extracted.json`

## Pattern Types

The script detects and extracts four pattern categories:
1. **startup**: Startup-related events
2. **oom_kill**: Out of memory kill events
3. **error**: Error patterns (most common in current dataset)
4. **performance**: Performance-related patterns

## Usage

```bash
# Run the script
/home/coding/aide-de-camp/.venv/bin/python scripts/extract_analysis_patterns.py

# Output is automatically saved to:
# data/analysis-patterns-extracted.json
```

## Missing Analysis Files

The script gracefully handles missing analysis files by setting:
- `analysis_file_path`: null
- `detected_patterns`: []
- `key_timestamps`: null

This ensures consistent output structure even when analysis data is unavailable.