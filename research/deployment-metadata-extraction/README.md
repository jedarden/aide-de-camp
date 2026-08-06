# Deployment Metadata Extraction - pbx-web vs whisper-stt

**Extraction Date:** 2026-08-06  
**Analysis Period:** 30 days (2026-07-07 to 2026-08-06)  
**Cluster:** ardenone-cluster

## Overview

This extraction captures deployment events, timestamps, outcomes, and patterns for `pbx-web` and `whisper-stt` services to enable comparative reliability analysis.

## Summary Statistics

### Overall Metrics
- **Total deployment events:** 32 (17 pbx-web, 15 whisper-stt)
- **Services analyzed:** 5 total (3 pbx-web namespace, 2 whisper-stt namespace)
- **Analysis timeframe:** 30 days
- **Success rate:** 100% for both services

### Service Comparison

| Metric | pbx-web | whisper-stt | whisper-openai |
|--------|---------|-------------|----------------|
| Revisions (30 days) | 4 | 10 | 5 |
| Deployment frequency | Low | High | Medium |
| Strategy | RollingUpdate | Recreate | RollingUpdate |
| Success rate | 100% | 100% | 100% |
| Days since last | 24 | 24 | 53 |

### Key Findings
- **Deployment frequency:** whisper-stt has 2.5x more deployments than pbx-web (10 vs 4)
- **Strategy difference:** whisper-stt uses `Recreate` (more disruptive) vs pbx-web's `RollingUpdate` (zero-downtime)
- **Success rates:** Both services maintain 100% success rates despite frequency differences
- **Recent activity:** Both main services last deployed ~24 days ago (late July 2026)

## Files Generated

### Structured Data Files
- `all-deployment-events.json` - Combined deployment events (32 events)
- `all-deployment-events.csv` - Combined deployment events in CSV format
- `pbx-web-deployment-events.json` - pbx-web namespace events (17 events)
- `pbx-web-events.csv` - pbx-web namespace events in CSV format
- `whisper-stt-deployment-events.json` - whisper-stt namespace events (15 events)
- `whisper-stt-events.csv` - whisper-stt namespace events in CSV format

### Analysis Files
- `deployment-summaries.json` - High-level metrics per deployment
- `deployment-comparison.json` - Comparative analysis between services
- `data_sources_documentation.json` - Data sources and query parameters

### Documentation
- `DATA_SOURCES.md` - Human-readable data sources documentation
- `README.md` - This file

## Data Structure

Each deployment event includes:
- **service:** Namespace (pbx-web or whisper-stt)
- **deployment_name:** Specific deployment (e.g., pbx-web, whisper-stt, whisper-openai)
- **revision:** Deployment revision number
- **replicaset:** Kubernetes ReplicaSet identifier
- **timestamp:** Deployment timestamp (ISO 8601)
- **age_days:** Days since deployment at extraction time
- **status:** Current status (active, scaled_down)
- **replicas:** Replica count
- **available:** Available replicas
- **ready:** Ready replicas
- **image:** Container image
- **strategy:** Deployment strategy (RollingUpdate, Recreate)
- **success:** Boolean success indicator

## Data Sources

### Cluster Access
- **Cluster:** ardenone-cluster
- **Access method:** kubectl-proxy over Tailscale
- **Read-only proxy:** http://traefik-ardenone-cluster:8001

### Source Data Files
- **pbx-web:** `research/pbx-web-30days/deployments-30days.json`
- **whisper-stt:** `research/whisper-stt-30days/deployments-30days.json`

### Query Methods
```bash
# ReplicaSets (deployment history)
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n <namespace>

# Events (deployment events)
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n <namespace> --sort-by='.lastTimestamp'

# Current pods
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n <namespace>
```

## Known Limitations

1. **Historical pod metadata:** Kubernetes does not retain detailed metadata for deleted pods
2. **Deletion timestamps:** Estimated from ReplicaSet data rather than exact pod deletion times
3. **Deployment duration:** Pod log analysis needed for actual deployment duration metrics
4. **Image pull times:** Not captured in current data collection
5. **Rollback events:** Not explicitly captured in current data structure

## Next Steps for Enhanced Analysis

### Immediate (Duration Metrics)
- Extract pod logs for actual deployment startup times
- Analyze container image pull durations
- Capture health check latency patterns

### Event Analysis
- Query Kubernetes events for ScalingReplicaSet events
- Identify FailedCreate events and failure patterns
- Correlate deployment events with system events

### Build Pipeline Integration
- Analyze Argo Workflows execution history
- Correlate deployments with CI/CD pipeline runs
- Track build-to-deployment latency

### Reliability Metrics
- Calculate deployment success rates by time window
- Analyze deployment failure patterns
- Measure mean time to recovery (MTTR) for failed deployments

## Usage

### Load Data in Python
```python
import json

# Load all events
with open('all-deployment-events.json', 'r') as f:
    data = json.load(f)
    events = data['events']

# Load comparison
with open('deployment-comparison.json', 'r') as f:
    comparison = json.load(f)
```

### Load Data in pandas
```python
import pandas as pd

# Load CSV
df = pd.read_csv('all-deployment-events.csv')

# Filter by service
pbx = df[df['service'] == 'pbx-web']
whisper = df[df['service'] == 'whisper-stt']
```

### Load Data in Shell
```bash
# Count events by service
cut -d',' -f1 all-deployment-events.csv | sort | uniq -c

# Extract timestamps
cut -d',' -f5 all-deployment-events.csv | tail -n +2

# Check success rates
cut -d',' -f1,13 all-deployment-events.csv | tail -n +2 | sort | uniq -c
```

## Related Analysis

- `research/pbx-vs-whisper-stt-30days/` - Full 30-day comparison data
- `research/adc-2vk54-30-day-pbx-whisper-comparative-analysis.md` - Detailed comparative analysis
- `research/deployment-analysis.md` - Deployment patterns and analysis

## Extraction Script

The extraction was performed using:
- **Script:** `research/extract_deployment_metadata.py`
- **Dependencies:** Python 3 standard library (json, csv, dataclasses, pathlib)
- **Execution:** `.venv/bin/python research/extract_deployment_metadata.py`

To re-run the extraction with updated source data:
```bash
cd /home/coding/aide-de-camp
.venv/bin/python research/extract_deployment_metadata.py
```

---

**Generated:** 2026-08-06  
**Bead ID:** adc-2nhq1  
**Status:** ✅ Complete