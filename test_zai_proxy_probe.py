#!/usr/bin/env python3
"""
Minimal ZAI Proxy Probe

Tests if the ZAI proxy is up and accepting requests before running E2E tests.
This is a health check to catch proxy outages early.
"""
import asyncio
import sys
import time
import json

import httpx


# ZAI proxy endpoint
ZAI_PROXY_URL = "https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages"


async def probe_zai_proxy() -> dict:
    """
    Probe the ZAI proxy with a minimal POST request.

    Returns:
        dict with keys: success (bool), status_code (int|None), error (str|None), latency_ms (float)
    """
    start_time = time.monotonic()

    try:
        # Create a minimal valid payload
        # The proxy expects an Anthropic-like API format
        payload = {
            "model": "claude-haiku-4-20250514",
            "max_tokens": 10,
            "messages": [
                {"role": "user", "content": "hi"}
            ],
        }

        print(f"🔍 Probing ZAI proxy at: {ZAI_PROXY_URL}")

        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            response = await client.post(
                ZAI_PROXY_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            latency_ms = (time.monotonic() - start_time) * 1000

            print(f"📡 Response status: {response.status_code}")
            print(f"⏱️  Latency: {latency_ms:.0f}ms")

            # Check if status code indicates the proxy is up
            # 2xx = success
            # 401/403 = proxy is up but auth failed (expected for minimal probe)
            # 5xx = proxy is up but internal error
            # 503 specifically = "no available server" (known outage mode)
            if 200 <= response.status_code < 500:
                # Proxy is accepting requests (even if it rejects the payload)
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "error": None,
                    "latency_ms": latency_ms,
                }
            elif response.status_code == 503:
                # Known outage mode from 2026-06-10
                error_msg = "Proxy returned 503 'no available server'"
                try:
                    error_detail = response.json()
                    error_msg += f": {error_detail}"
                except:
                    pass
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": error_msg,
                    "latency_ms": latency_ms,
                }
            else:
                # Server error (5xx)
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": f"Proxy returned {response.status_code}",
                    "latency_ms": latency_ms,
                }

    except httpx.ConnectError as e:
        latency_ms = (time.monotonic() - start_time) * 1000
        error_msg = f"Connection failed: {e}"
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "status_code": None,
            "error": error_msg,
            "latency_ms": latency_ms,
        }
    except httpx.TimeoutException as e:
        latency_ms = (time.monotonic() - start_time) * 1000
        error_msg = f"Request timed out: {e}"
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "status_code": None,
            "error": error_msg,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        latency_ms = (time.monotonic() - start_time) * 1000
        error_msg = f"Unexpected error: {e}"
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "status_code": None,
            "error": error_msg,
            "latency_ms": latency_ms,
        }


async def main():
    """Main entry point."""
    print("🚀 ZAI Proxy Health Check")
    print("=" * 60)

    result = await probe_zai_proxy()

    print("\n" + "=" * 60)
    if result["success"]:
        print("✅ PROBE PASSED")
        print("=" * 60)
        print(f"✅ ZAI proxy is accepting requests")
        print(f"   Status: {result['status_code']}")
        print(f"   Latency: {result['latency_ms']:.0f}ms")
        return 0
    else:
        print("❌ PROBE FAILED")
        print("=" * 60)
        print(f"❌ ZAI proxy is NOT accepting requests")
        print(f"   Error: {result['error']}")
        print(f"   Status: {result['status_code']}")
        print(f"   Latency: {result['latency_ms']:.0f}ms")
        print("\n⚠️  Recommendation: Create/extend an infra bead for proxy outage")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
