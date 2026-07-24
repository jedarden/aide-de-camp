#!/usr/bin/env python3
"""
Test script to verify router timing instrumentation.
"""

import asyncio
import sys
sys.path.insert(0, '/home/coding/aide-de-camp')

from src.intent.router import IntentRouter


async def test_router_timing():
    """Test that router timing breakdown includes all required components."""

    router = IntentRouter()

    # Test classification
    test_utterance = "check the status of spaxel"
    session_id = "test-session"

    print(f"Testing utterance: '{test_utterance}'")
    print(f"Session ID: {session_id}")
    print("-" * 60)

    classifications, timing_breakdown = await router.classify_utterance(
        utterance=test_utterance,
        session_id=session_id,
    )

    print("\n=== Router Timing Breakdown ===")
    print(f"Prompt construction:  {timing_breakdown.get('prompt_construction_ms', 'N/A'):.2f} ms" if timing_breakdown.get('prompt_construction_ms') else "Prompt construction:  N/A")
    print(f"Proxy call (total):   {timing_breakdown.get('proxy_call_ms', 'N/A'):.2f} ms" if timing_breakdown.get('proxy_call_ms') else "Proxy call (total):   N/A")
    print(f"  - Network (TTFB):   {timing_breakdown.get('proxy_network_ms', 'N/A'):.2f} ms" if timing_breakdown.get('proxy_network_ms') else "  - Network (TTFB):   N/A")
    print(f"  - Inference only:   {timing_breakdown.get('proxy_inference_ms', 'N/A'):.2f} ms" if timing_breakdown.get('proxy_inference_ms') else "  - Inference only:   N/A")
    print(f"JSON parsing:         {timing_breakdown.get('json_parse_ms', 'N/A'):.2f} ms" if timing_breakdown.get('json_parse_ms') else "JSON parsing:         N/A")
    print(f"Classification proc:  {timing_breakdown.get('process_ms', 'N/A'):.2f} ms" if timing_breakdown.get('process_ms') else "Classification proc:  N/A")
    print(f"Total classification: {timing_breakdown.get('total_ms', 'N/A'):.2f} ms" if timing_breakdown.get('total_ms') else "Total classification: N/A")
    print(f"Intents classified:   {timing_breakdown.get('intents_count', 'N/A')}" if timing_breakdown.get('intents_count') is not None else "Intents classified:   N/A")

    print("\n=== Verification ===")

    # Verify all required timing components are present
    required_fields = [
        'prompt_construction_ms',
        'proxy_call_ms',
        'proxy_network_ms',
        'proxy_inference_ms',
        'json_parse_ms',
        'process_ms',
        'total_ms',
        'intents_count'
    ]

    missing_fields = []
    for field in required_fields:
        if field not in timing_breakdown or timing_breakdown[field] is None:
            missing_fields.append(field)

    if missing_fields:
        print(f"❌ MISSING timing fields: {', '.join(missing_fields)}")
        return False
    else:
        print("✅ All required timing components are present")

    # Verify timing relationships
    proxy_call = timing_breakdown.get('proxy_call_ms', 0)
    network = timing_breakdown.get('proxy_network_ms', 0)
    inference = timing_breakdown.get('proxy_inference_ms', 0)

    if abs(proxy_call - (network + inference)) < 1:  # Allow 1ms rounding error
        print("✅ Timing relationship verified: proxy_call ≈ network + inference")
    else:
        print(f"⚠️  Timing mismatch: proxy_call({proxy_call:.2f}) ≠ network({network:.2f}) + inference({inference:.2f})")

    print("\n=== Classification Results ===")
    for i, classification in enumerate(classifications):
        print(f"Intent {i+1}:")
        print(f"  Type: {classification.intent_type.value}")
        print(f"  Project: {classification.project_slug or 'N/A'}")
        print(f"  Confidence: {classification.confidence}")

    return True


if __name__ == "__main__":
    success = asyncio.run(test_router_timing())
    sys.exit(0 if success else 1)
