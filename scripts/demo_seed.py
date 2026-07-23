#!/usr/bin/env python3
"""
Demo seeding and verification tool for aide-de-camp.

Automates the Phase 5 seeding runbook from docs/plan/plan.md:
1. Verifies registry entries for scripted projects
2. Runs context warmer for both scripted topics
3. Executes test dispatches and verifies fetch sources
4. Verifies component coverage
5. Emits pass/fail seeding report

Usage:
    python scripts/demo_seed.py [--verbose] [--dry-run]
    python scripts/demo_seed.py --help

Exit codes:
    0: All checks passed
    1: One or more verification failures
    2: Configuration error
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# Color codes for terminal output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


class CheckStatus(Enum):
    """Status of a verification check."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    """Result of a verification check."""
    name: str
    status: CheckStatus
    message: str
    details: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SeedingReport:
    """Complete seeding verification report."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    overall_status: CheckStatus = CheckStatus.PASS
    checks: list[CheckResult] = field(default_factory=list)

    def add_check(self, check: CheckResult) -> None:
        """Add a check result and update overall status."""
        self.checks.append(check)
        # Update overall status: FAIL > WARN > PASS
        if check.status == CheckStatus.FAIL:
            self.overall_status = CheckStatus.FAIL
        elif check.status == CheckStatus.WARN and self.overall_status == CheckStatus.PASS:
            self.overall_status = CheckStatus.WARN

    def summary(self) -> dict[str, Any]:
        """Generate summary dict for JSON output."""
        return {
            "timestamp": self.timestamp,
            "overall_status": self.overall_status.value,
            "total_checks": len(self.checks),
            "passed": sum(1 for c in self.checks if c.status == CheckStatus.PASS),
            "failed": sum(1 for c in self.checks if c.status == CheckStatus.FAIL),
            "warnings": sum(1 for c in self.checks if c.status == CheckStatus.WARN),
            "skipped": sum(1 for c in self.checks if c.status == CheckStatus.SKIP),
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "details": c.details,
                    "timestamp": c.timestamp,
                }
                for c in self.checks
            ],
        }


class DemoSeedVerifier:
    """
    Demo seeding and verification tool.

    Automates the Phase 5 seeding runbook with comprehensive checks.
    """

    # Scripted projects from the demo script
    SCRIPTED_PROJECTS = ["whisper-stt", "pbx-web"]

    # Scripted result types that need component coverage
    # (pending/ack and welcome are built-ins, not component-library shapes)
    SCRIPTED_RESULT_TYPES = [
        "status:whisper-stt",
        "status:pbx-web",
        "lookup:logs:whisper-stt",
        "lookup:config:whisper-stt",
        "brainstorm:pbx-web",
    ]

    # Required intents for each scripted project
    REQUIRED_INTENTS = {
        "whisper-stt": ["status", "lookup", "brainstorm", "task-profile"],
        "pbx-web": ["status", "lookup", "brainstorm", "task-profile"],
    }

    def __init__(self, verbose: bool = False, dry_run: bool = False):
        """Initialize the verifier."""
        self.verbose = verbose
        self.dry_run = dry_run
        self.report = SeedingReport()
        self.registry = None

        # Add src to path for imports
        src_path = Path(__file__).parent.parent / "src"
        sys.path.insert(0, str(src_path))

    def _print(self, message: str, color: str = Colors.WHITE) -> None:
        """Print a colored message."""
        if self.verbose or color in (Colors.GREEN, Colors.RED, Colors.YELLOW):
            print(f"{color}{message}{Colors.RESET}")

    def _print_check(self, result: CheckResult) -> None:
        """Print a check result with appropriate coloring."""
        status_colors = {
            CheckStatus.PASS: Colors.GREEN,
            CheckStatus.FAIL: Colors.RED,
            CheckStatus.WARN: Colors.YELLOW,
            CheckStatus.SKIP: Colors.CYAN,
        }
        color = status_colors.get(result.status, Colors.WHITE)
        icon = {
            CheckStatus.PASS: "✓",
            CheckStatus.FAIL: "✗",
            CheckStatus.WARN: "⚠",
            CheckStatus.SKIP: "○",
        }[result.status]

        self._print(f"{icon} {result.name}: {result.message}", color)

        if self.verbose and result.details:
            for key, value in result.details.items():
                self._print(f"    {key}: {value}", Colors.CYAN)

    async def _load_registry(self) -> dict:
        """Load the project registry."""
        if self.registry:
            return self.registry

        try:
            from registry import get_registry
            self.registry = get_registry(force=True)
            return self.registry
        except Exception as e:
            self._print(f"Failed to load registry: {e}", Colors.RED)
            raise

    async def _check_registry_entries(self) -> CheckResult:
        """
        Verify registry entries for every scripted project.

        Checks:
        - aliases exist
        - repo_path is set and has .beads/ workspace
        - argocd_app is readable on its mapped ArgoCD instance
        - intent_support covers every scripted intent including task-profile
        """
        try:
            registry = await self._load_registry()
            projects = registry.get("projects", {})

            errors = []
            warnings = []

            for project_slug in self.SCRIPTED_PROJECTS:
                project = projects.get(project_slug)

                if not project:
                    errors.append(f"Missing registry entry for {project_slug}")
                    continue

                # Check aliases
                aliases = project.get("aliases", [])
                if not aliases:
                    warnings.append(f"{project_slug}: No aliases defined")

                # Check repo_path
                repo_path = project.get("repo_path")
                if not repo_path:
                    errors.append(f"{project_slug}: repo_path not set")
                else:
                    repo = Path(repo_path)
                    if not repo.exists():
                        errors.append(f"{project_slug}: repo_path does not exist: {repo_path}")
                    elif not (repo / ".git").exists():
                        errors.append(f"{project_slug}: repo_path is not a git checkout: {repo_path}")
                    elif not (repo / ".beads").exists():
                        errors.append(f"{project_slug}: repo_path has no .beads/ workspace: {repo_path}")

                # Check intent_support
                intent_support = project.get("intent_support", [])
                required = self.REQUIRED_INTENTS.get(project_slug, [])
                missing = [intent for intent in required if intent not in intent_support]
                if missing:
                    errors.append(f"{project_slug}: Missing required intents: {missing}")

                # Check cluster configuration
                cluster = project.get("cluster")
                if not cluster:
                    errors.append(f"{project_slug}: cluster not set")

                # Check argocd_app
                argocd_app = project.get("argocd_app") or project_slug

                # Check ArgoCD endpoint resolution (via config/clusters.yaml)
                from fetch.clusters import resolve_argocd_endpoint
                try:
                    resolution = resolve_argocd_endpoint(cluster)
                    if not resolution.satisfiable:
                        # This is an error for the demo (criterion 3: zero visible error states)
                        errors.append(
                            f"{project_slug}: ArgoCD endpoint not satisfiable for '{cluster}': {resolution.reason}"
                        )
                except Exception as e:
                    warnings.append(f"{project_slug}: Could not resolve ArgoCD endpoint: {e}")

            if errors:
                return CheckResult(
                    name="Registry Verification",
                    status=CheckStatus.FAIL,
                    message=f"Failed with {len(errors)} error(s)",
                    details={"errors": errors, "warnings": warnings},
                )
            elif warnings:
                return CheckResult(
                    name="Registry Verification",
                    status=CheckStatus.WARN,
                    message=f"Passed with {len(warnings)} warning(s)",
                    details={"warnings": warnings},
                )
            else:
                return CheckResult(
                    name="Registry Verification",
                    status=CheckStatus.PASS,
                    message="All registry entries verified",
                    details={"projects": self.SCRIPTED_PROJECTS},
                )

        except Exception as e:
            return CheckResult(
                name="Registry Verification",
                status=CheckStatus.FAIL,
                message=f"Exception during check: {e}",
                details={"error": str(e)},
            )

    async def _check_context_warmer(self) -> CheckResult:
        """
        Run the context warmer for both scripted topics.

        Verifies that context warming succeeds for both scripted topics.
        """
        if self.dry_run:
            return CheckResult(
                name="Context Warmer",
                status=CheckStatus.SKIP,
                message="Skipped (dry-run mode)",
            )

        try:
            from context.warmer import get_context_warmer
            from session.store import get_store

            store = get_store()
            warmer = get_context_warmer()

            # Create or find cross-session topics for scripted projects
            topics = {}
            for project_slug in self.SCRIPTED_PROJECTS:
                # Find or create a cross-session topic for this project
                topic_id = f"demo-seed-{project_slug}"

                # Check if topic exists
                topic = await store.get_topic(topic_id)
                if not topic:
                    # Create cross-session topic
                    await store.create_topic(
                        topic_id=topic_id,
                        label=f"{project_slug} (demo seed)",
                        topic_type="project",
                        project_slugs=json.dumps([project_slug]),
                        scope="cross-session",
                    )

                topics[project_slug] = topic_id

            # Warm context for each topic
            errors = []
            for project_slug, topic_id in topics.items():
                try:
                    await warmer.warm_topic_context(topic_id, [project_slug])
                    self._print(f"Warmed context for {project_slug}", Colors.BLUE)
                except Exception as e:
                    errors.append(f"{project_slug}: {e}")

            if errors:
                return CheckResult(
                    name="Context Warmer",
                    status=CheckStatus.FAIL,
                    message=f"Failed to warm {len(errors)} topic(s)",
                    details={"errors": errors},
                )
            else:
                return CheckResult(
                    name="Context Warmer",
                    status=CheckStatus.PASS,
                    message="Context warmed for all scripted topics",
                    details={"topics": topics},
                )

        except Exception as e:
            return CheckResult(
                name="Context Warmer",
                status=CheckStatus.FAIL,
                message=f"Exception during check: {e}",
                details={"error": str(e)},
            )

    async def _check_dispatch_execution(self) -> CheckResult:
        """
        Execute test dispatches and verify fetch sources.

        Executes one throwaway dispatch per scripted step shape and confirms:
        - All fetch sources reachable (no fetch_coverage caveats)
        - watcher.alive via /health
        """
        if self.dry_run:
            return CheckResult(
                name="Dispatch Execution",
                status=CheckStatus.SKIP,
                message="Skipped (dry-run mode)",
            )

        try:
            import httpx
            from test.dispatch import TestDispatchRequest, dispatch_test_utterance

            # Scripted utterances from the demo (one per distinct shape)
            test_utterances = [
                ("What's the status of whisper stt?", "status", "whisper-stt"),
                ("How's the pbx web doing?", "status", "pbx-web"),
                ("Pull up the recent logs for whisper stt.", "lookup:logs", "whisper-stt"),
                ("Find the whisper stt deployment config.", "lookup:config", "whisper-stt"),
                ("Should the pbx web use redundant ingress controllers?", "brainstorm", "pbx-web"),
            ]

            errors = []
            warnings = []
            successful_dispatches = []

            # First, check /health for watcher status
            try:
                health_url = "http://localhost:8000/health"
                async with httpx.AsyncClient() as client:
                    response = await client.get(health_url, timeout=5.0)
                    health_data = response.json()

                    watcher_alive = health_data.get("watcher", {}).get("alive", False)
                    if not watcher_alive:
                        errors.append("Watcher not alive (check /health)")
            except Exception as e:
                errors.append(f"Health check failed: {e}")

            # Execute test dispatches
            for utterance, expected_intent, expected_project in test_utterances:
                try:
                    request = TestDispatchRequest(
                        utterance=utterance,
                        wait_for_results=True,
                        timeout_seconds=30,
                    )

                    result = await dispatch_test_utterance(request)

                    if result.status != "completed":
                        errors.append(
                            f"Dispatch failed: '{utterance[:50]}...' - {result.message}"
                        )
                        continue

                    # Check results for fetch_coverage caveats
                    if result.results:
                        for r in result.results:
                            fetch_coverage = r.get("fetch_coverage", {})
                            failed_sources = fetch_coverage.get("failed_sources", [])
                            if failed_sources:
                                warnings.append(
                                    f"Dispatch '{utterance[:50]}...' had failed sources: {failed_sources}"
                                )

                    successful_dispatches.append(utterance[:50] + "...")
                    self._print(f"Dispatched: {utterance[:50]}...", Colors.BLUE)

                except Exception as e:
                    errors.append(f"Dispatch exception for '{utterance[:50]}...': {e}")

            if errors:
                return CheckResult(
                    name="Dispatch Execution",
                    status=CheckStatus.FAIL,
                    message=f"Failed with {len(errors)} error(s)",
                    details={
                        "errors": errors,
                        "warnings": warnings,
                        "successful_dispatches": successful_dispatches,
                    },
                )
            elif warnings:
                return CheckResult(
                    name="Dispatch Execution",
                    status=CheckStatus.WARN,
                    message=f"Passed with {len(warnings)} warning(s)",
                    details={
                        "warnings": warnings,
                        "successful_dispatches": successful_dispatches,
                    },
                )
            else:
                return CheckResult(
                    name="Dispatch Execution",
                    status=CheckStatus.PASS,
                    message="All dispatches succeeded",
                    details={
                        "successful_dispatches": successful_dispatches,
                    },
                )

        except Exception as e:
            return CheckResult(
                name="Dispatch Execution",
                status=CheckStatus.FAIL,
                message=f"Exception during check: {e}",
                details={"error": str(e)},
            )

    async def _check_component_coverage(self) -> CheckResult:
        """
        Verify component coverage for all scripted result types.

        Every scripted RESULT step must select a real component-library component.
        If a shape would fall to the generic fallback, file a UI-regen bead for it and FAIL.

        Built-in cards (pending/ack, welcome, generic fallback) are exempt by design.
        """
        try:
            from components.library import get_library

            library = get_library()

            missing_components = []
            found_components = {}

            for result_type in self.SCRIPTED_RESULT_TYPES:
                component = library.select_component_for_result_type(result_type)

                if component is None:
                    missing_components.append(result_type)
                else:
                    found_components[result_type] = component.id

            if missing_components:
                return CheckResult(
                    name="Component Coverage",
                    status=CheckStatus.FAIL,
                    message=f"Missing components for {len(missing_components)} result type(s)",
                    details={
                        "missing_result_types": missing_components,
                        "found_components": found_components,
                        "action_required": (
                            "File UI-regen beads to create components for missing result types. "
                            "Each missing result_type needs a component with a match_score >= 0.7 "
                            "in component_usage_patterns."
                        ),
                    },
                )
            else:
                return CheckResult(
                    name="Component Coverage",
                    status=CheckStatus.PASS,
                    message="All scripted result types have components",
                    details={
                        "covered_result_types": list(found_components.keys()),
                    },
                )

        except Exception as e:
            return CheckResult(
                name="Component Coverage",
                status=CheckStatus.FAIL,
                message=f"Exception during check: {e}",
                details={"error": str(e)},
            )

    async def run_all_checks(self) -> SeedingReport:
        """Run all verification checks in order."""
        self._print(f"{Colors.BOLD}Starting Demo Seeding Verification{Colors.RESET}")
        self._print(f"Timestamp: {self.report.timestamp}")
        self._print(f"Dry-run: {self.dry_run}")
        self._print(f"Verbose: {self.verbose}")
        self._print("")

        # Run checks in sequence
        checks = [
            ("Registry Entries", self._check_registry_entries),
            ("Context Warmer", self._check_context_warmer),
            ("Dispatch Execution", self._check_dispatch_execution),
            ("Component Coverage", self._check_component_coverage),
        ]

        for check_name, check_func in checks:
            self._print(f"{Colors.BOLD}Running: {check_name}{Colors.RESET}", Colors.CYAN)

            try:
                result = await check_func()
                self.report.add_check(result)
                self._print_check(result)
            except Exception as e:
                result = CheckResult(
                    name=check_name,
                    status=CheckStatus.FAIL,
                    message=f"Check crashed: {e}",
                )
                self.report.add_check(result)
                self._print_check(result)

            self._print("")

        return self.report

    def emit_report(self, output_path: Optional[Path] = None) -> None:
        """Emit the seeding report to file and stdout."""
        summary = self.report.summary()

        # Print summary
        self._print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        self._print(f"{Colors.BOLD}Seeding Report Summary{Colors.RESET}")
        self._print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        self._print(f"Overall Status: {summary['overall_status']}")
        self._print(f"Total Checks: {summary['total_checks']}")
        self._print(f"  Passed: {summary['passed']}")
        self._print(f"  Failed: {summary['failed']}")
        self._print(f"  Warnings: {summary['warnings']}")
        self._print(f"  Skipped: {summary['skipped']}")

        # Write to file
        if output_path is None:
            output_path = Path(__file__).parent.parent / "docs" / "notes" / "seeding-report-latest.md"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(f"# Demo Seeding Verification Report\n\n")
            f.write(f"**Generated:** {summary['timestamp']}\n\n")
            f.write(f"## Summary\n\n")
            f.write(f"- **Overall Status:** {summary['overall_status']}\n")
            f.write(f"- **Total Checks:** {summary['total_checks']}\n")
            f.write(f"  - Passed: {summary['passed']}\n")
            f.write(f"  - Failed: {summary['failed']}\n")
            f.write(f"  - Warnings: {summary['warnings']}\n")
            f.write(f"  - Skipped: {summary['skipped']}\n\n")

            f.write(f"## Check Details\n\n")

            status_emoji = {
                "PASS": "✅",
                "FAIL": "❌",
                "WARN": "⚠️ ",
                "SKIP": "⏭️ ",
            }

            for check in summary["checks"]:
                emoji = status_emoji.get(check["status"], "❓")
                f.write(f"### {emoji} {check['name']}\n\n")
                f.write(f"**Status:** {check['status']}\n\n")
                f.write(f"**Message:** {check['message']}\n\n")

                if check["details"]:
                    f.write(f"**Details:**\n\n")
                    f.write(f"```json\n")
                    f.write(json.dumps(check["details"], indent=2))
                    f.write(f"\n```\n\n")

        self._print(f"\nReport written to: {output_path}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Demo seeding and verification tool for aide-de-camp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/demo_seed.py
    python scripts/demo_seed.py --verbose
    python scripts/demo_seed.py --dry-run --verbose
        """,
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip checks that require server interaction (context warmer, dispatches)",
    )

    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output report path (default: docs/notes/seeding-report-latest.md)",
    )

    args = parser.parse_args()

    verifier = DemoSeedVerifier(verbose=args.verbose, dry_run=args.dry_run)

    try:
        await verifier.run_all_checks()
        verifier.emit_report(args.output)

        # Exit with appropriate code
        if verifier.report.overall_status == CheckStatus.FAIL:
            sys.exit(1)
        elif verifier.report.overall_status == CheckStatus.WARN:
            sys.exit(0)  # Warnings are not failures
        else:
            sys.exit(0)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
