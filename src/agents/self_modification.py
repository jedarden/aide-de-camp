"""
Self-Modification Agent for aide-de-camp.

Reads and writes artifacts (prompts, configs) to improve system behavior
based on user feedback.
"""

import time
import json
import subprocess
from logging import getLogger
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

from ..components.hot_reload import get_reload_manager
from ..components.library import get_library
from ..escalate.llm import get_zai_client, ModelClass


logger = getLogger(__name__)


# Git subprocess utilities

@dataclass
class GitResult:
    """Result of a git command execution."""
    success: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False


def run_git_command(
    args: List[str],
    cwd: Optional[Path] = None,
    timeout: int = 10,
    check: bool = False
) -> GitResult:
    """
    Run a git command via subprocess and return structured output.

    Args:
        args: Git command arguments (e.g., ['status', '--short'])
        cwd: Working directory (defaults to aide-de-camp repo root)
        timeout: Command timeout in seconds (default: 10)
        check: If True, raise exception on non-zero exit (default: False)

    Returns:
        GitResult with success status, stdout, stderr, returncode, and timeout flag
    """
    if cwd is None:
        cwd = Path("/home/coding/aide-de-camp")

    cmd = ['git'] + args

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout
        )
        return GitResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            timed_out=False
        )
    except subprocess.TimeoutExpired as e:
        return GitResult(
            success=False,
            stdout=e.stdout.decode() if e.stdout else "",
            stderr=e.stderr.decode() if e.stderr else "Command timed out",
            returncode=-1,
            timed_out=True
        )
    except subprocess.CalledProcessError as e:
        return GitResult(
            success=False,
            stdout=e.stdout,
            stderr=e.stderr,
            returncode=e.returncode,
            timed_out=False
        )
    except Exception as e:
        return GitResult(
            success=False,
            stdout="",
            stderr=str(e),
            returncode=-1,
            timed_out=False
        )


def git_status(cwd: Optional[Path] = None, short: bool = True) -> GitResult:
    """
    Run git status.

    Args:
        cwd: Working directory (defaults to aide-de-camp repo root)
        short: If True, use --short format (default: True)

    Returns:
        GitResult with status output
    """
    args = ['status', '--short'] if short else ['status']
    return run_git_command(args, cwd=cwd)


def git_add(paths: List[str], cwd: Optional[Path] = None) -> GitResult:
    """
    Stage files for commit.

    Args:
        paths: List of file paths to stage (relative to cwd)
        cwd: Working directory (defaults to aide-de-camp repo root)

    Returns:
        GitResult with add output
    """
    args = ['add'] + paths
    return run_git_command(args, cwd=cwd)


def git_commit(message: str, paths: Optional[List[str]] = None, cwd: Optional[Path] = None) -> GitResult:
    """
    Create a git commit.

    Args:
        message: Commit message
        paths: Optional list of specific paths to commit (default: all staged)
        cwd: Working directory (defaults to aide-de-camp repo root)

    Returns:
        GitResult with commit output
    """
    args = ['commit', '-m', message]
    if paths is not None:
        args.extend(['--'] + paths)
    return run_git_command(args, cwd=cwd)


def git_show(ref: str, cwd: Optional[Path] = None) -> GitResult:
    """
    Show git object content (e.g., 'HEAD:path/to/file').

    Args:
        ref: Git reference (e.g., 'HEAD:path/to/file')
        cwd: Working directory (defaults to aide-de-camp repo root)

    Returns:
        GitResult with show output
    """
    return run_git_command(['show', ref], cwd=cwd)


def git_rev_parse(ref: str, short: bool = False, cwd: Optional[Path] = None) -> GitResult:
    """
    Get git SHA for a reference.

    Args:
        ref: Git reference (e.g., 'HEAD')
        short: If True, return short SHA (default: False)
        cwd: Working directory (defaults to aide-de-camp repo root)

    Returns:
        GitResult with SHA output
    """
    args = ['rev-parse']
    if short:
        args.append('--short')
    args.append(ref)
    return run_git_command(args, cwd=cwd)


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

    if head_result.success and head_result.stdout.strip():
        prev_commit_sha = head_result.stdout.strip()
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
            if diff.artifact_type == ArtifactType.PROMPT:
                return self._write_prompt(diff)
            elif diff.artifact_type == ArtifactType.CONFIG:
                return self._write_config(diff)
            elif diff.artifact_type == ArtifactType.COMPONENT:
                return self._write_component(diff)
            return False
        except Exception as e:
            print(f"Failed to apply diff: {e}")
            return False

    def _commit_artifact_write(self, artifact_path: Path, artifact_type: ArtifactType) -> None:
        """
        Create a git commit for an artifact write.

        Creates a commit with a machine-generated message following the convention:
        'auto: self-mod write to <path> [<commit-short-sha>]'

        Args:
            artifact_path: Path to the artifact that was written
            artifact_type: Type of artifact (prompt/config)
        """
        try:
            # Get the repo root directory
            repo_root = Path("/home/coding/aide-de-camp")

            # Get relative path from repo root
            rel_path = artifact_path.relative_to(repo_root)

            # Stage the file (use -A to handle files that may be in weird states)
            # This works for new files, modified files, and files that were deleted then recreated
            subprocess.run(
                ['git', 'add', '-A', str(rel_path)],
                cwd=repo_root,
                capture_output=True,
                check=False,
                timeout=10
            )

            # Generate standardized commit message with previous commit SHA
            commit_msg = generate_self_mod_commit_message(rel_path, cwd=repo_root)

            # Create the commit (file is now staged)
            # Only commit staged changes, ignoring other unstaged changes
            result = subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=10
            )

            # Only log if commit was successful
            if result.returncode == 0:
                # Get the short SHA of the commit just created
                sha_result = subprocess.run(
                    ['git', 'rev-parse', '--short', 'HEAD'],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10
                )

                short_sha = sha_result.stdout.strip()
                logger.info(f"Created git commit {short_sha} for {artifact_type.value} write to {rel_path}")
            else:
                logger.warning(f"Failed to create git commit: stdout={result.stdout}, stderr={result.stderr}, returncode={result.returncode}")

        except subprocess.TimeoutExpired:
            logger.error("Git command timed out")
        except Exception as e:
            logger.error(f"Failed to create git commit for artifact write: {e}")

    def _write_prompt(self, diff: ArtifactDiff) -> bool:
        """Write updated prompt file."""
        artifact = self.reload_mgr._artifacts.get(diff.artifact_name)
        if not artifact:
            return False

        with open(artifact.path, 'w') as f:
            f.write(diff.after)

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

        with open(artifact.path, 'w') as f:
            f.write(diff.after)

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
        if diff in self._pending_diffs:
            self._pending_diffs.remove(diff)

    def rollback(self, artifact_name: str, artifact_type: ArtifactType) -> bool:
        """
        Rollback an artifact to its previous version.

        For prompts/configs: read from git history
        For components: use component version history
        """
        if artifact_type == ArtifactType.COMPONENT:
            return self._rollback_component(artifact_name)

        # For prompts/configs, use git to get previous version
        import subprocess
        try:
            artifact = self.reload_mgr._artifacts.get(artifact_name)
            if not artifact:
                return False

            # Get previous version from git
            result = subprocess.run(
                ['git', 'show', f'HEAD:{artifact.path.name}'],
                capture_output=True,
                text=True,
                cwd=artifact.path.parent
            )

            if result.returncode == 0:
                with open(artifact.path, 'w') as f:
                    f.write(result.stdout)
                self.reload_mgr.force_reload(artifact_name)
                return True
        except Exception as e:
            print(f"Rollback failed: {e}")

        return False

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
        return self._pending_diffs.copy()

    def clear_pending_diffs(self):
        """Clear all pending diffs."""
        self._pending_diffs.clear()


# Singleton instance
_agent: Optional[SelfModificationAgent] = None


def get_self_modification_agent() -> SelfModificationAgent:
    """Get or create the self-modification agent singleton."""
    global _agent
    if _agent is None:
        _agent = SelfModificationAgent()
    return _agent
