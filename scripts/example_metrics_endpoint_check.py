#!/usr/bin/env python3
"""
Example usage of the endpoint connectivity utility for testing metrics endpoints.

This script demonstrates how to use the check_endpoint_connectivity and
check_metrics_endpoints functions to test HTTP endpoints, particularly
useful for monitoring and validating metrics endpoints for pbx-web and
whisper-stt services.

Usage examples:
    # Check a single endpoint
    python scripts/example_metrics_endpoint_check.py --single

    # Check multiple endpoints concurrently
    python scripts/example_metrics_endpoint_check.py --multiple

    # Check with custom timeout
    python scripts/example_metrics_endpoint_check.py --custom
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.test.utilities import (
    check_endpoint_connectivity,
    check_metrics_endpoints,
    check_endpoint_connectivity_sync,
)


async def check_single_endpoint_example():
    """Example: Check a single Prometheus metrics endpoint."""
    print("=" * 60)
    print("Example 1: Single Endpoint Check")
    print("=" * 60)

    result = await check_endpoint_connectivity(
        endpoint_url="http://localhost:9090/api/v1/query?query=up",
        timeout_seconds=10.0,
    )

    print(f"Endpoint: http://localhost:9090/api/v1/query?query=up")
    print(f"Success: {result.success}")
    print(f"Status Code: {result.status_code}")
    print(f"Response Time: {result.response_time_ms:.2f}ms")

    if result.success:
        print(f"Response Body (first 200 chars): {result.response_body[:200]}...")
    else:
        print(f"Error: {result.error_message}")

    print()


async def check_multiple_endpoints_example():
    """Example: Check multiple endpoints concurrently (pbx-web and whisper-stt)."""
    print("=" * 60)
    print("Example 2: Multiple Endpoints Concurrent Check")
    print("=" * 60)

    endpoints = [
        {
            "name": "prometheus",
            "url": "http://localhost:9090/api/v1/query?query=up",
        },
        {
            "name": "pbx-web",
            "url": "http://localhost:9090/metrics",
            "headers": {"Accept": "text/plain"},
        },
        {
            "name": "whisper-stt",
            "url": "http://localhost:9090/metrics",
        },
    ]

    results = await check_metrics_endpoints(endpoints, timeout_seconds=30.0)

    print(f"Checked {len(results)} endpoints concurrently:\n")

    for name, result in results.items():
        print(f"{name}:")
        print(f"  Success: {result.success}")
        if result.success:
            print(f"  Status: {result.status_code}")
            print(f"  Time: {result.response_time_ms:.2f}ms")
        else:
            print(f"  Error: {result.error_message}")
        print()

    print()


async def custom_configuration_example():
    """Example: Check endpoint with custom configuration."""
    print("=" * 60)
    print("Example 3: Custom Configuration")
    print("=" * 60)

    # Example with custom headers, timeout, and acceptable status codes
    result = await check_endpoint_connectivity(
        endpoint_url="https://prometheus.example.com/api/v1/query",
        timeout_seconds=5.0,
        method="GET",
        headers={
            "Authorization": "Bearer your-token",
            "Accept": "application/json",
        },
        expected_status_codes=[200, 202],  # Accept 200 or 202
        verify_ssl=True,
    )

    print(f"Endpoint: https://prometheus.example.com/api/v1/query")
    print(f"Success: {result.success}")
    print(f"Status Code: {result.status_code}")
    print(f"Response Time: {result.response_time_ms:.2f}ms")

    if result.success:
        print("✅ Endpoint is reachable and responding correctly")
    else:
        print(f"❌ Endpoint check failed: {result.error_message}")

    print()


def synchronous_example():
    """Example: Using the synchronous wrapper."""
    print("=" * 60)
    print("Example 4: Synchronous Wrapper")
    print("=" * 60)

    result = check_endpoint_connectivity_sync(
        endpoint_url="http://localhost:9090/api/v1/query?query=up",
        timeout_seconds=10.0,
    )

    print(f"Endpoint: http://localhost:9090/api/v1/query?query=up")
    print(f"Success: {result.success}")
    print(f"Status Code: {result.status_code}")
    print(f"Response Time: {result.response_time_ms:.2f}ms")

    print()


async def real_world_pbx_whisper_check():
    """Example: Real-world pbx-web and whisper-stt metrics check."""
    print("=" * 60)
    print("Example 5: Real-world pbx-web & whisper-stt Check")
    print("=" * 60)

    # Typical Prometheus queries for pbx-web and whisper-stt
    endpoints = [
        {
            "name": "pbx-web-status",
            "url": "http://localhost:9090/api/v1/query?query=up{job='pbx-web'}",
            "headers": {"Accept": "application/json"},
        },
        {
            "name": "whisper-stt-status",
            "url": "http://localhost:9090/api/v1/query?query=up{job='whisper-stt'}",
            "headers": {"Accept": "application/json"},
        },
        {
            "name": "pbx-web-metrics",
            "url": "http://pbx-web:9090/metrics",
            "headers": {"Accept": "text/plain"},
        },
        {
            "name": "whisper-stt-metrics",
            "url": "http://whisper-stt:9090/metrics",
            "headers": {"Accept": "text/plain"},
        },
    ]

    results = await check_metrics_endpoints(endpoints, timeout_seconds=30.0)

    print(f"Checked {len(results)} pbx-web and whisper-stt endpoints:\n")

    success_count = sum(1 for r in results.values() if r.success)
    print(f"Results: {success_count}/{len(results)} successful\n")

    for name, result in results.items():
        status = "✅" if result.success else "❌"
        print(f"{status} {name}")
        if result.success:
            print(f"   Status: {result.status_code}, Time: {result.response_time_ms:.2f}ms")
        else:
            print(f"   Error: {result.error_message}")

    print()


async def main():
    """Run example demonstrations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Examples of endpoint connectivity utility usage"
    )
    parser.add_argument(
        "--single",
        action="store_true",
        help="Run single endpoint check example"
    )
    parser.add_argument(
        "--multiple",
        action="store_true",
        help="Run multiple endpoints check example"
    )
    parser.add_argument(
        "--custom",
        action="store_true",
        help="Run custom configuration example"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run synchronous wrapper example"
    )
    parser.add_argument(
        "--real-world",
        action="store_true",
        help="Run real-world pbx-web & whisper-stt example"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all examples"
    )

    args = parser.parse_args()

    if args.single or args.all:
        await check_single_endpoint_example()

    if args.multiple or args.all:
        await check_multiple_endpoints_example()

    if args.custom or args.all:
        await custom_configuration_example()

    if args.sync or args.all:
        synchronous_example()

    if args.real_world or args.all:
        await real_world_pbx_whisper_check()

    if not any(vars(args).values()):
        print("No example selected. Use --help to see options.")
        print("\nQuick demo -- running single endpoint check...")
        await check_single_endpoint_example()


if __name__ == "__main__":
    asyncio.run(main())
