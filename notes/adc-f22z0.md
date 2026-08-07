# Pod Logs File Mapping (adc-f22z0)

## Summary

Scanned the `logs/` directory and created a comprehensive file mapping for all pod log files.

## Results

**Total log files found:** 10
- **With analysis files:** 0
- **Without analysis files:** 10

## File Structure

### Namespace: pbx-web-30day
- `lab-rebuild-relay-current.log` → pod: `lab-rebuild-relay`
- `pbx-rebuild-relay-current.log` → pod: `pbx-rebuild-relay`
- `pbx-web-main-current.log` → pod: `pbx-web-main`
- `pbx-web-pagefind.log` → pod: `pbx-web-pagefind`
- `pbx-web-web-container.log` → pod: `pbx-web-web-container`

### Namespace: <root> (no namespace)
- `pbx-web-nginx.log` → pod: `pbx-web-nginx`
- `pbx-web-site-generator-recent.log` → pod: `pbx-web-site-generator`
- `pbx-web-site-generator.log` → pod: `pbx-web-site-generator`
- `whisper-openai-pod.log` → pod: `whisper-openai-pod`
- `whisper-stt-pod.log` → pod: `whisper-stt-pod`

## Output

The mapping is written to `/tmp/pod_logs_mapping.json` with the following structure:

```json
{
  "total_count": 10,
  "with_analysis": 0,
  "without_analysis": 10,
  "mappings": [
    {
      "log_file_path": "logs/pbx-web-30day/lab-rebuild-relay-current.log",
      "analysis_file_path": null,
      "pod_name": "lab-rebuild-relay",
      "namespace": "pbx-web-30day"
    },
    ...
  ]
}
```

## Script

Created `scan_pod_logs.py` to:
- Recursively scan `logs/` directory for `.log` files
- Check for corresponding `.analysis.json` files
- Extract pod names from filenames (stripping `-current`, `-recent` suffixes)
- Extract namespaces from directory structure
- Output mapping to temporary file

## Next Steps

The mapping file at `/tmp/pod_logs_mapping.json` is ready for the next step to consume.
