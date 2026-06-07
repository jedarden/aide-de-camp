# adc-5jl: router.py lines 225-235 capture

## Task
Read and document lines 225-235 of `src/intent/router.py`.

## Captured Content

```python
# Lines 225-235 of src/intent/router.py

                classification = IntentClassification(
                    intent_type=intent_type,
                    project_slug=intent_data.get("project_slug"),
                    confidence=float(intent_data.get("confidence", 0.8)),
                    utterance_fragment=intent_data.get("utterance_fragment", utterance),
                    reasoning=intent_data.get("reasoning", ""),
                    urgency=intent_data.get("urgency", "normal"),
                )
                classifications.append(classification)
```

## Context
This code creates an `IntentClassification` dataclass instance with fields:
- `intent_type`: The classified intent type
- `project_slug`: Project identifier (optional)
- `confidence`: Float confidence score (defaults to 0.8)
- `utterance_fragment`: Portion of utterance (defaults to full utterance)
- `reasoning`: Explanation string (defaults to empty)
- `urgency`: Urgency level (defaults to "normal")

The classification is then appended to a `classifications` list.
