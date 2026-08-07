# Validation Flow Documentation

## Overview

This document traces the complete execution path from validation trigger through validation logic to result handling in the aide-de-camp system. The validation pipeline operates at multiple layers: request validation, intent classification, fetch orchestration, synthesis, and error handling.

---

## 1. Request Validation Flow

### Entry Point: `POST /dispatch` (src/main.py:1022)

```
Client Request → Pydantic Model → Validation → Processing
```

### Validation Sequence

#### 1.1 Pydantic Model Validation (`DispatchRequest`)

**Location:** `src/api/models.py:17-163`

**Validated Fields:**

| Field | Type | Validation | Error Message |
|-------|------|------------|---------------|
| `utterance` | str | Required, non-empty after strip | "utterance must be a non-empty string" |
| `session_id` | str | Required, non-empty after strip | "session_id must be a non-empty string" |
| `surface_id` | str | Required, non-empty after strip | "surface_id must be a non-empty string" |
| `utterance_id` | str | Optional, non-empty if provided | "utterance_id must be a non-empty string if provided" |

**Field Validators:**

```python
@field_validator('utterance')
@classmethod
def utterance_must_be_non_empty(cls, v: str) -> str:
    if not isinstance(v, str):
        raise ValueError('utterance must be a string')
    stripped = v.strip()
    if not stripped:
        raise ValueError('utterance must be a non-empty string')
    return stripped
```

#### 1.2 Exception Handlers

**Location:** `src/main.py:223-295`

**Validation Error Handler:**
- **Trigger:** `RequestValidationError` from Pydantic
- **Response:** HTTP 400 with detailed field-level errors
- **Output Structure:**
  ```json
  {
    "error": "Validation failed",
    "detail": "Request contains invalid or missing fields",
    "errors": [
      {
        "field": "utterance",
        "message": "utterance must be a non-empty string",
        "type": "value_error"
      }
    ],
    "status": 400
  }
  ```

**JSON Decode Error Handler:**
- **Trigger:** Malformed JSON in request body
- **Response:** HTTP 400 with parsing context
- **Output Structure:**
  ```json
  {
    "error": "Invalid JSON",
    "detail": "Malformed JSON: <error message>",
    "line": <line_number>,
    "column": <column_number>,
    "status": 400
  }
  ```

---

## 2. Intent Router Validation Flow

### Location: `src/intent/router.py`

### 2.1 Multi-Layer Classification

```
Utterance → Cache Check → Fast-Path Router → LLM Fallback → Intent Classification
```

#### 2.1.1 Cache Validation

**Location:** `src/intent/router.py:347-355`

**Validation Steps:**
1. Generate SHA256 cache key from utterance + session_id
2. Check cache for existing classification
3. Validate cache entry expiry (TTL: 900 seconds)

**Success Path:**
- Cache hit → Return cached `IntentClassification[]` immediately
- Timing: <5ms p50/p95

**Failure Modes:**
- Cache miss → Continue to fast-path router
- Expired entry → Remove from cache, continue to fast-path

#### 2.1.2 Fast-Path Router

**Location:** `src/intent/router.py:448-513`

**Validation Pattern:**
```python
det_router = get_deterministic_router()
fast_path_result = det_router.route_utterance(utterance)

if fast_path_result.success:
    # Convert to IntentClassification objects
    classifications = [...]
    # Cache the result
    self._cache_classification(utterance, session_id, classifications)
    return classifications, timing_breakdown
```

**Pattern-Based Validation:**
- Regex patterns for common intents (70-80% of requests)
- Keyword matching for action/lookup/status intents
- Project slug extraction

**Coverage:**
- Status intents: pod status, deployment checks
- Action intents: restart, scale, delete operations
- Lookup intents: logs, config, docs queries
- Brainstorm intents: ideation, planning

**Failure Modes:**
- No pattern match → Fall through to LLM fallback
- Pattern ambiguity → LLM fallback

#### 2.1.3 LLM Fallback Validation

**Location:** `src/intent/router.py:549-739`

**Validation Steps:**

**1. Prompt Construction Validation:**
```python
system_prompt = self._build_system_prompt()  # Load from prompts/router.md
user_message = f"Classify this utterance:\n\n{utterance}"
```

**2. ZAI Proxy Call Validation:**
```python
response_data = await client.call_simple(
    system_prompt=system_prompt,
    user_message=user_message,
    model=ModelClass.SONNET.value,
    max_tokens=100,
    temperature=0.0,
    return_timing=True,
)
```

**3. JSON Parse Validation:**
```python
intents_data = parse_llm_response(response, strip_fences=True, expect_json=True)
```

**Error Handling:**

| Error Type | Exception | Handler | Broadcasted Event |
|------------|-----------|---------|-------------------|
| Timeout | `LLMTimeoutError` | `RouterTimeoutError` | `router_unavailable` |
| Quota Exhausted | `LLMRateLimitError` | `RouterQuotaError` | `router_unavailable` |
| Proxy Down | `httpx.HTTPError` | `RouterProxyError` | `router_unavailable` |
| Malformed JSON | `ParseLLMError` | `RouterMalformedError` | `clarification_card` |
| Unknown | `Exception` | `RouterProxyError` | `router_unavailable` |

**Corrective Retry Pattern:**
```python
if retry_on_malformed and retry_count == 0:
    logger.info("Malformed JSON detected, attempting corrective retry...")
    classifications, _ = await self.classify_utterance(
        utterance=utterance,
        session_id=session_id,
        retry_on_malformed=False,  # Prevent infinite retry
    )
    return classifications, _
```

**Output Data Transformation:**
```python
classification = IntentClassification(
    intent_type=IntentType(intent_type_str),  # Enum validation
    project_slug=intent_data.get("project_slug"),
    confidence=float(intent_data.get("confidence", 0.8)),
    utterance_fragment=intent_data.get("utterance_fragment", utterance),
    reasoning=intent_data.get("reasoning", ""),
    urgency=intent_data.get("urgency", "normal"),
    lookup_kind=intent_data.get("lookup_kind") if intent_type == IntentType.LOOKUP else None,
)
```

---

## 3. Fetch Orchestrator Validation Flow

### Location: `src/fetch/orchestrator.py`

### 3.1 Concurrent Fetch Execution

```
FetchRequest → Command Matrix → Concurrent Tasks → Per-Source Timeout → Coverage Tracking
```

#### 3.1.1 Request Validation

**Location:** `src/fetch/orchestrator.py:73-95`

**FetchRequest Structure:**
```python
@dataclass
class FetchRequest:
    intent_id: str
    intent_type: IntentType
    session_id: str
    context: FetchContext
```

**FetchContext Validation:**
```python
@dataclass
class FetchContext:
    project_slug: Optional[str]
    session_id: str
    repo_path: Optional[str]
    ssh_target: Optional[str]
    host_alias: Optional[str]
    cluster: Optional[str]
    namespace: Optional[str]
    app_name: Optional[str]
```

#### 3.1.2 Command Matrix Resolution

**Location:** `src/fetch/orchestrator.py:92-95`

```python
command_specs = get_fetch_commands(request.intent_type)
required_sources = get_required_sources(request.intent_type)
```

**Intent Type → Sources Mapping:**

| Intent Type | Required Sources | Optional Sources |
|-------------|------------------|------------------|
| STATUS | KUBECTL_PODS | GIT_LOG, ARGOCD_APP |
| ACTION | KUBECTL_DEPLOYMENTS | KUBECTL_PODS, EVENTS |
| LOOKUP_LOGS | LOGS | KUBECTL_PODS |
| LOOKUP_CONFIG | COMPONENTS | KUBECTL_DEPLOYMENTS |
| LOOKUP_DOCS | FS_README | FS_EXPLORE |
| BRAINSTORM | BEAD_LIST | FS_HOME, REMINDERS |

#### 3.1.3 Per-Source Timeout Validation

**Location:** `src/fetch/orchestrator.py:116-174`

**Timeout Enforcement:**
```python
async def execute_with_timeout(
    source: FetchSource,
    required: bool,
    timeout: int | float,
    task: asyncio.Task
) -> tuple[FetchSource, bool, SourceResult]:
    try:
        result = await asyncio.wait_for(task, timeout=timeout)
        return source, required, result
    except asyncio.TimeoutError:
        logger.warning(f"Source {source.value} timed out after {timeout}s")
        result = SourceResult(
            source=source,
            status="timeout",
            data={},
            error=f"Timed out after {timeout}s",
            duration_ms=int(timeout * 1000),
        )
        return source, required, result
```

**Timeout Configuration:**
- Kubectl sources: 10 seconds
- Git sources: 8 seconds
- ArgoCD sources: 10 seconds
- Bead sources: 5 seconds
- Log sources: 30 seconds
- Filesystem sources: 5 seconds

#### 3.1.4 Coverage Tracking

**Location:** `src/fetch/orchestrator.py:208-217`

**Coverage Calculation:**
```python
coverage = FetchCoverage(
    total_sources=len(command_specs),
    succeeded=succeeded,
    timed_out=timed_out,
    failed=failed,
    skipped=skipped,
)
```

**Coverage Metrics:**
```python
success_rate = len(succeeded) / total_sources
```

#### 3.1.5 Terminal Failure Detection

**Location:** `src/intent/router.py:1063-1104`

**All Sources Failed:**
```python
if len(succeeded) == 0 and coverage.total_sources > 0:
    logger.error(f"All fetch sources failed for intent {request.intent_id}")
    result.terminal_failure = "all_sources_failed"
```

**Required Sources Failed:**
```python
required_sources_failed = [
    s for s in fetch_result.coverage.failed
    if any(cmd.source == s and cmd.required
           for cmd in get_fetch_commands(fetch_result.intent_type))
]
```

**Error Broadcast:**
```python
await handler.broadcast_all_sources_failed(
    intent_id=routed_intent.intent_id,
    intent_type=classification.intent_type.value,
    session_id=routed_intent.session_id,
    utterance=routed_intent.utterance,
    failed_sources=failed_sources,
)
```

---

## 4. Synthesize Strand Validation Flow

### Location: `src/synthesize/strand.py`

### 4.1 Result Synthesis

```
FetchResult → LLM Synthesis → JSON Parsing → Fallback Result
```

#### 4.1.1 Request Validation

**Location:** `src/synthesize/strand.py:113-140`

**SynthesizeRequest:**
```python
@dataclass
class SynthesizeRequest:
    intent_id: str
    intent_type: IntentType
    utterance: str
    project_slug: Optional[str]
    fetched_context: Optional[FetchResult]
    urgency: str
```

#### 4.1.2 Prompt Construction

**Location:** `src/synthesize/strand.py:127-145`

**Hot-Reload Prompts:**
- `prompts/synthesize.md` → Main synthesis prompt
- `prompts/urgency.md` → Urgency classification rules

**Splicing:**
```python
urgency_prompt = self._load_urgency_prompt()
if urgency_prompt:
    system_prompt = f"{prompt}\n\n## Urgency Classification Rules\n\n{urgency_prompt}"
else:
    system_prompt = prompt
```

#### 4.1.3 LLM Call Validation

**Location:** `src/synthesize/strand.py:153-169`

**Concurrency Protection:**
```python
limiter = get_concurrency_limiter()
async with limiter:
    response = await client.call_simple(
        system_prompt=system_prompt,
        user_message=user_message,
        model=ModelClass.HAIKU.value,  # Faster synthesis
        max_tokens=1024,
        temperature=0.3,
    )
```

#### 4.1.4 JSON Parse Validation (Fallback Pattern)

**Location:** `src/synthesize/strand.py:171-267`

**Parse with Fallback:**
```python
try:
    result_data = parse_llm_response(response)
except ParseLLMError as e:
    logger.error(f"Failed to parse synthesize response: {e}")
    raise json.JSONDecodeError(str(e), doc="", pos=0) from e
```

**Fallback Result:**
```python
except json.JSONDecodeError as e:
    # Synthesize uses fallback result pattern (not corrective retry)
    # Reasoning: Fetch data already obtained — should never be discarded
    return SynthesizeResult(
        intent_id=request.intent_id,
        data={
            "type": "error",
            "error": "Failed to parse synthesis response",
            "parse_error": str(e),
        },
        summary="An error occurred while processing the result.",
        urgency=Urgency.NORMAL,
    )
```

**Degraded-State UX:**
```python
# Broadcast degraded_raw_data event
await handler.broadcast_degraded_raw_data(
    intent_id=routed_intent.intent_id,
    intent_type=classification.intent_type.value,
    session_id=routed_intent.session_id,
    utterance=routed_intent.utterance,
    fetched_context=fetch_result,
    error_reason=str(synth_e),
)
```

#### 4.1.5 Urgency Classification

**Location:** `src/synthesize/strand.py:195-205`

**Urgency Levels:**
```python
class Urgency(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
```

**Validation:**
```python
try:
    urgency = Urgency(urgency_str)
except ValueError:
    urgency = Urgency.NORMAL  # Default fallback
```

---

## 5. Error Handling & Failure Modes

### 5.1 Error Hierarchy

```
Request Errors (400)
├── Validation Errors
│   ├── Missing required fields
│   ├── Empty string after strip
│   └── Invalid field types
└── JSON Decode Errors
    ├── Malformed JSON syntax
    └── Invalid data types

Router Errors (500)
├── Timeout Errors
│   └── LLM call exceeded 8s timeout
├── Quota Errors
│   └── ZAI proxy quota exhausted
├── Proxy Errors
│   └── ZAI proxy unreachable
└── Malformed Errors
    └── JSON parse failed (after retry)

Fetch Errors (500)
├── Terminal Failures
│   └── All sources failed
├── Required Source Failures
│   └── Critical source unavailable
└── Optional Source Failures
    └── Non-critical source unavailable

Synthesize Errors (500)
├── Parse Failures
│   └── Fallback result with raw data
└── Concurrency Limit
    └── Queue until slot available
```

### 5.2 SSE Event Broadcasting

**Degraded State Events:**

| Event | Trigger | Payload |
|-------|---------|---------|
| `clarification_card` | Router malformed JSON | parse_error, raw_output_snippet |
| `router_unavailable` | Router timeout/quota/proxy | error_reason, utterance |
| `all_sources_failed` | All fetch sources failed | failed_sources[] |
| `degraded_raw_data` | Synthesize failed | fetched_context, error_reason |

**Location:** `src/errors/degraded_state.py`

---

## 6. Data Transformation Pipeline

### 6.1 Request → Intent Classification

```
{
  "utterance": "Check pods in aide-de-camp namespace",
  "session_id": "550e8400-...",
  "surface_id": "surface-abc123"
}
↓ (Pydantic Validation)
{
  "utterance": "Check pods in aide-de-camp namespace",  # Stripped
  "session_id": "550e8400-...",
  "surface_id": "surface-abc123",
  "utterance_id": "660e8400-..."  # Auto-generated
}
↓ (Intent Router)
IntentClassification[
  {
    intent_type: STATUS,
    project_slug: "aide-de-camp",
    confidence: 0.95,
    utterance_fragment: "Check pods in aide-de-camp namespace",
    reasoning: "User wants to check pod status",
    urgency: "normal"
  }
]
```

### 6.2 Intent → Fetch Result

```
RoutedIntent {
  intent_id: "770e8400-...",
  classification: IntentClassification{...},
  session_id: "550e8400-...",
  utterance: "Check pods...",
  router_ms: 45,
  json_parse_ms: 2
}
↓ (Fetch Orchestrator)
FetchResult {
  intent_id: "770e8400-...",
  intent_type: STATUS,
  sources: {
    KUBECTL_PODS: SourceResult {
      status: "success",
      data: { "pods": [...], "healthy_count": 3 },
      duration_ms: 120
    },
    ARGOCD_APP: SourceResult {
      status: "success",
      data: { "sync_status": "Synced", "health_status": "Healthy" },
      duration_ms: 95
    },
    GIT_LOG: SourceResult {
      status: "timeout",
      error: "Timed out after 8s",
      duration_ms: 8000
    }
  },
  coverage: FetchCoverage {
    total_sources: 3,
    succeeded: [KUBECTL_PODS, ARGOCD_APP],
    timed_out: [GIT_LOG],
    failed: [],
    skipped: []
  },
  total_duration_ms: 8215,
  caveats: ["GIT_LOG timed out"]
}
```

### 6.3 Fetch → Synthesize → Result

```
FetchResult {...}
↓ (Synthesize Strand)
SynthesizeResult {
  intent_id: "770e8400-...",
  data: {
    "pods": [
      { "name": "pod-1", "phase": "Running", "ready": "1/1" },
      { "name": "pod-2", "phase": "Running", "ready": "1/1" },
      { "name": "pod-3", "phase": "Running", "ready": "1/1" }
    ],
    "summary": "3/3 pods running and healthy",
    "health_status": "Healthy",
    "sync_status": "Synced"
  },
  summary: "All 3 pods in aide-de-camp namespace are running and healthy. ArgoCD reports Synced and Healthy status.",
  urgency: NORMAL,
  coverage: { "total_sources": 3, "succeeded": 2, "timed_out": 1, "failed": 0 },
  caveats: ["GIT_LOG timed out"]
}
↓ (Result Storage + SSE)
Result {
  id: "880e8400-...",
  intent_id: "770e8400-...",
  topic_id: "990e8400-...",
  session_id: "550e8400-...",
  summary: "All 3 pods in aide-de-camp namespace are running and healthy...",
  data: { ... },
  urgency: "normal",
  result_type: "status:aide-de-camp",
  card_fallback: 0
}
↓ (Component Selection & Rendering)
Component Card (fallback if no match)
```

---

## 7. Validation Output Propagation

### 7.1 Timing Breakdown Storage

**Location:** `src/intent/router.py:774-781`

**Router Timing:**
```python
await store.update_utterance_router_timing(utterance_id, timing_breakdown)
```

**Timing Fields:**
```python
timing_breakdown = {
    "cached": bool,
    "fast_path": bool,
    "prompt_construction_ms": float,
    "proxy_call_ms": float,
    "proxy_network_ms": float,
    "proxy_inference_ms": float,
    "json_parse_ms": float,
    "process_ms": float,
    "total_ms": float,
    "intents_count": int,
}
```

### 7.2 Dispatch Timings Recording

**Location:** `src/intent/router.py:943-953`

**Per-Stage Capture:**
```python
timings = DispatchTimings()
timings.record("router_ms", routed_intent.router_ms)
timings.record("json_parse_ms", routed_intent.json_parse_ms)
timings.record("fetch_first_source_ms", ...)
timings.record("fetch_total_ms", ...)
timings.record("synthesize_total_ms", ...)
timings.record("sse_emit_ms", ...)
```

**Persistence:**
```python
await store.record_dispatch_timings(intent_id, **timings.to_fields())
```

### 7.3 Client-Side Reporting

**Endpoint:** `POST /api/v1/timings`

**Client-Reported Timings:**
```python
{
    "intent_id": "...",
    "stt_ms": 312,        # Speech-to-text final transcript
    "first_render_ms": 90 # First card render
}
```

---

## 8. Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Client Request (POST /dispatch)                                │
│  { utterance, session_id, surface_id }                          │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Pydantic Validation (DispatchRequest)                       │
│     ✓ utterance: non-empty string                               │
│     ✓ session_id: non-empty string                              │
│     ✓ surface_id: non-empty string                              │
└────────────────────┬──────────────────────────────────────────┘
                     │ Pass
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Intent Router (classify_utterance)                          │
│     ├─ Cache Check (SHA256 key)                                 │
│     ├─ Fast-Path Router (pattern matching)                      │
│     └─ LLM Fallback (corrective retry on parse error)           │
│  → IntentClassification[]                                       │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Process Intent (process_intent)                             │
│     ├─ Honesty Guards (action/reminder unavailable)             │
│     ├─ Task-Profile → Escalate to Bead                          │
│     └─ Other Intents → Fetch + Synthesize                        │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Fetch Orchestrator (execute_fetch)                           │
│     ├─ Command Matrix Resolution                                 │
│     ├─ Concurrent Source Execution                               │
│     ├─ Per-Source Timeout Enforcement                            │
│     ├─ Coverage Tracking (succeeded/timed_out/failed)           │
│     └─ Terminal Failure Detection (all sources failed)           │
│  → FetchResult                                                   │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Synthesize Strand (synthesize_intent)                       │
│     ├─ LLM Synthesis (Haiku, temp=0.3)                          │
│     ├─ JSON Parse (fallback result pattern)                      │
│     ├─ Urgency Classification                                    │
│     └─ Degraded-State UX (broadcast on failure)                  │
│  → SynthesizeResult                                              │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. Result Storage & Rendering                                   │
│     ├─ Topic Creation/Linking                                   │
│     ├─ Result Persistence (data, summary, urgency)               │
│     ├─ Component Selection (hot-path or fallback)                │
│     ├─ Card Rendering (HTML generation)                          │
│     └─ SSE Broadcast (result_created)                            │
│  → Result Card                                                   │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  7. Client Render (Canvas)                                        │
│     ├─ Card Injection (component or fallback)                    │
│     ├─ Topic Refresh (loadTopics)                                │
│     └─ Client Timing Report (stt_ms, first_render_ms)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. Error Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  ERROR: Request Validation Failed (400)                         │
├─────────────────────────────────────────────────────────────────┤
│  Trigger: Pydantic RequestValidationError                         │
│  Response: { error, detail, errors[], status }                    │
│  Broadcast: None (client-side error)                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ERROR: Router Malformed (500)                                   │
├─────────────────────────────────────────────────────────────────┤
│  Trigger: ParseLLMError after corrective retry                    │
│  Broadcast: clarification_card (parse_error, raw_output)        │
│  Recovery: User provides clarification                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ERROR: Router Timeout/Quota/Proxy (500)                         │
├─────────────────────────────────────────────────────────────────┤
│  Trigger: LLMTimeoutError, LLMRateLimitError, httpx.HTTPError    │
│  Broadcast: router_unavailable (error_reason)                     │
│  Recovery: Retry after delay or proxy restart                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ERROR: All Sources Failed (500)                                 │
├─────────────────────────────────────────────────────────────────┤
│  Trigger: len(succeeded) == 0 && total_sources > 0              │
│  Broadcast: all_sources_failed (failed_sources[])               │
│  Recovery: Fix connectivity or permissions                        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ERROR: Synthesize Parse Failed (500)                            │
├─────────────────────────────────────────────────────────────────┤
│  Trigger: json.JSONDecodeError in parse_llm_response            │
│  Broadcast: degraded_raw_data (fetched_context, error_reason)    │
│  Recovery: Display raw fetch data in fallback card                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. Validation Checklist

### Request Validation
- [x] Utterance is non-empty string (after strip)
- [x] Session ID is non-empty string (after strip)
- [x] Surface ID is non-empty string (after strip)
- [x] Utterance ID (optional) is non-empty if provided
- [x] JSON is well-formed (no parse errors)

### Intent Router Validation
- [x] Cache entry exists and is not expired
- [x] Fast-path pattern matches utterance
- [x] LLM response parses to valid JSON
- [x] Intent type enum is valid
- [x] Lookup kind is provided for lookup intents
- [x] Confidence score is 0.0-1.0

### Fetch Orchestrator Validation
- [x] Intent type maps to valid command matrix
- [x] Project slug resolves to registry entry
- [x] Required sources are available
- [x] Per-source timeout is configured
- [x] At least one source succeeded (terminal failure check)
- [x] Required sources did not fail

### Synthesize Strand Validation
- [x] Fetched context is not empty
- [x] LLM response parses to valid JSON
- [x] Data field is valid JSON object
- [x] Summary field is non-empty string
- [x] Urgency maps to valid enum value
- [x] Fallback result preserves fetch data

### Result Storage Validation
- [x] Intent ID exists in intents table
- [x] Topic ID exists in topics table
- [x] Session ID exists in sessions table
- [x] Result type is set for component lookup
- [x] Card fallback flag is set correctly
- [x] Dispatch timings are recorded

---

## Appendix: Key File Locations

| Component | File | Key Functions |
|-----------|------|---------------|
| Request Validation | `src/api/models.py` | `DispatchRequest`, field validators |
| Exception Handlers | `src/main.py:223-295` | `validation_exception_handler` |
| Intent Router | `src/intent/router.py` | `classify_utterance`, `route_utterance` |
| Deterministic Router | `src/intent/deterministic_router.py` | `route_utterance` (pattern-based) |
| Fetch Orchestrator | `src/fetch/orchestrator.py` | `execute_fetch` |
| Fetch Commands | `src/fetch/commands.py` | `get_fetch_commands`, command matrix |
| Synthesize Strand | `src/synthesize/strand.py` | `synthesize_intent` |
| Session Store | `src/session/store.py` | `create_result`, `record_dispatch_timings` |
| Degraded State Handler | `src/errors/degraded_state.py` | `broadcast_*` methods |
| SSE Broadcaster | `src/sse/broadcaster.py` | `broadcast` |
| Component Library | `src/components/library.py` | Component lookup, rendering |

---

## Document Metadata

- **Created:** 2026-08-07
- **Author:** Generated for bead adc-rtw7bs
- **Scope:** Complete validation flow from trigger to result
- **Coverage:** Request validation, intent routing, fetch orchestration, synthesis, error handling
