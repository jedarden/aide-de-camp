# ADC-5JL: Router.py Lines 225-235 Capture

## Task
Capture lines 225-235 of src/intent/router.py

## Lines Captured (225-235)

```python
                # Line 225 is blank
                classification = IntentClassification(
                    intent_type=intent_type,
                    project_slug=intent_data.get("project_slug"),
                    confidence=float(intent_data.get("confidence", 0.8)),
                    utterance_fragment=intent_data.get("utterance_fragment", utterance),
                    reasoning=intent_data.get("reasoning", ""),
                    urgency=intent_data.get("urgency", "normal"),
                )
                classifications.append(classification)
                # Line 235 is blank
```

## Context
This code appears within the `_classify_intent_internal` method, inside the loop that processes multiple intent classifications returned by the LLM. The code constructs an `IntentClassification` dataclass from parsed intent data and adds it to a list.

## Surrounding Code (220-240)
```python
                try:
                    intent_type = IntentType(intent_type_str)
                except ValueError:
                    logger.warning(f"Unknown intent type: {intent_type_str}")
                    intent_type = IntentType.STATUS

                classification = IntentClassification(
                    intent_type=intent_type,
                    project_slug=intent_data.get("project_slug"),
                    confidence=float(intent_data.get("confidence", 0.8)),
                    utterance_fragment=intent_data.get("utterance_fragment", utterance),
                    reasoning=intent_data.get("reasoning", ""),
                    urgency=intent_data.get("urgency", "normal"),
                )
                classifications.append(classification)

            logger.info(f"Classified {len(classifications)} intents from utterance")
            return classifications
```
