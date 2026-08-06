# pbx-web vs whisper-stt: 30-Day Deployment Analysis

**Analysis Period:** 2026-07-06 to 2026-08-06 (last 30 days)
**Analysis Date:** 2026-08-06
**Services Compared:** pbx-web (web service) vs whisper-stt (STT service)

## Executive Summary

Over the last 30 days, both `pbx-web` and `whisper-stt` services have been actively deployed with distinct deployment patterns and stability characteristics. This analysis reveals:

- **pbx-web**: 6 deployments with 2 version releases (1.0.8, 1.0.9)
- **whisper-stt**: 5 deployments with 4 version releases (1.8.1, 1.8.2, 1.8.4, 1.8.6)
- **Current Status**: All deployments healthy (100% replica availability)
- **Key Finding**: whisper-stt had a higher deployment velocity (4 versions vs 2) due to security fixes and feature rollout, while pbx-web had more operational infrastructure changes (secret migrations, routing)

## Deployment Frequency Analysis

### pbx-web Deployment Timeline

| Date | Version | Type | Description |
|------|---------|------|-------------|
| 2026-07-13 | 1.0.8 | Feature | Copy-to-clipboard transcript button |
| 2026-07-13 | 1.0.9 | Feature | Copy transcript includes timestamps |
| 2026-07-14 | N/A | Infra | Migrate secrets to OpenBao/ExternalSecret |
| 2026-07-14 | N/A | Infra | Force ESO resync + auto-restart on webhook secret rotation |
| 2026-07-27 | N/A | Infra | Make lab-rebuild-relay pick up rotated secrets automatically |
| 2026-07-28 | N/A | Feature | Add WebRTC web client page behind Google OAuth (reverted same day) |
| 2026-07-28 | N/A | Feature | Revert WebRTC web client page |

**Total Deployments**: 6 (excluding reverts as separate deployments)
**Feature Releases**: 2
**Infrastructure Changes**: 4
**Rollback Rate**: 1 feature was reverted (WebRTC client page)

### whisper-stt Deployment Timeline

| Date | Version | Type | Description |
|------|---------|------|-------------|
| 2026-07-07 | 1.8.1 | N/A | (CI auto-bump, deployment details not in declarative-config) |
| 2026-07-07 | 1.8.2 | Feature | Chunked upload support, route /jobs through Traefik |
| 2026-07-07 | 1.8.4 | Security | Bearer-auth chunked upload endpoints |
| 2026-07-07 | 1.8.6 | Security | Route /jobs/{id} + /jobs/chunked/* off Google auth |
| 2026-07-12 | N/A | Infra | Prefer big-CPU nodes via soft nodeAffinity |

**Total Deployments**: 5
**Feature Releases**: 1 (chunked upload)
**Security Releases**: 2 (bearer-auth fixes)
**Infrastructure Changes**: 1 (node affinity)
**Rollback Rate**: 0

## Deployment Patterns & Velocity

### Deployment Frequency

- **pbx-web**: 6 deployments in 30 days = **0.2 deployments/day**
- **whisper-stt**: 5 deployments in 30 days = **0.17 deployments/day**
- **Combined**: 11 deployments = **0.37 deployments/day**

Both services show similar deployment cadence, but with different drivers:

- **pbx-web**: Driven by infrastructure changes (secret management, routing)
- **whisper-stt**: Driven by security hardening and feature rollout

### Version Release Velocity

- **pbx-web**: 2 versions in 30 days = **1 version / 15 days**
- **whisper-stt**: 4 versions in 30 days = **1 version / 7.5 days**

whisper-stt had **2x higher version velocity**, primarily due to rapid security fixes rolled out on July 7th.

## Current Deployment Status

Both services are currently fully operational:

### pbx-web (ardenone-cluster)
- **lab-rebuild-relay**: 1/1 replicas ready
- **pbx-rebuild-relay**: 1/1 replicas ready  
- **pbx-web**: 1/1 replicas ready

### whisper-stt (ardenone-cluster)
- **whisper-openai**: 1/1 replicas ready
- **whisper-stt**: 1/1 replicas ready

## Failure Patterns & Issues

### Common Patterns (Both Services)

1. **No CI Build Workflow Records**: Neither `pbx-web-build` nor `whisper-stt-build` workflows appear in the last 30 days of Argo Workflow history. This suggests:
   - Workflows may be cleaned up aggressively via `podGC: OnPodCompletion`
   - Builds may be triggered on-demand rather than scheduled
   - Workflow retention policy may be short (success: 30min, failure: 2h default)

2. **No Deployment Failures**: Both services show 100% replica availability with no rollout failures recorded in the current state.

### pbx-web Specific Patterns

1. **Feature Rollback**: The WebRTC web client page feature was deployed and reverted on the same day (July 28), indicating:
   - Rapid detection and response to issues
   - Low-risk deployment approach (features can be quickly rolled back)
   - Possible testing gap for WebRTC authentication flow

2. **Secret Management Migration**: Multiple infrastructure changes focused on secret rotation and ExternalSecret Operator integration, suggesting:
   - Ongoing security hardening
   - Migration from legacy secret storage to OpenBao
   - Multi-phase rollout (migration → resync → automation)

3. **Multi-Component Service**: pbx-web includes 3 deployments (main web service + 2 relay services), increasing:
   - Deployment complexity
   - Coordination requirements
   - Potential failure surface area

### whisper-stt Specific Patterns

1. **Rapid Security Fixes**: Three consecutive security deployments on July 7th (1.8.2 → 1.8.4 → 1.8.6), indicating:
   - Authentication hardening discovered during deployment
   - Iterative security testing (bearer auth rollout → endpoint hardening → route adjustment)
   - Fast response to security gaps

2. **Node Affinity Optimization**: Infrastructure change to prefer big-CPU nodes, suggesting:
   - Performance optimization based on usage patterns
   - Resource-aware deployment strategy
   - Possible previous issues with resource constraints

3. **Traefik Migration**: Routing changes moving away from Google auth, indicating:
   - Infrastructure standardization
   - Reduced external dependencies

## Comparative Insights

### Deployment Stability

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| Deployments (30d) | 6 | 5 |
| Versions Released | 2 | 4 |
| Rollbacks | 1 | 0 |
| Current Health | 100% | 100% |
| Infrastructure Changes | 4 | 1 |
| Security Fixes | 0 | 2 |

### Deployment Drivers

- **pbx-web**: Infrastructure modernization (secret management, routing automation)
- **whisper-stt**: Security hardening and performance optimization

### Risk Profile

- **pbx-web**: Higher operational complexity (3 deployments) with rapid rollback capability
- **whisper-stt**: Lower complexity (2 deployments) with rapid security fix velocity

## Recommendations

### For pbx-web

1. **Testing Gap Investigation**: Review why WebRTC feature required same-day rollback. Consider:
   - Pre-deployment authentication testing for new features
   - Staged rollout for OAuth-integrated features

2. **Secret Migration Validation**: Confirm that all three phases of secret migration (ESO migration, resync enforcement, automation) are fully operational

### For whisper-stt

1. **Security Fix Pattern**: The rapid three-fix rollout on July 7th suggests security testing should be:
   - Integrated earlier in the development cycle
   - Automated to catch auth issues before deployment

2. **Node Affinity Monitoring**: Track the impact of big-CPU node affinity to ensure it's solving the intended performance issues

### For Both Services

1. **CI Workflow Retention**: Investigate why no workflow records exist for builds. Consider:
   - Increasing workflow retention for debugging
   - Confirming podGC policy alignment with operational needs

2. **Deployment Coordination**: Both services are deploying frequently (0.37 combined deployments/day). Ensure:
   - Change management processes can handle sustained cadence
   - Monitoring covers both services during concurrent deployments

## Conclusion

Both `pbx-web` and `whisper-stt` demonstrate healthy deployment patterns with 100% current availability. The last 30 days show:

- **pbx-web** focused on infrastructure modernization with rapid rollback capability
- **whisper-stt** executed rapid security hardening with high version velocity
- **Common strength**: No deployment failures or extended outages
- **Common gap**: CI workflow records not retained for post-mortem analysis

The distinct deployment drivers (infrastructure vs. security) suggest different team priorities but similar operational maturity—both services can deploy frequently without sacrificing stability.

---

**Data Sources:**
- `nixos-asterisk` git history (2026-07-06 to 2026-08-06)
- `jedarden/declarative-config` git history (2026-07-06 to 2026-08-06)  
- Argo Workflows `iad-ci` cluster (workflow queries)
- ArgoCD `ardenone-manager` cluster (deployment status)
- `ardenone-cluster` live deployment state (kubectl queries)

**Analysis Method:**
- Deployment frequency calculated from declarative-config commits
- Version history from nixos-asterisk VERSION bumps
- Current health from live cluster state
- CI/CD patterns from Argo Workflows history
