# Deployment Failure Pattern Classification

## Overview

This document describes the deployment failure pattern classification system developed for analyzing Kubernetes deployment failures across pbx-web and whisper-stt services.

## Pattern Categories

The system defines 6 failure pattern categories:

### 1. ImagePullBackOff (High Severity)
- **Description**: Container image cannot be pulled (registry issues, authentication, missing image)
- **Detection**: Regex patterns for image pull failures, registry errors, authentication issues
- **Keywords**: imagepullbackoff, pull error, registry, unauthorized

### 2. CrashLoopBackOff (Critical Severity)
- **Description**: Pod repeatedly crashes and restarts (application errors, misconfiguration)
- **Detection**: Regex patterns for restart loops, container termination, exit codes
- **Keywords**: crashloopbackoff, restart loop, container terminated, exit code

### 3. OOMKilled (High Severity)
- **Description**: Container killed due to memory exhaustion (resource limits exceeded)
- **Detection**: Regex patterns for memory exhaustion, OOM, memory limit exceeded
- **Keywords**: oomkilled, out of memory, memory exhausted, OOM

### 4. Probe_failure (Medium Severity)
- **Description**: Readiness or liveness probe failures (health check issues)
- **Detection**: Regex patterns for probe failures, health check errors, timeouts
- **Keywords**: readiness probe failed, liveness probe failed, health check failed

### 5. Dependency_timeout (Medium Severity)
- **Description**: Deployment timeout due to dependency unavailability
- **Detection**: Regex patterns for dependency timeouts, service unavailable, connection issues
- **Keywords**: dependency timeout, service unavailable, connection timeout

### 6. Other (Unknown Severity)
- **Description**: Other failure patterns not matching standard categories
- **Detection**: Generic error patterns and warnings
- **Keywords**: error, failed, failure, terminated, warning

## Analysis Results

### Current Deployment Health (Last 30 Days)

**Total Failures Classified**: 1

**Failure Breakdown**:
- **By Pattern Type**: Other (1) - deployment rollback
- **By Service**: pbx-web (1)
- **By Severity**: unknown (1)

### Key Finding

The deployment data shows **excellent health** with only 1 failure incident:
- **pbx-web deployment rollback** on 2026-07-13 (rolled back from revision 14 to 11, image 1.0.9 to 1.0.8)

**Absence of Standard Kubernetes Failures**:
- 0 ImagePullBackOff events
- 0 CrashLoopBackOff events
- 0 OOMKilled events
- 0 Probe failures
- 0 Dependency timeouts

### Deployment Success Metrics

**pbx-web**:
- Total deployments (30 days): 5
- Successful deployments: 5
- Failed deployments: 0
- Rollback events: 1
- Success rate: 100%

**whisper-stt**:
- Total deployments (30 days): 2
- Successful deployments: 2
- Failed deployments: 0
- Rollback events: 0
- Success rate: 100%

## Methodology

1. **Data Extraction**: Parsed deployment data from `parsed-data.json` which aggregated 19 source files
2. **Pattern Matching**: Applied regex patterns and keyword matching to failure records
3. **Classification**: Categorized each failure into one of 6 pattern types
4. **Preservation**: Maintained all original data fields plus added pattern classification fields

## Classification Algorithm

```python
def classify_failure(failure_record):
    # Extract searchable text from multiple fields
    # Check against pattern categories in specificity order
    # Add pattern_type, pattern_severity, pattern_description
    # Return enhanced record with classification
```

## Files Generated

1. **classify_failures.py** - Classification script with pattern definitions
2. **classified-failures.json** - Complete classification output with:
   - Pattern definitions
   - Classified failure records
   - Summary statistics
   - Metadata

## Usage

```bash
# Run classification
cd docs/research/deployment-data
python3 classify_failures.py

# View results
cat classified-failures.json
```

## Conclusion

The deployment infrastructure shows **excellent reliability** with minimal failure occurrences. The single rollback event was handled cleanly, and the absence of standard Kubernetes failure patterns (ImagePullBackOff, CrashLoopBackOff, OOMKilled, etc.) indicates well-configured deployments and stable application behavior.

This classification system provides a foundation for monitoring and categorizing deployment failures as the infrastructure grows and more deployment events occur.
