# ADC-43rx: utterance_fragment Default Value Documentation

## Task
Document the utterance_fragment default value at router.py:230

## Finding
From src/intent/router.py line 230, the utterance_fragment field uses:

```python
utterance_fragment=intent_data.get("utterance_fragment", utterance),
```

**Default value expression:** `utterance`

## Context
- Line 230 is within the IntentClassification object instantiation (lines 226-233)
- The field retrieves "utterance_fragment" from the `intent_data` dictionary
- If the key is not present in `intent_data`, it defaults to the `utterance` variable (which is the full user utterance passed to this function)
- This pattern ensures the classification always has a fragment of the utterance to work with, even if the LLM response doesn't explicitly break out a fragment

## Code Context (lines 225-235)
```python
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

## Acceptance Criteria Met
✅ The exact default value expression for utterance_fragment is documented: `utterance`
