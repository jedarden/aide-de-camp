#!/usr/bin/env python3
"""Comprehensive test of the /test/classify endpoint."""
import asyncio
import sys
sys.path.insert(0, '/home/coding/aide-de-camp')

from src.test.router import TestClassificationRequest, test_classify_intent


async def test_utterance(utterance: str, expected_intent_type: str = None):
    """Test a single utterance and verify classification."""
    print(f"\n=== Testing: '{utterance}' ===")
    request = TestClassificationRequest(
        utterance=utterance,
        session_id="test-session"
    )

    try:
        response = await test_classify_intent(request)
        print(f"✓ {response.message}")
        print(f"  Classifications: {len(response.classifications)}")

        for i, cls in enumerate(response.classifications, 1):
            print(f"  [{i}] Intent: {cls['intent_type']}")
            print(f"      Confidence: {cls['confidence']:.2f}")
            print(f"      Project: {cls['project_slug'] or 'none'}")
            print(f"      Urgency: {cls['urgency']}")
            print(f"      Fragment: \"{cls['utterance_fragment'][:60]}...\"")
            print(f"      Reasoning: \"{cls['reasoning'][:80]}...\"")

            # Verify expected intent type if provided
            if expected_intent_type and cls['intent_type'] != expected_intent_type:
                print(f"  ⚠ WARNING: Expected intent_type '{expected_intent_type}', got '{cls['intent_type']}'")
                return False
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run comprehensive tests."""
    print("=" * 70)
    print("COMPREHENSIVE CLASSIFICATION ENDPOINT TEST")
    print("=" * 70)

    tests = [
        ("what is the weather", "lookup"),
        ("tell me about Kubernetes", "lookup"),
        ("how are the pods doing", "status"),
        ("check the options pipeline status", "status"),
        ("deploy the latest version", "action"),
        ("find the recent logs", "lookup"),
        ("let's brainstorm ideas", "brainstorm"),
        ("create a bead for the new feature", "task-profile"),
    ]

    passed = 0
    failed = 0

    for utterance, expected_intent in tests:
        if await test_utterance(utterance, expected_intent):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
