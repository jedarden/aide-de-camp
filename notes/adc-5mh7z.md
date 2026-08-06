# Deployment Data Coverage Analysis (2026-08-06)

## Summary

Saved final deployment datasets to `docs/research/deployment-data/`:
- `pbx-web-deployments.json` - 17 deployments from 2026-05-02 to 2026-07-28
- `whisper-stt-deployments.json` - 22 deployments from 2026-06-14 to 2026-07-12

## Coverage Notes

Both datasets meet the "earliest ≤ 30 days ago" criterion:
- pbx-web: Earliest deployment is 2026-05-02 (well before 2026-07-07 threshold)
- whisper-stt: Earliest deployment is 2026-06-14 (before 2026-07-07 threshold)

**Neither dataset meets the "latest within 1 day of today (2026-08-06)" criterion:**
- pbx-web: Latest deployment was 2026-07-28 (8 days ago)
- whisper-stt: Latest deployment was 2026-07-12 (24 days ago)

## Recent Activity (Last 30 Days)

Within the 30-day analysis window (2026-07-07 to 2026-08-06):
- **pbx-web**: 4 deployments on 2026-07-13, 2026-07-15, 2026-07-27, 2026-07-28
- **whisper-stt**: 2 deployments on 2026-07-08, 2026-07-12

The datasets reflect actual deployment history - there simply haven't been deployments for either service in the last 8-24 days.
