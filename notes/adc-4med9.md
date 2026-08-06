# whisper-stt Deployment Data Documentation

## Deployment Data File Path

**Validated 30-day deployment data for whisper-stt service:**

```
/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json
```

## File Information

- **Service**: whisper-stt
- **Namespace**: whisper-stt  
- **Cluster**: ardenone-cluster
- **Time Range**: 2026-07-07 to 2026-08-06 (30 days)
- **Data Source**: kubectl read-only proxy
- **Generated**: 2026-08-06T09:07:50Z

## Validation Status

This deployment data file has been validated for:
- ✅ JSON well-formedness (parseable)
- ✅ 30-day completeness (no gaps, no duplicates)  
- ✅ Chronological sequence integrity
- ✅ Field presence and type validation

**Validation completed**: bead adc-1iz1a (JSON Well-Formedness and Completeness Validation)

## File Contents

The file contains comprehensive deployment analysis data including:
- Current deployment status (replicas, images, resources)
- 30-day deployment history with all replica sets
- Deployment events and transitions
- Resource allocation and limits
- Deployment conditions and health status

## Usage

This validated data file serves as the authoritative 30-day deployment snapshot for whisper-stt and can be used for:
- Historical deployment analysis
- Pattern recognition and trend analysis
- Resource utilization studies
- Comparison with other services (e.g., pbx-web)

## Related Files

- **Schema**: `whisper_stt_deployment_schema.py` - Data schema definition
- **Validation**: `src/validation/completeness.py` - Validation implementation  
- **Tests**: `tests/unit/test_completeness_validation.py` - 42 comprehensive tests
- **Documentation**: `notes/adc-1iz1a.md` - Validation implementation details

## Commit Information

**Commit message**: `docs: add validated 30-day deployment data for whisper-stt`

**Rationale**: Document validated deployment data file path following completion of JSON well-formedness and 30-day completeness validation (bead adc-1iz1a). The file is now ready for historical analysis and pattern recognition.
