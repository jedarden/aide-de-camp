# Component Pattern Documentation

## Overview

This document catalogs all `result_type` → `component_id` mappings and layout patterns discovered in the aide-de-camp codebase.

## Result Type Derivation

Result types are derived deterministically in `src/render/hot_path.py`:

```python
def derive_result_type(intent_type, project_slug, lookup_kind=None) -> str:
    # Format: "{intent_type}:{project_slug}"
    # Lookup format: "lookup:{lookup_kind}:{project_slug}"
    # Monitoring format: "monitoring:{project_slug}"
    # Default: "general" when project_slug is missing
```

**Examples:**
- `status:kubernetes` - Kubernetes status with project slug "kubernetes"
- `lookup:logs:ibkr-mcp` - Logs lookup for ibkr-mcp project
- `lookup:config:adc` - Config lookup for aide-de-camp project
- `monitoring:apexalgo-iad` - Monitoring for apexalgo-iad cluster
- `status:general` - Generic status (no project slug)

## Layout Buckets

Three layout buckets are defined in `src/components/library.py`:

1. **compact** - Dense, minimal layout
2. **normal** - Standard layout (default)
3. **expanded** - Detailed, spacious layout

## Component Selection Logic

The hot-path renderer (`src/render/hot_path.py`) uses deterministic selection:

```python
# Selection algorithm (no LLM):
# 1. Query component_usage_patterns for result_type + layout_bucket
# 2. Order by match_score DESC, sample_count DESC
# 3. Return first row where match_score >= threshold (default 0.7)
# 4. If no match, use built-in generic fallback card
```

**Key constraint:** The hot path NEVER generates components or uses semantic search - it only reads recorded mappings from `component_usage_patterns`.

## Baseline Components

Migration 003 (`src/components/seed_migration.py`) defines 10 baseline components:

| Component ID | Name | Description | Template Fields |
|--------------|------|-------------|-----------------|
| `comp-k8s-status` | kubernetes-status | Kubernetes pod and deployment status | `{{summary}}`, `{{pods}}` |
| `comp-git-status` | git-status | Git repository status | `{{summary}}`, `{{branch}}`, `{{files_changed}}` |
| `comp-ci-status` | ci-status | CI/CD workflow status | `{{summary}}`, `{{workflow_name}}`, `{{status}}` |
| `comp-action-card` | action-card | General action card for operations | `{{summary}}`, `{{action_hint}}`, `{{urgency}}` |
| `comp-logs-viewer` | logs-viewer | Log viewer and search card | `{{summary}}`, `{{logs}}`, `{{timestamp}}` |
| `comp-config-viewer` | config-viewer | Configuration file viewer | `{{summary}}`, `{{config_data}}` |
| `comp-monitoring-card` | monitoring-card | Monitoring and metrics card | `{{summary}}`, `{{metrics}}`, `{{alerts}}` |
| `comp-generic-status` | generic-status | Generic fallback status card | `{{summary}}`, `{{data}}` |
| `comp-generic-action` | generic-action | Generic fallback action card | `{{summary}}`, `{{action_hint}}` |
| `comp-generic-lookup` | generic-lookup | Generic fallback lookup card | `{{summary}}`, `{{lookup_result}}` |

## Complete Seed Pattern Mappings

### Kubernetes Status Patterns

| Result Type | Component ID | Layout Bucket | Match Score | Sample Count |
|-------------|--------------|----------------|--------------|--------------|
| `status:kubernetes` | `comp-k8s-status` | normal | 0.95 | 10 |
| `status:kubernetes` | `comp-k8s-status` | compact | 0.90 | 5 |
| `status:kubernetes` | `comp-k8s-status` | expanded | 0.92 | 8 |

**Notes:** Highest confidence (0.95) in normal layout for Kubernetes status.

### Git Status Patterns

| Result Type | Component ID | Layout Bucket | Match Score | Sample Count |
|-------------|--------------|----------------|--------------|--------------|
| `status:git` | `comp-git-status` | normal | 0.93 | 15 |
| `status:git` | `comp-git-status` | compact | 0.88 | 7 |

**Notes:** Git status strongly prefers normal layout; compact layout has lower confidence.

### CI/CD Status Patterns

| Result Type | Component ID | Layout Bucket | Match Score | Sample Count |
|-------------|--------------|----------------|--------------|--------------|
| `status:ci` | `comp-ci-status` | normal | 0.91 | 12 |
| `status:ci` | `comp-ci-status` | expanded | 0.94 | 6 |

**Notes:** CI status actually has higher confidence (0.94) in expanded layout despite fewer samples.

### Action Card Patterns

| Result Type | Component ID | Layout Bucket | Match Score | Sample Count |
|-------------|--------------|----------------|--------------|--------------|
| `action:general` | `comp-action-card` | normal | 0.85 | 20 |
| `action:general` | `comp-action-card` | compact | 0.82 | 10 |

**Notes:** Action cards have moderate confidence (0.85) and work well in both normal and compact layouts.

### Log Viewer Patterns

| Result Type | Component ID | Layout Bucket | Match Score | Sample Count |
|-------------|--------------|----------------|--------------|--------------|
| `lookup:logs:general` | `comp-logs-viewer` | expanded | 0.96 | 25 |
| `lookup:logs:general` | `comp-logs-viewer` | normal | 0.94 | 18 |

**Notes:** Log viewing has the highest confidence (0.96) in expanded layout, with extensive sampling (25).

### Configuration Viewer Patterns

| Result Type | Component ID | Layout Bucket | Match Score | Sample Count |
|-------------|--------------|----------------|--------------|--------------|
| `lookup:config:general` | `comp-config-viewer` | normal | 0.89 | 14 |

**Notes:** Config viewing only has normal layout mappings with moderate-high confidence.

### Monitoring Patterns

| Result Type | Component ID | Layout Bucket | Match Score | Sample Count |
|-------------|--------------|----------------|--------------|--------------|
| `monitoring:kubernetes` | `comp-monitoring-card` | normal | 0.92 | 8 |
| `monitoring:kubernetes` | `comp-monitoring-card` | expanded | 0.95 | 5 |

**Notes:** Similar to CI status, monitoring has higher confidence (0.95) in expanded layout.

### Generic Fallback Patterns

| Result Type | Component ID | Layout Bucket | Match Score | Sample Count |
|-------------|--------------|----------------|--------------|--------------|
| `status:general` | `comp-generic-status` | normal | 0.70 | 30 |
| `action:general` | `comp-generic-action` | normal | 0.70 | 25 |
| `lookup:general` | `comp-generic-lookup` | normal | 0.70 | 20 |

**Notes:** These are fallback patterns at the threshold (0.70) - they only match when no better component exists.

## Pattern Confidence Distribution

**High Confidence (≥0.95):**
- `lookup:logs:general` → `comp-logs-viewer` (expanded): 0.96
- `monitoring:kubernetes` → `comp-monitoring-card` (expanded): 0.95
- `status:kubernetes` → `comp-k8s-status` (normal): 0.95

**Good Confidence (0.85-0.94):**
- `status:ci` → `comp-ci-status` (expanded): 0.94
- `status:git` → `comp-git-status` (normal): 0.93
- `lookup:logs:general` → `comp-logs-viewer` (normal): 0.94
- `monitoring:kubernetes` → `comp-monitoring-card` (normal): 0.92
- `status:kubernetes` → `comp-k8s-status` (expanded): 0.92
- `status:ci` → `comp-ci-status` (normal): 0.91
- `lookup:config:general` → `comp-config-viewer` (normal): 0.89
- `action:general` → `comp-action-card` (normal): 0.85

**Moderate Confidence (0.70-0.84):**
- `status:kubernetes` → `comp-k8s-status` (compact): 0.90
- `status:git` → `comp-git-status` (compact): 0.88
- `action:general` → `comp-action-card` (compact): 0.82
- All generic fallback patterns: 0.70

## Layout Bucket Usage Patterns

**Expanded Layout:**
- Preferred for: logs viewing (0.96), CI status (0.94), monitoring (0.95)
- Use case: Detailed data requiring space for readability
- Components: `comp-logs-viewer`, `comp-ci-status`, `comp-monitoring-card`

**Normal Layout (Default):**
- Most common bucket for all component types
- Use case: Standard information display
- All baseline components have normal layout mappings

**Compact Layout:**
- Used for: Kubernetes status (0.90), git status (0.88), action cards (0.82)
- Use case: Summaries and overviews where space is at a premium
- Components: `comp-k8s-status`, `comp-git-status`, `comp-action-card`

## Template Placeholder Syntax

All templates use flat `{{field.path}}` substitution (defined in `src/render/hot_path.py`):

```python
# Examples:
{{summary}}              # Top-level field
{{pods}}                 # Top-level field
{{logs.0.message}}       # Nested list access (first log message)
{{config.data.api_key}}  # Nested dict access
```

**Escaping boundary:** All interpolated values are HTML-escaped at fill time for security.

## Diff Engine Result Type Inference

The diff engine (`src/diff/engine.py`) defines significant fields for result type comparison:

| Result Type | Significant Fields |
|-------------|-------------------|
| `status` | phase, health, ready, sync_status, restart_count, age |
| `pod_status` | phase, ready, restarts, age |
| `argo_status` | sync_status, health_status, revision |
| `ci_status` | phase, message, started_at, finished_at |
| `git_log` | commit_count, latest_commit, latest_author |
| `bead_list` | open_count, closed_count, latest_bead_id |
| `generic` | (no specific fields) |

## Database Schema

### component_usage_patterns Table

```sql
CREATE TABLE component_usage_patterns (
    result_type TEXT NOT NULL,          -- e.g., "status:ibkr-mcp", "lookup:logs:adc"
    component_id TEXT NOT NULL,
    layout_bucket TEXT NOT NULL DEFAULT 'normal',
    match_score REAL NOT NULL,          -- 0-1, selection threshold default 0.7
    sample_count INTEGER NOT NULL DEFAULT 1,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (result_type, component_id, layout_bucket)
);
```

**Index:** `idx_component_usage_patterns_match_score` on `match_score DESC`

## Selection Threshold

- **Default match threshold:** 0.7 (defined in `src/render/hot_path.py`)
- Result types with scores below 0.7 fall through to the built-in generic fallback card
- The fallback ensures the canvas never blanks - even novel result shapes render

## Usage Pattern Tracking

When the hot path matches a component:

```python
# src/render/hot_path.py:160
self.library.record_usage_pattern(
    component.id, 
    result_type, 
    match_score=1.0,  # Hot-path matches record at 1.0
    layout_bucket=bucket
)
```

This updates the running average in `component_usage_patterns`:
```sql
match_score = (match_score * sample_count + 1.0) / (sample_count + 1)
sample_count = sample_count + 1
```

## Notes on Scoring Logic

1. **Hot path matches** always record at `match_score=1.0` - confirmed, high-confidence usage
2. **UI-regen agent** may record lower scores during exploration/stewardship
3. **Seed patterns** provide initial baselines; real usage refines scores over time
4. **Selection order:** `match_score DESC, sample_count DESC` - higher score wins, ties broken by usage volume

## Summary

- **10 baseline components** defined in migration 003
- **13+ unique result_type patterns** with varying layout preferences
- **3 layout buckets:** compact, normal, expanded
- **Default threshold:** 0.7 (configurable via `match_threshold` parameter)
- **Hot path is deterministic:** no LLM, no semantic search, no generation
- **Fallback guaranteed:** built-in generic card prevents blank canvas
- **Pattern tracking:** running average of match scores, hot-path matches weight at 1.0

---

**Generated:** 2026-07-23  
**Source files:**
- `src/render/hot_path.py` - Result type derivation, hot-path renderer
- `src/components/library.py` - Component selection logic, layout buckets
- `src/components/seed_migration.py` - Baseline components and seed patterns
- `src/components/seed_patterns.py` - Alternative seed pattern definitions
- `src/diff/engine.py` - Diff engine result type inference
- `data/schema.sql` - Database schema for component tables
