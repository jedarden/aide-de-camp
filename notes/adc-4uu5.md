# adc-4uu5: Router.py Lines 225-235 Raw Content

## Task
Read and record the exact text of lines 225-235 from src/intent/router.py

## Raw Content (Lines 225-235)

```
        
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
These lines show the creation of an IntentClassification object with fields:
- intent_type
- project_slug
- confidence (default 0.8)
- utterance_fragment (defaults to original utterance)
- reasoning
- urgency (default "normal")

The classification is then appended to a classifications list.
