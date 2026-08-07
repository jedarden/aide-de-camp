#!/usr/bin/env python3
"""
Simple test to check classification behavior
"""
import asyncio
import httpx
import json

async def main():
    utterance = "how are the pods doing"
    session_id = "test-simple-session"

    print("=" * 80)
    print("Testing Classification Consistency")
    print("=" * 80)
    print(f"Utterance: {utterance}")
    print(f"Session ID: {session_id}")
    print()

    # Test 1: Call classify endpoint first
    print("1. Calling /api/v1/test/intent-classify first...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/test/intent-classify",
            json={"utterance": utterance},
            timeout=30.0
        )
        classify_result1 = response.json()
        print(f"Result: {json.dumps(classify_result1, indent=2)}")

    # Test 2: Call dispatch endpoint with same session_id
    print(f"\n2. Calling /api/v1/test/dispatch with same session_id...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "surface_id": "test-surface",
                "wait_for_results": True,
                "timeout_seconds": 30,
            },
            timeout=60.0
        )
        dispatch_result = response.json()
        if dispatch_result.get("results"):
            result = dispatch_result["results"][0]
            print(f"Intent type from dispatch: {result.get('intent_type')}")
            print(f"Project slug from dispatch: {result.get('project_slug')}")

    # Test 3: Call classify endpoint again
    print(f"\n3. Calling /api/v1/test/intent-classify again...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/test/intent-classify",
            json={"utterance": utterance},
            timeout=30.0
        )
        classify_result2 = response.json()
        print(f"Result: {json.dumps(classify_result2, indent=2)}")

    # Compare
    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)

    classify_type1 = classify_result1["classifications"][0]["intent_type"]
    dispatch_type = dispatch_result["results"][0]["intent_type"] if dispatch_result.get("results") else None
    classify_type2 = classify_result2["classifications"][0]["intent_type"]

    print(f"Classify #1: {classify_type1}")
    print(f"Dispatch:    {dispatch_type}")
    print(f"Classify #2: {classify_type2}")

    if classify_type1 == dispatch_type == classify_type2:
        print("\n✓ PASS: All endpoints return the same intent_type")
    else:
        print(f"\n✗ FAIL: Endpoints return different intent_types")

if __name__ == "__main__":
    asyncio.run(main())
