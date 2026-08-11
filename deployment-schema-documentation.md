# Comprehensive Deployment Data Schema Documentation

## Overview

The **deployment-data-schema-comprehensive.json** schema provides complete validation for deployment data with 30-day completeness requirements. This schema implements structural, temporal, data quality, and completeness validation rules as specified in the 30-day completeness validation specification.

## Schema File

**File**: `deployment-data-schema-comprehensive.json`  
**Schema Version**: JSON Schema Draft 07  
**Purpose**: Validate deployment data with comprehensive field validation and 30-day completeness requirements  
**Validation Coverage**: Structural (SV), Temporal (TV), Data Quality (DQ), Completeness (CV), Cross-Service (CSV)

## Quick Start

### Installation

```bash
# Install jsonschema validator
pip install jsonschema

# Or using the project venv
.venv/bin/pip install jsonschema
```

### Basic Usage

```bash
# Validate deployment data against the schema
jsonschema -i your-deployment-data.json deployment-data-schema-comprehensive.json

# Exit code 0 = valid, non-zero = validation errors
```

### Python Usage

```python
import json
from jsonschema import validate, ValidationError

# Load schema and data
with open('deployment-data-schema-comprehensive.json') as f:
    schema = json.load(f)
with open('your-deployment-data.json') as f:
    data = json.load(f)

# Validate
try:
    validate(instance=data, schema=schema)
    print("✅ Schema validation successful")
except ValidationError as e:
    print(f"❌ Validation failed: {e.message}")
    print(f"   Path: {'.'.join(str(p) for p in e.path)}")
```

## Schema Structure

### Required Top-Level Sections

1. **`metadata`** (Required) - Generation timestamps, data period coverage, source systems
2. **`argo_workflows`** (Optional) - CI/CD pipeline execution data  
3. **`argo_cd`** (Optional) - ArgoCD application sync and health status
4. **`cluster_deployments`** (Required) - Kubernetes deployment and ReplicaSet history
5. **`summary`** (Required) - 30-day deployment statistics and coverage metrics

### Optional Sections

6. **`pod_health`** - Current pod status and runtime metrics
7. **`resources`** - CPU/memory allocation and limits
8. **`storage`** - PVC and volume information
9. **`error_incidents`** - Failure tracking and incident details
10. **`notes`** - Additional observations and context

## Validation Rules

### Structural Validation (SV-001, SV-002, SV-003)

#### SV-001: Top-Level Structure
**Severity**: CRITICAL  
**Description**: Validates presence of required top-level sections (metadata, cluster_deployments, summary)  
**Impact**: Deployment data is incomplete without required sections  
**Example Failure**:
```json
❌ Missing required section: "cluster_deployments"
```

#### SV-002: Metadata Structure  
**Severity**: CRITICAL  
**Description**: Validates metadata field presence, types, and non-empty array requirements  
**Required Fields**:
- `generated_at` (string, ISO 8601 timestamp)
- `data_period_start` (string, ISO 8601 timestamp)
- `data_period_end` (string, ISO 8601 timestamp)  
- `services` (array, minItems: 1, must contain "whisper-stt")
- `clusters` (array, minItems: 1)
- `data_sources` (array, minItems: 1)

**Impact**: Cannot validate data period or scope without complete metadata

#### SV-003: Service-Specific Structure
**Severity**: CRITICAL  
**Description**: Validates service deployment data structure and required fields  
**Required Fields**:
- `namespace` (string)
- `deployment_name` (string)
- `created_at` (string, ISO 8601 timestamp)
- `current_image` (string, pattern: `registry/name:tag`)
- `current_replicas` (integer, >= 0)
- `replica_history` (array, minItems: 5)
- `deployments_last_30_days` (integer, >= 0)
- `successful_deployments` (integer, >= 0)
- `failed_deployments` (integer, >= 0)
- `deployment_versions` (array, minItems: 1)

**Impact**: Cannot perform completeness analysis without service data

### Temporal Validation (TV-001, TV-002, TV-003)

#### TV-001: 30-Day Coverage
**Severity**: CRITICAL if < 28 days, WARNING if < 30 days  
**Description**: Validates deployment data covers minimum 28 days (recommended 30) within analysis period  
**Thresholds**:
- **CRITICAL**: Less than 28 days covered
- **WARNING**: 28-29 days covered  
- **PASS**: 30 days covered

**Impact**: Insufficient data for trend analysis and pattern detection

#### TV-002: Timestamp Validity
**Severity**: CRITICAL  
**Description**: Validates all timestamp fields are in ISO 8601 format, not in the future, and not unreasonably old  
**Format**: ISO 8601 with timezone (e.g., `2026-08-06T09:30:00Z`)

**Note**: JSON Schema `format: "date-time"` is informational for some validators. For strict timestamp validation, use the completeness validation module.

#### TV-003: Timestamp Consistency
**Severity**: CRITICAL  
**Description**: Validates timestamp relationships: `data_period_start < data_period_end <= generated_at`  
**Impact**: Inconsistent timestamps indicate data generation errors

### Data Quality Validation (DQ-001, DQ-002, DQ-003)

#### DQ-001: Required Fields Presence
**Severity**: CRITICAL  
**Description**: Validates critical fields are present and non-null  
**Critical Fields**: namespace, deployment_name, current_image, replica_history  
**Impact**: Missing critical fields prevents deployment analysis

#### DQ-002: Numeric Field Ranges
**Severity**: CRITICAL  
**Description**: Validates numeric fields are non-negative and aggregate consistency  
**Rules**:
- All numeric fields >= 0
- `successful_deployments + failed_deployments <= total_deployments`

**Impact**: Invalid numeric values indicate data corruption

#### DQ-003: Enum Field Validity
**Severity**: WARNING  
**Description**: Validates status fields contain only allowed enum values  
**Valid Status Values**:
- ArgoCD sync: `["Synced", "OutOfSync", "Unknown"]`
- ArgoCD health: `["Healthy", "Progressing", "Degraded", "Missing", "Unknown"]`
- ReplicaSet status: `["successful", "rolled_over", "scaled_down_or_failed", "failed"]`
- Pod status: `["Running", "Pending", "Failed", "Succeeded", "Unknown"]`

**Impact**: Invalid status values may indicate data collection errors

### Completeness Validation (CV-001, CV-002, CV-003, CV-004)

#### CV-001: Minimum Deployment Days
**Severity**: CRITICAL if < 5 days, WARNING if < 10 days  
**Description**: Validates minimum 5 distinct deployment days (recommended 10) in replica_history  
**Thresholds**:
- **CRITICAL**: Less than 5 distinct deployment days
- **WARNING**: 5-9 distinct deployment days
- **PASS**: 10+ distinct deployment days

**Impact**: Insufficient deployment activity for reliability analysis

#### CV-002: Gap Detection
**Severity**: WARNING if gap >= 7 days, CRITICAL if gap >= 14 days  
**Description**: Detects significant gaps between consecutive deployments  
**Thresholds**:
- **WARNING**: Gap of 7-13 days
- **CRITICAL**: Gap of 14+ days

**Impact**: Gaps indicate missing data or service downtime affecting analysis completeness

#### CV-003: Replica History Completeness
**Severity**: CRITICAL  
**Description**: Validates replica_history is not empty and contains sufficient records  
**Minimum Records**: 5 replica history entries required  
**Impact**: Empty replica history prevents all deployment analysis

#### CV-004: Summary Metrics Consistency
**Severity**: WARNING  
**Description**: Validates summary metrics match cluster deployment data  
**Checks**:
- `summary.total_deployments_last_30_days` matches `cluster_deployments.{service}.deployments_last_30_days`
- `summary.gaps_detected` matches actual gap analysis

**Impact**: Inconsistent summary metrics indicate data aggregation errors

### Cross-Service Validation (CSV-001, CSV-002)

#### CSV-001: Data Period Alignment
**Severity**: WARNING  
**Description**: Validates all services use the same global data period for multi-service comparison  
**Impact**: Misaligned periods prevent cross-service analysis

#### CSV-002: Multi-Service Comparison
**Severity**: INFO  
**Description**: Validates data structure supports multiple services for comparative analysis  
**Impact**: Single-service data cannot be compared across services

## Field Documentation

### Metadata Fields

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `generated_at` | string | Yes | Timestamp when data was generated | `2026-08-06T09:30:00Z` |
| `data_period_start` | string | Yes | Start of 30-day analysis window | `2026-07-06T00:00:00Z` |
| `data_period_end` | string | Yes | End of 30-day analysis window | `2026-08-06T09:30:00Z` |
| `services` | array | Yes | Services covered (must include "whisper-stt") | `["whisper-stt"]` |
| `clusters` | array | Yes | Clusters queried for data | `["ardenone-cluster"]` |
| `data_sources` | array | Yes | Data sources used | `["kubernetes_replicasets", "argo_workflows"]` |

### Cluster Deployments Fields

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `namespace` | string | Yes | Kubernetes namespace | `whisper-stt` |
| `deployment_name` | string | Yes | Deployment resource name | `whisper-stt` |
| `created_at` | string | Yes | Initial deployment timestamp | `2026-05-01T17:26:49Z` |
| `current_image` | string | Yes | Current container image | `ronaldraygun/whisper-stt:1.8.6` |
| `current_replicas` | integer | Yes | Current running replicas | `1` |
| `replica_history` | array | Yes | ReplicaSet history (min 5 entries) | See below |
| `deployments_last_30_days` | integer | Yes | Total deployments in period | `4` |
| `successful_deployments` | integer | Yes | Successful deployments | `1` |
| `failed_deployments` | integer | Yes | Failed/scaled-down deployments | `3` |

### Replica History Entry Fields

Each entry in `replica_history` must include:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `name` | string | Yes | ReplicaSet name | `whisper-stt-847fd8d7b9` |
| `created_at` | string | Yes | ReplicaSet creation timestamp | `2026-07-12T16:53:42Z` |
| `image` | string | Yes | Container image used | `ronaldraygun/whisper-stt:1.8.6` |
| `replicas` | integer | Yes | Number of replicas | `1` |
| `available_replicas` | integer | No | Available replicas (nullable) | `1` |
| `ready_replicas` | integer | No | Ready replicas (nullable) | `1` |
| `status` | string | Yes | Deployment outcome | `successful` |
| `days_ago` | integer | Yes | Days since creation (0-30) | `25` |

## Common Validation Issues

### Issue 1: Missing Required Fields

**Error**: `'field_name' is a required property`  
**Cause**: Required field is missing from the data  
**Solution**: Add the missing field with appropriate value

**Example**:
```json
❌ {
  "metadata": {
    "data_period_start": "2026-07-06T00:00:00Z"
    // Missing: generated_at, data_period_end, services, clusters, data_sources
  }
}

✅ {
  "metadata": {
    "generated_at": "2026-08-06T09:30:00Z",
    "data_period_start": "2026-07-06T00:00:00Z",
    "data_period_end": "2026-08-06T09:30:00Z",
    "services": ["whisper-stt"],
    "clusters": ["ardenone-cluster"],
    "data_sources": ["kubernetes_replicasets"]
  }
}
```

### Issue 2: Insufficient Replica History

**Error**: `replica_history is too short (minimum 5 items)`  
**Cause**: replica_history array has fewer than 5 entries  
**Solution**: Add missing replica history entries or extend data collection period

**Example**:
```json
❌ "replica_history": [
  {"name": "rs-1", ...},
  {"name": "rs-2", ...}
]  // Only 2 entries

✅ "replica_history": [
  {"name": "rs-1", ...},
  {"name": "rs-2", ...},
  {"name": "rs-3", ...},
  {"name": "rs-4", ...},
  {"name": "rs-5", ...}
]  // 5 entries minimum
```

### Issue 3: Invalid Status Value

**Error**: `'invalid_status' is not one of ['successful', 'rolled_over', 'scaled_down_or_failed', 'failed']`  
**Cause**: Status field contains invalid enum value  
**Solution**: Use only allowed status values

**Example**:
```json
❌ {"status": "deployed"}  // Invalid
✅ {"status": "successful"}  // Valid
```

### Issue 4: Negative Numeric Value

**Error**: `-1 is less than the minimum of 0`  
**Cause**: Numeric field contains negative value  
**Solution**: Ensure all numeric fields are non-negative

**Example**:
```json
❌ {"current_replicas": -1}  // Invalid
✅ {"current_replicas": 1}  // Valid
```

### Issue 5: Invalid Image Format

**Error**: `Does not match pattern '^[a-z0-9-]+/[a-z0-9-]+:[\\w.+]+$'`  
**Cause**: Container image doesn't match registry/name:tag pattern  
**Solution**: Use proper image format

**Example**:
```json
❌ "whisper-stt:1.8.6"  // Missing registry
❌ "ronaldraygun/whisper-stt"  // Missing tag
✅ "ronaldraygun/whisper-stt:1.8.6"  // Valid format
```

## Testing

### Run Validation Tests

```bash
# Run comprehensive test suite
.venv/bin/python test-schema-validation.py

# Expected output:
# ✅ All validation tests passed - schema is working correctly
```

### Test Your Deployment Data

```python
import json
from jsonschema import validate, ValidationError

# Load schema
with open('deployment-data-schema-comprehensive.json') as f:
    schema = json.load(f)

# Load your data
with open('your-deployment-data.json') as f:
    data = json.load(f)

# Validate
try:
    validate(instance=data, schema=schema)
    print("✅ Schema validation successful")
    print(f"✅ Data period: {data['metadata']['data_period_start']} to {data['metadata']['data_period_end']}")
    print(f"✅ Coverage: {data['summary']['data_coverage']}")
    print(f"✅ Deployments: {data['summary']['total_deployments_last_30_days']}")
except ValidationError as e:
    print(f"❌ Validation failed: {e.message}")
    print(f"   Path: {'.'.join(str(p) for p in e.path)}")
```

## Advanced Usage

### Custom Validation Rules

For validation beyond JSON Schema (e.g., strict timestamp validation, gap detection), use the completeness validation module:

```python
from src.validation.validate_completeness import validate_30day_completeness

# Load data
with open('your-deployment-data.json') as f:
    data = json.load(f)

# Run comprehensive validation
result = validate_30day_completeness(data, service_name="whisper-stt")

# Check results
if result['status'] == 'PASS':
    print("✅ 30-day completeness validation passed")
else:
    print(f"❌ Validation failed: {result['status']}")
    for error in result['errors']:
        print(f"   [{error['rule_id']}] {error['message']}")
```

### Multi-Service Validation

```python
# Validate multiple services
services = ["whisper-stt", "pbx-web"]
for service in services:
    result = validate_30day_completeness(data, service_name=service)
    print(f"{service}: {result['status']}")
```

## Integration Points

This schema validates data from these sources:

- **Kubernetes API**: ReplicaSet queries via `traefik-ardenone-cluster:8001`
- **Argo Workflows**: Build pipeline execution tracking  
- **ArgoCD**: Application sync and health monitoring
- **Git History**: Deployment commit analysis
- **Pod Monitoring**: Current pod status and metrics

## Schema Maintenance

### Version History

- **v1.0** (2026-08-11): Comprehensive schema with 30-day completeness validation
  - Structural validation (SV-001, SV-002, SV-003)
  - Temporal validation (TV-001, TV-002, TV-003)
  - Data quality validation (DQ-001, DQ-002, DQ-003)
  - Completeness validation (CV-001, CV-002, CV-003, CV-004)
  - Cross-service validation (CSV-001, CSV-002)

### Extending the Schema

To add validation for new services or fields:

1. Add new properties to existing sections
2. Update `required` arrays if fields are mandatory  
3. Add new enum values for status fields
4. Update documentation with validation examples
5. Add tests to `test-schema-validation.py`

### Schema Testing

Test schema changes against known valid and invalid datasets:

```bash
# Test valid data (should pass)
jsonschema -i sample-whisper-stt-deployment-data.json deployment-data-schema-comprehensive.json

# Test invalid data (should fail)
echo '{"invalid": "data"}' | jsonschema -i /dev/stdin deployment-data-schema-comprehensive.json
```

## Limitations

### Timestamp Format Validation

JSON Schema's `format: "date-time"` keyword is informational for some validators (including the standard `jsonschema` library). For strict timestamp validation, use the completeness validation module:

```python
# Schema validation (timestamp format not enforced)
validate(instance=data, schema=schema)

# Strict timestamp validation (enforced)
from src.validation.validate_completeness import validate_30day_completeness
result = validate_30day_completeness(data)
```

### Complex Validation Rules

Some validation rules require procedural logic beyond JSON Schema:

- Gap detection and analysis
- Timestamp consistency checks
- Aggregate consistency validation  
- Cross-service period alignment

For these validations, use the `validate_30day_completeness` function.

## Support and Issues

For schema validation issues or enhancement requests, reference:
- **Task ID**: adc-6b7c8
- **Task**: Document and finalize deployment data schema
- **Acceptance Criteria**: Schema includes detailed field documentation, validation rule descriptions, tested against sample data

## Related Documentation

- [Deployment Data 30-Day Completeness Validation Rules](docs/research/deployment-data/)
- [Whisper-STT Deployment Schema README](whisper-stt-deployment-schema-README.md)
- [Validation Module Documentation](src/validation/validate_completeness.py)

---

**Schema Compliance**: Deployment data files matching this schema are validated for structural integrity, 30-day completeness, type safety, and operational analysis requirements.