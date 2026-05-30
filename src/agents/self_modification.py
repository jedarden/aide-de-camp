"""
Self-Modification Agent for aide-de-camp.

Reads and writes artifacts (prompts, configs) to improve system behavior
based on user feedback.
"""

import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

from ..components.hot_reload import get_reload_manager
from ..components.library import get_library


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

    def __init__(self):
        self.reload_mgr = get_reload_manager()
        self.component_library = get_library()
        self._pending_diffs: List[ArtifactDiff] = []

    def process_instruction(self, instruction: str) -> ArtifactDiff:
        """
        Process a user instruction for system modification.

        Args:
            instruction: Natural language instruction

        Returns:
            The proposed diff for user approval
        """
        # Parse the instruction to identify target
        request = self._parse_instruction(instruction)

        # Get current content
        current_content = self._get_artifact_content(request)

        # Generate update (this would be an LLM call in production)
        updated_content, change_summary = self._generate_update(
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

    def _parse_instruction(self, instruction: str) -> ModificationRequest:
        """
        Parse instruction to identify target artifact.

        In production, this is an LLM call. For now, use simple heuristics.
        """
        instruction_lower = instruction.lower()

        artifact_name = None
        artifact_type = None
        context = {}

        # Identify keywords
        if "prompt" in instruction_lower or "router" in instruction_lower:
            if "router" in instruction_lower:
                artifact_name = "router"
            elif "synthesize" in instruction_lower:
                artifact_name = "synthesize"
            elif "voice" in instruction_lower:
                artifact_name = "voice"
            elif "urgency" in instruction_lower:
                artifact_name = "urgency"
            artifact_type = ArtifactType.PROMPT

        elif "registry" in instruction_lower or "project" in instruction_lower:
            artifact_name = "registry"
            artifact_type = ArtifactType.CONFIG

        elif "monitoring" in instruction_lower:
            artifact_name = "monitoring"
            artifact_type = ArtifactType.CONFIG

        elif "component" in instruction_lower or "card" in instruction_lower:
            artifact_type = ArtifactType.COMPONENT

        # If no specific artifact identified, default to router prompt
        if artifact_name is None and artifact_type is None:
            artifact_name = "router"
            artifact_type = ArtifactType.PROMPT

        context["raw_instruction"] = instruction

        return ModificationRequest(
            instruction=instruction,
            artifact_name=artifact_name,
            artifact_type=artifact_type,
            context=context
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

    def _generate_update(
        self,
        request: ModificationRequest,
        current_content: str
    ) -> Tuple[str, str]:
        """
        Generate updated artifact content.

        In production, this is an LLM call that:
        1. Understands the instruction
        2. Analyzes current content
        3. Generates appropriate update

        For now, return a simple transformation.
        """
        # Simple heuristic-based updates for demo
        instruction_lower = request.instruction.lower()

        if "restart" in instruction_lower and "count" in instruction_lower:
            # Add restart count to synthesize prompt
            updated = current_content + "\n\n### Restart Count\nAlways include pod restart count in status results."
            summary = "Added restart count field to status results"
        elif "alias" in instruction_lower:
            # Add alias to registry (parse from instruction)
            updated = current_content + "\n  - new_alias"
            summary = "Added new alias to registry"
        elif "verbose" in instruction_lower or "more detail" in instruction_lower:
            # Increase detail level
            updated = current_content.replace("2-3 sentence", "3-5 sentence")
            summary = "Increased detail level in summaries"
        else:
            # Generic comment addition
            comment = f"\n\n# User feedback: {request.instruction}"
            updated = current_content + comment
            summary = f"Added note about user feedback"

        return updated, summary

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

    def _write_prompt(self, diff: ArtifactDiff) -> bool:
        """Write updated prompt file."""
        artifact = self.reload_mgr._artifacts.get(diff.artifact_name)
        if not artifact:
            return False

        with open(artifact.path, 'w') as f:
            f.write(diff.after)

        # Force reload to pick up changes
        self.reload_mgr.force_reload(diff.artifact_name)
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
