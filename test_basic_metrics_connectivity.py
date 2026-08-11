#!/usr/bin/env python3
"""
Simple metrics endpoint connectivity test using direct HTTP queries
"""

import httpx
import json
import asyncio
from datetime import datetime

PROMETHEUS_URL = "http://10.43.253.70:9090"

async def test_prometheus_connectivity():
    """Test basic connectivity to Prometheus metrics endpoint"""

    print("="*70)
    print("METRICS ENDPOINT CONNECTIVITY TEST")
    print("="*70)
    print(f"Target: {PROMETHEUS_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print("="*70)

    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": []
    }

    async with httpx.AsyncClient(timeout=30.0) as client:

        # Test 1: Basic Prometheus API health
        print("\n1. Testing Prometheus API health...")
        try:
            response = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": "up"})
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Prometheus API reachable (HTTP 200)")
                print(f"   Response status: {data.get('status')}")

                results["tests"].append({
                    "test": "prometheus_health",
                    "status": "success",
                    "http_code": 200
                })
            else:
                print(f"   ✗ Unexpected status: {response.status_code}")
                results["tests"].append({
                    "test": "prometheus_health",
                    "status": "failed",
                    "http_code": response.status_code
                })
        except Exception as e:
            print(f"   ✗ Error: {e}")
            results["tests"].append({
                "test": "prometheus_health",
                "status": "error",
                "error": str(e)
            })

        # Test 2: Query available namespaces
        print("\n2. Testing available namespaces...")
        try:
            response = await client.get(f"{PROMETHEUS_URL}/api/v1/label/namespace/values")
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                namespaces = data.get('data', [])
                print(f"   ✓ Found {len(namespaces)} namespaces")
                print(f"   Sample namespaces: {namespaces[:5]}")

                # Check if our target namespaces exist
                has_pbx = "pbx-web" in namespaces
                has_whisper = "whisper-stt" in namespaces

                print(f"   pbx-web namespace: {'✓ Found' if has_pbx else '✗ Not found'}")
                print(f"   whisper-stt namespace: {'✓ Found' if has_whisper else '✗ Not found'}")

                results["tests"].append({
                    "test": "namespace_discovery",
                    "status": "success",
                    "http_code": 200,
                    "namespaces_found": len(namespaces),
                    "pbx_web_exists": has_pbx,
                    "whisper_stt_exists": has_whisper
                })
            else:
                print(f"   ✗ Failed to get namespaces")
                results["tests"].append({
                    "test": "namespace_discovery",
                    "status": "failed",
                    "http_code": response.status_code
                })
        except Exception as e:
            print(f"   ✗ Error: {e}")
            results["tests"].append({
                "test": "namespace_discovery",
                "status": "error",
                "error": str(e)
            })

        # Test 3: Simple up metric query (without namespace filter)
        print("\n3. Testing basic 'up' metric query...")
        try:
            response = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": "up"})
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                results_count = len(data.get('data', {}).get('result', []))
                print(f"   ✓ Basic query works, returned {results_count} data points")

                # Show sample metrics
                if results_count > 0:
                    sample = data['data']['result'][0]
                    metric_name = sample.get('metric', {}).get('__name__', 'unknown')
                    print(f"   Sample metric: {metric_name}")

                results["tests"].append({
                    "test": "basic_up_query",
                    "status": "success",
                    "http_code": 200,
                    "data_points": results_count
                })
            else:
                print(f"   ✗ Query failed")
                results["tests"].append({
                    "test": "basic_up_query",
                    "status": "failed",
                    "http_code": response.status_code
                })
        except Exception as e:
            print(f"   ✗ Error: {e}")
            results["tests"].append({
                "test": "basic_up_query",
                "status": "error",
                "error": str(e)
            })

        # Test 4: pbx-web specific query
        print("\n4. Testing pbx-web metrics...")
        try:
            response = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": 'up{namespace="pbx-web"}'})
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                results_count = len(data.get('data', {}).get('result', []))
                print(f"   ✓ pbx-web query returned {results_count} data points")

                if results_count > 0:
                    print(f"   ✓ pbx-web has active metrics")
                    sample = data['data']['result'][0].get('metric', {})
                    print(f"   Sample: {sample}")
                else:
                    print(f"   ⚠ No metrics data found for pbx-web")

                results["tests"].append({
                    "test": "pbx_web_metrics",
                    "status": "success",
                    "http_code": 200,
                    "data_points": results_count,
                    "has_data": results_count > 0
                })
            else:
                print(f"   ✗ Query failed with status {response.status_code}")
                if response.status_code == 400:
                    print(f"   (This might mean namespace doesn't exist or has no metrics)")
                results["tests"].append({
                    "test": "pbx_web_metrics",
                    "status": "failed",
                    "http_code": response.status_code
                })
        except Exception as e:
            print(f"   ✗ Error: {e}")
            results["tests"].append({
                "test": "pbx_web_metrics",
                "status": "error",
                "error": str(e)
            })

        # Test 5: whisper-stt specific query
        print("\n5. Testing whisper-stt metrics...")
        try:
            response = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": 'up{namespace="whisper-stt"}'})
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                results_count = len(data.get('data', {}).get('result', []))
                print(f"   ✓ whisper-stt query returned {results_count} data points")

                if results_count > 0:
                    print(f"   ✓ whisper-stt has active metrics")
                    sample = data['data']['result'][0].get('metric', {})
                    print(f"   Sample: {sample}")
                else:
                    print(f"   ⚠ No metrics data found for whisper-stt")

                results["tests"].append({
                    "test": "whisper_stt_metrics",
                    "status": "success",
                    "http_code": 200,
                    "data_points": results_count,
                    "has_data": results_count > 0
                })
            else:
                print(f"   ✗ Query failed with status {response.status_code}")
                if response.status_code == 400:
                    print(f"   (This might mean namespace doesn't exist or has no metrics)")
                results["tests"].append({
                    "test": "whisper_stt_metrics",
                    "status": "failed",
                    "http_code": response.status_code
                })
        except Exception as e:
            print(f"   ✗ Error: {e}")
            results["tests"].append({
                "test": "whisper_stt_metrics",
                "status": "error",
                "error": str(e)
            })

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    success_count = sum(1 for test in results["tests"] if test["status"] == "success")
    total_count = len(results["tests"])

    print(f"Total tests: {total_count}")
    print(f"Successful: {success_count}")
    print(f"Failed: {total_count - success_count}")

    for test in results["tests"]:
        status_symbol = "✓" if test["status"] == "success" else "✗"
        print(f"  {status_symbol} {test['test']}: {test['status']}")
        if "http_code" in test:
            print(f"     HTTP: {test['http_code']}")
        if "data_points" in test:
            print(f"     Data points: {test['data_points']}")
        if "error" in test:
            print(f"     Error: {test['error']}")

    # Save results
    import pathlib
    output_dir = pathlib.Path("/home/coding/aide-de-camp/data")
    output_dir.mkdir(parents=True, exist_ok=True)

    results_file = output_dir / f"basic-connectivity-test-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Results saved to: {results_file}")

    return results

if __name__ == "__main__":
    asyncio.run(test_prometheus_connectivity())