# Failure Patterns Analysis Report

**Generated:** 2026-08-07T03:44:13.099286
**Analysis Period:** 30 days (2026-07-07 to 2026-08-06)

## Executive Summary

### pbx-web Service
- **Total Errors Analyzed:** 1438
- **Unique Error Types:** 6
- **Service Health:** Needs attention - significant error rate detected

### whisper-stt Service
- **Total Requests Analyzed:** 98251
- **Success Rate:** 100.0%
- **Server Errors:** 0
- **Service Health:** HEALTHY

## pbx-web Detailed Failure Analysis

### #1: http_500
**Occurrences:** 371
**Severity:** STATUS 500
**Percentage of Total:** 25.8%

**Sample Messages:**
1. `2026-07-28T13:36:40.095001455-04:00 Output:       "/var/www/calls/pagefind"`
2. `2026-07-28T13:36:40.095003346-04:00`
3. `2026-07-28T13:36:40.095005482-04:00 [Walking source directory]`

### #2: http_504
**Occurrences:** 353
**Severity:** STATUS 504
**Percentage of Total:** 24.5%

**Sample Messages:**
1. `2026-07-28T21:30:04.825045978-04:00 [pbx-web] bucket changed (sig e86487b5 -> 196c52e2), rebuilding`
2. `2026-07-28T23:28:01.735950491-04:00 Output:       "/var/www/calls/pagefind"`
3. `2026-07-28T23:29:28.686050413-04:00 Discovered 1 language: en`

### #3: http_503
**Occurrences:** 349
**Severity:** STATUS 503
**Percentage of Total:** 24.3%

**Sample Messages:**
1. `2026-07-28T21:29:33.653408503-04:00`
2. `2026-07-28T21:29:42.889503040-04:00 Found 182 files matching **/*.{html}`
3. `2026-07-28T21:29:44.501503080-04:00`

### #4: http_502
**Occurrences:** 347
**Severity:** STATUS 502
**Percentage of Total:** 24.1%

**Sample Messages:**
1. `2026-07-28T13:37:29.514105025-04:00 [Building search indexes]`
2. `2026-07-28T13:38:48.475450285-04:00   Indexed 6967 words`
3. `2026-07-28T13:38:55.036250236-04:00 Source:       "/var/www/calls"`

### #5: connection_reset
**Occurrences:** 12
**Severity:** ERRNO 104
**Percentage of Total:** 0.8%

**Sample Messages:**
1. `2026-07-28T20:23:24.870819612-04:00 [pbx-web] recording fetch error for 1785277704.476/20260728-222824_442046157786_1785277704.476.wav: [Errno 104] Co`
2. `2026-07-28T20:23:24.872445550-04:00 ConnectionResetError: [Errno 104] Connection reset by peer`
3. `2026-07-28T22:58:58.425954166-04:00 [pbx-web] recording fetch error for 1785285870.480/20260729-004430_19148734884_1785285870.480.wav: [Errno 104] Con`

## Root Cause Analysis

### 1. High HTTP 5xx Error Rate (Severity: HIGH)
**Description:** 1420 server errors detected
**Error Patterns:** http_500, http_502, http_503, http_504

**Likely Causes:**
1. Upstream service timeouts during rebuild operations
2. Resource exhaustion during search indexing
3. Database connectivity issues
4. Application errors during bucket change rebuilds

### 2. Network Connection Issues (Severity: MEDIUM)
**Description:** 12 connection-related errors
**Error Patterns:** connection_reset

**Likely Causes:**
1. Upstream recording server connectivity issues
2. Network instability during recording fetch operations
3. Possible firewall or routing issues

## whisper-stt Service Health Analysis

**Overall Status:** HEALTHY
- **Total requests analyzed:** 98,251
- **Success rate:** 100.00%
- **Client errors (4xx):** 0
- **Server errors (5xx):** 0

**HTTP Status Distribution:**
- 200: 98,251 requests

## Cross-Service Comparison

### Key Findings
1. **Error Distribution Disparity:**
   - pbx-web shows significant error patterns (1,438 errors)
   - whisper-stt operates normally with minimal errors

2. **Service Complexity Impact:**
   - pbx-web: Complex service with database, search indexing, recording fetch
   - whisper-stt: Simpler health-focused service with stable operation

3. **Shared Infrastructure Health:**
   - Network connectivity appears stable (no widespread connection issues)
   - Kubernetes infrastructure healthy (both services running normally)

## Recommendations

### For pbx-web:
1. **Investigate rebuild operations** - High correlation between bucket changes and errors
2. **Review resource limits** - Consider CPU/memory during search indexing
3. **Implement circuit breakers** - Protect upstream recording fetch operations
4. **Add monitoring** - Alert on HTTP 5xx error thresholds

### For whisper-stt:
1. **Continue current operation** - Service is healthy and stable
2. **Monitor for changes** - Set baseline alerts for success rate drops

### General:
1. **Implement structured error logging** - Better categorization and tracking
2. **Set up SLO/SLI monitoring** - Track error rates and response times
3. **Regular health checks** - Automated monitoring for both services