#!/usr/bin/env python3
"""
ZAI Proxy Probe

Simple health check for the ZAI proxy before running E2E tests.
This tests if the proxy is up and accepting requests.
"""
import asyncio
import sys
import os
import httpx
import time

# ZAI proxy endpoint
ZAI_PROXY_URL = os.environ.get(
    "ZAI_PROXY_URL",
    "https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages",
)

# Minimal test payload - smallest possible request
MINIMAL_PAYLOAD = {
    "model": "claude-haiku-4-20250514",
    "max_tokens": 10,
    "temperature": 0.7,
    "system": "You are a helpful assistant.",
    "messages": [
        {"role": "user", "content": "Hi"}
    ],
}


async def probe_zai_proxy() -> dict:
    """
    Probe the ZAI proxy with a minimal POST request.

    Returns:
        dict with keys: success (bool), status_code (int|None), error (str|None), latency_ms (float)
    """
    result = {
        "success": False,
        "status_code": None,
        "error": None,
        "latency_ms": 0.0,
    }

    print(f"🔍 Probing ZAI proxy at: {ZAI_PROXY_URL}")
    print(f"📤 Sending minimal POST request...")

    start_time = time.monotonic()

    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            response = await client.post(
                ZAI_PROXY_URL,
                json=MINIMAL_PAYLOAD,
                headers={"Content-Type": "application/json"},
            )

            elapsed_ms = (time.monotonic() - start_time) * 1000
            result["latency_ms"] = elapsed_ms
            result["status_code"] = response.status_code

            # Check for 2xx response
            if 200 <= response.status_code < 300:
                result["success"] = True
                print(f"✅ Proxy responded with HTTP {response.status_code} ({elapsed_ms:.0f}ms)")

                # Try to parse response to verify it's valid
                try:
                    data = response.json()
                    print(f"✅ Response is valid JSON")

                    # Check for expected ZAI proxy wrapping
                    if "result" in data:
                        print(f"✅ Response has ZAI proxy wrapper structure")
                    else:
                        print(f"⚠️  Response missing expected 'result' wrapper")

                except Exception as e:
                    print(f"⚠️  Response body not valid JSON: {e}")

            else:
                result["error"] = f"HTTP {response.status_code}"
                print(f"❌ Proxy returned HTTP {response.status_code}")
                print(f"   Response: {response.text[:200]}")

    except httpx.ConnectTimeout as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        result["latency_ms"] = elapsed_ms
        result["error"] = f"Connection timeout: {e}"
        print(f"❌ Connection timeout after {elapsed_ms:.0f}ms")

    except httpx.ReadTimeout as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        result["latency_ms"] = elapsed_ms
        result["error"] = f"Read timeout: {e}"
        print(f"❌ Read timeout after {elapsed_ms:.0f}ms")

    except httpx.ConnectError as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        result["latency_ms"] = elapsed_ms
        result["error"] = f"Connection error: {e}"
        print(f"❌ Connection failed: {e}")

    except httpx.HTTPStatusError as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        result["latency_ms"] = elapsed_ms
        result["status_code"] = e.response.status_code
        result["error"] = f"HTTP status error: {e}"
        print(f"❌ HTTP status error: {e.response.status_code}")

    except Exception as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        result["latency_ms"] = elapsed_ms
        result["error"] = f"Unexpected error: {e}"
        print(f"❌ Unexpected error: {e}")

    return result


async def main():
    """Main entry point."""
    print("=" * 60)
    print("ZAI Proxy Health Check")
    print("=" * 60)

    result = await probe_zai_proxy()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    if result["success"]:
        print(f"✅ PASS: ZAI proxy is up and accepting requests")
        print(f"   Latency: {result['latency_ms']:.0f}ms")
        print(f"   Status: HTTP {result['status_code']}")
        return 0
    else:
        print(f"❌ FAIL: ZAI proxy probe failed")
        if result["status_code"]:
            print(f"   Status: HTTP {result['status_code']}")
        if result["error"]:
            print(f"   Error: {result['error']}")
        if result["latency_ms"] > 0:
            print(f"   Latency: {result['latency_ms']:.0f}ms")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
