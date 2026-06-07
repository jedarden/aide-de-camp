# IntentClassification Constructor Identification (adc-5pt)

## Location
File: `src/intent/router.py`, lines 226-233

## Constructor Call
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

## Arguments
| Argument | Source | Default |
|----------|--------|---------|
| `intent_type` | `intent_type` variable | None |
| `project_slug` | `intent_data.get("project_slug")` | None |
| `confidence` | `float(intent_data.get("confidence", 0.8))` | 0.8 |
| `utterance_fragment` | `intent_data.get("utterance_fragment", utterance)` | `utterance` |
| `reasoning` | `intent_data.get("reasoning", "")` | "" |
| `urgency` | `intent_data.get("urgency", "normal")` | "normal" |

## Context
This constructor call appears within the `_classify_intent` method, inside a loop processing multiple intent classifications from LLM response. Each `IntentClassification` object is appended to the `classifications` list (line 234).
