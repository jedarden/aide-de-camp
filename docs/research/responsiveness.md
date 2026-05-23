# Responsiveness: What's Missing

The current design handles the core loop well: utterance → dispatch → result →
surface. What it doesn't address is how the system *feels* — how fast it responds,
how aware it is of changing state, how well it handles natural conversation, and
how it learns to serve better over time.

---

## 1. Speed: Reducing Perceived Latency

### Pre-warmed context for active topics

The first query on a topic is slow — the agent fetches kubectl, git, beads fresh.
The second query on the same topic an hour later is equally slow. It shouldn't be.

Active topics should have a **context bundle** kept warm: a background process
refreshes context for any topic with recent activity every N minutes. When an
intent arrives for that topic, the agent starts with pre-loaded context rather
than fetching from scratch.

Not a full index — just the last-fetched state for active topics. Kept in the
session store. Invalidated when the topic goes quiet.

### Partial results while loading

When a compound intent touches multiple systems (kubectl + ArgoCD + git), don't
wait for all of them. Stream partial results as each source responds:

```
User: "what's the state of the kalshi-tape deploy?"
t=0.5s  CI status arrives → "build passed 3m ago"   [partial card updates]
t=1.2s  declarative-config check → "pinned to :abc123"
t=2.8s  ArgoCD sync → "synced"
t=3.1s  pod status → "running 1/1"                  [card complete]
```

The card renders in stages. Each piece of information appears as it lands rather
than all at once after the slowest source responds.

### Speculative pre-fetch on likely follow-ups

If the result is "pipeline is behind by 2h," the next question is almost certainly
"why?" or "which worker is failing?". Pre-fetch worker logs and pod events in the
background immediately after surfacing the result. The follow-up arrives in 1s
instead of 8s.

Pattern recognition drives this: common follow-up sequences are learnable from
the intent history. After N occurrences of "status → why → worker logs", the
system starts pre-fetching worker logs whenever it returns a "behind" status.

---

## 2. Awareness: The System Notices Things

### Ambient monitoring of active topics

Currently the system is purely reactive — it answers questions but doesn't watch.
Active topics should have configurable monitoring:

- **Poll-based**: re-fetch context for the topic every N minutes, compare to last
  known state, surface if materially different
- **Event-based**: watch for relevant events (bead closes, CI completions, pod
  restarts) and push immediately when they occur

The user doesn't ask "is the options pipeline still behind?" every hour. The system
should watch and say "pipeline caught up" without being asked.

Monitoring runs at the topic level, not the project level — the user only wants
ambient awareness for things they've recently expressed interest in.

### Drift detection

Related to monitoring: the system detects when the current state of a topic
has drifted from what was last reported to the user. If the user was told
"running 1/1" and the pod has since restarted 3 times, the system flags this
without being asked.

Drift is not the same as change — a pod restarting once might not be worth
surfacing. The threshold is configurable per topic type and urgency.

### Diff-aware results

Results currently show full state. More useful: show what changed.

```
Instead of:
  "Pipeline is behind by 2h. Last event 4m ago."

Show:
  "Pipeline is still behind — improved from 4h to 2h since you last checked."
```

The session store has all prior results for a topic. Diff generation is a
post-processing step after the agent returns raw state. The voice model can
narrate diffs naturally ("it's improved" vs. "it's gotten worse") and the canvas
card highlights the delta.

---

## 3. Conversational Quality

### Multi-turn within a topic

Currently each utterance produces N new intents that may create new topics or
append to existing ones. But conversation within a topic is different: follow-up
questions should deepen the current topic rather than branch it.

```
User: "check the options pipeline"
System: [surfaces result: behind by 2h]
User: "why is it behind?"         ← follow-up, same topic
User: "how long has this been going on?"  ← follow-up, same topic
User: "ok now check kalshi-tape"  ← new topic
```

The voice model needs to track topic focus — which topic is "current" in the
conversation. Follow-up intents inherit the current topic's context rather than
routing from scratch. The router applies a prior: if the utterance is ambiguous,
prefer the currently focused topic.

### Interruption and correction

"Check the options pipeline — actually wait, check kalshi-tape first." Mid-utterance
correction. The voice model receives the full utterance after VAD (voice activity
detection) silence, so this is handled at the utterance level if VAD is set to
wait for natural pauses.

But longer corrections — "forget what I just asked, I need to focus on X" — need
to cancel in-flight intents. The trigger model helps here: if the intent hasn't
been dispatched yet, cancel it. If it has, mark the pending result as stale and
suppress surfacing it.

A voice command like "cancel that" maps to `cancel_intent(most_recent_intent_id)`.

### Confidence and uncertainty signaling

When context fetch is partial (one source timed out, one returned an error), the
result should say so rather than presenting partial state as complete:

```
"Pipeline status: behind by 2h — but I couldn't reach ArgoCD, so sync state
 is unknown. kubectl and git were both reachable."
```

The agent knows which sources succeeded and which failed. The result schema carries
a `fetch_coverage` field. The voice model narrates caveats naturally; the canvas
card shows source status as small indicators.

### Graceful degradation by layer

If a whole cluster is unreachable:
- Don't fail the entire compound intent
- Return what's available from other sources
- Clearly flag what's missing
- Offer to retry the missing leg when connectivity is restored

---

## 4. Attention Management

### Staleness indicators

Results age. A status result from 45 minutes ago on a fast-moving system is
probably stale. The canvas should show this visually (faded, timestamped) and
the voice model should qualify: "last time I checked, about an hour ago..."

Staleness threshold is topic-type-dependent:
- Pod status: stale after ~5 minutes
- Git log: stale after ~30 minutes
- Bead list: stale after ~15 minutes
- ArgoCD sync: stale after ~10 minutes

Crossing a staleness threshold doesn't push a new result — it just marks the
existing card as potentially stale. The ambient monitoring layer may pre-emptively
refresh active topics before they go stale.

### Notification batching

The system should not push every result the moment it arrives. Multiple results
for different topics arriving within a short window should be batched:

```
Bad:  "Options pipeline: caught up." ... 3 seconds ... "Kalshi-tape: running." ... 2s ... "IBKR MCP: 2 open beads."
Good: "Three things came back: pipeline caught up, kalshi-tape running, IBKR MCP has 2 open beads."
```

In audio mode, a batching window (e.g., 5s) groups results that arrive close
together into one narration pass. In canvas mode, cards appear immediately — no
batching needed since there's no interruption cost.

### Workload summary on reconnect

When a surface reconnects after being idle (user picks up their phone, opens the
canvas after being away), surface a brief summary of what happened:

"While you were away: pipeline caught up, the pdftract naming bead closed — 8
candidates — and there's one new exception waiting for your input."

This is read from the session store: results that arrived while no surface was
active, plus any new exceptions. Delivered as a single narration or a summary
card, not as individual pushes.

### Implicit feedback

Engagement patterns signal quality without explicit feedback:
- User expands a card → that component or level of detail is valued
- User dismisses a result immediately → the summary was sufficient; don't
  elaborate by default
- User asks a follow-up → the result raised a question; the result was incomplete
  or the summary was unclear
- User ignores a proactive push entirely → that type of push is not valuable

These signals are learnable. The system adjusts: default to compact summaries for
topics where expansion is rare, richer defaults for topics where expansion is common.
Reduce proactive push frequency for event types the user consistently ignores.

---

## 5. Learning and Personalization

### Usage pattern recognition

Over sessions, patterns emerge:
- User always checks options pipeline before market open
- User consistently asks about CI status after pushing to a branch
- After checking a deploy, user always checks pod logs within 2 minutes

These become candidates for automation: "you usually check pod logs after a deploy
— want me to include that automatically?" or silently pre-fetch without asking.

The learning surface is the intent history in the session store. Patterns are
extracted by a background process (a low-priority NEEDLE task bead) and stored
as suggested automations. The user can accept or dismiss them.

### Vocabulary adaptation

The user refers to things by shorthand: "the pipeline," "the MCP," "that naming
thing." Over time the system learns these aliases from context and resolves them
without disambiguation. The topic model accumulates alternate labels.

### Attention budget calibration

Different users have different tolerance for proactive pushes. The system starts
conservative (push only critical exceptions, everything else on-demand) and relaxes
as the user demonstrates they engage with proactive results. Calibration is per-
urgency-tier, not binary.

---

## 6. Context from the Environment (Stretch)

### Current working context

What the user is actively doing provides implicit intent context:
- The git branch currently checked out suggests which project is active
- The tmux session currently focused suggests which workstream is in progress
- The last `br list` query suggests which project the user is thinking about

These signals could be collected passively (a small background watcher on this
server) and injected into the router as a prior. "User is on branch `feat/options-enrichment`
in the options-pipeline repo" boosts the options-pipeline topic as the likely
target for ambiguous utterances.

This is intrusive if not done carefully. The user should know it's happening.
Start opt-in, opt-out explicit.

---

## Priority Assessment

| Feature | Leverage | Effort | When |
|---------|----------|--------|------|
| Partial results while loading | High | Low | Phase 0 prototype |
| Confidence / uncertainty signaling | High | Low | Phase 0 prototype |
| Multi-turn within topic | High | Medium | Phase 0 prototype |
| Workload summary on reconnect | High | Low | Phase 1 |
| Staleness indicators | Medium | Low | Phase 1 |
| Notification batching | Medium | Low | Phase 1 |
| Diff-aware results | High | Medium | Phase 1 |
| Pre-warmed context for active topics | High | Medium | Phase 2 |
| Interruption / cancel | Medium | Medium | Phase 2 |
| Ambient monitoring | High | High | Phase 2 |
| Speculative pre-fetch | Medium | High | Phase 3 |
| Implicit feedback loop | Medium | High | Phase 3 |
| Usage pattern recognition | Medium | High | Phase 3 |
| Environment context injection | Low | High | Phase 4 |
