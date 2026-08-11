#!/usr/bin/env python3
"""
Debug script to test different Prometheus queries and find working patterns
"""

import subprocess
import json
import sys
import re
from datetime import datetime

def test_query(description, query):
    """Test a single Prometheus query"""
    prometheus_ip = "10.43.253.70"

    # URL encode the query
    import urllib.parse
    encoded_query = urllib.parse.quote(query)

    print(f"\n{description}")
    print(f"Query: {query}")
    print(f"Encoded: {encoded_query}")

    cmd = f"""
    kubectl --server=http://traefik-ardenone-cluster:8001 run --rm -i --restart=Never curl-debug --image=curlimages/curl:latest --command -- curl -s 'http://{prometheus_ip}:9090/api/v1/query?query={encoded_query}'
    """

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            output = result.stdout.strip()

            # Parse response
            try:
                data = json.loads(output)

                if data.get("status") == "success":
                    result_count = len(data.get("data", {}).get("result", []))
                    print(f"✓ SUCCESS: {result_count} data points returned")

                    if result_count > 0:
                        print("Sample data:")
                        for i, item in enumerate(data["data"]["result"][:2]):
                            print(f"  {i+1}. {item.get('metric', {})} = {item.get('value', [])}")
                    return True, result_count
                else:
                    error = data.get("error", "Unknown error")
                    print(f"✗ FAILED: {error}")
                    return False, 0
            except json.JSONDecodeError as e:
                print(f"✗ JSON ERROR: {e}")
                print(f"Raw output (first 200 chars): {output[:200]}")
                return False, 0
        else:
            print(f"✗ COMMAND ERROR: {result.stderr}")
            return False, 0

    except subprocess.TimeoutExpired:
        print(f"✗ TIMEOUT (120s)")
        return False, 0
    except Exception as e:
        print(f"✗ EXCEPTION: {e}")
        return False, 0

def main():
    print("="*70)
    print("PROMETHEUS QUERY DEBUGGING")
    print("="*70)
    print(f"Time: {datetime.now().isoformat()}")

    # Test queries in order of complexity
    test_queries = [
        ("1. Basic up query (all namespaces)", "up"),
        ("2. Simple metric query", "up"),
        ("3. Prometheus self-monitoring", "prometheus_build_info"),
        ("4. pbx-web namespace filter", 'up{namespace="pbx-web"}'),
        ("5. whisper-stt namespace filter", 'up{namespace="whisper-stt"}'),
        ("6. Container CPU (pbx-web)", 'container_cpu_usage_seconds_total{namespace="pbx-web"}'),
        ("7. Container CPU (whisper-stt)", 'container_cpu_usage_seconds_total{namespace="whisper-stt"}'),
        ("8. All pbx-web metrics", '{__name__=~".*", namespace="pbx-web"}'),
        ("9. All whisper-stt metrics", '{__name__=~".*", namespace="whisper-stt"}'),
    ]

    results = []
    for desc, query in test_queries:
        success, count = test_query(desc, query)
        results.append({"description": desc, "query": query, "success": success, "count": count})

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    success_count = sum(1 for r in results if r["success"])
    print(f"Total queries: {len(results)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {len(results) - success_count}")

    print("\nDetailed results:")
    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"  {status} {r['description']}")
        if r["success"]:
            print(f"     Data points: {r['count']}")

    return 0 if success_count == len(results) else 1

if __name__ == "__main__":
    sys.exit(main())