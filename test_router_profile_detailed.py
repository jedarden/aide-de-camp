#!/usr/bin/env .venv/bin/python
"""
High-resolution intent router latency profiling with microsecond precision.

This script profiles the full dispatch pipeline with detailed breakdowns:
- Router classification (fast-path vs LLM)
- Fetch orchestration (parallel source execution)
- Synthesis (LLM call for result generation)
- Database operations
- Full end-to-end dispatch latency
"""

import asyncio
import json
import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from src.intent.router import IntentRouter, get_router_cache
from src.session.store import get_store
from src.instrument.timings import DispatchTimings, percentiles
from src.main import app  # Import the FastAPI app for testing


@dataclass
class TimingResult:
    """Result of a single timing measurement."""
    operation: str
    duration_ms: float
    details: Dict[str, Any]


class DetailedRouterProfiler:
    """High-resolution profiler for intent router latency."""

    def __init__(self):
        self.router = IntentRouter()
        self.cache = get_router_cache()
        self.store = get_store()
        self.results: Dict[str, Any] = {}

    def time_ms(self) -> float:
        """Get current time in milliseconds with high resolution."""
        return time.perf_counter() * 1000

    async def profile_router_with_resolution(self):
        """Profile router classification with microsecond precision."""
        print("\n" + "=" * 70)
        print("HIGH-RESOLUTION ROUTER CLASSIFICATION PROFILE")
        print("=" * 70)

        session_id = "profile-session-hires"
        self.cache.invalidate(session_id)

        # Test cases with different paths
        test_cases = [
            ("Fast-path single intent", "what's the status of pbx"),
            ("Fast-path lookup", "pull up recent logs for whisper"),
            ("Fast-path brainstorm", "brainstorm improvements to armor"),
            ("Multi-intent LLM", "check pbx status and pull up whisper logs"),
        ]

        results = []

        for description, utterance in test_cases:
            print(f"\n{description}")
            print(f"  Utterance: {utterance[:70]}")

            # Warm up
            self.cache.invalidate(session_id)
            await self.router.classify_utterance(utterance, session_id)

            # Measure multiple runs for accurate statistics
            times = []
            for _ in range(5):
                self.cache.invalidate(session_id)
                start = self.time_ms()
                result = await self.router.classify_utterance(utterance, session_id)
                elapsed = self.time_ms() - start
                times.append(elapsed)

            # Calculate statistics
            avg = statistics.mean(times)
            median = statistics.median(times)
            p95 = percentiles(times, (95,))[95]
            min_val = min(times)
            max_val = max(times)

            print(f"  Avg: {avg:.2f}ms | Median: {median:.2f}ms | p95: {p95:.2f}ms")
            print(f"  Range: [{min_val:.2f}ms - {max_val:.2f}ms]")
            print(f"  Intents: {len(result)}")

            for i, cls in enumerate(result):
                print(f"    [{i+1}] {cls.intent_type.value} → {cls.project_slug or 'no project'}")

            results.append({
                "description": description,
                "utterance": utterance,
                "avg_ms": avg,
                "median_ms": median,
                "p95_ms": p95,
                "min_ms": min_val,
                "max_ms": max_val,
                "intent_count": len(result),
                "samples": times,
            })

        self.results["router_classification"] = results
        return results

    async def profile_cache_vs_nocache(self):
        """Profile cache effectiveness with detailed comparison."""
        print("\n" + "=" * 70)
        print("CACHE VS NO-CACHE COMPARISON")
        print("=" * 70)

        session_id = "profile-session-cache-detail"
        utterance = "what's the status of pbx"

        print(f"\nUtterance: {utterance}")
        print("\nMeasuring cache hit vs miss latency...")

        # Cache miss (classification + cache insert)
        cache_miss_times = []
        for _ in range(5):
            self.cache.invalidate(session_id)
            start = self.time_ms()
            await self.router.classify_utterance(utterance, session_id, use_cache=True)
            elapsed = self.time_ms() - start
            cache_miss_times.append(elapsed)

        # Cache hit (lookup only)
        cache_hit_times = []
        for _ in range(20):
            start = self.time_ms()
            await self.router.classify_utterance(utterance, session_id, use_cache=True)
            elapsed = self.time_ms() - start
            cache_hit_times.append(elapsed)

        miss_avg = statistics.mean(cache_miss_times)
        hit_avg = statistics.mean(cache_hit_times)
        speedup = miss_avg / hit_avg if hit_avg > 0 else 0

        print(f"\nCache Miss (5 runs):")
        print(f"  Avg: {miss_avg:.2f}ms | Median: {statistics.median(cache_miss_times):.2f}ms")
        print(f"  p95: {percentiles(cache_miss_times, (95,))[95]:.2f}ms")

        print(f"\nCache Hit (20 runs):")
        print(f"  Avg: {hit_avg:.2f}ms | Median: {statistics.median(cache_hit_times):.2f}ms")
        print(f"  p95: {percentiles(cache_hit_times, (95,))[95]:.2f}ms")

        print(f"\nCache Performance:")
        print(f"  Speedup: {speedup:.1f}x")
        print(f"  Time saved per hit: {miss_avg - hit_avg:.2f}ms")

        self.results["cache_comparison"] = {
            "cache_miss_avg_ms": miss_avg,
            "cache_hit_avg_ms": hit_avg,
            "speedup_x": speedup,
            "time_saved_ms": miss_avg - hit_avg,
            "cache_miss_samples": cache_miss_times,
            "cache_hit_samples": cache_hit_times,
        }

        return self.results["cache_comparison"]

    async def profile_llm_breakdown(self):
        """Profile ZAI LLM call latency in isolation."""
        print("\n" + "=" * 70)
        print("ZAI LLM CALL BREAKDOWN")
        print("=" * 70)

        session_id = "profile-session-llm"

        # Test different utterance complexities
        test_cases = [
            ("Simple single intent", "what's the status of pbx"),
            ("Multi-intent", "check pbx status and pull up whisper logs"),
            ("Complex multi-intent", "check pbx, pull up whisper logs, and verify armor config"),
        ]

        results = []

        for description, utterance in test_cases:
            print(f"\n{description}")
            print(f"  Utterance: {utterance[:70]}")

            # Warm up
            self.cache.invalidate(session_id)
            await self.router.classify_utterance(utterance, session_id)

            # Measure multiple LLM calls
            times = []
            for _ in range(5):
                self.cache.invalidate(session_id)
                start = self.time_ms()
                result = await self.router.classify_utterance(utterance, session_id)
                elapsed = self.time_ms() - start
                times.append(elapsed)

            avg = statistics.mean(times)
            median = statistics.median(times)
            p95 = percentiles(times, (95,))[95]

            print(f"  Avg: {avg:.2f}ms | Median: {median:.2f}ms | p95: {p95:.2f}ms")
            print(f"  Intents detected: {len(result)}")

            results.append({
                "description": description,
                "avg_ms": avg,
                "median_ms": median,
                "p95_ms": p95,
                "intent_count": len(result),
                "samples": times,
            })

        self.results["llm_breakdown"] = results
        return results

    async def profile_db_operations(self):
        """Profile database operation latencies."""
        print("\n" + "=" * 70)
        print("DATABASE OPERATIONS PROFILE")
        print("=" * 70)

        session_id = f"profile-session-db-{uuid.uuid4()}"

        operations = []

        # Profile get_session
        times = []
        for _ in range(10):
            start = self.time_ms()
            await self.store.get_session(session_id)
            elapsed = self.time_ms() - start
            times.append(elapsed)

        avg = statistics.mean(times)
        print(f"\nget_session:")
        print(f"  Avg: {avg:.3f}ms | p95: {percentiles(times, (95,))[95]:.3f}ms")
        operations.append({"operation": "get_session", "avg_ms": avg, "samples": times})

        # Profile create_intent
        times = []
        for _ in range(10):
            utterance_id = str(uuid.uuid4())
            start = self.time_ms()
            await self.store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug=None,
                intent_type="status",
            )
            elapsed = self.time_ms() - start
            times.append(elapsed)

        avg = statistics.mean(times)
        print(f"\ncreate_intent:")
        print(f"  Avg: {avg:.3f}ms | p95: {percentiles(times, (95,))[95]:.3f}ms")
        operations.append({"operation": "create_intent", "avg_ms": avg, "samples": times})

        # Profile get_pending_intents
        times = []
        for _ in range(10):
            start = self.time_ms()
            await self.store.get_pending_intents(session_id)
            elapsed = self.time_ms() - start
            times.append(elapsed)

        avg = statistics.mean(times)
        print(f"\nget_pending_intents:")
        print(f"  Avg: {avg:.3f}ms | p95: {percentiles(times, (95,))[95]:.3f}ms")
        operations.append({"operation": "get_pending_intents", "avg_ms": avg, "samples": times})

        # Profile record_dispatch_timings
        times = []
        for _ in range(10):
            intent_id = str(uuid.uuid4())
            start = self.time_ms()
            await self.store.record_dispatch_timings(
                intent_id=intent_id,
                router_ms=100,
                fetch_first_source_ms=200,
                fetch_total_ms=500,
                synthesize_total_ms=800,
            )
            elapsed = self.time_ms() - start
            times.append(elapsed)

        avg = statistics.mean(times)
        print(f"\nrecord_dispatch_timings:")
        print(f"  Avg: {avg:.3f}ms | p95: {percentiles(times, (95,))[95]:.3f}ms")
        operations.append({"operation": "record_dispatch_timings", "avg_ms": avg, "samples": times})

        self.results["db_operations"] = operations
        return operations

    async def profile_route_utterance_breakdown(self):
        """Profile route_utterance with detailed breakdown."""
        print("\n" + "=" * 70)
        print("ROUTE UTTERANCE BREAKDOWN")
        print("=" * 70)

        session_id = "profile-session-route-detail"

        test_cases = [
            "what's the status of pbx",
            "pull up recent logs for whisper",
        ]

        results = []

        for utterance in test_cases:
            print(f"\nUtterance: {utterance[:70]}")

            # Measure route_utterance
            times = []
            router_ms_values = []

            for _ in range(3):
                self.cache.invalidate(session_id)
                utterance_id = str(uuid.uuid4())

                start = self.time_ms()
                try:
                    routed = await self.router.route_utterance(
                        utterance=utterance,
                        utterance_id=utterance_id,
                        session_id=session_id,
                    )
                    elapsed = self.time_ms() - start
                    times.append(elapsed)

                    if routed:
                        router_ms_values.append(routed[0].router_ms or 0)

                except Exception as e:
                    print(f"  Error: {e}")

            if times:
                avg = statistics.mean(times)
                avg_router = statistics.mean(router_ms_values) if router_ms_values else 0

                print(f"  route_utterance avg: {avg:.2f}ms")
                print(f"  router_ms avg: {avg_router:.2f}ms")
                print(f"  Overhead: {avg - avg_router:.2f}ms")

                results.append({
                    "utterance": utterance,
                    "route_utterance_avg_ms": avg,
                    "router_ms_avg": avg_router,
                    "overhead_ms": avg - avg_router,
                })

        self.results["route_utterance"] = results
        return results

    def print_comprehensive_summary(self):
        """Print a comprehensive summary of findings."""
        print("\n" + "=" * 70)
        print("COMPREHENSIVE LATENCY BREAKDOWN SUMMARY")
        print("=" * 70)

        if "router_classification" in self.results:
            print("\n🔍 ROUTER CLASSIFICATION:")
            for result in self.results["router_classification"]:
                print(f"\n  {result['description']}:")
                print(f"    Median: {result['median_ms']:.2f}ms")
                print(f"    p95: {result['p95_ms']:.2f}ms")
                print(f"    Intents: {result['intent_count']}")

        if "cache_comparison" in self.results:
            cache = self.results["cache_comparison"]
            print(f"\n💾 CACHE PERFORMANCE:")
            print(f"  Cache miss avg: {cache['cache_miss_avg_ms']:.2f}ms")
            print(f"  Cache hit avg: {cache['cache_hit_avg_ms']:.2f}ms")
            print(f"  Speedup: {cache['speedup_x']:.1f}x")

        if "llm_breakdown" in self.results:
            print(f"\n🤖 ZAI LLM CALL LATENCY:")
            for result in self.results["llm_breakdown"]:
                print(f"\n  {result['description']}:")
                print(f"    Median: {result['median_ms']:.2f}ms")
                print(f"    p95: {result['p95_ms']:.2f}ms")

        if "db_operations" in self.results:
            print(f"\n🗄️ DATABASE OPERATIONS:")
            for op in self.results["db_operations"]:
                print(f"  {op['operation']}: {op['avg_ms']:.3f}ms (avg)")

        if "route_utterance" in self.results:
            print(f"\n🚀 ROUTE UTTERANCE:")
            for result in self.results["route_utterance"]:
                print(f"  {result['utterance'][:50]}:")
                print(f"    Total: {result['route_utterance_avg_ms']:.2f}ms")
                print(f"    Router: {result['router_ms_avg']:.2f}ms")
                print(f"    Overhead: {result['overhead_ms']:.2f}ms")

        # Budget analysis
        print(f"\n📊 LATENCY BUDGET ANALYSIS:")
        print("  Per plan §6.5, target breakdown:")
        print("  - Fast-path routing: <10ms")
        print("  - Router classification (LLM): <3000ms")
        print("  - Cache hit: <1ms")
        print("  - DB operations: <5ms each")

    async def run_full_profile(self):
        """Run all profiling tests."""
        print("\n" + "=" * 70)
        print("DETAILED INTENT ROUTER LATENCY PROFILING")
        print("=" * 70)
        print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        await self.profile_router_with_resolution()
        await self.profile_cache_vs_nocache()
        await self.profile_llm_breakdown()
        await self.profile_db_operations()
        await self.profile_route_utterance_breakdown()

        print("\n" + "=" * 70)
        print("PROFILING COMPLETE")
        print("=" * 70)
        print(f"Finished at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Save results
        output_file = Path("/tmp/router_profile_detailed.json")
        output_file.write_text(json.dumps(self.results, indent=2, default=str))
        print(f"\nResults saved to: {output_file}")

        # Print summary
        self.print_comprehensive_summary()


async def main():
    """Run the detailed profiling."""
    profiler = DetailedRouterProfiler()
    await profiler.run_full_profile()


if __name__ == "__main__":
    asyncio.run(main())
