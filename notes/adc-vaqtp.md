# Deployment Data Extraction Summary

## Task Completion
Successfully extracted structured deployment data from existing JSON sources.

## Files Created

### 1. pbx-web-deployments.json
- Location: `docs/research/deployment-data/pbx-web-deployments.json`
- Records extracted: 5 deployment events
- Time period: 2026-07-13 to 2026-07-28
- Status breakdown: 4 success, 1 failed
- Deployment versions: 1.0.8, 1.0.9, python:3-slim

### 2. whisper-stt-deployments.json
- Location: `docs/research/deployment-data/whisper-stt-deployments.json`
- Records extracted: 5 replica sets
- Time period: 2026-06-14 to 2026-07-12
- Status breakdown: 2 success, 3 failed
- Deployment versions: 1.8.2, 1.8.4, 1.8.6, latest-cpu

## Data Structure
Each deployment record includes:
- `timestamp`: ISO 8601 format creation time
- `image_tag`: Extracted tag from full image string
- `status`: "success" or "failed" (mapped from outcome/status fields)
- `duration_seconds`: null (not available in source data)
- Additional metadata: image, revision, replicaSet, pod info

## Key Findings
- No Argo Workflow runs found in last 30 days for either service
- Deployments are managed via ArgoCD/ReplicaSets instead
- whisper-stt had rapid deployment sequence on 2026-07-08 (3 attempts)
- pbx-web had 1 rollback event on 2026-07-13

## Validation
✅ Both JSON files validated successfully:
- Parseable JSON structure
- All required fields present
- Valid ISO 8601 timestamps
- Correct status values (success/failed)
- Proper data types for all fields

## Extraction Scripts
- `docs/research/deployment-data/extract_pbx_web_deployments.py`
- `docs/research/deployment-data/extract_whisper_stt_deployments.py`
- `docs/research/deployment-data/validate_deployment_file.py`
