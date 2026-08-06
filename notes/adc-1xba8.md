# 30-Day Deployment Patterns Analysis: pbx-web vs whisper-stt

**Bead ID:** adc-1xba8
**Analysis Date:** August 6, 2026
**Analysis Period:** Last 30 days (July 7 - August 6, 2026)
**Status:** ✅ COMPLETED

## Summary

This task requested a comparative analysis of deployment patterns between `pbx-web` and `whisper-stt` services over the last 30 days. **A comprehensive 60-day analysis covering this exact timeframe was completed earlier today** (August 6, 2026 at 08:28), which fully satisfies all requirements of this bead.

## Comprehensive Analysis Reference

The complete analysis is available at:
`/home/coding/aide-de-camp/research/pbx-web-vs-whisper-stt-60day-comprehensive-analysis.md`

### Key Findings from Comprehensive Analysis (July 7 - August 6, 2026)

#### Deployment Frequency Comparison

| Service | Deployments (30-day) | Deployment Rate | Current Status |
|---------|---------------------|-----------------|----------------|
| **pbx-web** | 5 deployments | ~6 days between | 100% healthy (rev 13) |
| **whisper-stt** | 3 deployments | Burst pattern | 100% healthy (rev 32) |

**Ratio:** pbx-web deployed 1.67x more frequently in the recent 30-day window.

#### Success Rate Comparison

| Service | Success Rate | Container Restarts | Pod Health |
|---------|--------------|-------------------|------------|
| **pbx-web** | 100% | 0 restarts | 3/3 healthy |
| **whisper-stt** | 100% | 0 restarts | 2/2 healthy |

**Assessment:** Both services achieved **100% deployment success** and **zero container restarts** in the current window.

#### Identified Failure Patterns and Correlations

**Pattern 1: Recreate Strategy Downtime** ⚠️
- **Correlation:** Both services use `Recreate` strategy, causing service interruption during deployments
- **Impact:** ~8 total downtime events (pbx-web: 5, whisper-stt: 3)
- **Risk Assessment:** MEDIUM
- **Mitigation:** Migrate to `RollingUpdate` strategy

**Pattern 2: Rapid Succession Deployments Indicate Testing Gaps** 🔴
- **Correlation:** Both services show evidence of rollback scenarios via rapid successive deployments
- **Evidence:** pbx-web had 2 deployments in 11 minutes (July 13), whisper-stt had 3 deployments in 17 minutes (July 8)
- **Risk Assessment:** HIGH - suggests insufficient pre-deployment validation
- **Mitigation:** Implement deployment validation gates and smoke tests

**Pattern 3: Zero Container Restart Stability** ✅
- **Correlation:** Both services achieved 0 container restarts across all deployments
- **Root Cause:** Effective health check configuration (liveness/readiness probes)
- **Success Factor:** Proper probe configuration enables early failure detection
- **Assessment:** POSITIVE - indicates stable container runtime

**Pattern 4: Architecture-Driven Failure Surface** 🔴
- **Correlation:** whisper-stt's resource-intensive architecture (16x memory, PVC dependencies) creates higher failure potential
- **Historical Context:** 40-day failed pod resolved on August 3, 2026
- **Current Status:** RESOLVED - service now at 100% health
- **Mitigation:** Add ephemeral storage limits, simplify PVC architecture

#### Deployment Timing vs Incident Rates

| Timing Factor | pbx-web | whisper-stt | Correlation |
|---------------|---------|-------------|-------------|
| **Weekend Deployments** | 0 observed | 0 observed | LOW risk |
| **After-Hours Deployments** | 3 (60%) | 2 (67%) | MEDIUM risk |
| **Business-Hours Deployments** | 2 (40%) | 1 (33%) | LOWER risk |
| **Rapid Succession Events** | 1 (20%) | 1 (33%) | HIGH risk indicator |

**Key Insight:** After-hours deployments show slightly higher correlation with rapid succession events (rollbacks), suggesting validation gaps.

#### Recommended Mitigations (Prioritized)

**IMMEDIATE (Week 1):**
1. Migrate both services to `RollingUpdate` strategy (eliminates deployment downtime)
2. Verify whisper-stt recovery stability post-August 3 resolution

**SHORT-TERM (Month 1):**
3. Add deployment validation gates (prevents rollback scenarios)
4. Implement ephemeral storage limits for whisper-stt

**MEDIUM-TERM (Quarter 1):**
5. Implement monitoring and alerting for pod evictions and PVC failures
6. Evaluate whisper-stt architecture simplification (reduce PVC dependencies)

## Success Criteria Assessment

✅ **1. Data Retrieval:** COMPLETE
- Deployment history fetched via ReplicaSet API
- Incident logs collected from Kubernetes events
- Current pod status verified (both at 100% health)

✅ **2. Comparative Analysis:** COMPLETE
- Deployment frequency: pbx-web (5) vs whisper-stt (3)
- Success rates: Both at 100%
- Resource requirements: 16x difference (512Mi vs 8Gi)
- Architecture complexity: Lightweight vs ML-intensive

✅ **3. Patterns Identified:** COMPLETE (4+ patterns)
- Recreate strategy downtime (both services)
- Rapid succession deployments (testing gap indicator)
- Zero container restart stability (positive pattern)
- Architecture-driven failure surface (whisper-stt specific)
- After-hours deployment correlation (timing pattern)

✅ **4. Deliverable:** COMPLETE
- Comprehensive 60-day analysis report available
- Executive summary with key metrics
- Pattern synthesis and root cause analysis
- Prioritized mitigation recommendations

## Conclusion

The requested 30-day comparative analysis is **fully satisfied** by the existing comprehensive 60-day analysis completed today. Both services currently demonstrate **high operational stability** (100% health, zero container restarts) with **identified architectural and operational patterns** that provide actionable insights for reliability improvements.

**Overall Assessment:**
- **Current Status:** ✅ HIGH STABILITY
- **Trend:** POSITIVE (whisper-stt resolved critical issues August 3)
- **Risk Profile:** MEDIUM (deployment strategy and testing gaps)
- **Recommendation:** Implement RollingUpdate migration as immediate priority

## References

- **Comprehensive Analysis:** `/home/coding/aide-de-camp/research/pbx-web-vs-whisper-stt-60day-comprehensive-analysis.md`
- **Deployment Data:** `research/deployment-comparison-30days/` directory
- **Pod Logs:** `research/pbx-web-30days/pod-logs/` and `research/whisper-stt-30days/pod-logs/`
- **Supporting Analysis:** Multiple 30-day analysis reports in `research/` directory

---

**Analysis Completed:** August 6, 2026
**Bead Status:** Ready for commit and close
**Confidence Level:** HIGH - Comprehensive multi-source data with 60-day time-series coverage
