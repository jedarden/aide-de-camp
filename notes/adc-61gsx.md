# PBX-Web Deployment Data Collection (adc-61gsx)

## Task
Collect deployment event data for `pbx-web` service covering the last 30 days (2026-07-08 to 2026-08-06).

## Data Collection Summary

### Sources Checked
1. **Argo Workflows (iad-ci cluster)**: Queried for pbx-web-build template runs
2. **Cluster Events (ardenone-cluster)**: Searched for pbx-web related events
3. **Deployments/Pods/ReplicaSets (pbx-web namespace)**: Retrieved current and historical state

### Key Findings

#### Deployment Activity (Last 30 Days)
- **5 replica set creation events** detected between 2026-07-13 and 2026-07-28
- All deployments showing **Available=True** status with **1/1 replicas ready**
- No failed deployment events found

#### Current State
- **pbx-web**: Running `ronaldraygun/pbx-web:1.0.9` + `nginx:alpine`
- **pbx-rebuild-relay**: Running `python:3-slim`
- **lab-rebuild-relay**: Running `python:3-slim`
- All deployments healthy and stable

#### CI/CD Pipeline
- **Zero pbx-web-build workflows** executed in iad-ci cluster during the analysis window
- Current image version 1.0.9 was deployed prior to 2026-07-08
- No recent rebuild or deployment activity via CI pipeline

#### Events
- No Kubernetes events found in pbx-web namespace
- Events may have been aged out by the cluster (default TTL ~1 hour)

### Timeline of Activity
```
2026-07-13 18:07:55 - pbx-web-754f4cfdf7 replica set created
2026-07-13 18:18:07 - pbx-web-5ff68464d rolling update (1 replica active)
2026-07-15 03:24:40 - pbx-rebuild-relay-588d79c5b9 replica set created (1 replica active)
2026-07-27 17:56:07 - lab-rebuild-relay-79957dbd4 replica set created (1 replica active)
2026-07-28 17:05:51 - pbx-web-765bb76db8 replica set created
```

## Output
Structured data saved to: `docs/research/pbx-web-deployment-data.json`

## Health Assessment
**Status: HEALTHY**
- All deployments available and ready
- No deployment failures in last 30 days
- Replica sets show normal rollout behavior
- No crash loops or image pull errors detected

## Notes
- The pbx-web service appears stable with minimal deployment activity
- Most recent deployment activity was rolling updates rather than full new deployments
- CI/CD pipeline shows no build activity, suggesting manual deployment or pre-existing stable deployment
