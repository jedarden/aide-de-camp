-- Seed data for component_usage_patterns table
-- This provides initial mappings for common result types to components
--
-- These seeds represent common patterns discovered during testing and development.
-- They serve as a starting point for the hot-path component selection system.
--
-- Usage:
--   sqlite3 data/components.db < seed_usage_patterns.sql

-- Note: This file assumes components with these IDs exist.
-- If they don't exist, the INSERT will fail due to foreign key constraints.
-- In production, this should be run after component creation.

-- Common Kubernetes status patterns
INSERT OR IGNORE INTO component_usage_patterns (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
VALUES
  ('status:kubernetes', 'comp-k8s-status', 'normal', 0.95, 10, strftime('%s', 'now')),
  ('status:kubernetes', 'comp-k8s-status', 'compact', 0.90, 5, strftime('%s', 'now')),
  ('status:kubernetes', 'comp-k8s-status', 'expanded', 0.92, 8, strftime('%s', 'now'));

-- Git status patterns
INSERT OR IGNORE INTO component_usage_patterns (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
VALUES
  ('status:git', 'comp-git-status', 'normal', 0.93, 15, strftime('%s', 'now')),
  ('status:git', 'comp-git-status', 'compact', 0.88, 7, strftime('%s', 'now'));

-- CI/CD status patterns
INSERT OR IGNORE INTO component_usage_patterns (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
VALUES
  ('status:ci', 'comp-ci-status', 'normal', 0.91, 12, strftime('%s', 'now')),
  ('status:ci', 'comp-ci-status', 'expanded', 0.94, 6, strftime('%s', 'now'));

-- Generic action patterns
INSERT OR IGNORE INTO component_usage_patterns (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
VALUES
  ('action:general', 'comp-action-card', 'normal', 0.85, 20, strftime('%s', 'now')),
  ('action:general', 'comp-action-card', 'compact', 0.82, 10, strftime('%s', 'now'));

-- Lookup patterns for logs
INSERT OR IGNORE INTO component_usage_patterns (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
VALUES
  ('lookup:logs:general', 'comp-logs-viewer', 'expanded', 0.96, 25, strftime('%s', 'now')),
  ('lookup:logs:general', 'comp-logs-viewer', 'normal', 0.94, 18, strftime('%s', 'now'));

-- Lookup patterns for configuration
INSERT OR IGNORE INTO component_usage_patterns (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
VALUES
  ('lookup:config:general', 'comp-config-viewer', 'normal', 0.89, 14, strftime('%s', 'now'));

-- Monitoring patterns
INSERT OR IGNORE INTO component_usage_patterns (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
VALUES
  ('monitoring:kubernetes', 'comp-monitoring-card', 'normal', 0.92, 8, strftime('%s', 'now')),
  ('monitoring:kubernetes', 'comp-monitoring-card', 'expanded', 0.95, 5, strftime('%s', 'now'));

-- General fallback patterns (for unmatched result types)
INSERT OR IGNORE INTO component_usage_patterns (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
VALUES
  ('status:general', 'comp-generic-status', 'normal', 0.70, 30, strftime('%s', 'now')),
  ('action:general', 'comp-generic-action', 'normal', 0.70, 25, strftime('%s', 'now')),
  ('lookup:general', 'comp-generic-lookup', 'normal', 0.70, 20, strftime('%s', 'now'));
