# Dispatch Architecture: Scaling Beyond One Server

## The Constraint

A single Hetzner box handles maybe 20-30 active projects today. As the project graph grows — more repos, more clusters, richer context bundles — parallel agent calls will compete for CPU, memory, and API rate limits on one machine. The architecture needs to distribute agent execution across remote workers without changing the user experience.

---

## What Needs to Stay Central

Regardless of scale, the following must remain on the originating server:

- **Input receiver** — the voice/text endpoint (it's where the user is)
- **Intent router** — the LLM pass that segments and tags utterances; low compute, high latency sensitivity
- **Card renderer / SSE stream** — the frontend connection; results must funnel back here
- **Project registry** — the source of truth for project→worker routing

Everything else can move.

---

## What Can Be Distributed

- **Agent execution** — the actual LLM call + context fetch for each intent thread
- **Context fetching** — kubectl, git, beads calls that populate the agent's input
- **Background indexing** — optional shallow heartbeat that refreshes registry metadata

---

## Dispatch Models Considered

### Model 1: Direct HTTP (agent_endpoint per project)

Each project group has a long-running worker pod with an HTTP API. The router POSTs an intent to the worker; the worker executes the agent and streams back a card spec.

```
Router → POST /intent  →  Worker Pod (per project group)
                               │
                               ├─ fetches context (kubectl, git, beads)
                               ├─ runs LLM agent call
                               └─ streams card spec back via chunked response / SSE
```

**Pros:** Simple. No queue infrastructure. Works with the `agent_endpoint` field already in the registry design.  
**Cons:** Worker must be reachable by the router (needs stable internal DNS / Tailscale hostname). No retry or backpressure built in. Worker is either busy or free — no work queuing.

### Model 2: Queue-Based Dispatch (recommended)

A lightweight message queue sits between the router and workers. Router enqueues an intent message; any available worker for that project group dequeues and processes it; result goes back on a reply channel.

```
Router → enqueue(intent, reply_id)  →  Queue
                                          │
                          ┌───────────────┴──────────────────┐
                          ▼                                   ▼
                    Worker Pool A                      Worker Pool B
                  (options, kalshi)                (ardenone, devimprint)
                          │
                    dequeue intent
                    fetch context
                    run LLM call
                    enqueue result(reply_id)
                          │
Router ← dequeue(reply_id) ←───────────────────────────────────┘
  │
  ▼
SSE → frontend card
```

**Pros:** Natural backpressure. Workers scale horizontally (add pods = more throughput). Router doesn't need to know worker addresses. Work queues when all workers are busy instead of failing. Dead-letter queue for failed intents.  
**Cons:** Queue is a new dependency. Adds one round-trip of latency vs. direct HTTP.

### Model 3: Argo Workflows (heavy — not recommended for interactive use)

Treat each intent as an Argo Workflow submission. Already have `iad-ci` with Argo installed.

**Pros:** Already exists. Audit trail, retry policy, artifact storage built in.  
**Cons:** Pod scheduling latency (seconds to tens of seconds) is incompatible with interactive card streaming. Argo is right for CI/build jobs, not sub-second agent dispatch.

---

## Recommended: Queue-Based with Long-Running Workers

### Queue Technology

| Option | Latency | Ops burden | Notes |
|--------|---------|------------|-------|
| NATS JetStream | <1ms | Low — single binary, no deps | Already used in some ardenone workloads; Tailscale-routable |
| Redis Streams | ~1ms | Low — Redis already common | Simple consumer groups, good client support |
| HTTP long-poll | ~5ms | Zero — no infra | Workers poll the router; works through NAT/Tailscale without inbound exposure |
| RabbitMQ | ~2ms | Medium | Overkill |

**Best fit:** Redis Streams or NATS JetStream. Both are single-binary, Tailscale-routable, and have good Python/Go client libraries. Redis is more likely already present in the cluster.

HTTP long-poll is worth noting as the zero-infrastructure fallback: workers contact the router, not the other way around. Removes the need for stable worker DNS and works through any NAT.

### Worker Pod Design

Workers are long-running Deployments (not Jobs — consistent with existing infrastructure preference). Each worker:

1. Subscribes to a queue topic filtered by its project group(s)
2. Dequeues an intent message: `{intent_id, project_slug, intent_type, context_spec}`
3. Executes context fetches (kubectl/git/beads) against the systems it has access to
4. Runs a Claude API call with the fetched context
5. Publishes card spec to the reply channel: `{intent_id, card_spec}`
6. Loops back to step 2

Workers are stateless between intents. Context is fetched fresh each time.

### Worker Placement and Access

Workers need access to the systems they query. This is the key placement constraint:

| Project group | Systems accessed | Worker placement |
|---------------|-----------------|-----------------|
| options-pipeline | apexalgo-iad kubectl, iad-options kubectl | apexalgo-iad or this server |
| kalshi workloads | iad-kalshi kubectl, iad-ci workflows | iad-kalshi or this server |
| ardenone apps | ardenone-cluster kubectl, ArgoCD | ardenone-cluster or this server |
| lab projects | lab server git/beads | lab server (SSH dispatch) |

Workers on a cluster can use in-cluster ServiceAccount credentials for kubectl — no kubeconfig files needed. This is actually *better* security than routing everything through this server.

### Result Routing

The router needs to correlate results back to the originating SSE stream. Each intent gets a `session_id` (ties to the frontend connection) and an `intent_id` (ties to the specific thread). Workers include both in their reply. The router's SSE handler holds a map of `session_id → SSE channel` and pushes cards as results arrive.

---

## Scaling Path

```
Phase 0 (prototype): All agents run locally on this server. No queue. Direct function calls.

Phase 1 (multi-worker): Add Redis/NATS. Workers still on this server but dispatch is queued.
                        Validates the queue/reply protocol without cluster ops.

Phase 2 (remote workers): Deploy worker pods to one cluster (e.g., iad-options).
                           Workers use in-cluster SA for kubectl. Router stays here.

Phase 3 (worker pools by domain): Different worker pools per project group.
                                   Each pool has access only to its domain's systems.
                                   Principle of least privilege at the worker level.

Phase 4 (auto-scale): HPA on worker pools based on queue depth.
                       Idle workers scale to zero; cold-start latency budgeted.
```

The protocol between router and workers (intent message schema, card spec schema) is defined once in Phase 1 and stays stable across all phases. The infrastructure underneath it scales independently.

---

## Security Posture by Phase

| Phase | Access concentration | Risk |
|-------|---------------------|------|
| 0 | All on one server | Highest — single compromise = full access |
| 1 | Same, but queue-mediated | Same surface, better audit trail |
| 2 | Workers on cluster with scoped SA | Reduced — worker only accesses its cluster |
| 3 | Domain-isolated worker pools | Each pool has min necessary access |

The queue-based design enables the security improvement as a natural consequence of distributing workers — you don't need to retrofit it later.

---

## Open Questions

1. **Queue colocation**: Does the queue run on this server (simpler) or on a cluster (more resilient)? If this server goes down, is the interface down regardless? Probably yes — input receiver is here anyway.

2. **Worker cold start**: If workers scale to zero, first intent after idle period waits for pod scheduling. Acceptable? Minimum one replica to avoid this.

3. **Context fetch authorization**: Workers on a cluster use in-cluster SA for their local cluster. But what about cross-cluster queries (e.g., a kalshi worker that also needs to check ArgoCD on ardenone-manager)? Options: (a) route those sub-queries back through this server, (b) give the worker a read-only token for ArgoCD, (c) have the router do cross-cluster fetches and pass results in the context spec.

4. **Lab server**: Lab projects accessed via SSH. Either the lab server runs its own worker (polling the queue over Tailscale), or this server SSH-executes on demand. The former is cleaner.
