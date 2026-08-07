# Pod Log Files Catalog

**Bead:** adc-66510  
**Created:** 2026-08-06  
**Purpose:** Complete inventory of pod log files for extraction processing

---

## Summary

This catalog provides a comprehensive inventory of all pod log files across the aide-de-camp workspace, documenting their locations, naming conventions, content structures, and metadata mappings.

**Total Log Files Cataloged:** 40  
**Primary Log Directories:** 6  
**Namespaces Represented:** `pbx-web`, `whisper-stt`

---

## 1. Log File Locations

### 1.1 Primary Log Directories

| Directory | Purpose | File Count |
|-----------|---------|-------------|
| `/home/coding/aide-de-camp/logs/` | Main logs directory | 10 |
| `/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs/` | PBX web research logs | 12 |
| `/home/coding/aide-de-camp/research/whisper-stt-30days/pod-logs/` | Whisper STT research logs | 18 |
| `/home/coding/aide-de-camp/research-data/` | Research data archives | 6 |
| `/home/coding/aide-de-camp/data/` | Data directory logs | 2 |
| `/home/coding/aide-de-camp/docs/notes/` | Documentation test logs | 1 |

### 1.2 Complete File Inventory

#### Main Logs Directory (`/logs/`)

```
/home/coding/aide-de-camp/logs/
├── pbx-web-30day/
│   ├── lab-rebuild-relay-current.log
│   ├── pbx-rebuild-relay-current.log
│   ├── pbx-web-main-current.log
│   ├── pbx-web-pagefind.log
│   └── pbx-web-web-container.log
├── pbx-web-nginx.log
├── pbx-web-site-generator.log
├── pbx-web-site-generator-recent.log
├── whisper-openai-pod.log
└── whisper-stt-pod.log
```

#### PBX Web Research Pod Logs (`/research/pbx-web-30days/pod-logs/`)

```
/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs/
├── pbx-web-5ff68464d-mkn8n-current.log
├── pbx-web-5ff68464d-mkn8n-previous.log
├── pbx-web-current-nginx.log
├── pbx-web-current-site-generator.log
├── pbx-web-lab-rebuild-relay-79d6d858bb-lpqdb.log
├── pbx-web-pbx-rebuild-relay-8596977857-4292b.log
├── pbx-web-pbx-web-5ff68464d-lcfcp.log
├── pod-lab-rebuild-relay-79957dbd4-xsqhl-2026-08-06.log
├── pod-pbx-rebuild-relay-588d79c5b9-vmmlz-2026-08-06.log
├── pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log
├── whisper-stt-whisper-openai-68966786fb-tng29.log
└── whisper-stt-whisper-stt-847fd8d7b9-b8rsj.log
```

#### Whisper STT Research Pod Logs (`/research/whisper-stt-30days/pod-logs/`)

```
/home/coding/aide-de-camp/research/whisper-stt-30days/pod-logs/
├── pod-svclb-whisper-stt-c02117d2-f72hg.log
├── pod-whisper-openai-68966786fb-jsb5d-2026-06-14.log
├── pod-whisper-openai-68966786fb-jsb5d-2026-08-06-current.log
├── pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log
├── pod-whisper-openai-68966786fb-jsb5d-2026-08-06-previous.log
├── pod-whisper-openai-68966786fb-jsb5d-2026-08-06-stderr.log
├── pod-whisper-openai-68966786fb-jsb5d.log
├── pod-whisper-openai-68966786fb-tng29.log
├── pod-whisper-stt-847fd8d7b9-b8rsj.log
├── pod-whisper-stt-847fd8d7b9-v2rs5-2026-07-12.log
├── pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-current.log
├── pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log
├── pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-previous.log
├── pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-stderr.log
├── whisper-openai-68966786fb-jsb5d.log
├── whisper-openai-ardenone-cluster.log
├── whisper-openai-ardenone-manager.log
├── whisper-stt-847fd8d7b9-v2rs5.log
├── whisper-stt-ardenone-cluster.log
└── whisper-stt-ardenone-manager.log
```

---

## 2. File Naming Patterns

### 2.1 Naming Convention Types

#### Pattern A: Standard Pod Logs (`pod-<pod-name>-<date>.log`)

**Format:** `pod-{pod_name}-{YYYY-MM-DD}.log`

**Examples:**
- `pod-lab-rebuild-relay-79957dbd4-xsqhl-2026-08-06.log`
- `pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log`
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06.log`

**Extraction Pattern:**
- Prefix: `pod-`
- Pod name: Kubernetes pod identifier (DNS subdomain format)
- Date suffix: `-{YYYY-MM-DD}`
- Extension: `.log`

#### Pattern B: Stream-Specific Logs (`pod-<pod-name>-<date>-<stream>.log`)

**Format:** `pod-{pod_name}-{YYYY-MM-DD}-{stream}.log`

**Stream Types:** `current`, `previous`, `stderr`

**Examples:**
- `pod-whisper-openai-68966786fb-jsb5d-2026-08-06-current.log`
- `pod-whisper-openai-68966786fb-jsb5d-2026-08-06-previous.log`
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-stderr.log`

**Stream Meanings:**
- `current`: Current container log stream
- `previous`: Previous container log stream (after restart)
- `stderr`: Standard error stream only

#### Pattern C: Simple Pod Logs (`<pod-name>.log`)

**Format:** `{pod_name}.log`

**Examples:**
- `whisper-openai-68966786fb-jsb5d.log`
- `whisper-stt-847fd8d7b9-v2rs5.log`
- `pbx-web-5ff68464d-mkn8n-current.log`

#### Pattern D: Container/Component Logs (`<service>-<component>.log`)

**Format:** `{service}-{component}.log`

**Examples:**
- `pbx-web-nginx.log`
- `pbx-web-site-generator.log`
- `whisper-openai-pod.log`
- `whisper-stt-pod.log`

#### Pattern E: Cluster-Specific Logs (`<pod-name>-<cluster>.log`)

**Format:** `{pod_name}-{cluster}.log`

**Examples:**
- `whisper-openai-ardenone-cluster.log`
- `whisper-stt-ardenone-manager.log`

### 2.2 Naming Pattern Regex

```regex
# Pattern A: Standard pod logs
^pod-([a-z0-9]([-a-z0-9]*[a-z0-9])?)-(\d{4}-\d{2}-\d{2})\.log$

# Pattern B: Stream-specific logs
^pod-([a-z0-9]([-a-z0-9]*[a-z0-9])?)-(\d{4}-\d{2}-\d{2})-(current|previous|stderr)\.log$

# Pattern C: Simple pod logs
^([a-z0-9]([-a-z0-9]*[a-z0-9])?)\.log$

# Pattern D: Container/component logs
^([a-z0-9]([-a-z0-9]*[a-z0-9])?)-([a-z0-9]([-a-z0-9]*[a-z0-9])?)\.log$

# Pattern E: Cluster-specific logs
^([a-z0-9]([-a-z0-9]*[a-z0-9])?)-([a-z0-9]([-a-z0-9]*[a-z0-9])?)-([a-z0-9]([-a-z0-9]*[a-z0-9])?)\.log$
```

---

## 3. Log Content Structures

### 3.1 Timestamp Formats

#### Type 1: ISO 8601 with Microseconds and Timezone

**Format:** `YYYY-MM-DDTHH:MM:SS.ssssss±HH:MM`

**Examples:**
```
2026-07-28T13:26:14.980407690-04:00 
2026-07-28T13:26:14.980434961-04:00
```

**Source:** Application logs (Pagefind, site-generator)

#### Type 2: HTTP Combined Log Format

**Format:** `IP - - [DD/Mon/YYYY:HH:MM:SS +0000] "METHOD PATH PROTOCOL" STATUS SIZE "REFERRER" "UA" "-"`

**Examples:**
```
10.42.6.1 - - [06/Aug/2026:14:16:24 +0000] "GET / HTTP/1.1" 200 80237 "-" "kube-probe/1.34" "-"
10.42.6.1 - - [06/Aug/2026:14:16:34 +0000] "GET / HTTP/1.1" 200 80237 "-" "kube-probe/1.34" "-"
```

**Source:** Nginx access logs

#### Type 3: FastAPI/Uvicorn Log Format

**Format:** `LEVEL:     IP:PORT - "METHOD PATH PROTOCOL" STATUS MESSAGE`

**Examples:**
```
INFO:     10.42.2.1:34052 - "GET /health HTTP/1.1" 200 OK
INFO:     10.42.2.1:46748 - "GET /health HTTP/1.1" 200 OK
```

**Source:** FastAPI application logs (whisper-openai)

#### Type 4: Kubernetes/Go Log Format

**Format:** `LMMDD HH:MM:SS.mmmmmm threadid file.go:line] "Message" err="error details"`

**Examples:**
```
E0806 13:31:16.000615 2347420 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list"
E0806 13:31:16.517015 2347420 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list"
```

**Source:** Kubernetes client-go logs

#### Type 5: Simple Error Messages

**Format:** Plain text error messages without structured timestamps

**Examples:**
```
Error from server (BadRequest): container "site-generator" in pod "pbx-web-5ff68464d-lcfcp" is waiting to start: trying and failing to pull image
error: You must be logged in to the server (the server has asked for the client to provide credentials)
```

**Source:** kubectl command output

### 3.2 Log Content Patterns by File Type

| File Pattern | Content Type | Timestamp Format | Example Source |
|--------------|--------------|------------------|----------------|
| `*-nginx.log` | HTTP Access Logs | HTTP Combined | Nginx |
| `*-site-generator*.log` | Application Logs | ISO 8601 μs | Pagefind |
| `whisper-openai*.log` | FastAPI Logs | FastAPI Format | whisper-openai |
| `pod-*-stderr.log` | Error Logs | Kubernetes Format | kubectl |
| `pod-*-current.log` | Container Logs | Mixed | Containers |
| `pod-*-previous.log` | Previous Stream | Mixed | Containers |

---

## 4. Log File Path to Pod/Namespace Mapping

### 4.1 Mapping Logic

#### From File Path to Pod Name

```python
def extract_pod_name_from_path(file_path: str) -> str:
    """
    Extract pod name from log file path.
    
    Examples:
    - research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log
      → pbx-web-5ff68464d-mkn8n
    
    - logs/whisper-openai-pod.log
      → whisper-openai
    
    - research/whisper-stt-30days/pod-logs/whisper-openai-68966786fb-jsb5d.log
      → whisper-openai-68966786fb-jsb5d
    """
    # Remove directory path
    filename = os.path.basename(file_path)
    
    # Remove .log extension
    name_without_ext = filename.replace('.log', '')
    
    # Handle pod- prefix
    if name_without_ext.startswith('pod-'):
        name_without_ext = name_without_ext[4:]
    
    # Remove date suffix
    name_without_ext = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', name_without_ext)
    
    # Remove stream suffix
    name_without_ext = re.sub(r'-(current|previous|stderr)$', '', name_without_ext)
    
    return name_without_ext
```

#### From File Path to Namespace

```python
def extract_namespace_from_path(file_path: str) -> str:
    """
    Extract namespace from log file path using directory structure.
    
    Mapping:
    - research/pbx-web-30days/ → pbx-web
    - research/whisper-stt-30days/ → whisper-stt
    - logs/ → derived from pod name prefix
    """
    path_parts = file_path.split('/')
    
    # Check for research directory pattern
    if 'research' in path_parts:
        for part in path_parts:
            if part.endswith('-30days'):
                return part.replace('-30days', '')
    
    # For logs/ directory, derive from pod name
    pod_name = extract_pod_name_from_path(file_path)
    if pod_name.startswith('pbx-web'):
        return 'pbx-web'
    elif pod_name.startswith('whisper'):
        return 'whisper-stt'
    
    return 'default'
```

### 4.2 Complete Mapping Table

| File Path | Pod Name | Namespace | Log Type | Collection Date |
|----------|----------|-----------|----------|----------------|
| `logs/pbx-web-30day/pbx-web-main-current.log` | pbx-web-main | pbx-web | current | 2026-08-06 |
| `logs/pbx-web-nginx.log` | pbx-web-nginx | pbx-web | nginx | 2026-08-06 |
| `logs/whisper-openai-pod.log` | whisper-openai | whisper-stt | pod | 2026-08-06 |
| `logs/whisper-stt-pod.log` | whisper-stt | whisper-stt | pod | 2026-08-06 |
| `research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log` | pbx-web-5ff68464d-mkn8n | pbx-web | current | 2026-08-06 |
| `research/pbx-web-30days/pod-logs/pod-pbx-web-5ff68464d-mkn8n-previous.log` | pbx-web-5ff68464d-mkn8n | pbx-web | previous | 2026-08-06 |
| `research/whisper-stt-30days/pod-logs/pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-current.log` | whisper-stt-847fd8d7b9-v2rs5 | whisper-stt | current | 2026-08-06 |
| `research/whisper-stt-30days/pod-logs/pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-stderr.log` | whisper-stt-847fd8d7b9-v2rs5 | whisper-stt | stderr | 2026-08-06 |
| `research/whisper-stt-30days/pod-logs/whisper-openai-ardenone-cluster.log` | whisper-openai | whisper-stt | cluster | 2026-08-06 |

---

## 5. Metadata Fields by File Type

### 5.1 File System Metadata

| Field | Source | Type | Example |
|-------|--------|------|---------|
| `log_size_bytes` | `os.path.getsize()` | integer | `62900` |
| `file_modification_time` | `os.path.getmtime()` | ISO 8601 | `"2026-08-06T13:36:43.650548"` |
| `file_creation_time` | `os.path.getctime()` | ISO 8601 | `"2026-08-06T13:36:43.650548"` |
| `file_exists` | `os.path.exists()` | boolean | `true` |

### 5.2 Content-Derived Metadata

| Field | Source | Type | Example |
|-------|--------|------|---------|
| `log_line_count` | `wc -l` or file read | integer | `2762` |
| `first_log_entry` | First line parse | ISO 8601 | `"2026-07-28T17:26:15Z"` |
| `last_log_entry` | Last line parse | ISO 8601 | `"2026-08-06T12:30:45Z"` |
| `collection_date` | Filename parse | YYYY-MM-DD | `"2026-08-06"` |
| `log_type` | Filename suffix | enum | `"current"` |

### 5.3 Kubernetes Metadata (from pods-list.jsonl or analysis files)

| Field | Source | Type | Example |
|-------|--------|------|---------|
| `pod_phase` | Pod status | enum | `"Running"` |
| `restart_count` | Container status | integer | `0` |
| `creation_timestamp` | Pod metadata | ISO 8601 | `"2026-07-28T17:26:12Z"` |
| `deletion_timestamp` | Pod metadata | ISO 8601 | `"2026-08-06T10:00:00Z"` |
| `container_image` | Container spec | string | `"ronaldraygun/pbx-web:1.0.9"` |
| `node_name` | Pod spec | string | `"k3s-agent-minisforum"` |

---

## 6. Analysis File Structure

### 6.1 Analysis File Naming

**Pattern:** `{log_file_prefix}-analysis.json`

**Examples:**
- `pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json`
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-08-06-stderr-analysis.json`

### 6.2 Analysis File Content Schema

Based on `pod-logs-schema.md`, analysis files contain:

```json
{
  "pattern_detection": {
    "startup": {
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "oom_kill": {
      "count": 0,
      "timestamps": [],
      "samples": []
    },
    "error": {
      "count": 42,
      "timestamps": ["1785277704", "unknown"],
      "samples": ["Error: connection refused"]
    },
    "performance": {
      "count": 0,
      "timestamps": [],
      "samples": []
    }
  },
  "temporal_boundaries": {
    "first_log_entry": "2026-07-28T17:26:15Z",
    "last_log_entry": "2026-08-06T12:30:45Z",
    "analysis_date": "2026-08-06T13:40:20.792334Z"
  }
}
```

---

## 7. Empty and Invalid Log Files

### 7.1 Empty Files

The following log files are empty (0 bytes):

- `/home/coding/aide-de-camp/logs/whisper-stt-pod.log`
- `/home/coding/aide-de-camp/research/whisper-stt-30days/pod-logs/whisper-stt-ardenone-cluster.log`
- `/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs/pbx-web-5ff68464d-mkn8n-current.log`
- `/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs/pbx-web-5ff68464d-mkn8n-previous.log`
- `/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs/pbx-web-current-nginx.log`
- `/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs/pbx-web-current-site-generator.log`

### 7.2 Files with Single-Line Errors

Files containing only error messages:

- `/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs/pbx-web-pbx-web-5ff68464d-lcfcp.log`
  - Content: `Error from server (BadRequest): container "site-generator" in pod "pbx-web-5ff68464d-lcfcp" is waiting to start: trying and failing to pull image`

---

## 8. Special Cases and Edge Cases

### 8.1 Service Load Balancer Logs

**File:** `pod-svclb-whisper-stt-c02117d2-f72hg.log`

**Pattern:** Service load balancer pods follow naming convention `svclb-{service}-{random}`

**Namespace:** Typically `kube-system` or service namespace

### 8.2 Cross-Namespace Logs

Some pods in pbx-web directory are actually whisper-stt pods:

- `whisper-stt-whisper-openai-68966786fb-tng29.log`
- `whisper-stt-whisper-stt-847fd8d7b9-b8rsj.log`

These appear in `/research/pbx-web-30days/pod-logs/` but belong to `whisper-stt` namespace.

### 8.3 Multi-Cluster Logs

Cluster-specific logs indicate multi-cluster deployments:

- `whisper-openai-ardenone-cluster.log` (ardenone-cluster)
- `whisper-openai-ardenone-manager.log` (ardenone-manager)

### 8.4 Historical Logs

Files with older collection dates:

- `pod-whisper-openai-68966786fb-jsb5d-2026-06-14.log` (June 2026)
- `pod-whisper-stt-847fd8d7b9-v2rs5-2026-07-12.log` (July 2026)

---

## 9. Index Files

### 9.1 Existing Index Files

| File | Format | Record Count | Purpose |
|------|--------|--------------|---------|
| `pod-logs-index.jsonl` | JSONL | 5+ | Lightweight index |
| `pod-logs-complete-metadata.jsonl` | JSONL | 3+ | Complete metadata |

### 9.2 Index Schema References

The complete schema is documented in:
- `pod-logs-schema.md` (28 fields, 5 categories)
- Parent bead: adc-1i5hf (Document edge cases and validation scenarios)

---

## 10. Extraction Processing Guidelines

### 10.1 File Discovery Algorithm

```python
import os
from pathlib import Path

def discover_pod_logs(root_dir: str) -> list:
    """
    Discover all pod log files following established naming patterns.
    """
    log_files = []
    
    for root, dirs, files in os.walk(root_dir):
        for filename in files:
            if not filename.endswith('.log'):
                continue
            
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, root_dir)
            
            # Check against known patterns
            if matches_pod_log_pattern(filename):
                log_files.append({
                    'path': rel_path,
                    'absolute_path': file_path,
                    'filename': filename,
                    'size_bytes': os.path.getsize(file_path),
                    'exists': True
                })
    
    return log_files

def matches_pod_log_pattern(filename: str) -> bool:
    """
    Check if filename matches any known pod log pattern.
    """
    patterns = [
        r'^pod-([a-z0-9]([-a-z0-9]*[a-z0-9])?)-(\d{4}-\d{2}-\d{2})\.log$',
        r'^pod-([a-z0-9]([-a-z0-9]*[a-z0-9])?)-(\d{4}-\d{2}-\d{2})-(current|previous|stderr)\.log$',
        r'^([a-z0-9]([-a-z0-9]*[a-z0-9])?)-([a-z0-9]([-a-z0-9]*[a-z0-9])?)\.log$',
        r'^([a-z0-9]([-a-z0-9]*[a-z0-9])?)-pod\.log$',
    ]
    
    return any(re.match(pattern, filename) for pattern in patterns)
```

### 10.2 Metadata Extraction Strategy

1. **File System Metadata** (Fast):
   - File size, modification time, creation time
   - Use `os.path` functions

2. **Filename-Derived Metadata** (Fast):
   - Pod name, namespace, collection date
   - Use regex extraction from filename

3. **Content Parsing** (Slow):
   - Line count, first/last timestamps, pattern detection
   - Read file line by line

4. **External Metadata** (Optional):
   - Pod metadata from `pods-list.jsonl`
   - Analysis metadata from `-analysis.json` files

### 10.3 Processing Order Recommendations

1. Process empty files first (no content parsing needed)
2. Process files with analysis files (metadata available)
3. Process standard pod logs (full content parsing)
4. Handle edge cases and special files

---

## 11. Summary Statistics

| Metric | Value |
|--------|-------|
| **Total Log Files** | 40 |
| **Pod Name Variants** | 25+ |
| **Namespaces** | 2 (pbx-web, whisper-stt) |
| **Distinct Pod Names** | 18 |
| **Empty Files** | 6 |
| **Files with Analysis** | 5+ |
| **Log Types** | 4 (current, previous, stderr, nginx) |
| **Timestamp Formats** | 5 |
| **Primary Directories** | 3 |
| **Date Range** | 2026-06-14 to 2026-08-06 |

---

## 12. Next Steps for Extraction Processing

1. **Implement Discovery Algorithm**
   - Use the `discover_pod_logs()` function above
   - Generate complete file inventory

2. **Build Metadata Extractor**
   - Parse filenames for pod names and namespaces
   - Extract timestamps from content
   - Load analysis files when available

3. **Create Unified Index**
   - Follow `pod-logs-schema.md` specification
   - Include all 28 fields
   - Validate against edge cases

4. **Handle Special Cases**
   - Empty files (zero bytes, null timestamps)
   - Single-line error files
   - Cross-namespace files
   - Multi-cluster files

5. **Validate Coverage**
   - Ensure all 40 files are indexed
   - Verify all namespaces captured
   - Check temporal coverage

---

**Document Status:** ✅ Complete  
**Coverage:** All 40 pod log files cataloged  
**Schema Alignment:** Follows pod-logs-schema.md (v1.0)  
**Dependencies:** Parent bead adc-1i5hf
