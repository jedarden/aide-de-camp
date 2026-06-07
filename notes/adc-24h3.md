# Code Construct Analysis: router.py lines 225-235

## Task
Identify the code construct at router.py lines 225-235.

## Location
File: `/home/coding/aide-de-camp/src/intent/router.py`
Lines: 225-235

## Construct Type
**Object Instantiation** (dataclass instance creation)

## Detailed Analysis

### Line 224
```python
intent_type = IntentType.STATUS
```
- Variable assignment with enum value fallback
- This is a fallback case when an unknown intent type is encountered

### Lines 226-233 (Primary Construct)
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

This is **instantiation of a dataclass** (`IntentClassification`) using keyword arguments.

### Line 234
```python
classifications.append(classification)
```
- List method call appending the newly created object

## IntentClassification Dataclass Fields

Based on the instantiation, the `IntentClassification` dataclass has the following fields:

| Field | Type | Description | Default/Source |
|-------|------|-------------|----------------|
| `intent_type` | `IntentType` (Enum) | The classified intent type | From variable (enum) |
| `project_slug` | `str \| None` | Optional project identifier | From `intent_data` dict |
| `confidence` | `float` | Classification confidence score (0.0-1.0) | From `intent_data`, defaults to 0.8 |
| `utterance_fragment` | `str` | The specific fragment of the utterance | From `intent_data`, defaults to full `utterance` |
| `reasoning` | `str` | Explanation of classification | From `intent_data`, defaults to empty string |
| `urgency` | `str` | Urgency tier ("critical", "high", "normal", "low") | From `intent_data`, defaults to "normal" |

## Context
This code is inside the `classify_utterance` method of the `IntentRouter` class, which processes LLM responses to classify user intents. The instantiation creates `IntentClassification` objects from parsed JSON data returned by the LLM.
