
# pbx-web 30-Day Deployment Summary

## Current Status (2026-08-06)
- **3 pods running**: pbx-web (main app), pbx-rebuild-relay, lab-rebuild-relay
- **0 restarts** across all pods
- **Health checks**: Passing (6625 in recent logs)
- **Images**: ronaldraygun/pbx-web:1.0.9, python:3-slim, nginx:alpine

## Deployment Activity
- **11 replica sets** in pbx-web namespace over last 95 days
- **Current deployment**: 23 days old (pbx-web-5ff68464d)
- **Recent deployment activity**: Multiple replica sets from 8-95 days ago

## Error Patterns
- **Recording fetch errors**: Connection reset by peer, broken pipe errors
- **HTTP 500 responses**: Generated during recording fetch failures
- **No HTTP 5xx errors**: Found in recent Victorialogs data
- **No pod restart events**: All pods stable with 0 restart count

## Data Limitations
- **Victorialogs coverage**: Only recent ~7 hours available (10k logs)
- **No cluster events**: No pod events found in cluster-wide query
- **kubectl logs**: Available for current pods only (8-22 days of history)

## Log Files Generated
- logs/pbx-web-30day.json - Structured deployment data
- logs/pbx-web-victorialogs-raw.jsonl - Recent centralized logs (10k entries)
- logs/pbx-web-pods-describe.txt - Full pod descriptions
- logs/pbx-web-*-logs.txt - Current pod logs
