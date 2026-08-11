#!/usr/bin/env python3
"""
Simple connectivity test for pbx-web and whisper-stt metrics endpoints

Tests basic HTTP connectivity to Prometheus metrics endpoints for both services.
"""

import subprocess
import json
import sys
from datetime import datetime

def test_basic_prometheus_connectivity():
    """Test basic connectivity to Prometheus"""
    prometheus_ip = "10.43.253.70"

    print("="*70)
    print("METRICS ENDPOINT CONNECTIVITY TEST")
    print("="*70)
    print(f"Target Prometheus: {prometheus_ip}:9090")
    print(f"Test Time: {datetime.now().isoformat()}")
    print(f"Services: pbx-web, whisper-stt")
    print("="*70)

    results = {
        "test_metadata": {
            "timestamp": datetime.now().isoformat(),
            "prometheus_ip": prometheus_ip,
            "services_tested": ["pbx-web", "whisper-stt"]
        },
        "connectivity_tests": []
    }

    # Test 1: Basic Prometheus API health check
    print("\n1. Testing Prometheus API health endpoint...")
    try:
        cmd = f"""
        kubectl --server=http://traefik-ardenone-cluster:8001 run --rm -i --restart=Never curl-test --image=curlimages/curl:latest --command -- curl -s -w '\\n%{{http_code}}' http://{prometheus_ip}:9090/api/v1/query?query=up
        """

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            output = result.stdout.strip()

            # Extract HTTP status code (last 3 digits before any pod deletion messages)
            # Look for patterns like "200" or "200pod" and extract the numeric part
            import re
            status_match = re.search(r'(\d{3})(?:pod|\s)', output)
            if status_match:
                http_status = status_match.group(1)
                # Remove the status line and any kubectl messages from JSON response
                lines = output.split('\n')
                json_response_lines = []
                for line in lines:
                    # Skip lines that are just status codes or contain kubectl messages
                    if not re.match(r'^\d{3}', line) and 'deleted from default namespace' not in line and 'pod "' not in line.lower():
                        json_response_lines.append(line)
                json_response = '\n'.join(json_response_lines).strip()
            else:
                http_status = "000"
                json_response = output

            print(f"   HTTP Status: {http_status}")

            if http_status == "200":
                print(f"   ✓ Prometheus API is reachable (HTTP 200)")

                # Try to parse JSON
                try:
                    data = json.loads(json_response)
                    status = data.get("status")
                    print(f"   ✓ Response status: {status}")
                    print(f"   ✓ Basic connectivity confirmed")

                    results["connectivity_tests"].append({
                        "test": "prometheus_api_health",
                        "status": "success",
                        "http_code": 200,
                        "response_status": status
                    })
                except json.JSONDecodeError as e:
                    print(f"   ⚠ JSON parsing error: {e}")
                    print(f"   Raw response length: {len(json_response)} chars")
                    results["connectivity_tests"].append({
                        "test": "prometheus_api_health",
                        "status": "partial_success",
                        "http_code": 200,
                        "error": "json_parse_error",
                        "error_detail": str(e)
                    })
            else:
                print(f"   ✗ Unexpected HTTP status: {http_status}")
                results["connectivity_tests"].append({
                    "test": "prometheus_api_health",
                    "status": "failed",
                    "http_code": int(http_status) if http_status.isdigit() else "unknown"
                })
        else:
            print(f"   ✗ Command failed: {result.stderr}")
            results["connectivity_tests"].append({
                "test": "prometheus_api_health",
                "status": "command_failed",
                "error": result.stderr
            })

    except subprocess.TimeoutExpired:
        print(f"   ✗ Command timed out (120s)")
        results["connectivity_tests"].append({
            "test": "prometheus_api_health",
            "status": "timeout"
        })
    except Exception as e:
        print(f"   ✗ Exception: {e}")
        results["connectivity_tests"].append({
            "test": "prometheus_api_health",
            "status": "exception",
            "error": str(e)
        })

    # Test 2: pbx-web namespace metrics
    print("\n2. Testing pbx-web namespace metrics...")
    try:
        query = 'up{namespace="pbx-web"}'
        encoded_query = subprocess.run(['python3', '-c', f'import urllib.parse; print(urllib.parse.quote("{query}"))'],
                                      capture_output=True, text=True).stdout.strip()

        cmd = f"""
        kubectl --server=http://traefik-ardenone-cluster:8001 run --rm -i --restart=Never curl-pbx --image=curlimages/curl:latest --command -- curl -s -w '\\n%{{http_code}}' 'http://{prometheus_ip}:9090/api/v1/query?query={encoded_query}'
        """

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            output = result.stdout.strip()

            # Extract HTTP status code (last 3 digits before any pod deletion messages)
            import re
            status_match = re.search(r'(\d{3})(?:pod|\s)', output)
            if status_match:
                http_status = status_match.group(1)
                # Remove the status line and any kubectl messages from JSON response
                lines = output.split('\n')
                json_response_lines = []
                for line in lines:
                    # Skip lines that are just status codes or contain kubectl messages
                    if not re.match(r'^\d{3}', line) and 'deleted from default namespace' not in line and 'pod "' not in line.lower():
                        json_response_lines.append(line)
                json_response = '\n'.join(json_response_lines).strip()
            else:
                http_status = "000"
                json_response = output

            print(f"   HTTP Status: {http_status}")

            if http_status == "200":
                print(f"   ✓ pbx-web metrics endpoint reachable (HTTP 200)")

                # Check if we got data
                try:
                    data = json.loads(json_response)
                    result_count = len(data.get("data", {}).get("result", []))
                    print(f"   ✓ Metrics returned: {result_count} data points")

                    results["connectivity_tests"].append({
                        "test": "pbx_web_metrics",
                        "status": "success",
                        "http_code": 200,
                        "data_points": result_count
                    })

                    if result_count > 0:
                        print(f"   ✓ pbx-web has active metrics")
                        # Show sample data
                        sample = data["data"]["result"][0]
                        print(f"   Sample metric: {sample.get('metric', {})}")
                    else:
                        print(f"   ⚠ No metrics data found for pbx-web namespace")

                except json.JSONDecodeError as e:
                    print(f"   ⚠ JSON parsing error: {e}")
                    results["connectivity_tests"].append({
                        "test": "pbx_web_metrics",
                        "status": "partial_success",
                        "http_code": 200,
                        "error": "json_parse_error"
                    })
            else:
                print(f"   ✗ Unexpected HTTP status: {http_status}")
                results["connectivity_tests"].append({
                    "test": "pbx_web_metrics",
                    "status": "failed",
                    "http_code": int(http_status) if http_status.isdigit() else "unknown"
                })
        else:
            print(f"   ✗ Command failed: {result.stderr}")
            results["connectivity_tests"].append({
                "test": "pbx_web_metrics",
                "status": "command_failed"
            })

    except Exception as e:
        print(f"   ✗ Exception: {e}")
        results["connectivity_tests"].append({
            "test": "pbx_web_metrics",
            "status": "exception",
            "error": str(e)
        })

    # Test 3: whisper-stt namespace metrics
    print("\n3. Testing whisper-stt namespace metrics...")
    try:
        query = 'up{namespace="whisper-stt"}'
        encoded_query = subprocess.run(['python3', '-c', f'import urllib.parse; print(urllib.parse.quote("{query}"))'],
                                      capture_output=True, text=True).stdout.strip()

        cmd = f"""
        kubectl --server=http://traefik-ardenone-cluster:8001 run --rm -i --restart=Never curl-whisper --image=curlimages/curl:latest --command -- curl -s -w '\\n%{{http_code}}' 'http://{prometheus_ip}:9090/api/v1/query?query={encoded_query}'
        """

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            output = result.stdout.strip()

            # Extract HTTP status code (last 3 digits before any pod deletion messages)
            import re
            status_match = re.search(r'(\d{3})(?:pod|\s)', output)
            if status_match:
                http_status = status_match.group(1)
                # Remove the status line and any kubectl messages from JSON response
                lines = output.split('\n')
                json_response_lines = []
                for line in lines:
                    # Skip lines that are just status codes or contain kubectl messages
                    if not re.match(r'^\d{3}', line) and 'deleted from default namespace' not in line and 'pod "' not in line.lower():
                        json_response_lines.append(line)
                json_response = '\n'.join(json_response_lines).strip()
            else:
                http_status = "000"
                json_response = output

            print(f"   HTTP Status: {http_status}")

            if http_status == "200":
                print(f"   ✓ whisper-stt metrics endpoint reachable (HTTP 200)")

                # Check if we got data
                try:
                    data = json.loads(json_response)
                    result_count = len(data.get("data", {}).get("result", []))
                    print(f"   ✓ Metrics returned: {result_count} data points")

                    results["connectivity_tests"].append({
                        "test": "whisper_stt_metrics",
                        "status": "success",
                        "http_code": 200,
                        "data_points": result_count
                    })

                    if result_count > 0:
                        print(f"   ✓ whisper-stt has active metrics")
                        # Show sample data
                        sample = data["data"]["result"][0]
                        print(f"   Sample metric: {sample.get('metric', {})}")
                    else:
                        print(f"   ⚠ No metrics data found for whisper-stt namespace")

                except json.JSONDecodeError as e:
                    print(f"   ⚠ JSON parsing error: {e}")
                    results["connectivity_tests"].append({
                        "test": "whisper_stt_metrics",
                        "status": "partial_success",
                        "http_code": 200,
                        "error": "json_parse_error"
                    })
            else:
                print(f"   ✗ Unexpected HTTP status: {http_status}")
                results["connectivity_tests"].append({
                    "test": "whisper_stt_metrics",
                    "status": "failed",
                    "http_code": int(http_status) if http_status.isdigit() else "unknown"
                })
        else:
            print(f"   ✗ Command failed: {result.stderr}")
            results["connectivity_tests"].append({
                "test": "whisper_stt_metrics",
                "status": "command_failed"
            })

    except Exception as e:
        print(f"   ✗ Exception: {e}")
        results["connectivity_tests"].append({
            "test": "whisper_stt_metrics",
            "status": "exception",
            "error": str(e)
        })

    # Summary
    print("\n" + "="*70)
    print("CONNECTIVITY TEST SUMMARY")
    print("="*70)

    success_count = sum(1 for test in results["connectivity_tests"] if test["status"] == "success")
    total_count = len(results["connectivity_tests"])

    print(f"Total tests: {total_count}")
    print(f"Successful: {success_count}")
    print(f"Failed: {total_count - success_count}")

    for test in results["connectivity_tests"]:
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

    results_file = output_dir / f"metrics-connectivity-test-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Results saved to: {results_file}")

    # Return exit code based on success
    return 0 if success_count == total_count else 1

if __name__ == "__main__":
    sys.exit(test_basic_prometheus_connectivity())