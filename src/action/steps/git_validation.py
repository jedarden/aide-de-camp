"""
Git validation utilities for pre-flight checks.

This module provides standalone validation functions for git repository state
that can be used before any git operations. These checks help ensure the
repository is in a clean, expected state before performing mutations.

All validation functions raise GitStateError with descriptive messages
when validation fails, making it clear what needs to be fixed.
"""

import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


class GitError(RuntimeError):
    """Base exception for git operation failures."""
    pass


class GitConflictError(GitError):
    """
    Raised when git operations encounter merge conflicts or rejection.

    Attributes:
        message: Error message describing the conflict
        conflict_files: List of files with conflicts (if detected)
        conflict_type: Type of conflict (merge, push_rejection, etc.)
        details: Additional context about the conflict
    """
    def __init__(
        self,
        message: str,
        conflict_files: list[str] | None = None,
        conflict_type: str = "merge",
        details: dict | None = None,
    ):
        super().__init__(message)
        self.conflict_files = conflict_files or []
        self.conflict_type = conflict_type
        self.details = details or {}

    def __str__(self) -> str:
        """Return formatted error message with conflict details."""
        base_msg = super().__str__()
        if self.conflict_files:
            files_msg = f"\nConflicting files ({len(self.conflict_files)}): {', '.join(self.conflict_files[:5])}"
            if len(self.conflict_files) > 5:
                files_msg += f" ... and {len(self.conflict_files) - 5} more"
            base_msg += files_msg
        if self.details:
            details_msg = "\nDetails: " + ", ".join(f"{k}={v}" for k, v in self.details.items())
            base_msg += details_msg
        return base_msg


class GitNetworkError(GitError):
    """Raised when git operations fail due to network issues."""
    pass


class GitAuthenticationError(GitError):
    """Raised when git operations fail due to authentication issues."""
    pass


class GitStateError(GitError):
    """Raised when git repository is in an unexpected state."""
    pass


class GitValidationError(RuntimeError):
    """Raised when git validation fails with specific details."""
    def __init__(self, message: str, check_type: str, details: dict | None = None):
        super().__init__(message)
        self.check_type = check_type
        self.details = details or {}


def check_git_repository(
    repo_path: str | Path,
    timeout: int = 10,
) -> None:
    """
    Verify that a path is a valid git repository.

    Args:
        repo_path: Path to the repository
        timeout: Timeout in seconds for git commands

    Raises:
        GitStateError: If path is not a git repository
        GitNetworkError: If git command times out
    """
    repo_path = Path(repo_path)

    if not repo_path.exists():
        raise GitStateError(f"Repository path does not exist: {repo_path}")

    git_dir = repo_path / ".git"
    if not git_dir.exists():
        raise GitStateError(f"Not a git repository: {repo_path}")

    # Verify git is functional by running a simple command
    try:
        subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except subprocess.TimeoutExpired:
        raise GitNetworkError("Git repository check timed out")
    except subprocess.CalledProcessError as e:
        raise GitStateError(f"Git repository validation failed: {e.stderr.strip()}")
    except FileNotFoundError:
        raise GitStateError("Git command not found - ensure git is installed")


def check_current_branch(
    repo_path: str | Path,
    expected_branch: str = "main",
    timeout: int = 10,
) -> str:
    """
    Verify the repository is on the expected branch.

    Args:
        repo_path: Path to the repository
        expected_branch: Expected branch name (default: "main")
        timeout: Timeout in seconds for git commands

    Returns:
        The current branch name

    Raises:
        GitStateError: If not on the expected branch
        GitNetworkError: If git command times out
    """
    repo_path = Path(repo_path)

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )

        current_branch = result.stdout.strip()

        if current_branch != expected_branch:
            raise GitStateError(
                f"Not on expected branch '{expected_branch}': currently on '{current_branch}'. "
                f"Please switch to {expected_branch} branch first."
            )

        return current_branch

    except subprocess.TimeoutExpired:
        raise GitNetworkError("Git branch check timed out")
    except subprocess.CalledProcessError as e:
        raise GitStateError(f"Failed to determine current branch: {e.stderr.strip()}")
    except FileNotFoundError:
        raise GitStateError("Git command not found - ensure git is installed")


def check_uncommitted_changes(
    repo_path: str | Path,
    timeout: int = 10,
) -> None:
    """
    Verify the repository has no uncommitted changes.

    Args:
        repo_path: Path to the repository
        timeout: Timeout in seconds for git commands

    Raises:
        GitStateError: If repository has uncommitted changes
        GitNetworkError: If git command times out
    """
    repo_path = Path(repo_path)

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        if result.stdout.strip():
            # Parse the output to provide more helpful error messages
            changes = result.stdout.strip().split("\n")
            staged = [line for line in changes if line.startswith((" M", "M ", "MM", "A", "D")) and line[1] != " "]
            unstaged = [line for line in changes if line[1] == " " or line.startswith("??")]

            error_parts = []
            if unstaged:
                error_parts.append(f"{len(unstaged)} unstaged change(s)")
            if staged:
                error_parts.append(f"{len(staged)} staged change(s)")

            raise GitStateError(
                f"Repository has uncommitted changes ({', '.join(error_parts)}). "
                f"Please commit or stash them first.\n"
                f"Changes:\n{result.stdout.strip()}"
            )

    except subprocess.TimeoutExpired:
        raise GitNetworkError("Git status check timed out")
    except FileNotFoundError:
        raise GitStateError("Git command not found - ensure git is installed")


def check_remote_configuration(
    repo_path: str | Path,
    expected_remote_pattern: str | None = None,
    timeout: int = 10,
    require_remote: bool = False,
) -> dict[str, str]:
    """
    Verify git remote configuration and check for authentication issues.

    Args:
        repo_path: Path to the repository
        expected_remote_pattern: Optional pattern that should appear in remote URL
        timeout: Timeout in seconds for git commands
        require_remote: If False, skip validation when no remotes configured

    Returns:
        Dictionary with remote information

    Raises:
        GitStateError: If remote configuration is invalid
        GitAuthenticationError: If authentication fails
        GitNetworkError: If git command times out
    """
    repo_path = Path(repo_path)

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "-v"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        # Check for authentication failures
        if result.returncode != 0:
            error_output = result.stderr.lower()
            if any(pattern in error_output for pattern in [
                "authentication", "permission denied", "credentials", "auth", "fatal"
            ]):
                raise GitAuthenticationError(f"Git authentication failed: {result.stderr.strip()}")
            raise GitStateError(f"Git remote check failed: {result.stderr.strip()}")

        # Parse remote information
        remotes = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                url = parts[1]
                remotes[name] = url

        if not remotes:
            if require_remote:
                raise GitStateError("No git remotes configured")
            else:
                # Return empty dict when remotes not required
                logger.debug("No git remotes configured (remote check not required)")
                return {}

        # Check for expected pattern
        if expected_remote_pattern and remotes:
            pattern_found = any(expected_remote_pattern in url for url in remotes.values())
            if not pattern_found:
                raise GitStateError(
                    f"Git remote does not match expected pattern '{expected_remote_pattern}'. "
                    f"Configured remotes: {list(remotes.keys())}"
                )

        return remotes

    except subprocess.TimeoutExpired:
        raise GitNetworkError("Git remote check timed out")
    except FileNotFoundError:
        raise GitStateError("Git command not found - ensure git is installed")


def check_disk_space(
    repo_path: str | Path,
    min_free_mb: int = 100,
) -> None:
    """
    Verify there's sufficient disk space for git operations.

    Args:
        repo_path: Path to the repository
        min_free_mb: Minimum free space in megabytes

    Raises:
        GitStateError: If insufficient disk space
    """
    repo_path = Path(repo_path)

    try:
        stat = os.statvfs(repo_path)
        free_mb = (stat.f_bavail * stat.f_frsize) // (1024 * 1024)

        if free_mb < min_free_mb:
            raise GitStateError(
                f"Insufficient disk space: {free_mb}MB free, {min_free_mb}MB required"
            )
    except AttributeError:
        # statvfs not available (Windows, etc.) - skip check
        logger.debug("Disk space check not available on this platform")
    except GitStateError:
        # Re-raise our own errors
        raise
    except Exception as e:
        # Log but don't fail for other errors - disk space checks can be flaky
        logger.debug(f"Could not check disk space: {e}")


def check_file_permissions(
    repo_path: str | Path,
) -> None:
    """
    Verify write permissions to the repository.

    Args:
        repo_path: Path to the repository

    Raises:
        GitStateError: If no write permission
    """
    repo_path = Path(repo_path)

    try:
        # Test write permission by creating a temp file
        test_file = repo_path / ".write_test_temp"
        test_file.touch()
        # Atomic unlink with idempotent cleanup (safe if file already deleted)
        test_file.unlink(missing_ok=True)
    except PermissionError:
        raise GitStateError(f"No write permission for repository: {repo_path}")
    except Exception as e:
        # Log but don't fail - permission checks can be flaky in some environments
        logger.debug(f"Could not verify file permissions: {e}")


def detect_merge_conflicts(
    repo_path: str | Path,
    timeout: int = 10,
) -> list[str]:
    """
    Detect files with merge conflict markers in the working directory.

    This function actively scans the repository for conflict markers (<<<<<<<,
    =======, >>>>>>>) in tracked files to identify which files have unresolved
    merge conflicts.

    Args:
        repo_path: Path to the repository
        timeout: Timeout in seconds for git commands

    Returns:
        List of file paths (relative to repo root) that contain conflict markers

    Raises:
        GitStateError: If repository check fails
        GitNetworkError: If git command times out

    Example:
        >>> conflicts = detect_merge_conflicts("/path/to/repo")
        >>> if conflicts:
        ...     raise GitConflictError(
        ...         "Merge conflicts detected",
        ...         conflict_files=conflicts,
        ...         conflict_type="merge"
        ...     )
    """
    repo_path = Path(repo_path)

    try:
        # First check if we're in a merge/rebase/cherry-pick state
        # This is faster than scanning all files
        merge_head = repo_path / ".git" / "MERGE_HEAD"
        rebase_merge = repo_path / ".git" / "rebase" / "merge"
        cherry_pick_head = repo_path / ".git" / "CHERRY_PICK_HEAD"

        in_merge_state = (
            merge_head.exists() or
            rebase_merge.exists() or
            cherry_pick_head.exists()
        )

        if not in_merge_state:
            # Not in any conflict state, return early
            logger.debug(f"No merge conflict state detected in {repo_path}")
            return []

        # Search for files with conflict markers using git grep
        # This is more efficient than scanning all files manually
        result = subprocess.run(
            ["git", "-C", str(repo_path), "grep", "--cached", "-l", "^<<<<<<< "],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        # Also check working directory for unstaged conflicts
        result_working = subprocess.run(
            ["git", "-C", str(repo_path), "grep", "-l", "^<<<<<<< "],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        conflict_files = []

        # Parse cached (staged) conflicts
        if result.stdout.strip():
            files = result.stdout.strip().split("\n")
            conflict_files.extend(files)

        # Parse working directory conflicts
        if result_working.stdout.strip():
            files = result_working.stdout.strip().split("\n")
            conflict_files.extend(files)

        # Remove duplicates and sort
        conflict_files = sorted(set(conflict_files))

        if conflict_files:
            logger.warning(
                f"Detected {len(conflict_files)} file(s) with merge conflicts: "
                f"{', '.join(conflict_files[:5])}"
                + (f" ... and {len(conflict_files) - 5} more" if len(conflict_files) > 5 else "")
            )

        return conflict_files

    except subprocess.TimeoutExpired:
        raise GitNetworkError("Git conflict detection timed out")
    except FileNotFoundError:
        raise GitStateError("Git command not found - ensure git is installed")
    except Exception as e:
        logger.error(f"Failed to detect merge conflicts: {e}")
        # Don't raise - conflict detection is best-effort
        return []


def check_and_clean_git_locks(
    repo_path: str | Path,
) -> list[str]:
    """
    Check for and clean up git lock files from previous incomplete operations.

    Args:
        repo_path: Path to the repository

    Returns:
        List of lock file names that were found and cleaned

    Raises:
        GitStateError: If lock files cannot be cleaned
    """
    repo_path = Path(repo_path)
    git_dir = repo_path / ".git"

    lock_files = [
        git_dir / "index.lock",           # Git index lock
        git_dir / "MERGE_HEAD",           # Merge state
        git_dir / "CHERRY_PICK_HEAD",     # Cherry-pick state
        git_dir / "REVERT_HEAD",          # Revert state
        git_dir / "BISECT_LOG",           # Bisect state
        git_dir / "rebase",               # Rebase state directory
        git_dir / "MERGE_MSG",            # Merge message
    ]

    locks_found = []
    for lock_file in lock_files:
        if lock_file.exists():
            locks_found.append(lock_file.name)
            try:
                # Rename the exact, repository-owned path into a unique
                # quarantine first. The rename is the claim/commit point: a
                # concurrent git operation that replaces the lock after the
                # scan cannot have its new lock recursively deleted.
                quarantine = git_dir / f".adc-cleanup-{uuid.uuid4().hex}"
                try:
                    lock_file.replace(quarantine)
                except FileNotFoundError:
                    # Another owner completed this exact cleanup.
                    logger.debug(f"Git lock file already removed: {lock_file}")
                    continue
                if quarantine.is_dir():
                    shutil.rmtree(quarantine)
                else:
                    quarantine.unlink(missing_ok=True)
                logger.warning(f"Cleaned up git lock file: {lock_file}")
            except FileNotFoundError:
                # Idempotent: file already removed by another process, not an error
                logger.debug(f"Git lock file already removed: {lock_file}")
            except PermissionError as e:
                logger.error(f"Permission denied cleaning up git lock file {lock_file}: {e}")
                raise GitStateError(f"Cannot clean up git lock file {lock_file}: {e}")
            except Exception as e:
                logger.error(f"Failed to clean up git lock file {lock_file}: {e}")
                raise GitStateError(f"Cannot clean up git lock file {lock_file}: {e}")

    if locks_found:
        logger.warning(f"Found and cleaned up git state files: {locks_found}")

    return locks_found


class PreflightGitValidation:
    """
    Comprehensive pre-flight validation suite for git operations.

    This class runs all validation checks in a configurable order,
    providing detailed error reporting and early failure detection.
    """

    def __init__(
        self,
        repo_path: str | Path,
        expected_branch: str = "main",
        expected_remote_pattern: str | None = None,
        timeout: int = 10,
        min_free_mb: int = 100,
        strict: bool = True,
    ):
        """
        Initialize pre-flight validation.

        Args:
            repo_path: Path to the git repository
            expected_branch: Expected branch name
            expected_remote_pattern: Optional pattern for remote validation
            timeout: Timeout for git commands
            min_free_mb: Minimum free disk space in MB
            strict: If False, continue validation after errors to report all issues
        """
        self.repo_path = Path(repo_path)
        self.expected_branch = expected_branch
        self.expected_remote_pattern = expected_remote_pattern
        self.timeout = timeout
        self.min_free_mb = min_free_mb
        self.strict = strict

        self.results: list[dict[str, any]] = []
        self.errors: list[GitStateError | GitAuthenticationError | GitNetworkError] = []

    def validate_all(self) -> bool:
        """
        Run all validation checks.

        Returns:
            True if all validations pass

        Raises:
            GitStateError: If any validation fails (in strict mode)
            GitAuthenticationError: If authentication fails (in strict mode)
            GitNetworkError: If network operations fail (in strict mode)
        """
        logger.info(f"Starting pre-flight git validation for {self.repo_path}")

        # Define validation steps in order
        steps = [
            ("repository", self._validate_repository),
            ("branch", self._validate_branch),
            ("uncommitted_changes", self._validate_uncommitted),
            ("remote", self._validate_remote),
            ("locks", self._validate_locks),
            ("disk_space", self._validate_disk_space),
            ("permissions", self._validate_permissions),
        ]

        for step_name, step_func in steps:
            try:
                step_func()
                self.results.append({
                    "check": step_name,
                    "status": "passed",
                    "message": f"{step_name} validation passed",
                })
            except (GitStateError, GitAuthenticationError, GitNetworkError) as e:
                self.errors.append(e)
                self.results.append({
                    "check": step_name,
                    "status": "failed",
                    "message": str(e),
                    "error_type": type(e).__name__,
                })

                if self.strict:
                    raise

        if self.errors:
            logger.warning(
                f"Preflight validation completed with {len(self.errors)} error(s)"
            )
            for error in self.errors:
                logger.error(f"  - {error}")
        else:
            logger.info("Preflight validation completed successfully")

        return len(self.errors) == 0

    def _validate_repository(self) -> None:
        """Validate git repository."""
        check_git_repository(self.repo_path, self.timeout)

    def _validate_branch(self) -> None:
        """Validate current branch."""
        check_current_branch(self.repo_path, self.expected_branch, self.timeout)

    def _validate_uncommitted(self) -> None:
        """Validate no uncommitted changes."""
        check_uncommitted_changes(self.repo_path, self.timeout)

    def _validate_remote(self) -> None:
        """Validate remote configuration."""
        check_remote_configuration(
            self.repo_path,
            self.expected_remote_pattern,
            self.timeout,
            require_remote=bool(self.expected_remote_pattern),
        )

    def _validate_locks(self) -> None:
        """Validate and clean git locks."""
        check_and_clean_git_locks(self.repo_path)

    def _validate_disk_space(self) -> None:
        """Validate disk space."""
        check_disk_space(self.repo_path, self.min_free_mb)

    def _validate_permissions(self) -> None:
        """Validate file permissions."""
        check_file_permissions(self.repo_path)

    def get_summary(self) -> dict[str, any]:
        """
        Get validation summary.

        Returns:
            Dictionary with validation results summary
        """
        return {
            "repo_path": str(self.repo_path),
            "expected_branch": self.expected_branch,
            "total_checks": len(self.results),
            "passed": sum(1 for r in self.results if r["status"] == "passed"),
            "failed": sum(1 for r in self.results if r["status"] == "failed"),
            "results": self.results,
            "errors": [str(e) for e in self.errors],
        }


def validate_git_state(
    repo_path: str | Path,
    expected_branch: str = "main",
    expected_remote_pattern: str | None = None,
    strict: bool = True,
) -> dict[str, any]:
    """
    Convenience function to validate git state with default checks.

    Args:
        repo_path: Path to the git repository
        expected_branch: Expected branch name (default: "main")
        expected_remote_pattern: Optional pattern for remote validation
        strict: If False, continue after errors to report all issues

    Returns:
        Dictionary with validation results

    Raises:
        GitStateError: If validation fails (in strict mode)
        GitAuthenticationError: If authentication fails (in strict mode)
        GitNetworkError: If network operations fail (in strict mode)

    Example:
        ```python
        # Basic validation (raises on first error)
        validate_git_state("/path/to/repo")

        # Non-strict mode (report all errors)
        results = validate_git_state("/path/to/repo", strict=False)
        if results["failed"] > 0:
            print(f"Validation failed with {results['failed']} errors")
        ```
    """
    validator = PreflightGitValidation(
        repo_path=repo_path,
        expected_branch=expected_branch,
        expected_remote_pattern=expected_remote_pattern,
        strict=strict,
    )

    validator.validate_all()
    return validator.get_summary()
