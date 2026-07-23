#!/usr/bin/env python3
"""
Test Beads-Workspace Scoping: escalate, watcher, and fetch bf command execution.

Tests that:
1. Escalate creates beads in aide-de-camp workspace with --project {slug} tag
2. Watcher runs bf commands from aide-de-camp workspace
3. Fetch bead listing uses project workspace when available, falls back to adc workspace
4. Caveat text matches plan requirements
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Optional

# Ensure the project root is in the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.escalate.handler import (
    EscalateRequest,
    EscalateHandler,
    BEADS_WORKSPACE,
)
from src.fetch.orchestrator import FetchStrand, FetchContext
from src.fetch.commands import FetchSource, IntentType
from src.watcher.daemon import BeadWatcher
from src.session.store import SessionStore


def test_escalate_workspace_constant():
    """Test that escalate handler uses correct workspace constant."""
    print("Testing escalate handler workspace constant...")

    # Per plan: BEADS_WORKSPACE should be /home/coding/aide-de-camp
    assert BEADS_WORKSPACE == Path("/home/coding/aide-de-camp"), \
        f"BEADS_WORKSPACE should be /home/coding/aide-de-camp, got {BEADS_WORKSPACE}"

    print("  ✅ Escalate handler uses correct workspace: /home/coding/aide-de-camp")
    return True


async def test_escalate_bead_creation_with_project_tag():
    """Test that escalate creates beads with --project flag in correct workspace."""
    print("Testing escalate bead creation with --project tag...")

    handler = EscalateHandler()

    request = EscalateRequest(
        intent_id="test-intent-1",
        session_id="test-session",
        utterance="Fix the authentication bug in the login service",
        intent_type="task-profile",
        project_slug="pbx-web",  # Has project_slug
        topic_id="test-topic",
    )

    bead_body = "# Fix authentication bug\nInvestigate and fix the auth issue."

    # Mock subprocess to capture bf command invocation
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"abc-123\n", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_subprocess:
        bead_id = await handler.create_bead(request, bead_body)

        # Verify bf create was called
        assert mock_subprocess.called, "bf create should be called"
        call_args = mock_subprocess.call_args

        # The command is spread across positional args since subprocess_exec takes *args
        # call_args[0] is a tuple of all positional arguments
        args = list(call_args[0])
        assert "bf" in args, "Command should include 'bf'"
        assert "create" in args, "Command should include 'create'"
        # Note: bf uses --project=value format
        assert any(arg == "--project" or arg.startswith("--project=") for arg in args), \
            "Command should include --project flag"
        assert any("pbx-web" in arg for arg in args), \
            "Command should include project_slug 'pbx-web'"

        # Verify cwd is set to aide-de-camp workspace
        cwd_kwarg = call_args[1].get("cwd")
        assert cwd_kwarg == BEADS_WORKSPACE, \
            f"bf create should run from {BEADS_WORKSPACE}, got {cwd_kwarg}"

    print("  ✅ Escalate creates beads with --project flag from correct workspace")
    return True


async def test_escalate_bead_creation_without_project_slug():
    """Test that escalate works without project_slug (no --project flag)."""
    print("Testing escalate bead creation without project_slug...")

    handler = EscalateHandler()

    request = EscalateRequest(
        intent_id="test-intent-2",
        session_id="test-session",
        utterance="Organize my files",
        intent_type="task-profile",
        project_slug=None,  # No project_slug
        topic_id="test-topic",
    )

    bead_body = "# Organize files\nSort and categorize files."

    # Mock subprocess
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"xyz-456\n", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_subprocess:
        bead_id = await handler.create_bead(request, bead_body)

        # Verify bf create was called
        assert mock_subprocess.called, "bf create should be called"
        call_args = mock_subprocess.call_args
        args = list(call_args[0])

        # Should NOT have --project flag when project_slug is None
        assert not any(arg == "--project" or arg.startswith("--project=") for arg in args), \
            "Command should NOT include --project flag when project_slug is None"

        # Should still run from correct workspace
        cwd_kwarg = call_args[1].get("cwd")
        assert cwd_kwarg == BEADS_WORKSPACE, \
            f"bf create should run from {BEADS_WORKSPACE}"

    print("  ✅ Escalate works correctly without project_slug")
    return True


async def test_watcher_workspace_constant():
    """Test that watcher uses correct workspace constant."""
    print("Testing watcher workspace constant...")

    # Per plan: watcher should run bf from /home/coding/aide-de-camp
    assert BeadWatcher.BF_WORKSPACE == "/home/coding/aide-de-camp", \
        f"BF_WORKSPACE should be /home/coding/aide-de-camp, got {BeadWatcher.BF_WORKSPACE}"

    print("  ✅ Watcher uses correct workspace: /home/coding/aide-de-camp")
    return True


async def test_watcher_bf_list_from_workspace():
    """Test that watcher runs bf list from correct workspace."""
    print("Testing watcher bf list execution...")

    # Create a temporary database for the test
    import tempfile
    import os
    temp_db = tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False)
    temp_db.close()

    try:
        store = SessionStore(db_path=temp_db.name)
        # BeadWatcher also needs a SurfaceRouter
        from src.surface.router import SurfaceRouter
        router = SurfaceRouter(store=store)
        watcher = BeadWatcher(store=store, router=router)

        # Mock subprocess to capture bf command invocation
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b'[]\n', b"")

        with patch.object(watcher, "_bf_bin", "bf"):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_subprocess:
                await watcher._run_bf_list_closed()

                # Verify bf list was called
                assert mock_subprocess.called, "bf list should be called"
                call_args = mock_subprocess.call_args

                # Check the command (spread across positional args)
                args = list(call_args[0])
                assert "bf" in args, "Command should include 'bf'"
                assert "list" in args, "Command should include 'list'"
                assert "--status" in args, "Command should include --status"
                assert "closed" in args, "Command should include 'closed'"

                # Verify cwd is set to aide-de-camp workspace
                cwd_kwarg = call_args[1].get("cwd")
                assert cwd_kwarg == BeadWatcher.BF_WORKSPACE, \
                    f"bf list should run from {BeadWatcher.BF_WORKSPACE}, got {cwd_kwarg}"

        print("  ✅ Watcher runs bf list from correct workspace")
        return True
    finally:
        # Clean up temp database
        os.unlink(temp_db.name)

    print("  ✅ Watcher runs bf list from correct workspace")
    return True


async def test_fetch_bead_list_primary_path():
    """Test fetch bead listing primary path: project has .beads/ workspace."""
    print("Testing fetch bead listing primary path (project workspace)...")

    strand = FetchStrand()

    context = FetchContext(
        project_slug="pbx-web",
        repo_path="/home/coding/declarative-config",  # Has .beads/
        namespace="pbx-web",
        cluster="ardenone-cluster",
    )

    # Mock subprocess
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (
        b'[{"id": "pbx-1", "title": "Fix PBX bug"}]\n',
        b""
    )

    # Patch Path.exists to return True for paths containing .beads
    def exists_side_effect(self):
        return ".beads" in str(self)

    with patch.object(Path, 'exists', exists_side_effect):
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_subprocess:
            result = await strand._fetch_bead_list(context)

            # Verify primary path was used
            assert result["scope"] == "project_workspace", \
                "Should use project workspace scope"
            assert result["project"] == "pbx-web"
            assert result["count"] == 1

            # Check that bf list was called WITHOUT --project filter
            # (primary path: project's own workspace doesn't tag with aide-de-camp slug)
            call_args = mock_subprocess.call_args
            args = list(call_args[0])
            # Note: check that no --project=value argument exists
            assert not any(arg.startswith("--project=") for arg in args), \
                "Primary path should NOT use --project filter in project workspace"

            # Verify cwd is set to repo_path
            cwd_kwarg = call_args[1].get("cwd")
            assert cwd_kwarg == context.repo_path, \
                f"Primary path should run from {context.repo_path}"

    print("  ✅ Fetch bead listing uses primary path correctly")
    return True


async def test_fetch_bead_list_fallback_path():
    """Test fetch bead listing fallback path: no .beads/, use adc workspace with caveat."""
    print("Testing fetch bead listing fallback path (adc workspace)...")

    strand = FetchStrand()

    context = FetchContext(
        project_slug="options-pipeline",
        repo_path="/home/coding/options-pipeline",  # No .beads/
        namespace="optionspipeline",
        cluster="iad-options",
    )

    # Mock subprocess for fallback (adc workspace)
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (
        b'[{"id": "opt-1", "title": "Fix options bug"}]\n',
        b""
    )

    # Patch Path.exists to return False for paths containing .beads
    def exists_side_effect(self):
        return ".beads" not in str(self)

    with patch.object(Path, 'exists', exists_side_effect):
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_subprocess:
            result = await strand._fetch_bead_list(context)

            # Verify fallback path was used
            assert result["scope"] == "adc_workspace_filtered", \
                "Should use adc workspace filtered scope"
            assert result["project"] == "options-pipeline"
            assert result["count"] == 1

            # Check that caveat text matches plan requirement
            assert "caveat" in result, "Fallback path should include caveat"
            expected_caveat = "No local beads workspace for options-pipeline; showing aide-de-camp-originated beads only"
            assert result["caveat"] == expected_caveat, \
                f"Caveat text should match plan: got '{result.get('caveat')}'"

            # Check that bf list was called WITH --project filter
            # Note: bf uses --project=value format (single argument)
            call_args = mock_subprocess.call_args
            args = list(call_args[0])
            assert any("--project=options-pipeline" in arg or arg == "--project=options-pipeline" for arg in args), \
                "Fallback path should use --project filter"
            assert any("options-pipeline" in arg for arg in args), \
                "Fallback path should filter by project_slug"

            # Verify cwd is set to adc workspace
            cwd_kwarg = call_args[1].get("cwd")
            assert cwd_kwarg == "/home/coding/aide-de-camp", \
                f"Fallback path should run from /home/coding/aide-de-camp, got {cwd_kwarg}"

    print("  ✅ Fetch bead listing uses fallback path correctly with caveat")
    return True


async def test_fetch_bead_list_no_repo_path():
    """Test fetch bead listing when no repo_path is provided."""
    print("Testing fetch bead listing with no repo_path...")

    strand = FetchStrand()

    context = FetchContext(
        project_slug="some-project",
        repo_path=None,  # No repo_path
        namespace="somenamespace",
    )

    # Mock subprocess for fallback (adc workspace)
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b'[]\n', b"")

    # Patch Path.exists to return False for paths containing .beads
    def exists_side_effect(self):
        return ".beads" not in str(self)

    with patch.object(Path, 'exists', exists_side_effect):
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_subprocess:
            result = await strand._fetch_bead_list(context)

            # Should use fallback path (adc workspace)
            assert result["scope"] == "adc_workspace_filtered", \
                "No repo_path should trigger fallback path"
            assert "caveat" in result, "Fallback should include caveat"

            # Verify --project filter was used
            # Note: bf uses --project=value format (single argument)
            call_args = mock_subprocess.call_args
            args = list(call_args[0])
            assert any(arg.startswith("--project=") for arg in args), \
                "Fallback path should use --project filter"
            assert any("some-project" in arg for arg in args), \
                "Fallback should filter by project_slug"

    print("  ✅ Fetch bead listing handles no repo_path correctly")
    return True


async def main():
    """Run all tests."""
    print("=" * 70)
    print("Testing Beads-Workspace Scoping Implementation")
    print("=" * 70)
    print()

    tests = [
        # Escalate handler tests
        ("Escalate workspace constant", test_escalate_workspace_constant),
        ("Escalate bead creation with --project tag", test_escalate_bead_creation_with_project_tag),
        ("Escalate bead creation without project_slug", test_escalate_bead_creation_without_project_slug),

        # Watcher tests
        ("Watcher workspace constant", test_watcher_workspace_constant),
        ("Watcher bf list execution", test_watcher_bf_list_from_workspace),

        # Fetch bead listing tests
        ("Fetch bead listing primary path", test_fetch_bead_list_primary_path),
        ("Fetch bead listing fallback path", test_fetch_bead_list_fallback_path),
        ("Fetch bead listing no repo_path", test_fetch_bead_list_no_repo_path),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            if asyncio.iscoroutinefunction(test_fn):
                await test_fn()
            else:
                test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            failed += 1
        print()

    print("=" * 70)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
