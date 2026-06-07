# adc-26js: Utterance Fragment Assignment Location

## Task
Identify utterance_fragment assignment line in router.py lines 225-235.

## Finding

**Line 230** contains the `utterance_fragment` field assignment inside `IntentClassification()`:

```python
utterance_fragment=intent_data.get("utterance_fragment", utterance),
```

## Context

This is within the `IntentClassification` instantiation that spans lines 226-233 in `src/intent/router.py`. The assignment uses `intent_data.get()` with a fallback to the `utterance` variable if the key is not present in the intent_data dictionary.
