#!/usr/bin/env python3
"""Test script to verify the /test/classify endpoint works correctly."""
import asyncio
import sys
sys.path.insert(0, '/home/coding/aide-de-camp')

from src.test.router import TestClassificationRequest, test_classify_intent
from src.intent.router import get_router
from src.session.store import get_store


async def main():
    """Test the classify endpoint directly."""
    print("Testing intent classification endpoint...")

    # Test 1: weather query
    print("\n=== Test 1: 'what is the weather' ===")
    request1 = TestClassificationRequest(
        utterance="what is the weather",
        session_id="test-session-1"
    )

    try:
        response1 = await test_classify_intent(request1)
        print(f"✓ Response: {response1.message}")
        print(f"  Classifications: {len(response1.classifications)}")
        for cls in response1.classifications:
            print(f"    - Intent: {cls['intent_type']}, Confidence: {cls['confidence']:.2f}")
            print(f"      Fragment: {cls['utterance_fragment'][:50]}...")
            print(f"      Reasoning: {cls['reasoning'][:80]}...")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: research query
    print("\n=== Test 2: 'tell me about Kubernetes' ===")
    request2 = TestClassificationRequest(
        utterance="tell me about Kubernetes",
        session_id="test-session-2"
    )

    try:
        response2 = await test_classify_intent(request2)
        print(f"✓ Response: {response2.message}")
        print(f"  Classifications: {len(response2.classifications)}")
        for cls in response2.classifications:
            print(f"    - Intent: {cls['intent_type']}, Confidence: {cls['confidence']:.2f}")
            print(f"      Fragment: {cls['utterance_fragment'][:50]}...")
            print(f"      Reasoning: {cls['reasoning'][:80]}...")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: Compare with direct router call
    print("\n=== Test 3: Comparing with direct router call ===")
    router = get_router(get_store())

    try:
        classifications, _ = await router.classify_utterance(
            utterance="what is the weather",
            session_id="test-session-3"
        )
        print(f"✓ Direct router call returned {len(classifications)} classifications")
        for cls in classifications:
            print(f"    - Intent: {cls.intent_type.value}, Confidence: {cls.confidence:.2f}")
    except Exception as e:
        print(f"✗ Error calling router directly: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
