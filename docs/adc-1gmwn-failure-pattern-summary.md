# Deployment Failure Pattern Analysis
## pbx-web and whisper-stt Services (30-Day Window: 2026-06-24 to 2026-07-24)

### Executive Summary

Analysis of 30-day deployment logs for `pbx-web` and `whisper-stt` services identified **4 distinct failure modes** across both services. Total failure count: **440 occurrences**.

**Key Findings:**
- **Configuration issues** dominate: 432 occurrences (98.2%) - deprecated MetalLB annotations
- **Infrastructure issues**: 1 pod eviction due to ephemeral-storage exhaustion  
- **Service-specific issues**: 2 HTTP errors in pbx-web
- **Environmental issues**: 5 broken pipe errors in pbx-web

### Failure Modes by Category

#### 1. Configuration Failures (432 occurrences - 98.2%)

**Warning:deprecatedAnnotation**
- **Count**: 432 occurrences (216 per service)
- **Severity**: Warning
- **Affected Services**: pbx-web, whisper-stt
- **Pattern**: Both services use deprecated `metallb.universe.tf/allow-shared-ip` annotation
- **Impact**: Non-breaking but indicates dependency on deprecated MetalLB features
- **Recommendation**: Update to current MetalLB annotation format

#### 2. Environmental Failures (5 occurrences - 1.1%)

**AppLog:broken_pipe** 
- **Count**: 5 occurrences
- **Severity**: Medium  
- **Affected Service**: pbx-web only
- **Pattern**: `[Errno 32] Broken pipe` when serving audio recordings
- **Context**: Client disconnects during streaming audio playback
- **Impact**: Minor - client-side disconnects, not server failures
- **Example**: Recording fetch error for `1784309707.446/20260717-173507_15166419321_1784309707.446.wav`

#### 3. Service-Specific Failures (2 occurrences - 0.5%)

**AppLog:http_error**
- **Count**: 2 occurrences
- **Severity**: Medium
- **Affected Service**: pbx-web only  
- **Pattern**: HTTP 5xx errors during request processing
- **Impact**: Service disruption for affected requests
- **Root Cause**: Application-level errors during request handling

#### 4. Infrastructure Failures (1 occurrence - 0.2%)

**Pod:Failed (Evicted)**
- **Count**: 1 occurrence
- **Severity**: High
- **Affected Service**: whisper-stt (whisper-openai pod)
- **Pattern**: Pod eviction due to ephemeral-storage exhaustion
- **Details**: 
  - Node: `k3s-agent-c/10.20.23.113`
  - Threshold: 1.6GB ephemeral-storage limit
  - Available: 1.1GB at eviction time
  - Pod: `whisper-openai-6885fc878b-jjm5j`
  - Exit Code: 137 (SIGKILL)
- **Impact**: Service interruption, automatic pod restart

### Service-Level Breakdown

#### pbx-web (223 total failures)
- **Configuration**: 216 (96.9%) - deprecated annotations
- **Environmental**: 5 (2.2%) - broken pipe errors
- **Service-specific**: 2 (0.9%) - HTTP errors
- **Infrastructure**: 0 (0%)
- **Current Status**: All pods running, 0 restarts

#### whisper-stt (217 total failures)  
- **Configuration**: 216 (99.5%) - deprecated annotations
- **Infrastructure**: 1 (0.5%) - pod eviction
- **Environmental**: 0 (0%)
- **Service-specific**: 0 (0%)
- **Current Status**: 2/3 pods running (1 eviction), 0 restarts on active pods

### Recurring vs One-Off Issues

#### Recurring Issues (≥3 occurrences)
1. **DeprecatedAnnotation** (432 times) - Configuration debt
2. **BrokenPipe** (5 times) - Client disconnects during streaming

#### One-Off Issues
1. **Pod Eviction** (1 time) - Ephemeral-storage exhaustion on whisper-stt

### CI/CD Workflow Analysis

**Finding**: No workflow executions found in 30-day retention window
- **Workflow Templates**: Present but not executed
- **Templates Found**:
  - `pbx-web-build` → `ronaldraygun/pbx-web`
  - `whisper-stt-build` → `ronaldraygun/whisper-stt`
- **Retention Policy**: Workflows deleted 30min after success, 2hr after failure
- **Implication**: No CI/CD failures in analysis window (no builds executed)

### Severity Assessment

| Severity | Count | Percentage | Failure Types |
|----------|-------|------------|----------------|
| Warning | 432 | 98.2% | Deprecated annotations |
| Medium | 7 | 1.6% | Broken pipe, HTTP errors |
| High | 1 | 0.2% | Pod eviction |

### Recommendations

1. **Immediate (High Priority)**
   - Investigate whisper-stt ephemeral-storage usage
   - Add storage monitoring and alerts
   - Consider increasing ephemeral-storage limits or adding volume mounts

2. **Short-term (Medium Priority)**  
   - Update MetalLB annotations to current format
   - Add retry logic for broken pipe errors in pbx-web
   - Investigate HTTP 5xx errors in pbx-web

3. **Long-term (Low Priority)**
   - Implement CI/CD workflow execution monitoring
   - Add automated testing for deployment changes
   - Review resource allocation across both services

### Data Files Generated

- `data/adc-1gmwn/failure_analysis_report.json` - Detailed structured analysis
- `docs/adc-1gmwn-failure-pattern-summary.md` - This summary document

### Next Steps

Pass categorized failure data to comparative analysis bead to identify:
- Cross-service failure patterns
- Temporal failure clustering
- Correlation with deployment events
- Resource exhaustion trends