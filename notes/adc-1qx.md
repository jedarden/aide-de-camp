# adc-1qx: Locate router.py and identify target line range

## Task Summary
Confirmed existence of `src/intent/router.py` and identified lines 225-235 containing the `IntentClassification` constructor call.

## Findings

**File Path:** `src/intent/router.py` ✓

**Target Lines 225-235:**
- Line 225: blank line
- Lines 226-233: `IntentClassification` constructor instantiation
- Line 234: `classifications.append(classification)`
- Line 235: blank line

### IntentClassification Constructor (lines 226-233)
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

Parameters passed:
- `intent_type`: Parsed from string, defaults to `STATUS` on ValueError
- `project_slug`: Extracted from intent_data dict
- `confidence`: Float, defaults to 0.8
- `utterance_fragment`: Defaults to original utterance if not provided
- `reasoning`: Empty string default
- `urgency`: Defaults to "normal"

## Acceptance Criteria Met
- [x] File path confirmed as `src/intent/router.py`
- [x] Relevant line range 225-235 identified with IntentClassification constructor
