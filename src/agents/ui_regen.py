"""
UI-Regen Agent for aide-de-camp.

Manages the component library: generates, selects, and iterates components.

Component *generation* and *iteration* are LLM-driven (ZAI proxy, SONNET) so the
library can grow purpose-built card layouts for novel result shapes rather than
forcing every result into one of three fixed templates. The fixed list/summary/
generic generators survive only as ``_degradation_*`` fallbacks used when the
LLM is unavailable or returns an unusable response — keeping rendering
resilient. (See plan.md Component 7; "generate vs. stretch an existing
component" matching remains heuristic and is out of scope here — plan.md Open
Question #3.)
"""

import json
import re
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..components.library import Component, ComponentLibrary, get_library
from ..escalate.llm import ModelClass, get_zai_client

logger = getLogger(__name__)

# Prompts are loaded from disk per call so they hot-reload without a restart,
# mirroring src/synthesize/strand.py. Computed relative to the repo root so the
# agent works regardless of the process cwd.
_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
GENERATE_PROMPT_PATH = _PROMPTS_DIR / "ui_regen_generate.md"
ITERATE_PROMPT_PATH = _PROMPTS_DIR / "ui_regen_iterate.md"


@dataclass
class ComponentRequest:
    """A request to render a result."""

    result_id: str
    result_type: str
    result_data: Dict[str, Any]
    layout_bucket: str


@dataclass
class ComponentMatch:
    """A matched component with confidence score."""

    component: Component
    confidence: float
    reason: str


class UIRegenAgent:
    """
    Steward of the component library.

    Responsibilities:
    1. Find best-fit component for a result
    2. Generate new component if no good fit exists (LLM-driven)
    3. Apply component template to result data
    4. Iterate components based on feedback (LLM-driven)
    """

    def __init__(self):
        self.library: ComponentLibrary = get_library()
        self._zai_client = None

    # ------------------------------------------------------------------
    # ZAI client + prompt loading
    # ------------------------------------------------------------------

    async def _get_zai_client(self):
        """Get the ZAI client.

        Returns an injected client (set directly on ``self._zai_client``) when
        present — this is how tests stub the LLM. Otherwise lazily creates the
        shared global client.
        """
        if self._zai_client is None:
            self._zai_client = get_zai_client()
        return self._zai_client

    @staticmethod
    def _load_prompt(path: Path, fallback: str) -> str:
        """Load a prompt from disk (hot-reload); return ``fallback`` on failure."""
        try:
            return path.read_text()
        except Exception as e:
            logger.warning(f"Failed to load prompt {path}: {e}; using fallback")
            return fallback

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    async def render_result(self, request: ComponentRequest) -> str:
        """
        Render a result as HTML.

        Args:
            request: The rendering request

        Returns:
            Rendered HTML
        """
        # Try to get cached card
        cached = self.library.get_cached_card(
            request.result_id,
            "unknown",  # Will be set below
            request.layout_bucket,
        )

        if cached:
            # Verify component version is current
            component = self.library.get_component(cached.component_id)
            if component and component.version == cached.component_version:
                return cached.rendered_html

        # Find or create component
        component = await self._find_or_create_component(request)

        # Apply template
        rendered_html = self._apply_template(component, request.result_data)

        # Cache the result
        self.library.cache_card(
            request.result_id,
            component.id,
            component.version,
            request.layout_bucket,
            rendered_html,
        )

        # Record usage pattern
        self.library.record_usage_pattern(
            component.id,
            request.result_type,
            0.8,  # Default match score when we use a component
        )

        return rendered_html

    async def _find_or_create_component(self, request: ComponentRequest) -> Component:
        """Find existing component or create a new one.

        Selection against existing library entries stays heuristic (keyword /
        usage-pattern based) — see plan.md Open Question #3. Only the
        *generation* of a brand-new component is LLM-driven.
        """
        # Try to find best-fit component
        component = self.library.find_best_component(
            request.result_type,
            request.result_data,
        )

        if component:
            return component

        # No good fit, generate new component
        return await self._generate_component(request)

    async def _generate_component(self, request: ComponentRequest) -> Component:
        """Generate a new component from the result data shape (LLM-driven)."""
        result_type = request.result_type
        data = request.result_data

        # Generate component name and description
        name = self._infer_component_name(result_type)
        description = f"Renders {result_type} results"

        # Generate HTML template based on data structure (LLM call)
        template = await self._generate_template(data, result_type)

        # Create component
        component = self.library.create_component(
            name=name,
            description=description,
            html_template=template,
            change_note=f"Generated from {result_type} result",
        )

        return component

    def _infer_component_name(self, result_type: str) -> str:
        """Infer a component name from result type."""
        # Convert snake-case or kebab-case to name
        return result_type.replace("-", "_").replace("_", "-")

    # ------------------------------------------------------------------
    # Generation (LLM-driven)
    # ------------------------------------------------------------------

    async def _generate_template(self, data: Dict[str, Any], result_type: str) -> str:
        """Generate an HTML template for a result shape via the ZAI LLM.

        Sends the result type and a structural description of the data (field
        names, JSON types, nested fields, list lengths, sample values) and asks
        for a purpose-built card template speaking the flat ``{{field.path}}``
        substitution contract. On any LLM/parse failure — or an empty template —
        it degrades to the heuristic generic template so rendering never breaks.
        """
        try:
            client = await self._get_zai_client()
            system_prompt = self._load_prompt(
                GENERATE_PROMPT_PATH, _GENERATE_PROMPT_FALLBACK
            )
            user_message = self._build_generate_message(data, result_type)

            raw = await client.call_simple(
                system_prompt=system_prompt,
                user_message=user_message,
                model=ModelClass.SONNET.value,
                max_tokens=4096,
                temperature=0.4,  # Lower temperature for stable, valid HTML
            )
            template = self._extract_template(raw)
            if template.strip():
                logger.info(f"UI-regen generated LLM template for {result_type}")
                return template
            logger.warning(f"UI-regen LLM returned empty template for {result_type}; degrading")
        except Exception as e:
            logger.warning(f"UI-regen LLM generation failed for {result_type}: {e}; degrading")

        return self._degradation_generic_template(data, result_type)

    def _build_generate_message(self, data: Dict[str, Any], result_type: str) -> str:
        """Build the user message for the generation LLM call."""
        return (
            f"result_type: {result_type}\n\n"
            f"## Data Shape\n"
            f"{self._describe_data_shape(data)}"
        )

    # ------------------------------------------------------------------
    # Iteration (LLM-driven)
    # ------------------------------------------------------------------

    async def iterate_component(
        self,
        component_id: str,
        feedback: str,
        result_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Component]:
        """
        Iterate a component based on user feedback (LLM-driven).

        Args:
            component_id: The component to iterate
            feedback: User feedback describing what to improve
            result_data: Optional sample data to test against

        Returns:
            The updated component (new version) if the template changed, the
            original component if the LLM produced no change or failed, or None
            if the component was not found.
        """
        component = self.library.get_component(component_id)
        if not component:
            return None

        improved_template = await self._improve_template(
            component.html_template, feedback, result_data
        )

        # No-op: LLM returned the template unchanged (or failed). Leave the
        # component exactly as-is — no spurious version bump.
        if improved_template.strip() == component.html_template.strip():
            return component

        return self.library.update_component(
            component_id,
            improved_template,
            feedback,
        )

    async def _improve_template(
        self,
        current_template: str,
        feedback: str,
        sample_data: Optional[Dict[str, Any]],
    ) -> str:
        """Improve a template from user feedback via the ZAI LLM.

        Returns the full updated template. On any LLM/parse failure — or an
        empty response — returns ``current_template`` unchanged, so the caller
        can treat "no usable improvement" uniformly as a no-op.
        """
        try:
            client = await self._get_zai_client()
            system_prompt = self._load_prompt(
                ITERATE_PROMPT_PATH, _ITERATE_PROMPT_FALLBACK
            )
            user_message = self._build_iterate_message(
                current_template, feedback, sample_data
            )

            raw = await client.call_simple(
                system_prompt=system_prompt,
                user_message=user_message,
                model=ModelClass.SONNET.value,
                max_tokens=4096,
                temperature=0.4,
            )
            template = self._extract_template(raw)
            if template.strip():
                logger.info("UI-regen produced LLM-improved template")
                return template
            logger.warning("UI-regen LLM iteration returned empty template; leaving unchanged")
        except Exception as e:
            logger.warning(f"UI-regen LLM iteration failed: {e}; leaving template unchanged")

        return current_template

    def _build_iterate_message(
        self,
        current_template: str,
        feedback: str,
        sample_data: Optional[Dict[str, Any]],
    ) -> str:
        """Build the user message for the iteration LLM call."""
        shape = (
            self._describe_data_shape(sample_data)
            if sample_data
            else "(no sample data provided)"
        )
        return (
            f"## Feedback\n{feedback}\n\n"
            f"## Current Template\n{current_template}\n\n"
            f"## Data Shape\n{shape}"
        )

    # ------------------------------------------------------------------
    # Shared LLM helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_template(raw: str) -> str:
        """Extract the ``html_template`` string from an LLM response.

        GLM-4.7 wraps JSON in ```json fences — strip them. The ZAI client
        already unwrapped the Anthropic ``"result"`` envelope, so ``raw`` is the
        model's text content. Returns "" on any parse failure so callers can
        fall back.
        """
        raw = (raw or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        if not raw:
            return ""
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        if isinstance(obj, dict):
            return obj.get("html_template") or ""
        return ""

    @classmethod
    def _describe_data_shape(cls, data: Any, indent: int = 0) -> str:
        """Render a human/LLM-readable description of a result's data shape.

        Lists field names with their JSON types, recurses into nested objects,
        summarizes lists by length + a single sample element, and includes
        representative scalar sample values. Field names appear verbatim so the
        LLM can reference them as ``{{field.path}}`` placeholders.
        """
        pad = "  " * indent
        lines: List[str] = []
        if isinstance(data, dict):
            if not data:
                return f"{pad}(empty object)"
            for key, value in data.items():
                lines.extend(cls._describe_field(key, value, indent))
        elif isinstance(data, list):
            lines.extend(cls._describe_field("(root list)", data, indent))
        else:
            lines.append(f"{pad}{cls._type_label(data)} = {data!r}")
        return "\n".join(lines)

    @classmethod
    def _describe_field(cls, key: str, value: Any, indent: int) -> List[str]:
        """Describe a single field for the data-shape summary."""
        pad = "  " * indent
        if isinstance(value, dict):
            lines = [f"{pad}{key}: object with fields:"]
            for k, v in value.items():
                lines.extend(cls._describe_field(k, v, indent + 1))
            return lines
        if isinstance(value, list):
            n = len(value)
            if value and isinstance(value[0], dict):
                lines = [f"{pad}{key}: list[{n}] of objects, sample[0] fields:"]
                for k, v in value[0].items():
                    lines.extend(cls._describe_field(k, v, indent + 1))
                return lines
            if value:
                return [f"{pad}{key}: list[{n}] of {cls._type_label(value[0])}, sample[0] = {value[0]!r}"]
            return [f"{pad}{key}: list[0] (empty)"]
        return [f"{pad}{key}: {cls._type_label(value)} = {value!r}"]

    @staticmethod
    def _type_label(value: Any) -> str:
        """JSON-ish type label for a scalar/leaf value."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "str"
        return type(value).__name__

    # ------------------------------------------------------------------
    # Template application (sync — pure string substitution)
    # ------------------------------------------------------------------

    def _apply_template(self, component: Component, result_data: Dict[str, Any]) -> str:
        """Apply a component template to result data.

        Flat dot-path substitution: every ``{{field.path}}`` token is replaced
        with the value at that dot-path (list indices via numeric segments,
        e.g. ``{{pods.0.name}}``). Unknown paths resolve to "". No loops or
        conditionals — the LLM is instructed to emit only flat placeholders.
        """
        template = component.html_template
        result = template

        def replace_value(match):
            path = match.group(1).strip()
            value = self._get_nested_value(result_data, path)
            return "" if value is None else str(value)

        result = re.sub(r"\{\{([^}]+)\}\}", replace_value, result)
        return result

    @staticmethod
    def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
        """Get value from nested dict/list using dot notation."""
        keys = path.split(".")
        value: Any = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
                value = value[int(key)]
            else:
                return None
        return value

    # ------------------------------------------------------------------
    # Heuristic fallback templates (degradation path only)
    # ------------------------------------------------------------------
    # These three fixed layouts are ONLY used when the LLM is unavailable or
    # returns an unusable response. They must stay distinct from real LLM
    # output so tests can assert a generated template is genuinely novel.

    def _degradation_list_template(self, data: Dict[str, Any], result_type: str) -> str:
        """Fallback template for list-based results."""
        items = data.get("items", [])
        if not items:
            return "<div class='card-empty'>No data</div>"

        sample = items[0]
        fields = list(sample.keys()) if isinstance(sample, dict) else []

        item_rows = "\n".join(
            [
                "  <div class='card-item'>"
                f"    <span class='card-field'>{field}</span>"
                f"    <span class='card-value'>{{{{item.{field}}}}}</span>"
                "  </div>"
                for field in fields[:5]  # Limit to 5 fields
            ]
        )

        template = f"""<div class='card card-{result_type}'>
<div class='card-header'>
  <h3 class='card-title'>{result_type.title()}</h3>
  <span class='card-count'>{{{{summary_fields.total}}}} items</span>
</div>
<div class='card-body'>
{{{{#each items}}}}
{item_rows}
{{{{/each}}}}
</div>
</div>"""

        return template

    def _degradation_summary_template(self, data: Dict[str, Any], result_type: str) -> str:
        """Fallback template for summary-based results."""
        summary_fields = data.get("summary_fields", {})

        rows = "\n".join(
            [
                "  <div class='card-summary-row'>"
                f"    <span class='card-label'>{key.replace('_', ' ').title()}:</span>"
                f"    <span class='card-value'>{{{{summary_fields.{key}}}}}</span>"
                "  </div>"
                for key in list(summary_fields.keys())[:6]
            ]
        )

        template = f"""<div class='card card-{result_type} card-summary'>
<div class='card-header'>
  <h3 class='card-title'>{result_type.title()}</h3>
</div>
<div class='card-body'>
{rows}
</div>
</div>"""

        return template

    def _degradation_generic_template(self, data: Dict[str, Any], result_type: str) -> str:
        """Fallback generic template for any result."""
        fields = list(data.keys())

        rows = "\n".join(
            [
                "  <div class='card-field-row'>"
                f"    <span class='card-label'>{key}:</span>"
                f"    <span class='card-value'>{{{{{key}}}}}</span>"
                "  </div>"
                for key in fields[:8]
            ]
        )

        template = f"""<div class='card card-{result_type}'>
<div class='card-header'>
  <h3 class='card-title'>{result_type.title()}</h3>
</div>
<div class='card-body'>
{rows}
</div>
</div>"""

        return template

    # ------------------------------------------------------------------
    # Discovery / suggestions (sync, heuristic — unchanged)
    # ------------------------------------------------------------------

    def find_components_for_result_type(self, result_type: str) -> List[ComponentMatch]:
        """
        Find all components that could handle a result type, ranked by confidence.

        Args:
            result_type: The type of result to find components for

        Returns:
            List of component matches, sorted by confidence
        """
        matches: List[ComponentMatch] = []

        # Get all components
        components = self.library.list_components(limit=100)

        for component in components:
            # Calculate match score
            score = self.library._semantic_score(
                result_type,
                component.name,
                component.description,
            )

            if score > 0.3:  # Minimum threshold
                matches.append(
                    ComponentMatch(
                        component=component,
                        confidence=score,
                        reason=f"Semantic match: {score:.2f}",
                    )
                )

        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    def get_component_suggestions(
        self,
        result_data: Dict[str, Any],
        result_type: str,
    ) -> List[str]:
        """
        Get suggestions for component improvements based on result data.

        Args:
            result_data: The result data to analyze
            result_type: The type of result

        Returns:
            List of suggestion strings
        """
        suggestions = []

        # Analyze data structure for missing common fields
        if "items" in result_data and isinstance(result_data["items"], list):
            items = result_data["items"]
            if items:
                sample = items[0]
                if isinstance(sample, dict):
                    # Check for common fields that might be missing
                    if "status" not in sample and "phase" not in sample:
                        suggestions.append("Consider adding status field to items")
                    if "name" not in sample and "id" not in sample:
                        suggestions.append("Consider adding name/id field for identification")

        # Check for trend capability
        if "timestamp" in str(result_data) or "time" in str(result_data):
            suggestions.append("Data appears time-series; consider trend visualization")

        # Check for health/summary fields
        if "summary_fields" in result_data:
            summary = result_data["summary_fields"]
            if any(k in summary for k in ["healthy", "unhealthy", "degraded"]):
                suggestions.append("Consider health status indicator in component")

        return suggestions


# Inline fallbacks used only if the prompt files cannot be read from disk.
_GENERATE_PROMPT_FALLBACK = (
    "You are a component generator. Given a result_type and data_shape, generate "
    "a purpose-built HTML card template using flat {{field.path}} substitution "
    "(no loops/conditionals). Return ONLY JSON: "
    '{"html_template": "...", "rationale": "..."}.'
)
_ITERATE_PROMPT_FALLBACK = (
    "You are a component iterator. Given user feedback, a current HTML template, "
    "and an optional data_shape, return the complete updated template using flat "
    "{{field.path}} substitution. Return ONLY JSON: "
    '{"html_template": "...", "change_summary": "..."}.'
)


# Singleton instance
_agent: Optional[UIRegenAgent] = None


def get_ui_regen_agent() -> UIRegenAgent:
    """Get or create the UI-regen agent singleton."""
    global _agent
    if _agent is None:
        _agent = UIRegenAgent()
    return _agent
