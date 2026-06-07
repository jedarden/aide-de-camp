# ADC-WV1: Utterance Fragment Default Confirmation

## Task
Confirm utterance_fragment default at router.py:230

## Findings

### Exact Line (230)
```python
utterance_fragment=intent_data.get('utterance_fragment', utterance),
```

### Default Expression
- Uses `.get('utterance_fragment', utterance)` 
- If `intent_data` lacks `utterance_fragment` key, defaults to `utterance` variable
- `utterance` is the original parameter passed to `classify_utterance()` (line 166)

### TC-FC-020 Code Path Verified
The fallback code path (lines 239-249) when JSON parsing fails also uses:
```python
IntentClassification(
    intent_type=IntentType.STATUS,
    utterance_fragment=utterance,  # Line 245
    confidence=0.5,
    reasoning="Classification failed, defaulting to status",
)
```
This provides consistent defaulting behavior when classification fails entirely.

## Acceptance Criteria
- [x] Exact line confirmed
- [x] Default expression documented
- [x] TC-FC-020 code path verified
