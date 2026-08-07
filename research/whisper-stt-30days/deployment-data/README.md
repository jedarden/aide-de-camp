# Whisper-STT 30-Day Deployment Data

**Location:** `research/whisper-stt-30days/deployment-data/`

**Analysis Period:** 2026-07-07 to 2026-08-06 (30-day window)

**Status:** ✅ **VALIDATED** - All files pass JSON well-formedness and validation checks

**Validation:** Performed by validation runner (bead adc-2fgg3)

## Files

This directory contains validated deployment data extracted from the whisper-stt Kubernetes cluster:

### Core Deployment Data
- **`deployments-detailed.json`** - Deployment specifications for whisper-stt and whisper-openai
- **`replicasets-detailed.json`** - Complete ReplicaSet history with 200 entries spanning 97 days
- **`whisper-stt-status.json`** - Current deployment status (healthy, 1 replica available)

### Rollout History
- **`whisper-stt-rollout-history.txt`** - Text summary of whisper-stt deployment revisions
- **`whisper-openai-rollout-history.txt`** - Text summary of whisper-openai deployment revisions

## Data Coverage

- **Time Window:** 2026-07-07 to 2026-08-06 (30 days)
- **Deployments:** 2 deployments (whisper-stt, whisper-openai)
- **ReplicaSets:** 22 ReplicaSets with full revision history
- **Current Status:** Both deployments healthy and running
- **Validation:** All JSON files well-formed and passing structural validation

## Validation Results

All files in this directory have been validated for:
- ✅ JSON well-formedness (parseable)
- ✅ Required fields present
- ✅ Data type correctness
- ✅ Completeness (30-day coverage)

Reference: Validation runner implementation (bead adc-2fgg3)

## Usage

These files serve as the canonical validated dataset for:
- 30-day deployment pattern analysis
- Infrastructure reliability studies
- Comparison with other services (pbx-web)
- Deployment failure mode analysis

## Related Documentation

- Parent directory: `research/whisper-stt-30days/README.md`
- Comprehensive analysis: `research/whisper-stt-30days/FINAL_SUMMARY.md`
- Deployment analysis: `docs/research/deployment-data/README.md`

## Data Lineage

1. **Source:** Kubernetes API queries via kubectl-proxy
2. **Extraction:** Cluster data collection (bead adc-3ue38)
3. **Processing:** Deployment data extraction and structuring
4. **Validation:** Validation runner with comprehensive checks (bead adc-2fgg3)
5. **Storage:** Validated files in this directory

---
**Last Updated:** 2026-08-06  
**Validation Bead:** adc-2fgg3  
**Documentation Bead:** adc-24d33
