"""Consistency tests for cleanup operations that span Git and the filesystem.

The scenarios in this module deliberately stop cleanup at its failure points.
Each test then checks that the last published state is complete and that a
subsequent cleanup can finish the operation without repairing a truncated file
or invalid Git metadata.
"""

import errno
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import src.utils.atomic_write as atomic_write_module
from src.utils.atomic_write import atomic_write, atomic_write_rollback
from src.utils.git_cleanup import GitCleanupError, GitStateCleanup, cleanup_temporary_branches
from tests.helpers import registry_test_helpers as registry_helpers

ORIGINAL_REGISTRY = "projects:\n  demo:\n    aliases:\n      - demo\n"
MODIFIED_REGISTRY = "projects:\n  demo:\n    aliases:\n      - changed\n"


def _git(repo: Path, *args: str) -> str:
    """Run a read-only Git command and return its stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _temporary_branches(repo: Path, pattern: str) -> set[str]:
    """Return temporary branch names without relying on human-oriented output."""
    import fnmatch

    branches = _git(repo, "branch", "--format=%(refname:short)").splitlines()
    return {branch for branch in branches if fnmatch.fnmatch(branch, pattern)}


def _assert_registry_state(registry_path: Path, expected: str) -> None:
    """Assert both byte-level content and parseability of the published file."""
    assert registry_path.read_text() == expected
    assert yaml.safe_load(registry_path.read_text()) == yaml.safe_load(expected)
    assert not list(registry_path.parent.glob(f".{registry_path.name}.tmp_*.tmp"))


@pytest.fixture
def atomic_cleanup_repo(tmp_path: Path) -> Path:
    """Create a small repository whose branch state can be inspected cheaply."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    (repo / "state.txt").write_text("complete\n")
    subprocess.run(["git", "add", "state.txt"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial state"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    return repo


@pytest.fixture
def registry_cleanup_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the registry helper at an isolated filesystem tree."""
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(ORIGINAL_REGISTRY)
    monkeypatch.setattr(registry_helpers, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(registry_helpers, "_test_registry_backup_path", None)

    yield registry_path

    # Keep the helper's process-global bookkeeping clean if a test deliberately
    # leaves a failed cleanup available for retry.
    backup_path = registry_helpers._test_registry_backup_path
    if backup_path is not None:
        backup_path.unlink(missing_ok=True)
        registry_helpers._test_registry_backup_path = None


class TestGitCleanupConsistency:
    """Verify interrupted and concurrent Git cleanup leaves valid state."""

    def test_interrupted_cleanup_is_retryable_and_consistent(self, atomic_cleanup_repo: Path):
        """An interruption between branch deletions leaves a valid retry point."""
        cleanup = GitStateCleanup(repo_path=atomic_cleanup_repo)
        cleanup.__enter__()
        cleanup.create_temporary_branch("temp-interrupted")
        cleanup.create_temporary_branch("temp-survivor")

        real_run = subprocess.run
        interrupted = False

        def interrupt_first_delete(args, **kwargs):
            nonlocal interrupted
            if args[-2:] == ["-D", "temp-interrupted"] and not interrupted:
                interrupted = True
                raise KeyboardInterrupt("cleanup interrupted")
            return real_run(args, **kwargs)

        with patch("src.utils.git_cleanup.subprocess.run", side_effect=interrupt_first_delete):
            with pytest.raises(KeyboardInterrupt, match="cleanup interrupted"):
                cleanup._perform_cleanup()

        assert cleanup._cleanup_completed is False
        assert _temporary_branches(atomic_cleanup_repo, "temp-*") == {
            "temp-interrupted",
            "temp-survivor",
        }
        assert _git(atomic_cleanup_repo, "branch", "--show-current") == "main"

        # Retry after the interruption: both complete branch refs must be
        # removed, and no Git repair or manual filesystem cleanup is needed.
        cleanup._perform_cleanup()

        assert cleanup._cleanup_completed is True
        assert _temporary_branches(atomic_cleanup_repo, "temp-*") == set()
        assert _git(atomic_cleanup_repo, "branch", "--show-current") == "main"
        assert _git(atomic_cleanup_repo, "status", "--porcelain") == ""

    def test_concurrent_cleanup_operations_leave_no_orphaned_branches(
        self, atomic_cleanup_repo: Path
    ):
        """Two cleanup owners may race, but the final Git state stays consistent."""
        expected = {f"temp-concurrent-{index}" for index in range(6)}
        for branch in expected:
            subprocess.run(
                ["git", "-C", str(atomic_cleanup_repo), "branch", branch],
                capture_output=True,
                check=True,
            )

        listing_barrier = threading.Barrier(2)
        real_run = subprocess.run

        def synchronize_initial_listing(args, **kwargs):
            if args[-2:] == ["branch", "--format=%(refname:short)"]:
                listing_barrier.wait(timeout=5)
            return real_run(args, **kwargs)

        with patch(
            "src.utils.git_cleanup.subprocess.run",
            side_effect=synchronize_initial_listing,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda _:
                        cleanup_temporary_branches(
                            atomic_cleanup_repo,
                            branch_pattern="temp-concurrent-*",
                            return_details=True,
                        ),
                        range(2),
                    )
                )

        assert all(set(result) == {"deleted", "failures"} for result in results)
        assert set().union(*(set(result["deleted"]) for result in results)) == expected
        assert _temporary_branches(atomic_cleanup_repo, "temp-concurrent-*") == set()
        assert _git(atomic_cleanup_repo, "branch", "--show-current") == "main"
        assert _git(atomic_cleanup_repo, "status", "--porcelain") == ""

    def test_partial_cleanup_can_be_retried_after_a_transient_failure(
        self, atomic_cleanup_repo: Path
    ):
        """A failed branch removal does not prevent a later complete cleanup."""
        cleanup = GitStateCleanup(repo_path=atomic_cleanup_repo)
        cleanup.__enter__()
        cleanup.create_temporary_branch("temp-retry")
        cleanup.create_temporary_branch("temp-after-retry")

        real_run = subprocess.run
        fail_once = True

        def fail_one_delete(args, **kwargs):
            nonlocal fail_once
            if args[-2:] == ["-D", "temp-retry"] and fail_once:
                fail_once = False
                raise PermissionError(errno.EACCES, "temporary lock")
            return real_run(args, **kwargs)

        with patch("src.utils.git_cleanup.subprocess.run", side_effect=fail_one_delete):
            with pytest.raises(GitCleanupError, match="temp-retry"):
                cleanup._perform_cleanup()

        assert _temporary_branches(atomic_cleanup_repo, "temp-*") == {"temp-retry"}
        cleanup._perform_cleanup()

        assert _temporary_branches(atomic_cleanup_repo, "temp-*") == set()
        assert cleanup._cleanup_completed is True
        assert _git(atomic_cleanup_repo, "status", "--porcelain") == ""


class TestRegistryCleanupConsistency:
    """Verify registry restoration never exposes a partial document."""

    def test_disk_full_during_cleanup_preserves_last_complete_registry(
        self, registry_cleanup_path: Path
    ):
        """`ENOSPC` leaves the modified document and a valid backup intact."""
        registry_helpers.setup_test_registry()
        backup_path = registry_helpers._test_registry_backup_path
        assert backup_path is not None
        atomic_write(registry_cleanup_path, MODIFIED_REGISTRY)

        def raise_enospc(fd, data):
            raise OSError(errno.ENOSPC, "No space left on device")

        with patch.object(atomic_write_module.os, "write", side_effect=raise_enospc):
            with pytest.raises(OSError, match="No space left on device"):
                registry_helpers.cleanup_test_registry()

        _assert_registry_state(registry_cleanup_path, MODIFIED_REGISTRY)
        assert backup_path.exists()
        _assert_registry_state(backup_path, ORIGINAL_REGISTRY)

        registry_helpers.cleanup_test_registry()
        _assert_registry_state(registry_cleanup_path, ORIGINAL_REGISTRY)
        assert not backup_path.exists()

    def test_partial_cleanup_after_restore_is_retryable(self, registry_cleanup_path: Path):
        """A failed backup unlink keeps cleanup ownership available for retry."""
        registry_helpers.setup_test_registry()
        backup_path = registry_helpers._test_registry_backup_path
        assert backup_path is not None
        atomic_write(registry_cleanup_path, MODIFIED_REGISTRY)

        real_unlink = Path.unlink

        def fail_backup_unlink(path, missing_ok=False):
            if path == backup_path:
                raise PermissionError(errno.EACCES, "backup is temporarily locked")
            return real_unlink(path, missing_ok=missing_ok)

        with patch.object(Path, "unlink", new=fail_backup_unlink):
            with pytest.raises(PermissionError, match="temporarily locked"):
                registry_helpers.cleanup_test_registry()

        # Restoration was already published atomically; only backup removal
        # was incomplete, so the helper still owns enough state to retry.
        _assert_registry_state(registry_cleanup_path, ORIGINAL_REGISTRY)
        assert backup_path.exists()
        assert registry_helpers._test_registry_backup_path == backup_path

        registry_helpers.cleanup_test_registry()
        _assert_registry_state(registry_cleanup_path, ORIGINAL_REGISTRY)
        assert registry_helpers._test_registry_backup_path is None
        assert not backup_path.exists()

    def test_concurrent_restoration_publishes_complete_registry_documents(
        self, registry_cleanup_path: Path
    ):
        """Concurrent cleanup owners serialize restoration of one registry path."""
        registry_helpers.setup_test_registry()
        backup_path = registry_helpers._test_registry_backup_path
        assert backup_path is not None
        atomic_write(registry_cleanup_path, MODIFIED_REGISTRY)

        restore_barrier = threading.Barrier(2)

        def restore_concurrently(_):
            restore_barrier.wait(timeout=5)
            registry_helpers.restore_registry(backup_path)

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(restore_concurrently, range(2)))

        _assert_registry_state(registry_cleanup_path, ORIGINAL_REGISTRY)
        assert backup_path.exists()
        registry_helpers.cleanup_test_registry()
        assert not backup_path.exists()

    def test_rollback_publish_failure_preserves_original_and_staging_cleanup(
        self, tmp_path: Path
    ):
        """A failed atomic rollback publication cannot corrupt the target."""
        target = tmp_path / "registry.yaml"
        target.write_text(ORIGINAL_REGISTRY)
        real_replace = atomic_write_module.os.replace

        def fail_target_publish(source, destination):
            if Path(destination) == target:
                raise OSError(errno.ENOSPC, "No space left on device")
            return real_replace(source, destination)

        with patch.object(atomic_write_module.os, "replace", side_effect=fail_target_publish):
            with pytest.raises(OSError, match="No space left on device"):
                with atomic_write_rollback(target) as staging_path:
                    staging_path.write_text(MODIFIED_REGISTRY)

        _assert_registry_state(target, ORIGINAL_REGISTRY)
