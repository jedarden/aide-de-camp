#!/usr/bin/env .venv/bin/python
"""
Comprehensive intent router latency profiling.

This script profiles the full intent router pipeline with detailed breakdowns:
- Fast-path vs LLM routing
- Cache hit vs miss latency
- Individual component timings (ZAI call, DB queries, fetch orchestration, synthesis)
- End-to-end dispatch latency
"""

import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from src.intent.router import IntentRouter, get_router_cache
from src.session.store import get_store
from src.instrument.timings import DispatchTimings, percentiles


class RouterProfiler:
    """Profile intent router latency across all stages."""

    def __init__(self):
        self.router = IntentRouter()
        self.cache = get_router_cache()
        self.store = get_store()
        self.results: Dict[str, Any] = {}

    async def profile_classification(self):
        """Profile the classify_utterance method in detail."""
        print("\n" + "=" * 70)
        print("CLASSIFICATION LATENCY PROFILE")
        print("=" * 70)

        session_id = "profile-session-classify"
        self.cache.invalidate(session_id)

        test_cases = [
            # (utterance, description, expected_path)
            ("what's the status of pbx", "Simple status (fast-path)", "fast-path"),
            ("pull up recent logs for whisper", "Simple lookup (fast-path)", "fast-path"),
            ("has the pbx web caught up and what's the state of whisper stt",
             "Multi-intent (LLM)", "llm"),
            ("check the armor configuration", "Simple lookup (fast-path)", "fast-path"),
        ]

        results = []

        for utterance, description, expected_path in test_cases:
            print(f"\n{description}")
            print(f"  Utterance: {utterance[:70]}")

            # Clear cache for accurate measurement
            self.cache.invalidate(session_id)

            # Measure first call (cache miss)
            start = time.monotonic()
            classifications = await self.router.classify_utterance(
                utterance, session_id, use_cache=True
            )
            first_call_ms = (time.monotonic() - start) * 1000

            # Measure cache hit
            start = time.monotonic()
            classifications_cached = await self.router.classify_utterance(
                utterance, session_id, use_cache=True
            )
            cache_hit_ms = (time.monotonic() - start) * 1000

            # Measure with cache disabled (always LLM/fast-path)
            self.cache.invalidate(session_id)
            start = time.monotonic()
            classifications_no_cache = await self.router.classify_utterance(
                utterance, session_id, use_cache=False
            )
            no_cache_ms = (time.monotonic() - start) * 1000

            print(f"  First call (cache miss): {int(first_call_ms)}ms")
            print(f"  Cache hit: {int(cache_hit_ms)}ms")
            print(f"  Cache disabled: {int(no_cache_ms)}ms")
            print(f"  Intents detected: {len(classifications)}")

            for i, cls in enumerate(classifications):
                print(f"    [{i+1}] {cls.intent_type.value} → {cls.project_slug or 'no project'} "
                      f"(confidence: {cls.confidence})")

            results.append({
                "description": description,
                "utterance": utterance,
                "expected_path": expected_path,
                "first_call_ms": first_call_ms,
                "cache_hit_ms": cache_hit_ms,
                "no_cache_ms": no_cache_ms,
                "intent_count": len(classifications),
            })

        self.results["classification"] = results
        return results

    async def profile_zai_latency(self):
        """Profile ZAI proxy call latency in isolation."""
        print("\n" + "=" * 70)
        print("ZAI PROXY LATENCY PROFILE")
        print("=" * 70)

        session_id = "profile-session-zai"
        self.cache.invalidate(session_id)

        # Use a multi-intent utterance to force LLM call
        utterance = "check pbx status and pull up whisper logs"

        print(f"\nUtterance: {utterance}")
        print("\nMeasuring ZAI call latency (5 runs)...")

        times = []
        for i in range(5):
            self.cache.invalidate(session_id)  # Force cache miss
            start = time.monotonic()

            # The classify_utterance includes ZAI call time
            result = await self.router.classify_utterance(
                utterance, session_id, use_cache=False
            )

            elapsed = (time.monotonic() - start) * 1000
            times.append(elapsed)
            print(f"  Run {i+1}: {int(elapsed)}ms")

        if times:
            p50 = int(statistics.median(times))
            p95 = int(percentiles(times, (95,))[95])
            avg = int(statistics.mean(times))
            print(f"\nZAI Call Statistics:")
            print(f"  Average: {avg}ms")
            print(f"  p50: {p50}ms")
            print(f"  p95: {p95}ms")
            print(f"  Min: {int(min(times))}ms")
            print(f"  Max: {int(max(times))}ms")

            self.results["zai_latency"] = {
                "avg_ms": avg,
                "p50_ms": p50,
                "p95_ms": p95,
                "min_ms": int(min(times)),
                "max_ms": int(max(times)),
                "samples": times,
            }

        return self.results.get("zai_latency", {})

    async def profile_cache_effectiveness(self):
        """Profile cache hit rates and effectiveness."""
        print("\n" + "=" * 70)
        print("CACHE EFFECTIVENESS PROFILE")
        print("=" * 70)

        session_id = "profile-session-cache"

        # Simulate realistic usage pattern
        utterances = [
            "what's the status of pbx",  # Repeated 3x
            "what's the status of pbx",
            "what's the status of pbx",
            "pull up whisper logs",  # Repeated 2x
            "pull up whisper logs",
            "check armor config",  # Unique
            "what's the status of pbx",  # Again
        ]

        print(f"\nSimulating {len(utterances)} utterances with repetition pattern...")
        self.cache.invalidate(session_id)

        total_time = 0
        hit_count = 0
        miss_count = 0

        for i, utterance in enumerate(utterances):
            start = time.monotonic()
            result = await self.router.classify_utterance(
                utterance, session_id, use_cache=True
            )
            elapsed = (time.monotonic() - start) * 1000
            total_time += elapsed

            # Check if it was a cache hit (fast response)
            is_hit = elapsed < 50  # Cache hits are typically < 50ms
            if is_hit:
                hit_count += 1
            else:
                miss_count += 1

            print(f"  [{i+1}] {int(elapsed)}ms {'(hit)' if is_hit else '(miss)'} "
                  f"- {utterance[:50]}")

        stats = self.cache.get_stats()
        hit_rate = stats.get("hit_rate", 0)

        print(f"\nCache Statistics:")
        print(f"  Total requests: {len(utterances)}")
        print(f"  Cache hits: {hit_count}")
        print(f"  Cache misses: {miss_count}")
        print(f"  Hit rate: {hit_rate:.1%}")
        print(f"  Total time: {int(total_time)}ms")
        print(f"  Avg per request: {int(total_time / len(utterances))}ms")

        self.results["cache_effectiveness"] = {
            "total_requests": len(utterances),
            "hits": hit_count,
            "misses": miss_count,
            "hit_rate": hit_rate,
            "total_time_ms": total_time,
            "avg_per_request_ms": total_time / len(utterances),
        }

        return self.results["cache_effectiveness"]

    async def profile_db_queries(self):
        """Profile database query latencies."""
        print("\n" + "=" * 70)
        print("DATABASE QUERY LATENCY PROFILE")
        print("=" * 70)

        session_id = "profile-session-db"

        # Test session creation
        print("\nSession Operations:")
        start = time.monotonic()
        session = await self.store.get_session(session_id)
        get_session_ms = (time.monotonic() - start) * 1000
        print(f"  get_session(): {int(get_session_ms)}ms")

        # Test intent creation
        print("\nIntent Operations:")
        import uuid
        utterance_id = str(uuid.uuid4())
        start = time.monotonic()
        intent_id = await self.store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug=None,
            intent_type="status",
        )
        create_intent_ms = (time.monotonic() - start) * 1000
        print(f"  create_intent(): {int(create_intent_ms)}ms")

        # Test pending intents query
        start = time.monotonic()
        intents = await self.store.get_pending_intents(session_id)
        get_intents_ms = (time.monotonic() - start) * 1000
        print(f"  get_pending_intents(): {int(get_intents_ms)}ms")
        print(f"    Returned {len(intents)} intents")

        # Test timings record
        print("\nDispatch Timings Operations:")
        start = time.monotonic()
        await self.store.record_dispatch_timings(
            intent_id=intent_id,
            router_ms=100,
            fetch_first_source_ms=200,
            fetch_total_ms=500,
            synthesize_total_ms=800,
        )
        record_timings_ms = (time.monotonic() - start) * 1000
        print(f"  record_dispatch_timings(): {int(record_timings_ms)}ms")

        self.results["db_queries"] = {
            "get_session_ms": get_session_ms,
            "create_intent_ms": create_intent_ms,
            "get_intents_ms": get_intents_ms,
            "record_timings_ms": record_timings_ms,
        }

        return self.results["db_queries"]

    async def profile_route_utterance(self):
        """Profile the full route_utterance method."""
        print("\n" + "=" * 70)
        print("ROUTE UTTERANCE LATENCY PROFILE")
        print("=" * 70)

        session_id = "profile-session-route"
        self.cache.invalidate(session_id)

        utterances = [
            "what's the status of pbx",
            "pull up recent logs for whisper stt",
            "check the armor configuration",
        ]

        results = []

        for utterance in utterances:
            print(f"\nUtterance: {utterance[:70]}")

            # Clear cache
            self.cache.invalidate(session_id)

            # Generate unique utterance ID
            import uuid
            utterance_id = str(uuid.uuid4())

            # Measure route_utterance
            start = time.monotonic()
            try:
                routed_intents = await self.router.route_utterance(
                    utterance=utterance,
                    utterance_id=utterance_id,
                    session_id=session_id,
                )
                elapsed = (time.monotonic() - start) * 1000

                print(f"  Time: {int(elapsed)}ms")
                print(f"  Routed intents: {len(routed_intents)}")

                for routed in routed_intents:
                    print(f"    - {routed.classification.intent_type.value} "
                          f"(router_ms: {routed.router_ms}ms)")

                results.append({
                    "utterance": utterance,
                    "total_ms": elapsed,
                    "intent_count": len(routed_intents),
                    "router_ms": routed_intents[0].router_ms if routed_intents else None,
                })

            except Exception as e:
                print(f"  Error: {e}")

        self.results["route_utterance"] = results
        return results

    async def run_full_profile(self):
        """Run all profiling tests."""
        print("\n" + "=" * 70)
        print("INTENT ROUTER LATENCY PROFILING")
        print("=" * 70)
        print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        await self.profile_classification()
        await self.profile_zai_latency()
        await self.profile_cache_effectiveness()
        await self.profile_db_queries()
        await self.profile_route_utterance()

        print("\n" + "=" * 70)
        print("PROFILING COMPLETE")
        print("=" * 70)
        print(f"Finished at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Save results to file
        output_file = Path("/tmp/router_profile_results.json")
        output_file.write_text(json.dumps(self.results, indent=2))
        print(f"\nResults saved to: {output_file}")

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print a summary of key findings."""
        print("\n" + "=" * 70)
        print("SUMMARY OF KEY FINDINGS")
        print("=" * 70)

        if "classification" in self.results:
            cls_results = self.results["classification"]
            fast_path_avg = statistics.mean([
                r["first_call_ms"] for r in cls_results
                if r["expected_path"] == "fast-path"
            ])
            llm_avg = statistics.mean([
                r["first_call_ms"] for r in cls_results
                if r["expected_path"] == "llm"
            ])
            print(f"\nClassification:")
            print(f"  Fast-path average: {int(fast_path_avg)}ms")
            print(f"  LLM call average: {int(llm_avg)}ms")
            print(f"  Speedup from fast-path: {int(llm_avg / fast_path_avg)}x")

        if "zai_latency" in self.results:
            zai = self.results["zai_latency"]
            print(f"\nZAI Proxy Latency:")
            print(f"  p50: {zai['p50_ms']}ms")
            print(f"  p95: {zai['p95_ms']}ms")

        if "cache_effectiveness" in self.results:
            cache = self.results["cache_effectiveness"]
            print(f"\nCache Effectiveness:")
            print(f"  Hit rate: {cache['hit_rate']:.1%}")
            print(f"  Avg with cache: {int(cache['avg_per_request_ms'])}ms")

        if "db_queries" in self.results:
            db = self.results["db_queries"]
            print(f"\nDatabase Queries:")
            print(f"  get_session: {int(db['get_session_ms'])}ms")
            print(f"  create_intent: {int(db['create_intent_ms'])}ms")
            print(f"  record_timings: {int(db['record_timings_ms'])}ms")


async def main():
    """Run the profiling."""
    profiler = RouterProfiler()
    await profiler.run_full_profile()


if __name__ == "__main__":
    asyncio.run(main())
