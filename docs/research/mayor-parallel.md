# Stream Dispatch as a Parallel Mayor

## The Connection

The [needle-human-interface research](../gascity-study/mayor/needle-human-interface.md)
already defines the right abstraction: a **human interface adapter** that translates
between a human's preferred channel and NEEDLE's intake/escalation/observability
protocol.

Stream-dispatch is one implementation of that adapter — specifically the voice/web
channel. The parallel to Gas Town's Mayor is direct:

| | Gas Town Mayor | Stream Dispatch |
|---|---|---|
| Interface | One persistent Claude Code session | Voice/text web page |
| Decomposition | Mayor session decomposes in-context | Router segments utterance into threads |
| Worker dispatch | Mayor creates beads, workers claim them | Router invokes N parallel NEEDLE instances |
| Context growth | Mayor context compounds over time | Each NEEDLE invocation is stateless |
| Bottleneck | Single Mayor is a serialization point | Threads run in parallel, no shared state |
| Observability | Mayor reads state and reports | Card renderer displays results live |

Stream-dispatch avoids the Gas Town Mayor's core weakness — compounding context in
one long-lived session — by being **stateless and parallel**. Each intent thread is
an independent NEEDLE invocation with its own strand waterfall and its own context
window. When the user jumps from topic to topic mid-utterance, that's not a problem:
it's the natural input shape, and each topic becomes an independent invocation.

---

## Multiple Invocations, Not One

The user jumping from topic to topic is the expected case. "Has the options pipeline
caught up, also what's the status of the IBKR MCP, and remind me where I landed on
pdftract naming" — three topics, three NEEDLE invocations, running in parallel:

```
utterance
    │
    ▼
Router (segment + route)
    │
    ├─ intent: options-pipeline status  →  NEEDLE invocation A
    ├─ intent: ibkr-mcp status          →  NEEDLE invocation B
    └─ intent: pdftract naming recall   →  NEEDLE invocation C
                                               │
                                         all three run concurrently
                                         each with its own strand waterfall
                                         each with its own context window
                                               │
                                         card specs stream back independently
                                               │
                                         SSE → frontend renders each card as it lands
```

Each invocation is cold-started, runs its strand pipeline, returns a card spec, and
exits. No shared state between them. The router is the only coordinator.

---

## How This Fits the Adapter Interface

From the existing research, NEEDLE needs a human interface adapter that handles:

| Responsibility | Stream-dispatch implementation |
|---|---|
| **Work intake** (human → NEEDLE) | Voice/text → router → strand invocation or bead creation |
| **Escalation** (HUMAN bead → human) | Bead watcher pushes pending card to SSE stream |
| **Observability** (NEEDLE → human) | Card renderer; live status queries via live-profile intents |

Stream-dispatch is the "richest" adapter in the existing taxonomy — richer than
Telegram (which handles escalation and status but not real-time intake decomposition)
and closer to the Mayor adapter (which handles decomposition), but avoiding the
Mayor's context-compounding cost by making each invocation ephemeral.

---

## What the Strand Waterfall Looks Like Per Invocation

Each NEEDLE invocation for a stream-dispatch intent runs a purpose-built waterfall:

```
Fetch context  →  Synthesize response  →  (Escalate if async needed)
```

- **Fetch**: executes the context spec for this specific intent (kubectl, git, br)
- **Synthesize**: runs the LLM call with fetched context, produces card spec
- **Escalate**: if the intent can't be handled live, creates a bead and returns a pending card

This is shallow — 2-3 strands — because decomposition already happened in the router.
By the time NEEDLE is invoked, the utterance has been segmented and routed. NEEDLE's
job is execution, not planning.

The contrast with a Mayor-style invocation: a Mayor receives the raw utterance and
uses many strand passes (and much context) to decompose, plan, and execute. Here,
the router handles decomposition cheaply (one fast LLM call over the whole utterance),
and NEEDLE handles execution cheaply (one focused LLM call per thread with tight
context). Neither accumulates state.

This is architecturally equivalent to Gas City's **fanout bead** pattern: one input
spawns N parallel workers, each stateless, no coordinator holding shared context.
Gas City ships this as a first-class primitive (`internal/dispatch/fanout.go`).
Stream-dispatch implements the same shape at the NEEDLE invocation layer rather than
the bead layer — the router is the fanout point, NEEDLE invocations are the workers.

---

## The Statelessness Property

Gas Town's Mayor bottleneck comes from stateful accumulation: the Mayor session grows
longer with every interaction, consuming more tokens and becoming slower.

Stream-dispatch avoids this at every layer:

- **Router**: one LLM call per utterance, no persistent session
- **NEEDLE invocations**: cold-started per intent thread, exit on completion
- **Context**: fetched fresh per invocation from live systems
- **Session history**: stored externally (SQLite or beads), not in any running process

The only stateful component is the SSE connection from the browser to the router.
That's inherently bounded — it exists only while the browser tab is open.

---

## The Human Interface Adapter Framing

This means stream-dispatch should be designed *as* the adapter described in the
existing research, not as a standalone system. Concretely:

1. It implements the **adapter interface**: Work Intake + Escalation + Observability
2. It can run **alongside** other adapters (Telegram for push alerts, noop for direct CLI)
3. NEEDLE's internals don't change — the adapter is a translation layer over the
   existing event/command contract
4. The card renderer is just the observability surface for this channel

The existing research already has the implementation path (event emission → noop adapter
→ Telegram adapter → Mayor adapter). Stream-dispatch slots in as a parallel track to
the Mayor adapter path, sharing the same event emission infrastructure.

---

## References

- [gascity-study/mayor/needle-human-interface.md](../gascity-study/mayor/needle-human-interface.md) — the adapter interface this implements
- [gascity-study/mayor/concept.md](../gascity-study/mayor/concept.md) — Gas Town Mayor design and known weaknesses
- [gascity-study/mayor/needle-application.md](../gascity-study/mayor/needle-application.md) — ephemeral Mayor pattern for NEEDLE

> **Updated May 18 2026** — see [gascity-study/update-may-2026.md](../gascity-study/update-may-2026.md)
> for the full delta. Summary: Gas City grew from ~130 to 750 stars since early May and
> is now the more relevant reference. The Mayor bottleneck in Gas Town is still unaddressed.
> Gas City's **fanout bead + pool agents + optional Mayor** directly validates the
> parallel invocation model described here. The controller handles routing; no shared
> coordinator context is required.
