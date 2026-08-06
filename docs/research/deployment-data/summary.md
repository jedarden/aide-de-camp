# Deployment Data Validation Summary

## Overview
Validated deployment data completeness and 30-day coverage for both pbx-web and whisper-stt services.

## Key Findings

### Overall Status
- **Combined Date Range:** 44 days (June 14 - July 28, 2026) ✅ EXCEEDS 30-day requirement
- **Total Deployments:** 10 (5 pbx-web + 5 whisper-stt)
- **Success Rate:** 60% (6 successful, 4 failed)

### Per-Service Analysis

#### PBX-WEB (14 days, July 13-28)
- **Deployments:** 5 total (4 success, 1 failed)
- **Coverage:** 14 days with a 12-day gap (July 15-27)
- **Status:** Invalid due to significant data gap

#### Whisper-STT (28 days, June 14 - July 12)
- **Deployments:** 5 total (2 success, 3 failed)
- **Coverage:** 28 days with a 23-day gap (June 14 - July 8)
- **Status:** Invalid due to significant data gap

### Data Quality
✅ All required fields present (timestamp, image_tag, status)
✅ No null critical values
✅ Valid ISO8601 timestamps
⚠️ Significant gaps in deployment records

## Recommendations
1. **Investigate gaps:** 23-day gap in whisper-stt and 12-day gap in pbx-web may indicate missing kubernetes events
2. **Check event collection:** Verify event extraction scripts are capturing all deployment events
3. **Monitor failure rate:** Whisper-STT has 60% failure rate (3/5) - may need investigation

## Files Generated
- `validate_deployment_data.py` - Validation script
- `validation-report.md` - Detailed validation report

Generated: 2026-08-06
