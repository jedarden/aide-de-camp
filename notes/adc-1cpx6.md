# Deployment Patterns Analysis: pbx-web vs whisper-stt

**Task:** adc-1cpx6
**Completion Date:** 2026-07-24
**Analysis Period:** Last 30 days (2026-06-24 to 2026-07-24)

## Overview

Comparative analysis of pbx-web and whisper-stt deployment patterns to identify shared failure modes, deployment behaviors, and infrastructure dependencies. Analysis combined CI/CD workflow data from iad-ci cluster with live deployment status from ardenone-manager.

## Key Findings

### Critical Discovery: No CI/CD Activity
- **Both services:** 0 deployments via iad-ci workflows in last 30 days
- **Deployment method:** ArgoCD GitOps (direct cluster sync, not CI/CD pipeline)
- **Implication:** Workflow templates exist but are unused; actual deployments happen via declarative-config sync

### Deployment Churn Analysis

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| Total ReplicaSets (84 days) | 16 | 47 |
| Deployments per day | 0.19 | 0.56 |
| Current failure duration | 11 days | 12 days |
| Failed update attempts | ~2 per week | ~3 per week |

**Insight:** whisper-stt has 3× the deployment churn, indicating more frequent failed update attempts.

### Common Failure Patterns

**Shared across both services:**
1. **Infrastructure dependency failure** - Missing external dependency prevents deployment
2. **Extended duration failures** - 11-12 days continuous without remediation
3. **Deployment churn** - Continuous ReplicaSet creation without success
4. **No automated remediation** - Self-perpetuating failure loop
5. **Monitoring gap** - No alerts triggered on critical failures

### Service-Specific Failure Modes

#### pbx-web: Authentication Chain Failure
- **Primary failure:** ImagePullBackOff
- **Root cause:** Missing `docker-hub-registry` secret
- **Cascade failures:**
  - CreateContainerConfigError on relay pods (missing secrets)
  - ExternalSecret UpdateFailed (openbao ClusterSecretStore not ready)
- **Error frequency:** 40,391+ failed pull attempts over 11 days (~1 every 15 seconds)
- **Remediation:** Create secret + fix openbao ClusterSecretStore

#### whisper-stt: Storage Provisioning Failure
- **Primary failure:** Pending (PVC unbound)
- **Root cause:** Storage class "longhorn" does not exist on cluster
- **Available alternatives:** local-path, nfs-synology
- **Cascade failures:**
  - FailedScheduling - pods cannot be scheduled
  - ProvisioningFailed - continuous retry on missing storage class
- **Error frequency:** 1,744+ failed scheduling attempts over 12 days (~1 every 10 minutes)
- **Remediation:** Update PVCs to use local-path or install Longhorn

### Temporal Correlations

- **pbx-web failure onset:** 2024-07-13 (11 days ago)
- **whisper-stt failure onset:** 2024-07-12 (12 days ago)
- **Correlation:** Both services entered failed state within 24 hours
- **Hypothesis:** Possible shared infrastructure event or configuration change

## Categorized Failure Types

### Infrastructure Validation Gap
- **Severity:** Critical - complete service outage
- **Description:** Deployment manifests applied without verifying dependencies exist
- **Affected:** pbx-web, whisper-stt
- **Remediation:** Add pre-flight validation to ArgoCD sync process

### Secret Management Failure
- **Severity:** Critical
- **Description:** Image pull secrets and application secrets not available
- **Affected:** pbx-web
- **Cascade impact:** Relay pods unable to start, ExternalSecrets failing

### Storage Provisioning Failure
- **Severity:** Critical
- **Description:** PVCs reference non-existent storage class
- **Affected:** whisper-stt
- **Cascade impact:** Pods cannot be scheduled, workload completely down

### Monitoring and Alerting Gap
- **Severity:** High - extended MTTR
- **Description:** 11-12 day outages with no automated alerting or remediation
- **Affected:** pbx-web, whisper-stt
- **Remediation:** Implement Prometheus alerts for deployment health

## Recommendations

### Immediate (Priority 1)
1. Create missing docker-hub-registry secret in pbx-web namespace
2. Fix or restore openbao ClusterSecretStore
3. Update whisper-stt PVCs to use local-path storage class
4. Restart failed pods after fixes applied

### Short-term (Priority 2)
1. Add ArgoCD ResourcePolicy to prevent auto-sync without validation
2. Implement pre-flight checks in declarative-config pipeline
3. Add alerts for ImagePullBackOff, PVC Pending, ExternalSecret failures

### Long-term (Priority 3)
1. Migrate to public container registry (eliminate pull secrets)
2. Standardize storage classes across all clusters
3. Implement OPA/Gatekeeper policies for dependency validation

## Analysis Output

Full structured analysis saved to: `/home/coding/scratch/deployment-patterns-analysis.json`

## Methodology

1. Loaded 30-day CI/CD workflow data from iad-ci cluster
2. Queried ardenone-manager for live deployment status
3. Analyzed ReplicaSet history for deployment churn patterns
4. Categorized failure modes from pod events and PVC status
5. Identified temporal correlations and shared infrastructure dependencies
6. Generated structured JSON output with metrics and recommendations

## Conclusion

Both pbx-web and whisper-stt exhibit **critical infrastructure dependency failures** persisting for 11-12 days. While specific failure modes differ (image authentication vs. storage provisioning), both stem from **missing or misconfigured external infrastructure dependencies** that are not validated at deployment time. The absence of automated monitoring and alerting allowed these outages to persist for nearly two weeks without detection.

---

**Analysis Tool:** Python script analyzing kubectl output and JSON workflow data
**Data Sources:** iad-ci workflows, ardenone-manager pods/replicasets/events/PVCs
**Output Format:** Structured JSON with quantitative metrics and categorized failure patterns
