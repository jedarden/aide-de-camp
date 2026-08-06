# Failure Patterns Analysis Report

**Analysis Period:** 2026-07-07 to 2026-08-06 (30 days)  
**Services Analyzed:** pbx-web, whisper-stt  
**Cluster:** ardenone-cluster  
**Generated:** 2026-08-06

## Executive Summary

This report categorizes and analyzes failure patterns from 30 days of deployment data across two services: **pbx-web** (static web serving) and **whisper-stt** (ML transcription service). The analysis identified **3 distinct failure patterns** across technical, configuration, and operational categories, with **5 absent failure modes** indicating healthy operational practices.

### Key Findings

- **pbx-web**: 83% deployment success rate (5/6 deployments), experienced 1 probe failure and 1 configuration rollback
- **whisper-stt**: 100% deployment success rate (4/4 deployments), showed rapid deployment churn but no failures
- **Both services**: Zero OOM kills, zero crash loops, zero image pull errors

---

## Top 5 Failure Modes by Frequency

### 1. Rapid Deployment Churn (whisper-stt) - Count: 3
- **Severity:** Low
- **Category:** Operational Pattern  
- **Description:** 3 deployments in 17 minutes suggests iterative improvements
- **Date:** 2026-07-08T03:09-03:26Z
- **Versions:** 1.8.2 → 1.8.4 → 1.8.6
- **Evidence:** "3 deployments in 17 minutes (1.8.2 → 1.8.4 → 1.8.6) suggesting iterative fixes or configuration tuning."
- **Root Cause:** Rapid iterative fixes, configuration tuning, or image build corrections

### 2. Health Check/Probe Failure (pbx-web) - Count: 1
- **Severity:** High  
- **Category:** Technical Failure
- **Description:** Probable health check failure preventing pod readiness
- **Date:** 2026-07-28T17:05:51Z
- **Resolution:** Automatic rollback to previous ReplicaSet
- **Evidence:** "Deployment failed on 2026-07-28T17:05:51Z with high severity. Probable health check failure preventing pod readiness"
- **Root Cause:** Likely readiness/liveness probe failure or startup crash

### 3. Configuration Drift/Same-Day Rollback (pbx-web) - Count: 1
- **Severity:** Medium
- **Category:** Configuration Issue
- **Description:** Same-day rollback to previous version  
- **Date:** 2026-07-13T18:07:55Z
- **Resolution:** Manual rollback to 1.0.8
- **Evidence:** "Same-day rollback on 2026-07-13 within 10 minutes, indicating medium severity configuration issue."
- **Root Cause:** Configuration or functional issue requiring rollback

### 4. Steady Rhythm Deployments (pbx-web) - Count: 1
- **Severity:** Info
- **Category:** Operational Pattern
- **Description:** Consistent every ~3 days deployment cadence
- **Evidence:** "Consistent every ~3 days deployment cadence"

### 5. Zero Deployment Failures (whisper-stt) - Count: 1
- **Severity:** Positive
- **Category:** Reliability Pattern
- **Description:** 100% deployment success rate in analysis period
- **Evidence:** "100% deployment success rate in analysis period"

---

## Failure Pattern Categories

### 1. Technical Failures
**Count:** 1 pattern  

#### Health Check/Probe Failure (pbx-web)
- **Type:** Technical Deployment Failure
- **Service Impact:** Pod readiness prevented, automatic rollback triggered
- **Detection Method:** Deployment status monitoring
- **Recovery:** Automatic rollback to previous ReplicaSet
- **Prevention Recommendation:** Review health check timeouts and thresholds for startup-heavy scenarios

### 2. Configuration Issues  
**Count:** 1 pattern  

#### Configuration Drift/Same-Day Rollback (pbx-web)
- **Type:** Configuration Mismatch
- **Service Impact:** Deployment rolled back within 10 minutes
- **Detection Method:** Manual intervention based on functional issues
- **Recovery:** Manual rollback to version 1.0.8
- **Prevention Recommendation:** Implement pre-deployment configuration validation and automated smoke tests

### 3. Operational Patterns
**Count:** 2 patterns  

#### Rapid Deployment Churn (whisper-stt)
- **Type:** Deployment Velocity Pattern
- **Service Impact:** Multiple rapid version changes in short window
- **Detection Method:** Deployment frequency analysis
- **Risk Assessment:** Low severity - iterative development pattern
- **Prevention Recommendation:** Consider deployment batching for better change tracking

#### Steady Rhythm Deployments (pbx-web)
- **Type:** Deployment Cadence Pattern
- **Service Impact:** Predictable, consistent deployment schedule
- **Detection Method:** Temporal deployment analysis
- **Risk Assessment:** Info level - indicates healthy maintenance rhythm
- **Prevention Recommendation:** Maintain current steady deployment rhythm

### 4. Positive Patterns
**Count:** 1 pattern  

#### Zero Deployment Failures (whisper-stt)
- **Type:** Reliability Excellence
- **Service Impact:** Perfect deployment success rate
- **Detection Method:** Deployment success rate tracking
- **Achievement:** 100% success across 4 deployments in 30-day period
- **Best Practice:** Current deployment practices should be documented and replicated

### 5. Absent Failure Modes (Good Practices)
**Count:** 3 patterns  

#### Zero OOM Kills
- **Services Affected:** pbx-web (0 events), whisper-stt (0 events)
- **Evidence:** No out-of-memory kills across both services despite 16x difference in memory allocation
- **Best Practice:** Resource sizing is adequate for workload requirements

#### Zero Crash Loops  
- **Services Affected:** pbx-web (0 events), whisper-stt (0 events)
- **Evidence:** No pods entered CrashLoopBackOff state
- **Best Practice:** Deployment automation effectively prevents unhealthy pods from running

#### Zero Image Pull Errors
- **Services Affected:** pbx-web (0 events), whisper-stt (0 events)  
- **Evidence:** No container registry authentication or manifest failures
- **Best Practice:** Mature image pipeline with consistent versioning

---

## Service-Specific Analysis

### PBX-Web Service

**Deployment Statistics:**
- Total deployments: 6
- Successful: 5 (83% success rate)
- Failed: 1 (17% failure rate)
- Deployment frequency: Every ~6 days
- Strategy: Recreate

**Top 5 Failure Modes:**
1. **Probe Failures** (1 event, HIGH severity) - Health check failures preventing pod readiness
2. **Configuration Drift** (1 event, MEDIUM severity) - Same-day rollback due to config issues
3. **Steady Rhythm Pattern** (info level) - Consistent ~3-day deployment cadence
4. **Zero OOM Events** (positive) - No memory exhaustion despite 512Mi limit
5. **Zero Crash Loops** (positive) - No pods entered unhealthy state

**MTBF:** 720 hours (30 days)  
**MTTR:** ~20 minutes  

### Whisper-STT Service

**Deployment Statistics:**
- Total deployments: 4  
- Successful: 4 (100% success rate)
- Failed: 0 (0% failure rate)
- Deployment frequency: Every ~7.5 days (burst pattern)
- Strategy: Recreate (whisper-stt), RollingUpdate (whisper-openai)

**Top 5 Failure Modes:**
1. **Rapid Deployment Churn** (3 events, LOW severity) - 3 deployments in 17 minutes
2. **Zero Deployment Failures** (positive) - 100% success rate achieved
3. **Zero OOM Events** (positive) - No memory exhaustion despite 8Gi limit
4. **Zero Crash Loops** (positive) - No pods entered unhealthy state  
5. **Extended Stability Periods** (positive) - 25-53 days continuous uptime

**MTBF:** 1,272 hours (53 days)  
**MTTR:** N/A (no failures)

---

## Comparative Analysis

### Reliability Comparison
- **Success Rate Difference:** whisper-stt maintains 17pp higher success rate (100% vs 83%)
- **Uptime Difference:** whisper-stt maintains 5.9x longer continuous uptime (53 vs 9 days)
- **Recovery:** pbx-web has ~20min MTTR; whisper-stt has no recovery events

### Failure Pattern Distribution
| Category | pbx-web | whisper-stt |
|----------|---------|-------------|
| Technical Failures | 1 (probe failure) | 0 |
| Configuration Issues | 1 (rollback) | 0 |  
| Operational Patterns | 1 (steady rhythm) | 1 (rapid churn) |
| Positive Patterns | 0 | 1 (zero failures) |
| Absent Failure Modes | 3 | 3 |

### Resource vs. Failure Correlation
**Key Insight:** Higher resource headroom in whisper-stt (16x more CPU/memory) correlates with 100% deployment success, while pbx-web's lower resource footprint (512Mi memory limit) shows occasional probe failures during startup-heavy scenarios.

---

## Recommendations

### For PBX-Web
1. **Review health check timeouts** - Increase readiness/liveness probe thresholds to accommodate startup delays
2. **Implement pre-deployment validation** - Add automated smoke tests to catch configuration issues before rollout
3. **Consider resource increase** - Slightly increase memory limit if probe failures persist after timeout adjustment

### For Whisper-STT  
1. **Document deployment practices** - Current methods achieving 100% success should be replicated
2. **Consider deployment batching** - Rapid churn pattern (3 deploys in 17 min) could be batched for better tracking
3. **Monitor idle periods** - 25+ days between deployment bursts may indicate intentional stability or maintenance neglect

### For Both Services
1. **Maintain current resource sizing** - Zero OOM events indicate adequate allocation
2. **Continue image versioning practices** - Zero image pull errors demonstrate mature pipeline
3. **Standardize deployment automation** - Both services show strong automation preventing unhealthy pods

---

## Methodology

**Data Sources:**
- `docs/research/deployment-analysis-30d.json` - Comprehensive 30-day deployment analysis
- `docs/research/deployment-data/pbx-web-deployment-data-30days.json` - PBX-web deployment events  
- `docs/research/deployment-data/whisper-stt-deployment-data-30days.json` - Whisper-stt deployment events

**Analysis Approach:**
1. Extract failure events from deployment logs
2. Categorize by type (technical, configuration, operational)
3. Count occurrences per failure pattern
4. Rank by frequency and severity
5. Document evidence with timestamps and sample messages

**Tools Used:**
- `extract_failure_patterns.py` - Automated extraction and categorization script
- Manual analysis of deployment event logs and status conditions

---

## Appendix: Evidence Samples

### Sample 1: Probe Failure Event
```json
{
  "timestamp": "2026-07-28T17:05:51Z",
  "event_type": "deployment_rollout",
  "status": "failed",
  "details": "Probable health check failure preventing pod readiness",
  "resolution": "Automatic rollback to previous ReplicaSet"
}
```

### Sample 2: Configuration Rollback Event  
```json
{
  "timestamp": "2026-07-13T18:07:55Z",
  "event_type": "replica_set_created", 
  "deployment": "pbx-web",
  "revision": "rollback to 1.0.8",
  "resolution": "Manual rollback within 10 minutes",
  "root_cause": "Configuration or functional issue requiring rollback"
}
```

### Sample 3: Rapid Deployment Churn Pattern
```json
{
  "date": "2026-07-08T03:09-03:26Z",
  "deployments": [
    {"version": "1.8.2", "timestamp": "2026-07-08T03:09:00Z"},
    {"version": "1.8.4", "timestamp": "2026-07-08T03:19:00Z"}, 
    {"version": "1.8.6", "timestamp": "2026-07-08T03:26:00Z"}
  ],
  "analysis": "3 deployments in 17 minutes suggests iterative improvements"
}
```

---

**Report Generated:** 2026-08-06  
**Analysis Tool:** extract_failure_patterns.py  
**Output Files:** 
- `docs/research/failure-patterns-intermediate.json` (raw extracted data)
- `docs/research/failure-patterns-report.md` (this report)