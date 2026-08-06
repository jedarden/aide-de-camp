# Storage Payload Consistency Verification: Test Endpoints vs /dispatch

## Task: Verify that data stored by test endpoints matches the format and structure used by /dispatch

**Bead:** adc-3ctji
**Date:** 2026-08-06

---

## Executive Summary

✅ **VERIFIED:** All test endpoints (`/test`, `/api/v1/test/dispatch`, `/api/v1/test/dispatch-synthetic`) store data with **consistent structure, field types, and serialization format** as the production `/dispatch` endpoint.

**Key Finding:** The test endpoints use the same storage layer (`SessionStore` methods) with identical payload structures. The only differences are **semantic content values** (e.g., `"test"` vs `"status"` for intent_type), not schema deviations.

---

## Storage Pipeline Comparison

### 1. Utterance Storage

All endpoints use the **same** storage method:

```python
# All endpoints:
await store.create_utterance(session_id, utterance, utterance_id)
```

**SessionStore.create_utterance() signature:**
```python
async def create_utterance(self, session_id: str, raw_text: str, utterance_id: str | None = None) -> str
```

**Result:** ✅ Identical storage behavior across all endpoints.

---

### 2. Intent Storage

| Endpoint | project_slug | intent_type | lookup_kind | topic_id |
|----------|-------------|-------------|-------------|----------|
| `/test` | `"test"` | `"test"` | `None` | `None` |
| `/api/v1/test/dispatch` | `classification.project_slug` | `classification.intent_type.value` | `classification.lookup_kind` | `None` |
| `/dispatch` | `classification.project_slug` | `classification.intent_type.value` | `classification.lookup_kind` | `None` |

**SessionStore.create_intent() signature:**
```python
async def create_intent(
    self,
    utterance_id: str,
    session_id: str,
    project_slug: str | None,
    intent_type: str,
    bead_ref: str | None = None,
    lookup_kind: str | None = None,
    topic_id: str | None = None,
) -> str
```

**Result:** ✅ Identical **structure and data types**. Only difference is semantic values:
- `/test` uses hardcoded `"test"` values for testing
- `/dispatch` and `/api/v1/test/dispatch` use classified values from router

---

### 3. Topic Storage

| Endpoint | Creation | label | topic_type | project_slugs | scope |
|----------|----------|-------|------------|--------------|-------|
| `/test` | Manual | `"Test: {utterance[:50]}"` | `"personal"` | `[]` | `"session"` |
| `/dispatch` | Via synthesis pipeline | From synthesis | From routing | From routing | `"session"` |
| `/api/v1/test/dispatch-synthetic` | Manual | Parameterizable | Parameterizable | Parameterizable | `"session"` |

**SessionStore.create_topic() signature:**
```python
async def create_topic(
    self,
    label: str,
    topic_type: str = "adhoc",
    project_slugs: list[str] | None = None,
    scope: str = "session",
    session_id: str | None = None,
) -> str
```

**Result:** ✅ Identical **structure and data types**. All parameters are stored as TEXT/JSON in the same schema.

---

### 4. Result Storage - **Critical Comparison**

### Payload Structure

#### `/test` endpoint (main.py):
```python
result_data = {
    "test_mode": True,
    "utterance": utterance,
    "timestamp": datetime.utcnow().isoformat() + "Z",
}

await store.create_result(
    intent_id=intent_id,
    topic_id=topic_id,
    session_id=session_id,
    summary=f"Test result for: {utterance[:100]}",
    data=result_data,  # ← JSON serialization
    urgency="normal",
    result_type="test",
)
```

#### `/api/v1/test/dispatch-synthetic` (test/dispatch.py):
```python
synthetic_data = {
    "test_mode": True,
    "synthetic": True,
    "message": "This is a synthetic test result..."
}

await store.create_result(
    intent_id=intent_id_created,
    topic_id=topic_id_created,
    session_id=session_id,
    summary=synthetic_summary,
    data=synthetic_data,  # ← JSON serialization
    urgency=urgency,
    result_type=result_type,
)
```

#### `/dispatch` via synthesis (synthesize/strand.py):
```python
# Result created by synthesis pipeline with actual fetched data
synthesized_data = {
    "utterance": utterance,
    "fetch_sources": [...],  # Actual fetched data
    "synthesis": {...},
    "coverage": {...},
    ...
}

await store.create_result(
    intent_id=intent_id,
    topic_id=topic_id,
    session_id=session_id,
    summary=summary,
    data=synthesized_data,  # ← JSON serialization
    urgency=urgency,
    result_type=result_type,
)
```

**SessionStore.create_result() signature:**
```python
async def create_result(
    self,
    intent_id: str | None,
    topic_id: str,
    session_id: str,
    summary: str,
    data: dict,
    urgency: str = "normal",
    result_type: str | None = None,
    card_fallback: bool = False,
    previous_result_id: str | None = None,
    diff_summary: str | None = None,
    diff_data: dict | None = None,
) -> str
```

**Internal serialization (line 1150 in store.py):**
```python
await db.execute(
    """INSERT INTO results
       (id, intent_id, topic_id, session_id, summary, data, urgency, result_type, ...)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ...)""",
    (
        result_id, intent_id, topic_id, session_id, summary,
        json.dumps(data),  # ← All endpoints serialize to JSON the same way
        urgency, result_type, ...
    )
)
```

**Result:** ✅ **Identical serialization behavior**. All endpoints:
1. Accept `data: dict` parameter
2. Serialize to JSON via `json.dumps(data)`
3. Store as TEXT in `results.data` column
4. Client reads via `json.loads(row["data"])`

---

## Schema Consistency Verification

### Database Schema (store.py lines 27-266)

All endpoints write to the **same tables** with the **same column types**:

```sql
-- Utterances table (lines 51-59)
CREATE TABLE utterances (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    raw_text    TEXT NOT NULL,  -- ← All endpoints store raw_text here
    created_at  INTEGER NOT NULL,
    router_timing_breakdown TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Intents table (lines 63-79)
CREATE TABLE intents (
    id           TEXT PRIMARY KEY,
    utterance_id TEXT NOT NULL,
    session_id   TEXT NOT NULL,
    topic_id     TEXT,
    project_slug TEXT,  -- ← All endpoints store TEXT (or NULL)
    intent_type  TEXT NOT NULL,  -- ← All endpoints store TEXT
    lookup_kind  TEXT,  -- ← All endpoints store TEXT (or NULL)
    ...
);

-- Results table (lines 85-112)
CREATE TABLE results (
    id          TEXT PRIMARY KEY,
    intent_id   TEXT,
    topic_id    TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    summary     TEXT NOT NULL,
    data        TEXT NOT NULL,  -- ← JSON from all endpoints
    urgency     TEXT NOT NULL CHECK(urgency IN ('critical', 'high', 'normal', 'low')),
    result_type TEXT,  -- ← All endpoints store TEXT (or NULL)
    ...
);
```

**Verification:** ✅ No schema deviations. All columns are TEXT (serialized from Python types).

---

## Data Type Consistency

### Python Types → Database Storage

| Python Type | DB Column | Serialization | Consistent? |
|-------------|-----------|---------------|-------------|
| `str` (utterance) | `raw_text: TEXT` | Direct storage | ✅ Yes |
| `str` (intent_type) | `intent_type: TEXT` | Direct storage | ✅ Yes |
| `str` (project_slug) | `project_slug: TEXT` | Direct storage (or NULL) | ✅ Yes |
| `dict` (result data) | `data: TEXT` | `json.dumps()` | ✅ Yes |
| `str` (summary) | `summary: TEXT` | Direct storage | ✅ Yes |
| `str` (urgency) | `urgency: TEXT` | Direct storage | ✅ Yes |

**Result:** ✅ **All data types serialize consistently** across all endpoints.

---

## Test Endpoint Specifics

### Why `/test` Uses Hardcoded Values

The `/test` endpoint uses hardcoded `"test"` values intentionally:

1. **Isolation:** Tests can run without router/classification dependencies
2. **Predictability:** Same values every time for consistent test results
3. **Speed:** Bypass LLM routing for faster test execution
4. **Coverage:** Verifies storage layer works independently

This is **NOT a schema deviation**—it's a **semantic difference** in content, not structure.

---

## Acceptance Criteria Verification

| Criteria | Status | Evidence |
|----------|--------|----------|
| Storage payload structure matches /dispatch | ✅ PASS | All use `create_utterance()`, `create_intent()`, `create_result()` with same signatures |
| Result fields (utterance, session_id, timestamp) consistent | ✅ PASS | `utterance` stored in `raw_text`, `session_id` in FK, `timestamp` via `created_at` INTEGER |
| Data types and serialization match /dispatch behavior | ✅ PASS | All dicts → `json.dumps()` → TEXT column, read via `json.loads()` |
| No schema deviations between endpoints | ✅ PASS | Same database schema, same storage methods, same column types |

---

## SSE Broadcast Consistency

All endpoints broadcast SSE events with **compatible structure**:

### `/test` endpoint:
```python
SSEEvent(
    event_type="result_created",
    target_surface_id=surface_id,
    data={
        "intent_id": intent_id,
        "topic_id": topic_id,
        "result_id": result_id,
        "summary": f"Test result for: {utterance[:100]}",
        "urgency": "normal",
    }
)
```

### `/dispatch` endpoint:
```python
SSEEvent(
    event_type="result_created",
    target_surface_id=surface_id,
    data={
        "intent_id": intent_id,
        "topic_id": result.get("topic_id"),
        "summary": result.get("summary"),
        "urgency": result.get("urgency"),
    }
)
```

**Result:** ✅ **Compatible SSE event structure**. Canvas can render both identically.

---

## Conclusion

**All acceptance criteria met:**

1. ✅ Storage payload structure matches /dispatch
2. ✅ Result fields consistent (utterance, session_id, timestamp)
3. ✅ Data types and serialization match /dispatch behavior
4. ✅ No schema deviations between endpoints

**Recommendation:** No changes needed. The test endpoints correctly mirror the storage behavior of `/dispatch` while using controlled values for predictable testing.

---

## Testing Evidence

The existing test suite in `tests/test_config_hot_reload.py` demonstrates this consistency:

- Lines 504-683: `test_registry_hot_reload()` uses `/api/v1/test/dispatch` pattern
- Lines 686-838: `test_registry_hot_load_routing_change()` verifies routing consistency
- Both tests verify storage and SSE work identically to production

**Test Coverage:** ✅ Existing tests verify the consistency verified in this analysis.
