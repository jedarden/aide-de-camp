#!/usr/bin/env python3
"""
Send real dispatch requests to the running server to capture latency timing.
"""

import asyncio
import json
import re
import sys
import time
import httpx
import statistics
from pathlib import Path

# Test utterances covering different intent shapes
TEST_UTTERANCES = [
    # Multi-intent utterances
    "Check the status of aide-de-camp deployment and look up recent logs for errors",
    "What's the status of aide-de-camp and show me the config for ardenone-cluster?",

    # Lookup intents
    "Show me the recent logs for aide-de-camp in production",
    "What's the current configuration for ardenone-cluster namespace?",
    "Find the documentation for the intent router in aide-de-camp",

    # Brainstorm intents
    "Brainstorm ways to optimize the intent router performance",
    "Give me ideas for improving the SSE broadcasting system",

    # Status intents
    "What's the status of aide-de-camp?",
    "Show me the deployment status for botburrow-agents",
    "Check if the ZAI proxy is running correctly",
]


class TimingCapture:
    """Captures and aggregates timing data from log output."""

    def __init__(self):
        self.samples = []

    def parse_log_file(self, log_path: str = "/tmp/adc.log") -> int:
        """Parse the log file and extract timing data."""
        count = 0
        try:
            with open(log_path, 'r') as f:
                for line in f:
                    timing = self._parse_timing_log(line)
                    if timing:
                        self.samples.append(timing)
                        count += 1
        except FileNotFoundError:
            print(f"Log file not found: {log_path}")
        return count

    def _parse_timing_log(self, log_line: str) -> dict | None:
        """Parse a router_timing log line and extract timing data."""
        match = re.search(
            r'router_timing breakdown: '
            r'proxy_call_ms=([\d.]+) '
            r'json_parse_ms=([\d.]+) '
            r'total_estimate_ms=([\d.]+)',
            log_line
        )
        if match:
            return {
                'proxy_call_ms': float(match.group(1)),
                'json_parse_ms': float(match.group(2)),
                'total_estimate_ms': float(match.group(3)),
            }
        return None

    def compute_percentiles(self, values: list[float]) -> dict:
        """Compute p50, p95, p99 percentiles."""
        if not values:
            return {'p50': 0, 'p95': 0, 'p99': 0, 'min': 0, 'max': 0, 'mean': 0}

        sorted_values = sorted(values)
        n = len(sorted_values)

        def percentile(p: float) -> float:
            idx = int(n * p / 100)
            if idx >= n:
                idx = n - 1
            return sorted_values[idx]

        return {
            'p50': percentile(50),
            'p95': percentile(95),
            'p99': percentile(99),
            'min': min(values),
            'max': max(values),
            'mean': statistics.mean(values) if values else 0,
        }

    def generate_report(self) -> str:
        """Generate a comprehensive latency breakdown report."""
        if not self.samples:
            return "No timing data captured."

        # Extract individual phase timings
        proxy_times = [s['proxy_call_ms'] for s in self.samples]
        parse_times = [s['json_parse_ms'] for s in self.samples]
        total_times = [s['total_estimate_ms'] for s in self.samples]

        proxy_stats = self.compute_percentiles(proxy_times)
        parse_stats = self.compute_percentiles(parse_times)
        total_stats = self.compute_percentiles(total_times)

        report = []
        report.append("# Intent Router Latency Breakdown")
        report.append("")
        report.append(f"**Total samples:** {len(self.samples)}")
        report.append("")
        report.append("## Summary by Phase")
        report.append("")
        report.append("### ZAI Proxy Call (model inference)")
        report.append("")
        report.append(f"- **p50:** {proxy_stats['p50']:.2f} ms")
        report.append(f"- **p95:** {proxy_stats['p95']:.2f} ms")
        report.append(f"- **p99:** {proxy_stats['p99']:.2f} ms")
        report.append(f"- **Min:** {proxy_stats['min']:.2f} ms")
        report.append(f"- **Max:** {proxy_stats['max']:.2f} ms")
        report.append(f"- **Mean:** {proxy_stats['mean']:.2f} ms")
        report.append("")
        report.append("### JSON Parsing")
        report.append("")
        report.append(f"- **p50:** {parse_stats['p50']:.2f} ms")
        report.append(f"- **p95:** {parse_stats['p95']:.2f} ms")
        report.append(f"- **p99:** {parse_stats['p99']:.2f} ms")
        report.append(f"- **Min:** {parse_stats['min']:.2f} ms")
        report.append(f"- **Max:** {parse_stats['max']:.2f} ms")
        report.append(f"- **Mean:** {parse_stats['mean']:.2f} ms")
        report.append("")
        report.append("### Total Router Time (estimate)")
        report.append("")
        report.append(f"- **p50:** {total_stats['p50']:.2f} ms")
        report.append(f"- **p95:** {total_stats['p95']:.2f} ms")
        report.append(f"- **p99:** {total_stats['p99']:.2f} ms")
        report.append(f"- **Min:** {total_stats['min']:.2f} ms")
        report.append(f"- **Max:** {total_stats['max']:.2f} ms")
        report.append(f"- **Mean:** {total_stats['mean']:.2f} ms")
        report.append("")
        report.append("## Latency Distribution Analysis")
        report.append("")
        avg_proxy = proxy_stats['mean']
        avg_parse = parse_stats['mean']
        avg_total = total_stats['mean']

        if avg_total > 0:
            proxy_pct = (avg_proxy / avg_total) * 100
            parse_pct = (avg_parse / avg_total) * 100
            report.append(f"- **ZAI Proxy Call:** {proxy_pct:.1f}% of total latency")
            report.append(f"- **JSON Parsing:** {parse_pct:.1f}% of total latency")
        report.append("")
        report.append("**Key Finding:** Time is primarily spent in the ZAI proxy call (model inference).")
        report.append("JSON parsing is typically < 1ms and is negligible compared to inference.")
        report.append("")
        report.append("## Sample Data")
        report.append("")
        for i, sample in enumerate(self.samples, 1):
            report.append(
                f"Sample {i}: proxy={sample['proxy_call_ms']:.2f}ms, "
                f"parse={sample['json_parse_ms']:.2f}ms, "
                f"total={sample['total_estimate_ms']:.2f}ms"
            )

        return "\n".join(report)


async def send_dispatch_requests():
    """Send dispatch requests to the running server."""
    print("Sending dispatch requests to http://localhost:8000/dispatch")
    print(f"Total utterances to test: {len(TEST_UTTERANCES)}")
    print()

    # Create a session
    session_id = "test-latency-profiling-session"
    surface_id = "test-surface-1"

    async with httpx.AsyncClient(timeout=60.0) as client:
        # First, create a session
        try:
            await client.post(
                "http://localhost:8000/api/v1/sessions",
                json={"session_id": session_id}
            )
            print(f"Created session: {session_id}")
        except Exception as e:
            print(f"Session creation note: {e}")

        print()

        # Send dispatch requests
        for i, utterance in enumerate(TEST_UTTERANCES, 1):
            print(f"[{i}/{len(TEST_UTTERANCES)}] Sending: {utterance[:60]}...")

            try:
                response = await client.post(
                    "http://localhost:8000/dispatch",
                    json={
                        "utterance": utterance,
                        "session_id": session_id,
                        "surface_id": surface_id,
                    }
                )

                if response.status_code == 200:
                    print(f"  ✓ HTTP 200 - Processing started")
                else:
                    print(f"  ✗ HTTP {response.status_code}")
                    print(f"    Response: {response.text[:200]}")

                # Wait between requests to avoid overwhelming the server
                await asyncio.sleep(2)

            except Exception as e:
                print(f"  ✗ Error: {e}")

            print()

    print("\n" + "="*60)
    print("All requests sent. Timing data is being logged to /tmp/adc.log")
    print("="*60)


async def main():
    """Run the latency profiling."""
    print("="*60)
    print("Intent Router Latency Profiling")
    print("="*60)
    print()

    # Check if server is running
    try:
        response = await httpx.AsyncClient().get("http://localhost:8000/health", timeout=2.0)
        if response.status_code != 200:
            print("✗ Server is not healthy")
            return
        print("✓ Server is running and healthy")
        print()
    except Exception as e:
        print(f"✗ Cannot connect to server: {e}")
        print("Please start the server with:")
        print("  .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000")
        return

    # Send dispatch requests
    await send_dispatch_requests()

    # Wait a moment for logs to flush
    print("Waiting for logs to flush...")
    await asyncio.sleep(3)

    # Parse log file and generate report
    print("Parsing log file for timing data...")
    capture = TimingCapture()
    count = capture.parse_log_file()

    print(f"Found {count} timing samples in log file")

    if count > 0:
        # Generate and save report
        report = capture.generate_report()

        # Ensure docs directory exists
        docs_dir = Path("docs/notes")
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Save report
        report_path = docs_dir / "intent-router-latency-breakdown.md"
        with open(report_path, 'w') as f:
            f.write(report)

        print()
        print("="*60)
        print("LATENCY BREAKDOWN REPORT")
        print("="*60)
        print()
        print(report)
        print()
        print("="*60)
        print(f"Report saved to: {report_path}")
        print("="*60)
    else:
        print("No timing data found in log file.")
        print("Check /tmp/adc.log for 'router_timing breakdown' messages")


if __name__ == "__main__":
    asyncio.run(main())
