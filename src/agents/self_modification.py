"""
Self-Modification Agent for aide-de-camp.

Reads and writes artifacts (prompts, configs) to improve system behavior
based on user feedback.
"""

import time
import json
import subprocess
import threading
from logging import getLogger
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

from ..components.hot_reload import get_reload_manager
from ..components.library import get_library
from ..escalate.llm import get_zai_client, ModelClass
from ..freeze import ensure_unfrozen
from ..utils.atomic_write import atomic_write
from ..utils.git_retry import retry_on_transient_error, get_retry_tracker
from ..action.steps.gitops import GitOperationResult, GitOperationStatus


logger = getLogger(__name__)


# Git subprocess utilities

def _extract_commit_sha(stdout: str, command: str) -> str | None:
    """
    Extract commit SHA from git command output.

    Args:
        stdout: Command output to parse
        command: Git command that was run (for context)

    Returns:
        Commit SHA if found, None otherwise
    """
    if not stdout:
        return None

    stripped = stdout.strip()

    # For rev-parse commands, the entire output is the SHA
    if "rev-parse" in command:
        # Extract first word as SHA (handles short and long SHAs)
        parts = stripped.split()
        return parts[0] if parts else None

    # For commit commands, extract SHA from "commit <sha>" message
    if stripped.startswith("["):
        # e.g., "[main 8f3a2b1] Commit message"
        parts = stripped.split()
        for i, part in enumerate(parts):
            if part.startswith("[") and i + 1 < len(parts):
                # Next part after branch is usually the SHA
                return parts[i + 1]

    return None


def _execute_git_command_internal(
    args: List[str],
    cwd: Path,
    timeout: int,
    check: bool
) -> GitOperationResult:
    """
    Internal implementation of git command execution.

    This function contains the actual subprocess logic and is called
    by the retry wrapper.
    """
    cmd = ['git'] + args

    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout
    )

    # Convert subprocess result to GitOperationResult
    success = result.returncode == 0
    command_str = ' '.join(['git'] + args)
    commit_sha = _extract_commit_sha(result.stdout, command_str) if success else None

    return GitOperationResult(
        commit_sha=commit_sha,
        branch=None,  # Branch info added by caller if needed
        manifest_path=None,  # Manifest path added by caller if needed
        status=GitOperationStatus.SUCCESS if success else GitOperationStatus.FAILED,
        error=result.stderr if result.returncode != 0 else None,
        details={
            'stdout': result.stdout,
            'returncode': result.returncode,
            'command': command_str
        }
    )


@retry_on_transient_error(max_retries=3, backoff_factor=1.5, initial_delay=1.0)
def _run_git_command_with_retry(
    args: List[str],
    cwd: Path,
    timeout: int,
    check: bool
) -> GitOperationResult:
    """
    Run a git command with automatic retry on transient network failures.

    This function is wrapped with retry logic that handles:
    - Network timeouts
    - Connection errors
    - Temporary unavailability
    - DNS issues

    Non-transient errors (authentication, permission denied, etc.) are not retried.

    Args:
        args: Git command arguments (e.g., ['status', '--short'])
        cwd: Working directory
        timeout: Command timeout in seconds
        check: If True, raise exception on non-zero exit

    Returns:
        GitOperationResult with status, commit SHA, error details, and command output

    Raises:
        subprocess.TimeoutExpired: On command timeout (after retries)
        subprocess.CalledProcessError: On non-zero exit (if check=True)
        Exception: On other errors (after retries)
    """
    try:
        return _execute_git_command_internal(args, cwd, timeout, check)
    except subprocess.TimeoutExpired as e:
        # Re-raise as-is - the retry decorator will catch and retry
        raise
    except subprocess.CalledProcessError as e:
        # Re-raise as-is - the retry decorator will determine if it's transient
        raise
    except Exception as e:
        # Re-raise as-is - the retry decorator will determine if it's transient
        raise


def run_git_command(
    args: List[str],
    cwd: Optional[Path] = None,
    timeout: int = 10,
    check: bool = False,
    retry_on_failure: bool = True
) -> GitOperationResult:
    """
    Run a git command via subprocess and return structured output.

    Args:
        args: Git command arguments (e.g., ['status', '--short'])
        cwd: Working directory (defaults to aide-de-camp repo root)
        timeout: Command timeout in seconds (default: 10)
        check: If True, raise exception on non-zero exit (default: False)
        retry_on_failure: If True, retry on transient network failures (default: True)

    Returns:
        GitOperationResult with status, commit SHA, error details, and command output
    """
    if cwd is None:
        cwd = Path("/home/coding/aide-de-camp")

    retry_tracker = get_retry_tracker()
    command_str = f"git {' '.join(args)}"

    try:
        if retry_on_failure:
            # Use retry logic for network operations
            result = _run_git_command_with_retry(args, cwd, timeout, check)
            retry_tracker.record_attempt(command_str, 0, result.status == GitOperationStatus.SUCCESS)
            return result
        else:
            # Direct execution without retry
            result = _execute_git_command_internal(args, cwd, timeout, check)
            retry_tracker.record_attempt(command_str, 0, result.status == GitOperationStatus.SUCCESS)
            return result

    except subprocess.TimeoutExpired as e:
        retry_tracker.record_attempt(
            command_str, 0, False, f"Timeout: {e}"
        )
        return GitOperationResult(
            status=GitOperationStatus.FAILED,
            error=f"Command timed out: {e}",
            details={
                'stdout': e.stdout.decode() if e.stdout else "",
                'stderr': e.stderr.decode() if e.stderr else "Command timed out",
                'command': command_str,
                'timed_out': True
            }
        )
    except subprocess.CalledProcessError as e:
        retry_tracker.record_attempt(
            command_str, 0, False, f"Exit code {e.returncode}: {e.stderr}"
        )
        return GitOperationResult(
            status=GitOperationStatus.FAILED,
            error=e.stderr or f"Command failed with exit code {e.returncode}",
            details={
                'stdout': e.stdout,
                'returncode': e.returncode,
                'command': command_str
            }
        )
    except Exception as e:
        retry_tracker.record_attempt(
            command_str, 0, False, str(e)
        )
        return GitOperationResult(
            status=GitOperationStatus.FAILED,
            error=str(e),
            details={
                'command': command_str
            }
        )


def git_status(cwd: Optional[Path] = None, short: bool = True) -> GitOperationResult:
    """
    Run git status.

    Args:
        cwd: Working directory (defaults to aide-de-camp repo root)
        short: If True, use --short format (default: True)

    Returns:
        GitOperationResult with status output
    """
    args = ['status', '--short'] if short else ['status']
    return run_git_command(args, cwd=cwd)


def git_add(paths: List[str], cwd: Optional[Path] = None) -> GitOperationResult:
    """
    Stage files for commit.

    Args:
        paths: List of file paths to stage (relative to cwd)
        cwd: Working directory (defaults to aide-de-camp repo root)

    Returns:
        GitOperationResult with add output
    """
    args = ['add'] + paths
    return run_git_command(args, cwd=cwd)


def git_commit(message: str, paths: Optional[List[str]] = None, cwd: Optional[Path] = None) -> GitOperationResult:
    """
    Create a git commit.

    Args:
        message: Commit message
        paths: Optional list of specific paths to commit (default: all staged)
        cwd: Working directory (defaults to aide-de-camp repo root)

    Returns:
        GitOperationResult with commit output and commit SHA
    """
    args = ['commit', '-m', message]
    if paths is not None:
        args.extend(['--'] + paths)
    result = run_git_command(args, cwd=cwd)

    # Extract commit SHA if commit succeeded
    if result.status == GitOperationStatus.SUCCESS:
        # Get the commit SHA that was just created
        sha_result = git_rev_parse('HEAD', short=True, cwd=cwd)
        if sha_result.status == GitOperationStatus.SUCCESS and sha_result.commit_sha:
            result.commit_sha = sha_result.commit_sha

    return result


def git_show(ref: str, cwd: Optional[Path] = None) -> GitOperationResult:
    """
    Show git object content (e.g., 'HEAD:path/to/file').

    Args:
        ref: Git reference (e.g., 'HEAD:path/to/file')
        cwd: Working directory (defaults to aide-de-camp repo root)

    Returns:
        GitOperationResult with show output
    """
    return run_git_command(['show', ref], cwd=cwd)


def git_rev_parse(ref: str, short: bool = False, cwd: Optional[Path] = None) -> GitOperationResult:
    """
    Get git SHA for a reference.

    Args:
        ref: Git reference (e.g., 'HEAD')
        short: If True, return short SHA (default: False)
        cwd: Working directory (defaults to aide-de-camp repo root)

    Returns:
        GitOperationResult with SHA output and commit SHA populated
    """
    args = ['rev-parse']
    if short:
        args.append('--short')
    args.append(ref)
    return run_git_command(args, cwd=cwd)


def git_fetch(
    remote: str = "origin",
    branch: Optional[str] = None,
    cwd: Optional[Path] = None,
    timeout: int = 30
) -> GitOperationResult:
    """
    Fetch updates from a remote repository with automatic retry on network failures.

    Args:
        remote: Remote name (default: "origin")
        branch: Optional branch to fetch (if None, fetches all branches)
        cwd: Working directory (defaults to aide-de-camp repo root)
        timeout: Command timeout in seconds (default: 30)

    Returns:
        GitOperationResult with fetch output

    Example:
        result = git_fetch("origin", "main")
        if result.status == GitOperationStatus.SUCCESS:
            print("Fetch successful")
        else:
            print(f"Fetch failed: {result.error}")
    """
    args = ['fetch', remote]
    if branch:
        args.append(branch)

    logger.info(f"Fetching from {remote}" + (f" {branch}" if branch else ""))
    return run_git_command(args, cwd=cwd, timeout=timeout)


def git_push(
    remote: str = "origin",
    branch: str = "main",
    cwd: Optional[Path] = None,
    timeout: int = 30,
    force: bool = False
) -> GitOperationResult:
    """
    Push changes to a remote repository with automatic retry on network failures.

    Args:
        remote: Remote name (default: "origin")
        branch: Branch to push (default: "main")
        cwd: Working directory (defaults to aide-de-camp repo root)
        timeout: Command timeout in seconds (default: 30)
        force: If True, use force push (default: False, WARNING: use with caution)

    Returns:
        GitOperationResult with push output and branch populated

    Example:
        result = git_push("origin", "main")
        if result.status == GitOperationStatus.SUCCESS:
            print("Push successful")
        else:
            print(f"Push failed: {result.error}")
    """
    args = ['push', remote, branch]
    if force:
        args.append('--force')
        logger.warning(f"Force push requested to {remote}/{branch}")

    logger.info(f"Pushing to {remote}/{branch}")
    result = run_git_command(args, cwd=cwd, timeout=timeout)

    # Populate branch field on success
    if result.status == GitOperationStatus.SUCCESS:
        result.branch = branch

    return result


def git_pull(
    remote: str = "origin",
    branch: Optional[str] = None,
    cwd: Optional[Path] = None,
    timeout: int = 30
) -> GitOperationResult:
    """
    Pull changes from a remote repository with automatic retry on network failures.

    Args:
        remote: Remote name (default: "origin")
        branch: Optional branch to pull (if None, uses current branch)
        cwd: Working directory (defaults to aide-de-camp repo root)
        timeout: Command timeout in seconds (default: 30)

    Returns:
        GitOperationResult with pull output

    Example:
        result = git_pull("origin", "main")
        if result.status == GitOperationStatus.SUCCESS:
            print("Pull successful")
        else:
            print(f"Pull failed: {result.error}")
    """
    args = ['pull', remote]
    if branch:
        args.append(branch)

    logger.info(f"Pulling from {remote}" + (f" {branch}" if branch else ""))
    return run_git_command(args, cwd=cwd, timeout=timeout)


def generate_self_mod_commit_message(file_path: Path, cwd: Optional[Path] = None) -> str:
    """
    Generate a standardized commit message for self-modification writes.

    Creates a commit message with the format:
    'auto: self-mod write to <path> [<commit-short-sha>]'
    where <commit-short-sha> is the short SHA of the current HEAD (the commit
    we are building on top of).

    Args:
        file_path: Path to the file being modified (relative or absolute)
        cwd: Working directory (defaults to aide-de-camp repo root)

    Returns:
        Commit message string with path and optional previous commit SHA
    """
    if cwd is None:
        cwd = Path("/home/coding/aide-de-camp")

    # Get relative path from repo root
    try:
        rel_path = Path(file_path).relative_to(cwd)
    except ValueError:
        # If file_path is already relative or outside repo, use as-is
        rel_path = Path(file_path)

    # Get the short SHA of the current HEAD (previous commit)
    # This will be included in the commit message to show what we're building on
    head_result = git_rev_parse('HEAD', short=True, cwd=cwd)

    if head_result.status == GitOperationStatus.SUCCESS and head_result.commit_sha:
        prev_commit_sha = head_result.commit_sha
        return f"auto: self-mod write to {rel_path} [{prev_commit_sha}]"
    else:
        # No previous commit (e.g., initial commit or empty repo)
        return f"auto: self-mod write to {rel_path}"

# Prompt paths read per-invocation so edits take effect without a server restart
# (hot-reload), matching the pattern in src/synthesize/strand.py and
# src/intent/router.py.
SELF_MOD_PARSE_PROMPT_PATH = Path("/home/coding/aide-de-camp/prompts/self_mod_parse.md")
SELF_MOD_GENERATE_PROMPT_PATH = Path("/home/coding/aide-de-camp/prompts/self_mod_generate.md")

# Fallbacks used only if a prompt file cannot be read at runtime.
_PARSE_PROMPT_FALLBACK = (
    "You classify a user instruction to the artifact it targets. "
    'Return ONLY JSON: {"artifact_type": "prompt|config|component", '
    '"artifact_name": "<name>", "reasoning": "..."}.'
)
_GENERATE_PROMPT_FALLBACK = (
    "You apply a user instruction to an artifact. Return ONLY JSON: "
    '{"updated_content": "<full updated text>", "change_summary": "one sentence"}.'
)


class ArtifactType(Enum):
    """Types of artifacts that can be modified."""
    PROMPT = "prompt"
    CONFIG = "config"
    COMPONENT = "component"


@dataclass
class ArtifactDiff:
    """A diff showing changes to an artifact."""
    artifact_name: str
    artifact_type: ArtifactType
    before: str
    after: str
    change_summary: str
    confidence: float


@dataclass
class ModificationRequest:
    """A user request to modify system behavior."""
    instruction: str
    artifact_name: Optional[str]
    artifact_type: Optional[ArtifactType]
    context: Dict[str, Any]


class SelfModificationAgent:
    """
    Agent that modifies system artifacts based on user feedback.

    Workflow:
    1. Receive user instruction
    2. Identify target artifact
    3. Read current artifact content
    4. Generate update
    5. Surface diff to user
    6. On approval: write artifact
    7. On rejection: discard
    """

    def __init__(
        self,
        parse_prompt_path: Optional[Path] = None,
        generate_prompt_path: Optional[Path] = None,
    ):
        self.reload_mgr = get_reload_manager()
        self.component_library = get_library()
        self._pending_diffs: List[ArtifactDiff] = []
        self._pending_lock = threading.RLock()
        self._artifact_write_lock = threading.RLock()
        self.parse_prompt_path = parse_prompt_path or SELF_MOD_PARSE_PROMPT_PATH
        self.generate_prompt_path = generate_prompt_path or SELF_MOD_GENERATE_PROMPT_PATH
        self._zai_client = None

    async def _get_zai_client(self):
        """Get or create the ZAI proxy client (lazy singleton)."""
        if self._zai_client is None:
            self._zai_client = get_zai_client()
        return self._zai_client

    def _load_prompt(self, path: Path, fallback: str) -> str:
        """Load a self-modification prompt from disk (hot-reload, per call)."""
        try:
            return path.read_text()
        except Exception as e:
            logger.error(f"Failed to load prompt {path}: {e}")
            return fallback

    def _available_artifacts(self) -> List[Dict[str, str]]:
        """Build the list of registered artifacts for the parser prompt."""
        artifacts: List[Dict[str, str]] = []
        for name, path_str in self.reload_mgr.list_artifacts().items():
            suffix = Path(path_str).suffix.lower()
            type_str = "config" if suffix in (".yaml", ".yml") else "prompt"
            artifacts.append({"name": name, "type": type_str})
        return artifacts

    @staticmethod
    def _strip_fences(raw: str) -> str:
        """Strip ```json ... ``` markdown fences from a GLM response."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        return raw

    async def process_instruction(self, instruction: str) -> ArtifactDiff:
        """
        Process a user instruction for system modification.

        Args:
            instruction: Natural language instruction

        Returns:
            The proposed diff for user approval
        """
        # Parse the instruction to identify target (LLM call)
        request = await self._parse_instruction(instruction)

        # Get current content
        current_content = self._get_artifact_content(request)

        # Generate update (LLM call)
        updated_content, change_summary = await self._generate_update(
            request,
            current_content
        )

        diff = ArtifactDiff(
            artifact_name=request.artifact_name or "unknown",
            artifact_type=request.artifact_type or ArtifactType.PROMPT,
            before=current_content,
            after=updated_content,
            change_summary=change_summary,
            confidence=self._estimate_confidence(request, change_summary)
        )

        with self._pending_lock:
            self._pending_diffs.append(diff)
        return diff

    async def _parse_instruction(self, instruction: str) -> ModificationRequest:
        """
        Parse an instruction to identify the target artifact via an LLM call.

        The LLM classifies the free-text instruction against the registered
        artifacts and returns the artifact_type + artifact_name. Falls back to
        the router prompt if the call or its response cannot be parsed.
        """
        system_prompt = self._load_prompt(self.parse_prompt_path, _PARSE_PROMPT_FALLBACK)
        user_message = (
            "## Registered Artifacts\n"
            + json.dumps(self._available_artifacts(), indent=2)
            + f"\n\n## User Instruction\n{instruction}\n"
        )

        try:
            client = await self._get_zai_client()
            response = await client.call_simple(
                system_prompt=system_prompt,
                user_message=user_message,
                model=ModelClass.HAIKU.value,  # cheap, fast classification
                max_tokens=512,
                temperature=0.0,  # deterministic classification
            )
            data = json.loads(self._strip_fences(response))

            type_str = data.get("artifact_type", "prompt")
            name = data.get("artifact_name")

            try:
                artifact_type = ArtifactType(type_str)
            except ValueError:
                artifact_type = ArtifactType.PROMPT

            # Validate the name is actually registered; fall back to a known
            # artifact (preferring the router prompt) so we never target a
            # non-existent artifact.
            registered = list(self.reload_mgr.list_artifacts().keys())
            registered_set = set(registered)
            if artifact_type != ArtifactType.COMPONENT and (
                not name or name not in registered_set
            ):
                if "router" in registered_set:
                    name = "router"
                elif registered:
                    name = registered[0]
                else:
                    name = "unknown"
                artifact_type = ArtifactType.PROMPT

            return ModificationRequest(
                instruction=instruction,
                artifact_name=name,
                artifact_type=artifact_type,
                context={
                    "raw_instruction": instruction,
                    "reasoning": data.get("reasoning", ""),
                },
            )
        except Exception as e:
            logger.warning(
                f"_parse_instruction LLM parse failed, defaulting to router prompt: {e}"
            )
            return ModificationRequest(
                instruction=instruction,
                artifact_name="router",
                artifact_type=ArtifactType.PROMPT,
                context={"raw_instruction": instruction, "fallback": True},
            )

    def _get_artifact_content(self, request: ModificationRequest) -> str:
        """Get current content of the target artifact."""
        if request.artifact_type == ArtifactType.PROMPT:
            if request.artifact_name in self.reload_mgr.list_artifacts():
                return self.reload_mgr.get_prompt(request.artifact_name)
        elif request.artifact_type == ArtifactType.CONFIG:
            if request.artifact_name in self.reload_mgr.list_artifacts():
                # For configs, return YAML as string for diff
                artifact = self.reload_mgr._artifacts.get(request.artifact_name)
                if artifact:
                    return artifact.content

        return "# Artifact not found or not loaded"

    async def _generate_update(
        self,
        request: ModificationRequest,
        current_content: str
    ) -> Tuple[str, str]:
        """
        Generate updated artifact content via an LLM call.

        Sends the current content + instruction to the LLM and returns the full
        updated content plus a change summary. On failure, returns the content
        unchanged with an honest summary rather than fabricating a change.
        """
        system_prompt = self._load_prompt(
            self.generate_prompt_path, _GENERATE_PROMPT_FALLBACK
        )
        artifact_type = request.artifact_type.value if request.artifact_type else "prompt"
        user_message = (
            f"## Instruction\n{request.instruction}\n\n"
            f"## Artifact Type\n{artifact_type}\n\n"
            f"## Current Content\n```\n{current_content}\n```\n"
        )

        try:
            client = await self._get_zai_client()
            response = await client.call_simple(
                system_prompt=system_prompt,
                user_message=user_message,
                model=ModelClass.SONNET.value,  # higher quality for rewriting
                max_tokens=4096,
                temperature=0.2,
            )
            data = json.loads(self._strip_fences(response))

            updated = data.get("updated_content")
            summary = data.get("change_summary", "")
            if not isinstance(updated, str) or not updated.strip():
                logger.warning(
                    "_generate_update returned no updated_content; leaving artifact unchanged"
                )
                return current_content, summary or "No update generated"
            return updated, summary or "Updated artifact"
        except Exception as e:
            logger.error(f"_generate_update LLM call failed: {e}")
            return current_content, f"Update generation failed: {e}"

    def _estimate_confidence(
        self,
        request: ModificationRequest,
        change_summary: str
    ) -> float:
        """
        Estimate confidence in the proposed change.

        Higher confidence for:
        - Clear, specific instructions
        - Additive changes (vs destructive)
        - Low-risk artifacts (prompts vs registry)
        """
        confidence = 0.5  # Base confidence

        instruction_lower = request.instruction.lower()

        # Specific instructions increase confidence
        if any(word in instruction_lower for word in ["add", "include", "always"]):
            confidence += 0.2

        # Destructive keywords decrease confidence
        if any(word in instruction_lower for word in ["remove", "delete", "change entirely"]):
            confidence -= 0.2

        # Config changes are riskier than prompt changes
        if request.artifact_type == ArtifactType.CONFIG:
            confidence -= 0.1

        # Clamp to valid range
        return max(0.0, min(1.0, confidence))

    def apply_diff(self, diff: ArtifactDiff) -> bool:
        """
        Apply a diff by writing the updated artifact.

        Args:
            diff: The diff to apply

        Returns:
            True if successful, False otherwise
        """
        try:
            # Check freeze protection before writing
            ensure_unfrozen()

            with self._artifact_write_lock:
                if diff.artifact_type in (ArtifactType.PROMPT, ArtifactType.CONFIG):
                    artifact = self.reload_mgr._artifacts.get(diff.artifact_name)
                    if not artifact or artifact.path.read_text() != diff.before:
                        # Expected-version check: do not overwrite an edit made
                        # after this proposal was generated.
                        logger.warning("Refusing stale self-modification diff for %s", diff.artifact_name)
                        return False
                if diff.artifact_type == ArtifactType.PROMPT:
                    return self._write_prompt(diff)
                elif diff.artifact_type == ArtifactType.CONFIG:
                    return self._write_config(diff)
                elif diff.artifact_type == ArtifactType.COMPONENT:
                    return self._write_component(diff)
                return False
        except RuntimeError as e:
            # Clear error for freeze protection
            print(f"Cannot apply diff: {e}")
            return False
        except Exception as e:
            print(f"Failed to apply diff: {e}")
            return False

    def _commit_artifact_write(self, artifact_path: Path, artifact_type: ArtifactType) -> GitOperationResult:
        """
        Create a git commit for an artifact write.

        Creates a commit with a machine-generated message following the convention:
        'auto: self-mod write to <path> [<commit-short-sha>]'

        Args:
            artifact_path: Path to the artifact that was written
            artifact_type: Type of artifact (prompt/config)

        Returns:
            GitOperationResult with commit information
        """
        try:
            # Get the repo root directory
            repo_root = Path("/home/coding/aide-de-camp")

            # Get relative path from repo root
            rel_path = artifact_path.relative_to(repo_root)

            # Verify the file exists before trying to stage it
            if not artifact_path.exists():
                logger.error(f"Cannot commit artifact write: file does not exist at {artifact_path}")
                return GitOperationResult.create_failure(
                    error=f"File does not exist at {artifact_path}",
                )

            # Stage the file for commit using git operation
            add_result = git_add([str(rel_path)], cwd=repo_root)

            if add_result.status != GitOperationStatus.SUCCESS:
                logger.error(f"git add failed: {add_result.error}")
                return GitOperationResult.create_failure(
                    error=f"git add failed: {add_result.error}",
                )

            # Generate standardized commit message with previous commit SHA
            commit_msg = generate_self_mod_commit_message(rel_path, cwd=repo_root)

            # Create the commit using git operation
            commit_result = git_commit(commit_msg, cwd=repo_root)

            if commit_result.status != GitOperationStatus.SUCCESS:
                logger.warning(f"Failed to create git commit: {commit_result.error}")
                return GitOperationResult.create_failure(
                    error=f"git commit failed: {commit_result.error}",
                )

            # Get the short SHA of the commit just created
            sha_result = git_rev_parse('HEAD', short=True, cwd=repo_root)

            if sha_result.status == GitOperationStatus.SUCCESS and sha_result.commit_sha:
                short_sha = sha_result.commit_sha
                logger.info(f"Created git commit {short_sha} for {artifact_type.value} write to {rel_path}")

                return GitOperationResult.create_success(
                    commit_sha=short_sha,
                    branch="main",
                    manifest_path=str(rel_path),
                )
            else:
                # Commit succeeded but couldn't get SHA - still a success
                logger.warning(f"Commit succeeded but couldn't extract SHA: {sha_result.error}")
                return GitOperationResult.create_success(
                    commit_sha="unknown",
                    branch="main",
                    manifest_path=str(rel_path),
                )

        except Exception as e:
            logger.error(f"Failed to create git commit for artifact write: {e}")
            return GitOperationResult.create_failure(
                error=f"Exception during commit: {e}",
            )

    def _write_prompt(self, diff: ArtifactDiff) -> bool:
        """Write updated prompt file."""
        artifact = self.reload_mgr._artifacts.get(diff.artifact_name)
        if not artifact:
            return False

        atomic_write(artifact.path, diff.after)

        # Force reload to pick up changes
        self.reload_mgr.force_reload(diff.artifact_name)

        # Create git commit for the prompt write
        self._commit_artifact_write(artifact.path, diff.artifact_type)

        return True

    def _write_config(self, diff: ArtifactDiff) -> bool:
        """Write updated config file."""
        artifact = self.reload_mgr._artifacts.get(diff.artifact_name)
        if not artifact:
            return False

        atomic_write(artifact.path, diff.after)

        # Force reload
        self.reload_mgr.force_reload(diff.artifact_name)

        # Create git commit for the config write
        self._commit_artifact_write(artifact.path, diff.artifact_type)

        return True

    def _write_component(self, diff: ArtifactDiff) -> bool:
        """Write updated component to library."""
        # For components, we need to identify the component
        # This is a placeholder - in production, parse component_id from instruction
        if not diff.artifact_name.startswith("comp-"):
            return False

        component = self.component_library.get_component(diff.artifact_name)
        if not component:
            return False

        self.component_library.update_component(
            component.id,
            diff.after,
            diff.change_summary
        )
        return True

    def reject_diff(self, diff: ArtifactDiff):
        """Discard a diff without applying it."""
        with self._pending_lock:
            try:
                self._pending_diffs.remove(diff)
            except ValueError:
                pass

    def rollback(self, artifact_name: str, artifact_type: ArtifactType) -> GitOperationResult:
        """
        Rollback an artifact to its previous version.

        For prompts/configs: read from git history
        For components: use component version history

        Returns:
            GitOperationResult with rollback information
        """
        with self._artifact_write_lock:
            if artifact_type == ArtifactType.COMPONENT:
                success = self._rollback_component(artifact_name)
                return GitOperationResult.create_success(
                    commit_sha="component",
                    branch="main",
                    manifest_path=f"component/{artifact_name}",
                ) if success else GitOperationResult.create_failure(
                    error=f"Component rollback failed for {artifact_name}",
                )

            # For prompts/configs, use git to get previous version
            try:
                artifact = self.reload_mgr._artifacts.get(artifact_name)
                if not artifact:
                    return GitOperationResult.create_failure(
                        error=f"Artifact not found: {artifact_name}",
                    )

                # Get previous version from git using git_show
                # Reference format: HEAD:path/to/file
                ref = f"HEAD:{artifact.path.name}"
                result = git_show(ref, cwd=artifact.path.parent)

                if result.status == GitOperationStatus.SUCCESS:
                    # Extract file content from details
                    file_content = result.details.get('stdout', '')

                    if not file_content:
                        return GitOperationResult.create_failure(
                            error=f"git show succeeded but returned no content for {artifact_name}",
                        )

                    # P1 compare-and-swap boundary: the write lock prevents a
                    # concurrent apply/rollback from replacing this artifact.
                    logger.info(
                        "Rollback atomic write: restoring artifact %s at %s",
                        artifact_name,
                        artifact.path,
                    )
                    atomic_write(artifact.path, file_content)
                    self.reload_mgr.force_reload(artifact_name)
                    logger.info(
                        "Rollback atomic write completed for artifact %s",
                        artifact_name,
                    )

                    return GitOperationResult.create_success(
                        commit_sha="rollback",
                        branch="main",
                        manifest_path=str(artifact.path),
                    )
                else:
                    return GitOperationResult.create_failure(
                        error=f"git show failed: {result.error}",
                    )

            except Exception as e:
                logger.exception("Rollback failed for artifact %s: %s", artifact_name, e)
                return GitOperationResult.create_failure(
                    error=f"Rollback failed with exception: {e}",
                )

    def _rollback_component(self, component_id: str) -> bool:
        """Rollback a component using its version history."""
        component = self.component_library.get_component(component_id)
        if not component or component.version <= 1:
            return False

        target_version = component.version - 1
        self.component_library.rollback_component(component_id, target_version)
        return True

    def list_pending_diffs(self) -> List[ArtifactDiff]:
        """Get all pending diffs awaiting approval."""
        with self._pending_lock:
            return list(self._pending_diffs)

    def clear_pending_diffs(self):
        """Clear all pending diffs."""
        with self._pending_lock:
            # Swap to a fresh generation so proposals created concurrently are
            # not removed by a bulk clear.
            self._pending_diffs = []


# Singleton instance
_agent: Optional[SelfModificationAgent] = None


def get_self_modification_agent() -> SelfModificationAgent:
    """Get or create the self-modification agent singleton."""
    global _agent
    if _agent is None:
        _agent = SelfModificationAgent()
    return _agent
