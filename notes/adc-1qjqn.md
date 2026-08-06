# Metadata and Pattern Extraction Output Analysis

## Overview

This document analyzes the structure and format of three extraction outputs to understand how to combine them into a unified analysis framework.

## 1. Deployment Metadata Extraction

**Source:** `extract_deployment_metadata.py`  
**Output:** `notes/adc-yeect-deployment-metadata.json`

### Structure
```json
{
  "total_workflows": 29,
  "deployments": [...]
}
```

### Field Schema
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `workflow_name` | string | Workflow identifier | `"acb-build-dqhxq"` |
| `creationTimestamp` | ISO datetime | When workflow was created | `"2026-08-06T10:55:45Z"` |
| `phase` | string | Workflow status | `"Running"`, `"Failed"`, `"Succeeded"`, `"Error"` |
| `startedAt` | ISO datetime/null | When workflow started | `"2026-08-06T10:55:46Z"` or `null` |
| `finishedAt` | ISO datetime/null | When workflow completed | `"2026-08-06T11:27:55Z"` or `null` |
| `image_digest_tag` | string/null | Container image reference | `"ronaldraygun/spaxel"` or `null` |

### Key Characteristics
- **Flat structure:** Simple list of deployment records
- **Temporal focus:** Tracks workflow lifecycle timestamps
- **Limited context:** Only basic workflow metadata, no failure details
- **Sparse data:** Many fields are `null` (especially `image_digest_tag`)

---

## 2. Analysis Pattern Extraction

**Source:** `extract_analysis_patterns.py`  
**Output:** `data/analysis-patterns-extracted.json`

### Structure
```json
[
  {
    "log_file_path": "...",
    "pod_name": "...",
    "namespace": "...",
    "analysis_file_path": "...",
    "detected_patterns": [...],
    "key_timestamps": {...}
  }
]
```

### Field Schema
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `log_file_path` | string | Path to log file | `"pbx-web-30days/pod-logs/..."` |
| `pod_name` | string | Pod identifier | `"pbx-web-5ff68464d-mkn8n"` |
| `namespace` | string | Kubernetes namespace | `"pbx-web"`, `"whisper-stt"` |
| `analysis_file_path` | string/null | Path to analysis JSON | `"research/pbx-web-30days/..."` or `null` |
| `detected_patterns` | array | List of pattern types | `["error"]`, `["startup", "oom_kill"]`, `[]` |
| `key_timestamps` | object/null | Timestamp mapping | See below or `null` |

### Pattern Types
The `detected_patterns` array can contain:
- `"startup"` - Startup-related patterns
- `"oom_kill"` - Out of memory kill events
- `"error"` - Error patterns
- `"performance"` - Performance-related patterns

### Key Timestamps Structure
```json
{
  "analysis_date": "2026-08-06T13:40:21.623256",
  "log_file": "pbx-web-5ff68464d-mkn8n.log",
  "error_first": "1785277704",
  "error_last": "unknown",
  "startup_first": "1785277600",
  "startup_last": "1785277800"
}
```

### Key Characteristics
- **Log-centric:** Focuses on pod log analysis
- **Pattern detection:** Identifies specific behavioral patterns
- **Sparse patterns:** Most entries have empty `detected_patterns`
- **Missing analysis:** Some entries lack corresponding analysis files (`null` values)

---

## 3. Failure Pattern Extraction

**Source:** `extract_failure_patterns.py`  
**Output:** `docs/research/failure-patterns-intermediate.json`

### Structure
```json
{
  "metadata": {...},
  "failure_categories": {
    "technical_failures": {...},
    "configuration_issues": {...},
    "operational_patterns": {...},
    "positive_patterns": {...},
    "absent_failure_modes": {...}
  },
  "rankings": {
    "by_frequency": [...],
    "by_severity": {...}
  }
}
```

### Top-Level Metadata
| Field | Description | Example |
|-------|-------------|---------|
| `extraction_date` | When extraction was performed | `"2026-08-06T12:35:44.959855"` |
| `analysis_period` | Time range covered | `"2026-07-07 to 2026-08-06 (30 days)"` |
| `services_analyzed` | List of services | `["pbx-web", "whisper-stt"]` |
| `cluster` | Kubernetes cluster name | `"ardenone-cluster"` |

### Failure Pattern Schema
Each pattern object contains:
| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Pattern name (e.g., "Health Check/Probe Failure") |
| `service` | string | Service name (pbx-web, whisper-stt) |
| `count` | number | Occurrence frequency |
| `severity` | string | Impact level (high, medium, low, info, positive) |
| `description` | string | Human-readable explanation |
| `date` | string/null | ISO date or "N/A" |
| `resolution` | string/null | How it was resolved |
| `root_cause` | string/null | Underlying cause |
| `evidence` | string | Supporting evidence text |

### Failure Categories
1. **technical_failures** - Deployment failures due to technical issues
2. **configuration_issues** - Configuration drift or mismatches
3. **operational_patterns** - Deployment velocity and operational patterns
4. **positive_patterns** - Patterns indicating stability and reliability
5. **absent_failure_modes** - Failure types that did not occur (good practices)

### Rankings Structure
- **by_frequency:** Array of patterns sorted by occurrence count
- **by_severity:** Object with severity keys (high, medium, low, info, positive), each containing an array of patterns

### Key Characteristics
- **High-level aggregation:** Summarized patterns, not raw events
- **Rich context:** Includes severity, resolution, root cause
- **Categorized:** Organized into logical failure categories
- **Evidence-backed:** Each pattern includes supporting evidence
- **Multi-dimensional rankings:** Sortable by frequency and severity

---

## Field Comparison and Overlaps

### Common Fields Across All Three
| Field Concept | Metadata | Analysis Patterns | Failure Patterns |
|---------------|-----------|-------------------|------------------|
| Time/Date | ✅ creationTimestamp, startedAt, finishedAt | ✅ analysis_date, pattern timestamps | ✅ extraction_date, pattern date |
| Service/Target | ❌ (workflow name only) | ✅ namespace, pod_name | ✅ service |
| Status/Pattern | ✅ phase (Running/Failed/etc) | ✅ detected_patterns | ✅ type, severity |
| Evidence | ❌ | ✅ log_file_path | ✅ evidence, description |

### Unique Fields by Output

#### Metadata Only
- `workflow_name` - Workflow identifier
- `image_digest_tag` - Container image reference
- `phase` - Workflow execution status

#### Analysis Patterns Only
- `log_file_path` - Path to log file
- `pod_name` - Pod identifier
- `namespace` - Kubernetes namespace
- `analysis_file_path` - Path to analysis JSON
- Pattern-specific timestamps (`error_first`, `startup_last`, etc.)

#### Failure Patterns Only
- `count` - Pattern occurrence frequency
- `severity` - Impact level (high/medium/low/info/positive)
- `resolution` - How the issue was resolved
- `root_cause` - Underlying cause analysis
- `category` - Logical grouping (technical_failures, etc.)
- `rankings` - Sorted views by frequency and severity

---

## Integration Strategy

### 1. Temporal Alignment
- **Metadata:** Workflow lifecycle timestamps → **Deployment Events**
- **Analysis Patterns:** Log analysis timestamps → **Runtime Events**
- **Failure Patterns:** Aggregated timestamps → **Incident Timeline**

### 2. Entity Mapping
- **Workflow name** (metadata) → **Pod name** (analysis patterns) via deployment relationships
- **Service** (failure patterns) → **Namespace** (analysis patterns) via service-to-namespace mapping
- **Phase** (metadata) + **detected_patterns** (analysis) → **Failure type** (failure patterns)

### 3. Semantic Enrichment
- **Metadata** provides deployment context (when, what, status)
- **Analysis patterns** provides runtime evidence (logs, patterns, timestamps)
- **Failure patterns** provides high-level insights (severity, root cause, resolution)

### 4. Proposed Unified Schema

```json
{
  "metadata": {
    "extraction_date": "ISO datetime",
    "analysis_period": "date range",
    "services": ["pbx-web", "whisper-stt"],
    "cluster": "ardenone-cluster"
  },
  "events": [
    {
      "event_id": "unique-id",
      "timestamp": "ISO datetime",
      "event_type": "deployment|runtime|incident",
      
      // Deployment context (from metadata)
      "deployment": {
        "workflow_name": "...",
        "phase": "Running|Failed|Succeeded|Error",
        "image_digest_tag": "...",
        "startedAt": "ISO datetime",
        "finishedAt": "ISO datetime"
      },
      
      // Runtime evidence (from analysis patterns)
      "runtime": {
        "pod_name": "...",
        "namespace": "...",
        "log_file_path": "...",
        "detected_patterns": ["error", "startup"],
        "pattern_timestamps": {
          "error_first": "...",
          "error_last": "..."
        }
      },
      
      // Incident insights (from failure patterns)
      "incident": {
        "type": "Health Check/Probe Failure",
        "severity": "high|medium|low|info|positive",
        "category": "technical_failures",
        "description": "...",
        "resolution": "...",
        "root_cause": "...",
        "evidence": "..."
      }
    }
  ],
  "rankings": {
    "by_frequency": [...],
    "by_severity": {...}
  }
}
```

---

## Next Steps

1. **Create mapping logic:** Link workflow names to pod names via deployment events
2. **Temporal correlation:** Align deployment events with runtime patterns and incidents
3. **Implement merger:** Build unified extraction script that combines all three
4. **Validate consistency:** Ensure no data loss during combination
5. **Generate reports:** Produce unified analysis reports from combined data

---

## Summary

- **Metadata extraction** provides deployment lifecycle context but lacks runtime details
- **Analysis patterns** provides granular runtime evidence but is sparse and unaggregated  
- **Failure patterns** provides high-level insights but is disconnected from raw events

Combining these outputs will create a comprehensive view linking deployments → runtime behavior → failure insights, enabling root cause analysis and predictive monitoring.
