"""
Git cleanup utilities for temporary state management.

This module provides utilities for cleaning up temporary git state that may
be left behind during operations, including:
- Temporary branches created during operations
- Merge conflict state
- Temporary files or staging state
- Return to original branch after operations

All cleanup operations use try/finally patterns to guarantee cleanup
even when exceptions occur.
"""

import errno
import logging
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from src.action.steps.git_validation import (
    GitError,
    GitNetworkError,
    GitStateError,
    detect_merge_conflicts,
)

logger = logging.getLogger(__name__)


class GitCleanupError(GitError):
    """Raised when git cleanup operations fail."""
    pass


class GitStateCleanup:
    """
    Context manager for comprehensive git state cleanup.

    This context manager tracks the original git state and provides
    automatic cleanup on exit, ensuring the repository is left in a
    clean state even when exceptions occur.

    Example:
        with GitStateCleanup(repo_path="/path/to/repo") as cleanup:
            # Perform git operations that may create temporary state
            cleanup.create_temporary_branch("test-branch")
            # ... do work ...
            # Automatic cleanup on exit (success or exception)
    """

    def __init__(
        self,
        repo_path: str | Path,
        cleanup_branches: bool = True,
        cleanup_merge_state: bool = True,
        return_to_original_branch: bool = True,
        timeout: int = 30,
    ):
        """
        Initialize git state cleanup manager.

        Args:
            repo_path: Path to the git repository
            cleanup_branches: Whether to clean up temporary branches on exit
            cleanup_merge_state: Whether to clean up merge state on exit
            return_to_original_branch: Whether to return to original branch on exit
            timeout: Timeout for git commands in seconds
        """
        self.repo_path = Path(repo_path)
        self.cleanup_branches = cleanup_branches
        self.cleanup_merge_state = cleanup_merge_state
        self.return_to_original_branch = return_to_original_branch
        self.timeout = timeout

        # Track original state
        self.original_branch: Optional[str] = None
        self.created_branches: list[str] = []
        self.had_conflicts: bool = False

        # Track cleanup completion
        self._cleanup_completed = False
        self.cleanup_failures: list[dict[str, Any]] = []
        self.cleanup_state_before: dict[str, Any] = {}
        self.cleanup_state_after: dict[str, Any] = {}

    @staticmethod
    def _error_context(error: BaseException) -> str:
        """Return a useful, actionable description for a cleanup error."""
        if isinstance(error, PermissionError) or getattr(error, "errno", None) in {
            errno.EACCES,
            errno.EPERM,
        }:
            return f"permission denied ({error})"
        if getattr(error, "errno", None) == errno.ENOSPC:
            return f"disk full ({error})"
        if isinstance(error, subprocess.CalledProcessError):
            stderr = (error.stderr or "").strip()
            stderr_lower = stderr.lower()
            if "no space left" in stderr_lower or "disk full" in stderr_lower:
                return f"disk full ({stderr or error})"
            if "permission denied" in stderr_lower:
                return f"permission denied ({stderr or error})"
            return f"git exited with status {error.returncode}: {stderr or error}"
        return f"{type(error).__name__}: {error}"

    def _capture_cleanup_state(self) -> dict[str, Any]:
        """Capture the state used to validate cleanup before and after it runs."""
        state: dict[str, Any] = {
            "current_branch": None,
            "conflict_files": None,
            "branches": {},
            "errors": [],
        }

        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )
            state["current_branch"] = result.stdout.strip()
        except Exception as error:
            state["errors"].append(
                f"current branch: {self._error_context(error)}"
            )

        if self.cleanup_merge_state:
            try:
                state["conflict_files"] = detect_merge_conflicts(
                    self.repo_path, timeout=self.timeout
                )
            except Exception as error:
                state["errors"].append(
                    f"merge state: {self._error_context(error)}"
                )

        for branch_name in self.created_branches:
            try:
                result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(self.repo_path),
                        "branch",
                        "--list",
                        branch_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=True,
                )
                state["branches"][branch_name] = bool(result.stdout.strip())
            except Exception as error:
                state["errors"].append(
                    f"branch {branch_name}: {self._error_context(error)}"
                )

        return state

    def _record_cleanup_failure(
        self,
        operation: str,
        target: str,
        error: BaseException | str,
        *,
        before: Optional[dict[str, Any]] = None,
        after: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record and log one cleanup failure without losing its context."""
        detail = self._error_context(error) if isinstance(error, BaseException) else str(error)
        failure = {
            "operation": operation,
            "target": target,
            "error": detail,
            "state_before": before or {},
            "state_after": after or {},
        }
        self.cleanup_failures.append(failure)
        logger.error(
            "Git cleanup failed: operation=%s target=%s error=%s "
            "state_before=%s state_after=%s",
            operation,
            target,
            detail,
            before or {},
            after or {},
        )

    def _validate_cleanup_state(self, state: dict[str, Any]) -> None:
        """Record failures when the requested post-cleanup state is not met."""
        if state.get("errors"):
            self._record_cleanup_failure(
                "cleanup state validation",
                str(self.repo_path),
                "; ".join(state["errors"]),
                before=self.cleanup_state_before,
                after=state,
            )
            return

        if (
            self.return_to_original_branch
            and self.original_branch
            and state.get("current_branch") != self.original_branch
        ):
            self._record_cleanup_failure(
                "return to original branch",
                self.original_branch,
                f"post-cleanup branch is {state.get('current_branch')!r}",
                before=self.cleanup_state_before,
                after=state,
            )

        if self.cleanup_merge_state and state.get("conflict_files"):
            files = ", ".join(state["conflict_files"])
            self._record_cleanup_failure(
                "merge conflict cleanup",
                files,
                "conflicted files remain after cleanup",
                before=self.cleanup_state_before,
                after=state,
            )

        if self.cleanup_branches:
            remaining = [
                name for name, exists in state.get("branches", {}).items() if exists
            ]
            if remaining:
                self._record_cleanup_failure(
                    "temporary branch cleanup",
                    ", ".join(remaining),
                    "temporary branches remain after cleanup",
                    before=self.cleanup_state_before,
                    after=state,
                )

    def __enter__(self) -> 'GitStateCleanup':
        """Enter context and capture original git state."""
        self._capture_original_state()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """
        Exit context and perform cleanup.

        Cleanup runs even when an exception is raised, ensuring the
        repository is returned to a clean state.
        """
        try:
            self._perform_cleanup()
        except Exception as cleanup_error:
            # Log cleanup errors but don't suppress the original exception
            logger.error(
                "Error during git cleanup for repository %s: %s",
                self.repo_path,
                cleanup_error,
                exc_info=True,
            )
            if exc_type is None:
                # If no original exception, raise the cleanup error
                if isinstance(cleanup_error, GitCleanupError):
                    raise
                raise GitCleanupError(f"Cleanup failed: {cleanup_error}") from cleanup_error

        return False  # Don't suppress exceptions

    def _capture_original_state(self) -> None:
        """Capture the original git state for restoration."""
        try:
            # Get current branch
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )
            self.original_branch = result.stdout.strip()
            logger.info(f"Captured original branch: {self.original_branch}")

            # Check for existing merge conflicts
            try:
                conflict_files = detect_merge_conflicts(self.repo_path, timeout=self.timeout)
                self.had_conflicts = len(conflict_files) > 0
                if self.had_conflicts:
                    logger.warning(f"Repository has existing merge conflicts: {conflict_files}")
            except (GitStateError, GitNetworkError):
                # If we can't check for conflicts, proceed anyway
                logger.debug("Could not check for existing conflicts")

        except subprocess.TimeoutExpired:
            raise GitStateError("Timed out capturing original git state")
        except subprocess.CalledProcessError as e:
            raise GitStateError(f"Failed to capture original git state: {e.stderr.strip()}")
        except FileNotFoundError:
            raise GitStateError("Git command not found - ensure git is installed")

    def create_temporary_branch(self, branch_name: str, from_branch: Optional[str] = None) -> None:
        """
        Create a temporary branch and track it for cleanup.

        Args:
            branch_name: Name for the temporary branch
            from_branch: Optional base branch (defaults to current branch)
        """
        try:
            # Create branch from current or specified branch
            base = from_branch or self.original_branch or "HEAD"
            subprocess.run(
                ["git", "-C", str(self.repo_path), "branch", branch_name, base],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )

            self.created_branches.append(branch_name)
            logger.info(f"Created temporary branch: {branch_name} from {base}")

        except subprocess.CalledProcessError as e:
            raise GitStateError(f"Failed to create temporary branch '{branch_name}': {e.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise GitStateError(f"Timed out creating temporary branch '{branch_name}'")

    def switch_to_branch(self, branch_name: str) -> None:
        """
        Switch to a different branch.

        Args:
            branch_name: Branch to switch to
        """
        try:
            subprocess.run(
                ["git", "-C", str(self.repo_path), "checkout", branch_name],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )
            logger.info(f"Switched to branch: {branch_name}")

        except subprocess.CalledProcessError as e:
            raise GitStateError(f"Failed to switch to branch '{branch_name}': {e.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise GitStateError(f"Timed out switching to branch '{branch_name}'")

    def abort_merge(self, target: Optional[str] = None) -> bool:
        """
        Abort the current merge operation, cleaning up conflict state.
        """
        target = target or str(self.repo_path)
        try:
            # Check if we're in a merge state
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )

            # Unmerged entries can use several porcelain status codes (AA, DD,
            # AU, UA, DU, UD, and UU).  Checking only for ``UU`` leaves
            # modify/delete and add/add conflicts in an active merge.  Also
            # honor MERGE_HEAD when conflicts have already been staged as
            # resolved: the repository still needs ``merge --abort``.
            status_lines = result.stdout.splitlines()
            has_unmerged_entries = any(
                len(line) >= 2
                and ("U" in line[:2] or line[:2] in {"AA", "DD"})
                for line in status_lines
            )
            merge_head = self.repo_path / ".git" / "MERGE_HEAD"
            if not has_unmerged_entries and not merge_head.exists():
                logger.debug("No conflicted merge to abort in %s", self.repo_path)
                return True

            subprocess.run(
                ["git", "-C", str(self.repo_path), "merge", "--abort"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )
            logger.info("Aborted merge operation in %s", self.repo_path)
            return True

        except subprocess.TimeoutExpired:
            logger.error("Cleanup failed: operation=abort merge target=%s error=timed out", target)
        except Exception as e:
            logger.error(
                "Cleanup failed: operation=abort merge target=%s error=%s",
                target,
                self._error_context(e),
            )
        return False

    def _perform_cleanup(self) -> None:
        """Perform all cleanup operations to restore original state."""
        if self._cleanup_completed:
            logger.debug("Cleanup already completed, skipping")
            return

        logger.info("Starting git state cleanup for %s", self.repo_path)
        self.cleanup_failures = []
        self.cleanup_state_before = self._capture_cleanup_state()

        # Step 1: Clean up merge state if requested
        if self.cleanup_merge_state:
            conflict_target = ", ".join(
                self.cleanup_state_before.get("conflict_files") or []
            ) or str(self.repo_path)
            try:
                if not self._cleanup_merge_state():
                    self._record_cleanup_failure(
                        "merge conflict cleanup",
                        conflict_target,
                        "merge conflict cleanup did not reach the desired state",
                        before=self.cleanup_state_before,
                        after=self._capture_cleanup_state(),
                    )
            except Exception as error:
                self._record_cleanup_failure(
                    "merge conflict cleanup",
                    conflict_target,
                    error,
                    before=self.cleanup_state_before,
                    after=self._capture_cleanup_state(),
                )

        # Step 2: Return to original branch if requested
        if self.return_to_original_branch and self.original_branch:
            before = self._capture_cleanup_state()
            try:
                self._return_to_original_branch()
            except Exception as error:
                self._record_cleanup_failure(
                    "return to original branch",
                    self.original_branch,
                    error,
                    before=before,
                    after=self._capture_cleanup_state(),
                )

        # Step 3: Clean up temporary branches if requested
        if self.cleanup_branches and self.created_branches:
            before = self._capture_cleanup_state()
            try:
                if not self._cleanup_branches():
                    self._record_cleanup_failure(
                        "temporary branch cleanup",
                        ", ".join(self.created_branches),
                        "one or more temporary branches could not be removed",
                        before=before,
                        after=self._capture_cleanup_state(),
                    )
            except Exception as error:
                self._record_cleanup_failure(
                    "temporary branch cleanup",
                    ", ".join(self.created_branches),
                    error,
                    before=before,
                    after=self._capture_cleanup_state(),
                )

        self.cleanup_state_after = self._capture_cleanup_state()
        self._validate_cleanup_state(self.cleanup_state_after)
        self._cleanup_completed = not self.cleanup_failures

        if self.cleanup_failures:
            summaries = "; ".join(
                f"{failure['operation']} ({failure['target']}): {failure['error']}"
                for failure in self.cleanup_failures
            )
            raise GitCleanupError(
                f"Git cleanup incomplete for {self.repo_path}: {summaries}"
            )

        logger.info("Git state cleanup completed for %s", self.repo_path)

    def _cleanup_merge_state(self) -> None:
        """Clean up any merge conflict state."""
        try:
            # Check for merge conflicts
            conflict_files = detect_merge_conflicts(self.repo_path, timeout=self.timeout)
            merge_head = self.repo_path / ".git" / "MERGE_HEAD"

            if conflict_files or merge_head.exists():
                if conflict_files:
                    logger.warning(f"Cleaning up {len(conflict_files)} conflicted files")
                # Abort the merge to clean up conflict state
                if not self.abort_merge(", ".join(conflict_files)):
                    return False

                # Verify cleanup was successful
                remaining_conflicts = detect_merge_conflicts(self.repo_path, timeout=self.timeout)
                if remaining_conflicts:
                    logger.error(
                        "Cleanup failed: operation=merge conflict cleanup target=%s "
                        "remaining_files=%s",
                        self.repo_path,
                        remaining_conflicts,
                    )
                    return False
                else:
                    logger.info("Successfully cleaned up merge conflicts in %s", self.repo_path)

        except (GitStateError, GitNetworkError) as e:
            logger.error(
                "Cleanup failed: operation=merge conflict cleanup target=%s error=%s",
                self.repo_path,
                self._error_context(e),
            )
            raise
        except Exception as e:
            logger.error(
                "Cleanup failed: operation=merge conflict cleanup target=%s error=%s",
                self.repo_path,
                self._error_context(e),
            )
            raise
        return True

    def _return_to_original_branch(self) -> None:
        """Return to the original branch."""
        if not self.original_branch:
            logger.debug("No original branch to return to")
            return

        try:
            # Get current branch
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )
            current_branch = result.stdout.strip()

            if current_branch != self.original_branch:
                # Switch back to original branch
                subprocess.run(
                    ["git", "-C", str(self.repo_path), "checkout", self.original_branch],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=True,
                )
                logger.info(f"Returned to original branch: {self.original_branch}")
            else:
                logger.debug(f"Already on original branch: {self.original_branch}")

        except subprocess.CalledProcessError as e:
            # Raise exception so __exit__ can convert it to GitCleanupError
            raise GitStateError(f"Failed to return to original branch '{self.original_branch}': {e.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise GitStateError(f"Timed out returning to original branch '{self.original_branch}'")
        except Exception as e:
            raise GitStateError(f"Error returning to original branch: {e}")

    def _cleanup_branches(self) -> bool:
        """Clean up temporary branches that were created."""
        failed = False
        for branch_name in self.created_branches:
            before = self._capture_cleanup_state()
            try:
                # Check if branch still exists
                result = subprocess.run(
                    ["git", "-C", str(self.repo_path), "branch", "--list", branch_name],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=True,
                )

                if result.stdout.strip():
                    # Delete the branch (force delete in case it is not merged).
                    subprocess.run(
                        ["git", "-C", str(self.repo_path), "branch", "-D", branch_name],
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        check=True,
                    )
                    verify = subprocess.run(
                        [
                            "git",
                            "-C",
                            str(self.repo_path),
                            "branch",
                            "--list",
                            branch_name,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        check=True,
                    )
                    if verify.stdout.strip():
                        raise GitCleanupError(
                            f"temporary branch still exists after deletion: {branch_name}"
                        )
                    logger.info("Cleaned up temporary branch %s", branch_name)
                else:
                    logger.debug("Temporary branch %s already deleted", branch_name)

            except Exception as error:
                failed = True
                after = self._capture_cleanup_state()
                self._record_cleanup_failure(
                    "temporary branch cleanup",
                    branch_name,
                    error,
                    before=before,
                    after=after,
                )
                # Continue with the remaining branches so one failure cannot
                # silently leave all later temporary state behind.
                continue
        return not failed


@contextmanager
def git_state_cleanup(
    repo_path: str | Path,
    cleanup_branches: bool = True,
    cleanup_merge_state: bool = True,
    return_to_original_branch: bool = True,
    timeout: int = 30,
):
    """
    Context manager for automatic git state cleanup.

    This is a convenience wrapper around GitStateCleanup that provides
    a context manager interface.

    Args:
        repo_path: Path to the git repository
        cleanup_branches: Whether to clean up temporary branches on exit
        cleanup_merge_state: Whether to clean up merge state on exit
        return_to_original_branch: Whether to return to original branch on exit
        timeout: Timeout for git commands in seconds

    Example:
        with git_state_cleanup("/path/to/repo") as cleanup:
            cleanup.create_temporary_branch("test-branch")
            cleanup.switch_to_branch("test-branch")
            # ... do work ...
            # Automatic cleanup on exit
    """
    with GitStateCleanup(
        repo_path=repo_path,
        cleanup_branches=cleanup_branches,
        cleanup_merge_state=cleanup_merge_state,
        return_to_original_branch=return_to_original_branch,
        timeout=timeout,
    ) as cleanup_mgr:
        yield cleanup_mgr


def cleanup_temporary_branches(
    repo_path: str | Path,
    branch_pattern: Optional[str] = None,
    timeout: int = 30,
    *,
    raise_on_failure: bool = False,
    return_details: bool = False,
) -> list[str] | dict[str, Any]:
    """
    Clean up temporary branches matching a pattern.

    Args:
        repo_path: Path to the git repository
        branch_pattern: Optional pattern to match branch names (e.g., "temp-*")
        If not specified, no branches will be deleted (safety measure)
        timeout: Timeout for git commands in seconds
        raise_on_failure: Raise GitCleanupError after attempting every matching
                           branch when one or more deletions fail.
        return_details: Return both deleted branches and detailed failures.

    Returns:
        List of branch names that were deleted
    """
    repo_path = Path(repo_path)
    deleted_branches = []
    failures: list[tuple[str, BaseException]] = []
    failure_details: list[str] = []

    # Safety measure: if no pattern specified, don't delete any branches
    if not branch_pattern:
        logger.debug("No branch pattern specified - no branches will be deleted (safety measure)")
        if return_details:
            return {"deleted": deleted_branches, "failures": failure_details}
        return deleted_branches

    try:
        # List all branches
        result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )

        branches = result.stdout.strip().split("\n")
        branches = [b for b in branches if b]  # Remove empty strings

        # Filter branches by pattern if specified
        if branch_pattern:
            import fnmatch
            branches = [b for b in branches if fnmatch.fnmatch(b, branch_pattern)]

        # Delete matching branches (excluding current branch).  Every branch is
        # attempted independently so a failure does not hide later failures.
        current_result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        current_branch = current_result.stdout.strip()

        for branch in branches:
            if branch == current_branch:
                logger.debug(f"Skipping current branch: {branch}")
                continue

            try:
                subprocess.run(
                    ["git", "-C", str(repo_path), "branch", "-D", branch],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=True,
                )
                verify_result = subprocess.run(
                    ["git", "-C", str(repo_path), "branch", "--list", branch],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=True,
                )
                if verify_result.stdout.strip():
                    raise GitCleanupError(
                        f"branch still exists after deletion: {branch}"
                    )
                deleted_branches.append(branch)
                logger.info("Deleted temporary branch %s", branch)
            except Exception as error:
                failures.append((branch, error))
                failure_details.append(
                    f"{branch}: {GitStateCleanup._error_context(error)}"
                )
                logger.error(
                    "Cleanup failed: operation=temporary branch deletion "
                    "target=%s error=%s",
                    branch,
                    GitStateCleanup._error_context(error),
                )

        if failures and raise_on_failure:
            details = "; ".join(
                f"{branch}: {GitStateCleanup._error_context(error)}"
                for branch, error in failures
            )
            raise GitCleanupError(
                f"Temporary branch cleanup incomplete for {repo_path}: {details}"
            )

        if return_details:
            return {"deleted": deleted_branches, "failures": failure_details}
        return deleted_branches

    except subprocess.TimeoutExpired:
        logger.error(
            "Cleanup failed: operation=temporary branch listing target=%s error=timed out",
            repo_path,
        )
        raise GitStateError("Timed out cleaning up temporary branches")
    except subprocess.CalledProcessError as e:
        logger.error(
            "Cleanup failed: operation=temporary branch listing target=%s error=%s",
            repo_path,
            GitStateCleanup._error_context(e),
        )
        raise GitStateError(f"Failed to list branches for cleanup: {e.stderr.strip()}")
    except FileNotFoundError:
        logger.error(
            "Cleanup failed: operation=temporary branch listing target=%s error=git not found",
            repo_path,
        )
        raise GitStateError("Git command not found - ensure git is installed")
    except PermissionError as error:
        logger.error(
            "Cleanup failed: operation=temporary branch listing target=%s error=%s",
            repo_path,
            GitStateCleanup._error_context(error),
        )
        raise GitStateError(
            f"Permission denied listing temporary branches in {repo_path}"
        ) from error
    except OSError as error:
        logger.error(
            "Cleanup failed: operation=temporary branch listing target=%s error=%s",
            repo_path,
            GitStateCleanup._error_context(error),
        )
        raise GitStateError(
            f"Filesystem error listing temporary branches in {repo_path}: {error}"
        ) from error


def cleanup_merge_state(repo_path: str | Path, timeout: int = 30) -> bool:
    """
    Clean up merge conflict state by aborting the current merge.

    Args:
        repo_path: Path to the git repository
        timeout: Timeout for git commands in seconds

    Returns:
        True if cleanup was successful, False otherwise
    """
    repo_path = Path(repo_path)

    try:
        # Check for merge conflicts
        conflict_files = detect_merge_conflicts(repo_path, timeout=timeout)

        if not conflict_files:
            logger.debug("No merge conflicts to clean up")
            return True

        logger.info(f"Cleaning up {len(conflict_files)} conflicted files")

        # Abort the merge.  ``check=True`` is important here: reporting a
        # successful cleanup after git rejected the abort is a silent partial
        # cleanup failure.
        subprocess.run(
            ["git", "-C", str(repo_path), "merge", "--abort"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )

        # Verify cleanup was successful
        remaining_conflicts = detect_merge_conflicts(repo_path, timeout=timeout)
        if remaining_conflicts:
            logger.error(
                "Cleanup failed: operation=merge conflict cleanup target=%s "
                "remaining_files=%s",
                ", ".join(conflict_files),
                remaining_conflicts,
            )
            return False

        logger.info("Successfully cleaned up merge conflicts")
        return True

    except (GitStateError, GitNetworkError) as e:
        logger.error(
            "Cleanup failed: operation=merge conflict cleanup target=%s error=%s",
            repo_path,
            GitStateCleanup._error_context(e),
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error(
            "Cleanup failed: operation=merge conflict cleanup target=%s error=timed out",
            repo_path,
        )
        return False
    except Exception as e:
        logger.error(
            "Cleanup failed: operation=merge conflict cleanup target=%s error=%s",
            repo_path,
            GitStateCleanup._error_context(e),
        )
        return False


def cleanup_all_temporary_state(repo_path: str | Path, timeout: int = 30) -> dict:
    """
    Perform comprehensive cleanup of all temporary git state.

    This function cleans up:
    - Merge conflicts
    - Temporary branches (common patterns: temp-*, test-*, tmp-*)
    - Returns to main branch if not on a standard branch

    Args:
        repo_path: Path to the git repository
        timeout: Timeout for git commands in seconds

    Returns:
        Dictionary with cleanup results
    """
    repo_path = Path(repo_path)
    results = {
        "merge_conflicts_cleaned": False,
        "temporary_branches_deleted": [],
        "returned_to_main": False,
        "errors": [],
        "cleanup_complete": False,
    }

    # Clean up merge conflicts
    try:
        results["merge_conflicts_cleaned"] = cleanup_merge_state(repo_path, timeout=timeout)
        if not results["merge_conflicts_cleaned"]:
            results["errors"].append(
                f"Merge cleanup did not reach the desired state in {repo_path}"
            )
    except Exception as e:
        error = f"Merge cleanup error for {repo_path}: {GitStateCleanup._error_context(e)}"
        logger.error(error)
        results["errors"].append(error)

    # Check if on a temporary branch and switch to main first
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        current_branch = result.stdout.strip()

        # If on a temporary-looking branch, switch to main first
        if current_branch and any(current_branch.startswith(p) for p in ["temp-", "test-", "tmp-", "draft-"]):
            subprocess.run(
                ["git", "-C", str(repo_path), "checkout", "main"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            results["returned_to_main"] = True
            logger.info(f"Returned from temporary branch '{current_branch}' to main")
    except Exception as e:
        error = f"Branch switch error for {repo_path}: {GitStateCleanup._error_context(e)}"
        logger.error(error)
        results["errors"].append(error)

    # Clean up temporary branches (after switching to main)
    for pattern in ["temp-*", "test-*", "tmp-*", "draft-*"]:
        try:
            branch_result = cleanup_temporary_branches(
                repo_path,
                branch_pattern=pattern,
                timeout=timeout,
                return_details=True,
            )
            results["temporary_branches_deleted"].extend(branch_result["deleted"])
            for failure in branch_result["failures"]:
                error = (
                    f"Branch cleanup error for pattern {pattern} in {repo_path}: "
                    f"{failure}"
                )
                logger.error(error)
                results["errors"].append(error)
        except Exception as e:
            error = (
                f"Branch cleanup error for pattern {pattern} in {repo_path}: "
                f"{GitStateCleanup._error_context(e)}"
            )
            logger.error(error)
            results["errors"].append(error)

    # Final state validation makes partial cleanup observable even when every
    # individual command returned successfully but a concurrent actor restored
    # state before verification.
    try:
        final_branch_result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        final_branch = final_branch_result.stdout.strip()
        if results["returned_to_main"] and final_branch != "main":
            results["errors"].append(
                f"Cleanup state validation failed for {repo_path}: "
                f"expected main, found {final_branch!r}"
            )

        remaining = []
        for pattern in ["temp-*", "test-*", "tmp-*", "draft-*"]:
            branches_result = subprocess.run(
                ["git", "-C", str(repo_path), "branch", "--list", pattern],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            remaining.extend(
                line.strip().lstrip("* ")
                for line in branches_result.stdout.splitlines()
                if line.strip()
            )
        if remaining:
            error = (
                f"Cleanup state validation failed for {repo_path}: "
                f"temporary branches remain: {sorted(set(remaining))}"
            )
            logger.error(error)
            results["errors"].append(error)
    except Exception as e:
        error = f"Cleanup state validation error for {repo_path}: {GitStateCleanup._error_context(e)}"
        logger.error(error)
        results["errors"].append(error)

    results["cleanup_complete"] = not results["errors"]
    if results["errors"]:
        logger.error(
            "Partial git cleanup for %s: %d error(s)",
            repo_path,
            len(results["errors"]),
        )
    else:
        logger.info("Complete git cleanup for %s", repo_path)

    return results
