"""
GitOps mutation step for declarative-config edits.

This step performs templated field substitutions in YAML manifests, commits
the changes with the standard git identity, and pushes to origin. It is designed
to be strictly guarded to only perform templated substitutions — no LLM-authored
edits allowed.

Key security constraints:
- Never free-form edits — only templated substitutions
- Never direct kubectl mutations — all changes go through GitOps
- Commit with standard git identity (github@jedarden.com / jedarden)
- Push to origin main only
"""

import asyncio
import logging
import random
import subprocess
import time
import tempfile
import shutil
import os
from dataclasses import dataclass, field as dataclass_field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Literal

import yaml

# Import validation utilities for pre-flight checks
from .git_validation import (
    GitError,
    GitConflictError,
    GitNetworkError,
    GitAuthenticationError,
    GitStateError,
    PreflightGitValidation,
    detect_merge_conflicts,
)

# Import atomic write utility for safe file operations
from src.utils.atomic_write import atomic_write

logger = logging.getLogger(__name__)

GitOperationStatus = Literal["success", "failed", "partial"]


def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.25,
    log_retries: bool = True,
):
    """
    Decorator to retry functions that fail with transient network errors using exponential backoff.

    Implements exponential backoff with jitter to prevent thundering herd:
    delay = min(base_delay * 2^attempt, max_delay)
    jitter = delay * (random value in [-jitter_factor, +jitter_factor])
    final_delay = delay + jitter

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay before first retry in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 60.0)
        jitter_factor: Jitter as fraction of delay, ±25% by default (default: 0.25)
        log_retries: Whether to log retry attempts (default: True)

    Returns:
        Decorated function that retries on transient errors with exponential backoff
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except GitNetworkError as e:
                    # Network errors are transient - retry with backoff
                    if attempt >= max_retries:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for {func.__name__}. "
                            f"Last error: {type(e).__name__}: {e}"
                        )
                        raise

                    # Calculate exponential backoff delay
                    delay = min(base_delay * (2 ** attempt), max_delay)

                    # Add jitter: ±jitter_factor of the delay
                    jitter = delay * random.uniform(-jitter_factor, jitter_factor)
                    final_delay = delay + jitter

                    if log_retries:
                        logger.warning(
                            f"Transient network error in {func.__name__} on attempt "
                            f"{attempt + 1}/{max_retries + 1}, "
                            f"retrying in {final_delay:.2f}s "
                            f"(base: {delay:.2f}s, jitter: {jitter:+.2f}s): "
                            f"{type(e).__name__}: {e}"
                        )

                    time.sleep(final_delay)
                except (GitAuthenticationError, GitConflictError) as e:
                    # These are permanent errors - don't retry
                    logger.error(
                        f"Non-transient error in {func.__name__} (no retry): "
                        f"{type(e).__name__}: {e}"
                    )
                    raise
                except Exception as e:
                    # Unknown error - don't retry to be safe
                    logger.error(
                        f"Unexpected error in {func.__name__} (no retry): "
                        f"{type(e).__name__}: {e}"
                    )
                    raise

        return wrapper
    return decorator


@dataclass
class GitOperationResult:
    """Structured outcome of a GitOps operation.

    ``partial`` is used when the local commit succeeded but a later operation,
    normally the push, did not.  Keeping the commit SHA in that case lets a
    caller recover or retry without losing track of the local change.

    The ``success``, ``data``, and ``error`` accessors intentionally retain the
    old step-result interface while callers migrate to the explicit fields.
    """

    commit_sha: str | None = None
    branch: str | None = None
    manifest_path: str | None = None
    status: GitOperationStatus = "failed"
    error: str | None = None
    details: dict[str, Any] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"success", "failed", "partial"}:
            raise ValueError(f"Unsupported Git operation status: {self.status}")

    @property
    def success(self) -> bool:
        """Return whether the complete operation succeeded."""
        return self.status == "success"

    @property
    def data(self) -> dict[str, Any]:
        """Expose structured fields through the legacy result payload."""
        return {
            **self.details,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
            "manifest_path": self.manifest_path,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result for action/executor boundaries."""
        return {
            **self.data,
            "error": self.error,
        }


@dataclass
class StepResult:
    """Deprecated generic step result retained for non-GitOps imports."""
    success: bool
    data: dict[str, Any]
    error: str | None = None


@dataclass
class TemplateField:
    """
    A template field that can be substituted in a YAML manifest.

    Fields are specified as JSON Pointer paths (RFC 6901) relative to the
    document root. For example:
    - "/spec/template/spec/containers/0/image" → first container's image
    - "/spec/replicas" → replica count
    """
    path: str
    value: str | int

    def validate(self) -> None:
        """Validate that the field path is allowed."""
        # Security: only allow specific paths
        # Must start with / and not contain any wildcards or special chars
        if not self.path.startswith("/"):
            raise ValueError(f"Invalid field path '{self.path}': must start with /")

        # Check for suspicious patterns that might indicate free-form editing
        suspicious_patterns = ["*", "..", "//", "\n", "\r"]
        for pattern in suspicious_patterns:
            if pattern in self.path:
                raise ValueError(f"Invalid field path '{self.path}': contains forbidden pattern '{pattern}'")


class GitOpsCommitStep:
    """
    Perform templated declarative-config edits, commit, and push.

    This step reads a project manifest from jedarden/declarative-config,
    applies templated field substitutions (e.g., image tag), commits with
    the standard git identity, and pushes to origin main.

    The step is strictly guarded to only perform templated substitutions —
    no LLM-authored edits are allowed. All field paths are validated against
    a whitelist of allowed patterns.

    Returns:
        GitOperationResult with commit SHA, branch, manifest path, and status
    """

    # Allowed field path prefixes for security
    # These are the only paths that can be modified
    ALLOWED_PATH_PREFIXES = [
        "/spec/template/spec/containers/",  # container images
        "/spec/replicas",                    # replica counts
        "/spec/template/spec/",             # other template spec fields
    ]
    TARGET_BRANCH = "main"

    def __init__(
        self,
        declarative_config_path: str = "/home/coding/declarative-config",
        git_email: str = "github@jedarden.com",
        git_name: str = "jedarden",
        timeout: int = 30,
    ):
        """
        Initialize GitOps commit step.

        Args:
            declarative_config_path: Path to declarative-config repository
            git_email: Git commit email
            git_name: Git commit name
            timeout: Git operation timeout in seconds
        """
        self.declarative_config_path = Path(declarative_config_path)
        self.git_email = git_email
        self.git_name = git_name
        self.timeout = timeout

    def _operation_result(
        self,
        manifest_path: str | None,
        status: GitOperationStatus,
        *,
        commit_sha: str | None = None,
        error: str | None = None,
        **details: Any,
    ) -> GitOperationResult:
        """Build a result with the common GitOps operation metadata."""
        return GitOperationResult(
            commit_sha=commit_sha,
            branch=self.TARGET_BRANCH,
            manifest_path=manifest_path or None,
            status=status,
            error=error,
            details=details,
        )

    async def execute(
        self,
        manifest_path: str,
        template_fields: list[dict[str, Any]],
        project_cfg: dict[str, Any],
        dry_run: bool = False,
        **kwargs,
    ) -> GitOperationResult:
        """
        Execute GitOps commit with templated field substitutions.

        Args:
            manifest_path: Path to manifest file within declarative-config
                          (e.g., "k8s/ardenone-cluster/botburrow/deployment.yaml")
            template_fields: List of {path: str, value: str|int} dicts for substitution
            project_cfg: Project configuration with cluster/namespace info
            dry_run: If True, skip actual commit and push

        Returns:
            GitOperationResult with commit, branch, manifest, and status information
        """
        logger.info(f"Executing gitops_commit step for manifest '{manifest_path}'")

        # Validate inputs
        if not manifest_path:
            return self._operation_result(
                None,
                "failed",
                error="manifest_path is required",
            )

        if not template_fields:
            return self._operation_result(
                manifest_path,
                "failed",
                error="template_fields is required",
            )

        # Build full path to manifest
        full_manifest_path = self.declarative_config_path / manifest_path
        if not full_manifest_path.exists():
            return self._operation_result(
                manifest_path,
                "failed",
                error=f"Manifest file not found: {full_manifest_path}",
            )

        # Validate that we're in declarative-config (skip validation in dry_run mode)
        if not dry_run:
            try:
                self._validate_declarative_config_repo()
            except (GitStateError, GitAuthenticationError, GitNetworkError, GitError) as e:
                return self._operation_result(
                    manifest_path,
                    "failed",
                    error=str(e),
                )

        # Parse and validate template fields
        try:
            validated_fields = self._parse_and_validate_fields(template_fields)
        except (ValueError, RuntimeError) as e:
            return self._operation_result(
                manifest_path,
                "failed",
                template_fields=template_fields,
                error=f"Invalid template fields: {e}",
            )

        # Read manifest YAML
        try:
            manifest_data = self._read_manifest(full_manifest_path)
        except Exception as e:
            return self._operation_result(
                manifest_path,
                "failed",
                error=f"Failed to read manifest: {e}",
            )

        # Apply templated substitutions
        try:
            modified_manifest = self._apply_substitutions(manifest_data, validated_fields)
        except Exception as e:
            return self._operation_result(
                manifest_path,
                "failed",
                fields=[{"path": field.path, "value": field.value} for field in validated_fields],
                error=f"Failed to apply substitutions: {e}",
            )

        # Validate that no kubectl mutations are performed
        if self._detect_kubectl_mutation_risk(template_fields):
            logger.warning("gitops-commit: detected potential kubectl mutation risk - ensure GitOps compliance")

        if dry_run:
            logger.info("Dry run: skipping commit and push")
            return self._operation_result(
                manifest_path,
                "success",
                dry_run=True,
                modifications=len(validated_fields),
                preview=self._diff_manifests(manifest_data, modified_manifest),
            )

        # Write modified manifest
        try:
            self._write_manifest(full_manifest_path, modified_manifest)
        except Exception as e:
            return self._operation_result(
                manifest_path,
                "failed",
                error=f"Failed to write manifest: {e}",
            )

        # Commit changes
        original_manifest_backup = None
        try:
            # Backup original manifest for potential rollback
            original_manifest_backup = manifest_data

            commit_result = self._commit_changes(
                manifest_path,
                validated_fields,
                project_cfg,
            )
            commit_sha = commit_result.commit_sha
        except (GitConflictError, GitAuthenticationError, GitStateError) as e:
            # Rollback on commit failure for git-specific errors
            try:
                self._write_manifest(full_manifest_path, original_manifest_backup or manifest_data)
                logger.info(f"Rolled back manifest changes after commit failure: {e}")
            except Exception as rollback_error:
                logger.error(f"Failed to rollback changes: {rollback_error}")

            return self._operation_result(
                manifest_path,
                "failed",
                error=f"Failed to commit changes: {e}",
            )
        except Exception as e:
            # Rollback on any other error
            try:
                self._write_manifest(full_manifest_path, original_manifest_backup or manifest_data)
                logger.info(f"Rolled back manifest changes after unexpected error: {e}")
            except Exception as rollback_error:
                logger.error(f"Failed to rollback changes: {rollback_error}")

            return self._operation_result(
                manifest_path,
                "failed",
                error=f"Failed to commit changes: {e}",
            )

        # Push to origin
        try:
            self._push_changes(manifest_path=manifest_path, commit_sha=commit_sha)
        except (GitConflictError, GitAuthenticationError) as e:
            # Don't rollback on push failures - commit is local and valid
            # User can resolve conflicts or auth issues and retry
            return self._operation_result(
                manifest_path,
                "partial",
                commit_sha=commit_sha,
                commit_locally=True,
                error=f"Failed to push changes: {e}",
            )
        except GitNetworkError as e:
            # Network failures might be transient
            return self._operation_result(
                manifest_path,
                "partial",
                commit_sha=commit_sha,
                commit_locally=True,
                error=f"Failed to push changes (network): {e}",
            )
        except Exception as e:
            return self._operation_result(
                manifest_path,
                "partial",
                commit_sha=commit_sha,
                error=f"Failed to push changes: {e}",
            )

        logger.info(f"gitops_commit completed: commit={commit_sha}, manifest={manifest_path}")

        return self._operation_result(
            manifest_path,
            "success",
            commit_sha=commit_sha,
            modifications=len(validated_fields),
        )

    def _validate_declarative_config_repo(self) -> None:
        """
        Validate that we're in the declarative-config repository.

        Uses comprehensive pre-flight validation checks to ensure the repository
        is in a clean state before performing any operations.
        """
        validator = PreflightGitValidation(
            repo_path=self.declarative_config_path,
            expected_branch="main",
            expected_remote_pattern="declarative-config",
            timeout=self.timeout,
            min_free_mb=100,
            strict=True,  # Raise immediately on first error
        )

        # Run all validation checks
        # Will raise GitStateError, GitAuthenticationError, or GitNetworkError
        # if any check fails
        validator.validate_all()

        logger.info(f"Pre-flight validation passed for {self.declarative_config_path}")

    def _parse_and_validate_fields(self, template_fields: list[dict[str, Any]]) -> list[TemplateField]:
        """Parse and validate template field specifications."""
        validated = []

        for field_spec in template_fields:
            if not isinstance(field_spec, dict):
                raise ValueError(f"Invalid field spec: {field_spec}")

            path = field_spec.get("path")
            value = field_spec.get("value")

            if not path or value is None:
                raise ValueError(f"Field spec missing 'path' or 'value': {field_spec}")

            # Create and validate TemplateField
            field = TemplateField(path=str(path), value=value)
            field.validate()

            # Security: validate against allowed path prefixes
            if not self._is_path_allowed(path):
                raise RuntimeError(f"Field path '{path}' is not in allowed prefixes")

            validated.append(field)

        return validated

    def _is_path_allowed(self, path: str) -> bool:
        """Check if a path is allowed for substitution."""
        for prefix in self.ALLOWED_PATH_PREFIXES:
            if path.startswith(prefix):
                return True
        return False

    def _read_manifest(self, manifest_path: Path) -> Any:
        """Read and parse YAML manifest."""
        with open(manifest_path, "r") as f:
            return yaml.safe_load(f)

    def _write_manifest(self, manifest_path: Path, data: Any) -> None:
        """Write data to YAML manifest using atomic write operation."""
        # Use atomic_write for safe file operations with temp file + atomic rename
        yaml_content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        atomic_write(manifest_path, yaml_content)

    def _apply_substitutions(self, manifest: Any, fields: list[TemplateField]) -> Any:
        """Apply templated field substitutions to manifest."""
        import copy

        # Work on a copy to avoid modifying the original
        modified = copy.deepcopy(manifest)

        for field in fields:
            self._apply_field_substitution(modified, field.path, field.value)

        return modified

    def _apply_field_substitution(self, data: Any, path: str, value: Any) -> None:
        """Apply a single field substitution using JSON Pointer syntax."""
        # Parse JSON Pointer path (split by /, ignoring empty first element)
        parts = [p for p in path.split("/") if p]

        if not parts:
            raise ValueError(f"Invalid path: {path}")

        # Navigate to the parent object
        current = data
        for part in parts[:-1]:
            # Handle array indices (numeric parts)
            if part.isdigit():
                if not isinstance(current, list):
                    raise ValueError(f"Path '{path}' expects list at '{part}'")
                current = current[int(part)]
            else:
                if not isinstance(current, dict):
                    raise ValueError(f"Path '{path}' expects dict at '{part}'")
                current = current.get(part)

                if current is None:
                    raise ValueError(f"Path '{path}' not found in manifest")

        # Set the final value
        final_key = parts[-1]
        if final_key.isdigit():
            # Array index (not typical for substitutions but handle it)
            idx = int(final_key)
            if not isinstance(current, list):
                raise ValueError(f"Path '{path}' expects list at final key")
            current[idx] = value
        else:
            if not isinstance(current, dict):
                raise ValueError(f"Path '{path}' expects dict at final key")
            current[final_key] = value

    def _detect_kubectl_mutation_risk(self, template_fields: list[dict[str, Any]]) -> bool:
        """Detect if template fields suggest kubectl mutation bypass."""
        # Check if fields include namespace, kind, or metadata.name changes
        risky_paths = ["/metadata/name", "/metadata/namespace", "/kind", "/apiVersion"]

        for field in template_fields:
            path = field.get("path", "")
            for risky in risky_paths:
                if path.startswith(risky):
                    return True

        return False

    def _diff_manifests(self, original: Any, modified: Any) -> str:
        """Generate a simple diff between original and modified manifests."""
        # This is a simplified diff - in production, use a proper diff library
        import json

        try:
            orig_str = json.dumps(original, sort_keys=True, default=str)
            mod_str = json.dumps(modified, sort_keys=True, default=str)

            if orig_str == mod_str:
                return "No changes detected"

            # Simple line-by-line comparison
            orig_lines = orig_str.split("\n")
            mod_lines = mod_str.split("\n")

            diff_lines = []
            for i, (orig, mod) in enumerate(zip(orig_lines, mod_lines)):
                if orig != mod:
                    diff_lines.append(f"Line {i}: '{orig}' → '{mod}'")

            return "\n".join(diff_lines[:10])  # Limit to first 10 differences
        except Exception:
            return "Diff generation failed"

    def _commit_changes(
        self,
        manifest_path: str,
        fields: list[TemplateField],
        project_cfg: dict[str, Any],
    ) -> GitOperationResult:
        """Commit changes with standard git identity."""
        try:
            # Configure git identity
            subprocess.run(
                ["git", "-C", str(self.declarative_config_path), "config", "user.email", self.git_email],
                check=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "-C", str(self.declarative_config_path), "config", "user.name", self.git_name],
                check=True,
                timeout=10,
            )

            # Check if there are actual changes
            result = subprocess.run(
                ["git", "-C", str(self.declarative_config_path), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if not result.stdout.strip():
                raise GitStateError("No changes to commit")

            # Build commit message
            commit_msg = self._build_commit_message(manifest_path, fields, project_cfg)

            # Stage and commit
            subprocess.run(
                ["git", "-C", str(self.declarative_config_path), "add", manifest_path],
                check=True,
                timeout=10,
            )

            result = subprocess.run(
                ["git", "-C", str(self.declarative_config_path), "commit", "-m", commit_msg],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                error_output = result.stderr.strip().lower()
                # Check for authentication failures
                if any(pattern in error_output for pattern in ["authentication", "permission denied", "credentials", "auth"]):
                    raise GitAuthenticationError(f"Git authentication failed during commit: {result.stderr.strip()}")

                # Check for merge conflicts in error message
                if "merge conflict" in error_output or "fix conflicts" in error_output:
                    # Detect actual conflicting files
                    conflict_files = detect_merge_conflicts(self.declarative_config_path, timeout=5)
                    raise GitConflictError(
                        f"Merge conflict detected during commit: {result.stderr.strip()}",
                        conflict_files=conflict_files,
                        conflict_type="merge",
                        details={"operation": "commit"}
                    )
                raise GitError(f"git commit failed: {result.stderr.strip()}")

            # After successful commit, still check for lingering conflict state
            # This catches cases where commit succeeded but left conflicts behind
            try:
                conflict_files = detect_merge_conflicts(self.declarative_config_path, timeout=5)
                if conflict_files:
                    raise GitConflictError(
                        "Merge conflicts detected after commit - repository is in conflicted state",
                        conflict_files=conflict_files,
                        conflict_type="merge",
                        details={"operation": "post_commit_check"}
                    )
            except (GitStateError, GitNetworkError) as e:
                # Don't fail commit for detection errors, just log
                logger.warning(f"Could not check for conflicts after commit: {e}")

            # Extract commit SHA
            result = subprocess.run(
                ["git", "-C", str(self.declarative_config_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )

            commit_sha = result.stdout.strip()
            if not commit_sha:
                raise GitStateError("Git commit succeeded but returned no commit SHA")

            return GitOperationResult(
                commit_sha=commit_sha,
                branch=self.TARGET_BRANCH,
                manifest_path=manifest_path,
                status="success",
            )

        except subprocess.TimeoutExpired:
            raise GitNetworkError("Git operation timed out during commit")
        except FileNotFoundError:
            raise GitError("Git command not found - ensure git is installed")

    def _build_commit_message(
        self,
        manifest_path: str,
        fields: list[TemplateField],
        project_cfg: dict[str, Any],
    ) -> str:
        """Build standardized commit message."""
        project_slug = project_cfg.get("project_slug", "unknown")
        cluster = project_cfg.get("cluster", "unknown")

        lines = [
            f"feat({project_slug}): update {manifest_path}",
            "",
            f"GitOps-managed update for {project_slug} on {cluster}",
            "",
            "Template field substitutions:",
        ]

        for field in fields:
            lines.append(f"  - {field.path}: {field.value}")

        lines.append("")
        lines.append("Co-Authored-By: Claude <noreply@anthropic.com>")

        return "\n".join(lines)

    @retry_with_exponential_backoff(
        max_retries=3,
        base_delay=1.0,
        max_delay=60.0,
        jitter_factor=0.25,
        log_retries=True
    )
    def _push_changes(
        self,
        manifest_path: str | None = None,
        commit_sha: str | None = None,
    ) -> GitOperationResult:
        """Push changes to origin main with retry logic for network failures."""
        # Push to origin
        result = subprocess.run(
            ["git", "-C", str(self.declarative_config_path), "push", "origin", self.TARGET_BRANCH],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip().lower()
            stdout_msg = result.stdout.strip().lower()

            # Detect authentication failures
            if any(pattern in error_msg + stdout_msg for pattern in [
                "authentication", "permission denied", "credentials",
                "auth", "could not read", "fatal"
            ]):
                raise GitAuthenticationError(f"Git authentication failed during push: {result.stderr.strip()}")

            # Detect network failures (these will trigger retry)
            if any(pattern in error_msg + stdout_msg for pattern in [
                "connection", "network", "timeout", "unreachable", "dns", "host"
            ]):
                raise GitNetworkError(f"Network failure during git push: {result.stderr.strip()}")

            # Detect common push failures
            if "rejected" in error_msg or "rejected" in stdout_msg:
                if "non-fast-forward" in error_msg or "non-fast-forward" in stdout_msg:
                    raise GitConflictError(
                        f"Non-fast-forward push: {result.stderr.strip()} - remote has new commits, pull required",
                        conflict_files=[],
                        conflict_type="push_rejection",
                        details={"reason": "non_fast_forward", "hint": "pull remote changes first"}
                    )
                else:
                    raise GitConflictError(
                        f"Push rejected: {result.stderr.strip()} - may need to pull remote changes first",
                        conflict_files=[],
                        conflict_type="push_rejection",
                        details={"reason": "unknown"}
                    )
            elif "merge conflict" in error_msg or "merge conflict" in stdout_msg:
                # Detect actual conflicting files after push failure
                conflict_files = detect_merge_conflicts(self.declarative_config_path, timeout=5)
                raise GitConflictError(
                    f"Merge conflict detected: {result.stderr.strip()}",
                    conflict_files=conflict_files,
                    conflict_type="merge",
                    details={"operation": "push"}
                )
            else:
                raise GitError(f"git push failed: {result.stderr.strip()}")

        return GitOperationResult(
            commit_sha=commit_sha,
            branch=self.TARGET_BRANCH,
            manifest_path=manifest_path,
            status="success",
        )

    async def rollback(self, manifest_path: str, commit_sha: str) -> GitOperationResult:
        """
        Rollback a commit by atomically restoring its parent manifest.

        Args:
            manifest_path: Path to manifest file
            commit_sha: Commit SHA to revert

        Returns:
            GitOperationResult with rollback information
        """
        logger.info(f"Rolling back commit {commit_sha} for {manifest_path}")

        manifest_file = self.declarative_config_path / manifest_path
        original_content: str | None = None
        original_exists = manifest_file.exists()

        def restore_original_manifest() -> None:
            """Restore the pre-rollback worktree content without a direct write."""
            if not original_exists or original_content is None:
                logger.warning(
                    "Rollback atomic restore skipped for %s because the original "
                    "manifest was not present",
                    manifest_file,
                )
                return

            logger.info(
                "Rollback atomic restore: restoring %s after failed rollback",
                manifest_file,
            )
            atomic_write(manifest_file, original_content)

        revert_committed = False

        try:
            if original_exists:
                original_content = manifest_file.read_text()

            # Read the parent version without allowing git to mutate the
            # worktree.  The generated GitOps commit stages only this manifest,
            # so restoring this path is the complete rollback payload.
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.declarative_config_path),
                    "show",
                    f"{commit_sha}^:{manifest_path}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            if result.returncode != 0:
                return self._operation_result(
                    manifest_path,
                    "failed",
                    commit_sha=commit_sha,
                    error=f"git revert failed while reading parent: {result.stderr}",
                )

            logger.info(
                "Rollback atomic write: publishing parent of %s to %s",
                commit_sha,
                manifest_file,
            )
            atomic_write(manifest_file, result.stdout)

            # Stage only the atomically restored manifest.  This keeps the
            # index operation separate from the file publication and ensures a
            # failed commit can restore both worktree and index state.
            result = subprocess.run(
                ["git", "-C", str(self.declarative_config_path), "add", "--", manifest_path],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                try:
                    restore_original_manifest()
                except Exception as restore_error:
                    logger.error(
                        "Rollback atomic restore failed for %s: %s",
                        manifest_file,
                        restore_error,
                    )
                return self._operation_result(
                    manifest_path,
                    "failed",
                    commit_sha=commit_sha,
                    error=f"Rollback staging failed: {result.stderr}",
                )

            # Commit the revert
            result = subprocess.run(
                ["git", "-C", str(self.declarative_config_path), "commit", "-m", f"Revert {commit_sha}"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                # The staged rollback has not been committed.  Unstage it and
                # restore the original worktree content atomically so a
                # partially completed rollback cannot leave a truncated file.
                try:
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            str(self.declarative_config_path),
                            "reset",
                            "HEAD",
                            "--",
                            manifest_path,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    restore_original_manifest()
                except Exception as restore_error:
                    logger.error(
                        "Rollback atomic restore failed for %s: %s",
                        manifest_file,
                        restore_error,
                    )
                return self._operation_result(
                    manifest_path,
                    "failed",
                    commit_sha=commit_sha,
                    error=f"Revert commit failed: {result.stderr}",
                )

            revert_committed = True

            # Push the revert
            self._push_changes(manifest_path=manifest_path, commit_sha=commit_sha)

            return self._operation_result(
                manifest_path,
                "success",
                commit_sha=commit_sha,
                reverted_commit=commit_sha,
            )

        except Exception as e:
            return self._operation_result(
                manifest_path,
                "partial" if revert_committed else "failed",
                commit_sha=commit_sha,
                error=f"Rollback failed: {e}",
            )
