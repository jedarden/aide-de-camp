#!/usr/bin/env python3
"""
Analyze pod logs to extract patterns and create structured analysis files.
"""

import re
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

# Pattern definitions
PATTERNS = {
    "startup": [
        r"Starting application",
        r"Application initialized",
        r"Server starting",
        r"Listening on",
        r"Ready to serve",
        r"readiness probe succeeded",
        r"startup probe",
        r"initialization complete",
        r"bootstrapping",
        r"Loading config",
        r"registering",
    ],
    "oom_kill": [
        r"Out of memory",
        r"OOM kill",
        r"Memory limit exceeded",
        r"Killed process",
        r"oom-killer",
        r"memory cgroup out of memory",
        r"Process.*was killed",
        r"exited with code 137",  # SIGKILL (often OOM)
    ],
    "error": [
        r"\[ERROR\]",
        r"\[FATAL\]",
        r"error:",
        r"Error:",
        r"failed",
        r"Failed",
        r"exception",
        r"Exception",
        r"panic:",
        r"Panic:",
        r"traceback",
        r"Traceback",
        r"refused",
        r"timeout",
        r"connection.*reset",
        r"cannot connect",
    ],
    "performance": [
        r"slow request",
        r"high latency",
        r"took .+(seconds?|ms)",
        r"request.*timeout",
        r"deadline exceeded",
        r"slow query",
        r"latency.*high",
        r"response time",
        r"processing.*took",
    ]
}

def parse_timestamp(line: str) -> str:
    """Extract timestamp from log line."""
    # Try various timestamp formats
    time_patterns = [
        r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}',  # ISO or similar
        r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}',      # MM/DD/YYYY
        r'\w{3} \d{1,2} \d{2}:\d{2}:\d{2}',          # Mon DD HH:MM:SS
        r'\d{10}',                                      # Unix timestamp
    ]

    for pattern in time_patterns:
        match = re.search(pattern, line)
        if match:
            return match.group(0)
    return "unknown"

def categorize_line(line: str) -> Dict[str, Any]:
    """Categorize a single log line."""
    line_lower = line.lower()
    categories = []

    for category, patterns in PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                categories.append(category)
                break  # Only count one match per category

    return {
        "categories": categories,
        "timestamp": parse_timestamp(line),
        "line": line.strip()[:200]  # Truncate long lines
    }

def analyze_log_file(log_path: Path) -> Dict[str, Any]:
    """Analyze a single log file and return structured results."""
    print(f"Analyzing {log_path.name}...")

    results = {
        "file": str(log_path),
        "file_name": log_path.name,
        "analysis_date": datetime.now().isoformat(),
        "total_lines": 0,
        "patterns": {
            "startup": {"count": 0, "timestamps": [], "samples": []},
            "oom_kill": {"count": 0, "timestamps": [], "samples": []},
            "error": {"count": 0, "timestamps": [], "samples": []},
            "performance": {"count": 0, "timestamps": [], "samples": []},
        },
        "summary": []
    }

    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                results["total_lines"] += 1
                categorized = categorize_line(line)

                if categorized["categories"]:
                    for cat in categorized["categories"]:
                        results["patterns"][cat]["count"] += 1
                        results["patterns"][cat]["timestamps"].append(categorized["timestamp"])

                        # Keep sample lines (max 5 per category)
                        if len(results["patterns"][cat]["samples"]) < 5:
                            results["patterns"][cat]["samples"].append(categorized["line"])

    except Exception as e:
        results["error"] = f"Failed to read log: {str(e)}"

    # Build summary
    for cat, data in results["patterns"].items():
        if data["count"] > 0:
            results["summary"].append({
                "category": cat,
                "count": data["count"],
                "first_occurrence": data["timestamps"][0] if data["timestamps"] else "unknown",
                "last_occurrence": data["timestamps"][-1] if data["timestamps"] else "unknown",
            })

    results["summary"].sort(key=lambda x: x["count"], reverse=True)

    return results

def main():
    """Find and analyze all pod log files."""
    base_dir = Path("/home/coding/aide-de-camp/research")

    # Find all .log files
    log_files = []
    for log_dir in base_dir.glob("*/pod-logs"):
        if log_dir.is_dir():
            log_files.extend(log_dir.glob("*.log"))

    # Also handle standalone .log files
    log_files.extend(base_dir.glob("*/*.log"))

    log_files = sorted(set(log_files))

    print(f"Found {len(log_files)} log files to analyze")

    # Analyze each log file
    all_results = {}
    for log_file in log_files:
        results = analyze_log_file(log_file)
        all_results[log_file.name] = results

        # Write individual analysis file
        analysis_path = log_file.parent / f"{log_file.stem}-analysis.json"
        with open(analysis_path, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"  → Written: {analysis_path.name}")
        print(f"    - Total lines: {results['total_lines']}")
        print(f"    - Patterns found: {', '.join(f'{k}={v['count']}' for k, v in results['patterns'].items() if v['count'] > 0)}")
        print()

    # Write consolidated summary
    summary_path = base_dir / "log-analysis-summary.json"
    with open(summary_path, 'w') as f:
        json.dump({
            "analysis_date": datetime.now().isoformat(),
            "total_logs_analyzed": len(log_files),
            "results": all_results
        }, f, indent=2)

    print(f"Consolidated summary written to: {summary_path}")

    # Print final summary
    print("\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)
    for file_name, results in all_results.items():
        if results.get("summary"):
            print(f"\n{file_name}:")
            for item in results["summary"]:
                print(f"  {item['category']}: {item['count']} occurrences")

if __name__ == "__main__":
    main()
