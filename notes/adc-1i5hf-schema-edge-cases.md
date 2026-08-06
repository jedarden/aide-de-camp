# Schema Edge Cases and Validation Scenarios

## Overview

This document comprehensively identifies all edge cases that the Pod-Logs JSONL schema must handle, defines how each case is represented in JSONL format, documents validation rules, and provides examples for each scenario.

**Schema Version:** 1.0  
**Date:** 2026-08-06  
**Scope:** Pod-Logs JSONL Index Schema (28 fields across 5 categories)

---

## Edge Case Categories

### 1. Missing Analysis Files
### 2. Empty Log Files
### 3. Deleted/Terminated Pods
### 4. Missing/Invalid Timestamps
### 5. Array Consistency Issues
### 6. Null vs Empty vs Omitted Fields
### 7. Unicode and Special Characters
### 8. Malformed Data Structures
### 9. Large Payload Edge Cases
### 10. Cross-Field Constraint Violations

---

## 1. Missing Analysis Files

### Description
Analysis files (`*-analysis.json`) may not exist for log files that haven't been processed yet or when analysis generation failed.

### Representation Strategy
- `analysis_metadata.analysis_file_path`: `null`
- `analysis_metadata.analysis_date`: `null`
- `pattern_detection`: All pattern categories have `count: 0`, empty arrays
- `temporal_boundaries.first_log_entry`: `null`
- `temporal_boundaries.last_log_entry`: `null`
- `temporal_boundaries.analysis_date`: `null`

### Validation Rules
- `analysis_file_path` must be `null` (not empty string)
- `analysis_date` must be `null` (not empty string)
- All pattern counts must be `0`
- All pattern arrays must be empty `[]`
- `first_log_entry` and `last_log_entry` must be `null`

### Example
```json
{
  "pod_identification": {
    "pod_name": "pbx-web-5ff68464d-mkn8n",
    "namespace": "pbx-web",
    "pod_phase": "Running",
    "restart_count": 0,
    "creation_timestamp": "2026-07-28T17:26:12Z",
    "deletion_timestamp": null,
    "container_image": "ronaldraygun/pbx-web:1.0.9",
    "node_name": "k3s-agent-minisforum"
  },
  "log_file_metadata": {
    "log_file_path": "research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log",
    "log_size_bytes": 62900,
    "log_line_count": 2762,
    "collection_date": "2026-08-06",
    "log_type": "current"
  },
  "analysis_metadata": {
    "analysis_file_path": null,
    "analysis_date": null
  },
  "pattern_detection": {
    "startup": {"count": 0, "timestamps": [], "samples": []},
    "oom_kill": {"count": 0, "timestamps": [], "samples": []},
    "error": {"count": 0, "timestamps": [], "samples": []},
    "performance": {"count": 0, "timestamps": [], "samples": []}
  },
  "temporal_boundaries": {
    "first_log_entry": null,
    "last_log_entry": null,
    "analysis_date": null,
    "collection_date": "2026-08-06"
  }
}
```

---

## 2. Empty Log Files

### Description
Log files may be empty (0 bytes) when a pod was created but produced no output, or when the log collection happened immediately after pod creation.

### Representation Strategy
- `log_file_metadata.log_size_bytes`: `0`
- `log_file_metadata.log_line_count`: `0` (can be `null` for unanalyzed files)
- `temporal_boundaries.first_log_entry`: `null` (no log entries exist)
- `temporal_boundaries.last_log_entry`: `null`

### Validation Rules
- `log_size_bytes` must be exactly `0`
- `log_line_count` must be `0` or `null`
- `log_line_count` must not be negative
- `first_log_entry` and `last_log_entry` must be `null` for empty files

### Example
```json
{
  "pod_identification": {
    "pod_name": "pbx-web-5ff68464d-empty",
    "namespace": "pbx-web",
    "pod_phase": "Running",
    "restart_count": 0,
    "creation_timestamp": "2026-08-06T10:00:00Z",
    "deletion_timestamp": null,
    "container_image": "ronaldraygun/pbx-web:1.0.9",
    "node_name": "k3s-agent-minisforum"
  },
  "log_file_metadata": {
    "log_file_path": "research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-empty-2026-08-06.log",
    "log_size_bytes": 0,
    "log_line_count": 0,
    "collection_date": "2026-08-06",
    "log_type": "current"
  },
  "analysis_metadata": {
    "analysis_file_path": null,
    "analysis_date": null
  },
  "pattern_detection": {
    "startup": {"count": 0, "timestamps": [], "samples": []},
    "oom_kill": {"count": 0, "timestamps": [], "samples": []},
    "error": {"count": 0, "timestamps": [], "samples": []},
    "performance": {"count": 0, "timestamps": [], "samples": []}
  },
  "temporal_boundaries": {
    "first_log_entry": null,
    "last_log_entry": null,
    "analysis_date": null,
    "collection_date": "2026-08-06"
  }
}
```

---

## 3. Deleted/Terminated Pods

### Description
Pods may be in terminated states (Failed, Succeeded) with deletion timestamps set, indicating they are no longer running.

### Representation Strategy
- `pod_identification.pod_phase`: `"Failed"` or `"Succeeded"`
- `pod_identification.deletion_timestamp`: ISO 8601 timestamp (not `null`)
- `deletion_timestamp` must be ≥ `creation_timestamp`
- All other fields populated normally

### Validation Rules
- `pod_phase` must be one of: `"Failed"`, `"Succeeded"`, `"Unknown"` (terminated states)
- `deletion_timestamp` must NOT be `null`
- `deletion_timestamp` must be ≥ `creation_timestamp`
- `deletion_timestamp` must be valid ISO 8601 format with Z suffix

### Example
```json
{
  "pod_identification": {
    "pod_name": "pbx-web-5ff68464d-failed",
    "namespace": "pbx-web",
    "pod_phase": "Failed",
    "restart_count": 3,
    "creation_timestamp": "2026-08-05T10:00:00Z",
    "deletion_timestamp": "2026-08-06T10:00:00Z",
    "container_image": "ronaldraygun/pbx-web:1.0.9",
    "node_name": "k3s-agent-minisforum"
  },
  "log_file_metadata": {
    "log_file_path": "research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-failed-2026-08-06.log",
    "log_size_bytes": 125000,
    "log_line_count": 5234,
    "collection_date": "2026-08-06",
    "log_type": "previous"
  },
  "analysis_metadata": {
    "analysis_file_path": "pod-pbx-web-5ff68464d-failed-2026-08-06-analysis.json",
    "analysis_date": "2026-08-06T13:40:21.580554Z"
  },
  "pattern_detection": {
    "startup": {"count": 4, "timestamps": ["1754768400", "1754772000", "1754775600", "1754779200"], "samples": ["Application started", "Application started", "Application started", "Application started"]},
    "oom_kill": {"count": 3, "timestamps": ["1754772100", "1754775800", "1754779500"], "samples": ["Killed process", "Killed process", "Killed process"]},
    "error": {"count": 42, "timestamps": ["1754777704", "unknown"], "samples": ["Error: connection refused", "Fatal: cannot connect to database"]},
    "performance": {"count": 0, "timestamps": [], "samples": []}
  },
  "temporal_boundaries": {
    "first_log_entry": "2026-08-05T10:00:15Z",
    "last_log_entry": "2026-08-06T09:59:45Z",
    "analysis_date": "2026-08-06T13:40:20.792334Z",
    "collection_date": "2026-08-06"
  }
}
```

---

## 4. Missing/Invalid Timestamps

### Description
Timestamps may be missing (`null`), invalid format, or contain timezone inconsistencies.

### Representation Strategies

#### 4.1 Null Timestamps
```json
{
  "pod_identification": {
    "creation_timestamp": null,
    "deletion_timestamp": null
  },
  "temporal_boundaries": {
    "first_log_entry": null,
    "last_log_entry": null,
    "analysis_date": null
  }
}
```

#### 4.2 Invalid Timestamp Format (Should be rejected)
```json
{
  "pod_identification": {
    "creation_timestamp": "not-a-timestamp",  // INVALID
    "deletion_timestamp": "2026-08-06 10:00:00"  // INVALID (no Z suffix)
  }
}
```

#### 4.3 Microseconds in Temporal Fields
```json
{
  "temporal_boundaries": {
    "first_log_entry": "2026-08-06T10:00:15.123456Z",  // VALID (microseconds allowed)
    "last_log_entry": "2026-08-06T12:30:45.789012Z"
  }
}
```

### Validation Rules
- **Null timestamps:** Must be `null`, NOT empty string `""`
- **ISO 8601 format:** Must match `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$`
- **Timezone:** Must use UTC (`Z` suffix), not `+00:00` or other offsets
- **Microseconds:** Allowed in `analysis_date` and `temporal_boundaries.*`
- **Temporal ordering:** `first_log_entry` ≤ `last_log_entry` < `analysis_date` (when all non-null)

---

## 5. Array Consistency Issues

### Description
Pattern detection arrays must have consistent lengths with their counts.

### Valid Example
```json
{
  "pattern_detection": {
    "error": {
      "count": 2,
      "timestamps": ["1785277704", "1785277800"],
      "samples": ["Error: connection refused", "Fatal: database timeout"]
    }
  }
}
```

### Invalid Examples

#### 5.1 Count Mismatch
```json
{
  "pattern_detection": {
    "error": {
      "count": 2,  // INVALID: count doesn't match array length
      "timestamps": ["1785277704"],
      "samples": ["Error: connection refused"]
    }
  }
}
```

#### 5.2 Array Length Mismatch
```json
{
  "pattern_detection": {
    "error": {
      "count": 2,
      "timestamps": ["1785277704", "1785277800"],
      "samples": ["Error: connection refused"]  // INVALID: only 1 sample
    }
  }
}
```

#### 5.3 Non-Zero Count with Empty Arrays
```json
{
  "pattern_detection": {
    "error": {
      "count": 1,  // INVALID: count is 1 but arrays are empty
      "timestamps": [],
      "samples": []
    }
  }
}
```

#### 5.4 Valid Zero Count with Empty Arrays
```json
{
  "pattern_detection": {
    "error": {
      "count": 0,  // VALID: zero count with empty arrays
      "timestamps": [],
      "samples": []
    }
  }
}
```

### Validation Rules
- **Consistency:** `count === timestamps.length === samples.length`
- **Zero count rule:** If `count === 0`, arrays MUST be empty `[]`
- **Non-zero count:** Arrays must have exactly `count` elements
- **Timestamp values:** Each element must be Unix epoch string OR `"unknown"`
- **Sample values:** Each element must be non-empty string (min length 1)

---

## 6. Null vs Empty vs Omitted Fields

### Description
The schema must distinguish between `null`, empty values, and omitted fields.

### Representation Strategy

#### 6.1 Null Fields (Explicitly No Data)
```json
{
  "pod_identification": {
    "deletion_timestamp": null,  // Pod is running, no deletion timestamp
    "container_image": null,      // Image not available
    "node_name": null            // Node not available
  },
  "analysis_metadata": {
    "analysis_file_path": null,  // No analysis file exists
    "analysis_date": null
  }
}
```

#### 6.2 Empty Fields (Zero-Value Defaults)
```json
{
  "log_file_metadata": {
    "log_size_bytes": 0,         // Empty file
    "log_line_count": 0           // No lines
  },
  "pattern_detection": {
    "startup": {
      "count": 0,
      "timestamps": [],          // Empty array
      "samples": []               // Empty array
    }
  }
}
```

#### 6.3 Omitted Fields (NOT ALLOWED)
All 28 leaf fields are REQUIRED - fields cannot be omitted. The top-level objects are also required.

### Validation Rules
- **Required fields:** All 28 leaf fields MUST be present
- **Null handling:** Only nullable fields may be `null` (10 fields total)
- **Empty arrays:** MUST be `[]`, not `null` or omitted
- **Empty strings:** NOT allowed for required non-nullable string fields
- **Zero values:** Allowed for numeric fields (`restart_count`, `log_size_bytes`, `log_line_count`, all pattern counts)

### Field Nullability Matrix

| Category | Nullable Fields | Non-Nullable Fields |
|----------|----------------|---------------------|
| **pod_identification** | `pod_phase`, `deletion_timestamp`, `container_image`, `node_name` | `pod_name`, `namespace`, `restart_count`, `creation_timestamp` |
| **log_file_metadata** | `log_line_count`, `log_type` | `log_file_path`, `log_size_bytes`, `collection_date` |
| **analysis_metadata** | `analysis_file_path`, `analysis_date` | (none) |
| **pattern_detection** | (none - but arrays can be empty) | All `count` fields, all array objects |
| **temporal_boundaries** | `first_log_entry`, `last_log_entry`, `analysis_date` | `collection_date` |

---

## 7. Unicode and Special Characters

### Description
Log data may contain Unicode characters, emoji, special escape sequences, and null characters.

### Valid Examples

#### 7.1 Unicode Emoji
```json
{
  "pattern_detection": {
    "error": {
      "count": 1,
      "timestamps": ["1785277704"],
      "samples": ["Error: ❌ Connection failed 🔴"]
    }
  }
}
```

#### 7.2 Chinese Characters
```json
{
  "pattern_detection": {
    "error": {
      "count": 1,
      "timestamps": ["1785277704"],
      "samples": ["错误：数据库连接失败"]
    }
  }
}
```

#### 7.3 Arabic Characters (RTL Text)
```json
{
  "pattern_detection": {
    "error": {
      "count": 1,
      "timestamps": ["1785277704"],
      "samples": ["خطأ: فشل الاتصال بقاعدة البيانات"]
    }
  }
}
```

#### 7.4 Cyrillic Characters
```json
{
  "pattern_detection": {
    "error": {
      "count": 1,
      "timestamps": ["1785277704"],
      "samples": ["Ошибка: подключение к базе данных не удалось"]
    }
  }
}
```

#### 7.5 Special Escape Sequences
```json
{
  "pattern_detection": {
    "error": {
      "count": 1,
      "timestamps": ["1785277704"],
      "samples": ["Error: Line 1\nLine 2\tTabbed"]
    }
  }
}
```

#### 7.6 Null Character (Via Unicode Escape)
```json
{
  "pattern_detection": {
    "error": {
      "count": 1,
      "timestamps": ["1785277704"],
      "samples": ["Error: Invalid character\\u0000in input"]
    }
  }
}
```

### Validation Rules
- **UTF-8 encoding:** All strings must be valid UTF-8
- **Unicode escapes:** Valid JSON escapes (`\\uXXXX`) are allowed
- **Control characters:** Must be properly escaped (e.g., `\\n`, `\\t`, `\\u0000`)
- **Emoji and multi-byte:** Preserved as-is (no transformation)
- **RTL text:** Preserved as-is (no reordering)

---

## 8. Malformed Data Structures

### Description
Structural issues that violate the schema or produce unparseable JSON.

### Invalid Examples

#### 8.1 Missing Required Object
```json
{
  "pod_identification": {...},
  "log_file_metadata": {...},
  // "analysis_metadata": {...},  // INVALID: missing required object
  "pattern_detection": {...},
  "temporal_boundaries": {...}
}
```

#### 8.2 Wrong Type for Object
```json
{
  "pod_identification": "not-an-object",  // INVALID: must be object
  "log_file_metadata": {...}
}
```

#### 8.3 Wrong Type for Array
```json
{
  "pattern_detection": {
    "error": {
      "count": 1,
      "timestamps": "not-an-array",  // INVALID: must be array
      "samples": ["Error: connection refused"]
    }
  }
}
```

#### 8.4 Wrong Type for Numeric Field
```json
{
  "pod_identification": {
    "restart_count": "0",  // INVALID: must be integer, not string
    "creation_timestamp": "2026-08-06T10:00:00Z"
  }
}
```

#### 8.5 Extra Unknown Field
```json
{
  "pod_identification": {
    "pod_name": "pbx-web-5ff68464d-mkn8n",
    "unknown_field": "value"  // INVALID: not in schema
  }
}
```

### Validation Rules
- **Type checking:** All fields must match their declared types (string, integer, array, object)
- **Required objects:** All 5 top-level objects must be present
- **Required leaf fields:** All 28 leaf fields must be present within their objects
- **Unknown fields:** Should be rejected or ignored (implementation choice)
- **Structural integrity:** JSON must be parseable without syntax errors

---

## 9. Large Payload Edge Cases

### Description
Very large arrays, deeply nested structures, or massive payloads that could cause performance issues.

### Valid Examples

#### 9.1 Large Pattern Arrays
```json
{
  "pattern_detection": {
    "error": {
      "count": 10000,
      "timestamps": ["1680000000", "1680000001", ..., "1680099999"],
      "samples": ["Error line 1", "Error line 2", ..., "Error line 10000"]
    }
  }
}
```

#### 9.2 Deeply Nested JSON
While the pod-logs schema is flat (no deep nesting), analysis files might contain deeply nested structures:
```json
{
  "analysis_metadata": {
    "analysis_file_path": "pod-complex-analysis.json",
    "analysis_date": "2026-08-06T13:40:21.580554Z"
  }
}
// The analysis.json file referenced could contain deeply nested data
```

### Validation Rules
- **Performance:** Validation should complete in <1 second for typical payloads
- **Memory:** Should handle 10,000+ element arrays without excessive memory usage
- **Recursion depth:** Deep nesting in referenced files shouldn't crash the validator
- **Error messages:** Large malformed payloads should produce clear error messages with context snippets

---

## 10. Cross-Field Constraint Violations

### Description
Inconsistencies between related fields that violate business rules.

### Invalid Examples

#### 10.1 Temporal Ordering Violation
```json
{
  "temporal_boundaries": {
    "first_log_entry": "2026-08-06T12:00:00Z",
    "last_log_entry": "2026-08-06T10:00:00Z"  // INVALID: before first_log_entry
  }
}
```

#### 10.2 Analysis Date Before Log Collection
```json
{
  "temporal_boundaries": {
    "collection_date": "2026-08-06",
    "analysis_date": "2026-08-05T13:40:21Z"  // INVALID: before collection_date
  }
}
```

#### 10.3 Deletion Before Creation
```json
{
  "pod_identification": {
    "creation_timestamp": "2026-08-06T10:00:00Z",
    "deletion_timestamp": "2026-08-05T10:00:00Z"  // INVALID: before creation
  }
}
```

#### 10.4 Analysis After Collection But Before Log End
```json
{
  "temporal_boundaries": {
    "first_log_entry": "2026-08-05T10:00:00Z",
    "last_log_entry": "2026-08-06T12:00:00Z",
    "analysis_date": "2026-08-06T11:00:00Z"  // INVALID: before last_log_entry
  }
}
```

### Validation Rules
- **Temporal ordering:** `first_log_entry` ≤ `last_log_entry` < `analysis_date` (when all non-null)
- **Collection constraint:** `collection_date` ≤ `analysis_date` (when both non-null)
- **Pod lifecycle:** `creation_timestamp` ≤ `deletion_timestamp` (when both non-null)
- **Null handling:** If any field in a constraint is `null`, the constraint is not violated

---

## Edge Case Severity Classification

### Critical (Must Reject)
- Missing required top-level objects
- Missing required leaf fields
- Invalid timestamp formats
- Wrong field types
- Cross-field constraint violations
- Array length mismatches with counts

### Warning (Should Flag)
- Very large arrays (>10,000 elements)
- Unicode surrogate pairs or complex emoji
- Mixed line endings in files
- Unknown fields

### Info (May Log)
- Null values in normally populated fields
- Empty arrays in non-error pattern categories
- Microseconds in timestamps (unusual but valid)

---

## Testing Strategy

### Unit Test Coverage
1. **Null handling:** Test each nullable field with `null` values
2. **Empty values:** Test zero counts, empty arrays, zero-byte files
3. **Type checking:** Test wrong types for each field
4. **Array consistency:** Test count/array mismatches
5. **Temporal ordering:** Test all cross-field timestamp constraints
6. **Unicode:** Test emoji, RTL text, multi-byte characters
7. **Large payloads:** Test arrays with 10,000+ elements

### Integration Test Coverage
1. **Full entries:** Test complete valid entries
2. **Missing analysis:** Test entries without analysis files
3. **Empty logs:** Test entries with 0-byte log files
4. **Terminated pods:** Test entries with deletion timestamps
5. **File I/O:** Test reading/writing JSONL files

### Property-Based Testing
1. **Timestamp ordering:** Generate random timestamps and verify constraints
2. **Array consistency:** Generate random counts and verify array lengths
3. **Unicode safety:** Generate random Unicode strings and verify validity

---

## Validation Implementation Checklist

### Type Validators
- [ ] String fields (with timestamp validation for date fields)
- [ ] Integer fields (strict type checking)
- [ ] Float fields (accept int or float)
- [ ] Array fields (strict type checking)
- [ ] Object fields (structural validation)

### Constraint Validators
- [ ] Temporal ordering (all timestamp relationships)
- [ ] Array length consistency (count === array.length)
- [ ] Null vs empty distinction
- [ ] Field presence (all 28 fields required)
- [ ] Regex patterns (DNS subdomain, container image, timestamps)

### Edge Case Handlers
- [ ] Missing analysis files (null metadata + zero patterns)
- [ ] Empty log files (zero bytes + null timestamps)
- [ ] Terminated pods (deletion_timestamp validation)
- [ ] Unicode and special characters (UTF-8 validation)
- [ ] Large payloads (performance validation)

---

## Example Validation Function Signatures

```python
def validate_pod_logs_entry(entry: dict) -> Tuple[bool, List[str]]:
    """Validate a complete pod-logs JSONL entry."""
    pass

def validate_temporal_boundaries(boundaries: dict) -> Tuple[bool, List[str]]:
    """Validate temporal ordering constraints."""
    pass

def validate_pattern_arrays(category: dict) -> Tuple[bool, List[str]]:
    """Validate count/array consistency for a pattern category."""
    pass

def validate_timestamp_format(timestamp: Optional[str], allow_microseconds: bool = False) -> bool:
    """Validate ISO 8601 timestamp format."""
    pass
```

---

## Conclusion

This documentation covers all major edge cases the Pod-Logs JSONL schema must handle. Each edge case includes:

1. **Description:** What the edge case is
2. **Representation:** How it's represented in JSONL
3. **Validation Rules:** What constraints must be enforced
4. **Examples:** Valid and invalid JSONL snippets

Implementing validation according to these rules ensures robust handling of real-world data including missing files, empty logs, terminated pods, Unicode content, and various structural anomalies.

---

## Related Documentation

- **Schema Definition:** `notes/adc-663bz-schema-definition.md`
- **Session Store Schema:** `notes/adc-13874-session-store-schema.md`
- **Validation Implementation:** `docs/adc-1r71j-data-type-validation-implementation.md`
- **JSON Parsing Edge Cases:** `tests/test_json_parsing_edge_cases.py`
- **Persistence Edge Cases:** `test_persistence_edge_cases.py`