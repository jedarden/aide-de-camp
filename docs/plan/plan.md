# aide-de-camp: Application Plan

## Overview

aide-de-camp is a universal personal interface that accepts stream-of-consciousness voice and text input, routes it to parallel agents across any domain, and renders results as a live canvas of HTML cards or as synthesized audio narration. It is built on top of existing personal infrastructure and improves itself through conversational feedback after initial bootstrap.

CLI invocation: `adc`

---

## Problem Statement

Managing multiple active projects requires constant context-switching between dedicated tabs, terminals, and chat sessions. The input channel (typing into a specific Claude Code tab) is also the routing layer, and that conflation adds cognitive overhead. The same problem extends beyond coding: research, lookups, personal context, reminders — anything that requires knowing which system to ask before you can ask it.

aide-de-camp eliminates that overhead by providing a single input surface that routes automatically, dispatches in parallel, and returns organized results without requiring the user to know where to ask.

---

## Core Architecture

### The Hot Path

```
User utterance (voice or text)
  → STT transcription (Web Speech API or whisper-stt)
  → Intent Router (one LLM call, haiku-class, ~500ms est.)
      output: [{project_slug, intent_type, urgency, utterance_fragment,
                lookup_kind (lookup intents only)}, ...]
  → N parallel Fetch+Synthesize workers (one per intent thread)
      Fetch: deterministic code, executes command matrix based on intent_type
             (lookup intents: intent_type + lookup_kind)
      Synthesize: one LLM call per thread (sonnet-class, ~1-2s est.)
      output: {data, summary} — urgency carries through unchanged from the
              intent thread (see Urgency ownership)
  → Server-side card render (no LLM): deterministic component lookup via
      component_usage_patterns, template filled into card_cache;
      no match → result flagged for the built-in fallback card
  → Cards streamed via SSE to active canvas — client injects the rendered
      HTML, or renders fallback-flagged results with its built-in generic card
```

Target: < 3 seconds from utterance to first partial result on canvas. No Claude Code session startup on this path.

> The ~500ms and ~1-2s figures above — and every per-stage number in this plan — are design **estimates**. Nothing on the hot path has been measured yet. See Latency Budget & Instrumentation.

### Latency Budget & Instrumentation

The <3s promise is the product's central claim, so it gets a budget, instrumentation, and a gate — not just a diagram annotation. Per-stage targets below are estimates chosen so the end-to-end budget is plausible; the Measured columns show actual captured timings from 206 production-like runs across three test shapes (see bead adc-2xf52 for detailed analysis).

| Stage | Target (ESTIMATE) | Measured p50 | Measured p95 |
|-------|-------------------|--------------|--------------|
| STT final transcript (Web Speech API) | ~300ms | *Not measured* (client-side) | *Not measured* (client-side) |
| Intent Router (haiku-class via ZAI proxy) | ~500ms | **2,808ms** ❌ (Jul 24) | **5,558ms** ❌ (Jul 24) |
| Fetch — first source returns (surfaces as a per-source progress state on the pending card) | ~500ms | **0-16ms** ✅ | **0-21ms** ✅ |
| Fetch — window closes (all sources resolved or timed out; gates synthesize start — see Fetch Strand) | ~1s | **0-51ms** ✅ | **0-191ms** ✅ |
| Synthesize — first token (sonnet-class via ZAI proxy; starts at fetch-window close) | ~1s (cap set by the e2e gate — see internal-consistency note) | *Not measured* (instrumentation gap) | *Not measured* (instrumentation gap) |
| Synthesize — total (first token through completion) | ~1-2s | **3,108-3,984ms** ❌ | **4,663-7,877ms** ❌ |
| SSE emit → first card render | ~100ms | *Not measured* | *Not measured* |
| Escalate — bead formulation + safety validation + `bf create` (haiku-class via ZAI proxy; off the first-card path, see note below) | ~2s | **3,992ms** ❌ | **5,445ms** ❌ |
| **End-to-end: utterance end → first partial card** | **< 3s** | **5,219-5,571ms** ❌ | **8,853-10,404ms** ❌ |

**Internal consistency — the e2e row is the binding gate.** The hot-path stages are strictly sequential (STT → router → fetch-window close → synthesize first token → SSE emit), so their targets must sum inside the end-to-end budget: 300 + 500 + 1000 + 1000 + 100 ms ≈ 2.9s against the 3s gate, leaving ~100ms of unallocated slack. (The fetch first-source and escalate rows sit off this critical path — the former lands inside the fetch window, the latter is off the first-card path per the note below.) Synthesize-first-token was originally sketched at ~1–2s — the Hot Path diagram's ~1–2s figure survives as the estimate for the *full* synthesize call, first token through completion — but at a 2s first token the stages sum to ~3.9s: every stage could pass its own budget individually while the end-to-end gate fails, a contradiction that would otherwise surface only at rehearsal. Hence the ~1s first-token allocation above. All per-stage targets remain ESTIMATES and are **provisional allocations, not independent pass/fail gates**: once the Measured p50/p95 columns fill, re-derive the stage allocations from measured slack (a stage running under budget donates headroom to one running over) with the e2e row held fixed and overriding — the Gate below then applies against the re-derived allocations. A run where every stage meets its allocation but the e2e row misses is still a failed run.

**Task-profile first card.** The escalate stage does not gate the <3s promise: for a task-profile thread, the ack/pending card (a served built-in template, not a component-library render — see Component Library → Built-in cards) renders as soon as the router resolves the thread (router + SSE emit only) — before bead formulation and `bf create` complete — then updates in place with the bead ref when the escalate stage returns. The escalate row above budgets that in-place update, not the first card; the end-to-end row applies to the ack card.

**Instrumentation requirement.** The server records per-stage timings for every dispatch — `router_ms`, `fetch_first_source_ms`, `fetch_total_ms` (fetch-window close), `synthesize_first_token_ms`, `synthesize_total_ms`, `escalate_ms` (task-profile dispatches: formulation + validation + `bf create`), `sse_emit_ms`, plus client-reported STT and first-render timestamps when available — and persists them to the session store's `dispatch_timings` table (schema in Data Model). This is not optional telemetry: it is the only way the Measured columns get filled, and it doubles as the per-step timing log the Phase 5 rehearsal checklist requires.

**Gate.** ❌ **DEMO BLOCKED** — Latency budget compliance **FAILED**. The Measured p50/p95 columns have been filled from real runs, and the system does **NOT** meet acceptable performance targets for demo purposes.

**Gate Status (2026-07-24):** Budget compliance verification (adc-1jrkq) shows router latency at 2,651ms p50 (5.3× over 500ms budget) and 6,441ms p95 (4.3× over 1,500ms budget). End-to-end latency exceeds the 3s promise by 2-2.5×. Per the plan's explicit gate criteria, the demo cannot proceed until either: (1) router latency is reduced to meet budget targets, or (2) the on-screen promise is changed to reflect actual performance.

### The Async Path

```
Task-profile intent (research, coding, long-running work)
  → Generated-Bead Safety validation + approval (see Escalate Strand)
  → NEEDLE task bead created (bf create)
  → Existing Claude Code workers pick up bead normally
  → Bead watcher detects closure event
  → Result written to session store results table
  → SSE push to active canvas (or Telegram if no canvas)
```

> ⚠ The "or Telegram if no canvas" leg is NON-FUNCTIONAL today — Telegram delivery has never worked in any deployment (stubbed methods, unreachable bridge URL; see ADR-1). Until ADR-1 lands, a result arriving with no active canvas is persisted to the session store but reaches no surface.

The diagram above is the happy path only. Beads also get refused, fail repeatedly, or sit unclaimed — and NEEDLE has no built-in circuit breaker: it re-dispatches a failing bead forever. The async path therefore also specifies:

- **Re-dispatch circuit breaker.** NEEDLE exposes no dispatch-attempt API, so the breaker's signal is the bead's own comment stream: a worker that declines a bead appends a structured refusal comment — `bf comment <id> "REFUSED: <reason>"` — the same convention the live incident's workers followed when they committed refusal records to the bead. Each tick the watcher checks its open tracked beads (every unresolved `intents.bead_ref`) alongside the closed list, parses comments past a per-bead high-water mark, and persists the running refusal count in the watcher-owned `bead_watch` table (see Data Model) — on disk, so breaker state survives watcher restarts. After N refusals (default 3) or T hours without progress (default 24h — no closure and no new non-refusal comment), it fences the bead — `bf update` to `status=blocked`, so workers stop picking it up — sets the intent's status to `stuck`, and pushes a "task stuck — needs your input" card to the active surface with the most recent refusal reason attached.
- **Terminal failures.** A bead closed as failed/refused resolves its intent to `failed`; the reason surfaces as a card, never silently dropped. User cancellation still maps to `cancelled`.
- **Visible aging.** Pending cards show elapsed time; a card past its SLA is flagged on canvas before the breaker trips, so a stuck task is never invisible. The SLA is defined, not vibes: built-in per-intent-type defaults (task-profile: 6h; hot-path intents flag at 30s pending, since their budget is 3s) with a per-project `sla_hours` override in the registry entry. Flag ownership is split by path: for bead-backed (task-profile) intents the watcher computes `sla_deadline` at bead creation, stores it in `bead_watch`, and stamps `sla_flagged_at` when the flag fires. Hot-path intents have no bead and no watcher row — their 30s flag is owned by the **canvas client**: a pure client-side timer from the local pending placeholder's creation at submit time (the canvas creates the placeholder before any server response — see Escalate Strand, Pending/ack card render path) applies the aged-pending treatment with no server round-trip, deliberately, because a hung or wedged server is exactly the failure this flag must survive (see the matching Degraded-State UX row).

### The Self-Improvement Path

```
Feedback signal (explicit instruction or implicit engagement pattern)
  → Self-modification agent (Claude Code via NEEDLE task bead)
      reads target artifact (prompt file, registry YAML)
      generates update
      surfaces diff to user
  → User approves → artifact written → hot-reloaded on next invocation
```

Component templates are deliberately absent from the artifact list above: visual/component feedback follows the same feedback → diff → approval loop, but routes through the UI-regen agent, the sole writer of component *definitions* in the library — the `components`, `component_versions`, and `component_tags` tables in `data/components.db`. The hot-path server also writes to that DB on every dispatch, but only mechanical render/usage state (`card_cache` rows and the usage-stat columns), never definitions. One flow, two agents, disjoint write scopes — see Security Model.

---

## Components

### 1. Intent Router

**Runtime:** Direct API call (haiku-class via ZAI proxy)

One LLM call per utterance. Receives the full utterance text, the project registry, and a segmentation prompt. Returns a JSON array of intent threads, each tagged with:

```json
[
  {
    "project_slug": "pbx-web",
    "intent_type": "status",
    "urgency": "normal",
    "utterance_fragment": "has the pbx web caught up?"
  },
  {
    "project_slug": "whisper-stt",
    "intent_type": "status",
    "urgency": "normal",
    "utterance_fragment": "what's the state of whisper stt"
  },
  {
    "project_slug": "whisper-stt",
    "intent_type": "lookup",
    "lookup_kind": "logs",
    "urgency": "normal",
    "utterance_fragment": "and pull up its recent logs"
  }
]
```

`lookup_kind` appears only on `lookup` threads (see the intent-type list below); no other intent type carries it.

Intent types: `status`, `action`, `brainstorm`, `lookup`, `reminder`, `self-modification`, `monitoring-config`, `task-profile`, `clarification`

- **status**: Query current state (pods, pipelines, deployments, beads)
- **action**: Execute a command (deploy, restart, create) — executes only through the Action Execution Model (declarative-config Git operations + ArgoCD sync status, or reviewed escalation beads); never direct kubectl mutation
- **brainstorm**: Explore options, design, architecture discussion
- **lookup**: Find specific information. Every lookup thread carries a router-emitted `lookup_kind` — `logs` | `config` | `docs` (default `docs` when the utterance names nothing sharper) — because "recent logs" and "deployment config" for the same project are different fetches and different cards, not one. `lookup_kind` selects the fetch matrix (`prompts/fetch/lookup-{lookup_kind}.md`) and is embedded in the result's `result_type` (`lookup:{lookup_kind}:{project_slug}`, e.g. `lookup:logs:whisper-stt` vs `lookup:config:whisper-stt`), so log-lookup and config-lookup results select components independently. Persisted on the intent row (`intents.lookup_kind`)
- **reminder**: Set or query reminders — **NOT YET IMPLEMENTED**: no reminders table, scheduler, or module exists. The router does not dispatch this type; a reminder-shaped utterance is handled as `clarification` with a "reminders aren't available yet" card. Minimal design sketch in Future Work
- **self-modification**: Instructions to improve the interface itself
- **monitoring-config**: Configure ambient monitoring rules
- **task-profile**: Durable async work items that escalate to NEEDLE beads
- **clarification**: Low-confidence routing outcome requiring user input (meta-type, not dispatched)

The router reloads its segmentation prompt and the project registry per call through an mtime-checked cache: each file is stat'd on every call and re-read only when its mtime has changed — the same strategy every hot-reloaded artifact uses (see Hot-Reload Architecture). Hot-reload is automatic; an edit takes effect on the next call.

**Urgency ownership:** the router assigns the initial `urgency` on every intent thread as part of hot-path segmentation, guided by `prompts/urgency.md` (folded into the single router call — no extra LLM call on the hot path). The escalate strand refines urgency when formulating task-profile beads, and rule-driven ambient-monitoring results — which have no intent thread behind them — take their urgency from the firing rule in `config/monitoring.yaml` (see Bead Watcher). No other component assigns urgency; in particular, synthesize never does — it outputs `{data, summary}` and the thread's router-assigned urgency carries through to the result unchanged.

Ambiguous intents: if confidence is below threshold, router returns an `intent_type: "clarification"` thread. The voice model or canvas handles the clarification round-trip before dispatching.

### 2. Project Registry

**Format:** YAML file, read per-invocation by the router

Defines projects the router knows about:

```yaml
projects:
  pbx-web:
    aliases: ["pbx", "the pbx", "phone system"]
    description: "PBX web interface on ardenone-cluster"
    cluster: ardenone-cluster  # ArgoCD endpoint for this cluster resolves via config/clusters.yaml (see Fetch Strand — Cluster→ArgoCD Endpoint Resolution)
    namespace: pbx-web
    repo_path: /home/coding/declarative-config  # local checkout: git-log + per-project bead listing (pbx-web manifests live in k8s/ardenone-cluster/pbx-web/)
    argocd_app: pbx-web  # ArgoCD Application name for the fetch matrix's sync row; defaults to the project slug when omitted
    sla_hours: 6          # pending-card SLA override (see The Async Path — Visible aging)
    intent_support: [status, action, brainstorm, lookup, task-profile]
    # `action` appears in intent_support for routing completeness, but action
    # dispatch is DISABLED until the Action strand ships — see Action Execution
    # Model (Status: executor NOT BUILT)
    workflows:
      deploy:
        # DESIGN-ONLY — no executor interprets `steps` yet; the step vocabulary
        # is defined in Action Execution Model → "Future: Action strand".
        # Mutating steps follow the Action Execution Model: gitops-commit
        # edits jedarden/declarative-config; argocd-sync-status polls the
        # read-only ArgoCD API until the app reports Synced/Healthy
        steps: [ci-status, image-tag, gitops-commit, argocd-sync-status, pod-status]

  whisper-stt:
    aliases: ["whisper", "stt", "speech-to-text"]
    description: "Whisper STT service on ardenone-cluster"
    cluster: ardenone-cluster
    namespace: whisper-stt
    repo_path: /home/coding/declarative-config  # local checkout: git-log + per-project bead listing (whisper-stt manifests live in k8s/ardenone-cluster/whisper-stt/)
    argocd_app: whisper-stt  # explicit here for clarity; equals the slug default
    intent_support: [status, brainstorm, lookup, task-profile]
```

Updated by the self-modification agent. `src/environment/discovery.py` (the repo scanner) only *seeds* the registry — an initial or explicitly re-run scan that proposes entries; after seeding, the self-modification agent is the sole ongoing author, and the scanner never overwrites an entry the agent has written. Hot-reloaded on every router call.

### 3. Fetch Strand

**Runtime:** Deterministic code, no LLM

Executes a command matrix based on `intent_type` and the project's registry entry — for `lookup` intents, on `intent_type` **plus** the router-emitted `lookup_kind`, so a logs lookup and a config lookup against the same project run different matrices. No LLM decisions — the commands are determined by the intent type (and lookup kind) and project config.

The command matrix itself lives in `prompts/fetch/{intent_type}.md` — except `lookup`, which has one matrix per kind: `prompts/fetch/lookup-{lookup_kind}.md` (`lookup-logs.md`, `lookup-config.md`, `lookup-docs.md`). Despite the directory name, these files are **not LLM prompts** — they are declarative configuration: markdown tables with frontmatter that `src/fetch/commands.py` parses on each invocation (the hot-reload table's "context fetch strategy" row refers to this parse, not a model call). They are self-modifiable and git-versioned like every other artifact. The `prompts/` location is historical; a `config/fetch/` rename would be cosmetic cleanup, not a behavior change.

Example command matrix for `intent_type: status`:

| Source | Command |
|--------|---------|
| Pod status | `kubectl get pods -n {namespace}` |
| ArgoCD sync | `curl {argocd_api}/api/v1/applications/{argocd_app}` — `argocd_app` from the registry entry (defaults to the project slug when omitted); `{argocd_api}` resolved from the entry's `cluster` via `config/clusters.yaml` (see Cluster→ArgoCD Endpoint Resolution below) |
| Git log | `git -C {repo_path} log -10 --oneline` |
| Bead list | `bf list --status open` — run in the project's repo checkout when it has one, with **no** `--project` filter (a project's own workspace doesn't tag its beads with its aide-de-camp slug; filtering there returns zero rows). The `--project {slug}` filter applies only on the no-checkout fallback: `bf list --project {slug} --status open` in the aide-de-camp workspace (see Beads-Workspace Scoping) |
| CI status | `kubectl get workflows -n argo-workflows -l project={slug}` |

Results are structured data passed to the Synthesize strand. Fetch runs each source concurrently under per-source timeouts (declared alongside each command in the fetch config); the fetch window closes when every source has resolved or timed out, and only then does Synthesize fire — once, on the full set. Sources that finish early surface immediately as lightweight per-source progress states on the pending card ("3/5 sources in"), which is how fetch progress streams to canvas; sources that miss the window are never re-synthesized — they appear only as `fetch_coverage` caveats.

A `fetch_coverage` field tracks which sources succeeded and which failed. Failed sources are surfaced as caveats in the result.

#### Cluster→ArgoCD Endpoint Resolution

There is no single ArgoCD API. Applications on ardenone-cluster live on ardenone-manager's ArgoCD, which exposes a no-auth read-only proxy; apexalgo-iad and the other iad-* Spot clusters are managed by the ArgoCD instance on **rs-manager**, which today has **no equivalent no-auth read-only proxy** — only the authenticated, Tailscale-only API at `argocd-rs-manager.tail1b1987.ts.net:8080`. Querying the wrong instance returns not-found — indistinguishable from "app doesn't exist" — and puts a `fetch_coverage` caveat strip on the card. The fetch strand therefore resolves the ArgoCD endpoint from the registry entry's `cluster` through `config/clusters.yaml` (hot-reloaded via the same mtime-checked cache as every config artifact):

```yaml
# config/clusters.yaml — cluster → ArgoCD API mapping
clusters:
  ardenone-cluster:
    argocd_api: https://argocd-ro-ardenone-manager-ts.ardenone.com:8444  # ArgoCD on ardenone-manager
    access: read-only-proxy   # no auth; the proxy injects a read-only token
  apexalgo-iad:
    argocd_api: https://argocd-rs-manager.tail1b1987.ts.net:8080         # ArgoCD on rs-manager
    access: authenticated     # ⚠ no no-auth RO proxy exists for rs-manager today — see known-issues register
  # iad-options, iad-kalshi, and other iad-* Spot clusters also map to rs-manager's ArgoCD
```

A cluster absent from this file, or mapped with an `access` mode the fetch strand cannot satisfy (it holds no ArgoCD credentials, so it can only consume `read-only-proxy` endpoints), resolves the ArgoCD source as **failed** — an honest `fetch_coverage` caveat, never a silent wrong-instance query. **Demo consequence:** both scripted projects declare `cluster: apexalgo-iad`, so their ArgoCD state is readable only from rs-manager — a must-fix-before-demo row in the Phase 5 known-issues register: either provision an rs-manager read-only proxy mirroring the ardenone-manager pattern (and flip its `clusters.yaml` entry to `read-only-proxy`), or every scripted status card carries a caveat strip and criterion 3 fails the take.

### 4. Synthesize Strand

**Runtime:** Direct API call (sonnet-class via ZAI proxy)

Takes `{intent_spec, fetched_context}` → produces `{data, summary}`.

- `data`: structured JSON matching the component library's expected schema for this intent type
- `summary`: 1-3 sentence narration suitable for audio mode

Single-turn inference, invoked exactly once per thread when the fetch window closes (all sources resolved or timed out — see Fetch Strand); a source arriving after the window never triggers re-synthesis, it shows up only as a `fetch_coverage` caveat. The call streams its output tokens so the card fills progressively — output streaming, not incremental fetch input, is what puts a partial card on canvas early. Reads its system prompt from a file per invocation (hot-reload). The synthesize prompt is the highest-leverage artifact in the system — it defines result format, detail level, and what fields to include.

Runs once per intent thread in parallel across all active threads.

### 5. Escalate Strand

**Runtime:** Direct API call + `bf create`

For task-profile intents that need durable async handling:
1. One LLM call to formulate a bead body from the intent + context, refining the router-assigned urgency for the bead
2. The body passes Generated-Bead Safety validation (below); action-derived beads additionally wait for user approval
3. `bf create` in the aide-de-camp beads workspace, tagged `--project {slug}` (see Beads-Workspace Scoping below)
4. Returns a pending-card spec with the bead reference

**Pending/ack card render path.** The pending/ack card is **not** a component-library render: no `results` row exists until bead closure, so there is nothing for `results.result_type` selection to key on and no `result_id` for `card_cache`. Pending/ack cards — including per-source fetch-progress and elapsed-time states — are built-in frontend templates shipped in `src/canvas/`, exactly like the welcome and generic fallback cards (see Component Library → Built-in cards). The pending lifecycle starts client-side, not with a server event: at submit time the canvas creates a **local per-utterance pending placeholder** — before any server response has arrived, so even a hung server leaves a card on canvas to age — which splits into per-thread pending cards when the dispatch ack arrives. The client fills those from SSE events (dispatch ack, per-source progress, bead ref on `bf create` return) and replaces them with the component-rendered card when the real result lands; the 30s aged-pending timer runs from the local placeholder's creation, not from any SSE event (see the Degraded-State UX aged-pending row).

The bead watcher subsequently bridges bead closure to result delivery.

#### Beads-Workspace Scoping

"The appropriate project" is deliberately **not** another repo's `.beads/`. Every aide-de-camp-originated bead lives in the aide-de-camp repo's own beads workspace, carrying its target project as the `--project {slug}` field. One workspace for create, poll, and fence means the escalate strand and the bead watcher run every `bf` invocation from the aide-de-camp checkout directory and are guaranteed to see every bead they own; NEEDLE workers roam across workspaces and pick these up like any other.

The one exception is read-only: the fetch matrix's per-project bead listing reports on a project's *own* backlog, so it runs `bf list --status open` in that project's repo checkout when the registry entry has a `repo_path` with a `.beads/` workspace — deliberately with **no** `--project` filter: a project's own workspace doesn't tag its beads with its aide-de-camp slug, so `--project {slug}` there would return zero or near-zero rows and render a plausible-looking empty backlog on camera. The `--project {slug}` filter belongs only to the fallback: when there is no local workspace, fetch falls back to the aide-de-camp workspace filtered by `--project {slug}` — still real data, but only aide-de-camp-originated beads — and `fetch_coverage` records the narrower scope so the card carries a caveat ("no local beads workspace for {slug}; showing aide-de-camp-originated beads only").

#### Generated-Bead Safety

An LLM-authored bead body is an instruction that autonomous workers will execute. Unconstrained, this is the system's sharpest edge — live evidence: an escalate-authored bead containing an unscoped `kubectl delete pod` instruction put NEEDLE workers into a refusal loop (workers correctly refuse it; NEEDLE re-dispatches it forever). Every escalate-authored bead body therefore passes a deterministic validation gate before `bf create`:

- **Cluster-mutation verbs are denied.** Bead bodies must not instruct workers to run `kubectl apply/create/delete/scale/patch/edit/annotate/rollout` or any other live mutation of a managed resource. These violate the GitOps rule and workers refuse them.
- **Mutations must be phrased as declarative-config edits.** Any desired change to cluster state is written as "edit the manifest under `k8s/<cluster>/...` in `jedarden/declarative-config`, commit, push; ArgoCD syncs" — the only sanctioned mutation path (see Action Execution Model).
- **Scoping is required.** Bead bodies that reference cluster resources must name the cluster, namespace, and specific resource. Unscoped operational instructions ("delete the pod", "restart everything") are rejected.

Validation failure → the bead is not created; the escalate strand re-formulates once with the failure reason in context, and surfaces a clarification card if the second attempt also fails.

**User-approval gate:** no action-derived bead (anything instructing workers to change state — deploys, config edits, restarts, deletions) is created without explicit approval. The proposed bead body is rendered as a card on canvas (narrated in audio mode); approve → `bf create`, reject → discard. Purely informational task-profile beads (research, lookups) skip the approval gate but never the validation pass.

### 6. Voice Model

**Runtime:** OpenAI Realtime API (persistent session, via the DUCK-E session handler — see Technology Stack)

The conversational layer. Receives transcribed utterances (or audio directly), calls `dispatch_intent()` tool to trigger routing, and narrates results at appropriate moments.

Tool calls are triggers, not queries. `dispatch_intent()` returns an acknowledgment immediately; results arrive out-of-band and are surfaced by the voice model at natural conversational pauses.

The voice model's system prompt controls narration style, batching behavior, urgency handling, and multi-turn topic tracking. Read per session-turn from a file (hot-reload).

In audio mode there is no canvas. The voice model reads `result.summary` directly. When a user transitions from audio to canvas, pending results are rendered using the component library and appear on canvas — session continuity means the canvas catches up.

### 7. UI-Regen Agent

**Runtime:** Claude Code via NEEDLE (task bead)

Steward of the component library — asynchronous only. It is never on the hot path and never renders a card a user is waiting on.

**Hot-path selection and rendering happen in the server, not here.** On every dispatch the server picks the component deterministically — highest `match_score` in `component_usage_patterns` for the result's `result_type`, no LLM call (lookup result_types embed the router's `lookup_kind`, so `lookup:logs:whisper-stt` and `lookup:config:whisper-stt` are distinct keys selecting distinct components) — fills its template with the result data per layout bucket, writes the output to `card_cache`, and streams the rendered HTML over SSE; the client injects it. When nothing matches (a first-ever result shape, or no score above threshold), the server flags the result and the client renders it with the built-in generic fallback card (see Component Library) — a novel shape never blanks the canvas, it just renders plainly until the library catches up.

**Escaping contract (render path).** Template fill is the escaping boundary: every interpolated value — fetch output, `result.data` fields, `summary`, raw log lines — is HTML-escaped at template-fill time, and templates receive data as text only, never raw HTML from results, so a markup-looking log line renders as literal text instead of breaking layout or executing in the canvas. This binds LLM-generated component templates and the built-in generic fallback card's key/value grid alike (the fallback escapes client-side, where it renders). The same contract binds every client-filled built-in card: SSE-event values interpolated into built-in templates on the client — per-source progress states, bead refs, elapsed-time strings, error details, and above all worker/LLM-authored free text like the stuck card's refusal reasons lifted from bead comments — are inserted as text nodes (or escaped identically to the fallback card's values), never as HTML.

The UI-regen agent's job is making the library catch up. Given a result shape that fell to the fallback card or a weak match:
1. Finds the best-fit existing component (semantic match against component descriptions) and records the mapping in `component_usage_patterns` so the hot-path lookup hits it next time
2. If no good fit, generates a new component from scratch and stores it
3. On feedback, iterates the component (updates library, triggers canvas re-render)

Multi-step: reads library, generates or selects, writes back. Claude Code's file access and tool use make this the right runtime.

Created as a task bead; not on the hot path. Canvas updates in place when a component is versioned (SSE push: `component_updated: {component_id, version}`).

### 8. Self-Modification Agent

**Runtime:** Claude Code via NEEDLE (task bead)

Reads and writes the artifacts that encode system behavior:
- Router prompt (`prompts/router.md`)
- Project registry (`config/registry.yaml`)
- Strand prompts (`prompts/fetch/*.md` — one per intent type, per `lookup_kind` for lookup; `prompts/synthesize.md`; `prompts/escalate/task-profile.md`)
- Urgency classifier prompt (`prompts/urgency.md`)
- Voice model prompt (`prompts/voice.md`)
- Monitoring config (`config/monitoring.yaml`)
- Exception routing rules (`config/exceptions.yaml`)

Workflow for every modification:
1. Read current artifact
2. Understand intent of change
3. Generate updated artifact
4. Surface diff to user (in canvas or narrated in audio mode)
5. On approval: write artifact, hot-reload takes effect on next invocation
6. On rejection: discard

Safety model:
- Diffs before every application — no silent changes
- Versioning is git: every artifact write (`prompts/*.md`, `config/*.yaml`) is a git commit with a machine-generated message; rolling back any update is one instruction → `git revert` of that commit. Component library artifacts get the same guarantee through the `component_versions` table. No bespoke version store.
- Confidence threshold: unambiguous changes (adding an alias) can auto-apply with notification; structural changes always require explicit approval
- Out-of-band kill switch: self-modification can break the very interface used to undo it (a bad router prompt means no more routed instructions). Two escape hatches bypass the interface entirely: `ADC_SELFMOD_FREEZE=1` in the server environment, or `adc freeze` from the CLI (which falls back to touching a `data/FREEZE` sentinel file if the server is unresponsive). While frozen, every self-modification and auto-apply write is refused, and `adc restore-artifacts` git-reverts `prompts/` and `config/` to the last-known-good commit — no canvas, voice session, or router involvement required. **Break-glass caveat:** the sentinel-file fallback and the git revert are local filesystem/git operations against the server's artifact store — `adc` is a thin HTTP client (see adc CLI connectivity), so from a remote machine neither works exactly when the server is unresponsive. The break-glass procedure is: SSH into the server host first, then run `adc freeze` / `adc restore-artifacts` there.

### 9. Background Analysis Bead

**Runtime:** Claude Code via NEEDLE (task bead, low priority)

Runs on a schedule. Reads intent history and engagement signals from the session store, identifies patterns, proposes artifact updates.

Examples:
- "User consistently drills into status results for more detail → propose adding causality fields to synthesize prompt"
- "User ignores pipeline monitoring pushes for 5 days → propose lowering urgency tier"
- "After deploy status, user always asks about pod logs within 2 minutes → propose speculative pre-fetch"

Proposals are surfaced as cards on canvas for user review. Auto-apply only above a high confidence threshold — and an auto-apply is not a third artifact writer: the accepted proposal executes through the self-modification agent's write path, inheriting its write scope (`prompts/` and `config/` only), its git-commit-per-write rollback guarantee (one-instruction revert), and the out-of-band kill switch — all auto-apply is refused while the freeze is engaged.

### 10. Bead Watcher

**Runtime:** In-process daemon loop — an asyncio background task spawned by FastAPI lifespan startup, inside the same process as the server (see Deploy Stage A process model). No LLM

Watches for bead close events from NEEDLE workers. Detection is CLI-only: the watcher polls `bf list --status closed` on a fixed interval (default 30s) and keeps a high-water mark (newest close timestamp already processed) to pick out new closures. On the same tick it checks each open tracked bead — every unresolved `intents.bead_ref` — via `bf show`, parsing comments past a per-bead high-water mark for `REFUSED:` entries (the circuit-breaker signal; see The Async Path). All `bf` invocations run from the aide-de-camp repo's beads workspace (see Beads-Workspace Scoping under the Escalate Strand). It never reads `.beads/` files directly — the SQLite db is the CLI's private store, and `issues.jsonl` is only a flush checkpoint that misses unflushed mutations; both are documented corruption/staleness footguns in this workspace.

On close:
1. Resolves the closed bead to its intent via `intents.bead_ref` and reads `session_id` from the intent row — the bead itself carries no session metadata; the mapping lives entirely in the session store
2. Looks up active surface in session store
3. Writes result to `results` table and marks the intent `resolved` (or `failed`, per The Async Path's terminal-failure rule)
4. Fires SSE push to canvas or Telegram push if no canvas active

> ⚠ The Telegram push in step 4 is NON-FUNCTIONAL until ADR-1 lands — `src/telegram/fallback.py`'s delivery methods are stubs pointed at an unreachable bridge URL (see ADR-1). Today, a bead closing with no active canvas writes to `results` but notifies no one.

The same poll loop drives the async-path circuit breaker (see The Async Path): each tick it folds newly parsed refusal comments into `bead_watch` (refusal count, last reason, comment high-water mark), flags cards whose `sla_deadline` has passed, and fences stuck beads to `status=blocked`, flipping their intents to `stuck`. Breaker and SLA state live in `bead_watch` in the session store — never only in memory — so a watcher restart loses nothing.

**Ambient monitoring tick.** The watcher daemon is also the runtime for ambient monitoring — there is no separate monitoring process. On its own timer (`tick_interval_seconds` in `config/monitoring.yaml`, default 300; the config hot-reloads per tick per the Hot-Reload Architecture), the daemon evaluates each rule in `config/monitoring.yaml` against its watched topic: `src/monitoring/ambient.py` runs the relevant fetch-matrix sources through the fetch strand, diffs the output against `topic_context_cache`, and when a rule fires writes a `results` row directly — `topic_id` set, `intent_id` NULL (system-originated, no utterance behind it), `urgency` and exception type taken from the rule via `config/monitoring.yaml` and `config/exceptions.yaml`, `summary` filled from the rule's deterministic template (no LLM anywhere on the tick). From there the result enters Surface Routing Rules like any other: SSE push to the active surface, exception-class handling when urgency is critical.

Pure I/O. Not a separately started process: FastAPI's lifespan startup spawns the watcher loop in-process, so the single Stage A run command brings up hot path, watcher, ambient monitoring, and circuit breaker together — the server cannot be up with the watcher silently absent. Liveness is verified, not assumed: the watcher stamps `last_tick_at` after every poll tick, and `GET /health` exposes a `watcher` block (`alive`, `last_tick_at`, tick count) where `alive` is true only while the task is running **and** `last_tick_at` is within 2× the poll interval. A crashed watcher task is logged and restarted with backoff by the lifespan supervisor; the `/health` gap makes the crash observable. Under Deploy Stage B the same in-process model ships inside the aide-de-camp Deployment (never a K8s Job/CronJob, per infrastructure conventions).

---

## Degraded-State UX

"Failed sources are surfaced as caveats" is not a design. Every failure mode below maps to a **designed error card rendered from a fixed template** — these templates ship as built-in cards in the served frontend, the fourth built-in family (see Component Library → Built-in cards), filled client-side from SSE error events — so the canvas never shows a blank region, a spinner that never resolves, raw JSON, or a stack trace. These cards are what the Phase 5 known-issues register's degraded-state row points at.

| Failure mode | Canvas presentation | Recovery action |
|--------------|---------------------|-----------------|
| One fetch source fails or times out | Normal card built from the surviving sources; a caveat strip (from `fetch_coverage`) names what's missing — e.g. "ArgoCD unreachable — sync status omitted" | Per-source retry on the caveat; the next dispatch on the topic refetches everything |
| ALL fetch sources fail | "No data" error card: intent header + per-source failure list. Fixed template, no LLM call — synthesize is skipped, there is nothing to synthesize | Retry button re-runs fetch for the intent; utterance and intent are preserved |
| ZAI proxy down / timeout / quota-exhausted at the **router** stage | Dispatch-level error card: "Router unavailable — LLM proxy unreachable", with the raw utterance shown so nothing is lost | Retry re-dispatches the persisted utterance. ⚠ No fallback LLM endpoint exists — a proxy outage kills the entire hot path (router **and** synthesize); a direct-API fallback is tracked as Open Question 8 |
| ZAI proxy failure at the **synthesize** stage | Degraded "raw data" card: the structured fetch output renders under a "summary unavailable" banner — fetched data is never discarded | Retry-synthesize action reuses the fetched context (no refetch) |
| SSE connection drops | Unobtrusive "reconnecting…" indicator; existing cards stay visible, marked stale | Client auto-reconnects (EventSource backoff + `Last-Event-ID`); on reconnect the workload-summary replay delivers anything surfaced while disconnected |
| Hot-path card still pending at 30s (server hung, dispatch lost — no SSE event will ever arrive) | Aged-pending treatment applied by the **canvas client itself**: the card exists to age at all because the canvas creates a local per-utterance pending placeholder at submit time, before any server response (split into per-thread pending cards on the dispatch ack — see Escalate Strand, Pending/ack card render path); a client-side timer from the placeholder's creation, no server dependency, shows elapsed time plus "taking longer than expected" (see The Async Path — Visible aging) | Retry re-dispatches the card's utterance; the aged card is replaced by the retry's result |
| Router returns malformed JSON / schema-invalid output | After one automatic corrective retry, a clarification-style card: "Couldn't parse that into intents", showing the utterance with an edit-and-resend action. Raw model output goes to logs, never the canvas | User edits or resends; malformed output is logged as fodder for router-prompt iteration |

Quota exhaustion on the ZAI proxy presents identically to the proxy being down — same rows, same cards. The proxy is a single point of failure for the entire hot path; that is a deliberate Deploy Stage A trade-off (tracked as Open Question 8), and it stays visible here rather than hidden.

---

## Data Model

### Session Store (SQLite)

```sql
sessions (
  id          TEXT PRIMARY KEY,
  created_at  INTEGER,
  last_active INTEGER,
  primary_surface_id TEXT
)

surfaces (
  id              TEXT PRIMARY KEY,
  session_id      TEXT,
  type            TEXT,  -- 'canvas' | 'telegram' | 'audio'
  state           TEXT,  -- 'active' | 'idle' | 'disconnected'
  always_available INTEGER DEFAULT 0,  -- 1 for Telegram (⚠ aspirational: Telegram delivery non-functional; ADR-1 removes session-bound Telegram surfaces)
  last_seen       INTEGER
)

utterances (
  id          TEXT PRIMARY KEY,
  session_id  TEXT,
  raw_text    TEXT,
  created_at  INTEGER
)

intents (
  id           TEXT PRIMARY KEY,
  utterance_id TEXT,
  session_id   TEXT,
  topic_id     TEXT,  -- primary topic, authoritative and always set; see intent_topics
  project_slug TEXT,
  intent_type  TEXT,
  lookup_kind  TEXT,  -- lookup intents only: 'logs' | 'config' | 'docs' (router-emitted; see Intent Router). NULL otherwise
  status       TEXT,  -- 'pending' | 'dispatched' | 'resolved' | 'stuck' | 'failed' | 'cancelled'
  bead_ref     TEXT,  -- set for task-profile intents
  created_at   INTEGER,
  resolved_at  INTEGER
)

dispatch_timings (
  intent_id                 TEXT PRIMARY KEY,
  router_ms                 INTEGER,  -- shared across intents from the same utterance
  fetch_first_source_ms     INTEGER,
  fetch_total_ms            INTEGER,
  synthesize_first_token_ms INTEGER,
  synthesize_total_ms       INTEGER,
  escalate_ms               INTEGER,  -- task-profile dispatches only; null otherwise
  sse_emit_ms               INTEGER,
  stt_ms                    INTEGER,  -- client-reported; null when unavailable
  first_render_ms           INTEGER,  -- client-reported; null when unavailable
  created_at                INTEGER
)

results (
  id          TEXT PRIMARY KEY,
  intent_id   TEXT,  -- NULL for monitoring-originated results (see Bead Watcher)
  result_type TEXT,  -- deterministic card-selector key, set at result-write time:
                     -- "{intent_type}:{project_slug}" for intent-derived results — one per
                     -- intent thread (the aggregated thread card), never per fetch source;
                     -- lookup threads insert the intent's lookup_kind:
                     -- "lookup:{lookup_kind}:{project_slug}" (e.g. "lookup:logs:whisper-stt"
                     -- vs "lookup:config:whisper-stt" — distinct keys, distinct cards);
                     -- "monitoring:{project_slug}" for monitoring-originated rows.
                     -- The hot-path component lookup keys on this column, no LLM
                     -- (see UI-Regen Agent / component_usage_patterns)
  topic_id    TEXT,
  session_id  TEXT,
  summary     TEXT,
  data        TEXT,  -- JSON
  urgency     TEXT,  -- 'critical' | 'high' | 'normal' | 'low'
  created_at  INTEGER,
  surfaced_at INTEGER,
  acked_at    INTEGER,
  previous_result_id TEXT,  -- prior result of the SAME result_type on the same topic
                            -- (diff scope; NULL when none exists) — a status result
                            -- never diffs against a brainstorm result. Pure lineage,
                            -- set across sessions (project topics are cross-session):
                            -- the diff strip renders only when this points at a result
                            -- from the current session (see Cold start & demo seed —
                            -- Topic scope vs. session scope)
  diff_summary TEXT,  -- human-readable diff summary
  diff_data    TEXT   -- JSON: detailed field diffs
)

topics (
  id           TEXT PRIMARY KEY,
  label        TEXT,
  type         TEXT,  -- 'project' | 'research' | 'personal' | 'exception' | 'compound'
  project_slugs TEXT,  -- JSON array
  scope        TEXT,  -- 'session' | 'cross-session' | 'global'
  session_id   TEXT,  -- null for cross-session/global
  created_at   INTEGER,
  last_active  INTEGER,
  archived_at  INTEGER
)

topic_context_cache (
  topic_id     TEXT PRIMARY KEY,
  context_data TEXT,  -- JSON: pre-fetched context (kubectl, git, beads results)
  fetched_at  INTEGER,
  expires_at  INTEGER
)

feedback_signals (
  signal_id    TEXT PRIMARY KEY,
  signal_type  TEXT,
  session_id   TEXT,
  result_id    TEXT,
  topic_id     TEXT,
  timestamp    INTEGER,
  data         TEXT,  -- JSON: signal-specific data
  surface_type TEXT,
  processed    INTEGER,  -- 0 or 1
  processed_at INTEGER
)

-- Additional memberships for compound topics only: intents.topic_id is the
-- primary topic (always set, authoritative); this table never replaces it,
-- it only holds the extra topics a compound intent also belongs to.
intent_topics (
  intent_id TEXT,
  topic_id  TEXT,
  PRIMARY KEY (intent_id, topic_id)
)

-- Watcher-owned: circuit-breaker and SLA state per tracked bead.
-- Persisted here (not in watcher memory) so refusal counts and SLA
-- flags survive watcher restarts. See The Async Path and Bead Watcher.
bead_watch (
  bead_ref            TEXT PRIMARY KEY,
  intent_id           TEXT,
  refusal_count       INTEGER DEFAULT 0,
  last_refusal_reason TEXT,
  last_refusal_at     INTEGER,
  comment_high_water  TEXT,     -- newest comment id/timestamp already parsed
  sla_deadline        INTEGER,  -- set at bead creation: intent-type default or registry sla_hours
  sla_flagged_at      INTEGER,
  fenced_at           INTEGER,
  created_at          INTEGER
)
```

### Component Library (SQLite, separate DB)

```sql
components (
  id            TEXT PRIMARY KEY,
  name          TEXT,
  description   TEXT,
  html_template TEXT,
  version       INTEGER,
  created_at    INTEGER,
  last_used     INTEGER,
  usage_count   INTEGER
)

component_versions (
  component_id  TEXT,
  version       INTEGER,
  html_template TEXT,
  created_at    INTEGER,
  change_note   TEXT,
  PRIMARY KEY (component_id, version)
)

card_cache (
  result_id         TEXT,
  component_id      TEXT,
  component_version INTEGER,
  layout_bucket     TEXT,  -- 'compact' | 'normal' | 'expanded'
  rendered_html     TEXT,
  created_at        INTEGER,
  PRIMARY KEY (result_id, component_id, layout_bucket)
)

component_tags (
  component_id TEXT,
  tag TEXT,
  PRIMARY KEY (component_id, tag)
)

component_usage_patterns (
  component_id TEXT,
  result_type TEXT,  -- thread-level key matching results.result_type, e.g.
                     -- "status:pbx-web", "lookup:logs:whisper-stt",
                     -- "lookup:config:whisper-stt" (lookup keys carry lookup_kind,
                     -- so log-lookup and config-lookup components select
                     -- independently) — never per-source ("pod-status")
                     -- granularity; a thread's sources aggregate into one card
  match_score REAL,  -- 0-1
  sample_count INTEGER,
  last_matched INTEGER,
  PRIMARY KEY (component_id, result_type)
)
```

**Built-in generic fallback card.** The hot-path selector (see The Hot Path / UI-Regen Agent) is a deterministic lookup: highest `match_score` in `component_usage_patterns` for the result's `result_type`, no LLM. When no component matches — a first-ever result shape, or nothing above threshold — the card does not come from this DB at all: the served frontend ships a generic fallback card (key/value grid over `result.data` plus the `summary` line, all values HTML-escaped per the render-path escaping contract — see UI-Regen Agent) as part of `src/canvas/`, and the server flags the result so the client uses it. Novel shapes therefore always render something legible even with zero library rows; the UI-regen agent later promotes recurring fallback shapes into real components. `card_cache` rows are written only for real component renders.

**Built-in cards.** The fallback card is one of four card families that ship as fixed templates in the served frontend (`src/canvas/`) and never come from this DB: (1) the generic fallback card above, (2) the first-run welcome card (see Cold start & demo seed), (3) the pending/ack cards — the task-profile ack/pending card and the hot-path pending card with its per-source progress states — and (4) the error/clarification cards: the fixed-template cards Degraded-State UX defines (router-unavailable, all-sources-failed, degraded raw-data, malformed-router-output) plus the no-match clarification card (see Cold start & demo seed), filled client-side from SSE error events. Pending/ack cards cannot be library components even in principle: component selection keys on `results.result_type` and `card_cache` keys on `result_id`, and neither exists before the result does (task-profile results only appear at bead closure) — which is also why their lifecycle starts as a local per-utterance placeholder the canvas creates at submit time, before any server event (see Escalate Strand, Pending/ack card render path). The client fills these templates from SSE events (dispatch ack, per-source progress, bead ref, elapsed time, error details) and swaps in the component-rendered card when the result arrives. Consequence for Phase 5: built-in cards across all four families are exempt from — and never seeded for — the component-library requirements in the seeding runbook and rehearsal checklist.

---

## File System Layout

```
aide-de-camp/
├── adc                      ← CLI entry point (shell script or Python package)
├── README.md                ← operational/configuration reference (env vars, configuration table — the file ADR-1 cites)
├── README-PHASE4.md         ← Phase 4 verification evidence (cited by Implementation Phases)
├── config/
│   ├── registry.yaml        ← project registry (hot-reloaded by router)
│   ├── clusters.yaml        ← cluster → ArgoCD endpoint mapping (see Fetch Strand)
│   ├── monitoring.yaml      ← ambient monitoring rules
│   └── exceptions.yaml      ← exception routing rules
├── prompts/
│   ├── router.md            ← intent segmentation prompt
│   ├── synthesize.md        ← result generation prompt
│   ├── voice.md             ← voice model system prompt
│   ├── urgency.md           ← urgency classification prompt
│   ├── fetch/               ← per-intent-type fetch instructions
│   │   ├── status.md
│   │   ├── action.md
│   │   ├── lookup-logs.md   ← lookup matrices are per lookup_kind (see Intent Router)
│   │   ├── lookup-config.md
│   │   ├── lookup-docs.md
│   │   └── ...
│   └── escalate/            ← escalate/task-profile prompts
│       └── task-profile.md
├── src/
│   ├── main.py              ← FastAPI app entry point
│   ├── registry.py          ← project registry loader
│   ├── agents/              ← agent implementations
│   │   ├── self_modification.py  ← self-improvement agent
│   │   └── ui_regen.py          ← UI-regen agent
│   ├── components/          ← component library and hot-reload
│   │   ├── library.py           ← component library DB operations
│   │   └── hot_reload.py        ← hot-reload watcher
│   ├── context/             ← context warming and pre-fetch
│   │   ├── warmer.py            ← context warmer for active topics
│   │   └── prefetch.py          ← speculative pre-fetch
│   ├── conversation/        ← multi-turn conversation handling
│   ├── diff/                ← diff generation for results
│   ├── environment/         ← environment and repo discovery
│   │   └── discovery.py        ← repo scanner: seeds registry.yaml (one-time/on-demand scan); self-mod agent is sole ongoing author (see Project Registry)
│   ├── escalate/            ← escalate strand for task-profile intents
│   │   ├── handler.py           ← escalate request handler
│   │   ├── llm.py               ← LLM calls for bead formulation
│   │   └── commands.py          ├── bead creation commands
│   ├── feedback/            ← feedback processing and background analysis
│   │   ├── processor.py         ← explicit feedback processor
│   │   ├── signals.py           ← implicit feedback signal tracking
│   │   └── background_analysis.py ← background analysis bead
│   ├── fetch/               ← fetch strand (deterministic, per intent type)
│   │   ├── commands.py          ← fetch command matrix, intent types, data structures
│   │   └── orchestrator.py      ← FetchStrand: concurrent fetch execution, streaming, coverage tracking
│   ├── intent/              ← intent router (LLM classification)
│   │   └── router.py            ← intent segmentation and routing
│   ├── memory/              ← memory store and extraction (supporting store for cross-session context; not yet surfaced by any component — Future Work)
│   │   ├── store.py             ← memory persistence
│   │   └── extraction.py        ← memory extraction from results
│   ├── monitoring/          ← ambient monitoring
│   │   └── ambient.py           ← ambient monitoring rules
│   ├── realtime/            ← OpenAI Realtime API voice session
│   │   ├── session.py           ← voice session handler
│   │   ├── batching.py          ← result batching for narration
│   │   ├── continuity.py        ← audio-to-canvas session continuity
│   │   └── dispatch.py          ← tool-as-trigger dispatch
│   ├── session/             ← session store (SQLite)
│   │   └── store.py             ← session store operations
│   ├── sse/                 ← SSE broadcasting
│   │   ├── broadcaster.py       ← SSE connection registry
│   │   └── events.py            ← SSE event types
│   ├── stt/                 ← speech-to-text (whisper-stt browser fallback)
│   │   └── fallback.py          ← STT fallback client behind /api/v1/stt
│   ├── surface/             ← surface routing
│   │   └── router.py            ← result surface routing logic
│   ├── synthesize/          ← synthesize strand (LLM)
│   │   └── strand.py            ← result synthesis
│   ├── telegram/            ← Telegram fallback surface
│   │   └── fallback.py          ← Telegram delivery
│   ├── test/                ← test-harness endpoints (bypass Web Speech API for e2e tests)
│   ├── topic/               ← topic model
│   │   └── model.py             ← topic operations
│   ├── watcher/             ← bead watcher daemon
│   │   └── daemon.py            ← NEEDLE bead watcher
│   ├── canvas/              ← web frontend (SSE consumer, card renderer)
│   │   └── index.html           ← single-page canvas UI
│   └── cli/                 ← adc CLI
│       ├── main.py              ← CLI entry point
│       ├── commands.py          ← CLI commands
│       ├── config.py            ← CLI configuration
│       └── sse.py               ← SSE streaming for CLI
├── data/
│   ├── session.db           ← session store (SQLite)
│   └── components.db        ← component library (SQLite)
└── docs/
    ├── research/            ← architecture and design research
    ├── plan/
    │   └── plan.md          ← this file
    └── notes/
        ├── core-verification-evidence.md  ← phase verification evidence (cited by Implementation Phases)
        └── naming.md
```

---

## Deployment Model

aide-de-camp is a **live web application**, not a static site. The FastAPI server is the intelligence layer — it handles SSE connections, maintains session state, runs the router and synthesize strands, and serves the frontend HTML. There is no CDN path (no CF Pages).

*Naming note: deployment stages are **Deploy Stage A** (bare-metal) and **Deploy Stage B** (k8s) — deliberately not "Phase 0/1+", which collided with the Implementation Phases numbering (deployment "Phase 1+" had nothing to do with implementation Phase 1). References elsewhere to the "Phase 0 deployment" (e.g., ADR-1) mean Deploy Stage A. Stage A is the hosting model through the screen-capture demo and public launch; Stage B is post-launch hardening.*

### Why not static

- SSE connections are long-lived; CDNs cannot proxy them
- WebSocket for the Realtime API voice session requires a persistent backend
- The session store (SQLite) and artifact store (prompts, registry) require a writable filesystem
- Hot-reload depends on the running server reading updated files from disk on each invocation

### Current Deployment: Deploy Stage A (bare-metal — Hetzner server directly)

**Status: LIVE** ✅ — running server confirmed 2026-07-20 (ADR-1 audit)

The server runs as a process on the Hetzner server itself, not in k8s:
- NEEDLE workers and the aide-de-camp server share the same filesystem
- Self-modification agent writes directly to `prompts/` and `config/` — hot-reload works without any coordination
- Exposed via Tailscale (the server is already on the mesh); no ingress config needed
- SQLite DBs are local files; no PVC required

Running command: `uvicorn src.main:app --host 0.0.0.0 --port 8000`

**Stage A process model — exactly one process, by design.** The command above is the complete process inventory. The bead watcher (which also hosts ambient monitoring and the async-path circuit breaker — see Bead Watcher) is **not** a second command an operator must remember: FastAPI's lifespan startup spawns the watcher loop as an asyncio background task inside this same uvicorn process. A separately documented daemon is exactly the step that gets skipped, and its absence is silent — closures never surface, SLAs never fire, monitoring never ticks, while every test still passes (the "verified-in-tests, dead live" pattern). Startup-spawning makes that failure impossible; liveness is still checked, not assumed: `GET /health` reports `watcher.alive` / `watcher.last_tick_at` (see Bead Watcher), and the pre-demo seeding runbook verifies it in item (3).

No container, no CI, no ArgoCD. Managed as a long-running process (see CLAUDE.md for restart commands).

### Release flow (Deploy Stage A)

Version is in `pyproject.toml` only. No CI build — runs from source.

Release: `bump version in pyproject.toml` → `commit` → `git tag vX.Y.Z` → `push`.

### Future: Deploy Stage B (containerized, ardenone-cluster)

**Status: NOT BUILT** ❌

Session persistence and multi-surface routing are implementation Phase 1 deliverables and run on Stage A (currently PARTIAL — see Implementation Phases); they are not the trigger for this stage. The Stage B trigger is operational: uptime independent of the Hetzner box, container isolation, and standard CI/ArgoCD management. Not needed for the demo or launch. When that point arrives, containerize and move to k8s:

```
Docker image: ronaldraygun/aide-de-camp
Deployment: ardenone-cluster, namespace: aide-de-camp
PVC: /data/ (SATA, ReadWriteOnce)
  /data/session.db        ← session store
  /data/components.db     ← component library
  /data/prompts/          ← hot-reloadable prompt files
  /data/config/           ← registry.yaml, monitoring.yaml, exceptions.yaml
```

The artifact store (prompts, registry) moves from the repo's working directory to the PVC. The self-modification agent updates artifacts via the aide-de-camp API (`PATCH /artifacts/{name}`), which writes to the PVC path the server reads from. The PVC artifact directory is itself a git repository: the server commits every `PATCH /artifacts/{name}` write with the same machine-generated message convention, so the "versioning is git" safety model — one-instruction rollback, `adc restore-artifacts` — survives the move to Stage B unchanged.

### Future: Traefik configuration for SSE and WebSocket (Deploy Stage B)

**Status: NOT BUILT** ❌

Traefik's default response buffering breaks SSE. The IngressRoute needs:

```yaml
# IngressRoute annotations
traefik.ingress.kubernetes.io/router.middlewares: aide-de-camp-strip-prefix@kubernetescrd

# Middleware: disable buffering, extend timeouts
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: aide-de-camp-streaming
spec:
  buffering:
    maxResponseBodyBytes: 0   # disable buffering
  headers:
    customResponseHeaders:
      X-Accel-Buffering: "no"
```

ServersTransport timeout:

```yaml
apiVersion: traefik.io/v1alpha1
kind: ServersTransport
metadata:
  name: aide-de-camp-longlived
spec:
  forwardingTimeouts:
    responseHeaderTimeout: 0    # no timeout on SSE streams
    dialTimeout: 5s
```

DUCK-E's existing WebSocket IngressRoute config is the reference implementation for this cluster.

### SQLite concurrency

**Status: COMPLETE** ✅

Multiple writers (bead watcher, background analysis bead, session handler) require WAL mode to avoid lock contention:

```python
# On DB open
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```

WAL mode allows concurrent reads during writes and serializes multiple writers without blocking. For a personal single-user app, this is sufficient.

### adc CLI connectivity

The `adc` CLI is a thin HTTP client. It talks to the running server over Tailscale:

```bash
# ~/.config/adc/config
server_url = "http://localhost:8000"   # Deploy Stage A (local)
# Future: "http://aide-de-camp.ardenone.com" (Deploy Stage B)
```

No local inference. The CLI sends requests to the FastAPI backend and streams the SSE response to the terminal.

One exception: the kill-switch fallbacks (`adc freeze`'s `data/FREEZE` sentinel, `adc restore-artifacts`' git revert) act on the server's local filesystem, not over HTTP — they only work when `adc` runs on the server host itself. SSH in first; see the Self-Modification Agent safety model's break-glass procedure.

### Future: CI/CD (Deploy Stage B)

**Status: NOT BUILT** ❌

New Argo WorkflowTemplate `aide-de-camp-build` on iad-ci:
- Docker build → `ronaldraygun/aide-de-camp`
- Update image tag in `jedarden/declarative-config` (k8s/ardenone-cluster/aide-de-camp/)
- ArgoCD syncs automatically

Same pattern as every other containerized service in the stack.

---

## Technology Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | FastAPI (Python) | Reuse DUCK-E scaffolding; SSE + WebSocket support; async-native |
| STT | Web Speech API → whisper-stt fallback | Zero-latency browser-native; whisper-stt already deployed |
| Voice session | OpenAI Realtime API (via DUCK-E session handler) | DUCK-E scaffolding already built on this |
| LLM calls | ZAI proxy (`llm-proxy.ardenone.com`) | Pay-per-token, no subscription pressure on hot path |
| Task workers | NEEDLE + Claude Code | Existing infrastructure, unchanged |
| Session store | SQLite (WAL mode) | Lightweight, local, additive-only schema; single-user app |
| Artifact store | PVC-mounted filesystem (Deploy Stage B) / local filesystem (Deploy Stage A) | Writable at runtime; hot-reload reads per-invocation |
| Frontend | Vanilla JS + Web Components | No build pipeline; SSE consumer injects server-rendered component-card HTML. Client-side rendering is limited to the built-in card templates shipped with the served frontend (`src/canvas/`): the generic fallback card, the first-run welcome card, the pending/ack card with its progress states, the error/clarification cards (see Degraded-State UX), and the aged-pending treatment on overdue cards — every component-library card arrives server-rendered |
| Deploy Stage A hosting | Hetzner server, local process | Simplest path; shared filesystem with NEEDLE workers |
| Deploy Stage B hosting | ardenone-cluster, k8s Deployment | Behind existing Traefik + Tailscale ingress |

---

## Implementation Phases

**Status vocabulary.** Every phase status below carries one of two verification tiers — never read "COMPLETE" without its tier:

- **verified-in-tests** — deliverables pass the automated test harness / smoke tests (the `src/test/` endpoints that bypass the Web Speech API). Says nothing about behavior on the live server for a real user.
- **verified-live** — observed working on the running server, with the date and how it was observed recorded on the status line.

As of 2026-07-22 no phase has reached verified-live end-to-end; the only live check on record (2026-07-20, ADR-1) disproved a Phase 1 deliverable.

### Phase 0 — Minimal Viable Surface (~2 days)

**Status: COMPLETE (verified-in-tests)** — not yet verified-live

*Verification evidence:* see `docs/notes/core-verification-evidence.md` — smoke test results, 20+ runs with all tests passing (test harness, not live; date unrecorded — re-verify)

Validates the core question: does routing + parallel dispatch reduce friction?

- Single HTML page: textarea + mic button (Web Speech API)
- `POST /dispatch` endpoint: router → N parallel synthesize calls → SSE stream
- Results appear as basic cards as agents resolve
- No persistence, no auth, no component library, no ambient push

Deliverable: the core query loop working end-to-end.

### Phase 1 — Session and Topics (~1 week)

**Status: PARTIAL** ⚠️ — session store, topics, and bead watcher are verified-in-tests; the Telegram fallback deliverable is non-functional in every deployment to date (stub methods returning `False`, unreachable hardcoded bridge URL, architectural mismatch — see ADR-1, observed live 2026-07-20). Re-opened pending ADR-1 implementation.

*Verification evidence:* see `docs/notes/core-verification-evidence.md` — session store, SSE, surface registration (test harness, not live; date unrecorded — re-verify). Those tests passed while the Telegram stubs shipped — this is exactly why the two-tier vocabulary above exists.

Results persist; the canvas has memory.

- Session store (SQLite, 7+ tables with topic_context_cache and feedback_signals)
- Topic model: canvas shows one card per **(active topic, result_type)** pair, each updated in place — a status card and a brainstorm card on the same project topic coexist as distinct cards, grouped under the topic; a new result replaces only the card sharing both its topic and its result_type
- Telegram surface fallback (reuse telegram-claude-bridge)
- Bead watcher: closed NEEDLE beads push results to active surface
- Workload summary on reconnect
- Staleness indicators on cards

Deliverable: sessions that survive browser refresh (verified-in-tests); Telegram fallback working (**not met** — see ADR-1).

### Phase 2 — Self-Improvement Loop (~2 weeks)

**Status: COMPLETE (verified-in-tests)** — not yet verified-live

*Verification evidence:* see `docs/notes/core-verification-evidence.md` — component library, hot-reload manager (test harness, not live; date unrecorded — re-verify)

The interface can be improved by talking into it.

- Self-modification agent (Claude Code via NEEDLE)
- Hot-reload confirmed at every artifact layer
- Component library: UI-regen agent generates first components from actual result shapes
- Canvas live-updates when a component is versioned
- Explicit feedback processed: "always include X" → prompt updated → hot-reloaded

Deliverable: at least one end-to-end self-modification cycle working (user instructs change, diff surfaced, approved, takes effect without redeploy).

### Phase 3 — Responsiveness (~2-3 weeks)

**Status: COMPLETE (verified-in-tests)** — not yet verified-live

*Verification evidence:* see `docs/notes/core-verification-evidence.md` — ambient monitoring, context warmer (test harness, not live; date unrecorded — re-verify)

The interface feels alive, not just reactive.

- Ambient monitoring: active topics watched for state changes
- Diff-aware results: show what changed since last result
- Pre-warmed context: active topics refreshed in background every N minutes
- Multi-turn within topic: follow-up questions deepen current topic context
- Speculative pre-fetch: common follow-up patterns pre-fetched
- Notification batching in audio mode
- Implicit feedback signals fed to background analysis bead

Deliverable: monitoring fires unprompted for a watched topic; follow-up questions are visibly faster.

### Phase 4 — Audio Surface (~1-2 weeks)

**Status: COMPLETE (verified-in-tests)** — not yet verified-live

*Verification evidence:* see `README-PHASE4.md` (repo root; full voice session implementation with Realtime API) and `docs/notes/core-verification-evidence.md` (both test harness, not live; date unrecorded — re-verify)

Full audio mode via Realtime API.

- Realtime API voice session replaces text input path
- Tool-as-trigger model: `dispatch_intent()` returns ack, result arrives async
- Urgency-tiered voice narration
- Audio-to-canvas session continuity

Deliverable: full voice session with canvas catch-up on surface switch.

### Phase 5 — Demo Readiness (~3-5 days)

**Status: COMPLETE** ✅ — **ArgoCD caveat resolution VERIFIED 2026-07-23**; latency optimization COMPLETE and budget compliance VERIFIED 2026-07-24; demo ready to proceed

Phases 0-4 make the system work end-to-end; none of them make a screen-capture of it smooth. **Public launch gates on this phase, not on Phases 0-4** — the launch artifact is a recording, and a complete-and-verified core is necessary but not sufficient to produce one. This phase turns "the demo isn't smooth" from a feeling into a checklist with pass/fail criteria.

**Verification evidence (2026-07-23):**
- ArgoCD readability confirmed via seeding tool (`docs/notes/seeding-report-latest.md`): Dispatch Execution check PASSED with all 5 scripted test dispatches succeeding and zero warnings about failed ArgoCD sources. Both pbx-web and whisper-stt (ardenone-cluster projects) resolve through the ardenone-manager read-only proxy with no caveats.
- Registry verification PASSED: both scripted projects properly configured with correct `cluster`, `argocd_app`, and `repo_path` entries.
- Outstanding issues from seeding run: Context Warmer implementation (SessionStore missing `get_topic` method), Component Coverage (5 result types need UI-regen beads).

#### Demo script (golden path)

One scripted run, recorded in a single unedited take. The take is **canvas-only**: utterances enter through the canvas page's Web Speech STT — the Realtime API voice session (Phase 4's audio surface) is not part of the launch recording; a voice-session demo is post-launch work (see Open Question 6). Every utterance uses a registered project (pbx-web, whisper-stt) and only intents the registry supports for that project — step 5's `task-profile` included: both example entries list it in `intent_support`. The `action` intent is deliberately excluded from the script — its execution model carries its own constraints and adds risk without adding demo value.

**Note:** Both scripted projects (pbx-web, whisper-stt) are hosted on ardenone-cluster, whose ArgoCD applications live on ardenone-manager and are readable via the existing no-auth read-only proxy at `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444`. This ArgoCD-readability path (Option B, per HUMAN decision bead adc-359d) ensures the scripted status cards render without `fetch_coverage` caveat strips, satisfying smooth criterion 3.

| Step | Utterance | Intent(s) | Expected canvas output |
|------|-----------|-----------|------------------------|
| 1 | "Has the pbx web caught up, and what's the state of whisper stt?" | status ×2 (pbx-web, whisper-stt) | Router splits into two threads; two cards appear and resolve **in parallel** — pod status, ArgoCD sync state, recent commits (from declarative-config, where both apps' manifests live), per-project status. Both projects are on ardenone-cluster; their ArgoCD apps (pbx-web, whisper-stt) resolve via the ardenone-manager read-only proxy, so no `fetch_coverage` caveat appears. |
| 2 | "Pull up the recent logs for whisper stt." | lookup/logs (whisper-stt) | Log-lookup card (`lookup:logs:whisper-stt`) with recent log lines, appearing under the existing whisper-stt topic as its own card beside the step-1 status card — one card per (topic, result_type): grouped, not a new pile |
| 3 | "Should pbx web keep using the static site generator, or is it time to move to a dynamic frontend? Give me the trade-offs." | brainstorm (pbx-web) | Brainstorm card: structured trade-off summary, visually distinct from status cards and coexisting with the step-1 pbx-web status card on the same topic (distinct result_type → distinct card, per the (topic, result_type) granularity) |
| 4 | "Find whisper stt's deployment config — which cluster and namespace is it on?" | lookup/config (whisper-stt) | Config-lookup card (`lookup:config:whisper-stt`) with cluster/namespace and manifest pointers from registry + fetched config — a different `lookup_kind` than step 2, so a different fetch matrix, result_type, and component; it renders as its own card, it does not overwrite step 2's log card |
| 5 | "Queue up a research task: compare the last month of pbx web deployment patterns against whisper stt's and write up common failure patterns — no rush." | task-profile | Escalate strand fires; ack/pending card appears immediately on router completion with an explicit "queuing async" state, then updates in place with the `bf` bead reference once `bf create` returns (see the Latency Budget's escalate row). Bead **closure is not part of the take** — the pending card is the demo-visible outcome |
| 6 | "Anything new on pbx web since we started?" | status (pbx-web) | Existing pbx-web **status** card updates **in place** — no new card — with a diff summary naming exactly what changed since step 1. The diff runs against the step-1 status result via `previous_result_id`, which is scoped to the same result_type on the same topic: step 3's brainstorm card is a different result_type, stays on canvas untouched, and never enters the diff. The diff strip renders here because step 1's result is in-session — the same session-scoped display rule that suppresses "changes since the seed run" strips on step 1 (see Cold start & demo seed — Topic scope vs. session scope). If nothing changed, an explicit "no changes since" diff state (also a passing outcome). No speed contrast is claimed: seeding warms both scripted topics, so step 1 is just as warm |

#### Definition of "smooth" (measurable)

The take passes only if all of the following hold — each is observable in the recording or in the timing log:

1. First partial card ≤ 3s after end of utterance, on **every** scripted step — for the task-profile step (5) the qualifying card is the ack/pending card rendered on router completion, per the Latency Budget's task-profile note (this finally verifies the plan's own hot-path target on camera)
2. Every thread from a multi-intent utterance renders as its own card — zero dropped or merged threads
3. Zero visible error states: no raw JSON, no stack traces, no empty cards, no failed-fetch caveats on scripted topics — and scope caveats count as failures here, explicitly: the Beads-Workspace Scoping fallback's "showing aide-de-camp-originated beads only" strip on a scripted card fails the take (the seeding runbook's `repo_path` verification exists to make it impossible)
4. Zero dead-end cards: every card either resolves with data or shows an honest pending state the script accounts for (step 5)
5. The SSE connection never visibly drops and the page is never refreshed during the take
6. STT accepts each scripted utterance on the first attempt (a mis-transcription restarts the take, it is not edited around)
7. The full take completes in a single unedited capture

#### Known-issues register

Seeded from what this plan already establishes. The rule: an issue either blocks the take or is explicitly routed around by the script — never silently hoped past.

| Issue | Established by | Must fix before demo? | Demo handling |
|-------|----------------|-----------------------|---------------|
| Telegram fallback has never worked in any deployment (push API the code assumes doesn't exist) | ADR-1 | No | Demo is canvas-only; Telegram stays out of the script and the take. ADR-1 implementation lands post-launch |
| < 3s first-card target never measured under real fetch load | Open Questions 2 & 4; verification evidence is smoke tests, not timed runs | **Yes** | Timed rehearsal runs are the measurement; any step over budget files a defect bead |
| Task-profile pending-card lifecycle (24h/3-failure circuit breaker, `stuck` status, visible aging) is designed in The Async Path but not yet implemented or verified | Async Path — re-dispatch circuit breaker + visible aging | **Yes** (pending-card honesty: bead ref, explicit async state, elapsed time); No (breaker trip / closure on camera) | Pending card must show the bead ref, an explicit async state, and elapsed time — never an endless spinner. Script waits for neither closure nor the breaker |
| Degraded-state error cards are fully specified in Degraded-State UX but not yet implemented or verified against real source timeouts | Degraded-State UX (card templates); Open Question 2 (timeout behavior unmeasured) | **Yes** | Implement and verify the fixed card templates; a mid-take kubectl/ArgoCD timeout must render as the designed caveat strip on an otherwise-complete card, not as an error or a blank |
| Clarification round-trip flow unresolved | Open Question 7 | No | Script uses exact registry aliases so clarification never triggers; the no-match card (below) is the insurance if it does |
| Both scripted projects NOW declare `cluster: ardenone-cluster`, whose ArgoCD applications live on ardenone-manager — and ardenone-manager HAS a no-auth read-only ArgoCD proxy (`https://argocd-ro-ardenone-manager-ts.ardenone.com:8444`) that the fetch strand can consume directly. Zero ArgoCD-source caveats on scripted status cards. | Cluster→ArgoCD Endpoint Resolution (Fetch Strand); `config/clusters.yaml`; HUMAN decision bead adc-359d (Option B: re-script demo onto ardenone-cluster projects) | **No — RESOLVED (VERIFIED 2026-07-23)** | Demo re-scripted onto pbx-web and whisper-stt (both ardenone-cluster-hosted). Their ArgoCD apps resolve via the existing ardenone-manager read-only proxy (access: read-only-proxy), so scripted status cards render caveat-free. **Verified via seeding tool run 2026-07-23T16:08:59**: Dispatch Execution check PASSED with all 5 scripted test dispatches succeeding and zero warnings about failed ArgoCD sources (see `docs/notes/seeding-report-latest.md`). The seeding runbook's item (3) verifies each scripted project's `argocd_app` exists and returns application state on the correct instance (ardenone-manager's ArgoCD, not rs-manager's). Option A (rs-manager RO proxy) deferred post-launch as the better end-state. |
| Synthesize latency exceeds budget by 2-3× — p50 3,108-3,984ms against ~1-2s target; p95 reaches 7,877ms. Accounts for ~60% of e2e latency. Demo-blocking per plan gate. | Latency baseline (bead adc-2xf52); docs/notes/latency-baseline-2026-07.md | **Yes** | Synthesis must be optimized to meet budget before demo can proceed. Bead adc-1btyk filed for investigation. |
| Intent Router latency exceeds budget by 3-4× — p50 1,587-2,074ms against ~500ms target; p95 reaches 4,301ms. Accounts for ~40% of e2e latency. Demo-blocking per plan gate. | Latency baseline (bead adc-2xf52); docs/notes/latency-baseline-2026-07.md | **Yes** | Router must be optimized to meet budget before demo can proceed. Bead adc-25sn9 filed for investigation. |

New defects found during rehearsal are appended here with the same must-fix triage before the real take.

#### Cold start & demo seed

The recording starts from a first-run canvas, so the first frame of the demo *is* the cold-start experience — it cannot be undefined.

- **First-run canvas state:** never a blank page. A welcome card renders on first load: one-line description of aide-de-camp, the list of registered projects (served from `registry.yaml`), and 2-3 example utterances drawn from those projects' supported intents. It is **built into the served frontend** (`src/canvas/`, exactly like the generic fallback card) — not a component-library row — so the demo's first frame renders correctly even against an empty `components.db`, with zero dependence on DB state or a prior UI-regen run. The first real result replaces it.
- **No-match routing:** an utterance that resolves to no registered project returns a `clarification` thread, rendered as a friendly clarification card — "no project matching *X*; registered projects are: …" with the nearest-alias suggestion. Never an empty canvas, never a raw router error.
- **Pre-demo seeding (runbook, not hidden magic):** before recording — (1) registry populated and alias-verified for every project in the script, with `intent_support` confirmed to cover every scripted intent — including `task-profile` on both pbx-web and whisper-stt, or step 5 dies in routing — and `repo_path` confirmed present and pointing at a checkout for every scripted project (for pbx-web and whisper-stt: `/home/coding/declarative-config`, where both apps' ArgoCD manifests live; this provides git log source even though the projects have no separate code repos), or step 1's git log source fails; (2) context warmer run against both scripted topics so `topic_context_cache` is warm and step 1 lands inside budget; (3) one throwaway dispatch per scripted topic to confirm every fetch source (kubectl proxies, ArgoCD, git, `bf`) is reachable *before* the take starts — for ArgoCD this means confirming each scripted project's `argocd_app` exists and returns application state on the instance its `cluster` maps to in `config/clusters.yaml` (for both scripted projects: ardenone-cluster maps to ardenone-manager's ArgoCD at `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444`, which is a read-only-proxy endpoint and requires no additional provisioning), not merely that some ArgoCD endpoint answers — and confirming `GET /health` reports `watcher.alive: true` (see Deploy Stage A process model); (4) **component library seeded for every scripted result shape** — UI-regen is async and nothing guarantees it has ever run, so left alone every scripted card renders as the generic key/value fallback (killing step 3's "visually distinct" expectation, among others). For each distinct result_type the script produces — `status:pbx-web`, `status:whisper-stt`, `lookup:logs:whisper-stt`, `lookup:config:whisper-stt`, `brainstorm:pbx-web` (selection keys on the **full** result_type, so each needs its own `component_usage_patterns` mapping row, even where one component template serves two of them) — file a UI-regen bead from a throwaway dispatch's output and confirm it closed; then re-run the step-(3) dispatches and confirm every scripted **result** card renders a real component-library card — **no scripted result card falls to the generic fallback** is a hard runbook exit condition. Step 5's ack/pending card is deliberately absent from this list: pending/ack cards are served built-ins (see Component Library → Built-in cards), not component-library shapes — there is nothing to seed for them and nothing UI-regen could produce. The recording still opens on the first-run welcome card — seeding warms the caches and the component library behind it, it doesn't fake the output.
- **Topic scope vs. session scope (what seeding carries over, and what it must not):** project topics are **cross-session** (`topics.scope: 'cross-session'`, `session_id` NULL). That is what makes runbook items (2)–(4) work at all: the take starts a fresh session, and a fresh session reuses the seeded topics — same topic_ids, warm `topic_context_cache` — instead of minting new ones and cold-fetching step 1 straight through the 3s gate. Card display is scoped the other way: the canvas renders only the **current session's** results, so a fresh session opens on the welcome card, never on replayed seed cards (the reconnect workload-summary replay is within-session recovery, not cross-session history). Diff display follows the same session scoping: `previous_result_id` is pure lineage — set whenever a prior result of the same result_type exists on the topic, regardless of session, so step 1's results do point at the seed dispatches — but the server includes the diff strip at card-render time only when the previous result belongs to the current session. Step 1 therefore renders clean cards with no unscripted "changes since the seed run" strips, while step 6 still diffs legitimately against step 1, which is in-session (see the `previous_result_id` schema comment and demo step 6).

#### Rehearsal checklist

- [ ] 3 consecutive clean end-to-end runs of the golden path, each meeting every "smooth" criterion, before the real take
- [ ] Every rehearsal starts from the demo's actual starting state: fresh session, seeded registry, warm cache, seeded component library (per Cold start & demo seed)
- [ ] Every scripted **result** card is a real component-library card — any result card falling to the generic fallback is a defect that reopens seeding-runbook item (4). Pending/ack and welcome cards are exempt by design: they are served built-ins (see Component Library → Built-in cards), so step 5's qualifying ack/pending card rendering from the built-in template is correct behavior, not a fallback defect
- [ ] Rehearsals are recorded and reviewed — visual glitches invisible in the moment are still defects
- [ ] Per-step timing log (utterance end → first card) captured each run; any step > 3s files a defect bead
- [ ] Mid-take failure fallback decided **in advance**: a visible error discards the take and restarts from cold — never narrated around, never edited out
- [ ] Known-issues register re-reviewed on demo day; any open must-fix blocks the take

Deliverable: one unedited screen-capture recording of the full golden path meeting every criterion in the smooth definition.

### Future Work

**Status: NOT STARTED** ❌

*Note: Phases 0 and 2-4 are complete at the verified-in-tests tier only, Phase 1 is PARTIAL (Telegram fallback non-functional — see ADR-1), and Phase 5 (Demo Readiness) — the launch gate — has not started. No phase is verified-live yet; closing that gap — starting with ADR-1 — and shipping Phase 5 come before any item below.*

Potential enhancements beyond Phase 5:
- Multi-modal input (image processing for UI feedback via Agentation)
- Advanced topic clustering and auto-archival
- Cross-session context persistence with summarization
- Mobile-native surface (iOS/Android app)
- Collaborative sessions (multi-user shared canvases)
- Advanced memory extraction with semantic search
- Reminders (the `reminder` intent, currently NOT YET IMPLEMENTED — see Intent Router). Minimal sketch: a `reminders` table in the session store (text, due_at, recurrence, status), a due-check folded into the bead watcher's existing poll tick (no new daemon, per the no-CronJob convention), and delivery via Surface Routing Rules — which makes firing with no canvas open gated on ADR-1's Telegram channel
- Claude Realtime migration for the voice session (today: OpenAI Realtime API via the DUCK-E session handler)

---

## Self-Improvement: Hot-Reload Architecture

Every artifact that encodes behavior is readable, writable, and reloaded per-invocation:

| Behavior | Artifact | Reload point |
|----------|----------|-------------|
| Utterance segmentation | `prompts/router.md` | Each router call |
| Intent→project routing | `config/registry.yaml` | Each router call |
| Context fetch strategy | `prompts/fetch/{type}.md` (lookup: `lookup-{kind}.md`) | Each fetch invocation |
| Result format and detail | `prompts/synthesize.md` | Each synthesize call |
| Voice narration style | `prompts/voice.md` | Each session turn |
| Urgency classification | `prompts/urgency.md` | Each router call (initial assignment); each escalate call (bead refinement) |
| Visual rendering | Component library (DB) | Each card render |
| Monitoring rules | `config/monitoring.yaml` | Each monitoring tick |

Per-invocation reload is the implementation strategy, via an mtime-checked cache: stat the artifact on each invocation, re-read only when the mtime has changed, serve the cached parse otherwise. This is the single reload strategy for every file-backed artifact above — no component reads uncached, and none caches past an mtime change. File watching adds complexity for no benefit — prompts change rarely and stat calls are cheap.

---

## Surface Routing Rules

When a result is ready to surface, the bead watcher or synthesize strand uses this priority:

1. The surface the utterance originated from (if still connected)
2. Most recently active connected surface
3. Any connected surface
4. Telegram (always-available fallback) — ⚠ NON-FUNCTIONAL until ADR-1 lands

Exception-class results (urgency: critical, type: exception) push to Telegram regardless of canvas state if no canvas has been active within the past N minutes.

> ⚠ Tier 4 and the exception-class push do not work today: Telegram delivery has never functioned in any deployment of aide-de-camp — the delivery methods are stubs pointed at an unreachable bridge URL (see ADR-1). Until ADR-1 lands, a result that falls through to tier 4 is persisted to the session store but reaches no one. "Always-available fallback" is design intent, not shipped behavior.

---

## Relationship to Existing Infrastructure

aide-de-camp adds a routing and rendering layer on top of existing infrastructure without replacing any of it:

- **NEEDLE workers** — unchanged. Task beads work exactly as before. The bead watcher is a new in-process watcher loop inside the aide-de-camp server that observes bead closure events.
- **telegram-claude-bridge** — ⚠ planned reuse for the Telegram surface and HUMAN bead push delivery turned out to be architecturally infeasible: the bridge is a Claude Code session router, not a push-notification API, and this integration has never worked in any deployment. See ADR-1, which proposes replacing it with a direct Telegram Bot API integration.
- **whisper-stt** — already deployed on ardenone-cluster; available as STT backend.
- **ZAI proxy** — all direct API calls (router, synthesize, escalate) route through `llm-proxy.ardenone.com`.
- **claude-governor** — governs subscription token consumption for self-modification and UI-regen task beads.
- **DUCK-E** — FastAPI scaffolding, WebSocket handling, OpenAI Realtime API session management, and middleware reused as the voice layer foundation.
- **beads (bf CLI)** — task work items and HUMAN exceptions only. Conversational session state lives in a separate SQLite session store.
- **kubectl proxies** — fetch strand uses existing kubectl proxy access per cluster.
- **ArgoCD** — fetch strand reads ArgoCD application state via the endpoint mapped to the project's `cluster` in `config/clusters.yaml`: the no-auth read-only proxy `argocd-ro-ardenone-manager-ts.ardenone.com:8444` for ardenone-cluster apps (ArgoCD on ardenone-manager); apexalgo-iad and the other iad-* Spot clusters are managed by rs-manager's ArgoCD, which has no equivalent read-only proxy today (must-fix before the demo — see the Phase 5 known-issues register).

Net-new code: the codebase measures approximately **15,400 lines** of Python. That is a size figure, not a completeness figure — the count includes stubbed paths (ADR-1's Telegram fallback methods, which log a warning and return `False`, count the same as working code). For an honest completeness picture, use the per-phase statuses in Implementation Phases (verified-in-tests vs. verified-live) plus a stub sweep of `src/`, not line or module counts. See the File System Layout section for the module breakdown.

---

## Security Model

- aide-de-camp runs on the Hetzner server; all kubectl access is read-only via the kubectl proxies (same as existing tooling) — cluster mutations happen only as Git operations (see Action Execution Model below)
- No cluster credentials stored by aide-de-camp; existing proxy infrastructure holds them. aide-de-camp holds no admin kubeconfigs and must never be granted one
- Write scopes are per-agent and disjoint: the self-modification agent writes only the `prompts/` and `config/` directories within the repo; the UI-regen agent writes only component definitions in the component library — the `components`, `component_versions`, and `component_tags` tables in `data/components.db`, plus the `match_score` mappings it records in `component_usage_patterns`. The hot-path server is the one other writer to that DB, confined to mechanical render/usage state on each dispatch: `card_cache` rows and the usage-stat columns (`components.usage_count`/`last_used`, `component_usage_patterns.sample_count`/`last_matched`) — bookkeeping, never templates or definitions. Background-analysis auto-applies are not a third artifact writer: they execute through the self-modification agent's write path, inheriting its scope, freeze/kill-switch behavior, and git-commit rollback (see Background Analysis Bead). Neither agent writes the other's artifacts
- All artifact changes go through diff-review before application
- Rollback available for any artifact via git history (see Self-Modification Agent safety model)

### Action Execution Model

**Status: policy in force; executor NOT BUILT ❌ (design-only).** The rules below already bind the one mutation path that exists (escalate-strand beads under Generated-Bead Safety), but no runtime component executes `action` intents: there is no `src/action/` module and nothing interprets the registry's `workflows.steps`. Until the Action strand sketched below ships, `action` intents are **not dispatched** — the server renders a fixed "action execution isn't built yet" card offering to requeue the request as a task-profile, which flows through the escalate strand's reviewed-bead path. This is why the Phase 5 demo script excludes `action`.

The `action` intent and the registry's mutating workflow steps never translate into direct kubectl mutation — the read-only proxies could not execute one, and the GitOps rule forbids it even where credentials exist (live edits fight ArgoCD's selfHeal and don't stick). Every permitted action resolves to exactly one of:

1. **GitOps mutation** — deploys, restarts, scaling, and config changes execute as edits to manifests in `jedarden/declarative-config` (k8s/ path): commit, push, ArgoCD syncs. A "restart" is a manifest-level change (e.g., a rollout-trigger annotation bump) committed to the repo, not `kubectl rollout restart`.
2. **ArgoCD sync status polling** — after a GitOps commit, aide-de-camp polls the read-only ArgoCD API until the Application reports Synced/Healthy, then reports the outcome. aide-de-camp itself performs no ArgoCD writes; if a sync is genuinely stuck and needs a forced sync or other operator action, that escalates as a reviewed bead (next item), not an API call from aide-de-camp.
3. **Reviewed escalation bead** — anything not expressible as (1)+(2) becomes an escalate-strand bead, subject to Generated-Bead Safety validation and the user-approval gate, executed by NEEDLE/Claude Code workers under their own credentials.

Credentials per action class:

| Action class | Credential used | Held by |
|--------------|-----------------|---------|
| Fetch / status reads | read-only kubectl proxies, read-only ArgoCD proxy | proxy pods (no tokens on disk) |
| GitOps mutation | git credentials for `jedarden/declarative-config` | existing git credential helper |
| Sync status polling | none (read-only ArgoCD proxy injects its own token) | proxy |
| Escalated beads | workers' own credentials | NEEDLE workers, outside aide-de-camp |

#### Future: Action strand (executor sketch — NOT BUILT ❌)

When built, `action` execution gets exactly one owner: a deterministic step runner (`src/action/executor.py`, no LLM) that interprets a registry workflow's `steps` list. The step vocabulary the registry example uses:

| Step | Class | Semantics |
|------|-------|-----------|
| `ci-status` | read | Latest Argo Workflow for the project (same source as the fetch matrix's CI row); a green build gates the rest of the workflow |
| `image-tag` | read | Resolves the image tag/digest that build produced (never `:latest`) |
| `gitops-commit` | GitOps mutation | **The executor itself authors the declarative-config edit** — a templated field substitution (e.g., the image-tag field in the project's manifest under `k8s/<cluster>/...` in `jedarden/declarative-config`), committed and pushed under the standard git identity via the existing credential helper. Never free-form and never LLM-authored: any edit beyond a templated substitution is out of vocabulary and must go through a reviewed escalation bead |
| `argocd-sync-status` | read | Polls the read-only ArgoCD API until the Application reports Synced/Healthy, or a timeout expires and the step fails |
| `pod-status` | read | Post-sync `kubectl get pods -n {namespace}` via the read-only proxy, confirming the rollout actually landed |

Each step's outcome streams to the canvas as a progress card; a failed step halts the workflow and renders per Degraded-State UX. Building the executor — and only then removing the dispatch gate above — is post-launch work, deliberately off the demo path.

---

## Open Questions

Triaged 2026-07-22 against the corrected phase statuses above. A question is marked ANSWERED only where this document itself records the answer; nothing below cites measurements that were never taken.

1. **Routing accuracy** — how reliably can a haiku-class model split a rambling multi-project utterance into clean tagged threads? What's the false-split / under-split rate in practice?

   **OPEN — blocks demo.** Phase 0's smoke tests exercise the split path but no false-split / under-split rate was recorded. Needs live utterance data; part of taking Phase 0 to verified-live.

2. **Context latency** — can the fetch strand reliably hit kubectl + ArgoCD + git + beads within a 2-3s window? Which sources need timeouts and what's the degraded-result behavior?

   **OPEN — blocks demo.** Degraded-result behavior is answered in design (partial results + `fetch_coverage` caveats, see Fetch Strand), but the 2-3s window has never been measured against real kubectl/ArgoCD/git/beads latencies. Part of Phase 3's verified-live work.

3. **Component selection** — when does the UI-regen agent generate a new component vs. stretch an existing one? How is "good enough" match defined?

   **OPEN — reopens Phase 2 at the live tier.** `component_usage_patterns.match_score` exists to hold this signal, but no "good enough" threshold is defined anywhere in this plan; the generate-vs-stretch policy remains implicit in the UI-regen agent.

4. **Concurrency budget** — how many parallel synthesize calls can the ZAI proxy handle without queue pressure affecting the <3s target?

   **OPEN — blocks demo.** No concurrency measurement against the ZAI proxy is recorded in this plan or the cited evidence; the <3s target under parallel synthesize load is unverified.

5. **Topic vague reference resolution** — "the pipeline" vs. "options pipeline" vs. "options-pipeline". When does the router resolve from context vs. ask for clarification?

   **ANSWERED (mechanism) — see Intent Router and Project Registry.** Known names resolve via registry `aliases`; below the confidence threshold the router emits an `intent_type: "clarification"` thread instead of guessing. The threshold value itself is untuned — a live-usage task, not a demo blocker.

6. **Voice UX** — push-to-talk vs. continuous listening + VAD silence detection. What's the right default for the audio surface?

   **OPEN — does not block launch.** Phase 4 shipped the Realtime API session (verified-in-tests), but this plan records no push-to-talk vs. VAD decision. The launch recording is canvas-only — Phase 5's golden path enters every utterance through the canvas page's Web Speech STT, and no voice-session step exists in the script — so this question gates the *post-launch* voice-session demo, not the launch take. Extract the implemented default from `README-PHASE4.md` and record it here before any voice-session demo is scripted.

7. **Disambiguation flow** — when router confidence is below threshold, how does the clarification round-trip work without breaking conversational flow in audio mode?

   **OPEN — reopens Phase 4 at the live tier.** The mechanism is designed (clarification meta-type; "the voice model or canvas handles the clarification round-trip" — see Intent Router), but the audio-mode round-trip has never been observed live, and conversational-flow quality is precisely what verified-in-tests cannot show.

8. **LLM-proxy single point of failure** — the ZAI proxy is the sole LLM endpoint for both router and synthesize; should a direct-API fallback endpoint exist, and at what stage?

   **OPEN — demo severity: a proxy outage or quota exhaustion during the take kills the entire hot path** (router and synthesize both fail; the Degraded-State UX error cards are the only mitigation, and per the rehearsal checklist a visible error discards the take). No fallback endpoint is designed anywhere in this plan — accepted as a deliberate Deploy Stage A trade-off; revisit at Deploy Stage B.

---

## ADR-1: 2026-07-20 — Decouple the Telegram fallback surface from telegram-claude-bridge

**Status:** Accepted — 2026-07-22 (owner decision, recorded in bead adc-614p)

**Decision recorded 2026-07-22: ACCEPTED** (bead adc-614p). The bridge-stateless-proxy variant of the Decision — reusing telegram-claude-bridge's stateless proxy /send and /edit endpoints with a fixed chat_id, avoiding a second bot — is explicitly permitted; the implementer of bead adc-2uye chooses between it and a dedicated bot at implementation time, with the credential/chat_id provisioning tracked in bead adc-1oxl. The Telegram tier stays NON-FUNCTIONAL until those implementing steps ship and are verified live — every ⚠ annotation in the plan body pointing here stays true until then. The implementing steps are:

1. **Provisioning bead (one-time human step):** create the dedicated bot (or confirm reuse of the bridge's stateless proxy `/send`/`/edit` endpoints), capture the bot token and `chat_id`, configure `ADC_TELEGRAM_CHAT_ID` and the token secret.
2. **Rewrite `src/telegram/fallback.py`** against the Telegram Bot API (`sendMessage`/`editMessageText`), replacing the three stubbed methods (`send_exception`, `send_workload_summary`, `register_surface`).
3. **Remove `register_surface()` and the session→Telegram binding from the surfaces model** — Telegram stops being a session-bound surface row and becomes a fixed notification destination.
4. **Verify end-to-end and clean up:** force an exception-class result with no canvas connected, confirm the message arrives, then remove the ⚠ NON-FUNCTIONAL annotations from the plan body and update `README.md`'s configuration table.

### Context

The plan's "Surface Routing Rules" section makes Telegram the fallback of last resort:

> Exception-class results (urgency: critical, type: exception) push to Telegram regardless of canvas state if no canvas has been active within the past N minutes.

At the time of the 2026-07-20 audit, Phase 1 ("Session and Topics") was marked `Status: COMPLETE ✅` with "Telegram surface fallback (reuse telegram-claude-bridge)" listed as a shipped deliverable, and "Relationship to Existing Infrastructure" stated that `telegram-claude-bridge` was reused for the Telegram surface. (The plan body has since been corrected in light of this ADR: Phase 1 is now PARTIAL, and the reuse is recorded as architecturally infeasible.)

Live verification on 2026-07-20 against the running server (PID confirmed serving from this checkout, `git -C /home/coding/aide-de-camp` cwd) shows this promise does not hold:

1. **Wrong default, and never overridden at runtime.** `src/telegram/fallback.py` hardcodes `DEFAULT_BRIDGE_URL = "http://telegram-claude-bridge:8000"` — a k8s-internal-style hostname that does not resolve from the bare Hetzner host process (Phase 0 deployment, per this plan's "Deployment Model"). The documented fix — `ADC_TELEGRAM_BRIDGE_URL` env var, default value corrected in `README.md`'s configuration table — exists in code (bead `adc-lc4` already tracks making the URL configurable) but the server is started per this repo's `CLAUDE.md` run command with no env vars set, so the live process still uses the broken default. `GET /api/v1/status/telegram_bridge` on the running server currently returns `{"reachable": false, "bridge_url": "http://telegram-claude-bridge:8000", ...}`. The documented working URL (`https://telegram-proxy-telegram-bridge-ardenone-cluster-ts.ardenone.com:8444`) was independently confirmed reachable (`{"ok":true,"polling":true,...}`) during this audit.
2. **Even pointed at the right URL, the surface doesn't do what the plan promises.** `send_exception()`, `send_workload_summary()`, and `register_surface()` in `src/telegram/fallback.py` are stubs: each logs a warning and returns `False` (or a fake `True` for `register_surface`), with an explicit code comment explaining why — "telegram-claude-bridge uses pull-based architecture (manages sessions internally per forum topic), not push-based message delivery," and "the `/register_surface` endpoint does NOT exist in telegram-claude-bridge." These are exactly the three methods the exception-routing and workload-summary promises above depend on.
3. **The mismatch is architectural, not a bug.** Checked `/home/coding/telegram-claude-bridge`'s own README and CLAUDE.md: it is a *Claude Code session router* — one persistent `claude` process per `(chat_id, thread_id)` forum-topic pair, created via bot commands (`/new`), with tools like `update_progress` only available *inside* an active session. It has no concept of "register an external session_id against a chat_id and let me push arbitrary notifications to it." aide-de-camp's `TelegramFallback` class was written against an imagined generic push-notification API that the real service doesn't expose.

Net effect: the *only* channel the plan defines for reaching the user when no canvas is open — critical alerts, exception routing, workload summaries — has never worked in any deployment of aide-de-camp, and the existing beads (`adc-lc4`, `adc-44u`, and children) address the URL/observability half of the problem but not the deeper architecture mismatch in point 3.

### Decision

Give aide-de-camp its **own** direct, minimal Telegram Bot API integration — a fixed `chat_id` (the user's personal chat with a dedicated bot, configured once via `ADC_TELEGRAM_CHAT_ID` / a bot token secret) — instead of routing fallback notifications through `telegram-claude-bridge`. aide-de-camp calls `sendMessage`/`editMessageText` directly (or via `telegram-claude-bridge`'s stateless *proxy* component's `/send`, `/edit` endpoints if reusing its bot-token holder is preferred over provisioning a second bot — but *not* through the bridge's session/topic layer). `register_surface()`, and the assumption that a `session_id` maps to a Telegram forum topic, are removed. All aide-de-camp Telegram traffic becomes plain messages to one fixed destination — no topic creation, no session binding, no dependency on whether the user happens to have a live Claude Code conversation running in that bridge at the time.

### Alternatives Considered

- **A. Fix the URL and build the missing session→chat_id registry against telegram-claude-bridge's real model** (create/reuse a dedicated aide-de-camp forum topic, post into it via proxy calls). Rejected: telegram-claude-bridge's session model exists to route messages to a live `claude` process. Posting plain notifications into a topic either requires keeping a phantom Claude session alive just to have somewhere to post, or bypassing the bridge's session semantics and talking to its proxy layer directly anyway — at which point this is the Decision above, just laundered through a second project's internal model and its future schema changes.
- **B. Implement `register_surface()` for real** (a one-time `/register <session_id>` command run inside a bridge topic, stored server-side). Rejected: reintroduces the coupling of Alternative A, and "always-available fallback" is specifically the guarantee that must *not* depend on a setup step the user might forget, or on telegram-claude-bridge's session lifecycle (stale-session cleanup, restarts) continuing to hold that mapping.
- **C. Drop the Telegram fallback surface entirely; rely on canvas + CLI only.** Rejected: removes a load-bearing requirement from the plan's own Surface Routing Rules rather than fixing it — the entire point of urgency-tiered exception routing is reaching the user when no canvas tab is open.

### Consequences

- Exception pushes and workload summaries can actually work, independent of `telegram-claude-bridge` health, session state, or whether a forum topic happens to exist.
- Removes a runtime dependency and API-contract coupling on a project whose primary purpose (multi-agent coding sessions per Telegram topic) is unrelated to notification delivery — aide-de-camp no longer breaks silently when telegram-claude-bridge changes its internal session/topic schema.
- Two independent Telegram integrations now exist in the household stack (telegram-claude-bridge's own bot, aide-de-camp's own bot or shared-proxy usage) — needs a one-line note in `README.md`'s configuration table clarifying which is which, so a future pass doesn't "fix" aide-de-camp by re-coupling it to the bridge.
- Out of scope: two-way interaction (replying to a card *from* Telegram) — this ADR only covers aide-de-camp → Telegram notification delivery, not conversational input. That would need its own design if wanted later.
- Requires a one-time human step (bot token / chat_id provisioning) outside NEEDLE's reach — tracked as a separate bead rather than assumed away.
