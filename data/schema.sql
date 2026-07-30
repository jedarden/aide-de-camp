-- aide-de-camp Component Library Schema
-- This database stores UI components and their versions for rendering result cards

-- Enable WAL mode for concurrent access
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- Components table: stores the current version of each component
CREATE TABLE IF NOT EXISTS components (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,                  -- e.g., "pod-status", "git-log-summary"
    description TEXT,                    -- What result types this component handles
    html_template TEXT NOT NULL,         -- The HTML/CSS template (parameterized)
    version INTEGER NOT NULL DEFAULT 1, -- Current version number
    created_at INTEGER NOT NULL,         -- Unix timestamp
    last_used INTEGER,                  -- Unix timestamp
    usage_count INTEGER NOT NULL DEFAULT 0
);

-- Component versions: history of all component versions
CREATE TABLE IF NOT EXISTS component_versions (
    component_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    html_template TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    change_note TEXT,                   -- Why this version was created
    PRIMARY KEY (component_id, version)
);

-- Card cache: rendered cards for specific results
CREATE TABLE IF NOT EXISTS card_cache (
    result_id TEXT NOT NULL,
    component_id TEXT NOT NULL,
    component_version INTEGER NOT NULL,
    layout_bucket TEXT NOT NULL,        -- 'compact' | 'normal' | 'expanded'
    rendered_html TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (result_id, component_id, layout_bucket)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_components_last_used ON components(last_used);
CREATE INDEX IF NOT EXISTS idx_components_usage_count ON components(usage_count);
CREATE INDEX IF NOT EXISTS idx_component_versions_created ON component_versions(created_at);
CREATE INDEX IF NOT EXISTS idx_card_cache_created ON card_cache(created_at);

-- Component metadata table: stores tags and categories
CREATE TABLE IF NOT EXISTS component_tags (
    component_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (component_id, tag)
);

-- Component usage patterns: tracks which result types use which components
CREATE TABLE IF NOT EXISTS component_usage_patterns (
    result_type TEXT NOT NULL,          -- e.g., "status:ibkr-mcp", "lookup:logs:adc"
    component_id TEXT NOT NULL,
    layout_bucket TEXT NOT NULL DEFAULT 'normal',  -- 'compact' | 'normal' | 'expanded'
    match_score REAL NOT NULL,          -- How well this component fits this result type (0-1)
    sample_count INTEGER NOT NULL DEFAULT 1,
    updated_at INTEGER NOT NULL,        -- Unix timestamp when last updated
    PRIMARY KEY (result_type, component_id, layout_bucket)
);

-- Index for pattern selection by match_score
CREATE INDEX IF NOT EXISTS idx_component_usage_patterns_match_score
ON component_usage_patterns(match_score DESC);

-- Template for component management
-- Usage:
--   INSERT INTO components (id, name, description, html_template, created_at)
--   VALUES ('comp-xxx', 'pod-status', 'Renders kubernetes pod status', '<div>...</div>', strftime('%s', 'now'))
--
--   INSERT INTO component_versions (component_id, version, html_template, created_at, change_note)
--   VALUES ('comp-xxx', 1, '<div>...</div>', strftime('%s', 'now'), 'Initial version')
--
--   INSERT INTO card_cache (result_id, component_id, component_version, layout_bucket, rendered_html, created_at)
--   VALUES ('res-yyy', 'comp-xxx', 1, 'normal', '<div>...</div>', strftime('%s', 'now'))
