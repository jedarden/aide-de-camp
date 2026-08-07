# Failure Pattern Taxonomy

*Generated from deployment data analysis*

**Analysis Date:** 2026-08-06T21:27:15.637599
**Total Patterns:** 6
**Total Failures Analyzed:** 0

## Service Statistics

| Service | Total Events | Failures | Successes |
|---------|--------------|----------|-----------|
| pbx-web | 5 | 0 | 4 |
| whisper-stt | 4 | 0 | 4 |

## Pattern Categories

### ImagePullBackOff

**Description:** Container image cannot be pulled from registry (authentication issues, missing images, network problems)
**Severity:** high

**Statistics:**
- Frequency: 0 occurrences
- Time span: 0 days
- First occurrence: unknown
- Last occurrence: unknown

---


### CrashLoopBackOff

**Description:** Pod repeatedly crashes and restarts (application errors, misconfiguration, runtime exceptions)
**Severity:** critical

**Statistics:**
- Frequency: 0 occurrences
- Time span: 0 days
- First occurrence: unknown
- Last occurrence: unknown

---


### OOMKilled

**Description:** Container killed due to exceeding memory limits (memory leaks, insufficient limits, high load)
**Severity:** critical

**Statistics:**
- Frequency: 0 occurrences
- Time span: 0 days
- First occurrence: unknown
- Last occurrence: unknown

---


### Probe_failure

**Description:** Health check failures (readiness, liveness, or startup probes failing)
**Severity:** medium

**Statistics:**
- Frequency: 0 occurrences
- Time span: 0 days
- First occurrence: unknown
- Last occurrence: unknown

---


### Dependency_timeout

**Description:** Timeouts connecting to external services (databases, APIs, network services)
**Severity:** high

**Statistics:**
- Frequency: 0 occurrences
- Time span: 0 days
- First occurrence: unknown
- Last occurrence: unknown

---


### Other

**Description:** Uncategorized or rare failure patterns not matching standard categories
**Severity:** variable

**Statistics:**
- Frequency: 0 occurrences
- Time span: 0 days
- First occurrence: unknown
- Last occurrence: unknown

---

