# Component Usage Patterns Seed Data Design

## Overview

This document defines the seed data structure and match score values for the `component_usage_patterns` table in the aide-de-camp component library system. The seed data provides initial mappings between result types and UI components to enable the hot-path renderer to select appropriate components without LLM calls.

## Schema Definition

### Table: `component_usage_patterns`

```sql
CREATE TABLE component_usage_patterns (
    result_type TEXT NOT NULL,          -- e.g., "status:ibkr-mcp", "lookup:logs:adc"
    component_id TEXT NOT NULL,        -- References components.id
    layout_bucket TEXT NOT NULL,        -- 'compact' | 'normal' | 'expanded'
    match_score REAL NOT NULL,          -- Confidence score 0.0-1.0
    sample_count INTEGER NOT NULL DEFAULT 1,
    updated_at INTEGER NOT NULL,        -- Unix timestamp
    PRIMARY KEY (result_type, component_id, layout_bucket)
);
```

### Seed Data Format

```python
(
    result_type: str,      # Colon-separated hierarchical key
    component_id: str,      # Must exist in components table
    layout_bucket: str,    # One of: 'compact', 'normal', 'expanded'
    match_score: float,    # 0.0 to 1.0 confidence
    sample_count: int      # Number of times this pattern has been observed
)
```

## Result Type Taxonomy

Result types follow a colon-separated hierarchical naming convention derived in `src/render/hot_path.py`:

```
{intent_type}:{project_slug}                    # Intent-derived
lookup:{lookup_kind}:{project_slug}            # Lookup threads
monitoring:{project_slug}                       # Monitoring results
{intent_type}:general                           # No project slug fallback
```

### Common Intent Types

- **status** - Status checks, health queries, state queries
- **action** - Actions, operations, executions
- **lookup** - Data lookups (logs, config, metrics)
- **monitoring** - Monitoring and alerting data
- **compound** - Multi-part aggregated results

### Common Project Slugs

- **ibkr-mcp** - Interactive Brokers MCP server
- **adc** - aide-de-camp (self)
- **general** - Fallback when no project identified
- **k8s** - Kubernetes operations
- **git** - Git operations

## Layout Buckets

### Layout: `compact` (Dense, ~120px height)

- **Use case**: High-density displays, list views, status dashboards
- **Best for**: Simple status checks, binary states, counters, badges
- **Typical content**: Status indicator + 1-2 key fields, minimal text
- **Examples**: Pod running/stopped, build success/fail, deployment ready/pending

### Layout: `normal` (Balanced, ~200px height)

- **Use case**: Default card layout, balanced information density
- **Best for**: Most result types, moderate information density
- **Typical content**: Title + 3-6 key-value pairs, summary, 1-level nested data
- **Examples**: Pod status with resource limits, commit info with files changed, logs viewer preview

### Layout: `expanded` (Full, ~400px+ height)

- **Use case**: Maximum information display, detailed views
- **Best for**: Complex results, multi-item lists, full logs/config
- **Typical content**: Full arrays/objects, long text, multiple sections, tables
- **Examples**: Full pod spec, complete commit message, extended logs, full config file

## Match Score Rationale

### Score Range: 0.0 - 1.0

| Score Range | Confidence | Interpretation |
|-------------|-----------|----------------|
| **0.95 - 1.00** | Perfect | Exact component designed for this result type |
| **0.85 - 0.94** | Excellent | Very strong semantic match, purpose-built component |
| **0.70 - 0.84** | Good | Strong match, general-purpose component fits well |
| **0.50 - 0.69** | Fair | Moderate match, usable but not ideal |
| **0.30 - 0.49** | Poor | Weak match, fallback territory |
| **0.00 - 0.29** | None | No meaningful match, should not be used |

### Scoring Guidelines

1. **Exact name match** = 1.0 (component.name == result_type key part)
2. **Keyword overlap** = +0.1 per matching keyword (max +0.3)
3. **Domain specificity** = +0.15 for domain-specific components
4. **Layout appropriateness** = +0.05 for layout-appropriate components
5. **Proven fit** = baseline score from successful usage

### Thresholds

- **Hot-path threshold**: 0.7 (DEFAULT_MATCH_THRESHOLD in `hot_path.py`)
- **Semantic fallback threshold**: 0.5 (in `ComponentLibrary.find_best_component`)
- Patterns below 0.7 will trigger fallback to generic card

## Seed Data Patterns

### Core Principle

Each pattern represents a learned mapping: *"When result_type X appears in context Y, component Z with layout L is a good fit with confidence S."*

### Category: Status Results

```python
# Project-specific status patterns
("status:ibkr-mcp", "comp-ibkr-status", "normal", 0.95, 25),
("status:ibkr-mcp", "comp-ibkr-status", "compact", 0.90, 10),
("status:adc", "comp-adc-status", "normal", 0.95, 20),
("status:adc", "comp-adc-status", "compact", 0.88, 8),

# Kubernetes status patterns
("status:k8s", "comp-k8s-pod-status", "normal", 0.94, 30),
("status:k8s", "comp-k8s-pod-status", "compact", 0.89, 15),
("status:k8s", "comp-k8s-deployment-status", "normal", 0.92, 18),
("status:k8s", "comp-k8s-service-status", "compact", 0.91, 12),

# Git operations status
("status:git", "comp-git-status", "normal", 0.93, 22),
("status:git", "comp-git-status", "compact", 0.87, 11),
("status:git", "comp-git-commit-info", "normal", 0.91, 16),

# CI/CD status
("status:ci", "comp-ci-pipeline-status", "normal", 0.96, 28),
("status:ci", "comp-ci-pipeline-status", "compact", 0.90, 14),
("status:ci", "comp-ci-build-status", "expanded", 0.92, 10),
```

**Rationale**:
- Project-specific patterns get highest scores (0.95) for exact fit
- K8s patterns score high (0.89-0.94) as k8s operations have well-defined schemas
- CI/CD gets 0.92-0.96 as CI results are highly structured
- Compact layouts score 0.04-0.06 lower than normal for same pattern (density trade-off)

### Category: Lookup Results

```python
# Logs lookup patterns
("lookup:logs:ibkr-mcp", "comp-logs-viewer", "expanded", 0.96, 40),
("lookup:logs:ibkr-mcp", "comp-logs-viewer", "normal", 0.93, 25),
("lookup:logs:adc", "comp-logs-viewer", "expanded", 0.95, 35),
("lookup:logs:adc", "comp-logs-viewer", "normal", 0.92, 20),
("lookup:logs:k8s", "comp-k8s-logs", "expanded", 0.97, 50),
("lookup:logs:general", "comp-logs-viewer", "expanded", 0.85, 15),

# Config lookup patterns
("lookup:config:ibkr-mcp", "comp-config-viewer", "normal", 0.92, 18),
("lookup:config:ibkr-mcp", "comp-config-viewer", "expanded", 0.94, 12),
("lookup:config:adc", "comp-config-viewer", "normal", 0.91, 15),
("lookup:config:k8s", "comp-k8s-config", "expanded", 0.95, 30),
("lookup:config:general", "comp-config-viewer", "normal", 0.82, 10),

# Metrics lookup patterns
("lookup:metrics:k8s", "comp-k8s-metrics", "normal", 0.93, 20),
("lookup:metrics:k8s", "comp-k8s-metrics", "expanded", 0.95, 15),
```

**Rationale**:
- Logs patterns score highest (0.93-0.97) as logs have very specific structure
- Expanded layouts favored for logs (full log display)
- Config scores 0.82-0.95 depending on specificity
- Metrics patterns get 0.93+ for structured numerical data

### Category: Action Results

```python
# General action patterns
("action:general", "comp-action-result", "normal", 0.85, 20),
("action:general", "comp-action-result", "compact", 0.80, 10),

# Deployment actions
("action:deploy", "comp-deployment-result", "normal", 0.92, 25),
("action:deploy", "comp-deployment-result", "expanded", 0.90, 12),

# Restart/restart actions
("action:restart", "comp-restart-result", "compact", 0.91, 18),
("action:restart", "comp-restart-result", "normal", 0.88, 14),

# Scaling actions
("action:scale", "comp-scale-result", "normal", 0.90, 16),
("action:scale", "comp-scale-result", "expanded", 0.87, 8),
```

**Rationale**:
- General actions get moderate scores (0.80-0.85) as action results vary widely
- Specific action types (deploy, restart, scale) score higher (0.87-0.92)
- Compact layouts work well for simple binary action results

### Category: Monitoring Results

```python
# Kubernetes monitoring
("monitoring:k8s", "comp-k8s-monitoring", "normal", 0.94, 35),
("monitoring:k8s", "comp-k8s-monitoring", "expanded", 0.96, 25),
("monitoring:k8s", "comp-k8s-monitoring", "compact", 0.88, 15),

# Application monitoring
("monitoring:adc", "comp-adc-metrics", "normal", 0.91, 20),
("monitoring:ibkr-mcp", "comp-ibkr-metrics", "normal", 0.90, 18),

# General monitoring
("monitoring:general", "comp-monitoring-card", "normal", 0.82, 12),
```

**Rationale**:
- K8s monitoring scores highest (0.88-0.96) as k8s metrics are well-structured
- Expanded layouts score highest for monitoring (time series, multiple metrics)
- Project-specific monitoring scores 0.90-0.91

### Category: Fallback Patterns (Generic Components)

```python
# Generic fallbacks for unmatched types
("status:general", "comp-generic-status", "normal", 0.70, 30),
("status:general", "comp-generic-status", "compact", 0.68, 15),
("action:general", "comp-generic-action", "normal", 0.70, 25),
("lookup:general", "comp-generic-lookup", "normal", 0.70, 20),
("monitoring:general", "comp-generic-monitoring", "normal", 0.70, 18),
("compound:general", "comp-generic-compound", "expanded", 0.70, 22),
```

**Rationale**:
- All generic patterns score exactly 0.70 (at threshold)
- Provides minimum viable match without false confidence
- Sample counts reflect high usage but low specificity

## Component Template Examples

### Status Component Template

```html
<!-- comp-k8s-pod-status -->
<div class="k8s-pod-card" data-pod-name="{{pod.name}}" data-namespace="{{pod.namespace}}">
  <div class="pod-header">
    <span class="pod-name">{{pod.name}}</span>
    <span class="pod-namespace">{{pod.namespace}}</span>
  </div>
  <div class="pod-status {{pod.phase.lower}}">{{pod.phase}}</span>
  <div class="pod-details">
    <div class="detail-row">
      <span class="label">Ready:</span>
      <span class="value">{{pod.ready}}/{{pod.containers}}</span>
    </div>
    <div class="detail-row">
      <span class="label">Restarts:</span>
      <span class="value">{{pod.restarts}}</span>
    </div>
    <div class="detail-row">
      <span class="label">Age:</span>
      <span class="value">{{pod.age}}</span>
    </div>
  </div>
</div>
```

### Logs Component Template

```html
<!-- comp-logs-viewer -->
<div class="logs-viewer" data-source="{{source}}">
  <div class="logs-header">
    <span class="source">{{source}}</span>
    <span class="line-count">{{lines.length}} lines</span>
  </div>
  <div class="logs-content">
    {{#each lines}}
    <div class="log-line {{#if error}}error{{/if}}">
      <span class="timestamp">{{this.timestamp}}</span>
      <span class="level">{{this.level}}</span>
      <span class="message">{{this.message}}</span>
    </div>
    {{/each}}
  </div>
</div>
```

## Sample Count Guidance

Sample counts should reflect:

1. **Production usage**: 20-50 for well-established patterns
2. **Common patterns**: 10-25 for frequently used patterns
3. **New patterns**: 5-15 for recently established patterns
4. **Generic fallbacks**: 15-30 (high usage, low specificity)

Higher sample counts indicate more reliable patterns when sorting by `match_score DESC, sample_count DESC`.

## Layout Bucket Assignment Strategy

### When to use `compact`:

- Binary status (running/stopped, success/fail)
- Single-value metrics (CPU: 75%, Memory: 2GB)
- Counters and badges (3 pods, 5 errors)
- High-density status dashboards

### When to use `normal`:

- Default layout for most result types
- 3-8 key-value pairs
- Single-level nested objects
- Summary + details views

### When to use `expanded`:

- Logs and text output (>10 lines)
- Full configurations (YAML/JSON)
- Multi-item lists (>10 items)
- Time-series data
- Complex nested structures

## Implementation Notes

1. **Component ID Requirements**: All `component_id` values must exist in the `components` table before seed patterns are loaded. The `load_seed_patterns()` function in `seed_patterns.py` validates this.

2. **Timestamp Handling**: The `updated_at` field uses Unix timestamps (seconds since epoch). Seed data should use `int(time.time())` at load time.

3. **Transaction Safety**: Pattern loading uses `INSERT OR IGNORE` to prevent conflicts with existing patterns while being idempotent.

4. **Validation**: Match scores are validated to be in range 0.0-1.0. Layout buckets must be one of: 'compact', 'normal', 'expanded'.

5. **Index Usage**: The `idx_component_usage_patterns_match_score` index enables efficient queries for `ORDER BY match_score DESC`.

## Usage Example

```python
from src.components.seed_patterns import load_seed_patterns, DEFAULT_SEED_PATTERNS
from src.components.library import get_library

# Load seed patterns into the component library
library = get_library()
loaded_count = load_seed_patterns(library)

print(f"Loaded {loaded_count} seed patterns")
```

## Migration Notes

When migrating from the old schema (without `layout_bucket`), existing patterns are assigned `layout_bucket = 'normal'` by default. See `_migrate_component_usage_patterns()` in `library.py`.

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-23  
**Schema Version**: component_usage_patterns v2 (with layout_bucket and updated_at)
