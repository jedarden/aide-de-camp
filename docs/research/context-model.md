# Context Model: Centralized Access vs. Centralized Storage

## The Concern

If the dispatch system needs to answer questions about 20+ projects, it seems like all project knowledge needs to live in one place. That's a large surface area — security risk, operational burden of keeping everything current, and a single point of failure.

## The Distinction That Matters

**Centralized storage** = all content, history, and state is copied to and indexed on one machine.

**Centralized access paths** = one machine knows *how to reach* each system, but content stays where it lives.

These feel similar but have very different operational profiles.

---

## What Already Exists on This Server

This machine already holds the access layer for everything:

| System | Access method | Already works |
|--------|--------------|---------------|
| Git repos | Cloned in `/home/coding/` | Yes |
| Kubernetes clusters | kubectl-proxy over Tailscale | Yes |
| ArgoCD | Read-only HTTPS proxy | Yes |
| Argo CI logs | kubectl on iad-ci kubeconfig | Yes |
| Beads | `.beads/` in each repo | Yes |
| Lab server | SSH over Tailscale | Yes |

The server is already the hub — it has to be, because the kubectl proxies and Tailscale routes are configured here. The question isn't *whether* to centralize, it's *how much pre-computation* to do vs. how much to fetch on demand.

---

## Three Possible Context Strategies

### A. Full Index (maximum surface area)

A background process crawls all repos, indexes file content + git history + beads into a local vector/full-text store. Agents query the index.

- **Latency**: very low (pre-computed)
- **Freshness**: depends on crawl cadence; can be stale
- **Surface area**: very high — all content on disk in an indexed form
- **Ops burden**: high — crawl jobs, index maintenance, storage

Verdict: overkill for the goal. This is what a code search product does.

### B. Shallow Registry + On-Demand Fetch (recommended)

Maintain a **project registry** with only:
- project slug, repo path, primary cluster/namespace
- workflow template membership (from the project graph)
- lightweight heartbeat metadata: last commit timestamp, open bead count, pod phase

When an intent is dispatched, the agent for that intent fetches *just what it needs* to answer the question: recent git log, current pod status, open beads. Nothing is pre-indexed. The registry is small enough to be a YAML file.

- **Latency**: moderate (a few kubectl/git calls per agent)
- **Freshness**: always live
- **Surface area**: minimal — only the registry lives here; content is fetched transiently
- **Ops burden**: low — registry is hand-maintained, no crawl jobs

Verdict: right fit. The agents already need to make live calls to be accurate; pre-indexing just adds staleness risk.

### C. Federated Agents (maximum distribution)

Agents don't run on this server — they run close to their project (lab server for lab projects, ardenone-cluster for cluster-ops). The router sends intents over an internal API; agents reply with card specs. Only the router + renderer live centrally.

- **Latency**: higher (network hop per agent)
- **Freshness**: always live
- **Surface area**: lowest — projects are never centralized at all
- **Ops burden**: highest — need agent endpoints deployed and maintained per project

Verdict: correct direction for a mature system, but premature for a prototype. The agent-per-project boundary is worth preserving in the design even if all agents run locally at first — it makes federation possible later without a rewrite.

---

## Recommended Model: Registry + Lazy Fetch

```
┌─────────────────────────────────────────────────────────────┐
│  Project Registry (YAML, ~200 lines)                        │
│  ─ project slugs + repo paths                               │
│  ─ workflow template membership                              │
│  ─ access method per system (kubectl server, cluster name)  │
│  ─ last-known metadata (updated by lightweight heartbeat)   │
└─────────────────────────────────────────────────────────────┘
         │  router reads at startup, refreshes on demand
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Intent Router                                              │
│  ─ matches utterance to project(s) / workflow template      │
│  ─ constructs per-agent context spec (what to fetch)        │
└─────────────────────────────────────────────────────────────┘
         │  dispatches N parallel agent calls
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Agent (one per intent thread)                              │
│  ─ receives: intent + context spec                          │
│  ─ fetches live: git log / kubectl / br / ArgoCD            │
│  ─ does NOT read full file trees unless the intent requires │
│  ─ returns: card spec JSON                                  │
└─────────────────────────────────────────────────────────────┘
```

### What the agent fetches per intent type

| Intent type | What gets fetched |
|-------------|------------------|
| `status` | pod phases, ArgoCD sync, last CI run, last commit |
| `deploy` (compound) | CI status + image tag + declarative-config pin + pod image |
| `bead-status` | `br list --project X --status open` |
| `lookup` | specific file read, grep, or git show |
| `brainstorm` | nothing fetched — pure LLM with project description |

### What never gets pre-indexed

- File contents (fetched on `lookup` intent only)
- Full git history (only last N commits fetched for `status`)
- Log streams (fetched only if explicitly asked)
- Secrets (never touched)

---

## The Real Surface Area

Under this model, the surface area added by stream-dispatch is:

- One YAML project registry (~200 lines)
- One backend process (router + agent spawner)
- One frontend page

The machine's *existing* attack surface (repos, kubeconfigs, kubectl access) doesn't grow — it was already there. Stream-dispatch just adds a programmatic query layer over it.

The new risk is: **a single prompt-injection via an agent's fetched content could cause the agent to act instead of report.** Mitigation: agents in this system are read-only by design. They can `git log`, `kubectl get`, `br list` — they cannot `git push`, `kubectl apply`, or `br close`. Enforce this at the agent system prompt level and by not providing write tools.

---

## Federated Path (future)

The registry entry for each project should include an optional `agent_endpoint` field. When present, the router sends the intent to that remote agent instead of spawning locally. This makes federation a registry config change, not an architectural change.

```yaml
projects:
  lab-project-x:
    repo: jedarden/lab-project-x
    agent_endpoint: http://lab-agent.tail1b1987.ts.net:8080  # runs on lab server
```

Projects without `agent_endpoint` continue to be handled by local agents.
