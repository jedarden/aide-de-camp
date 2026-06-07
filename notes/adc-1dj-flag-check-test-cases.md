---
name: adc-1dj-flag-check-test-cases
description: Flag check test case documentation for IntentRouter confidence threshold logic
metadata:
  type: project
  bead_id: adc-1dj
  created: 2026-06-07
---

# Flag Check Test Cases

## Overview

The "flag check" functionality is implemented in `src/intent/router.py` within the `IntentRouter` class. It uses confidence scores from LLM-based intent classification to determine routing behavior:

- **confidence >= 0.9**: Dispatch immediately (high confidence)
- **confidence 0.7-0.9**: Dispatch but flag for possible clarification (medium confidence)
- **confidence < 0.7**: Return `intent_type="clarification"` requiring user input (low confidence)

## Components Under Test

1. **IntentType Enum** (`src/intent/router.py:26-36`)
   - Contains `CLARIFICATION` type for low-confidence intents

2. **IntentClassification** (`src/intent/router.py:40-47`)
   - Contains `confidence: float` field (default 1.0)

3. **IntentRouter.classify_utterance()** (`src/intent/router.py:164-252`)
   - Parses LLM JSON response
   - Handles unknown intent types (defaults to STATUS)
   - Handles JSON decode errors (fallback to STATUS with 0.5 confidence)

4. **IntentRouter.route_utterance()** (`src/intent/router.py:254-289`)
   - Calls classify_utterance
   - Creates RoutedIntent objects

5. **IntentRouter.process_intent()** (`src/intent/router.py:291-311`)
   - Routes task-profile to escalate strand
   - Routes others to fetch + synthesize strands

## Test Scenarios

### Happy Path (High Confidence Dispatch)

#### TC-FC-001: High Confidence (>0.9) Dispatch
- **Description**: Intent with confidence 0.95 should dispatch immediately
- **Input**: `{"intent_type": "status", "confidence": 0.95, "project_slug": "options-pipeline", ...}`
- **Expected**: RoutedIntent created with classification.intent_type = STATUS
- **Assert**: No clarification flag, proceed to fetch/synthesize

#### TC-FC-002: Maximum Confidence (1.0) Dispatch
- **Description**: Intent with confidence 1.0 should dispatch immediately
- **Input**: `{"intent_type": "action", "confidence": 1.0, ...}`
- **Expected**: RoutedIntent created with classification.intent_type = ACTION
- **Assert**: No clarification flag, proceed to fetch/synthesize

#### TC-FC-003: Boundary High (0.9) Dispatch
- **Description**: Intent with confidence exactly 0.9 should dispatch immediately
- **Input**: `{"intent_type": "lookup", "confidence": 0.9, ...}`
- **Expected**: RoutedIntent created with classification.intent_type = LOOKUP
- **Assert**: No clarification flag, proceed to fetch/synthesize

### Flag for Possible Clarification (Medium Confidence)

#### TC-FC-004: Medium Confidence (0.8) Flag
- **Description**: Intent with confidence 0.8 should dispatch but be flagged for clarification
- **Input**: `{"intent_type": "status", "confidence": 0.8, "project_slug": null, ...}`
- **Expected**: RoutedIntent created with classification.intent_type = STATUS, confidence = 0.8
- **Assert**: Intent dispatched but marked for possible clarification
- **Note**: The actual flagging mechanism needs implementation (currently documented but not enforced in code)

#### TC-FC-005: Medium Confidence (0.75) Flag
- **Description**: Intent with confidence 0.75 should dispatch but be flagged
- **Input**: `{"intent_type": "brainstorm", "confidence": 0.75, ...}`
- **Expected**: RoutedIntent created, confidence = 0.75
- **Assert**: Dispatch with flag for clarification

#### TC-FC-006: Boundary Medium (0.7) Flag
- **Description**: Intent with confidence exactly 0.7 should dispatch but be flagged
- **Input**: `{"intent_type": "action", "confidence": 0.7, ...}`
- **Expected**: RoutedIntent created, confidence = 0.7
- **Assert**: Dispatch with flag for clarification

### Explicit Clarification Request (Low Confidence)

#### TC-FC-007: Low Confidence (0.6) Clarification
- **Description**: Intent with confidence 0.6 should return clarification type
- **Input**: `{"intent_type": "clarification", "confidence": 0.6, "utterance_fragment": "check the pods", ...}`
- **Expected**: RoutedIntent with classification.intent_type = CLARIFICATION
- **Assert**: Intent marked as requiring user clarification

#### TC-FC-008: Very Low Confidence (0.3) Clarification
- **Description**: Intent with confidence 0.3 should require clarification
- **Input**: `{"intent_type": "clarification", "confidence": 0.3, ...}`
- **Expected**: RoutedIntent with classification.intent_type = CLARIFICATION
- **Assert**: Intent marked as requiring user clarification

#### TC-FC-009: Zero Confidence Clarification
- **Description**: Intent with confidence 0.0 should require clarification
- **Input**: `{"intent_type": "clarification", "confidence": 0.0, ...}`
- **Expected**: RoutedIntent with classification.intent_type = CLARIFICATION
- **Assert**: Intent marked as requiring user clarification

### Edge Cases

#### TC-FC-010: Missing Confidence Field
- **Description**: JSON response missing confidence field should use default 0.8
- **Input**: `{"intent_type": "status", "project_slug": "test", ...}` (no confidence key)
- **Expected**: Classification created with default confidence = 0.8
- **Assert**: `classification.confidence == 0.8`

#### TC-FC-011: Invalid Confidence String
- **Description**: Confidence as string "high" should be converted to float or fail
- **Input**: `{"intent_type": "status", "confidence": "high", ...}`
- **Expected**: ValueError or successful conversion to float
- **Assert**: Appropriate error handling or conversion

#### TC-FC-012: Negative Confidence
- **Description**: Negative confidence value should be handled
- **Input**: `{"intent_type": "status", "confidence": -0.5, ...}`
- **Expected**: ValueError or clamping to valid range
- **Assert**: Appropriate error handling or normalization

#### TC-FC-013: Over-Unity Confidence (>1.0)
- **Description**: Confidence > 1.0 should be handled
- **Input**: `{"intent_type": "status", "confidence": 1.5, ...}`
- **Expected**: ValueError or clamping to 1.0
- **Assert**: Appropriate error handling or normalization

#### TC-FC-014: Unknown Intent Type
- **Description**: Invalid intent_type should default to STATUS
- **Input**: `{"intent_type": "invalid-type", "confidence": 0.9, ...}`
- **Expected**: Classification with intent_type = STATUS (default fallback)
- **Assert**: classification.intent_type == IntentType.STATUS
- **Note**: Currently logged as warning and defaults to STATUS

#### TC-FC-015: Empty Intent Array
- **Description**: Empty JSON array from LLM should be handled
- **Input**: `[]`
- **Expected**: Empty list of classifications
- **Assert**: `classifications == []`

#### TC-FC-016: Multiple Intents with Mixed Confidence
- **Description**: Multiple intents with varying confidence levels
- **Input**: `[
  {"intent_type": "status", "confidence": 0.95},
  {"intent_type": "action", "confidence": 0.75},
  {"intent_type": "clarification", "confidence": 0.5}
]`
- **Expected**: 3 RoutedIntents with appropriate routing per confidence level
- **Assert**: First dispatches, second flagged, third requires clarification

### Error Conditions

#### TC-FC-017: Malformed JSON Response
- **Description**: Non-JSON response from LLM should trigger fallback
- **Input**: `"This is not JSON"`
- **Expected**: Fallback classification with intent_type = STATUS, confidence = 0.5
- **Assert**: Fallback classification created, error logged

#### TC-FC-018: JSON Decode Error
- **Description**: Invalid JSON structure should trigger fallback
- **Input**: `{"intent_type": "status", "confidence": }` (incomplete JSON)
- **Expected**: Fallback classification with intent_type = STATUS, confidence = 0.5
- **Assert**: Fallback classification created, error logged

#### TC-FC-019: LLM Timeout/Failure
- **Description**: LLM call timeout should raise or handle gracefully
- **Input**: Timeout exception from LLM client
- **Expected**: Exception propagated or fallback classification
- **Assert**: Error logged, appropriate error handling

#### TC-FC-020: Missing Utterance Fragment
- **Description**: Intent without utterance_fragment should use original utterance
- **Input**: `{"intent_type": "status", "confidence": 0.9}` (no utterance_fragment)
- **Expected**: classification.utterance_fragment == original utterance
- **Assert**: Utterance fragment defaults to full utterance

### Task-Profile Routing with Confidence

#### TC-FC-021: Task-Profile with High Confidence
- **Description**: Task-profile intent with high confidence should escalate to bead
- **Input**: `{"intent_type": "task-profile", "confidence": 0.95, ...}`
- **Expected**: Intent escalated to NEEDLE bead
- **Assert**: Escalate handler called, bead created

#### TC-FC-022: Task-Profile with Low Confidence
- **Description**: Task-profile intent with low confidence should still escalate
- **Input**: `{"intent_type": "task-profile", "confidence": 0.5, ...}`
- **Expected**: Intent escalated to NEEDLE bead (task-profiles always escalate)
- **Assert**: Escalate handler called despite low confidence

### Session Context Integration

#### TC-FC-023: Session Context Boosts Confidence
- **Description**: Relevant recent intents should boost confidence
- **Input**: Utterance "how are they?" after recent intent about "pods in options-pipeline"
- **Expected**: Classification with higher confidence due to context
- **Assert**: confidence > baseline without context

#### TC-FC-024: No Session Context (New Session)
- **Description**: New session with no context should handle appropriately
- **Input**: Utterance with no prior intents in session
- **Expected**: Classification based solely on utterance content
- **Assert**: No errors, baseline confidence

### Urgency Tier Integration

#### TC-FC-025: Low Confidence with Critical Urgency
- **Description**: Low confidence intent marked as critical should handle specially
- **Input**: `{"intent_type": "clarification", "confidence": 0.5, "urgency": "critical"}`
- **Expected**: Intent marked for clarification but urgency preserved
- **Assert**: classification.urgency == "critical"

#### TC-FC-026: Missing Urgency Defaults to Normal
- **Description**: Intent without urgency should default to "normal"
- **Input**: `{"intent_type": "status", "confidence": 0.9}` (no urgency)
- **Expected**: classification.urgency == "normal"
- **Assert**: Default urgency applied

### Boundary Values (Comprehensive)

#### TC-FC-027: Float Precision at Boundaries
- **Description**: Test boundary values with float precision
- **Inputs**: confidence = 0.899999, 0.900001, 0.699999, 0.700001
- **Expected**: Correct classification based on threshold logic
- **Assert**: 0.899999 should flag, 0.900001 should dispatch, 0.699999 should clarify, 0.700001 should flag

## Implementation Gaps Identified

1. **No Explicit Flag Field**: The codebase documents the "flag for possible clarification" behavior but does not implement a dedicated `flagged: bool` field on `IntentClassification` or `RoutedIntent`. The flagging behavior appears to be implicit based on confidence value alone.

2. **No Clarification Handler**: While `IntentType.CLARIFICATION` is defined, there is no explicit handler for clarification intents in the router. The code routes to `_fetch_and_synthesize` for non-task-profile intents.

3. **No UI Feedback for Flagged Intents**: The system does not currently surface the "flagged" state to the user surface.

## Recommendations

1. Add explicit `flagged: bool` field to `IntentClassification`
2. Implement clarification intent handler or explicit rejection
3. Add UI indication for flagged intents (e.g., subtle badge showing "low confidence")
4. Consider confidence calibration via feedback loop
5. Add metrics tracking for confidence distribution

## Test Priority

| Priority | Test Cases |
|----------|------------|
| P0 (Critical) | TC-FC-001, TC-FC-004, TC-FC-007, TC-FC-017, TC-FC-018 |
| P1 (High) | TC-FC-002, TC-FC-003, TC-FC-005, TC-FC-006, TC-FC-008, TC-FC-010, TC-FC-014 |
| P2 (Medium) | TC-FC-009, TC-FC-011, TC-FC-012, TC-FC-013, TC-FC-015, TC-FC-016, TC-FC-021 |
| P3 (Low) | TC-FC-019, TC-FC-020, TC-FC-022, TC-FC-023, TC-FC-024, TC-FC-025, TC-FC-026, TC-FC-027 |

## Files to Create

1. `test/test_flag_check.py` - Unit tests for confidence threshold logic
2. `test/integration/test_flag_check_integration.py` - Integration tests with mock LLM
3. `test/fixtures/flag_check_fixtures.py` - Shared test data and fixtures

## References

- Implementation: `src/intent/router.py`
- Intent types: `src/intent/router.py:26-36`
- Classification logic: `src/intent/router.py:164-252`
- Routing logic: `src/intent/router.py:254-311`
