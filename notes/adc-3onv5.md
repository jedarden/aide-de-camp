# Parse pbx-web Deployment Data (adc-3onv5)

## Summary
Successfully parsed and structured pbx-web deployment data from Kubernetes ReplicaSet records.

## What Was Done

### 1. Data Collection
- Fetched raw ReplicaSet data from ardenone-cluster via kubectl proxy
- Retrieved 11 total ReplicaSets representing deployment history
- Saved raw JSON to `~/scratch/pbx-web-raw-30d.json`

### 2. Parsing Implementation
Created Python script that:
- Extracted key fields from each ReplicaSet:
  - Name (ReplicaSet identifier)
  - Deployment revision number (from annotations)
  - Creation timestamp
  - Current replica count vs desired replicas
  - Container images (site-generator and nginx versions)
  - Namespace and UID
- Filtered to deployments from last 30 days (3 deployments met criteria)
- Calculated deployment duration (time since creation)
- Determined deployment status (active/inactive/scaling)

### 3. Structured Output
Saved to `~/scratch/pbx-web-deployments-30d.json` with:
- 3 deployment records from last 30 days
- 1 active deployment (pbx-web-5ff68464d, revision 14, running image 1.0.9)
- 2 inactive deployments (older ReplicaSets with 0 replicas)

## Key Findings

### Deployment History (Last 30 Days)
- **Most Recent**: pbx-web-765bb76db8 (revision 13)
  - Created: 2026-07-28
  - Image: ronaldraygun/pbx-web:1.0.9
  - Status: inactive (superseded by revision 14)

- **Current Active**: pbx-web-5ff68464d (revision 14)
  - Created: 2026-07-13
  - Image: ronaldraygun/pbx-web:1.0.9
  - Status: active (1 replica running)
  - Duration: 24 days

- **Older**: pbx-web-754f4cfdf7 (revision 11)
  - Created: 2026-07-13
  - Image: ronaldraygun/pbx-web:1.0.8
  - Status: inactive

### Observations
- Current active deployment has been running for 24+ days
- Most recent deployment (revision 13) was rolled back in favor of revision 14
- Image version stable at 1.0.9 across recent deployments
- No deployment failures observed (all ReplicaSets show clean rollout history)

## Notes
- No Argo workflow executions found for pbx-web-build in last 30 days
- Used ReplicaSet data as proxy for deployment history
- ReplicaSet timestamps indicate when each deployment revision was created
- Duration calculated from creation to present (not finishedAt, since active deployments don't have finish time)

## Deliverables
- `~/scratch/pbx-web-raw-30d.json` - Raw ReplicaSet JSON
- `~/scratch/pbx-web-deployments-30d.json` - Structured deployment records
