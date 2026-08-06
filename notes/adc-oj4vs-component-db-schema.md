# Component DB Schema Documentation

Generated from: `data/schema.sql`
Purpose: Stores UI components and their versions for rendering result cards in aide-de-camp

## Database Configuration

- **Journal Mode**: WAL (Write-Ahead Logging) for concurrent access
- **Synchronous Mode**: NORMAL (balanced performance/safety)

---

## Tables

### 1. components

**Purpose**: Stores the current version of each component. This is the primary table for active component definitions.

**Primary Key**: `id`

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | TEXT | PRIMARY KEY | Unique component identifier (e.g., "comp-xxx") |
| `name` | TEXT | NOT NULL | Human-readable component name (e.g., "pod-status", "git-log-summary") |
| `description` | TEXT | NULLABLE | Describes what result types this component handles |
| `html_template` | TEXT | NOT NULL | The HTML/CSS template with parameterization placeholders |
| `version` | INTEGER | NOT NULL, DEFAULT 1 | Current version number (increments on updates) |
| `created_at` | INTEGER | NOT NULL | Unix timestamp of component creation |
| `last_used` | INTEGER | NULLABLE | Unix timestamp of last use (NULL if never used) |
| `usage_count` | INTEGER | NOT NULL, DEFAULT 0 | Number of times this component has been used |

**Relationships**:
- Has many: `component_versions` (via `component_id`)
- Has many: `component_tags` (via `component_id`)
- Has many: `component_usage_patterns` (via `component_id`)
- Has many: `card_cache` entries (via `component_id`)

**Indexes**:
- `idx_components_last_used` on `last_used` (DESC)
- `idx_components_usage_count` on `usage_count` (DESC)

---

### 2. component_versions

**Purpose**: Version history for all components. Maintains a complete audit trail of component template changes.

**Primary Key**: Composite (`component_id`, `version`)

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `component_id` | TEXT | NOT NULL, FK → components.id | References the component this version belongs to |
| `version` | INTEGER | NOT NULL | Version number for this component |
| `html_template` | TEXT | NOT NULL | The HTML/CSS template for this specific version |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when this version was created |
| `change_note` | TEXT | NULLABLE | Human-readable note explaining why this version was created |

**Relationships**:
- Belongs to: `components` (via `component_id`)

**Indexes**:
- `idx_component_versions_created` on `created_at` (DESC)

**Notes**: 
- Composite primary key ensures one version per component per version number
- Templates are immutable once stored in version history

---

### 3. card_cache

**Purpose**: Stores pre-rendered HTML cards for specific results. Implements a caching layer to avoid re-rendering identical results.

**Primary Key**: Composite (`result_id`, `component_id`, `layout_bucket`)

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `result_id` | TEXT | NOT NULL | Unique identifier for the result being cached |
| `component_id` | TEXT | NOT NULL, FK → components.id | Which component was used to render |
| `component_version` | INTEGER | NOT NULL | Version of component used for rendering |
| `layout_bucket` | TEXT | NOT NULL | Layout context: 'compact', 'normal', or 'expanded' |
| `rendered_html` | TEXT | NOT NULL | Pre-rendered HTML output |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when cache entry was created |

**Relationships**:
- Belongs to: `components` (via `component_id`)

**Indexes**:
- `idx_card_cache_created` on `created_at` (DESC) - for cache eviction/aging

**Notes**:
- Layout bucket allows different cached renderings for same result+component in different UI contexts
- Primary key allows one cached rendering per component per result per layout context

---

### 4. component_tags

**Purpose**: Stores tags and categories for components. Enables component discovery and filtering by characteristics.

**Primary Key**: Composite (`component_id`, `tag`)

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `component_id` | TEXT | NOT NULL, FK → components.id | Component being tagged |
| `tag` | TEXT | NOT NULL | Tag/category label (e.g., "kubernetes", "status", "lightweight") |

**Relationships**:
- Belongs to: `components` (via `component_id`)

**Notes**:
- Many-to-many relationship between components and tags
- Composite primary key prevents duplicate tags on same component
- No separate `tags` table — tags are stored inline as strings

---

### 5. component_usage_patterns

**Purpose**: Tracks which result types use which components with what effectiveness. Enables intelligent component selection for new results based on historical patterns.

**Primary Key**: Composite (`result_type`, `component_id`, `layout_bucket`)

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `result_type` | TEXT | NOT NULL | Result type identifier (e.g., "status:ibkr-mcp", "lookup:logs:adc") |
| `component_id` | TEXT | NOT NULL, FK → components.id | Component used for this result type |
| `layout_bucket` | TEXT | NOT NULL, DEFAULT 'normal' | Layout context: 'compact', 'normal', or 'expanded' |
| `match_score` | REAL | NOT NULL | Quality score (0.0-1.0) indicating how well component fits result type |
| `sample_count` | INTEGER | NOT NULL, DEFAULT 1 | Number of samples used to compute match_score |
| `updated_at` | INTEGER | NOT NULL | Unix timestamp when pattern was last updated |

**Relationships**:
- Belongs to: `components` (via `component_id`)

**Indexes**:
- `idx_component_usage_patterns_match_score` on `match_score` (DESC) - for ranking components by fit

**Notes**:
- Implements machine learning-style pattern matching for component selection
- Higher `match_score` = better historical fit
- `sample_count` provides confidence weighting (higher count = more reliable score)
- Layout-specific patterns allow different components for compact vs expanded views

---

## Relationship Diagram

```
components (1) ──── (N) component_versions
    │
    ├── (1) ──── (N) component_tags
    │
    ├── (1) ──── (N) component_usage_patterns
    │
    └── (1) ──── (N) card_cache
```

---

## Key Design Patterns

### 1. Version History Immutability
- `component_versions` stores immutable snapshots
- `components.version` increments on changes
- Historical renderings remain valid via `card_cache.component_version`

### 2. Layout Context Isolation
- `layout_bucket` ('compact', 'normal', 'expanded') is a first-class concept
- Separate cached renderings per layout context
- Usage patterns learned per layout context

### 3. Adaptive Component Selection
- `component_usage_patterns.match_score` enables ML-style ranking
- Pattern learning occurs implicitly as components are used
- `sample_count` enables confidence-based selection

### 4. Caching by Composite Key
- `card_cache` PK: `(result_id, component_id, layout_bucket)`
- One cache entry per component per result per layout
- Supports cache invalidation by `created_at` timestamp

---

## Usage Example (from schema comments)

```sql
-- Create a new component
INSERT INTO components (id, name, description, html_template, created_at)
VALUES ('comp-xxx', 'pod-status', 'Renders kubernetes pod status', '<div>...</div>', strftime('%s', 'now'));

-- Record its first version
INSERT INTO component_versions (component_id, version, html_template, created_at, change_note)
VALUES ('comp-xxx', 1, '<div>...</div>', strftime('%s', 'now'), 'Initial version');

-- Cache a rendered card
INSERT INTO card_cache (result_id, component_id, component_version, layout_bucket, rendered_html, created_at)
VALUES ('res-yyy', 'comp-xxx', 1, 'normal', '<div>...</div>', strftime('%s', 'now'));
```

---

## Summary

- **5 tables**: components, component_versions, card_cache, component_tags, component_usage_patterns
- **5 indexes**: Supporting common query patterns (last_used, usage_count, created_at, match_score)
- **Design focus**: Version history immutability, layout context isolation, adaptive component selection via pattern learning
- **Storage**: SQLite with WAL mode for concurrent access
