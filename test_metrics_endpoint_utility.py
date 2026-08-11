#!/usr/bin/env python3
"""
Metrics Endpoint Connectivity Test Utility

Demonstrates usage of the check_endpoint_connectivity utility for testing
pbx-web and whisper-stt metrics endpoints.

This script provides a simple, reusable function for checking HTTP connectivity
to metrics endpoints with proper timeout handling and error reporting.
"""

import asyncio
import sys
from typing import Dict, Any, Optional
from datetime import datetime

# Import the connectivity utilities
from src.test.utilities import (
    check_endpoint_connectivity,
    check_metrics_endpoints,
    EndpointConnectivityResult,
)


def format_result(result: EndpointConnectivityResult, indent: int = 0) -> str:
    """Format a connectivity result for display."""
    prefix = " " * indent
    lines = []

    if result.success:
        lines.append(f"{prefix}✓ SUCCESS - HTTP {result.status_code}")
        lines.append(f"{prefix}  Response time: {result.response_time_ms:.2f}ms")
        if result.response_body:
            body_preview = result.response_body[:100]
            if len(result.response_body) > 100:
                body_preview += "..."
            lines.append(f"{prefix}  Response preview: {body_preview}")
    else:
        lines.append(f"{prefix}✗ FAILED")
        lines.append(f"{prefix}  Error: {result.error_message}")
        if result.status_code:
            lines.append(f"{prefix}  HTTP Status: {result.status_code}")

    return "\n".join(lines)


async def test_prometheus_connectivity(
    prometheus_ip: str = "10.43.253.70",
    prometheus_port: int = 9090,
) -> Dict[str, Any]:
    """
    Test basic connectivity to Prometheus server.

    Args:
        prometheus_ip: Prometheus server IP address
        prometheus_port: Prometheus server port

    Returns:
        Dictionary with test results
    """
    print(f"\n{'='*70}")
    print("PROMETHEUS CONNECTIVITY TEST")
    print(f"{'='*70}")
    print(f"Target: {prometheus_ip}:{prometheus_port}")
    print(f"Time: {datetime.now().isoformat()}")

    base_url = f"http://{prometheus_ip}:{prometheus_port}"

    # Test 1: Basic API health check
    print(f"\n1. Testing Prometheus API health endpoint...")
    result = await check_endpoint_connectivity(
        endpoint_url=f"{base_url}/api/v1/query?query=up",
        timeout_seconds=30.0,
        expected_status_codes=[200],
        verify_ssl=False,  # Prometheus typically uses HTTP
    )

    print(format_result(result, indent=3))

    return {
        "test": "prometheus_api_health",
        "result": result.to_dict(),
        "timestamp": datetime.now().isoformat(),
    }


async def test_pbx_web_metrics(
    prometheus_ip: str = "10.43.253.70",
    prometheus_port: int = 9090,
) -> Dict[str, Any]:
    """
    Test pbx-web namespace metrics availability.

    Args:
        prometheus_ip: Prometheus server IP address
        prometheus_port: Prometheus server port

    Returns:
        Dictionary with test results
    """
    print(f"\n2. Testing pbx-web namespace metrics...")

    base_url = f"http://{prometheus_ip}:{prometheus_port}"
    query = 'up{namespace="pbx-web"}'

    # URL encode the query
    import urllib.parse
    encoded_query = urllib.parse.quote(query)

    result = await check_endpoint_connectivity(
        endpoint_url=f"{base_url}/api/v1/query?query={encoded_query}",
        timeout_seconds=30.0,
        expected_status_codes=[200],
        verify_ssl=False,
    )

    print(format_result(result, indent=3))

    # If successful, try to parse and show metrics count
    if result.success and result.response_body:
        try:
            import json
            data = json.loads(result.response_body)
            result_count = len(data.get("data", {}).get("result", []))
            print(f"     Metrics returned: {result_count} data points")

            if result_count > 0:
                sample = data["data"]["result"][0]
                print(f"     Sample metric: {sample.get('metric', {})}")

        except json.JSONDecodeError as e:
            print(f"     ⚠ JSON parsing error: {e}")

    return {
        "test": "pbx_web_metrics",
        "result": result.to_dict(),
        "timestamp": datetime.now().isoformat(),
    }


async def test_whisper_stt_metrics(
    prometheus_ip: str = "10.43.253.70",
    prometheus_port: int = 9090,
) -> Dict[str, Any]:
    """
    Test whisper-stt namespace metrics availability.

    Args:
        prometheus_ip: Prometheus server IP address
        prometheus_port: Prometheus server port

    Returns:
        Dictionary with test results
    """
    print(f"\n3. Testing whisper-stt namespace metrics...")

    base_url = f"http://{prometheus_ip}:{prometheus_port}"
    query = 'up{namespace="whisper-stt"}'

    # URL encode the query
    import urllib.parse
    encoded_query = urllib.parse.quote(query)

    result = await check_endpoint_connectivity(
        endpoint_url=f"{base_url}/api/v1/query?query={encoded_query}",
        timeout_seconds=30.0,
        expected_status_codes=[200],
        verify_ssl=False,
    )

    print(format_result(result, indent=3))

    # If successful, try to parse and show metrics count
    if result.success and result.response_body:
        try:
            import json
            data = json.loads(result.response_body)
            result_count = len(data.get("data", {}).get("result", []))
            print(f"     Metrics returned: {result_count} data points")

            if result_count > 0:
                sample = data["data"]["result"][0]
                print(f"     Sample metric: {sample.get('metric', {})}")

        except json.JSONDecodeError as e:
            print(f"     ⚠ JSON parsing error: {e}")

    return {
        "test": "whisper_stt_metrics",
        "result": result.to_dict(),
        "timestamp": datetime.now().isoformat(),
    }


async def test_all_endpoints_concurrent(
    prometheus_ip: str = "10.43.253.70",
    prometheus_port: int = 9090,
) -> Dict[str, Any]:
    """
    Test all endpoints concurrently for faster results.

    This demonstrates the check_metrics_endpoints function which runs
    multiple endpoint checks in parallel.

    Args:
        prometheus_ip: Prometheus server IP address
        prometheus_port: Prometheus server port

    Returns:
        Dictionary with all test results
    """
    print(f"\n{'='*70}")
    print("CONCURRENT METRICS ENDPOINTS TEST")
    print(f"{'='*70}")
    print(f"Target: {prometheus_ip}:{prometheus_port}")
    print(f"Time: {datetime.now().isoformat()}")

    base_url = f"http://{prometheus_ip}:{prometheus_port}"

    # URL encode queries
    import urllib.parse

    endpoints = [
        {
            "name": "prometheus_health",
            "url": f"{base_url}/api/v1/query?query=up",
        },
        {
            "name": "pbx_web",
            "url": f"{base_url}/api/v1/query?query={urllib.parse.quote('up{namespace=\"pbx-web\"}')}",
        },
        {
            "name": "whisper_stt",
            "url": f"{base_url}/api/v1/query?query={urllib.parse.quote('up{namespace=\"whisper-stt\"}')}",
        },
    ]

    print(f"\nTesting {len(endpoints)} endpoints concurrently...")

    results = await check_metrics_endpoints(
        endpoints=endpoints,
        timeout_seconds=30.0,
    )

    print(f"\nResults:")
    for name, result in results.items():
        print(f"\n{name}:")
        print(format_result(result, indent=3))

    return {
        "concurrent_test": True,
        "timestamp": datetime.now().isoformat(),
        "results": {name: result.to_dict() for name, result in results.items()},
    }


async def main():
    """Run all metrics endpoint connectivity tests."""
    print(f"\n{'='*70}")
    print("METRICS ENDPOINT CONNECTIVITY TEST UTILITY")
    print(f"{'='*70}")
    print(f"This utility demonstrates reusable endpoint connectivity testing")
    print(f"for pbx-web and whisper-stt metrics endpoints.")

    # Configuration
    prometheus_ip = "10.43.253.70"
    prometheus_port = 9090

    # Run sequential tests
    prometheus_result = await test_prometheus_connectivity(prometheus_ip, prometheus_port)
    pbx_web_result = await test_pbx_web_metrics(prometheus_ip, prometheus_port)
    whisper_stt_result = await test_whisper_stt_metrics(prometheus_ip, prometheus_port)

    # Run concurrent tests
    concurrent_results = await test_all_endpoints_concurrent(prometheus_ip, prometheus_port)

    # Summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}")

    all_results = {
        "prometheus": prometheus_result,
        "pbx_web": pbx_web_result,
        "whisper_stt": whisper_stt_result,
        "concurrent": concurrent_results,
    }

    for test_name, result in all_results.items():
        if "result" in result:
            success = result["result"]["success"]
            status = "✓ PASSED" if success else "✗ FAILED"
            print(f"{test_name:20s}: {status}")
        else:
            print(f"{test_name:20s}: (composite test)")

    return all_results


if __name__ == "__main__":
    try:
        results = asyncio.run(main())
        print(f"\n{'='*70}")
        print("Test completed successfully")
        print(f"{'='*70}")
        sys.exit(0)

    except KeyboardInterrupt:
        print(f"\n\nTest interrupted by user")
        sys.exit(1)

    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
