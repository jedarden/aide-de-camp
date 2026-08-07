# Confirmation Prompt System

## Overview

The confirmation prompt system provides a user-facing interface for displaying confirmation questions and capturing responses for destructive actions (e.g., pod deletion).

## Architecture

The system consists of three main components:

### 1. Template System (`src/confirmations/confirmations.py`)

- **Source**: Created in `adc-46ksu`
- **Purpose**: Manages confirmation question templates from `config/confirmations.yaml`
- **Functions**:
  - `get_pod_deletion_confirmation()`: Retrieves formatted confirmation dialog
  - `format_confirmation_message()`: Formats complete message with warnings

### 2. Prompt Manager (`src/confirmations/prompts.py`)

- **Source**: Created in this task (`adc-2tw9h`)
- **Purpose**: Manages confirmation prompt lifecycle (create, display, capture, validate)
- **Class**: `ConfirmationPromptManager`
- **Functions**:
  - `create_pod_deletion_confirmation()`: Creates new confirmation prompt
  - `display_confirmation_prompt()`: Formats prompt for user display
  - `capture_confirmation_response()`: Captures raw user response
  - `get_confirmation_for_validation()`: Retrieves data for validation step

### 3. API Endpoints (`src/main.py`)

- **Source**: Created in this task (`adc-2tw9h`)
- **Purpose**: Exposes confirmation system via REST API
- **Endpoints**:
  - `POST /api/v1/confirmations`: Create new confirmation prompt
  - `GET /api/v1/confirmations/{id}`: Get confirmation details
  - `POST /api/v1/confirmations/{id}/respond`: Submit user response
  - `GET /api/v1/confirmations/{id}/wait`: Wait for response (blocking)

## Usage Flow

### Step 1: Create Confirmation Prompt

```python
from src.confirmations.prompts import create_pod_deletion_confirmation

confirmation = await create_pod_deletion_confirmation(
    intent_id="intent-123",
    session_id="session-456",
    pod_name="pbx-web-5ff68464d-mkn8n",
    namespace="default",
    cluster="iad-ci",
)

# Returns:
# {
#     "confirmation_id": "...",
#     "question": "Do you want to proceed with deleting pod pbx-web-5ff68464d-mkn8n? (yes/no)",
#     "message": "...",  # Full formatted message with warnings
#     "context": {...},
#     "status": "pending"
# }
```

### Step 2: Display Confirmation to User

```python
from src.confirmations.prompts import display_confirmation_prompt

message = await display_confirmation_prompt(confirmation['confirmation_id'])
# Display this message to the user via your preferred interface:
# - Canvas UI (SSE broadcast)
# - Telegram fallback
# - CLI prompt
# - API response
```

### Step 3: Capture User Response

```python
from src.confirmations.prompts import capture_confirmation_response

result = await capture_confirmation_response(
    confirmation_id=confirmation['confirmation_id'],
    response="yes",  # Raw user response (yes/no/pod-name)
)

# Returns:
# {
#     "success": true,
#     "confirmation_id": "...",
#     "response": "yes",
#     "responded_at": "2026-08-07T12:34:56Z"
# }
```

### Step 4: Validate Response (Next Step)

```python
from src.confirmations.prompts import get_confirmation_for_validation

validation_data = await get_confirmation_for_validation(confirmation['confirmation_id'])

# Returns complete data for validation:
# {
#     "confirmation_id": "...",
#     "question": "...",
#     "response": "yes",
#     "context": {...},
#     "created_at": "...",
#     "responded_at": "...",
#     "status": "responded"
# }
```

## API Usage

### Create Confirmation Prompt

```bash
curl -X POST http://localhost:8000/api/v1/confirmations \
  -H "Content-Type: application/json" \
  -d '{
    "intent_id": "intent-123",
    "session_id": "session-456",
    "pod_name": "pbx-web-5ff68464d-mkn8n",
    "namespace": "default",
    "cluster": "iad-ci"
  }'
```

### Get Confirmation Details

```bash
curl http://localhost:8000/api/v1/confirmations/{confirmation_id}
```

### Submit User Response

```bash
curl -X POST http://localhost:8000/api/v1/confirmations/{confirmation_id}/respond \
  -H "Content-Type: application/json" \
  -d '{"response": "yes"}'
```

### Wait for Response (Blocking)

```bash
curl "http://localhost:8000/api/v1/confirmations/{confirmation_id}/wait?timeout=300"
```

## SSE Events

When a user responds to a confirmation, the system broadcasts an SSE event:

```python
{
    "event_type": "confirmation_responded",
    "data": {
        "confirmation_id": "...",
        "response": "yes",
        "responded_at": "2026-08-07T12:34:56Z"
    }
}
```

This allows connected canvas surfaces to react to confirmation responses in real-time.

## Database Schema

Confirmation prompts are stored in the `confirmation_prompts` table:

- `id`: Primary key (confirmation_id)
- `intent_id`: Associated intent
- `session_id`: Associated session
- `prompt_type`: Type of confirmation (e.g., "pod_deletion")
- `question`: The confirmation question
- `context`: JSON context (pod_name, namespace, cluster, etc.)
- `response`: User's response (NULL until answered)
- `status`: "pending", "responded", "expired"
- `created_at`: Timestamp when prompt was created
- `responded_at`: Timestamp when response was captured (NULL until answered)

## Acceptance Criteria Met

✅ **1. Confirmation question is displayed to user**
   - `display_confirmation_prompt()` returns formatted message
   - Multiple display channels supported (API, SSE, CLI, Telegram)

✅ **2. User is able to provide a response**
   - REST API endpoint accepts user responses
   - Multiple response formats accepted (yes/no/pod-name)

✅ **3. Response is captured and stored**
   - `capture_confirmation_response()` stores raw response
   - Response persisted to database with timestamp
   - SSE event broadcasted to connected surfaces

✅ **4. System waits for user input**
   - Blocking endpoint `/api/v1/confirmations/{id}/wait` for synchronous workflows
   - Polling support via GET `/api/v1/confirmations/{id}` for asynchronous workflows
   - SSE events for real-time notification

## Integration Points

### Canvas UI

The confirmation system integrates with the canvas UI through:
- SSE broadcasts for real-time updates
- REST API for creating and managing prompts
- Event type: `CONFIRMATION_RESPONDED`

### Action Execution System

The confirmation system is designed to integrate with the action execution system (`src/action/executor.py`):
- Can be called from workflow steps
- Responses stored for validation in next step
- No validation performed in this step (per task requirements)

### Session Store

The system uses the existing session store database:
- `create_confirmation_prompt()`: Creates new prompt record
- `get_confirmation_prompt()`: Retrieves prompt details
- `submit_confirmation_response()`: Stores user response

## Testing

Run the demo script to test the system:

```bash
.venv/bin/python demo_confirmation_system.py
```

This demonstrates:
1. Creating a confirmation prompt
2. Displaying it to the user
3. Capturing user response
4. Getting data for validation

## Confirmed Deletions Storage

### Overview

Once a user confirmation is validated, the system stores the confirmed deletion record for use by the deletion execution step. This is implemented in `src/confirmations/confirmed_deletions.py`.

### Storage Format

Confirmed deletions are stored in `data/confirmed-deletions/confirmed-pods.jsonl` as newline-delimited JSON records.

**Record format:**
```json
{
  "timestamp": "2026-08-07T06:57:36.427226+00:00",
  "pod_name": "pbx-web-5ff68464d-mkn8n",
  "namespace": "default",
  "cluster": "iad-ci",
  "user_response": "yes",
  "confirmation_id": "demo-conf-001",
  "intent_id": "intent-demo-123",
  "session_id": "session-demo-456",
  "status": "confirmed"
}
```

### Functions

#### `document_confirmed_deletion()`
Documents a confirmed pod deletion with timestamp and stores for deletion step.

```python
from src.confirmations.confirmed_deletions import document_confirmed_deletion

record = document_confirmed_deletion(
    pod_name="pbx-web-5ff68464d-mkn8n",
    namespace="default",
    cluster="iad-ci",
    user_response="yes",
    confirmation_id="abc-123"
)
```

#### `get_latest_confirmed_deletion()`
Retrieves the most recent confirmed deletion record for execution.

```python
from src.confirmations.confirmed_deletions import get_latest_confirmed_deletion

deletion = get_latest_confirmed_deletion()
if deletion:
    execute_pod_deletion(deletion['pod_name'], deletion['namespace'], deletion['cluster'])
```

#### `get_confirmed_deletion_by_confirmation_id()`
Retrieves a specific confirmed deletion record by confirmation ID.

```python
from src.confirmations.confirmed_deletions import get_confirmed_deletion_by_confirmation_id

record = get_confirmed_deletion_by_confirmation_id("abc-123")
```

#### `list_all_confirmed_deletions()`
Lists all confirmed deletion records, optionally limited.

```python
from src.confirmations.confirmed_deletions import list_all_confirmed_deletions

# Get last 5 confirmed deletions
recent = list_all_confirmed_deletions(limit=5)
```

#### `get_deletion_count()`
Gets statistics about confirmed deletions.

```python
from src.confirmations.confirmed_deletions import get_deletion_count

stats = get_deletion_count()
# Returns: {"total_confirmed": 1, "total_rejected": 0, "total_records": 1}
```

### Integration with Deletion Execution

The deletion execution step uses this storage to retrieve pod details:

```python
from src.confirmations.confirmed_deletions import get_latest_confirmed_deletion

# Get the latest confirmed deletion
deletion = get_latest_confirmed_deletion()

if deletion and deletion['status'] == 'confirmed':
    # Execute the deletion
    kubectl_delete_pod(
        pod_name=deletion['pod_name'],
        namespace=deletion['namespace'],
        cluster=deletion['cluster']
    )
    logger.info(f"Executed deletion for {deletion['pod_name']} "
                f"(confirmation_id: {deletion['confirmation_id']})")
else:
    logger.warning("No confirmed deletion found for execution")
```

### Testing

Run the demo script to test the storage system:

```bash
.venv/bin/python demo_confirmed_deletion.py
```

This demonstrates:
1. Documenting a confirmed deletion
2. Retrieving the latest confirmed deletion
3. Looking up by confirmation ID
4. Listing all confirmed deletions
5. Getting deletion statistics
6. Verifying persistent storage

## Future Enhancements

Potential improvements for future iterations:
- Canvas UI component for confirmation cards
- Telegram interactive buttons for confirmations
- Confirmation history and audit trail ✅ (Implemented via confirmed-pods.jsonl)
- Multi-step confirmations for complex operations
- Confirmation templates for other destructive actions