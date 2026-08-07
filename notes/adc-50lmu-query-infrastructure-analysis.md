# Query Infrastructure and Time Range Pattern Analysis

## Overview
Analysis of the aide-de-camp codebase query construction system and existing time range filtering patterns.

## Query Infrastructure Location

### Core Files
- **`src/fetch/commands.py`** - Defines fetch command matrix, intent types, and data sources
- **`src/fetch/orchestrator.py`** - Implements concurrent fetch execution with streaming support
- **`src/fetch/clusters.py`** - Cluster endpoint resolution for ArgoCD queries

### Key Components

#### 1. IntentType Enum (`src/fetch/commands.py:19-32`)
Defines the types of intents that require fetch operations:
```python
class IntentType(Enum):
    STATUS = "status"
    ACTION = "action"
    BRAINSTORM = "brainstorm"
    LOOKUP = "lookup"
    LOOKUP_LOGS = "lookup:logs"
    LOOKUP_CONFIG = "lookup:config"
    LOOKUP_DOCS = "lookup:docs"
    REMINDER = "reminder"
    SELF_MODIFICATION = "self-modification"
    MONITORING_CONFIG = "monitoring-config"
    TASK_PROFILE = "task-profile"
    STUCK = "stuck"
```

#### 2. FetchSource Enum (`src/fetch/commands.py:35-54`)
Defines available data sources:
```python
class FetchSource(Enum):
    KUBECTL_PODS = "kubectl_pods"
    KUBECTL_DEPLOYMENTS = "kubectl_deployments"
    KUBECTL_WORKFLOWS = "kubectl_workflows"
    ARGOCD_APP = "argocd_app"
    GIT_LOG = "git_log"
    GIT_STATUS = "git_status"
    BEAD_LIST = "bead_list"
    BEAD_DETAILS = "bead_details"
    CI_STATUS = "ci_status"
    COMPONENTS = "components"
    LOGS = "logs"
    EVENTS = "events"
    SESSION_STATE = "session_state"
    TOPIC_CONTEXT = "topic_context"
    REMINDERS = "reminders"
    FS_EXPLORE = "fs_explore"
    FS_README = "fs_readme"
    FS_HOME = "fs_home"
```

#### 3. FetchCommandSpec Dataclass (`src/fetch/commands.py:309-318`)
Defines specification for single fetch commands:
```python
@dataclass
class FetchCommandSpec:
    source: FetchSource
    command_template: str
    timeout_seconds: int = 5
    required: bool = False
    cacheable: bool = True
    timeout_ms: int | None = None  # Optional override from config/fetch.yaml
```

## Query Method Signature and Parameters

### FetchContext Dataclass (`src/fetch/commands.py:648-678`)
Context variables for command template expansion:

```python
@dataclass
class FetchContext:
    project_slug: str | None = None
    namespace: str | None = None
    cluster: str | None = None
    repo_path: str | None = None
    app_name: str | None = None
    deployment: str | None = None
    pod_name: str | None = None
    topic_id: str | None = None
    session_id: str | None = None
    intent_id: str | None = None
    ssh_target: str | None = None
    host_alias: str | None = None
    proxy: str = "http://traefik-ardenone-manager:8001"
    argocd_proxy: str = "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444"
    
    def expand_template(self, template: str) -> str:
        """Expand a command template with context values."""
        result = template
        for key, value in self.__dict__.items():
            if value is not None:
                placeholder = "{" + key + "}"
                result = result.replace(placeholder, str(value))
        return result
```

### Command Template Examples
From `FETCH_COMMAND_MATRIX` in `src/fetch/commands.py`:

```python
# Kubectl pods
FetchCommandSpec(
    source=FetchSource.KUBECTL_PODS,
    command_template="kubectl --server={proxy} get pods -n {namespace} -o json",
    timeout_seconds=5,
)

# ArgoCD app
FetchCommandSpec(
    source=FetchSource.ARGOCD_APP,
    command_template="curl -s {argocd_proxy}/api/v1/applications/{app_name}",
    timeout_seconds=5,
)

# Git log
FetchCommandSpec(
    source=FetchSource.GIT_LOG,
    command_template="git -C {repo_path} log -10 --oneline --pretty=format:'%h|%s|%an|%ar'",
    timeout_seconds=3,
)
```

### Main Entry Points

#### FetchStrand.fetch() (`src/fetch/orchestrator.py:73-256`)
```python
async def fetch(
    self,
    request: FetchRequest,
    on_partial_result: Optional[Callable[[FetchSource, SourceResult], None]] = None,
) -> FetchResult
```

#### execute_fetch() (`src/fetch/orchestrator.py:1081-1096`)
```python
async def execute_fetch(
    request: FetchRequest,
    stream_callback: Optional[StreamCallback] = None,
) -> FetchResult
```

## Existing Time Range Usage Patterns

### 1. 30-Day Filtering Pattern (`filter_workflows_30days.py`)

**Cutoff-based filtering with datetime objects:**
```python
from datetime import datetime, timezone, timedelta

# Define cutoff date
cutoff_date = '2026-07-07'
cutoff_dt = datetime.fromisoformat(cutoff_date).replace(tzinfo=timezone.utc)

# Alternative: 30 days from now
cutoff_date = datetime.now(tz=datetime.now().astimezone().tzinfo) - timedelta(days=30)

# Filter by timestamp
filtered_items = []
for item in all_items:
    metadata = item.get('metadata', {})
    creation_ts = metadata.get('creationTimestamp')
    
    if creation_ts:
        created_dt = parse_timestamp(creation_ts)
        if created_dt >= cutoff_dt:
            filtered_items.append(item)
```

### 2. Time Range JSON Structure (`data/example_query_whisper-stt_30d.json`)

Standard 30-day query output format:
```json
{
  "service": "whisper-stt",
  "time_range": {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
  },
  "error_metrics": { ... },
  "latency_metrics": { ... },
  "query_timestamp": "2026-08-06T19:05:09.255490"
}
```

### 3. Log Fetching with Time Filtering (`fetch_whisper_stt_logs.py`)

**Pattern: Fetch all data, then filter by timestamp:**
```python
# Fetch all data first
all_entries = []
for pod in pods:
    entries = get_pod_logs(namespace, pod_name)
    all_entries.extend(entries)

# Filter to last 30 days
cutoff_date = datetime.now(tz=...) - timedelta(days=30)
filtered_entries = []

for entry in all_entries:
    ts_str = entry.get("timestamp")
    if ts_str:
        ts = datetime.fromisoformat(ts_str)
        if ts >= cutoff_date:
            filtered_entries.append(entry)
```

## Time Range Query Construction Methods

### Method 1: Command-Level Time Range
Not currently implemented in the fetch system, but could be added as context variables:

**Potential enhancement:**
```python
@dataclass
class FetchContext:
    # ... existing fields ...
    time_start: str | None = None  # ISO 8601 timestamp
    time_end: str | None = None    # ISO 8601 timestamp
    days_lookback: int | None = None  # Number of days
    
# Command template with time range
command_template="kubectl --server={proxy} logs -n {namespace} {pod_name} --since-time={time_start}"
```

### Method 2: Post-Processing Time Filter
Current pattern used in existing scripts:

```python
# Fetch all data
data = await fetch_source(context)

# Filter after fetch
cutoff = datetime.now(timezone.utc) - timedelta(days=30)
filtered = [item for item in data if parse_timestamp(item.get('timestamp')) >= cutoff]
```

### Method 3: Application-Level Time Range
Used in metrics calculation scripts:

```python
# Define time range upfront
time_range = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
}

# Pass to all query functions
metrics = calculate_metrics(data, time_range=time_range)
```

## Key Findings

### Infrastructure Strengths
1. **Template-based command system** - Flexible placeholder expansion
2. **Concurrent execution** - All fetch sources run in parallel
3. **Timeout management** - Per-source timeout enforcement
4. **Coverage tracking** - Success/failure/timeout reporting
5. **Streaming callbacks** - Progressive results as sources complete

### Time Range Patterns
1. **30-day standard** - Multiple scripts use 30-day lookback
2. **Cutoff-based filtering** - Most common pattern: `datetime.now() - timedelta(days=30)`
3. **ISO 8601 timestamps** - Standard format for time values
4. **Post-fetch filtering** - Time filtering applied after data retrieval
5. **Structured output** - Time range metadata included in query results

### Missing Time Range Features
1. **No time range context variables** - FetchContext lacks time_start/time_end/days_lookback
2. **No command-level time filtering** - All time filtering done post-fetch
3. **No time range parameter in command templates** - Templates don't support time placeholders
4. **No standardized time range query API** - Each script implements its own time logic

## Recommendations

### For Implementing 30-Day Queries

1. **Add time range context to FetchContext:**
```python
@dataclass
class FetchContext:
    # ... existing fields ...
    time_start: str | None = None
    time_end: str | None = None
    days_lookback: int | None = None
```

2. **Create time range helper function:**
```python
def create_30day_time_range() -> dict:
    """Create standard 30-day time range structure."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": 30
    }
```

3. **Use existing post-fetch pattern:**
```python
# Fetch all data
result = await fetch_strand.fetch(request)

# Filter by time range
filtered = filter_by_time_range(result, time_range)
```

4. **Include time range in output metadata:**
```json
{
  "query_metadata": {
    "time_range": {
      "start": "2026-07-07T00:00:00Z",
      "end": "2026-08-06T23:59:59Z",
      "days": 30
    },
    "query_timestamp": "2026-08-06T19:05:09.255490"
  },
  "data": { ... }
}
```

## Related Files

- `src/fetch/commands.py` - Command matrix and context definitions
- `src/fetch/orchestrator.py` - Fetch execution and streaming
- `filter_workflows_30days.py` - Example of 30-day workflow filtering
- `fetch_whisper_stt_logs.py` - Example of log fetching with time filtering
- `data/example_query_whisper-stt_30d.json` - Example 30-day query output
- `data/example_query_pbx-web_30d.json` - Example 30-day query output
