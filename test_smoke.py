#!/usr/bin/env python3
"""
ADC Smoke Test - Core verification of server functionality

Tests:
1. Server process running
2. Health endpoint responding
3. Canvas HTML loads
4. SSE endpoint accessible
5. Test dispatch endpoint works
"""
import subprocess
import time
import json
import sys
import uuid
from pathlib import Path

import httpx


def check_server_running():
    """Check if uvicorn process is running."""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True
        )
        return "uvicorn src.main:app" in result.stdout
    except Exception as e:
        print(f"❌ Failed to check process: {e}")
        return False


def test_health_endpoint():
    """Test /health endpoint."""
    try:
        response = httpx.get("http://localhost:8000/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        assert data.get("status") == "ok", f"Expected status='ok', got {data}"
        assert data.get("service") == "adc-voice", f"Expected service='adc-voice', got {data}"
        print(f"✅ Health endpoint: {data}")
        return True
    except Exception as e:
        print(f"❌ Health endpoint failed: {e}")
        return False


def test_canvas_loads():
    """Test canvas HTML loads."""
    try:
        response = httpx.get("http://localhost:8000/", timeout=5)
        response.raise_for_status()
        html = response.text
        assert "<!DOCTYPE html>" in html, "No DOCTYPE"
        assert "ADC (aide-de-camp) - Canvas" in html, "No canvas title"
        assert "topicsContainer" in html, "No topics container"
        print("✅ Canvas HTML loads correctly")
        return True
    except Exception as e:
        print(f"❌ Canvas load failed: {e}")
        return False


def test_sse_endpoint():
    """Test SSE endpoint is accessible."""
    try:
        # SSE requires session_id, should return proper error when missing
        response = httpx.get("http://localhost:8000/api/v1/sse", timeout=5)
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✅ SSE endpoint accessible (returns 422 without session_id as expected)")
        return True
    except Exception as e:
        print(f"❌ SSE endpoint test failed: {e}")
        return False


def test_list_utterances():
    """Test test utterances endpoint."""
    try:
        response = httpx.get("http://localhost:8000/api/v1/test/utterances", timeout=5)
        response.raise_for_status()
        data = response.json()
        assert "utterances" in data, "No utterances in response"
        assert len(data["utterances"]) > 0, "No utterances listed"
        print(f"✅ Test utterances endpoint: {len(data['utterances'])} utterances available")
        return True
    except Exception as e:
        print(f"❌ Test utterances endpoint failed: {e}")
        return False


def test_simple_dispatch():
    """Test a simple dispatch without waiting for results."""
    try:
        session_id = str(uuid.uuid4())
        surface_id = str(uuid.uuid4())

        payload = {
            "utterance": "hello world test",
            "session_id": session_id,
            "surface_id": surface_id,
            "wait_for_results": False
        }

        response = httpx.post(
            "http://localhost:8000/api/v1/test/dispatch",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        assert data.get("status") in ("dispatched", "completed"), f"Unexpected status: {data.get('status')}"
        assert "intent_count" in data, "No intent_count in response"
        assert "utterance_id" in data, "No utterance_id in response"

        print(f"✅ Simple dispatch: {data['intent_count']} intents, utterance_id={data['utterance_id'][:8]}...")
        return True
    except Exception as e:
        print(f"❌ Simple dispatch failed: {e}")
        return False


def run_smoke_test():
    """Run all smoke tests."""
    print("🚀 ADC Smoke Test Starting...")
    print("=" * 60)

    tests = [
        ("Server process running", check_server_running),
        ("Health endpoint", test_health_endpoint),
        ("Canvas loads", test_canvas_loads),
        ("SSE endpoint", test_sse_endpoint),
        ("Test utterances list", test_list_utterances),
        ("Simple dispatch", test_simple_dispatch),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n📋 Testing: {name}")
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"💥 Test crashed: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("📊 Smoke Test Results:")
    print("=" * 60)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    print("=" * 60)
    print(f"Total: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("🎉 All smoke tests PASSED")
        return 0
    else:
        print("⚠️  Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_test())