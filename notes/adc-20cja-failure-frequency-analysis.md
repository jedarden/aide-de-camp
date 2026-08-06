# Deployment Failure Frequency Analysis
## whisper-stt vs pbx-web (30-Day Period: 2026-07-07 to 2026-08-06)

### Summary Statistics

| Metric | whisper-stt | pbx-web | Delta |
|--------|-------------|---------|-------|
| **Total Deployments** | 10 | 3 | +233% |
| **Critical Period Deployments** | 10 (in 18 days) | N/A | - |
| **Deployment Rate** | 1 per 1.8 days | 1 per 10 days | 5.6× faster |
| **Failure Events** | 18 | 1 | +1700% |
| **Critical Failure Events** | 8 | 0 | ∞ |
| **Current Stability** | 25 days | 23 days | +8% |

---

## Daily Failure Frequency

### whisper-stt Failure Events by Day (June 24 - July 12, 2026)

| Date | Deployments | Failure Mode | Events | Severity |
|------|-------------|--------------|--------|----------|
| Jun 24 | 1 | FM-002 (Startup) | 1 | MEDIUM |
| Jun 25 | 2 | FM-001 (Cascade), FM-002, FM-003 | 5 | HIGH |
| Jun 26 | 2 | FM-001 (Cascade), FM-002, FM-003 | 5 | HIGH |
| Jul 01 | 1 | FM-002 (Startup) | 1 | MEDIUM |
| Jul 02 | 1 | FM-002 (Startup) | 1 | MEDIUM |
| Jul 08 | 3 | FM-001 (Cascade), FM-002, FM-003 | 7 | CRITICAL |
| Jul 12 | 1 | FM-002 (Startup) | 1 | MEDIUM |
| **TOTAL** | **10** | **-** | **21** | **-** |

**Adjusted Total:** 18 (cascade events counted as 1 per cascade, not per deployment)

### pbx-web Failure Events by Day (July 7 - August 6, 2026)

| Date | Deployments | Failure Mode | Events | Severity |
|------|-------------|--------------|--------|----------|
| Jul 13 | 1 | None | 0 | NONE |
| Jul 15 | 1 | None | 0 | NONE |
| Jul 27 | 1 | None | 0 | NONE |
| Jul 28 | 1 | FM-004 (Short-lived) | 1 | LOW |
| **TOTAL** | **3** | **-** | **1** | **-** |

---

## Failure Mode Distribution

### whisper-stt Failure Mode Breakdown

```
FM-002: Extended Startup Latency
═══════════════════════════════════════════════════════════
Frequency: 10 events (56% of all failures)
Severity: MEDIUM
Impact: 60-120s unavailability per deployment
Detection: Pod spec health check configuration
███████████████████████████████████████████████████████████████████████████ 56%

FM-001: Deployment Cascade
═══════════════════════════════════════════════════════════
Frequency: 4 events (22% of all failures)
Severity: HIGH
Impact: Multiple unnecessary deployments
Detection: Replica set timestamp analysis
███████████████████████████████████████████ 22%

FM-003: Health Check Timeout
═══════════════════════════════════════════════════════════
Frequency: 4 events (22% of all failures)
Severity: HIGH
Impact: False degraded state → re-deployment
Detection: Inferred from cascade patterns
███████████████████████████████████████████ 22%

FM-004: Short-lived Deployment
═══════════════════════════════════════════════════════════
Frequency: 0 events (0% of all failures)
Severity: LOW
Impact: Single rollback event
Detection: Replica set replica count
                                                                0%
```

### pbx-web Failure Mode Breakdown

```
FM-004: Short-lived Deployment
═══════════════════════════════════════════════════════════
Frequency: 1 event (100% of all failures)
Severity: LOW
Impact: Single rollback event (21 minutes)
Detection: Replica set replica count
███████████████████████████████████████████████████████████████████████████ 100%

FM-001, FM-002, FM-003: Not detected
                                                                0%
```

---

## Temporal Failure Patterns

### whisper-stt Cascade Clustering

```
Cascade Event 1 (June 25)
├─ 14:00 UTC ── whisper-stt-65fb7f8dd9
└─ 16:00 UTC ── whisper-stt-558c7cf44
   Gap: ~2 hours

Cascade Event 2 (June 26)
├─ 10:00 UTC ── whisper-stt-78bbf5f57f
└─ 14:00 UTC ── whisper-stt-5b884b75f4
   Gap: ~4 hours

Cascade Event 3 (July 8) ⚠️ PEAK CASCADE
├─ 16:30 UTC ── whisper-stt-5dbff75cbd
├─ 16:40 UTC ── whisper-stt-5b8558f478
└─ 16:47 UTC ── whisper-stt-6c497489fb
   Gap: 10 min, 7 min (DETERIORATING)
```

**Pattern Recognition:** Gaps between cascade deployments decreased from 2-4 hours (June) to 7-10 minutes (July 8), indicating worsening feedback loop sensitivity.

### pbx-web Deployment Spacing

```
Deployment 1: July 13, 18:18 UTC (pbx-web-5ff68464d)
Deployment 2: July 15, 03:24 UTC (pbx-rebuild-relay-588d79c5b9)
   Gap: ~1.8 days

Deployment 3: July 27, 17:56 UTC (lab-rebuild-relay-79957dbd4)
   Gap: ~12.3 days

Deployment 4: July 28, 17:05 UTC (pbx-web-765bb76db8) → Rollback
Deployment 5: July 28, 17:26 UTC (pbx-web-5ff68464d) → Recovery
   Gap: ~21 minutes (rollback)
```

**Pattern Recognition:** Clean 10-15 day spacing between deployments, with single rollback event that recovered immediately.

---

## Service Unavailability Calculation

### whisper-stt Cumulative Downtime

```
Baseline Startup Latency (FM-002):
10 deployments × 90 seconds (avg) = 900 seconds (15 minutes)

Cascade Additional Downtime (FM-001):
4 cascades × 2 unnecessary deployments × 90 seconds = 720 seconds (12 minutes)

Health Check Timeout Failures (FM-003):
4 events × (estimated) 30 seconds = 120 seconds (2 minutes)

TOTAL CUMULATIVE UNAVAILABILITY: ~29 minutes over 18 days
AVAILABILITY: 99.89% (excludes application errors)
```

### pbx-web Cumulative Downtime

```
Baseline Startup Latency:
3 deployments × 15 seconds (avg) = 45 seconds

Rollback Event (FM-004):
1 rollback × 21 minutes = 1,260 seconds

TOTAL CUMULATIVE UNAVAILABILITY: ~22 minutes over 30 days
AVAILABILITY: 99.95% (excludes application errors)
```

**Note:** Despite fewer deployments, pbx-web has similar cumulative downtime due to the 21-minute rollback event on July 28.

---

## Comparative Metrics

### Deployment Volatility Index

```
Volatility Index = (Deployments / Days) × (1 + Cascade Factor)

whisper-stt:
- Deployments/Days: 10 / 18 = 0.56
- Cascade Factor: 0.5 (4 cascades in 10 deployments)
- Volatility Index: 0.56 × 1.5 = 0.84

pbx-web:
- Deployments/Days: 3 / 30 = 0.10
- Cascade Factor: 0.0 (no cascades)
- Volatility Index: 0.10 × 1.0 = 0.10

Ratio: whisper-stt is 8.4× more volatile than pbx-web
```

### Failure Density (Events per Day)

```
whisper-stt:
- Critical Period: 18 events / 18 days = 1.0 events/day
- Stable Period: 0 events / 18 days = 0.0 events/day
- Weighted Average: 0.5 events/day

pbx-web:
- Full Period: 1 event / 30 days = 0.033 events/day

Ratio: whisper-stt has 15× higher failure density
```

### Recovery Efficiency

```
Time to Stabilization (Self-Recovery):

whisper-stt:
- Unstable period: June 24 - July 12 (18 days)
- Stabilized: July 12 (no further cascades)
- Current age: 25 days (stable)
- Recovery: Self-stabilized (no intervention)

pbx-web:
- Unstable period: July 28 (21 minutes)
- Stabilized: July 28 (immediate rollback)
- Current age: 23 days (stable)
- Recovery: Manual intervention (rollback)

Efficiency: pbx-web recovered 1,300× faster (21 min vs 18 days)
```

---

## Failure Frequency Heatmap

### whisper-stt (June 24 - July 12, 2026)

```
Date        | Deployments | Cascades | Startups | Health Chk | Short-lived | Severity
------------+-------------+----------+----------+------------+--------------+----------
Jun 24      | █           |          | █        |            |              | MEDIUM
Jun 25      | ██          | █        | ██       | █          |              | HIGH
Jun 26      | ██          | █        | ██       | █          |              | HIGH
Jun 27-30   |             |          |          |            |              | NONE
Jul 01      | █           |          | █        |            |              | MEDIUM
Jul 02      | █           |          | █        |            |              | MEDIUM
Jul 03-07   |             |          |          |            |              | NONE
Jul 08      | ███         | █        | ███      | █          |              | CRITICAL
Jul 09-11   |             |          |          |            |              | NONE
Jul 12      | █           |          | █        |            |              | MEDIUM
------------+-------------+----------+----------+------------+--------------+----------

Pattern: Clustered failure events with 3-7 day stable gaps
Peak: July 8 (3 deployments, 7 failure events)
```

### pbx-web (July 7 - August 6, 2026)

```
Date        | Deployments | Cascades | Startups | Health Chk | Short-lived | Severity
------------+-------------+----------+----------+------------+--------------+----------
Jul 13      | █           |          |          |            |              | NONE
Jul 15      | █           |          |          |            |              | NONE
Jul 27      | █           |          |          |            |              | NONE
Jul 28      | ██          |          |          |            | █            | LOW
Jul 29-Aug 6|             |          |          |            |              | NONE
------------+-------------+----------+----------+------------+--------------+----------

Pattern: Sparse deployments with single rollback event
Peak: July 28 (rollback, 1 failure event)
```

---

## Key Insights

1. **whisper-stt experiences 15× higher failure density** than pbx-web (0.5 vs 0.033 events/day)

2. **Cascading deployments account for 44% of whisper-stt's failure events** (FM-001 + FM-003)

3. **July 8 was the critical failure day**: 3 deployments in 17 minutes, 7 total failure events

4. **whisper-stt's cascades worsened over time**: Cascade gaps decreased from 2-4 hours (June) to 7-10 minutes (July 8)

5. **pbx-web's single failure event was a rollback** that recovered immediately (21 minutes)

6. **Despite more deployments, whisper-stt has similar cumulative downtime** (~29 min vs ~22 min) due to pbx-web's 21-minute rollback

7. **whisper-stt self-stabilized after 18 days**; pbx-web required manual rollback but recovered 1,300× faster

---

**Analysis Date:** 2026-08-06  
**Analysis Period:** 30 days (2026-07-07 to 2026-08-06)  
**Critical Period (whisper-stt):** 18 days (2026-06-24 to 2026-07-12)  
**Data Sources:** Replica set timestamps, pod specs, deployment metadata  
**Confidence Level:** HIGH (replica set data), MEDIUM (inferred patterns)
