#!/usr/bin/env python3
"""
Final validation test for optimized router prompt.
Tests both single-intent and multi-intent classification.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.intent.router import IntentRouter
from src.session.store import get_store


async def test_router():
    print("="*60)
    print("Final Router Validation Test")
    print("="*60)

    store = get_store()
    router = IntentRouter(store=store)
    router._clear_cache()

    # Test utterances (single and multi-intent)
    test_utterances = [
        ("Check pods in aide-de-camp", "single-intent"),
        ("Deploy the new version of mtl-my-way", "single-intent"),
        ("Check pods in aide-de-camp and deploy new version", "multi-intent"),
        ("Investigate the CI failure and restart the pipeline", "multi-intent"),
        ("Look up the logs and check the config", "multi-intent"),
    ]

    print(f"\nTesting {len(test_utterances)} utterances...\n")

    results = []

    for utterance, test_type in test_utterances:
        try:
            classifications, timing_breakdown = await router.classify_utterance(
                utterance=utterance,
                session_id="test-validation",
                retry_on_malformed=False
            )

            intent_types = [c.intent_type.value for c in classifications]
            latency = timing_breakdown.get("total_ms", 0)

            status = "✅" if len(classifications) > 0 else "❌"
            print(f"{status} '{utterance[:40]}...'")
            print(f"   Type: {test_type}")
            print(f"   Intents: {len(classifications)} - {intent_types}")
            print(f"   Latency: {latency:.0f}ms")

            results.append({
                "utterance": utterance,
                "test_type": test_type,
                "success": len(classifications) > 0,
                "intents_count": len(classifications),
                "intent_types": intent_types,
                "latency_ms": latency
            })

        except Exception as e:
            print(f"❌ '{utterance[:40]}...'")
            print(f"   ERROR: {e}")
            results.append({
                "utterance": utterance,
                "test_type": test_type,
                "success": False,
                "error": str(e)
            })

    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")

    total = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total - successful

    single_intent_results = [r for r in results if r["test_type"] == "single-intent"]
    multi_intent_results = [r for r in results if r["test_type"] == "multi-intent"]

    single_intent_success = sum(1 for r in single_intent_results if r["success"])
    multi_intent_success = sum(1 for r in multi_intent_results if r["success"])

    print(f"\nOverall Results:")
    print(f"  Total: {total}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")

    print(f"\nSingle-Intent Classification:")
    print(f"  {single_intent_success}/{len(single_intent_results)} successful")

    print(f"\nMulti-Intent Classification:")
    print(f"  {multi_intent_success}/{len(multi_intent_results)} successful")

    if multi_intent_results:
        avg_multi_intents = sum(r.get("intents_count", 0) for r in multi_intent_results if r["success"]) / max(len([r for r in multi_intent_results if r["success"]]), 1)
        print(f"  Average intents per utterance: {avg_multi_intents:.1f}")

    # Latency statistics
    latencies = [r.get("latency_ms", 0) for r in results if r.get("latency_ms")]
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        p50_latency = sorted(latencies)[len(latencies) // 2]
        print(f"\nLatency Statistics:")
        print(f"  Average: {avg_latency:.0f}ms")
        print(f"  P50: {p50_latency:.0f}ms")

    print(f"\n{'='*60}")

    if successful == total:
        print("✅ All tests passed!")
    elif successful >= total * 0.8:
        print("⚠️  Most tests passed (80%+)")
    else:
        print("❌ Many tests failed - review prompt")

    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(test_router())
