#!/usr/bin/env python3
"""
Test multi-intent classification with optimized prompts.
Measures token count reduction and accuracy preservation.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.intent.router import IntentRouter
from src.session.store import get_store


def count_tokens(text: str) -> int:
    """Estimate token count: ~1 token per 4 characters."""
    import re
    text = re.sub(r'\s+', ' ', text).strip()
    return len(text) // 4


# Current prompt (from router.md)
CURRENT_PROMPT = """# Intent Router
Classify utterances. Return JSON array.

Types:
- status: Query state
- action: Execute commands
- brainstorm: Explore options
- lookup: Find info (lookup_kind: logs|config|docs)
- reminder: Time-based tasks
- task-profile: Multi-step work

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Different type/project/target → separate intents. Map projects by name."""

# Ultra-optimized prompt (target: 35-40% reduction)
ULTRA_PROMPT = """# Intent Router
Classify utterances. Return JSON array.

Types: status/state | action/execute | brainstorm/explore | lookup/find | reminder/time | task-profile/multi-step

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Split by type/project. Map projects by name."""

# Extreme-optimized prompt (target: 45-50% reduction)
EXTREME_PROMPT = """# Intent Router
Classify utterances. Return JSON array.

Types: status|action|brainstorm|lookup|reminder|task-profile

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Split by type/project."""


# Sample multi-intent utterances for accuracy testing
TEST_UTTERANCES = [
    "Check pods in aide-de-camp and deploy the new version",
    "Investigate the CI failure for spaxel and restart the pipeline",
    "Look up the logs for ardenone-cluster and check if the beads are working",
    "Deploy the new version of mtl-my-way and set up a reminder to check it tomorrow",
    "Brainstorm options for the new feature and create a task profile for implementation",
    "Check the status of the kalshi-tape deployment and look up the config for iad-options",
    "What's the status of the aide-de-camp router and can we optimize it?",
    "Deploy clasp and vista, then set a reminder to check them",
    "Investigate why the proxy is slow and brainstorm optimization strategies",
    "Check pods in ardenone-cluster and lookup docs for connection pooling",
]


async def test_prompt_accuracy(prompt_name: str, prompt_text: str, utterances: list[str]) -> dict:
    """Test classification accuracy with a given prompt."""
    print(f"\n{'='*60}")
    print(f"Testing: {prompt_name}")
    print(f"{'='*60}")

    # Temporarily replace router.md
    router_md_path = Path("/home/coding/aide-de-camp/prompts/router.md")
    backup_path = router_md_path.with_suffix(".md.backup")

    # Backup current prompt
    original_content = router_md_path.read_text()
    backup_path.write_text(original_content)

    # Write test prompt
    router_md_path.write_text(prompt_text)

    try:
        # Create router (it will load the new prompt)
        store = get_store()
        router = IntentRouter(store=store)
        router._clear_cache()  # Clear cache for fair testing

        results = []
        timings = []

        for utterance in utterances:
            try:
                start = time.perf_counter()
                classifications, timing_breakdown = await router.classify_utterance(
                    utterance=utterance,
                    session_id="test-session",
                    retry_on_malformed=False
                )
                elapsed = (time.perf_counter() - start) * 1000

                timings.append(elapsed)

                # Count how many intents were found (multi-intent detection)
                results.append({
                    "utterance": utterance,
                    "intents_count": len(classifications),
                    "classifications": [c.intent_type.value for c in classifications],
                    "timing_ms": elapsed
                })

                print(f"✓ '{utterance[:50]}...'")
                print(f"  → {len(classifications)} intents: {[c.intent_type.value for c in classifications]}")
                print(f"  → {elapsed:.0f}ms")

            except Exception as e:
                print(f"✗ '{utterance[:50]}...' → ERROR: {e}")
                results.append({
                    "utterance": utterance,
                    "error": str(e),
                    "intents_count": 0
                })

        # Calculate statistics
        valid_timings = [t for r in results for t in [r.get("timing_ms")] if t is not None]
        if valid_timings:
            avg_latency = sum(valid_timings) / len(valid_timings)
            min_latency = min(valid_timings)
            max_latency = max(valid_timings)
            p50 = sorted(valid_timings)[len(valid_timings) // 2]
        else:
            avg_latency = min_latency = max_latency = p50 = 0

        total_intents = sum(r.get("intents_count", 0) for r in results)
        multi_intent_count = sum(1 for r in results if r.get("intents_count", 0) > 1)

        stats = {
            "prompt_name": prompt_name,
            "total_intents": total_intents,
            "multi_intent_count": multi_intent_count,
            "avg_latency_ms": avg_latency,
            "min_latency_ms": min_latency,
            "max_latency_ms": max_latency,
            "p50_latency_ms": p50,
            "results": results
        }

        print(f"\n📊 Statistics:")
        print(f"  Total intents detected: {total_intents}")
        print(f"  Multi-intent utterances: {multi_intent_count}/{len(utterances)}")
        print(f"  Avg latency: {avg_latency:.0f}ms")
        print(f"  P50 latency: {p50:.0f}ms")
        print(f"  Min/Max: {min_latency:.0f}ms / {max_latency:.0f}ms")

        return stats

    finally:
        # Restore original prompt
        router_md_path.write_text(original_content)
        backup_path.unlink(missing_ok=True)


async def main():
    print("="*60)
    print("Multi-Intent Prompt Optimization Test")
    print("="*60)

    # Calculate token counts
    current_tokens = count_tokens(CURRENT_PROMPT)
    ultra_tokens = count_tokens(ULTRA_PROMPT)
    extreme_tokens = count_tokens(EXTREME_PROMPT)

    print(f"\n📏 Token Counts:")
    print(f"  Current:    {current_tokens} tokens")
    print(f"  Ultra:      {ultra_tokens} tokens ({100*(1-ultra_tokens/current_tokens):.1f}% reduction)")
    print(f"  Extreme:    {extreme_tokens} tokens ({100*(1-extreme_tokens/current_tokens):.1f}% reduction)")
    print(f"  Savings:    {current_tokens - ultra_tokens} tokens (ultra), {current_tokens - extreme_tokens} tokens (extreme)")

    # Test each prompt variant
    current_stats = await test_prompt_accuracy("Current (Baseline)", CURRENT_PROMPT, TEST_UTTERANCES)
    ultra_stats = await test_prompt_accuracy("Ultra-Optimized", ULTRA_PROMPT, TEST_UTTERANCES)
    extreme_stats = await test_prompt_accuracy("Extreme-Optimized", EXTREME_PROMPT, TEST_UTTERANCES)

    # Compare results
    print(f"\n{'='*60}")
    print("📊 COMPARISON")
    print(f"{'='*60}")

    print(f"\nLatency Comparison:")
    print(f"  Current P50:  {current_stats['p50_latency_ms']:.0f}ms")
    print(f"  Ultra P50:    {ultra_stats['p50_latency_ms']:.0f}ms ({current_stats['p50_latency_ms'] - ultra_stats['p50_latency_ms']:.0f}ms improvement)")
    print(f"  Extreme P50:  {extreme_stats['p50_latency_ms']:.0f}ms ({current_stats['p50_latency_ms'] - extreme_stats['p50_latency_ms']:.0f}ms improvement)")

    print(f"\nAccuracy Comparison:")
    print(f"  Current:  {current_stats['total_intents']} intents, {current_stats['multi_intent_count']} multi-intent")
    print(f"  Ultra:    {ultra_stats['total_intents']} intents, {ultra_stats['multi_intent_count']} multi-intent")
    print(f"  Extreme:  {extreme_stats['total_intents']} intents, {extreme_stats['multi_intent_count']} multi-intent")

    # Recommendation
    print(f"\n{'='*60}")
    print("💡 RECOMMENDATION")
    print(f"{'='*60}")

    ultra_latency_gain = current_stats['p50_latency_ms'] - ultra_stats['p50_latency_ms']
    extreme_latency_gain = current_stats['p50_latency_ms'] - extreme_stats['p50_latency_ms']

    # Check if accuracy is preserved
    ultra_accuracy_ok = ultra_stats['total_intents'] >= current_stats['total_intents'] * 0.9
    extreme_accuracy_ok = extreme_stats['total_intents'] >= current_stats['total_intents'] * 0.9

    if ultra_accuracy_ok and ultra_latency_gain >= 200:
        print("✅ RECOMMENDED: Ultra-Optimized Prompt")
        print(f"   - {100*(1-ultra_tokens/current_tokens):.1f}% token reduction")
        print(f"   - ~{ultra_latency_gain:.0f}ms P50 latency improvement")
        print(f"   - Accuracy preserved: {ultra_stats['total_intents']} intents detected")
    elif extreme_accuracy_ok and extreme_latency_gain >= 200:
        print("✅ RECOMMENDED: Extreme-Optimized Prompt")
        print(f"   - {100*(1-extreme_tokens/current_tokens):.1f}% token reduction")
        print(f"   - ~{extreme_latency_gain:.0f}ms P50 latency improvement")
        print(f"   - Accuracy preserved: {extreme_stats['total_intents']} intents detected")
    else:
        print("⚠️  No optimization recommended - accuracy degradation detected")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
