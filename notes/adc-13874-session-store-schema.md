# Session Store Schema Documentation

Generated: 2026-08-06
Source: `src/session/store.py` and `data/session.db`

## Overview

The session store is a SQLite database with WAL (Write-Ahead Logging) mode enabled for concurrent access. It stores sessions, surfaces, utterances, intents, results, topics, timing data, and various tracking tables for the aide-de-camp voice/text dispatch system.

**Database Location:** `/home/coding/aide-de-camp/data/session.db`
**WAL Mode:** Enabled (PRAGMA journal_mode=WAL)
**Synchronous Mode:** NORMAL

---

## Table Schema

### 1. `sessions`
**Purpose:** Surface-agnostic persistent entities representing user sessions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Session UUID |
| `created_at` | INTEGER | NOT NULL | Unix timestamp of session creation |
| `last_active` | INTEGER | NOT NULL | Unix timestamp of last activity |
| `primary_surface_id` | TEXT | - | ID of the primary surface (nullable) |
| `reformulation_count` | INTEGER | DEFAULT 0 | Number of re-formulation attempts (prevents infinite loops) |

**Notes:**
- Multiple surfaces can connect to the same session
- `reformulation_count` tracks user re-formulation attempts for the same intent

---

### 2. `surfaces`
**Purpose:** Transient windows into sessions (canvas, telegram, audio).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Surface UUID |
| `session_id` | TEXT | NOT NULL, FK | Reference to sessions.id (ON DELETE CASCADE) |
| `type` | TEXT | NOT NULL, CHECK | One of: 'canvas', 'telegram', 'audio' |
| `state` | TEXT | NOT NULL, CHECK | One of: 'active', 'idle', 'disconnected' (default: 'active') |
| `always_available` | INTEGER | CHECK(0,1), DEFAULT 0 | Always-available fallback surface (e.g., Telegram) |
| `last_seen` | INTEGER | NOT NULL | Unix timestamp of last heartbeat |

**Indexes:**
- `idx_surfaces_session` on `session_id`
- `idx_surfaces_state` on `state`

**Notes:**
- Surfaces are transient UI connections (browser tabs, Telegram chats, etc.)
- Telegram is the "always_available" fallback surface

---

### 3. `utterances`
**Purpose:** Raw input from users (text or voice-transcribed text).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Utterance UUID |
| `session_id` | TEXT | NOT NULL, FK | Reference to sessions.id (ON DELETE CASCADE) |
| `raw_text` | TEXT | NOT NULL | Original user input text |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when utterance was created |
| `router_timing_breakdown` | TEXT | - | JSON: detailed timing breakdown from intent router (nullable) |

**Indexes:**
- `idx_utterances_session` on `session_id`

**Router Timing Breakdown JSON Schema:**
```json
{
  "prompt_construction_ms": number,
  "proxy_call_ms": number,
  "proxy_network_ms": number,
  "proxy_inference_ms": number,
  "json_parse_ms": number,
  "process_ms": number,
  "total_ms": number,
  "intents_count": number,
  "cached": boolean
}
```

---

### 4. `intents`
**Purpose:** Parsed intent threads from utterances (classified by LLM router).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Intent UUID |
| `utterance_id` | TEXT | NOT NULL, FK | Reference to utterances.id (ON DELETE CASCADE) |
| `session_id` | TEXT | NOT NULL, FK | Reference to sessions.id (ON DELETE CASCADE) |
| `topic_id` | TEXT | FK | Reference to topics.id (ON DELETE SET NULL) |
| `project_slug` | TEXT | - | Project slug (e.g., 'pbx-web', 'whisper-stt') |
| `intent_type` | TEXT | NOT NULL | Intent type (status, action, lookup, brainstorm, reminder, task-profile, monitoring_config, self_modification) |
| `lookup_kind` | TEXT | - | Lookup intents only: 'logs', 'config', 'docs' (router-emitted) |
| `status` | TEXT | NOT NULL, CHECK | One of: 'pending', 'dispatched', 'resolved', 'cancelled', 'stuck', 'failed' (default: 'pending') |
| `bead_ref` | TEXT | - | Bead ID reference (for task-profile intents) |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when intent was created |
| `resolved_at` | INTEGER | - | Unix timestamp when intent was resolved |

**Indexes:**
- `idx_intents_session` on `session_id`
- `idx_intents_topic` on `topic_id`
- `idx_intents_status` on `status`

**Intent Status Values:**
- `pending` - Initial state, awaiting dispatch
- `dispatched` - Sent to fetch/synthesize pipeline
- `resolved` - Completed successfully
- `cancelled` - Cancelled by user or system
- `stuck` - Circuit breaker fenced (bead refused N times or aged out)
- `failed` - Failed with no recovery path

**Intent Types:**
- `status` - Hot-path status query
- `action` - Hot-path action request
- `lookup` - Hot-path lookup (logs, config, docs)
- `brainstorm` - Brainstorming request
- `reminder` - Reminder/time-based intent
- `task-profile` - Async bead-backed task
- `monitoring_config` - Monitoring configuration change
- `self_modification` - Self-modification request

---

### 5. `results`
**Purpose:** Structured data returned by agents (fetch + synthesize output).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Result UUID |
| `intent_id` | TEXT | FK, nullable | Reference to intents.id (NULL for monitoring-originated results) |
| `topic_id` | TEXT | NOT NULL, FK | Reference to topics.id (ON DELETE CASCADE) |
| `session_id` | TEXT | NOT NULL, FK | Reference to sessions.id (ON DELETE CASCADE) |
| `summary` | TEXT | NOT NULL | Human-readable result summary |
| `data` | TEXT | NOT NULL | JSON: structured result data |
| `urgency` | TEXT | NOT NULL, CHECK | One of: 'critical', 'high', 'normal', 'low' (default: 'normal') |
| `result_type` | TEXT | - | Component selector key (e.g., 'status:pbx-web', 'lookup:logs:whisper-stt') |
| `card_fallback` | INTEGER | NOT NULL, CHECK(0,1) | 1 when no component matched (fallback card), 0 when component rendered |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when result was created |
| `surfaced_at` | INTEGER | - | Unix timestamp when result was shown to user (nullable) |
| `acked_at` | INTEGER | - | Unix timestamp when user acknowledged (nullable) |
| `previous_result_id` | TEXT | FK | Reference to results.id for diff (ON DELETE SET NULL) |
| `diff_summary` | TEXT | - | Human-readable diff summary (nullable) |
| `diff_data` | TEXT | - | JSON: detailed field diffs (nullable) |

**Indexes:**
- `idx_results_session` on `session_id`
- `idx_results_topic` on `topic_id`
- `idx_results_created` on `created_at`
- `idx_results_previous` on `previous_result_id`

**Result Type Format:**
- Intent-derived: `"{intent_type}:{project_slug}"`
- Lookup intents: `"lookup:{lookup_kind}:{project_slug}"`
- Monitoring-originated: `"monitoring:{project_slug}"`

**Diff Data JSON Schema:**
```json
{
  "fields": [
    {
      "field_name": string,
      "old_value": any,
      "new_value": any,
      "change_type": "added" | "removed" | "changed"
    }
  ],
  "summary": string
}
```

---

### 6. `topics`
**Purpose:** Persistent concerns organizing intents and results.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Topic UUID |
| `label` | TEXT | NOT NULL | Human-readable topic label |
| `type` | TEXT | NOT NULL, CHECK | One of: 'project', 'research', 'personal', 'exception', 'compound' (default: 'adhoc') |
| `project_slugs` | TEXT | - | JSON array of project slugs |
| `scope` | TEXT | NOT NULL, CHECK | One of: 'session', 'cross-session', 'global' (default: 'session') |
| `session_id` | TEXT | FK | Reference to sessions.id (ON DELETE SET NULL) |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when topic was created |
| `last_active` | INTEGER | NOT NULL | Unix timestamp of last activity |
| `archived_at` | INTEGER | - | Unix timestamp when topic was archived (nullable) |

**Indexes:**
- `idx_topics_session` on `session_id`
- `idx_topics_scope` on `scope`
- `idx_topics_active` on `last_active DESC`

**Topic Types:**
- `project` - Project-specific concerns
- `research` - Research topics
- `personal` - Personal notes/tasks
- `exception` - Exception/HUMAN items
- `compound` - Multi-type topics

**Topic Scopes:**
- `session` - Visible only within the session that created it
- `cross-session` - Visible across all sessions (session_id is NULL)
- `global` - Global topics (future use)

---

### 7. `topic_context_cache`
**Purpose:** Pre-warmed context for active topics (kubectl, git, beads results).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `topic_id` | TEXT | PRIMARY KEY, FK | Reference to topics.id (ON DELETE CASCADE) |
| `context_data` | TEXT | NOT NULL | JSON: pre-fetched context |
| `fetched_at` | INTEGER | NOT NULL | Unix timestamp when context was fetched |
| `expires_at` | INTEGER | NOT NULL | Unix timestamp when context expires |

**Indexes:**
- `idx_context_expires` on `expires_at`

**Context Data JSON Schema:**
```json
{
  "kubectl": {...},
  "git": {...},
  "beads": {...}
}
```

---

### 8. `intent_topics`
**Purpose:** Many-to-many relationship between intents and topics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `intent_id` | TEXT | PRIMARY KEY part, FK | Reference to intents.id (ON DELETE CASCADE) |
| `topic_id` | TEXT | PRIMARY KEY part, FK | Reference to topics.id (ON DELETE CASCADE) |

**Notes:**
- Composite primary key: (intent_id, topic_id)
- Allows one intent to be associated with multiple topics

---

### 9. `feedback_signals`
**Purpose:** Implicit user behavior tracking for background analysis.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `signal_id` | TEXT | PRIMARY KEY | Signal UUID |
| `signal_type` | TEXT | NOT NULL | Signal type (e.g., 'ack_speed', 'click', 'scroll') |
| `session_id` | TEXT | NOT NULL, FK | Reference to sessions.id (ON DELETE CASCADE) |
| `result_id` | TEXT | FK | Reference to results.id (ON DELETE SET NULL) |
| `topic_id` | TEXT | FK | Reference to topics.id (ON DELETE SET NULL) |
| `timestamp` | INTEGER | NOT NULL | Unix timestamp when signal occurred |
| `data` | TEXT | NOT NULL | JSON: signal-specific data |
| `surface_type` | TEXT | - | Surface type ('canvas', 'telegram', 'audio') |
| `processed` | INTEGER | CHECK(0,1) | 0 = unprocessed, 1 = processed (default: 0) |
| `processed_at` | INTEGER | - | Unix timestamp when signal was processed |

**Indexes:**
- `idx_signals_session` on `session_id`
- `idx_signals_type` on `signal_type`
- `idx_signals_processed` on `processed`
- `idx_signals_result` on `result_id`

---

### 10. `dispatch_timings`
**Purpose:** Per-stage latency capture for every dispatch (Latency Budget & Instrumentation).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `intent_id` | TEXT | PRIMARY KEY | Intent thread ID (routed_intent.intent_id) |
| `router_ms` | INTEGER | - | Intent router classification time |
| `json_parse_ms` | INTEGER | - | JSON parsing time (router response) |
| `fetch_first_source_ms` | INTEGER | - | Time to first fetch source response |
| `fetch_total_ms` | INTEGER | - | Total fetch execution time |
| `synthesize_first_token_ms` | INTEGER | - | Time to first synthesize token (streaming) |
| `synthesize_total_ms` | INTEGER | - | Total synthesize time |
| `escalate_ms` | INTEGER | - | Escalation time (NULL for hot-path) |
| `sse_emit_ms` | INTEGER | - | SSE broadcast time |
| `stt_ms` | INTEGER | - | Client-reported speech-to-text time |
| `first_render_ms` | INTEGER | - | Client-reported first render time |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when dispatch started |

**Indexes:**
- `idx_dispatch_timings_created` on `created_at`

**Notes:**
- Keyed by intent thread ID (routed_intent.intent_id), NOT intents.id
- Client-reported columns (stt_ms, first_render_ms) are set via `/api/v1/timings` endpoint
- synthesize_first_token_ms is NULL for non-streaming synthesize calls

---

### 11. `bead_watch`
**Purpose:** Circuit breaker tracking for async beads (Plan §10 The Async Path).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `bead_ref` | TEXT | PRIMARY KEY | Bead ID (references intents.bead_ref) |
| `refusal_count` | INTEGER | NOT NULL | Number of REFUSED: comments seen (default: 0) |
| `last_refusal_reason` | TEXT | - | Most recent refusal reason |
| `last_refusal_at` | INTEGER | - | Unix timestamp of most recent refusal |
| `comment_high_water` | INTEGER | NOT NULL | Latest comment index processed (default: -1) |
| `sla_deadline` | INTEGER | NOT NULL | Unix timestamp when SLA expires |
| `sla_flagged_at` | INTEGER | - | Unix timestamp when SLA was flagged (NULL if not flagged) |
| `fenced_at` | INTEGER | - | Unix timestamp when bead was fenced (NULL if not fenced) |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when watch row was created |

**Indexes:**
- `idx_bead_watch_sla_deadline` on `sla_deadline`
- `idx_bead_watch_fenced` on `fenced_at`

**Circuit Breaker Thresholds:**
- Refusal threshold: 3 refusals → fence
- Age threshold: 24 hours without progress → fence

**Default SLA by Intent Type:**
- `task-profile`: 6 hours
- `status`: 30 seconds
- `action`: 30 seconds
- `lookup`: 30 seconds
- `brainstorm`: 30 minutes
- `reminder`: 24 hours

---

### 12. `pending_bead_approvals`
**Purpose:** Beads awaiting user approval before creation (action, self_modification, monitoring_config).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID for this approval request |
| `intent_id` | TEXT | NOT NULL, FK | Reference to intents.id (ON DELETE CASCADE) |
| `session_id` | TEXT | NOT NULL, FK | Reference to sessions.id (ON DELETE CASCADE) |
| `bead_body` | TEXT | NOT NULL | The bead body awaiting approval |
| `bead_type` | TEXT | NOT NULL | Bead type ('action', 'self_modification', 'monitoring_config') |
| `validation_result` | TEXT | NOT NULL | JSON: ValidationResult with approval details |
| `utterance` | TEXT | NOT NULL | Original user utterance |
| `project_slug` | TEXT | - | Optional project slug |
| `topic_id` | TEXT | - | Optional topic ID |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when approval was requested |
| `expires_at` | INTEGER | NOT NULL | Unix timestamp when approval expires |
| `status` | TEXT | NOT NULL, CHECK | One of: 'pending', 'approved', 'rejected' (default: 'pending') |

**Indexes:**
- `idx_pending_approvals_session` on `session_id`
- `idx_pending_approvals_intent` on `intent_id`
- `idx_pending_approvals_status` on `status`
- `idx_pending_approvals_expires` on `expires_at`

---

### 13. `card_cache`
**Purpose:** Pre-rendered HTML for result components (server-side rendering cache).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `result_id` | TEXT | PRIMARY KEY part | Reference to results.id |
| `component_id` | TEXT | PRIMARY KEY part | Component ID that rendered this HTML |
| `layout_bucket` | TEXT | PRIMARY KEY part | Layout bucket used for rendering |
| `rendered_html` | TEXT | NOT NULL | Pre-rendered HTML content |
| `created_at` | INTEGER | NOT NULL | Unix timestamp when cache entry was created |

**Indexes:**
- `idx_card_cache_result_id` on `result_id`

**Notes:**
- Composite primary key: (result_id, component_id, layout_bucket)
- Allows multiple cached variations per result (different layouts)
- Populated after component selection to avoid repeated rendering

---

## Foreign Key Relationships

```
sessions (1) ----< (*) surfaces
sessions (1) ----< (*) utterances
sessions (1) ----< (*) intents
sessions (1) ----< (*) results
sessions (1) ----< (*) topics [ON DELETE SET NULL]
sessions (1) ----< (*) feedback_signals
sessions (1) ----< (*) pending_bead_approvals

surfaces (*) ----> (1) sessions [ON DELETE CASCADE]

utterances (*) ----> (1) sessions [ON DELETE CASCADE]
utterances (1) ----< (*) intents

intents (*) ----> (1) utterances [ON DELETE CASCADE]
intents (*) ----> (1) sessions [ON DELETE CASCADE]
intents (*) ----> (?) topics [ON DELETE SET NULL]
intents (1) ----< (*) results [ON DELETE CASCADE, nullable]
intents (1) ----< (*) intent_topics (M:N) ----> (?) topics [ON DELETE CASCADE]

topics (*) ----> (?) sessions [ON DELETE SET NULL]
topics (1) ----< (*) results [ON DELETE CASCADE]
topics (1) ----< (*) topic_context_cache [ON DELETE CASCADE]
topics (1) ----< (*) intent_topics (M:N) ----> (?) intents [ON DELETE CASCADE]

results (*) ----> (?) intents [ON DELETE CASCADE]
results (*) ----> (1) sessions [ON DELETE CASCADE]
results (*) ----> (1) topics [ON DELETE CASCADE]
results (*) ----> (?) results (self) [ON DELETE SET NULL]
results (1) ----< (*) card_cache
results (1) ----< (*) feedback_signals [ON DELETE SET NULL]

feedback_signals (*) ----> (1) sessions [ON DELETE CASCADE]
feedback_signals (*) ----> (?) results [ON DELETE SET NULL]
feedback_signals (*) ----> (?) topics [ON DELETE SET NULL]

pending_bead_approvals (*) ----> (?) intents [ON DELETE CASCADE]
pending_bead_approvals (*) ----> (1) sessions [ON DELETE CASCADE]
```

---

## Enum/Check Constraints Summary

### surfaces.type
- 'canvas'
- 'telegram'
- 'audio'

### surfaces.state
- 'active'
- 'idle'
- 'disconnected'

### intents.status
- 'pending'
- 'dispatched'
- 'resolved'
- 'cancelled'
- 'stuck'
- 'failed'

### topics.type
- 'project'
- 'research'
- 'personal'
- 'exception'
- 'compound'

### topics.scope
- 'session'
- 'cross-session'
- 'global'

### results.urgency
- 'critical'
- 'high'
- 'normal'
- 'low'

### pending_bead_approvals.status
- 'pending'
- 'approved'
- 'rejected'

---

## Migration History

The database includes additive migrations that run on initialization:

1. **results.result_type** - Added for component selector key
2. **results.card_fallback** - Added to track generic fallback card usage
3. **intents.lookup_kind** - Added for lookup intent specificity
4. **intents.status** - Extended to include 'stuck' and 'failed' (table recreation required)
5. **results.intent_id** - Made nullable for monitoring-originated results (table recreation required)
6. **bead_watch.comment_high_water** - Changed default from 0 to -1 (table recreation required)
7. **sessions.reformulation_count** - Added to track re-formulation attempts
8. **utterances.router_timing_breakdown** - Added for detailed router timing
9. **dispatch_timings.json_parse_ms** - Added for precise JSON parsing timing

---

## Usage Notes

### Concurrency
- WAL mode enabled: `PRAGMA journal_mode=WAL`
- Synchronous mode: `PRAGMA synchronous=NORMAL`
- Allows concurrent reads during writes

### Foreign Keys
- Foreign key constraints are defined but **NOT enforced** by SQLite (PRAGMA foreign_keys is never enabled)
- Cascade/delete behavior is handled explicitly in application code (e.g., `delete_session()`)

### Timestamps
- All timestamps are Unix timestamps (seconds since epoch)
- Stored as INTEGER in SQLite
- Generated via `int(datetime.now().timestamp())` in Python

### IDs
- Most IDs are UUIDs generated via `uuid4()`
- Exception: `intent_id` in `dispatch_timings` references the intent thread ID (routed_intent.intent_id), not necessarily the intents.id

### JSON Columns
- JSON data stored as TEXT
- Application code handles serialization/deserialization
- Common JSON columns: `data`, `router_timing_breakdown`, `project_slugs`, `context_data`, `diff_data`, `validation_result`

---

## Database File

**Location:** `/home/coding/aide-de-camp/data/session.db`
**Size (as of 2026-08-06):** 733 KB

**Connection Method:**
```python
from src.session.store import get_store
store = get_store()  # Uses DEFAULT_DB_PATH or ADC_DB_PATH env var
```

**Environment Variable Override:**
- `ADC_DB_PATH` - Override database path (used by tests for isolation)

---

## Index Summary

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| idx_surfaces_session | surfaces | session_id | Find surfaces by session |
| idx_surfaces_state | surfaces | state | Find surfaces by state |
| idx_utterances_session | utterances | session_id | Find utterances by session |
| idx_intents_session | intents | session_id | Find intents by session |
| idx_intents_topic | intents | topic_id | Find intents by topic |
| idx_intents_status | intents | status | Find intents by status |
| idx_results_session | results | session_id | Find results by session |
| idx_results_topic | results | topic_id | Find results by topic |
| idx_results_created | results | created_at | Order results by creation time |
| idx_results_previous | results | previous_result_id | Diff chain traversal |
| idx_topics_session | topics | session_id | Find topics by session |
| idx_topics_scope | topics | scope | Find topics by scope |
| idx_topics_active | topics | last_active DESC | Order topics by activity |
| idx_context_expires | topic_context_cache | expires_at | Expired cache cleanup |
| idx_signals_session | feedback_signals | session_id | Find signals by session |
| idx_signals_type | feedback_signals | signal_type | Find signals by type |
| idx_signals_processed | feedback_signals | processed | Find unprocessed signals |
| idx_signals_result | feedback_signals | result_id | Find signals by result |
| idx_dispatch_timings_created | dispatch_timings | created_at | Time-windowed queries |
| idx_bead_watch_sla_deadline | bead_watch | sla_deadline | Find beads past SLA |
| idx_bead_watch_fenced | bead_watch | fenced_at | Find fenced beads |
| idx_pending_approvals_session | pending_bead_approvals | session_id | Find approvals by session |
| idx_pending_approvals_intent | pending_bead_approvals | intent_id | Find approvals by intent |
| idx_pending_approvals_status | pending_bead_approvals | status | Find approvals by status |
| idx_pending_approvals_expires | pending_bead_approvals | expires_at | Find expired approvals |
| idx_card_cache_result_id | card_cache | result_id | Find cached cards by result |

---

**End of Documentation**
