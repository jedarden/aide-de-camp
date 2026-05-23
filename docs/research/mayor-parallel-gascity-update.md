# Gas Town / Gas City — Update May 18 2026

Comparison against the early-May 2026 research snapshot.

## Activity

| | Gas Town | Gas City |
|---|---|---|
| Stars (early May) | ~13,500 (recorded) | ~130 (recorded) |
| Stars (May 18) | 15,276 | **750** (~6x growth in ~2.5 weeks) |
| Last release | v1.1.0 — May 7 | v1.1.0 — May 6 |
| Status | High-activity, architecturally stable | High-growth, architecturally active |

Gas City's star count was almost certainly sampled just after v1.0.0 launch (April 21). The two projects now release in coordinated cadence.

---

## What Hasn't Changed

- Gas Town's seven-role taxonomy (Mayor, Polecats, Crew, Refinery, Witness, Deacon, Dogs) — unchanged
- Molecules / Formulas / Wisps / Protomolecules — unchanged
- GUPP nudging — still ships, minor bug fixes
- Beads as persistence substrate — unchanged
- **Mayor context-compounding weakness — still present, not addressed in Gas Town**

---

## Gas Town — Material Changes

### Persistent Polecat Pool (shipped)
Polecats now have a persistent pool with reuse eligibility visible in `gt list`. Reduces session churn. Polecat recovery after merged MR fixed. Auto-save uncommitted work safety net added.

### Witness-as-AT-Team-Lead (spec only, not shipped)
`docs/design/witness-at-team-lead.md` — a full design spec for replacing tmux session management with Claude Code Agent Teams. Witness acts as AT team lead; polecats become AT teammates. Key properties:
- Uses AT's file-locked task claiming to eliminate Dolt write contention (estimated 80-90% reduction)
- Bead dependencies map to AT task dependencies — when task A closes, task B becomes claimable by any idle teammate
- **This is Gas Town's answer to parallel multi-topic dispatch — but it hasn't shipped**

### Convoy completion + cross-rig notifications
v1.1.0 fires notifications on convoy completion without polling.

---

## Gas City — Material Changes

### Dispatch Fanout Primitive (shipped)
`internal/dispatch/fanout.go` — parallel fanout at the bead/molecule level:
- A fanout bead spawns N child fragments in parallel (`gc.fanout_mode = "parallel"`)
- Closes when all children resolve
- Idempotent spawning with resume-safe state (`spawning` → `spawned`)
- **No coordinator required — no Mayor context consumed**

This is the clearest answer to parallel multi-topic dispatch in either project.

### Pool Agents with Label-Based Claiming (shipped)
`[agent.pool]` with `min`/`max`/`check` + `sling_query`. Dispatch routes beads to a named pool via label; pool members race to claim via `bd ready --metadata-field gc.routed_to=<name>`. Multiple topic-specific beads can be slung simultaneously; multiple pool instances process in parallel. First-come-first-served, zero central coordinator.

### `mol-review-quorum` Formula (shipped, core pack)
Concrete parallel dispatch pattern: two read-only reviewer lanes run in parallel, synthesis step runs after both resolve. Template for the multi-topic invocation pattern.

### Orders with Trigger Conditions (shipped)
Event-triggered formula dispatch — an external event fires parallel work without any agent receiving the trigger. Controller handles routing. Zero coordinator overhead.

### `gc wait` Primitive (shipped May 18)
Durable blocking — an agent or workflow blocks until a signal arrives without polling. Paired with `gc wait list --json` for inspection.

### Kubernetes + ACP Runtime Providers (shipped)
Agents can now run as K8s pods (`internal/runtime/k8s`) or via ACP socket transport. Expands where agents can run beyond tmux/subprocess.

### Mayor Made Optional (architectural)
In Gas City, "Mayor" is a pack convention, not an SDK type. The controller owns all infrastructure behavior. A coordinator role is optional:
- Per-topic pool agents (no shared context)
- Fanout beads for parallel spawning
- Orders for event-triggered dispatch
- `gc wait` for gate semantics

If no Mayor is configured, work still routes.

---

## Key Finding for Parallel Multi-Topic Dispatch

Neither project has shipped a dedicated "multi-topic parallel ingestion" pattern from a stream-of-consciousness input. But Gas City's composition of:

1. **Fanout bead** → spawn N parallel workers from one input
2. **Pool agents** → workers claim without central coordinator
3. **Orders/triggers** → event-driven dispatch with zero coordinator overhead
4. **Mayor optional** → no required serialization point

...gives all the primitives needed. The controller handles routing; agents are stateless with respect to each other.

Gas Town's answer (Witness-as-AT-Team-Lead) is the right architectural direction but hasn't shipped.

**Verdict**: Gas City is now the more relevant reference for the stream-dispatch parallel invocation model. The fanout + pool pattern directly validates the multiple-invocations-per-utterance approach.
