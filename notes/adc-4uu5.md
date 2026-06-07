# Raw Content: src/intent/router.py lines 225-235

Task: Record exact line text for lines 225-235 without modification.

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

Captured: 2025-01-07
Bead: adc-4uu5
