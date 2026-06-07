# adc-5yb: Record utterance_fragment expression at router.py:230

## Task
Read and record the exact utterance_fragment expression from `src/intent/router.py` line 230.

## Finding
The exact source line is:

```python
utterance_fragment=intent_data.get("utterance_fragment", utterance),
```

This is found within the `IntentClassification` constructor, where it sets the `utterance_fragment` field by:
1. First checking if `utterance_fragment` exists in the `intent_data` dictionary
2. Falling back to the `utterance` variable if not present
