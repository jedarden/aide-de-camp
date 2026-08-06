# Deployment Data Coverage Verification - adc-4xjqq

## Task Completed: 2026-08-06

Verified deployment data completeness and coverage for the 30-day analysis window (2026-07-07 to 2026-08-06).

## Files Analyzed

- `docs/research/deployment-data/pbx-web-deployments.json`
- `docs/research/deployment-data/whisper-stt-deployments.json`

## Key Findings

### pbx-web Deployment Coverage

**Status:** ⚠️ Partial Coverage (15/30 days)

- **CI Workflows:** 0 found (aggressive cleanup policy)
- **Production Deployments:** 2 events captured
  - 2026-07-13: Initial deployment of revision 14 (ronaldraygun/pbx-web:1.0.9)
  - 2026-07-28: Current active deployment (ronaldraygun/pbx-web:1.0.9)
- **Coverage Gap:** Missing 15 days from target 30-day window
- **Root Cause:** No CI builds in window; workflows deleted within hours/days; current image deployed prior to analysis

### whisper-stt Deployment Coverage

**Status:** ❌ No Coverage (0/30 days)

- **CI Workflows:** 0 found
- **Production Deployments:** 0 captured
- **Coverage Gap:** Complete 30-day window missing
- **Root Cause:** Workflow retention policy ~9 days; all workflows in window cleaned up

### Data Completeness

✅ **All required fields present in both files:**
- Workflow name, creationTimestamp, phase
- Image information (repository, digest, tag)
- Git commit details (SHA, message, author)
- Query metadata and findings
- Node execution details

## Coverage Gaps & Root Causes

1. **Aggressive Workflow Cleanup:** iad-ci cluster deletes workflows within hours/days
2. **No Recent CI Activity:** Both services have stable production images (no new builds needed)
3. **Limited Retention:** Workflow retention policy ~9 days prevents full 30-day analysis

## Alternative Data Sources Identified

For future 30-day deployment analysis:
- ArgoCD application sync history
- declarative-config git commits for manifests
- Container registry image tags and build dates
- Kubernetes ReplicaSets in target namespaces

## Recommendations

1. Increase workflow TTL for historical analysis
2. Implement WorkflowArchive or external logging
3. Cross-reference ArgoCD for deployment history
4. Track git history for deployment triggers

## Deliverables

✅ Created `docs/research/deployment-data/verify_coverage.py` - Python analysis script
✅ Created `docs/research/deployment-data/coverage-report.json` - Detailed analysis results
✅ Updated `docs/research/deployment-data/README.md` - Added comprehensive coverage report section
✅ Data completeness verified (all required fields present)
✅ Coverage gaps documented with root causes
✅ Summary statistics recorded (deployments per service, success/failure counts, date ranges)

## Notes

The deployment data files are structurally complete and contain all required metadata. The coverage gaps are due to infrastructure policies (workflow cleanup) rather than data collection issues. For complete 30-day deployment analysis in the future, alternative data sources should be utilized.
