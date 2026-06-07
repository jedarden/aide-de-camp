# Code Construct Analysis: router.py lines 225-235

## Location
File: `/home/coding/aide-de-camp/src/intent/router.py`
Lines: 226-233

## Construct Type
**Object Instantiation** of the `IntentClassification` class.

## Code

```python
classification = IntentClassification(
    intent_type=intent_type,
    project_slug=intent_data.get("project_slug"),
    confidence=float(intent_data.get("confidence", 0.8)),
    utterance_fragment=intent_data.get("utterance_fragment", utterance),
    reasoning=intent_data.get("reasoning", ""),
    urgency=intent_data.get("urgency", "normal"),
)
```

## Key Fields and Parameters

| Field | Source | Default/Fallback |
|-------|--------|------------------|
| `intent_type` | Variable `intent_type` | None (required) |
| `project_slug` | `intent_data.get("project_slug")` | `None` |
| `confidence` | `intent_data.get("confidence", 0.8)` | `0.8` (cast to `float`) |
| `utterance_fragment` | `intent_data.get("utterance_fragment", utterance)` | `utterance` variable |
| `reasoning` | `intent_data.get("reasoning", "")` | `""` (empty string) |
| `urgency` | `intent_data.get("urgency", "normal")` | `"normal"` |

## Context
The instantiated object is appended to a `classifications` list (line 234), suggesting this is part of a batch classification loop processing multiple intents from an utterance.

## Pattern Notes
- Uses Python's dataclass-style instantiation with named parameters
- Defensive extraction from dictionary using `.get()` with sensible defaults
- Type coercion applied (`float()` for confidence)
