"""
Integration tests for demo seeding verification tool.

Tests the demo_seed.py script with mocked failures to ensure it correctly
detects and reports seeding issues.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# Add src and scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from demo_seed import (
    CheckResult,
    CheckStatus,
    DemoSeedVerifier,
    SeedingReport,
)


class TestSeedingReport:
    """Tests for SeedingReport data class."""

    def test_empty_report(self):
        """Empty report should have PASS status."""
        report = SeedingReport()
        assert report.overall_status == CheckStatus.PASS
        assert len(report.checks) == 0

    def test_add_pass_check(self):
        """Adding a PASS check keeps status as PASS."""
        report = SeedingReport()
        report.add_check(CheckResult(
            name="Test",
            status=CheckStatus.PASS,
            message="OK",
        ))
        assert report.overall_status == CheckStatus.PASS
        assert len(report.checks) == 1

    def test_add_fail_check(self):
        """Adding a FAIL check changes status to FAIL."""
        report = SeedingReport()
        report.add_check(CheckResult(
            name="Test",
            status=CheckStatus.FAIL,
            message="Failed",
        ))
        assert report.overall_status == CheckStatus.FAIL

    def test_add_warn_check(self):
        """Adding a WARN check changes status to WARN."""
        report = SeedingReport()
        report.add_check(CheckResult(
            name="Test",
            status=CheckStatus.WARN,
            message="Warning",
        ))
        assert report.overall_status == CheckStatus.WARN

    def test_fail_overrides_warn(self):
        """FAIL check should override WARN status."""
        report = SeedingReport()
        report.add_check(CheckResult(
            name="Test1",
            status=CheckStatus.WARN,
            message="Warning",
        ))
        assert report.overall_status == CheckStatus.WARN

        report.add_check(CheckResult(
            name="Test2",
            status=CheckStatus.FAIL,
            message="Failed",
        ))
        assert report.overall_status == CheckStatus.FAIL

    def test_summary(self):
        """Test summary generation."""
        report = SeedingReport()
        report.add_check(CheckResult(
            name="Check1",
            status=CheckStatus.PASS,
            message="OK",
        ))
        report.add_check(CheckResult(
            name="Check2",
            status=CheckStatus.FAIL,
            message="Failed",
            details={"error": "test"},
        ))

        summary = report.summary()
        assert summary["total_checks"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert len(summary["checks"]) == 2


class TestDemoSeedVerifier:
    """Tests for DemoSeedVerifier."""

    def test_init(self):
        """Test verifier initialization."""
        verifier = DemoSeedVerifier(verbose=True, dry_run=True)
        assert verifier.verbose is True
        assert verifier.dry_run is True
        assert len(verifier.SCRIPTED_PROJECTS) == 2
        assert "whisper-stt" in verifier.SCRIPTED_PROJECTS
        assert "pbx-web" in verifier.SCRIPTED_PROJECTS

    @pytest.mark.asyncio
    async def test_check_registry_missing_entries(self):
        """Test registry verification with missing project entries."""
        verifier = DemoSeedVerifier(dry_run=True)

        # Mock registry with missing projects
        mock_registry = {
            "projects": {
                "other-project": {
                    "aliases": ["other"],
                    "repo_path": "/home/coding/other-project",
                    "intent_support": ["status", "task-profile"],
                    "cluster": "apexalgo-iad",
                }
            }
        }

        # Patch the _load_registry method directly
        with patch.object(verifier, "_load_registry", return_value=mock_registry):
            result = await verifier._check_registry_entries()

        assert result.status == CheckStatus.FAIL
        assert "Missing registry entry" in result.details["errors"][0]

    @pytest.mark.asyncio
    async def test_check_registry_missing_repo_path(self):
        """Test registry verification with missing repo_path."""
        verifier = DemoSeedVerifier(dry_run=True)

        # Mock registry with entries but missing repo_path
        mock_registry = {
            "projects": {
                "whisper-stt": {
                    "aliases": ["whisper", "stt"],
                    "repo_path": None,  # Missing!
                    "intent_support": ["status", "lookup", "brainstorm", "task-profile"],
                    "cluster": "ardenone-cluster",
                    "argocd_app": "whisper-stt",
                },
                "pbx-web": {
                    "aliases": ["pbx"],
                    "repo_path": None,  # Missing!
                    "intent_support": ["status", "lookup", "brainstorm", "task-profile"],
                    "cluster": "ardenone-cluster",
                    "argocd_app": "pbx-web",
                },
            }
        }

        with patch.object(verifier, "_load_registry", return_value=mock_registry):
            result = await verifier._check_registry_entries()

        assert result.status == CheckStatus.FAIL
        errors = result.details["errors"]
        assert any("repo_path not set" in e for e in errors)

    @pytest.mark.asyncio
    async def test_check_registry_missing_intents(self):
        """Test registry verification with missing required intents."""
        verifier = DemoSeedVerifier(dry_run=True)

        # Create temp git dirs with .beads workspace
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            whisper_dir = tmppath / "whisper-stt"
            pbx_dir = tmppath / "pbx-web"

            whisper_dir.mkdir()
            pbx_dir.mkdir()
            (whisper_dir / ".git").touch()
            (whisper_dir / ".beads").mkdir()
            (pbx_dir / ".git").touch()
            (pbx_dir / ".beads").mkdir()

            # Mock registry missing task-profile intent
            mock_registry = {
                "projects": {
                    "whisper-stt": {
                        "aliases": ["whisper", "stt"],
                        "repo_path": str(whisper_dir),
                        "intent_support": ["status", "lookup", "brainstorm"],  # Missing task-profile
                        "cluster": "ardenone-cluster",
                    },
                    "pbx-web": {
                        "aliases": ["pbx"],
                        "repo_path": str(pbx_dir),
                        "intent_support": ["status", "lookup", "brainstorm"],  # Missing task-profile
                        "cluster": "ardenone-cluster",
                    },
                }
            }

            with patch.object(verifier, "_load_registry", return_value=mock_registry):
                result = await verifier._check_registry_entries()

            assert result.status == CheckStatus.FAIL
            errors = result.details["errors"]
            assert any("Missing required intents" in e for e in errors)

    @pytest.mark.asyncio
    async def test_check_registry_argocd_auth_required(self):
        """Test registry verification with authenticated ArgoCD (not consumable)."""
        verifier = DemoSeedVerifier(dry_run=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            whisper_dir = tmppath / "whisper-stt"
            whisper_dir.mkdir()
            (whisper_dir / ".git").touch()
            (whisper_dir / ".beads").mkdir()

            # Mock registry with authenticated ArgoCD (not consumable)
            mock_registry = {
                "projects": {
                    "whisper-stt": {
                        "aliases": ["whisper", "stt"],
                        "repo_path": str(whisper_dir),
                        "intent_support": ["status", "lookup", "brainstorm", "task-profile"],
                        "cluster": "apexalgo-iad",  # This cluster requires auth
                    },
                }
            }

            mock_clusters = {
                "apexalgo-iad": {
                    "argocd_api": "https://argocd-rs-manager.tail1b1987.ts.net:8080",
                    "access": "authenticated",  # Not consumable!
                }
            }

            with patch.object(verifier, "_load_registry", return_value=mock_registry):
                with patch("fetch.clusters.resolve_argocd_endpoint") as mock_resolve:
                    # Mock the resolution result
                    mock_resolution = MagicMock()
                    mock_resolution.satisfiable = False
                    mock_resolution.reason = "Cluster 'apexalgo-iad' ArgoCD requires authentication (no no-auth read-only proxy available)"
                    mock_resolve.return_value = mock_resolution

                    result = await verifier._check_registry_entries()

            assert result.status == CheckStatus.FAIL
            errors = result.details["errors"]
            assert any("ArgoCD endpoint not satisfiable" in e for e in errors)
            assert any("requires authentication" in e for e in errors)

    @pytest.mark.asyncio
    async def test_check_registry_pass(self):
        """Test registry verification with all checks passing."""
        verifier = DemoSeedVerifier(dry_run=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            whisper_dir = tmppath / "whisper-stt"
            pbx_dir = tmppath / "pbx-web"

            whisper_dir.mkdir()
            pbx_dir.mkdir()
            (whisper_dir / ".git").touch()
            (whisper_dir / ".beads").mkdir()
            (pbx_dir / ".git").touch()
            (pbx_dir / ".beads").mkdir()

            # Mock registry with everything correct
            mock_registry = {
                "projects": {
                    "whisper-stt": {
                        "aliases": ["whisper", "stt", "speech-to-text"],
                        "repo_path": str(whisper_dir),
                        "intent_support": ["status", "lookup", "brainstorm", "task-profile"],
                        "cluster": "ardenone-cluster",  # Has read-only proxy
                    },
                    "pbx-web": {
                        "aliases": ["pbx", "phone system"],
                        "repo_path": str(pbx_dir),
                        "intent_support": ["status", "lookup", "brainstorm", "task-profile"],
                        "cluster": "ardenone-cluster",
                    },
                }
            }

            mock_clusters = {
                "ardenone-cluster": {
                    "argocd_api": "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444",
                    "access": "read-only-proxy",  # Consumable!
                }
            }

            with patch.object(verifier, "_load_registry", return_value=mock_registry):
                with patch("fetch.clusters.resolve_argocd_endpoint") as mock_resolve:
                    # Mock the resolution result
                    mock_resolution = MagicMock()
                    mock_resolution.satisfiable = True
                    mock_resolve.return_value = mock_resolution

                    result = await verifier._check_registry_entries()

            assert result.status == CheckStatus.PASS
            assert "verified" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_context_warmer_dry_run(self):
        """Test context warmer check skips in dry-run mode."""
        verifier = DemoSeedVerifier(dry_run=True)
        result = await verifier._check_context_warmer()

        assert result.status == CheckStatus.SKIP
        assert "dry-run" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_dispatch_execution_dry_run(self):
        """Test dispatch execution check skips in dry-run mode."""
        verifier = DemoSeedVerifier(dry_run=True)
        result = await verifier._check_dispatch_execution()

        assert result.status == CheckStatus.SKIP
        assert "dry-run" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_component_coverage_missing(self):
        """Test component coverage check with missing components."""
        verifier = DemoSeedVerifier(dry_run=True)

        # Mock library with no components
        mock_library = MagicMock()
        mock_library.select_component_for_result_type = MagicMock(return_value=None)

        with patch("components.library.get_library", return_value=mock_library):
            result = await verifier._check_component_coverage()

        assert result.status == CheckStatus.FAIL
        assert len(result.details["missing_result_types"]) == 5
        assert "status:whisper-stt" in result.details["missing_result_types"]

    @pytest.mark.asyncio
    async def test_check_component_coverage_complete(self):
        """Test component coverage check with all components present."""
        verifier = DemoSeedVerifier(dry_run=True)

        # Mock library with all components
        mock_library = MagicMock()
        mock_component = MagicMock()
        mock_component.id = "comp-test123"

        def mock_select(result_type):
            return mock_component

        mock_library.select_component_for_result_type = mock_select

        with patch("components.library.get_library", return_value=mock_library):
            result = await verifier._check_component_coverage()

        assert result.status == CheckStatus.PASS
        assert len(result.details["covered_result_types"]) == 5

    @pytest.mark.asyncio
    async def test_run_all_checks(self):
        """Test running all checks in sequence."""
        verifier = DemoSeedVerifier(dry_run=True, verbose=False)

        # Mock all checks to return known results
        async def mock_registry():
            return CheckResult(
                name="Registry",
                status=CheckStatus.PASS,
                message="OK",
            )

        async def mock_context():
            return CheckResult(
                name="Context",
                status=CheckStatus.SKIP,
                message="Skipped",
            )

        async def mock_dispatch():
            return CheckResult(
                name="Dispatch",
                status=CheckStatus.SKIP,
                message="Skipped",
            )

        async def mock_component():
            return CheckResult(
                name="Component",
                status=CheckStatus.PASS,
                message="OK",
            )

        verifier._check_registry_entries = mock_registry
        verifier._check_context_warmer = mock_context
        verifier._check_dispatch_execution = mock_dispatch
        verifier._check_component_coverage = mock_component

        report = await verifier.run_all_checks()

        assert len(report.checks) == 4
        assert report.overall_status == CheckStatus.PASS


class TestEmitReport:
    """Tests for report emission."""

    def test_emit_report_creates_file(self):
        """Test that report emission creates a file."""
        report = SeedingReport()
        report.add_check(CheckResult(
            name="Test Check",
            status=CheckStatus.PASS,
            message="All good",
        ))

        verifier = DemoSeedVerifier(dry_run=True)
        verifier.report = report

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            temp_path = Path(f.name)

        try:
            verifier.emit_report(temp_path)
            assert temp_path.exists()

            content = temp_path.read_text()
            assert "# Demo Seeding Verification Report" in content
            assert "Test Check" in content
            assert "All good" in content

        finally:
            temp_path.unlink()

    def test_emit_report_default_path(self):
        """Test report emission to default path."""
        report = SeedingReport()
        verifier = DemoSeedVerifier(dry_run=True)
        verifier.report = report

        default_path = (
            Path(__file__).parent.parent / "docs" / "notes" / "seeding-report-latest.md"
        )

        # Just verify the method doesn't crash with default path
        # (don't actually write to avoid git pollution in tests)
        with patch.object(verifier, "_print"):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__ = MagicMock()
                mock_open.return_value.__exit__ = MagicMock()
                mock_open.return_value.write = MagicMock()

                verifier.emit_report()

                # Verify open was called
                mock_open.assert_called_once()


class TestMockedFailures:
    """Test scenarios with mocked failures for integration testing."""

    @pytest.mark.asyncio
    async def test_registry_failure_propagates_to_overall_fail(self):
        """Test that registry failure causes overall FAIL status."""
        verifier = DemoSeedVerifier(dry_run=True)

        # Mock to return failure
        async def mock_registry_fail():
            return CheckResult(
                name="Registry Verification",
                status=CheckStatus.FAIL,
                message="Registry errors",
                details={"errors": ["test error"]},
            )

        verifier._check_registry_entries = mock_registry_fail

        report = await verifier.run_all_checks()

        assert report.overall_status == CheckStatus.FAIL
        assert any(c.status == CheckStatus.FAIL for c in report.checks)

    @pytest.mark.asyncio
    async def test_component_failure_propagates_to_overall_fail(self):
        """Test that component coverage failure causes overall FAIL status."""
        verifier = DemoSeedVerifier(dry_run=True)

        # Mock registry to pass, components to fail
        async def mock_registry_pass():
            return CheckResult(
                name="Registry Verification",
                status=CheckStatus.PASS,
                message="OK",
            )

        async def mock_component_fail():
            return CheckResult(
                name="Component Coverage",
                status=CheckStatus.FAIL,
                message="Missing components",
                details={"missing_result_types": ["status:test-project"]},
            )

        verifier._check_registry_entries = mock_registry_pass
        verifier._check_context_warmer = lambda: CheckResult(
            name="Context", status=CheckStatus.SKIP, message="Skip"
        )
        verifier._check_dispatch_execution = lambda: CheckResult(
            name="Dispatch", status=CheckStatus.SKIP, message="Skip"
        )
        verifier._check_component_coverage = mock_component_fail

        report = await verifier.run_all_checks()

        assert report.overall_status == CheckStatus.FAIL

    @pytest.mark.asyncio
    async def test_multiple_failures_all_reported(self):
        """Test that multiple failures are all reported."""
        verifier = DemoSeedVerifier(dry_run=True)

        errors = []

        async def mock_fail(check_name):
            errors.append(check_name)
            return CheckResult(
                name=check_name,
                status=CheckStatus.FAIL,
                message=f"{check_name} failed",
            )

        verifier._check_registry_entries = lambda: mock_fail("Registry")
        verifier._check_context_warmer = lambda: mock_fail("Context")
        verifier._check_dispatch_execution = lambda: mock_fail("Dispatch")
        verifier._check_component_coverage = lambda: mock_fail("Components")

        report = await verifier.run_all_checks()

        assert len(errors) == 4
        assert report.overall_status == CheckStatus.FAIL
        assert all(c.status == CheckStatus.FAIL for c in report.checks)

    @pytest.mark.asyncio
    async def test_warning_with_passes_results_in_warn(self):
        """Test that warnings with other passes results in WARN status."""
        verifier = DemoSeedVerifier(dry_run=True)

        async def mock_registry_warn():
            return CheckResult(
                name="Registry Verification",
                status=CheckStatus.WARN,
                message="Minor issues",
                details={"warnings": ["alias missing"]},
            )

        async def mock_context_skip():
            return CheckResult(
                name="Context", status=CheckStatus.SKIP, message="Skip"
            )

        async def mock_dispatch_skip():
            return CheckResult(
                name="Dispatch", status=CheckStatus.SKIP, message="Skip"
            )

        async def mock_components_pass():
            return CheckResult(
                name="Components", status=CheckStatus.PASS, message="OK"
            )

        verifier._check_registry_entries = mock_registry_warn
        verifier._check_context_warmer = mock_context_skip
        verifier._check_dispatch_execution = mock_dispatch_skip
        verifier._check_component_coverage = mock_components_pass

        report = await verifier.run_all_checks()

        assert report.overall_status == CheckStatus.WARN
