# Failure Pattern Analysis Report

**Generated:** 2026-08-06T21:41:03.820324
**Analysis Period:** 30 days (2026-07-07 to 2026-08-06)

## Executive Summary

- **Total patterns identified:** 7
- **Total failures detected:** 1
- **Patterns with occurrences:** 1
- **Services analyzed:** pbx-web, whisper-stt
- **Data quality:** complete

## Failure Pattern Taxonomy

### ImagePullBackOff

**Description:** Container image cannot be pulled from registry
**Severity:** high
**Frequency:** 0 occurrences
**Time span:** 0 days

**Indicators:**
  - `image pull error`
  - `ErrImagePull`
  - `ImagePullBackOff`

**Common causes:**
  - registry unavailable
  - missing image
  - authentication failure
  - network issues

### CrashLoopBackOff

**Description:** Pod repeatedly crashes and restarts
**Severity:** critical
**Frequency:** 0 occurrences
**Time span:** 0 days

**Indicators:**
  - `crash`
  - `CrashLoopBackOff`
  - `restart count`
  - `terminated`

**Common causes:**
  - application errors
  - misconfiguration
  - runtime exceptions
  - missing dependencies

### OOMKilled

**Description:** Container killed due to exceeding memory limits
**Severity:** critical
**Frequency:** 0 occurrences
**Time span:** 0 days

**Indicators:**
  - `OOMKilled`
  - `out of memory`
  - `memory limit exceeded`

**Common causes:**
  - memory leaks
  - insufficient limits
  - high load
  - memory-intensive operations

### Probe_failure

**Description:** Health check failures (readiness, liveness, or startup probes)
**Severity:** medium
**Frequency:** 0 occurrences
**Time span:** 0 days

**Indicators:**
  - `probe failed`
  - `readiness probe`
  - `liveness probe`
  - `unhealthy`

**Common causes:**
  - application not ready
  - deadlock
  - slow startup
  - health check misconfiguration

### Dependency_timeout

**Description:** Timeouts connecting to external services or dependencies
**Severity:** high
**Frequency:** 0 occurrences
**Time span:** 0 days

**Indicators:**
  - `timeout`
  - `connection refused`
  - `dependency unavailable`
  - `upstream error`

**Common causes:**
  - database unavailable
  - API timeout
  - network issues
  - service discovery failure

### Deployment_rollback

**Description:** Deployment was rolled back to a previous version
**Severity:** medium
**Frequency:** 1 occurrences
**Time span:** 1 days
**Images affected:** ronaldraygun/pbx-web:1.0.8

**Sample occurrences:**
  1. 2026-07-13T18:07:55Z
     Image: ronaldraygun/pbx-web:1.0.8
     Notes: Rolled back to 1.0.8 on same day

**Indicators:**
  - `rollback`
  - `rolled back`
  - `revert`
  - `previous version`

**Common causes:**
  - deployment failure
  - health check failures
  - configuration errors
  - errors detected post-deployment

### Other

**Description:** Other failure patterns not matching standard categories
**Severity:** variable
**Frequency:** 0 occurrences
**Time span:** 0 days

**Indicators:**
  - `error`
  - `failed`
  - `failure`
  - `issue`

**Common causes:**
  - various

## Service-Specific Analysis

### pbx-web

**Total events:** 5
**Current image:** ronaldraygun/pbx-web:1.0.9

**Event types:**
  - deployment_rollout: 4
  - deployment_rollback: 1

**Deployment outcomes:**
  - success: 4
  - rolled_back: 1

**Failures detected:**
  - Deployment_rollback: 2026-07-13T18:07:55Z

### whisper-stt

**Total events:** 4
**Current image:** ronaldraygun/whisper-stt:1.8.6

**Event types:**
  - deployment_rollout: 4

**Deployment outcomes:**
  - success: 4

**No failures detected** ✅

## Methodology

This analysis examined:
1. Deployment events from the last 30 days
2. Pod health indicators for failure signals
3. Deployment outcomes (success, rollback, failure)
4. Image version changes and patterns

Failures are categorized using the taxonomy defined above, with severity
ratings ranging from 'info' to 'critical'.

## Recommendations

### Monitoring
- Continue monitoring for the failure patterns defined in the taxonomy
- Set up alerts for critical patterns (CrashLoopBackOff, OOMKilled)
- Track deployment success rates over time

### Data Collection
- Collect pod status and event data for deeper failure analysis
- Track CI/CD workflow execution and failures
- Monitor image pull success rates and timing

---

*Analysis based on data from: deployment-data/