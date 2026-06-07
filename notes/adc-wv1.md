# ADC-WV1: Confirm utterance_fragment default at router.py:230

## Verification Summary

Confirmed that `IntentClassification` at router.py:230 is constructed with:
```python
utterance_fragment=intent_data.get('utterance_fragment', utterance),
```

## Details

- **Location:** `src/intent/router.py:230`
- **Function:** `classify_utterance(self, utterance: str, session_id: str)`
- **Default expression:** `intent_data.get('utterance_fragment', utterance)`
- **Fallback behavior:** When LLM response doesn't include 'utterance_fragment' field, defaults to the original `utterance` parameter

## TC-FC-020 Code Path

This test case validates the default fallback behavior when the LLM omits the 'utterance_fragment' field in its response. The code ensures `IntentClassification.utterance_fragment` always has a value, either:
1. The LLM-provided fragment (if present)
2. The full original utterance (if omitted)

## Related Code Context

The IntentClassification dataclass (lines 39-47):
```python
@dataclass
class IntentClassification:
    intent_type: IntentType
    project_slug: str | None = None
    confidence: float = 1.0
    utterance_fragment: str = ""
    reasoning: str = ""
    urgency: str = "normal"
```
