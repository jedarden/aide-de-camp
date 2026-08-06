# Deployment Success Rates Calculation - Task adc-24gnb

## Task Completed
Calculate deployment success/failure metrics for pbx-web and whisper-stt services.

## Approach
Created a Python script (`src/calculate_deployment_metrics.py`) to:
1. Load deployment data from child bead 1 datasets
2. Extract deployment events from JSON files
3. Filter to last 30 days of activity
4. Calculate success rates, deployment counts, and frequency metrics

## Results Summary

### pbx-web Service
- **Success Rate**: 100.0% (5/5 deployments successful)
- **Deployment Frequency**: 0.3571 deployments/day (~1 deployment every 2.8 days)
- **Mean Time Between Deployments**: 89.74 hours
- **Deployment Components**: pbx-web, pbx-rebuild-relay, lab-rebuild-relay
- **Period**: 2026-07-13 to 2026-07-28 (15 days)

### whisper-stt Service
- **Success Rate**: 100.0% (4/4 deployments successful)
- **Deployment Frequency**: 1.0 deployment/day (1 deployment per day)
- **Mean Time Between Deployments**: 36.58 hours
- **Deployment Components**: whisper-stt only
- **Period**: 2026-07-08 to 2026-07-12 (4 days)

## Key Findings
1. Both services have **100% deployment success rates** in the 30-day period
2. whisper-stt has **higher deployment frequency** (1.0/day vs 0.357/day)
3. whisper-stt deployments are **more frequent** (36.58h avg vs 89.74h avg)
4. pbx-web includes multiple deployment components (main app + 2 relays)
5. Both services show **zero deployment failures**

## Output Files
- `docs/research/deployment-metrics-intermediate.json` - Complete metrics dataset
- `src/calculate_deployment_metrics.py` - Calculation script

## Acceptance Criteria Met
✅ Success rate computed for pbx-web (100.0%)
✅ Success rate computed for whisper-stt (100.0%)
✅ Deployment frequency metrics calculated
✅ Results saved to intermediate file for next bead