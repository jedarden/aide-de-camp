# Log Dataset Standardization and Combination (adc-49xxy)

## Task Completed
Standardized and combined Kubernetes and Argo workflow logs into a unified comparison dataset for failure pattern analysis.

## Transformation Process

### Input Data
- **K8s logs**: `/tmp/k8s-logs.json` (2 deployments: pbx-web, whisper-stt)
- **Argo logs**: `/tmp/argo-logs.json` (workflow templates and execution data)

### Output Files
- **JSON format**: `/tmp/combined-logs.json` (20KB, 49 records)
- **CSV format**: `/tmp/combined-logs.csv` (9.9KB, 50 rows including header)

## Data Standardization Applied

### 1. Timestamp Normalization
- Converted all timestamps to ISO 8601 UTC format (e.g., `2026-06-24T00:00:00Z`)
- Handled timezone offsets by standardizing to UTC
- 43 out of 49 records contain timestamps

### 2. Error Code Normalization
- Numeric exit codes converted to `EXIT_N` format
- Example: `137` → `EXIT_137`
- Applied to pod failure records

### 3. Service Identification
- Added `service` field to all 49 records
- Services: `pbx-web` (22 records), `whisper-stt` (27 records)

### 4. Source Type Classification
- `k8s_event`: Kubernetes events (2 records)
- `deployment`: Deployment revision records (38 records)
- `pod`: Pod status records (6 records)
- `argo_workflow_template`: Workflow template metadata (2 records)
- `argo_data_limitation`: Data retention limitations (1 record)

## Dataset Statistics

### By Service
- pbx-web: 22 records
- whisper-stt: 27 records

### By Source Type
- Deployments: 38 records
- Pods: 6 records
- K8s events: 2 records
- Argo workflow templates: 2 records
- Data limitation notes: 1 record

### Key Findings
- Both services show deployment activity (12 revisions for pbx-web, 11 for whisper-stt)
- whisper-stt has one failed pod (Evicted due to ephemeral-storage)
- Both services have deprecated MetalLB annotation warnings
- Argo workflow templates exist but have no execution history (retention policy limits data to 8 days)

## Files Created
- `/home/coding/aide-de-camp/notes/combine_logs_adc-49xxy.py` - Transformation script
- `/home/coding/aide-de-camp/notes/adc-49xxy.md` - This documentation

## Validation
✓ Combined dataset includes all log entries (49 records)
✓ Consistent timestamp format (ISO 8601)
✓ Error codes normalized (EXIT_N format)
✓ Service identifier added to each record
✓ Output saved to both JSON and CSV formats
✓ No duplicate entries
✓ Source type field included in all records

## Usage
The combined dataset is ready for failure pattern analysis, trend detection, and comparative analysis between pbx-web and whisper-stt services over the 30-day period (2026-06-24 to 2026-07-24).
