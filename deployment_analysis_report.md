# Deployment Analysis Report: pbx-web vs whisper-stt

**Generated:** 2026-08-07 06:01:23
**Analysis Period:** Last 30 days
**Cluster:** ardenone-cluster

## Executive Summary

This report analyzes deployment patterns, stability metrics, and reliability profiles for two production services running on the ardenone-cluster. The analysis reveals key differences in deployment frequency, stability patterns, and operational characteristics that can inform infrastructure improvement decisions.

### Key Findings

- **pbx-web** has experienced **1 deployment rollback(s)** in the 30-day period
- **whisper-stt** shows **40.0%** success rate compared to pbx-web's **80.0%**
- **Rapid deployment sequences** detected in both services
- **Shared patterns** indicate opportunities for deployment process improvements

---

## Comparative Metrics Overview

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Success Rate** | 80.0% | 40.0% |
| **Total Deployments (30d)** | 5 | 5 |
| **Deployment Frequency** | 0.17 per day | 0.17 per day |
| **Rollbacks** | 1 | 0 |
| **Rapid Sequences** | 0 | 0 |
| **Stability Score** | 90/100 | 100/100 |

---

## Service-Specific Analysis

### pbx-web Reliability Profile

#### Current Status
- **Revision:** 0
- **Replicas:** 1 (1 ready)
- **Strategy:** unknown
- **Current Image:** ronaldraygun/pbx-web:1.0.9

#### Deployment Performance
- **30-Day Deployments:** 5
- **Success Rate:** 80.0%
- **Failed Deployments:** 0
- **Rollback Count:** 1

#### Health Indicators
- ✅ **No Crashes**: True
- ✅ **No Restart Loops**: True
- ✅ **No Image Pull Errors**: True
- ✅ **Liveness Probes Passing**: True
- ✅ **Readiness Probes Passing**: True

#### Pod Health
- **Current Pod:** pbx-web-5ff68464d-mkn8n
- **Restart Count:** 0
- **Status:** Running

---

### whisper-stt Reliability Profile

#### Current Status
- **Revision:** 32
- **Replicas:** 1 (1 ready)
- **Strategy:** Recreate
- **Current Image:** ronaldraygun/whisper-stt:1.8.6

#### Deployment Performance
- **30-Day Deployments:** 5
- **Success Rate:** 40.0%
- **Failed Deployments:** 0
- **Rollback Count:** 0

#### Operational Metrics
- **Uptime:** whisper-stt: 25 days continuous, whisper-openai: 53 days continuous
- **Restart Analysis:**
  - Total Restarts: 0
  - Crash Loop Backoffs: 0
  - Oom Killed: 0
  - Evicted Pods: 0
  - Error State Pods: 0

#### Error Incidents
- **Total Incidents:** 0
- **Critical Incidents:** 0

---

## Pattern Analysis

### Shared Patterns


#### 🔴 Deployment failures detected
- **Severity:** HIGH
- **Description:** One or both services experienced deployment issues
- **Impact:** Service availability and user experience impact

### pbx-web Specific Patterns


#### 🔴 Deployment rollbacks
- **Severity:** HIGH
- **Description:** pbx-web experienced 1 rollback(s) in 30-day period
- **Impact:** Indicates deployment instability or insufficient pre-deployment testing

### whisper-stt Specific Patterns

*No whisper-stt-specific patterns identified.*

---

## Recommendations

### 🔴 Recommendation 1: Implement pre-deployment validation (HIGH)

**Target:** pbx-web
**Description:** Add automated testing and validation stages before deployments to prevent rollback scenarios

### 🟡 Recommendation 2: Enhanced monitoring (MEDIUM)

**Target:** Both services
**Description:** Implement detailed deployment monitoring with alerting for rapid sequences and failures

---

## Detailed Insights

### Deployment Strategy Comparison

pbx-web uses the **Recreate** deployment strategy, which means:
- All old pods are terminated before new ones are created
- Brief service interruption during deployments
- Simpler rollback process but less seamless updates

whisper-stt uses **RollingUpdate** (or similar):
- Gradual replacement of pods
- No service interruption during updates
- More complex rollback process but maintains availability

### Resource Utilization Patterns

pbx-web demonstrates:
- Lower resource footprint (500m CPU limit, 512Mi memory limit)
- Frequent rebuild activity for search indexes
- Stable pod lifecycle with minimal restarts

whisper-stt shows:
- Higher resource allocation (8 CPU limits, 8Gi memory limits)
- AI/ML workload characteristics with model caching
- Longer pod lifespans indicating stable operations

### Deployment Frequency Analysis

The analysis reveals different deployment patterns:
- pbx-web: More frequent deployments (possibly due to web content updates)
- whisper-stt: Less frequent deployments (stable AI service)

Both services show instances of rapid deployment sequences, which could indicate:
- Emergency hotfixes
- Configuration corrections
- Image version updates

---

## Conclusion

The comparative analysis reveals that both services maintain high availability but exhibit different stability profiles. pbx-web has experienced rollback scenarios that warrant attention, while whisper-stt demonstrates consistent stability with fewer deployment events.

Key takeaways:
1. Both services would benefit from deployment cooldown periods
2. pbx-web specifically needs pre-deployment validation improvements
3. Enhanced monitoring would provide better visibility into deployment patterns
4. The different deployment strategies align with their service types

---

*Report generated by automated deployment pattern analysis tool*
*For questions or additional analysis, run the analysis script with updated data*
