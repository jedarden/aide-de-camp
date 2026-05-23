# Agent Runtimes: What Powers Each Component

## The Question

Claude Code interactive instances (what NEEDLE workers currently use) are powerful
but have overhead: session startup, PTY management, subscription token consumption.
Not every component in stream-dispatch needs that. The right runtime depends on
what the component actually does.

Three available runtimes:

| Runtime | Characteristics | Cost model |
|---------|----------------|------------|
| **Realtime API** | Conversational, persistent session, voice I/O | Per-token (or subscription for realtime) |
| **Direct API call** | Single-turn, stateless, no tool access | Pay-per-token via ZAI proxy |
| **Claude Code via NEEDLE** | Multi-step, tool access (files, shell), stateful per-session | Subscription tokens (claude-governor governed) |

---

## Component Map

### Voice model
**Runtime: Realtime API**

The thin conversational layer. Receives utterances, calls trigger tools, narrates
summaries. Needs a persistent session for natural conversation flow and voice I/O.
Does not need file access. Does not execute multi-step tasks.

Not Claude Code. Overhead of a NEEDLE invocation per utterance turn would kill
conversational latency.

### Router (utterance segmentation + routing)
**Runtime: Direct API call**

One LLM call per utterance: "here's the text, give me intent threads with project
tags." Stateless. No tool access. Result is a structured JSON array. Runs in
under 1 second with a haiku-class model.

Claude Code startup latency (PTY initialization, session setup) is 2-4 seconds —
longer than the call itself. Direct API is the only viable choice here.

### Fetch strand
**Runtime: Deterministic code, not LLM**

The Fetch strand executes a context spec: `kubectl get pods`, `git log -10`,
`br list --project X`. These are deterministic operations — the intent type
determines which commands to run, and the commands themselves are not LLM
decisions. An LLM call here adds latency and cost for no reasoning benefit.

Fetch is code that executes a command matrix based on `intent_type`. The output
is structured data handed to Synthesize. No Claude Code needed.

### Synthesize strand
**Runtime: Direct API call**

Takes fetched context + intent → produces `{data, summary}`. Single-turn
inference. No tool access needed — the context was already fetched by the Fetch
strand and passed in.

Direct API call with a sonnet-class model. Fast, cheap, no session overhead.
This runs once per intent thread in parallel across all active threads.

### Escalate strand
**Runtime: Direct API call + `br create`**

Formulates a bead body from the intent + context (one LLM call), then runs
`br create` (shell invocation). Brief, sequential. No interactive session needed.

### UI-regen agent (component generation and iteration)
**Runtime: Claude Code via NEEDLE (task bead)**

Generating a new component or iterating an existing one is multi-step:
1. Read the current component from the library
2. Understand what to change
3. Generate the update
4. Possibly iterate if the first attempt isn't right
5. Write to the component library DB

File access and multi-step reasoning make this the right fit for Claude Code
via NEEDLE. Created as a `stream-task` bead, picked up by a dedicated worker.
Not on the hot path — component generation happens asynchronously, result pushed
to canvas when done.

### Self-modification agent (prompt, registry, routing rule updates)
**Runtime: Claude Code via NEEDLE (task bead)**

Reads files, writes files, shows diffs, iterates. The canonical multi-step
file-editing task. This is exactly what Claude Code workers already do for
coding tasks. Same runtime, different artifact types (prompt files and YAML
instead of source code).

The self-modification agent is the component that makes "improving the interface
by talking into it" work. It is a Claude Code instance, operating on the
interface's own artifacts.

### Background analysis bead (pattern recognition, improvement proposals)
**Runtime: Claude Code via NEEDLE (task bead)**

Reads from the session store, analyzes intent/engagement history, identifies
patterns, proposes artifact updates. Long-running analysis. Multi-step. File
access to read prompt files and registry for context.

Runs on a schedule (low-priority bead, created periodically) not on the hot path.

### Task beads (research, coding, long-running work)
**Runtime: Claude Code via NEEDLE (existing)**

Unchanged from current NEEDLE workers. Already the right runtime.

### Bead watcher
**Runtime: No LLM — daemon process**

Watches for bead close events, reads session_id from closed bead, looks up
active surface in session store, writes to results table, fires SSE push or
Telegram push. Pure I/O — no inference needed.

---

## Summary

```
Realtime API          Voice model
                      (persistent conversational session)

Direct API call       Router — utterance segmentation
(ZAI proxy,          Synthesize strand — result generation
no session)          Escalate strand — bead body formulation

Deterministic code    Fetch strand — kubectl/git/br execution
(no LLM)             Bead watcher — event routing daemon

Claude Code           UI-regen agent — component generation/iteration
via NEEDLE            Self-modification agent — prompt/registry/config updates
(task beads)          Background analysis — pattern recognition, proposals
                      All existing task beads — research, coding, etc.
```

The hot path (voice → router → fetch → synthesize → result) uses only direct
API calls and deterministic code. No Claude Code session startup on the critical
path. A full round-trip from utterance to first partial result should be under 3
seconds.

Claude Code via NEEDLE handles everything that improves the system itself. These
are task beads — asynchronous, not on the critical path, dispatched after the
live response is already on its way to the user.

---

## Subscription Pressure

Claude Code workers consume subscription tokens, governed by claude-governor.
The self-modification and UI-regen agents add to this consumption. Two mitigations:

1. These agents are task beads — they run during quieter periods when general
   worker load is low. claude-governor already manages this tradeoff.

2. Self-modification calls are infrequent by nature (a user doesn't restructure
   the interface dozens of times per day). Component generation is triggered only
   when a new result type genuinely lacks a suitable component.

The high-frequency hot-path components (router, synthesize) use direct API calls
(ZAI proxy, pay-per-token) — no subscription pressure there.
