#!/usr/bin/env python3
"""
Automated diagnostic suite for pluck starvation alerts.

This script performs comprehensive checks when a starvation alert is raised:
1. Bead store consistency (direct database query)
2. Checkpoint freshness (current.json vs forensic.jsonl)
3. Pluck query logic validation (SQL logging)
4. Database corruption detection (bead doctor --rehearse)
5. Config validation (bead-rs vs bf mismatch)

Output: Structured JSON report with findings, severity levels, and recommendations.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def resolve_bead_bin(explicit: Optional[str] = None) -> str:
    """Locate the bead CLI.

    A systemd user manager runs services with a minimal PATH that does not
    include ~/.local/bin or ~/.cargo/bin, where this box's bead wrapper and
    binaries actually live — a bare "bead" raises FileNotFoundError there and
    every check that shells out would report a false failure. An explicit path
    (the healthcheck passes --bead-bin) always wins.
    """
    if explicit:
        return explicit
    found = shutil.which("bead")
    if found:
        return found
    for candidate in (
        Path.home() / ".local" / "bin" / "bead",
        Path.home() / ".cargo" / "bin" / "bead",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "bead"  # let subprocess surface the familiar not-found error


def parse_bead_payload(stdout: str) -> List[Dict[str, Any]]:
    """Parse `bead list --json` output into a flat list of bead dicts.

    The CLI emits compact JSONL, prints a bare "[]" for an empty result, and
    has been seen emitting nested arrays. Every shape must normalize to the
    same list: an empty frontier must count 0 (a bare `[]` parsed as one
    entry would both miscount and crash the dict-only consumers downstream),
    and a non-JSON progress line is skipped, not fatal.
    """
    if not stdout.strip():
        return []
    parsed: Any = None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if isinstance(parsed, dict):
        parsed = [parsed]
    flat: List[Dict[str, Any]] = []
    for item in parsed if isinstance(parsed, list) else []:
        if isinstance(item, list):
            flat.extend(i for i in item if isinstance(i, dict))
        elif isinstance(item, dict):
            flat.append(item)
    return flat


class PluckStarvationDiagnostic:
    """Comprehensive diagnostic suite for pluck starvation alerts."""

    SEVERITY_LEVELS = {
        "critical": 5,  # Data corruption or loss
        "high": 4,      # Starvation confirmed, beads truly invisible
        "medium": 3,    # Potential issue detected
        "low": 2,       # Minor inconsistency
        "info": 1,      # Informational
    }

    def __init__(self, workspace_path: str = "/home/coding/aide-de-camp",
                 bead_bin: Optional[str] = None):
        self.workspace = Path(workspace_path)
        self.bead_bin = resolve_bead_bin(bead_bin)
        self.beads_dir = self.workspace / ".beads"
        self.beads_db = self.beads_dir / "beads.db"
        self.checkpoint_dir = self.beads_dir / "checkpoint"
        self.config_file = self.beads_dir / "config.json"
        self.needle_yaml = self.workspace / ".needle.yaml"

        self.findings: List[Dict[str, Any]] = []
        self.start_time = datetime.now(timezone.utc)

    def add_finding(self, category: str, severity: str, message: str,
                   details: Optional[Dict[str, Any]] = None, recommendation: Optional[str] = None) -> None:
        """Add a diagnostic finding."""
        finding = {
            "category": category,
            "severity": severity,
            "severity_level": self.SEVERITY_LEVELS.get(severity, 0),
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if details:
            finding["details"] = details
        if recommendation:
            finding["recommendation"] = recommendation
        self.findings.append(finding)

    def check_bead_store_consistency(self) -> Dict[str, Any]:
        """Check bead store consistency by directly querying beads.db."""
        print("[1/5] Checking bead store consistency...")

        result = {
            "database_exists": self.beads_db.exists(),
            "database_readable": False,
            "total_beads": 0,
            "open_beads": 0,
            "in_progress_beads": 0,
            "closed_beads": 0,
            "assigned_but_open_beads": 0,
            "beads_with_dependencies": 0,
            "manually_blocked_beads": 0,
        }

        if not result["database_exists"]:
            self.add_finding(
                "database",
                "critical",
                f"Database file not found: {self.beads_db}",
                recommendation="Check if .beads/ directory is corrupted or if workspace is properly initialized."
            )
            return result

        try:
            conn = sqlite3.connect(self.beads_db)
            cursor = conn.cursor()

            # Check database readability
            cursor.execute("SELECT COUNT(*) FROM issues")
            result["total_beads"] = cursor.fetchone()[0]
            result["database_readable"] = True

            # Count by status
            cursor.execute("SELECT COUNT(*) FROM issues WHERE base_status = 'open'")
            result["open_beads"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM issues WHERE base_status = 'in_progress'")
            result["in_progress_beads"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM issues WHERE base_status = 'closed'")
            result["closed_beads"] = cursor.fetchone()[0]

            # Check for assigned-but-open beads (stuck state)
            cursor.execute("""
                SELECT COUNT(*) FROM issues
                WHERE base_status = 'open' AND assignee IS NOT NULL
            """)
            result["assigned_but_open_beads"] = cursor.fetchone()[0]

            if result["assigned_but_open_beads"] > 0:
                self.add_finding(
                    "database",
                    "high",
                    f"Found {result['assigned_but_open_beads']} assigned-but-open beads (stuck state)",
                    details={"count": result["assigned_but_open_beads"]},
                    recommendation="Run: bead update <id> --clear-assignee for each affected bead"
                )

            # Check beads with dependencies
            # The dependencies table uses blocked_issue_id and blocker_issue_id columns
            cursor.execute("""
                SELECT COUNT(DISTINCT blocked_issue_id) FROM dependencies
                WHERE blocked_issue_id IN (SELECT id FROM issues WHERE base_status != 'closed')
                   OR blocker_issue_id IN (SELECT id FROM issues WHERE base_status != 'closed')
            """)
            result["beads_with_dependencies"] = cursor.fetchone()[0]

            # Check manually blocked beads
            cursor.execute("SELECT COUNT(*) FROM issues WHERE manual_blocked = 1")
            result["manually_blocked_beads"] = cursor.fetchone()[0]

            conn.close()

            self.add_finding(
                "database",
                "info",
                f"Database contains {result['total_beads']} beads ({result['open_beads']} open, {result['in_progress_beads']} in progress, {result['closed_beads']} closed)",
                details=result
            )

        except sqlite3.Error as e:
            self.add_finding(
                "database",
                "critical",
                f"Database error: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
                recommendation="Run: bead doctor --repair to fix database corruption"
            )
            result["error"] = str(e)

        return result

    def check_checkpoint_freshness(self) -> Dict[str, Any]:
        """Check checkpoint freshness by comparing current.json against forensic.jsonl."""
        print("[2/5] Checking checkpoint freshness...")

        result = {
            "checkpoint_dir_exists": self.checkpoint_dir.exists(),
            "current_json_exists": False,
            "forensic_jsonl_exists": False,
            "current_json_lines": 0,
            "forensic_jsonl_lines": 0,
            "publish_lock_exists": False,
            "checkpoint_stale": False,
        }

        if not result["checkpoint_dir_exists"]:
            self.add_finding(
                "checkpoint",
                "critical",
                "Checkpoint directory not found",
                recommendation="Run: bead sync flush-only to create checkpoint"
            )
            return result

        current_json = self.checkpoint_dir / "current.json"
        forensic_jsonl = self.checkpoint_dir / "forensic.jsonl"
        publish_lock = self.checkpoint_dir / "publish.lock"

        result["current_json_exists"] = current_json.exists()
        result["forensic_jsonl_exists"] = forensic_jsonl.exists()
        result["publish_lock_exists"] = publish_lock.exists()

        if result["publish_lock_exists"]:
            self.add_finding(
                "checkpoint",
                "medium",
                "Publish lock file exists - checkpoint update may be in progress or stalled",
                recommendation="Check if bead sync is running; if stalled, remove publish.lock"
            )

        # Read current.json to get checkpoint info
        if current_json.exists():
            try:
                with open(current_json, 'r') as f:
                    current_data = json.load(f)
                    result["current_created_at"] = current_data.get("created_at")
                    result["current_issue_count"] = current_data.get("issue_count", 0)
                    result["current_event_count"] = current_data.get("event_count", 0)
                    result["current_generation_id"] = current_data.get("generation_id")
            except json.JSONDecodeError as e:
                self.add_finding(
                    "checkpoint",
                    "high",
                    f"current.json is corrupted: {str(e)}",
                    details={"error": str(e)},
                    recommendation="Restore from previous.json or forensic.jsonl"
                )
                return result

        # Count lines in forensic.jsonl (contains both issues AND events)
        if forensic_jsonl.exists():
            try:
                with open(forensic_jsonl, 'r') as f:
                    result["forensic_jsonl_lines"] = sum(1 for _ in f)

                    # Count issue records only (lines with "record_type":"issue")
                    with open(forensic_jsonl, 'r') as f2:
                        issue_count = sum(1 for line in f2 if '"record_type":"issue"' in line)
                        result["forensic_issue_count"] = issue_count
            except Exception as e:
                self.add_finding(
                    "checkpoint",
                    "high",
                    f"Cannot read forensic.jsonl: {str(e)}",
                    details={"error": str(e)}
                )

        # Compare issue counts (current.json issue_count vs forensic.jsonl issue records)
        if result.get("current_issue_count") and result.get("forensic_issue_count"):
            # Allow small tolerance for timing differences
            if abs(result["current_issue_count"] - result["forensic_issue_count"]) > 5:
                self.add_finding(
                    "checkpoint",
                    "high",
                    f"Checkpoint inconsistency: current.json reports {result['current_issue_count']} issues but forensic.jsonl has {result['forensic_issue_count']} issue records",
                    details={
                        "current_issue_count": result["current_issue_count"],
                        "forensic_issue_count": result["forensic_issue_count"],
                        "forensic_total_lines": result["forensic_jsonl_lines"]
                    },
                    recommendation="Run: bead sync flush-only to synchronize checkpoint"
                )
                result["checkpoint_stale"] = True

        self.add_finding(
            "checkpoint",
            "info",
            f"Checkpoint: {result['current_issue_count']} issues in current.json, {result['forensic_jsonl_lines']} lines in forensic.jsonl",
            details=result
        )

        return result

    def check_pluck_query_logic(self) -> Dict[str, Any]:
        """Validate pluck query logic by examining the ready frontier query."""
        print("[3/5] Checking pluck query logic...")

        result = {
            "ready_frontier_count": 0,
            "exclusion_criteria": {},
            "excluded_beads": [],
            "query_executed": False,
        }

        # Run bead list --ready --json and capture output
        try:
            cmd_result = subprocess.run(
                [self.bead_bin, "list", "--ready", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.workspace)
            )

            if cmd_result.returncode == 0:
                result["query_executed"] = True
                ready_beads = parse_bead_payload(cmd_result.stdout)

                result["ready_frontier_count"] = len(ready_beads)
                # Capture a sample of bead IDs for debugging
                result["ready_bead_sample"] = [b.get("id") for b in ready_beads[:5] if b.get("id")]
            else:
                self.add_finding(
                    "pluck_query",
                    "high",
                    f"bead list --ready failed: {cmd_result.stderr}",
                    details={"stderr": cmd_result.stderr, "returncode": cmd_result.returncode},
                    recommendation="Check bead CLI installation and database integrity"
                )

        except subprocess.TimeoutExpired:
            self.add_finding(
                "pluck_query",
                "high",
                "bead list --ready timed out after 30 seconds",
                recommendation="Database may be locked or corrupted; run: bead doctor --repair"
            )
        except Exception as e:
            self.add_finding(
                "pluck_query",
                "medium",
                f"Unexpected error running bead list --ready: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__}
            )

        # Read existing pluck diagnostics if available
        pluck_diagnostics = self.beads_dir / "diagnostics" / "pluck-diagnostics.json"
        if pluck_diagnostics.exists():
            try:
                with open(pluck_diagnostics, 'r') as f:
                    diag_data = json.load(f)
                    result["existing_diagnostics"] = diag_data
                    result["total_open_beads"] = diag_data.get("total_open_beads", 0)
                    result["final_candidate_count"] = diag_data.get("final_candidate_count", 0)

                    # Check for starvation condition
                    if diag_data.get("total_open_beads", 0) > 0 and diag_data.get("final_candidate_count", 0) == 0:
                        self.add_finding(
                            "pluck_query",
                            "critical",
                            f"STARVATION DETECTED: {diag_data['total_open_beads']} open beads exist but pluck found {diag_data['final_candidate_count']} candidates",
                            details=diag_data,
                            recommendation="Run full diagnostic and investigate exclusion criteria"
                        )
            except Exception as e:
                self.add_finding(
                    "pluck_query",
                    "low",
                    f"Could not read existing pluck diagnostics: {str(e)}"
                )

        self.add_finding(
            "pluck_query",
            "info",
            f"Ready frontier query returned {result['ready_frontier_count']} beads",
            details=result
        )

        return result

    def check_database_corruption(self) -> Dict[str, Any]:
        """Detect database corruption using bead doctor --rehearse."""
        print("[4/5] Checking database corruption with bead doctor...")

        result = {
            "rehearse_executed": False,
            "corruption_detected": False,
            "corruption_details": None,
        }

        try:
            # Run bead doctor --rehearse (does not modify actual database)
            cmd_result = subprocess.run(
                [self.bead_bin, "doctor", "--rehearse"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.workspace)
            )

            result["rehearse_executed"] = True
            result["returncode"] = cmd_result.returncode
            result["stdout"] = cmd_result.stdout
            result["stderr"] = cmd_result.stderr

            # Check for actual corruption indicators (not just the word "error" in progress messages)
            stdout_lower = cmd_result.stdout.lower()
            stderr_lower = cmd_result.stderr.lower()

            # Real corruption indicators
            real_corruption_keywords = [
                "corruption", "corrupt", "malformed", "inconsistent",
                "database is corrupted", "fatal", "critical failure"
            ]

            # Exclude false positives from normal output
            false_positive_keywords = [
                "recovery rehearsal completed successfully",
                "semantic: equivalent",
                "cleanup: success",
                "diagnostics completed"
            ]

            # Check for real corruption (not false positives)
            for keyword in real_corruption_keywords:
                if keyword in stdout_lower or keyword in stderr_lower:
                    # Make sure it's not in a success context
                    if not any(fp in stdout_lower or fp in stderr_lower for fp in false_positive_keywords):
                        result["corruption_detected"] = True
                        result["corruption_details"] = f"Found corruption indicator: {keyword}"
                        break

            if cmd_result.returncode != 0:
                self.add_finding(
                    "database_corruption",
                    "high",
                    f"bead doctor --rehearse failed with exit code {cmd_result.returncode}",
                    details={
                        "returncode": cmd_result.returncode,
                        "stderr": cmd_result.stderr[:500],  # Truncate for readability
                    },
                    recommendation="Run: bead doctor --repair to fix detected issues"
                )
            elif result["corruption_detected"]:
                self.add_finding(
                    "database_corruption",
                    "medium",
                    "bead doctor detected potential database issues",
                    details={"output": cmd_result.stderr[:500]},
                    recommendation="Review full output with: bead doctor --rehearse"
                )
            else:
                self.add_finding(
                    "database_corruption",
                    "info",
                    "bead doctor --rehearse completed successfully - no corruption detected"
                )

        except subprocess.TimeoutExpired:
            self.add_finding(
                "database_corruption",
                "high",
                "bead doctor --rehearse timed out after 60 seconds",
                recommendation="Database may be severely corrupted; consider recovery from checkpoint"
            )
        except Exception as e:
            self.add_finding(
                "database_corruption",
                "medium",
                f"Could not run bead doctor --rehearse: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__}
            )

        return result

    def check_config_validation(self) -> Dict[str, Any]:
        """Validate .beads/config.json and .needle.yaml for backend consistency."""
        print("[5/5] Checking configuration consistency...")

        result = {
            "config_json_exists": self.config_file.exists(),
            "needle_yaml_exists": self.needle_yaml.exists(),
            "backend_mismatch": False,
            "config_backend": None,
            "needle_backend": None,
        }

        # Check .beads/config.json
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    json.load(f)  # parse alone validates the file
                    # bead-rs config stores metadata, not backend directly
                    result["config_backend"] = "bead-rs"  # Inferred from file format
            except Exception as e:
                self.add_finding(
                    "config",
                    "medium",
                    f"Could not read .beads/config.json: {str(e)}",
                    details={"error": str(e)}
                )
        else:
            # Check for legacy bf config.yaml
            legacy_config = self.beads_dir / "config.yaml"
            if legacy_config.exists():
                result["config_backend"] = "bf"
                result["uses_legacy_config"] = True

        # Check .needle.yaml
        if self.needle_yaml.exists():
            try:
                with open(self.needle_yaml, 'r') as f:
                    import yaml
                    needle_data = yaml.safe_load(f)
                    result["needle_backend"] = needle_data.get("bead_cli", {}).get("backend")
            except ImportError:
                # Fallback: read as text and parse manually
                with open(self.needle_yaml, 'r') as f:
                    content = f.read()
                    if "bead_cli:" in content and "backend: bead-rs" in content:
                        result["needle_backend"] = "bead-rs"
                    elif "bead_cli:" in content and "backend: bf" in content:
                        result["needle_backend"] = "bf"
            except Exception as e:
                self.add_finding(
                    "config",
                    "low",
                    f"Could not read .needle.yaml: {str(e)}"
                )

        # Check for mismatch
        if result["config_backend"] and result["needle_backend"]:
            if result["config_backend"] != result["needle_backend"]:
                result["backend_mismatch"] = True
                self.add_finding(
                    "config",
                    "critical",
                    f"Backend mismatch: .beads config indicates '{result['config_backend']}' but .needle.yaml declares '{result['needle_backend']}'",
                    details={
                        "config_backend": result["config_backend"],
                        "needle_backend": result["needle_backend"]
                    },
                    recommendation="Update .needle.yaml bead_cli.backend to match actual backend"
                )

        self.add_finding(
            "config",
            "info",
            f"Configuration: backend={result['needle_backend'] or 'unknown'}, mismatch={result['backend_mismatch']}",
            details=result
        )

        return result

    def generate_report(self) -> Dict[str, Any]:
        """Generate the complete diagnostic report."""
        print("\n" + "="*70)
        print("PLUCK STARVATION DIAGNOSTIC REPORT")
        print("="*70 + "\n")

        # Run all diagnostic checks
        db_results = self.check_bead_store_consistency()
        checkpoint_results = self.check_checkpoint_freshness()
        pluck_results = self.check_pluck_query_logic()
        corruption_results = self.check_database_corruption()
        config_results = self.check_config_validation()

        # Sort findings by severity level
        sorted_findings = sorted(
            self.findings,
            key=lambda f: f.get("severity_level", 0),
            reverse=True
        )

        # Generate overall assessment
        critical_findings = [f for f in sorted_findings if f.get("severity") == "critical"]
        high_findings = [f for f in sorted_findings if f.get("severity") == "high"]

        if critical_findings:
            overall_status = "CRITICAL"
            overall_message = f"CRITICAL issues detected: {len(critical_findings)} critical finding(s)"
        elif high_findings:
            overall_status = "HIGH_RISK"
            overall_message = f"High-risk issues detected: {len(high_findings)} high finding(s)"
        else:
            overall_status = "HEALTHY"
            overall_message = "No critical or high-severity issues detected"

        # Compile report
        report = {
            "metadata": {
                "workspace": str(self.workspace),
                "timestamp": self.start_time.isoformat(),
                "diagnostic_duration_seconds": (
                    datetime.now(timezone.utc) - self.start_time
                ).total_seconds(),
                "overall_status": overall_status,
                "overall_message": overall_message,
            },
            "findings": sorted_findings,
            "detailed_results": {
                "database": db_results,
                "checkpoint": checkpoint_results,
                "pluck_query": pluck_results,
                "corruption_check": corruption_results,
                "config": config_results,
            },
            "recommendations": self._compile_recommendations(sorted_findings),
        }

        return report

    def _compile_recommendations(self, findings: List[Dict[str, Any]]) -> List[str]:
        """Compile prioritized recommendations from findings."""
        recommendations = []
        seen = set()

        for finding in findings:
            rec = finding.get("recommendation")
            if rec and rec not in seen:
                recommendations.append(f"[{finding['severity'].upper()}] {rec}")
                seen.add(rec)

        return recommendations

    def save_report(self, report: Dict[str, Any],
                    output_path: Optional[str] = None) -> str:
        """Save the report to a JSON file.

        Without an explicit path the report lands at a timestamped default.
        (Passing --output used to only rename the destination without ever
        writing the file — the caller's contract is that the path returned is
        a readable report, whichever branch produced it.)
        """
        if output_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_path = f"/tmp/pluck-starvation-diagnostic-{timestamp}.json"

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)

        return output_path


def main():
    """Main entry point for the diagnostic script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Automated diagnostic suite for pluck starvation alerts"
    )
    parser.add_argument(
        "--workspace",
        default="/home/coding/aide-de-camp",
        help="Path to the workspace directory (default: /home/coding/aide-de-camp)"
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: /tmp/pluck-starvation-diagnostic-<timestamp>.json)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (only print summary)"
    )
    parser.add_argument(
        "--bead-bin",
        help="Path to the bead CLI (default: bead on PATH, falling back to "
             "~/.local/bin/bead and ~/.cargo/bin/bead)"
    )

    args = parser.parse_args()

    # Run diagnostics
    diagnostic = PluckStarvationDiagnostic(args.workspace, args.bead_bin)
    report = diagnostic.generate_report()

    # Save report (to --output when given, else the timestamped default)
    output_path = diagnostic.save_report(report, args.output)

    # Print summary
    if not args.quiet:
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Overall Status: {report['metadata']['overall_status']}")
        print(f"Duration: {report['metadata']['diagnostic_duration_seconds']:.2f} seconds")
        print(f"Findings: {len(report['findings'])}")
        print(f"Output: {output_path}")

        if report['recommendations']:
            print("\nTop Recommendations:")
            for rec in report['recommendations'][:5]:
                print(f"  • {rec}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
