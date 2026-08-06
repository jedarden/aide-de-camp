# Deployment Success Rate Calculation (adc-ricou)

## Task Completion Summary

Calculated deployment success/failure rates for pbx-web and whisper-stt services based on 30-day deployment data (2026-07-07 to 2026-08-06).

## Results

### pbx-web
- **Total deployments (30 days)**: 5
- **Successful deployments**: 5
- **Failed deployments**: 0
- **Rollback events**: 1 (2026-07-13 - rolled back from revision 12 to 1.0.8, then re-deployed revision 14 later same day)
- **Success rate**: 100.0%
- **Failure rate**: 0.0%

### whisper-stt
- **Total deployments (30 days)**: 4
- **Successful deployments**: 4
- **Failed deployments**: 0
- **Rollback events**: 0
- **Success rate**: 100.0%
- **Failure rate**: 0.0%

## Analysis Details

### Success Criteria
A deployment is considered successful if:
- For pbx-web: The deployment operation completed successfully (outcome documented as "success" or operation completed without failure)
- For whisper-stt: A ReplicaSet was successfully created and pods reached ready state
- Rollbacks that execute successfully are counted as successful operations (the rollback itself succeeded, even though it reverted to a previous version)

### Key Findings
1. **Both services achieved 100% deployment success** over the 30-day period
2. **Zero failed deployments** across both services
3. **pbx-web had higher deployment activity** (5 vs 4 deployments) - approximately 25% more frequent deployment cadence
4. **whisper-stt showed more stability** with no rollbacks required
5. **Both services maintained excellent uptime** with all deployments reaching ready state

### Deployment Context
- **pbx-web rollback**: On 2026-07-13, pbx-web rolled back from revision 12 to 1.0.8, then deployed revision 14 later the same day. The rollback operation itself completed successfully.
- **whisper-stt rapid deployment sequence**: Three deployments occurred on 2026-07-08 (revisions 30, 31, then 32), suggesting iterative image improvements during active development.

## Files Generated
- `calculate_deployment_success_rates.py` - Calculation script
- `deployment_success_rates.json` - Machine-readable results with detailed metrics

## Acceptance Criteria Status
✅ 1. pbx-web success rate computed: **100.0%**
✅ 2. pbx-web failure rate computed: **0.0%**
✅ 3. whisper-stt success rate computed: **100.0%**
✅ 4. whisper-stt failure rate computed: **0.0%**
✅ 5. Raw counts documented in deployment_success_rates.json

## Data Sources
- pbx-web: `pbx-web-deployment-data-30days.json` (loaded from previous bead)
- whisper-stt: `whisper-stt-deployment-data-30days.json` (loaded from previous bead)
- Analysis period: 2026-07-07 to 2026-08-06 (30 days)
