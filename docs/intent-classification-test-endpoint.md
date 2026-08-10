# Intent classification test endpoint

`/test/intent-classify` is a lightweight, text-only endpoint for checking the
intent router. It bypasses microphone, Web Speech API, WebSocket, fetch, and
synthesis work; it only classifies the supplied utterance.

## Route

The handler route is:

```text
POST /test/intent-classify
```

In the current `src.main` application, the test router is mounted under
`/api/v1/test`. Because the handler already includes the `/test` segment, the
full URL registered by this checkout is:

```text
POST /api/v1/test/test/intent-classify
```

Use the full URL below when running the server from this repository. The
registered path can also be confirmed at `GET /openapi.json`. Older test
scripts may show `/api/v1/test/intent-classify`; that path is not registered by
the current application mount.

## Request

Send JSON with one required field, `utterance`:

```json
{
  "utterance": "how are the pods doing"
}
```

This endpoint does not accept `session_id`; classification uses the fixed
internal test session. A missing or non-string `utterance` returns `400` from
the application's validation handler.

### curl examples

Set the server address once, then call the endpoint:

```bash
BASE_URL="${ADC_SERVER_URL:-http://localhost:8000}"
CLASSIFY_URL="$BASE_URL/api/v1/test/test/intent-classify"

curl --fail-with-body -sS "$CLASSIFY_URL" \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{"utterance":"how are the pods doing"}' | jq .
```

Classify a lookup request without running the full dispatch pipeline:

```bash
curl --fail-with-body -sS "$CLASSIFY_URL" \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{"utterance":"find the recent logs for the nap-api container"}' | jq .
```

## Response format

A successful response contains the original utterance, one or more
classification objects, and a summary message:

```json
{
  "utterance": "how are the pods doing",
  "classifications": [
    {
      "intent_type": "status",
      "project_slug": null,
      "confidence": 0.94,
      "utterance_fragment": "how are the pods doing",
      "reasoning": "The utterance asks for current system status.",
      "urgency": "normal"
    }
  ],
  "message": "Classified into 1 intent(s)"
}
```

The following fields are returned for every classification:

| Field | Meaning |
| --- | --- |
| `intent_type` | The routed type, such as `status`, `action`, `lookup`, `brainstorm`, `reminder`, `monitoring-config`, `task-profile`, or `clarification`. |
| `project_slug` | Matched project identifier, or `null` when no project is identified. |
| `confidence` | Classifier confidence from `0.0` to `1.0`. |
| `utterance_fragment` | Portion of the utterance represented by this classification. |
| `reasoning` | Short explanation from the classifier. |
| `urgency` | `critical`, `high`, `normal`, or `low`. |

Lookup classifications may also contain `lookup_kind`, whose value is
`logs`, `config`, or `docs`:

```json
{
  "utterance": "find the recent logs for the nap-api container",
  "classifications": [
    {
      "intent_type": "lookup",
      "project_slug": "iad-native-ads",
      "confidence": 0.91,
      "utterance_fragment": "find the recent logs for the nap-api container",
      "reasoning": "The user is asking to inspect container logs.",
      "urgency": "normal",
      "lookup_kind": "logs"
    }
  ],
  "message": "Classified into 1 intent(s)"
}
```

Confidence and reasoning are generated values, so they can vary between
requests. For regression checks, compare `intent_type`, `project_slug`, and
the number of returned classifications. A compound utterance can produce
multiple objects in `classifications`.

## Available smoke-test utterances

These are the maintained pre-canned cases in the test suite. The expected
classification is the first intent type returned unless noted otherwise.

| Name | Utterance | Expected `intent_type` | Expected `project_slug` |
| --- | --- | --- | --- |
| `status_query` | `how are the pods doing` | `status` | — |
| `project_status` | `check the options pipeline status` | `status` | `options-pipeline` |
| `action_request` | `deploy the latest version of nap-api` | `action` | `iad-native-ads` |
| `lookup_request` | `find the recent logs for the nap-api container` | `lookup` | `iad-native-ads` |
| `weather_query` | `what is the weather` | `lookup` | — |
| `research_query` | `tell me about Kubernetes architecture patterns` | `lookup` | — |
| `brainstorm` | `let's brainstorm ways to optimize the pipeline performance` | `brainstorm` | — |
| `task_profile` | `create a bead for implementing the new monitoring feature` | `task-profile` | — |
| `multi_intent` | `how's the pipeline and also check the ibkr mcp status` | Usually multiple `status` classifications | — |

`weather` is not a valid `intent_type`; weather and general research questions
are represented as `lookup`. The multi-intent case is intentionally allowed to
return more than one classification, one for each detected fragment.

To try another utterance, replace the string in the JSON body; no fixture name
or session setup is required.
