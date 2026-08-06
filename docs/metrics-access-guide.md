# Metrics Access Guide

## Authentication & Access Requirements

### Prerequisites

1. **VPN Connection Required**
   - Tailscale VPN must be active for all direct service access
   - Cloudflare Tunnel access available for Grafana (public)

2. **kubectl Access**
   - Read-only proxy: `kubectl --server=http://traefik-ardenone-cluster:8001`
   - Admin access: Requires direct kubeconfig (not typically needed)

3. **Port-forward Setup**
   - Required for Prometheus and Victorialogs direct access
   - Run in background for persistent connections

## Access Methods

### Method 1: Port-Forward (Recommended for Queries)

#### Victorialogs Access
```bash
# Setup port-forward
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/vlogs-server 9428:9428 --address=localhost &

# Test connectivity
curl -s http://localhost:9428/health

# Run query
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D&limit=10" | jq .
```

#### Prometheus Access
```bash
# Setup port-forward
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/kube-prometheus-stack-arde-prometheus 9090:9090 --address=localhost &

# Test connectivity
curl -s http://localhost:9090/-/healthy

# Run query
curl -s "http://localhost:9090/api/v1/query?query=up%7Bnamespace%3D%22pbx-web%22%7D" | jq .
```

### Method 2: VPN Direct Access

#### Victorialogs via VPN
```bash
# Access via Tailscale hostname
curl -k https://vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com:9428/health

# Run query via VPN
curl -k "https://vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D&limit=10" | jq .
```

### Method 3: Grafana (Public Access)

```bash
# Public access via Cloudflare Tunnel
# URL: https://grafana.ardenone.com
# Auth: Google SSO

# Access via API (requires authentication token)
GRAFANA_TOKEN="your-api-token"
curl -s "https://grafana.ardenone.com/api/datasources" \
  -H "Authorization: Bearer $GRAFANA_TOKEN"
```

## Testing Connectivity

### Health Check Endpoints

```bash
# Victorialogs health check
curl -s http://localhost:9428/health
# Expected: OK

# Prometheus health check  
curl -s http://localhost:9090/-/healthy
# Expected: "Prometheus Server is Healthy."

# Check port-forward status
netstat -tunlp | grep -E "9428|9090"
```

### Connection Validation

```bash
# Test Victorialogs query
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D&limit=1" | jq . | head -5
# Should return: Single log entry

# Test Prometheus query
curl -s "http://localhost:9090/api/v1/query?query=up" | jq .data.result | head -5  
# Should return: List of targets with status

# Verify 30-day log coverage
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D%5B30d%5D&limit=1" | jq ._time
# Should return: Timestamp from 30 days ago
```

## Query Access Patterns

### 1. Interactive Query Testing

```bash
# Quick error check (last hour)
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D%20%7C%3D%20%22error%22%5B1h%5D" | jq '.[] | {_time, _msg}'

# Current CPU usage
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(container_cpu_usage_seconds_total%7Bnamespace%3D%22pbx-web%22%7D%5B5m%5D))%20by%20(pod)" | jq .data.result
```

### 2. Historical Analysis (30-day)

```bash
# Error rate over 30 days
curl -s "http://localhost:9428/select/logsql/query?query=count_over_time(%7Bnamespace%3D%22pbx-web%22%7D%20%7C%3D%20%225xx%22%20%5B30d%5D)" | jq .

# Resource pressure events (30-day window)
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22whisper-stt%22%7D%20%7C%3D%20%22OOM%22%20%5B30d%5D" | jq .
```

### 3. Real-time Monitoring

```bash
# Stream live logs (via Victorialogs stream endpoint)
curl -s "http://localhost:9428/api/v1/stream" -d '{"query":"{namespace=\"pbx-web\"}"}'

# Current resource usage
curl -s "http://localhost:9090/api/v1/query?query=container_memory_usage_bytes%7Bnamespace%3D%22whisper-stt%22%7D" | jq .data.result
```

## Rate Limits & Performance

### Query Optimization
- **Victorialogs**: Add time ranges to limit data scanned: `[1h]`, `[24h]`, `[30d]`
- **Prometheus**: Use `rate()` functions for efficient time-series calculations
- **Both**: Filter by namespace and pod to reduce query scope

### Performance Considerations
- Victorialogs 30-day queries may take 5-10 seconds
- Prometheus queries should be limited to 10-day window
- Rate limiting: ~100 queries per second for Prometheus
- Concurrency: Multiple port-forwards supported

## Troubleshooting

### Common Issues

#### Port-forward fails to start
```bash
# Check if service exists
kubectl --server=http://traefik-ardenone-cluster:8001 get svc -n monitoring

# Check if service has correct port
kubectl --server=http://traefik-ardenone-cluster:8001 get svc -n monitoring vlogs-server -o yaml

# Try alternative method (pod port-forward)
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n monitoring -l app=vserver
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring <pod-name> 9428:9428
```

#### Query returns no data
```bash
# Verify service is running
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web

# Check service name/namespace
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -A | grep pbx

# Test with broader query
curl -s "http://localhost:9428/select/logsql/query?query=%7B%7D&limit=10" | jq .
```

#### Prometheus retention limit
```bash
# Check retention setting
kubectl --server=http://traefik-ardenone-cluster:8001 get prometheus kube-prometheus-stack-arde -n monitoring -o yaml | grep retention

# For data older than 10 days, use Victorialogs instead
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D%5B30d%5D" | jq .
```

### VPN Issues

```bash
# Check Tailscale status
tailscale status

# Test VPN DNS resolution
curl -k https://vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com:9428/health

# Fallback to port-forward if VPN unavailable
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring svc/vlogs-server 9428:9428
```

## Integration Examples

### Python Script Example
```python
import requests
from datetime import datetime, timedelta

# Victorialogs query for error rates
def get_error_rate_30d(namespace):
    query = f'count_over_time({{namespace="{namespace}"}} |= "error" [30d])'
    url = f"http://localhost:9428/select/logsql/query"
    params = {"query": query, "limit": "100"}
    response = requests.get(url, params=params)
    return response.json()

# Prometheus query for current CPU usage
def get_cpu_usage(namespace):
    query = f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}"}}[5m])) by (pod)'
    url = "http://localhost:9090/api/v1/query"
    params = {"query": query}
    response = requests.get(url, params=params)
    return response.json()
```

### Shell Script Example
```bash
#!/bin/bash
# Monitor pbx-web error rate and CPU usage

echo "=== PBX-WEB Status Check ==="
echo "Current CPU Usage:"
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(container_cpu_usage_seconds_total%7Bnamespace%3D%22pbx-web%22%7D%5B5m%5D))%20by%20(pod)" | jq -r '.data.result[].metric.pod + ": " + (.data.result[].value[1] | tostring)'

echo "Recent Errors (last hour):"
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D%20%7C%3D%20%22error%22%5B1h%5D" | jq -r '.[] | "\(.timestamp): \(.msg)"'
```

## Security Considerations

1. **VPN Required**: All direct service access requires Tailscale VPN
2. **Read-Only Access**: kubectl proxy provides read-only cluster access
3. **No External Access**: Prometheus and Victorialogs not exposed publicly
4. **Grafana Authentication**: Public Grafana requires Google SSO
5. **Port-Forward Security**: Local port-forward binds to localhost only
6. **Certificate Handling**: VPN endpoints use self-signed certs (use `-k` flag)

## Maintenance Notes

### Port-Forward Cleanup
```bash
# Kill background port-forwards
pkill -f "port-forward.*9428"
pkill -f "port-forward.*9090"

# Or find and kill specific process
lsof -ti:9428 | xargs kill -9
lsof -ti:9090 | xargs kill -9
```

### Service Status Monitoring
```bash
# Check all monitoring services
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n monitoring

# Check service endpoints
kubectl --server=http://traefik-ardenone-cluster:8001 get endpoints -n monitoring
```

## Access Summary

| Tool | Public Access | VPN Access | Port-Forward | Auth Required |
|------|----------------|--------------|---------------|----------------|
| Victorialogs | ❌ | ✅ | ✅ | VPN cert |
| Prometheus | ❌ | ✅ | ✅ | VPN cert |
| Grafana | ✅ (Cloudflare) | ✅ | ✅ | Google SSO |
| kubectl proxy | ✅ (read-only) | ✅ | N/A | None |

## Quick Reference

### Start Monitoring Session
```bash
# Terminal 1: Victorialogs
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring svc/vlogs-server 9428:9428 &

# Terminal 2: Prometheus  
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring svc/kube-prometheus-stack-arde-prometheus 9090:9090 &

# Test both
curl -s http://localhost:9428/health && echo "Victorialogs OK"
curl -s http://localhost:9090/-/healthy && echo "Prometheus OK"
```

### Common Query Pattern
```bash
# For 30-day historical data: Use Victorialogs
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D%5B30d%5D" | jq .

# For real-time metrics: Use Prometheus
curl -s "http://localhost:9090/api/v1/query?query=container_memory_usage_bytes%7Bnamespace%3D%22whisper-stt%22%7D" | jq .
```
