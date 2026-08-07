# Deployment Data Extraction - adc-1o3uh

## Task Completed

Successfully extracted and parsed deployment failure data from log files in `docs/research/deployment-data/`.

## Script Created

`parse_deployment_data.py` - Python script that:
- Reads classified failures and deployment data JSON files
- Parses timestamps with multiple format fallbacks (ISO 8601 variants)
- Extracts required fields: timestamp, pattern_type, service, image_version
- Outputs structured data to console for verification
- Handles malformed timestamps gracefully with warnings

## Results

Extracted **6 deployment records** from the data sources:
- **Services found:** pbx-web
- **Pattern types found:** CrashLoopBackOff, Other, deployment_rollout
- **Records with valid timestamps:** 6/6 (100%)
- **Records with image versions:** 6/6 (100%)

## Data Sources Parsed

1. `classified-failures.json` - 1 record with pattern classification
2. `pbx-web-deployment-data-30days.json` - 5 records with deployment events
3. `whisper-stt-deployment-data-30days.json` - 0 records (no data available)

## Key Features

- **Timestamp parsing:** Handles 5 different ISO 8601 formats with graceful fallback
- **Image version extraction:** Parses `image:tag` format to extract version
- **Structured output:** Console-formatted records with all required fields
- **Summary statistics:** Aggregated counts for services, pattern types, and validation
- **Error handling:** Continues processing on individual record failures

## Sample Output Structure

Each record contains:
```
- timestamp (datetime object)
- timestamp_raw (original string)
- pattern_type (failure category)
- service (service name)
- image_version (container tag)
- image_full (full image reference)
- event_type (deployment event type)
- severity/pattern_severity (when available)
- revision (when available)
- source_file (data provenance)
```

## Usage

```bash
.venv/bin/python parse_deployment_data.py
```

This foundational data extraction enables downstream analysis including pattern frequency analysis, time-based failure trends, and service-specific deployment reliability metrics.
