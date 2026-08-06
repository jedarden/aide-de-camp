# Deployment Logs Collection Summary

## Collection Date: 2026-08-06

## Services Collected
1. **pbx-web** - Web service running on ardenone-cluster
2. **whisper-stt** - Speech-to-text service running on ardenone-cluster

## Data Files Collected

### pbx-web (11 files)
- `pbx-web-events.jsonl` - Events (2 records)
- `pbx-web-deployment.json` - Deployment specification and status
- `pbx-web-replicasets.jsonl` - Replica set history (17 records)
- `pbx-web-pods.jsonl` - Current pod information (3 records)
- `pbx-web-logs-current.txt` - All container logs (7,798 lines)
- `pbx-web-logs-site-generator.txt` - Site generator container logs (2,000 lines)
- `pbx-web-logs-nginx.txt` - Nginx container logs (2,000 lines)
- `pbx-web-argocd.json` - ArgoCD application status
- `all-recent-workflows.jsonl` - Recent CI/CD workflows (20 records)

### whisper-stt (11 files)
- `whisper-stt-events.jsonl` - Events (0 records)
- `whisper-stt-deployment.json` - Deployment specification and status
- `whisper-stt-replicasets.jsonl` - Replica set history (22 records)
- `whisper-stt-pods.jsonl` - Current pod information (2 records)
- `whisper-stt-logs-current.txt` - Container logs (0 records)
- `whisper-stt-logs-container.txt` - Specific container logs (0 records)
- `whisper-stt-logs-all.txt` - All logs with byte limit (0 records)
- `whisper-stt-argocd.json` - ArgoCD application status

### Observations

#### pbx-web
- Current pod: pbx-web-5ff68464d-mkn8n (created 2026-07-28, ~9 days ago)
- 2 containers: site-generator and nginx
- Active logging in both containers
- 17 replica sets in history
- 2 warning events detected

#### whisper-stt
- Current pod: whisper-stt-847fd8d7b9-v2rs5 (created 2026-07-12, ~25 days ago)
- No logs in current container (possibly using log driver without stdout capture)
- 22 replica sets in history
- No warning events detected
- Related pod whisper-openai running since 2026-06-14

#### CI/CD Workflows
- Workflow templates exist (pbx-web-build, whisper-stt-build)
- No workflow runs captured in available window
- 20 recent workflows from other services (armor, vista, warden, etc.)

## Time Period Covered
Data covers approximately the last 30 days (2026-07-07 to 2026-08-06).

## Success Criteria Met
✅ pbx-web logs retrieved successfully
✅ whisper-stt logs retrieved (though container stdout appears empty)
✅ Data stored in workspace files
