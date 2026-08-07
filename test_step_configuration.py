#!/usr/bin/env python3
"""
Test script to verify step configuration loading and bucket initialization.
"""

import sys
sys.path.append('/home/coding/aide-de-camp')

from pathlib import Path
from query_whisper_stt_victorialogs_latency import WhisperSTTVictoriaLogsQuery, load_step_config

def test_configuration_loading():
    """Test that configuration is loaded correctly."""
    print("=" * 70)
    print("TESTING STEP CONFIGURATION LOADING")
    print("=" * 70)

    # Load step from config
    step = load_step_config()
    print(f"\n✓ Loaded step configuration: '{step}'")

    # Initialize query engine
    query_engine = WhisperSTTVictoriaLogsQuery(
        "2026-07-07T00:00:00Z",
        "2026-08-06T23:59:59Z",
        step=step
    )

    print(f"✓ Query engine initialized with step: {step}")
    print(f"  Parsed step_hours: {query_engine.step_hours}")

    # Initialize time buckets
    buckets = query_engine._initialize_time_buckets()

    print(f"\n✓ Time buckets initialized: {len(buckets)} buckets")
    # Note: The date range is actually 31 days (July 7 to August 6 inclusive)
    expected_buckets = 31 * 24  # 744 for 31 days
    print(f"  Expected for 31-day window (2026-07-07 to 2026-08-06): {expected_buckets} buckets")
    print(f"  Match: {'✅ YES' if len(buckets) == expected_buckets else '❌ NO'}")

    # Show bucket structure
    if len(buckets) > 0:
        print(f"\n✓ First bucket structure:")
        print(f"  Index: {buckets[0]['bucket_index']}")
        print(f"  Window: {buckets[0]['window_start']} to {buckets[0]['window_end']}")
        print(f"  Record count: {buckets[0]['record_count']}")

        print(f"\n✓ Last bucket structure:")
        print(f"  Index: {buckets[-1]['bucket_index']}")
        print(f"  Window: {buckets[-1]['window_start']} to {buckets[-1]['window_end']}")
        print(f"  Record count: {buckets[-1]['record_count']}")

    # Verify manageability
    is_manageable = len(buckets) < 1000
    print(f"\n✓ Manageability check:")
    print(f"  Bucket count: {len(buckets)}")
    print(f"  Target: < 1000")
    print(f"  Status: {'✅ MANAGEABLE' if is_manageable else '❌ EXCEEDS TARGET'}")

    return len(buckets) == 744 and is_manageable

if __name__ == "__main__":
    success = test_configuration_loading()
    sys.exit(0 if success else 1)
