# Deployment Data Files - August 2026

## Overview

This document tracks the validated 30-day deployment data files for comparison and analysis use.

## File Locations

### whisper-stt Deployment Data (Latest - Validated)
- **Path**: `/home/coding/aide-de-camp/whisper-stt-deployments-30d.json`
- **Cluster**: ardenone-cluster
- **Namespace**: whisper-stt
- **Service**: whisper-stt, whisper-openai
- **Coverage**: 2026-07-07 to 2026-08-06 (30 days)
- **Validation**: ✓ Passed - All required fields present, well-formed JSON, 30-day coverage verified
- **Generated**: 2026-08-06T12:03:32Z
- **Schema**: WhisperSTTDeploymentSchema (whisper_stt_deployment_schema.py)
- **Validator**: validate_whisper_stt_deployment.py
- **Deployments**: 2 total, 2 successful, 0 failed

### pbx-web Deployment Data
- **Path**: `/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json`
- **Cluster**: ardenone-cluster
- **Namespace**: pbx-web
- **Service**: pbx-web
- **Coverage**: 2026-07-07 to 2026-08-06 (30 days)
- **Validation**: ✓ Passed - All required fields present, well-formed JSON, 30-day coverage verified
- **Generated**: 2026-08-06T12:37:36Z

## Usage

These files are used for:
- Comparative deployment analysis between services
- Deployment frequency metrics
- Historical deployment pattern analysis
- Resource utilization comparison
- Health and stability assessment

## Data Sources

- **Kubernetes API**: ReplicaSets, Deployments, Pods via kubectl read-only proxy
- **Cluster**: ardenone-cluster (read-only proxy)
- **Collection Method**: Direct kubectl queries via Tailscale proxy

## Validation Status

Both files were validated on 2026-08-06 using the validation script at:
`/home/coding/aide-de-camp/validate_30day_deployment_files.py`

Validation checks:
- ✓ Required fields presence
- ✓ Data type correctness
- ✓ Timestamp validity
- ✓ 30-day coverage completeness
- ✓ Data consistency
- ✓ Well-formed JSON

## Comparison Notes

### Key Differences Between Services

1. **Deployment Strategy**:
   - whisper-stt: Recreate strategy for whisper-stt, RollingUpdate for whisper-openai
   - pbx-web: Recreate strategy

2. **Deployment Frequency**:
   - whisper-stt: 5 total ReplicaSets in 30-day period, rapid deployment sequence on 2026-07-08
   - pbx-web: 5 deployment events in 30-day period, including 1 rollback

3. **Container Configuration**:
   - whisper-stt: Single container per pod
   - pbx-web: Multi-container (nginx + site-generator)

## Related Documentation

- Deployment Analysis: `/home/coding/aide-de-camp/research/deployment-analysis.md`
- Comparison Metrics: `/home/coding/aide-de-camp/docs/research/deployment-metrics-comparison.json`
- Metadata Sources: `/home/coding/aide-de-camp/research/deployment-metadata-sources.md`

## Maintenance

When updating these files:
1. Re-run validation: `.venv/bin/python validate_30day_deployment_files.py`
2. Update validation date in this document
3. Update coverage dates in this document
4. Commit with version tag

---

**Last Validated**: 2026-08-06  
**Bead ID**: adc-181i4  
**Validation Script**: validate_30day_deployment_files.py
