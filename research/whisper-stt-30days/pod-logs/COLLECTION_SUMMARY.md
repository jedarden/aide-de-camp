# Whisper-STT Pod Log Collection Summary

**Collection Date:** 2026-08-06  
**Cluster:** ardenone-cluster  
**Namespace:** whisper-stt

## Pods Identified

### Current Pods
1. **whisper-openai-68966786fb-jsb5d**
   - Status: Running
   - Created: 2026-06-14T04:55:49Z
   - Image: docker.io/fedirz/faster-whisper-server:latest-cpu
   - Restart Count: 0
   - Log File: `pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log` (8.4 MB)
   - Coverage: ~53 days of runtime

2. **whisper-stt-847fd8d7b9-v2rs5**
   - Status: Running
   - Created: 2026-07-12T16:53:42Z
   - Image: docker.io/ronaldraygun/whisper-stt:1.8.6
   - Restart Count: 0
   - Log File: `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log` (210 bytes)
   - Coverage: ~24 days of runtime (no stdout logs)

### Historical ReplicaSets (No Accessible Logs)
The following ReplicaSets were created during the 30-day window but pods were deleted:
1. **whisper-stt-5dbff75cbd-*** (Created: 2026-07-08, Image: ronaldraygun/whisper-stt:1.8.2)
2. **whisper-stt-5b8558f478-*** (Created: 2026-07-08, Image: ronaldraygun/whisper-stt:1.8.4)
3. **whisper-stt-6c497489fb-*** (Created: 2026-07-08, Image: ronaldraygun/whisper-stt:1.8.6)

Historical pod logs are not accessible as the pods have been deleted and no log aggregation system is configured.

## Coverage Analysis

- **whisper-openai pod:** Covers the full 30-day period (created before window, still running)
- **whisper-stt pod:** Covers ~24 days (created during window, still running)
- **Historical pods:** ~4 days of coverage (2026-07-08 to 2026-07-12) - logs lost

## Log File Contents

- `pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log`: Full runtime logs from whisper-openai pod
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log`: Minimal output (pod runs silently)

## Notes

- No restart events occurred on current pods (restart_count=0)
- Previous logs are not available (--previous flag returned no data)
- whisper-stt pod appears to run with minimal stdout logging
