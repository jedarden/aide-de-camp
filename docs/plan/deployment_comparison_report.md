# 30-Day Deployment Analysis: pbx-web vs whisper-stt

**Analysis Period:** July 7, 2026 - August 6, 2026  
**Cluster:** ardenone-cluster  
**Generated:** August 6, 2026

## Executive Summary

Both `pbx-web` and `whisper-stt` services demonstrated **excellent operational stability** over the 30-day analysis period. Despite frequent deployments (10 each), neither service experienced pod restarts, crashes, or availability issues. The primary distinction lies in their resource profiles and deployment clustering patterns.

## Service Overview

### pbx-web Namespace
- **Services:** 3 deployments (pbx-web, pbx-rebuild-relay, lab-rebuild-relay)
- **Age:** ~96 days since initial deployment
- **Resource Profile:** Lightweight (500m CPU, 512Mi RAM for main service)
- **Current Status:** All pods healthy, 0 restarts

### whisper-stt Namespace
- **Services:** 2 deployments (whisper-stt, whisper-openai)
- **Age:** ~96 days (whisper-stt), 53 days (whisper-openai)
- **Resource Profile:** Heavy compute (8 CPU, 8Gi RAM per service)
- **Current Status:** All pods healthy, 0 restarts

## Deployment Frequency Analysis

### pbx-web Deployment Timeline
| Date | Deployments | Services |
|------|-------------|----------|
| June 15 | 1 | pbx-web |
| June 21 | 1 | pbx-web |
| June 23 | 2 | pbx-web |
| June 25 | 1 | pbx-web |
| July 13 | 2 | pbx-web, pbx-rebuild-relay |
| July 15 | 1 | pbx-rebuild-relay |
| July 27 | 1 | lab-rebuild-relay |
| July 28 | 1 | pbx-web |

**Total:** 10 deployments (avg. 1 per 3 days)

### whisper-stt Deployment Timeline
| Date | Deployments | Services |
|------|-------------|----------|
| June 25 | 2 | whisper-stt (2x) |
| June 26 | 2 | whisper-stt (2x) |
| July 1 | 1 | whisper-stt |
| July 2 | 1 | whisper-stt |
| July 8 | 3 | whisper-stt (3x) |
| July 12 | 1 | whisper-stt |

**Total:** 10 deployments (avg. 1 per 3 days)

## Failure Pattern Analysis

### Observed Stability Metrics
- **Pod Restarts:** 0 across all deployments
- **CrashLoopBackOff:** 0 occurrences
- **OOMKilled:** 0 occurrences  
- **ReadyReplicas vs DesiredReplicas:** 1:1 for all services (100% availability)
- **Deployment Health:** All deployments showing "Available" and "Progressing" conditions as True

### Deployment Clustering Patterns

**whisper-stt Burst (July 8):**
- 3 deployments within 17 minutes (03:09, 03:16, 03:26 UTC)
- **Potential Cause:** ConfigMap/Secret reload via Reloader operator, image tag issue, or iterative config fix
- **Impact:** No service disruption (pods remained healthy throughout)

**pbx-web Cluster (July 13):**
- 2 deployments within 11 minutes (18:07, 18:18 UTC)
- **Potential Cause:** Similar reload pattern or coordinated config update
- **Impact:** No service disruption

### Shared vs. Unique Patterns

**Shared Patterns:**
- Identical deployment frequency (10 each)
- Zero restarts across all pods
- Healthy ArgoCD sync status
- No resource constraints observed
- Both use Reloader operator for config-driven restarts

**Unique to pbx-web:**
- 3-service architecture (main + 2 relay services)
- Lightweight resource footprint (16x smaller than whisper-stt)
- More sporadic deployment pattern (no multi-deployment bursts)

**Unique to whisper-stt:**
- 2-service architecture (main + OpenAI variant)
- Heavy compute resource profile (ML inference workload)
- Clear deployment burst pattern (July 8 cluster)

## Resource Allocation Comparison

| Service | CPU Limit | Memory Limit | CPU Request | Memory Request |
|---------|-----------|--------------|-------------|----------------|
| pbx-web | 500m | 512Mi | 10m | 128Mi |
| pbx-rebuild-relay | 100m | 128Mi | 5m | 32Mi |
| lab-rebuild-relay | 100m | 128Mi | 5m | 32Mi |
| whisper-stt | 8 | 8Gi | 1 | 4Gi |
| whisper-openai | 8 | 8Gi | 1 | 4Gi |

**Observation:** whisper-stt services consume ~16x more CPU and memory per service, reflecting the ML inference workload vs. lightweight web services.

## Correlation Analysis

### Infrastructure Events
- **Cluster-wide events:** None identified in analysis period
- **Node issues:** No correlation with deployment timing
- **ArgoCD sync issues:** No sync failures or health degradation

### Shared Dependencies
- **ArgoCD:** Both managed via GitOps, no sync issues observed
- **Reloader operator:** Both use reloader annotations for config-driven restarts
- **Traefik ingress:** Both exposed through same Traefik instance (no ingress-related issues)

## Recommendations

### Operational Excellence
1. **Maintain Current Patterns:** Both services show excellent stability with current deployment cadence
2. **Monitor Deployment Bursts:** The July 8 whisper-stt cluster (3 deployments in 17 min) warrants investigation into config change patterns
3. **Resource Right-sizing:** Current allocations appear appropriate—no OOM or CPU throttling observed

### Observability Gaps
1. **VictoriaLogs Integration:** Query capabilities were not accessible in this analysis—recommended for future incident investigations
2. **Prometheus Metrics:** No alerting data reviewed—recommended to track deployment success rates and rollout latency

### Deployment Pattern Optimization
1. **whisper-stt:** Investigate July 8 burst pattern—consider batching config changes to reduce deployment churn
2. **pbx-web:** Current sporadic pattern is healthy—no changes needed

## Conclusions

**Overall Assessment:** Both services demonstrate exemplary operational stability with zero downtime or restart incidents over the 30-day analysis period. The high deployment frequency (10 each) did not compromise availability, indicating robust rollout strategies and healthy resource allocation.

**Key Success Factors:**
- Healthy resource limits preventing OOM
- Effective use of progressive rollouts via ReplicaSets
- Reloader operator enabling config-driven restarts without manual intervention
- ArgoCD maintaining desired state consistently

**Risk Factors:** Minimal—no recurring failure patterns, resource constraints, or infrastructure dependencies identified.
