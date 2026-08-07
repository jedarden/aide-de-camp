# Log Extraction Test Script

## Overview

`test_log_extraction.py` is a comprehensive test script that runs extraction functions on multiple log files and validates the results. It supports testing various log extraction functions with formatted output in either table or JSON format.

## Features

- ✅ **Single file testing**: Test extraction on individual log files
- ✅ **Directory batch testing**: Process all log files in a directory recursively
- ✅ **Multiple extraction functions**: Test different extraction strategies
- ✅ **Multiple output formats**: Table (human-readable) or JSON (machine-readable)
- ✅ **Error handling**: Graceful error reporting for missing files and parsing errors
- ✅ **Performance tracking**: Execution time tracking for each extraction
- ✅ **Summary statistics**: Overall success/failure rates

## Available Extraction Functions

| Function | Description | File Types |
|----------|-------------|------------|
| `pod_metadata` | Extract pod metadata including timestamps and file size | .log, .txt |
| `log_file_metadata` | Extract log file metadata (size, timestamps, deletion info) | .log, .txt, .json |
| `deployment_metadata` | Extract deployment metadata from JSON files | .json, .jsonl |
| `failure_patterns` | Extract failure pattern counts from log content | .log, .txt |

## Usage Examples

### Test a single file
```bash
python test_log_extraction.py logs/pbx-web-nginx.log
```

### Test all log files in a directory
```bash
python test_log_extraction.py --directory logs/
```

### Test specific extraction functions
```bash
python test_log_extraction.py --directory logs/ --functions pod_metadata deployment_metadata
```

### Output as JSON
```bash
python test_log_extraction.py --directory logs/ --format json
```

### Save output to file
```bash
python test_log_extraction.py --directory logs/ --format table --output extraction_results.txt
python test_log_extraction.py --directory logs/ --format json --output extraction_results.json
```

### Test only failure pattern extraction
```bash
python test_log_extraction.py --directory logs/ --functions failure_patterns
```

## Command-Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `file` | - | Path to a single log file to test |
| `--directory` | `-d` | Path to directory containing log files |
| `--functions` | `-f` | Extraction functions to run (default: all) |
| `--format` | - | Output format: `table` or `json` (default: table) |
| `--output` | `-o` | Output file path (default: stdout) |
| `--help` | `-h` | Show help message and exit |

## Output Formats

### Table Format (Default)

Human-readable output with:
- Summary statistics (total, successful, failed)
- Per-file results with status indicators (✓/✗)
- Extracted data fields
- Error messages for failed extractions
- Execution time in milliseconds

```
========================================================================================================================
LOG EXTRACTION TEST RESULTS - 2026-08-06T23:27:03.758332
========================================================================================================================

Total extractions: 2
Successful: 2 (100%)
Failed: 0 (0%)

📄 pbx-web-30day.json
   Path: logs/pbx-web-30day.json

   ✓ deployment_metadata (0.1ms)
      analysis_period: last 30 days (2026-07-07 to 2026-08-06)
      cluster: ardenone-cluster
      extraction_function: deployment_metadata
      namespace: pbx-web
```

### JSON Format

Machine-readable output with structured data:
```json
{
  "timestamp": "2026-08-06T23:27:34.010061",
  "summary": {
    "total_extractions": 58,
    "successful": 58,
    "failed": 0
  },
  "results": [
    {
      "file_path": "logs/pbx-web-nginx.log",
      "function_name": "failure_patterns",
      "success": true,
      "execution_time_ms": 27.39,
      "data": {
        "total_lines": 1000,
        "error": 5,
        "failed": 3
      }
    }
  ]
}
```

## Error Handling

The script handles various error conditions gracefully:

- **Missing files**: Reports "File not found" error
- **Missing directories**: Shows "No log files found" warning
- **Parsing errors**: Returns error message with exception type
- **Invalid JSON**: Reports "Invalid JSON" with parse error details
- **Unknown functions**: Reports "Unknown function" error

Exit codes:
- `0`: All extractions successful
- `1`: One or more extractions failed

## Integration with CI/CD

The script can be integrated into CI/CD pipelines for automated log validation:

```bash
# In CI pipeline
python test_log_extraction.py --directory logs/ --format json --output results.json
if [ $? -ne 0 ]; then
    echo "Log extraction tests failed"
    exit 1
fi
```

## Requirements

- Python 3.8+
- Project dependencies (install via `pip install -e ".[dev]"`)
- Existing extraction modules in the project

## Implementation Details

The script uses a modular extraction function architecture:

1. **ExtractionResult class**: Encapsulates extraction results with success status, data, errors, and execution time
2. **Safe wrapper functions**: Each extraction function has a `_safe` variant that returns `(success, data, error)` tuples
3. **Batch processing**: Processes multiple files in directory recursively
4. **Output formatting**: Separate formatters for table and JSON output

## Contributing

To add new extraction functions:

1. Implement the extraction logic as `extract_<name>_safe(file_path)`
2. Return tuple: `(success: bool, data: Optional[Dict], error: Optional[str])`
3. Add to `EXTRACTION_FUNCTIONS` dictionary
4. Update documentation

## License

Part of the aide-de-camp project.
