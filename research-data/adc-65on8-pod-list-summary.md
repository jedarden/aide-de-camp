# Available Pods Summary

**Generated:** 2026-08-06  
**Source:** Previous pod discovery tasks

## Overview
This document presents the available pods discovered in the cluster, organized by service type and displayed with clear metadata for easy identification.

---

## PBX Web Service Pods

| Pod Name | Status | Ready | Age | Node |
|----------|--------|-------|-----|------|
| `pbx-web-5ff68464d-mkn8n` | ✅ Running | 2/2 | 8d | k3s-agent-minisforum |
| `pbx-rebuild-relay-588d79c5b9-vmmlz` | ✅ Running | 1/1 | 22d | k3s-agent-minisforum |
| `lab-rebuild-relay-79957dbd4-xsqhl` | ✅ Running | 1/1 | 9d | k3s-agent-minisforum |

**Total PBX Web Pods:** 3  
**Status:** All pods running normally

---

## Whisper STT Service Pods

| Pod Name | Status | Ready | Age | Node |
|----------|--------|-------|-----|------|
| `whisper-stt-847fd8d7b9-v2rs5` | ✅ Running | 1/1 | 24d | k3s-agent-minisforum |
| `whisper-openai-68966786fb-jsb5d` | ✅ Running | 1/1 | 53d | k3s-lenovo-tiny |

**Total Whisper STT Pods:** 2  
**Status:** All pods running normally

---

## Cluster Health Summary

| Metric | Value |
|--------|-------|
| **Total Pods** | 5 |
| **Running** | 5 (100%) |
| **Pending** | 0 |
| **Failed** | 0 |
| **Nodes in Use** | 2 (k3s-agent-minisforum, k3s-lenovo-tiny) |

---

## Pod Details

### PBX Web Application Pods
- **pbx-web-5ff68464d-mkn8n** - Main PBX web application deployment
  - Status: Running (2/2 containers ready)
  - Age: 8 days
  - Most recently deployed of the group

### PBX Relay Pods
- **pbx-rebuild-relay-588d79c5b9-vmmlz** - PBX rebuild relay service
  - Status: Running (1/1 containers ready)
  - Age: 22 days
  - Longest-running PBX-related pod

- **lab-rebuild-relay-79957dbd4-xsqhl** - Lab rebuild relay service
  - Status: Running (1/1 containers ready)
  - Age: 9 days

### Whisper STT Pods
- **whisper-stt-847fd8d7b9-v2rs5** - Whisper STT service deployment
  - Status: Running (1/1 containers ready)
  - Age: 24 days
  - Hosted on k3s-agent-minisforum

- **whisper-openai-68966786fb-jsb5d** - Whisper OpenAI integration
  - Status: Running (1/1 containers ready)
  - Age: 53 days
  - Longest-running pod overall
  - Hosted on k3s-lenovo-tiny

---

## Notes
- All pods are in `Running` status with no restarts recorded
- The cluster appears stable with evenly distributed workloads
- Whisper OpenAI pod has the longest uptime at 53 days
- Most pod activity appears to be on the k3s-agent-minisforum node