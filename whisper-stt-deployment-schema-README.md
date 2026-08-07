# Whisper-STT Deployment Data Schema

## Overview

This schema defines validation rules for whisper-stt deployment data files, ensuring data integrity, completeness, and compliance with operational analysis requirements.

## Schema File

**File**: `whisper-stt-deployment-schema.json`  
**Schema Version**: JSON Schema Draft 07  
**Purpose**: Validate whisper-stt deployment data with 30-day completeness requirements

## Validation Scope

### Required Top-Level Sections

1. **metadata** - Generation timestamps, data period coverage, sources
2. **argo_workflows** - CI/CD build pipeline execution data
3. **argo_cd** - ArgoCD application sync and health status
4. **cluster_deployments** - Kubernetes deployment and ReplicaSet history
5. **summary** - 30-day deployment statistics and coverage metrics
6. **pod_health** - Current pod status and runtime metrics

### Optional Sections

- **resources** - CPU/memory allocation and limits
- **storage** - PVC and volume information
- **error_incidents** - Failure tracking and incident details
- **notes** - Additional observations and context

## Key Validation Rules

### 30-Day Completeness Requirements

The schema enforces 30-day data completeness through:

```json
"metadata": {
  "data_period_start": "ISO-8601 timestamp",
  "data_period_end": "ISO-8601 timestamp",
  "services": ["whisper-stt"],
  "data_sources": ["kubernetes_replicasets", "argo_workflows", "argo_cd"]
}
```

**Coverage Validation**:
- `summary.data_coverage`: Percentage format (e.g., "100%")
- `summary.gaps_detected`: Boolean flag for data gaps
- `summary.largest_gap_days`: Integer (0-30 days)

### Data Type Enforcement

**Timestamps**: All timestamps use ISO 8601 format with timezone
- Example: `"2026-08-06T12:03:32.329077Z"`

**Status Enums**: Standardized status values
- ArgoCD sync: `["Synced", "OutOfSync", "Unknown"]`
- ArgoCD health: `["Healthy", "Progressing", "Degraded", "Missing", "Unknown"]`
- ReplicaSet status: `["successful", "rolled_over", "scaled_down_or_failed", "failed"]`
- Pod status: `["Running", "Pending", "Failed", "Succeeded", "Unknown"]`

**Numeric Ranges**: Non-negative integers with minimums
- Deployment counts: `>= 0`
- Days ago: `0-30` (valid within 30-day window)
- Replica counts: `>= 0`

### Image Format Validation

Container images must follow pattern: `registry/name:tag`

```regex
^[a-z0-9-]+/[a-z0-9-]+:[\w.+]+$
```

**Examples**:
- ✅ `ronaldraygun/whisper-stt:1.8.6`
- ✅ `fedirz/faster-whisper-server:latest-cpu`
- ❌ `whisper-stt:1.8.6` (missing registry)
- ❌ `ronaldraygun/whisper-stt` (missing tag)

### Resource Format Validation

**CPU**: Cores or millicores
- `"1"` = 1 core
- `"100m"` = 100 millicores (0.1 core)

**Memory**: Standard Kubernetes units
- `"4Gi"` = 4 gibibytes
- `"512Mi"` = 512 mebibytes
- `"8192Mi"` = 8192 mebibytes

Pattern: `^[\d]+(Ei|Pi|Ti|Gi|Mi|Ki|E|P|T|G|M|K)?$`

## Using the Schema

### Validation with jsonschema CLI

```bash
# Install jsonschema validator
pip install jsonschema

# Validate deployment data
jsonschema -i whisper-stt-deployments-30d.json whisper-stt-deployment-schema.json

# Exit code 0 = valid, non-zero = validation errors
```

### Validation with Python

```python
import json
from jsonschema import validate, ValidationError

# Load schema and data
with open('whisper-stt-deployment-schema.json') as f:
    schema = json.load(f)
with open('whisper-stt-deployments-30d.json') as f:
    data = json.load(f)

# Validate
try:
    validate(instance=data, schema=schema)
    print("✅ Validation successful")
except ValidationError as e:
    print(f"❌ Validation failed: {e.message}")
    print(f"   Path: {'.'.join(str(p) for p in e.path)}")
```

### Validation with JavaScript/Node.js

```javascript
const Ajv = require("ajv");
const fs = require("fs");

// Load schema and data
const schema = JSON.parse(fs.readFileSync("whisper-stt-deployment-schema.json"));
const data = JSON.parse(fs.readFileSync("whisper-stt-deployments-30d.json"));

// Validate
const ajv = new Ajv();
const validate = ajv.compile(schema);
const valid = validate(data);

if (valid) {
    console.log("✅ Validation successful");
} else {
    console.log("❌ Validation failed:", validate.errors);
}
```

## Common Validation Issues

### Missing Required Fields

**Error**: `'field_name' is a required property`

**Solution**: Add the missing field to your deployment data file

### Invalid Timestamp Format

**Error**: `does not match format 'date-time'`

**Solution**: Use ISO 8601 format with timezone
```json
"generated_at": "2026-08-06T12:03:32.329077Z"
```

### Invalid Status Values

**Error**: `does not match any of the allowed values`

**Solution**: Use only enumerated status values from schema
```json
"status": "Synced"  // ✅ Valid
"status": " synced"  // ❌ Invalid (extra space)
```

### Coverage Gap Detected

**Error**: `summary.gaps_detected is true but largest_gap_days > 7`

**Solution**: Either fix data gap or document acceptable gap size in analysis

## Schema Maintenance

### Version History

- **v1.0** (2026-08-06): Initial schema definition based on 30-day deployment analysis requirements

### Extending the Schema

To add validation for new services or fields:

1. Add new properties to existing sections
2. Update `required` arrays if fields are mandatory
3. Add new enum values for status fields
4. Update this README with validation examples

### Schema Testing

Test schema changes against known valid and invalid datasets:

```bash
# Test valid data
jsonschema -i whisper-stt-deployments-30d.json whisper-stt-deployment-schema.json

# Test invalid data (should fail)
echo '{"invalid": "data"}' | jsonschema -i /dev/stdin whisper-stt-deployment-schema.json
```

## Integration Points

This schema validates data from these sources:

- **Kubernetes API**: ReplicaSet queries via `traefik-ardenone-cluster:8001`
- **Argo Workflows**: Build pipeline execution tracking
- **ArgoCD**: Application sync and health monitoring
- **Git History**: Deployment commit analysis

## Support and Issues

For schema validation issues or enhancement requests, reference the task context:
- **Task ID**: adc-xq0ba
- **Task**: Write deployment data validation schema
- **Acceptance**: Schema defines all required fields, specifies data types, validates 30-day completeness

---

**Schema Compliance**: Deployment data files matching this schema are validated for 30-day completeness, type safety, and operational analysis requirements.