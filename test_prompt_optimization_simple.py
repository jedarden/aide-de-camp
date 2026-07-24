#!/usr/bin/env python3
"""
Test prompt optimization impact on single-intent classification.
Measures token reduction and latency improvement.
"""

import asyncio
import sys
import time
from pathlib import Path

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

# Optimized prompt (30-35% reduction target)
OPTIMIZED_PROMPT = """# Intent Router
Classify utterances. Return JSON array.

Types: status/state | action/execute | brainstorm/explore | lookup/find | reminder/time | task-profile/multi-step

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Split by type/project. Map projects by name."""

# Ultra-optimized prompt (40-45% reduction target)
ULTRA_PROMPT = """# Intent Router
Classify utterances. Return JSON array.

Types: status|action|brainstorm|lookup|reminder|task-profile

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Split by type/project."""


# Sample single-intent utterances (avoid max_tokens truncation)
TEST_UTTERANCES = [
    "Check pods in aide-de-camp",
    "Deploy the new version of mtl-my-way",
    "Look up the logs for ardenone-cluster",
    "Brainstorm options for the new feature",
    "Check the status of the kalshi-tape deployment",
    "What's the status of the aide-de-camp router?",
    "Deploy clasp",
    "Investigate why the proxy is slow",
    "Check pods in ardenone-cluster",
    "Look up the config for iad-options",
]


async def test_prompt(prompt_name: str, prompt_text: str, utterances: list[str]) -> dict:
    """Test classification with a given prompt."""
    print(f"\n{'='*60}")
    print(f"Testing: {prompt_name}")
    print(f"{'='*60}")

    router_md_path = Path("/home/coding/aide-de-camp/prompts/router.md")
    original_content = router_md_path.read_text()
    backup_path = router_md_path.with_suffix(".md.backup")
    backup_path.write_text(original_content)

    router_md_path.write_text(prompt_text)

    try:
        store = get_store()
        router = IntentRouter(store=store)
        router._clear_cache()

        results = []
        timings = []
        errors = []

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

                results.append({
                    "utterance": utterance,
                    "intents_count": len(classifications),
                    "classification": classifications[0].intent_type.value if classifications else None,
                    "timing_ms": elapsed
                })

                print(f"✓ '{utterance[:50]}...' → {classifications[0].intent_type.value if classifications else 'ERROR'} ({elapsed:.0f}ms)")

            except Exception as e:
                errors.append(str(e))
                results.append({
                    "utterance": utterance,
                    "error": str(e),
                    "intents_count": 0
                })
                print(f"✗ '{utterance[:50]}...' → ERROR")

        if timings:
            avg_latency = sum(timings) / len(timings)
            min_latency = min(timings)
            max_latency = max(timings)
            p50 = sorted(timings)[len(timings) // 2]
        else:
            avg_latency = min_latency = max_latency = p50 = 0

        stats = {
            "prompt_name": prompt_name,
            "total_classified": len([r for r in results if not r.get("error")]),
            "total_errors": len(errors),
            "avg_latency_ms": avg_latency,
            "min_latency_ms": min_latency,
            "max_latency_ms": max_latency,
            "p50_latency_ms": p50,
            "results": results
        }

        print(f"\n📊 Statistics:")
        print(f"  Classified: {stats['total_classified']}/{len(utterances)}")
        print(f"  Errors: {stats['total_errors']}")
        print(f"  Avg latency: {avg_latency:.0f}ms")
        print(f"  P50 latency: {p50:.0f}ms")
        print(f"  Min/Max: {min_latency:.0f}ms / {max_latency:.0f}ms")

        return stats

    finally:
        router_md_path.write_text(original_content)
        backup_path.unlink(missing_ok=True)


async def main():
    print("="*60)
    print("Prompt Optimization Test (Single-Intent)")
    print("="*60)

    current_tokens = count_tokens(CURRENT_PROMPT)
    optimized_tokens = count_tokens(OPTIMIZED_PROMPT)
    ultra_tokens = count_tokens(ULTRA_PROMPT)

    print(f"\n📏 Token Counts:")
    print(f"  Current:    {current_tokens} tokens")
    print(f"  Optimized:  {optimized_tokens} tokens ({100*(1-optimized_tokens/current_tokens):.1f}% reduction)")
    print(f"  Ultra:      {ultra_tokens} tokens ({100*(1-ultra_tokens/current_tokens):.1f}% reduction)")
    print(f"  Savings:    {current_tokens - optimized_tokens} tokens (optimized), {current_tokens - ultra_tokens} tokens (ultra)")

    current_stats = await test_prompt("Current (Baseline)", CURRENT_PROMPT, TEST_UTTERANCES)
    optimized_stats = await test_prompt("Optimized", OPTIMIZED_PROMPT, TEST_UTTERANCES)
    ultra_stats = await test_prompt("Ultra-Optimized", ULTRA_PROMPT, TEST_UTTERANCES)

    print(f"\n{'='*60}")
    print("📊 COMPARISON")
    print(f"{'='*60}")

    print(f"\nToken Reduction:")
    print(f"  Current:    {current_tokens} tokens")
    print(f"  Optimized:  {optimized_tokens} tokens ({100*(1-optimized_tokens/current_tokens):.1f}% reduction)")
    print(f"  Ultra:      {ultra_tokens} tokens ({100*(1-ultra_tokens/current_tokens):.1f}% reduction)")

    print(f"\nAccuracy:")
    print(f"  Current:  {current_stats['total_classified']}/{len(TEST_UTTERANCES)} classified")
    print(f"  Optimized: {optimized_stats['total_classified']}/{len(TEST_UTTERANCES)} classified")
    print(f"  Ultra:  {ultra_stats['total_classified']}/{len(TEST_UTTERANCES)} classified")

    print(f"\nLatency Improvement:")
    print(f"  Current P50:  {current_stats['p50_latency_ms']:.0f}ms")
    print(f"  Optimized P50:  {optimized_stats['p50_latency_ms']:.0f}ms ({current_stats['p50_latency_ms'] - optimized_stats['p50_latency_ms']:.0f}ms improvement)")
    print(f"  Ultra P50:  {ultra_stats['p50_latency_ms']:.0f}ms ({current_stats['p50_latency_ms'] - ultra_stats['p50_latency_ms']:.0f}ms improvement)")

    print(f"\n{'='*60}")
    print("💡 RECOMMENDATION")
    print(f"{'='*60}")

    optimized_gain = current_stats['p50_latency_ms'] - optimized_stats['p50_latency_ms']
    ultra_gain = current_stats['p50_latency_ms'] - ultra_stats['p50_latency_ms']

    # Check if accuracy is preserved (within 90%)
    optimized_accuracy_ok = optimized_stats['total_classified'] >= current_stats['total_classified'] * 0.9
    ultra_accuracy_ok = ultra_stats['total_classified'] >= current_stats['total_classified'] * 0.9

    token_reduction_target_met = (100*(1-optimized_tokens/current_tokens) >= 30) or (100*(1-ultra_tokens/current_tokens) >= 30)
    latency_target_met = (optimized_gain >= 200) or (ultra_gain >= 200)

    if optimized_accuracy_ok and 100*(1-optimized_tokens/current_tokens) >= 30:
        print("✅ RECOMMENDED: Optimized Prompt")
        print(f"   - {100*(1-optimized_tokens/current_tokens):.1f}% token reduction (target: 30-40%)")
        print(f"   - ~{optimized_gain:.0f}ms P50 latency improvement (target: 200-300ms)")
        print(f"   - Accuracy preserved: {optimized_stats['total_classified']}/{len(TEST_UTTERANCES)} classified")
    elif ultra_accuracy_ok and 100*(1-ultra_tokens/current_tokens) >= 30:
        print("✅ RECOMMENDED: Ultra-Optimized Prompt")
        print(f"   - {100*(1-ultra_tokens/current_tokens):.1f}% token reduction (target: 30-40%)")
        print(f"   - ~{ultra_gain:.0f}ms P50 latency improvement (target: 200-300ms)")
        print(f"   - Accuracy preserved: {ultra_stats['total_classified']}/{len(TEST_UTTERANCES)} classified")
    else:
        print("⚠️  No clear recommendation - testing completed with mixed results")

    print(f"\nTargets:")
    print(f"  Token reduction: 30-40% {'✅' if token_reduction_target_met else '❌'}")
    print(f"  Latency improvement: 200-300ms {'✅' if latency_target_met else '❌'}")
    print(f"  Accuracy preserved: {'✅' if (optimized_accuracy_ok or ultra_accuracy_ok) else '❌'}")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
