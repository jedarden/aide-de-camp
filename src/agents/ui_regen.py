"""
UI-Regen Agent for aide-de-camp.

Manages the component library: generates, selects, and iterates components.
"""

import json
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

from ..components.library import ComponentLibrary, Component, get_library


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
    2. Generate new component if no good fit exists
    3. Apply component template to result data
    4. Iterate components based on feedback
    """

    def __init__(self):
        self.library: ComponentLibrary = get_library()

    def render_result(self, request: ComponentRequest) -> str:
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
            request.layout_bucket
        )

        if cached:
            # Verify component version is current
            component = self.library.get_component(cached.component_id)
            if component and component.version == cached.component_version:
                return cached.rendered_html

        # Find or create component
        component = self._find_or_create_component(request)

        # Apply template
        rendered_html = self._apply_template(component, request.result_data)

        # Cache the result
        self.library.cache_card(
            request.result_id,
            component.id,
            component.version,
            request.layout_bucket,
            rendered_html
        )

        # Record usage pattern
        self.library.record_usage_pattern(
            component.id,
            request.result_type,
            0.8  # Default match score when we use a component
        )

        return rendered_html

    def _find_or_create_component(self, request: ComponentRequest) -> Component:
        """Find existing component or create a new one."""
        # Try to find best-fit component
        component = self.library.find_best_component(
            request.result_type,
            request.result_data
        )

        if component:
            return component

        # No good fit, generate new component
        return self._generate_component(request)

    def _generate_component(self, request: ComponentRequest) -> Component:
        """
        Generate a new component from result data shape.

        In production, this is an LLM call. For now, use template heuristics.
        """
        result_type = request.result_type
        data = request.result_data

        # Generate component name and description
        name = self._infer_component_name(result_type)
        description = f"Renders {result_type} results"

        # Generate HTML template based on data structure
        template = self._generate_template(data, result_type)

        # Create component
        component = self.library.create_component(
            name=name,
            description=description,
            html_template=template,
            change_note=f"Generated from {result_type} result"
        )

        return component

    def _infer_component_name(self, result_type: str) -> str:
        """Infer a component name from result type."""
        # Convert snake-case or kebab-case to name
        return result_type.replace('-', '_').replace('_', '-')

    def _generate_template(self, data: Dict[str, Any], result_type: str) -> str:
        """
        Generate HTML template based on data structure.

        In production, this is an LLM call. For now, use heuristics.
        """
        # Basic template structure
        if "items" in data and isinstance(data["items"], list):
            return self._generate_list_template(data, result_type)
        elif "summary_fields" in data:
            return self._generate_summary_template(data, result_type)
        else:
            return self._generate_generic_template(data, result_type)

    def _generate_list_template(self, data: Dict[str, Any], result_type: str) -> str:
        """Generate template for list-based results."""
        # Get a sample item to understand structure
        items = data.get("items", [])
        if not items:
            return "<div class='card-empty'>No data</div>"

        sample = items[0]
        fields = list(sample.keys()) if isinstance(sample, dict) else []

        # Generate item rows
        item_rows = "\n".join([
            f"  <div class='card-item'>"
            f"    <span class='card-field'>{field}</span>"
            f"    <span class='card-value'>{{{item}.{field}}}}</span>"
            f"  </div>"
            for field in fields[:5]  # Limit to 5 fields
        ])

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

    def _generate_summary_template(self, data: Dict[str, Any], result_type: str) -> str:
        """Generate template for summary-based results."""
        summary_fields = data.get("summary_fields", {})

        rows = "\n".join([
            f"  <div class='card-summary-row'>"
            f"    <span class='card-label'>{key.replace('_', ' ').title()}:</span>"
            f"    <span class='card-value'>{{{{summary_fields.{key}}}}}</span>"
            f"  </div>"
            for key in list(summary_fields.keys())[:6]
        ])

        template = f"""<div class='card card-{result_type} card-summary'>
<div class='card-header'>
  <h3 class='card-title'>{result_type.title()}</h3>
</div>
<div class='card-body'>
{rows}
</div>
</div>"""

        return template

    def _generate_generic_template(self, data: Dict[str, Any], result_type: str) -> str:
        """Generate generic template for any result."""
        fields = list(data.keys())

        rows = "\n".join([
            f"  <div class='card-field-row'>"
            f"    <span class='card-label'>{key}:</span>"
            f"    <span class='card-value'>{{{{{key}}}}}</span>"
            f"  </div>"
            for key in fields[:8]
        ])

        template = f"""<div class='card card-{result_type}'>
<div class='card-header'>
  <h3 class='card-title'>{result_type.title()}</h3>
</div>
<div class='card-body'>
{rows}
</div>
</div>"""

        return template

    def _apply_template(self, component: Component, result_data: Dict[str, Any]) -> str:
        """
        Apply component template to result data.

        Simple string substitution for now. In production, use a proper template engine.
        """
        template = component.html_template
        result = template

        # Simple Mustache-like substitution
        def replace_value(match):
            path = match.group(1)
            value = self._get_nested_value(result_data, path)
            return str(value) if value is not None else ""

        import re
        result = re.sub(r'\{\{([^}]+)\}\}', replace_value, result)

        # Handle each blocks (basic implementation)
        # In production, use a proper template engine
        return result

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get value from nested dict using dot notation."""
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit():
                value = value[int(key)]
            else:
                return None
        return value

    def iterate_component(
        self,
        component_id: str,
        feedback: str,
        result_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Component]:
        """
        Iterate a component based on user feedback.

        Args:
            component_id: The component to iterate
            feedback: User feedback describing what to improve
            result_data: Optional sample data to test against

        Returns:
            The updated component, or None if not found
        """
        component = self.library.get_component(component_id)
        if not component:
            return None

        # Generate improved template
        # In production, this is an LLM call with:
        # - Current template
        # - User feedback
        # - Sample result data
        improved_template = self._improve_template(
            component.html_template,
            feedback,
            result_data
        )

        # Update component
        updated = self.library.update_component(
            component_id,
            improved_template,
            feedback
        )

        return updated

    def _improve_template(
        self,
        current_template: str,
        feedback: str,
        sample_data: Optional[Dict[str, Any]]
    ) -> str:
        """
        Generate improved template based on feedback.

        In production, this is an LLM call. For now, use simple heuristics.
        """
        feedback_lower = feedback.lower()

        # Add common fields if requested
        if "restart" in feedback_lower and "count" in feedback_lower:
            # Add restart count field
            if "restart" not in current_template.lower():
                restart_row = """  <div class='card-field-row'>
    <span class='card-label'>Restarts:</span>
    <span class='card-value'>{{restarts}}</span>
  </div>"""
                # Insert before closing div
                if "</div>" in current_template:
                    current_template = current_template.replace(
                        "</div>",
                        restart_row + "</div>",
                        1
                    )

        elif "trend" in feedback_lower or "sparkline" in feedback_lower:
            # Add trend indicator
            if "trend" not in current_template.lower():
                trend_div = "<div class='card-trend' data-field='trend'></div>"
                current_template = current_template.replace(
                    "<div class='card-body'>",
                    "<div class='card-body'>" + trend_div
                )

        elif "clutter" in feedback_lower or "too much" in feedback_lower:
            # Simplify - remove some fields
            # This is a naive approach; in production, use LLM
            lines = current_template.split('\n')
            simplified = [l for i, l in enumerate(lines) if i % 3 != 0 or 'card-header' in l]
            current_template = '\n'.join(simplified)

        return current_template

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
                component.description
            )

            if score > 0.3:  # Minimum threshold
                matches.append(ComponentMatch(
                    component=component,
                    confidence=score,
                    reason=f"Semantic match: {score:.2f}"
                ))

        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    def get_component_suggestions(
        self,
        result_data: Dict[str, Any],
        result_type: str
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


# Singleton instance
_agent: Optional[UIRegenAgent] = None


def get_ui_regen_agent() -> UIRegenAgent:
    """Get or create the UI-regen agent singleton."""
    global _agent
    if _agent is None:
        _agent = UIRegenAgent()
    return _agent
