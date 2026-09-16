-- Test verification: bead ready frontier query correctness
-- This file documents the schema evolution and correct queries for bead-rs backend
--
-- SCHEMA HISTORY:
-- Original (bead-forge/bf): used `status` and `blocked_by` columns
-- Current (bead-rs): uses `base_status` and `manual_blocked` columns
--
-- INCORRECT QUERY (legacy, will fail):
-- SELECT id FROM issues
-- WHERE status = 'open'
-- AND assignee IS NULL
-- AND blocked_by IS NOT NULL
-- ORDER BY priority DESC, created_at ASC
--
-- CORRECT QUERY (bead-rs schema):
SELECT id FROM issues
WHERE base_status = 'open'
AND assignee IS NULL
AND manual_blocked = 0
ORDER BY priority DESC, created_at ASC;

-- Verification counts:
-- Total open beads should equal: (unassigned + unblocked) + assigned + blocked
-- Ready beads = unassigned + unblocked + not manually blocked

-- Test case: run both counts and verify
SELECT
  COUNT(*) FILTER (WHERE base_status = 'open') as total_open,
  COUNT(*) FILTER (WHERE base_status = 'open' AND assignee IS NULL AND manual_blocked = 0) as ready_for_claiming,
  COUNT(*) FILTER (WHERE base_status = 'open' AND assignee IS NOT NULL) as assigned_open,
  COUNT(*) FILTER (WHERE base_status = 'open' AND manual_blocked = 1) as manually_blocked
FROM issues;
