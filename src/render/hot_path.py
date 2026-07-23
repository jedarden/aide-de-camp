"""Deterministic, no-LLM server-side card selector (the dispatch hot path).

On every dispatch the server picks the component to render a result
*deterministically* — the highest ``match_score`` row in
``component_usage_patterns`` for the result's ``result_type``, no LLM call —
fills that component's template with the result data per layout bucket, writes
the rendered HTML to ``card_cache``, records the usage, and returns it for SSE
streaming. When nothing matches (a first-ever result shape, or no score above
threshold) the result is *flagged* (``card_fallback``) and the client renders
the built-in generic fallback card — a novel shape never blanks the canvas.

Scope of writes (plan, Component Library → Built-in generic fallback card +
UI-Regen Agent): the hot-path renderer is the sole writer of ``card_cache`` and
the component usage stats (``components.usage_count`` / ``last_used`` and
``component_usage_patterns``). It NEVER writes component definitions
(``components`` rows, ``component_versions``, ``component_tags``) — that is the
UI-regen agent's job alone, so the two never race on a component's identity.
"""

import html
import json
import re
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Optional

from ..components.library import Component, ComponentLibrary, get_library

logger = getLogger(__name__)

# A component_usage_patterns row must clear this to be selected (plan: "highest
# match_score ... no LLM"; below this the result falls to the built-in fallback).
DEFAULT_MATCH_THRESHOLD = 0.7

# The hot path renders one card per intent thread at a single layout bucket.
DEFAULT_LAYOUT_BUCKET = "normal"

# Flat ``{{field.path}}`` token (no loops/conditionals) — the same substitution
# contract the UI-regen generator is told to emit (see ui_regen.py).
_PLACEHOLDER = re.compile(r"\{\{([^}]+)\}\}")


def derive_result_type(
    intent_type: Optional[str],
    project_slug: Optional[str],
    lookup_kind: Optional[str] = None,
) -> str:
    """Derive the deterministic card-selector key written to ``results.result_type``.

    - intent-derived: ``"{intent_type}:{project_slug}"`` — one per intent thread
      (the aggregated thread card), never per fetch source.
    - lookup threads insert the router's ``lookup_kind``:
      ``"lookup:{lookup_kind}:{project_slug}"`` (e.g. ``lookup:logs:ibkr-mcp`` vs
      ``lookup:config:ibkr-mcp`` — distinct keys, distinct cards).
    - monitoring-originated rows: ``"monitoring:{project_slug}"``.

    A missing project slug collapses to ``"general"`` so the key is always a
    non-empty, colon-segmented string the selector can index on.
    """
    slug = project_slug or "general"
    itype = intent_type or "status"
    if itype == "monitoring":
        return f"monitoring:{slug}"
    if itype == "lookup" and lookup_kind:
        return f"lookup:{lookup_kind}:{slug}"
    return f"{itype}:{slug}"


@dataclass
class RenderOutcome:
    """Result of a hot-path render: either a real component render, or a fallback flag.

    ``rendered_html`` is None exactly when no component matched (the client must
    render the built-in generic fallback card). ``card_fallback`` is the boolean
    mirror persisted onto the result row so loadTopics()/the SSE consumer both
    see the same decision without re-running the selector.
    """

    rendered_html: Optional[str]
    component_id: Optional[str]
    card_fallback: bool
    layout_bucket: str


class HotPathRenderer:
    """Deterministic server-side card selector — never on the LLM path.

    Selection is a single ``component_usage_patterns`` lookup on
    ``result_type``; on a match it fills the template (escaping every
    interpolated value — the render-path escaping boundary), writes
    ``card_cache``, and bumps the usage stats. On no match it returns a
    fallback outcome and writes nothing to the component DB.
    """

    def __init__(
        self,
        library: Optional[ComponentLibrary] = None,
        match_threshold: float = DEFAULT_MATCH_THRESHOLD,
        layout_bucket: str = DEFAULT_LAYOUT_BUCKET,
    ):
        self.library = library or get_library()
        self.match_threshold = match_threshold
        self.layout_bucket = layout_bucket

    def render(
        self,
        result_id: str,
        result_type: str,
        result_data: dict[str, Any],
        summary: Optional[str] = None,
        urgency: Optional[str] = None,
        layout_bucket: Optional[str] = None,
    ) -> RenderOutcome:
        """Select + render a card for one result. Deterministic, no LLM.

        On a match: fills the template (escaped), writes card_cache keyed
        ``(result_id, component_id, layout_bucket)``, and records the usage
        pattern + usage stats. On no match / below threshold: returns a fallback
        outcome with the rendered fallback HTML and writes nothing to the
        component DB.
        """
        bucket = layout_bucket or self.layout_bucket

        component = self.library.select_component_for_result_type(
            result_type, self.match_threshold
        )
        if component is None:
            logger.debug(
                "hot-path fallback: no component matched result_type=%s "
                "(threshold %.2f) for result %s",
                result_type,
                self.match_threshold,
                result_id,
            )
            # Render the fallback card server-side for SSE streaming
            fallback_html = render_fallback_card(
                summary=summary,
                data=result_data,
                urgency=urgency,
            )
            return RenderOutcome(
                rendered_html=fallback_html,
                component_id=None,
                card_fallback=True,
                layout_bucket=bucket,
            )

        rendered_html = fill_template(component.html_template, result_data)

        # The server is the sole writer of card_cache + usage stats (write-scope
        # separation). cache_card bumps components.usage_count/last_used;
        # record_usage_pattern updates component_usage_patterns (sample_count,
        # last_matched, running match_score). Neither touches component
        # definitions — that is the UI-regen agent's job.
        self.library.cache_card(
            result_id, component.id, component.version, bucket, rendered_html
        )
        # A hot-path match is a confirmed, high-confidence usage — record at 1.0
        # so reliably-matching components trend toward the top of the selector.
        self.library.record_usage_pattern(component.id, result_type, match_score=1.0)

        logger.info(
            "hot-path rendered result %s with component %s v%s (result_type=%s)",
            result_id,
            component.id,
            component.version,
            result_type,
        )
        return RenderOutcome(
            rendered_html=rendered_html,
            component_id=component.id,
            card_fallback=False,
            layout_bucket=bucket,
        )


# ---------------------------------------------------------------------------
# Template fill — the render-path escaping boundary
# ---------------------------------------------------------------------------

def fill_template(template: str, result_data: dict[str, Any]) -> str:
    """Flat dot-path substitution with HTML escaping at fill time.

    Every ``{{field.path}}`` token is replaced with the HTML-escaped value at
    that dot-path (list indices via numeric segments, e.g. ``{{pods.0.name}}``).
    Unknown paths resolve to "". This is the escaping boundary the plan binds
    every server-filled card to (UI-Regen Agent → "Escaping contract"): a
    markup-looking log line interpolated here renders as literal text instead of
    breaking layout or executing in the canvas. No loops or conditionals — the
    generator is instructed to emit only flat placeholders.
    """
    if not template:
        return ""

    def replace_value(match: re.Match) -> str:
        path = match.group(1).strip()
        value = _get_nested_value(result_data, path)
        if value is None:
            return ""
        return html.escape(str(value), quote=False)

    return _PLACEHOLDER.sub(replace_value, template)


def _get_nested_value(data: dict[str, Any], path: str) -> Any:
    """Resolve a dot-path against a dict/list (numeric segments index lists)."""
    value: Any = data
    for key in path.split("."):
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
        else:
            return None
    return value


# ---------------------------------------------------------------------------
# Generic fallback card renderer (server-side)
# ---------------------------------------------------------------------------

def _stringify_value(value: Any) -> str:
    """Stringify a value for fallback card display (mirrors client-side _stringify)."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value)
    except Exception:
        return str(value)


def _fallback_rows(data: Any) -> list[tuple[str, str]]:
    """Flatten result.data into [key, value] string pairs (mirrors client-side _fallbackRows)."""
    if data is None:
        return []

    obj = data

    # Handle string - try to parse as JSON
    if isinstance(data, str):
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return [('value', data)]

    # Handle array
    if isinstance(obj, list):
        rows = []
        for i, v in enumerate(obj[:50]):  # Max 50 rows
            rows.append((str(i), _stringify_value(v)))
        return rows

    # Handle object
    if isinstance(obj, dict):
        rows = []
        for k in list(obj.keys())[:50]:  # Max 50 rows
            rows.append((k, _stringify_value(obj[k])))
        return rows

    # Handle primitive
    return [('value', str(obj))]


def render_fallback_card(
    summary: str | None = None,
    data: dict[str, Any] | None = None,
    urgency: str | None = None,
) -> str:
    """Render the generic fallback card HTML (server-side version of createFallbackCard).

    This generates the same HTML structure as the client-side createFallbackCard()
    function in canvas.js, ensuring the fallback card can be streamed via SSE
    and injected directly into the canvas without a blank canvas state.

    All dynamic values are HTML-escaped per the escaping contract.

    Args:
        summary: Optional result summary
        data: Optional result data dict for key/value grid
        urgency: Optional urgency level for badge

    Returns:
        HTML string for the fallback card
    """
    try:
        # Build fallback card HTML
        card_parts = ['<div class="builtin-card fallback-card" data-builtin="fallback">']

        # Header with icon and title
        card_parts.append('  <div class="builtin-header">')
        card_parts.append(f'    <span class="builtin-icon">{html.escape("🗒️", quote=False)}</span>')
        card_parts.append(f'    <span class="builtin-title">{html.escape("Result", quote=False)}</span>')
        card_parts.append('  </div>')

        # Summary paragraph
        if summary:
            card_parts.append(f'  <p class="fallback-summary">{html.escape(summary, quote=False)}</p>')

        # Key/value grid from data
        if data:
            rows = _fallback_rows(data)
            if rows:
                card_parts.append('  <div class="fallback-grid">')
                for key, value in rows:
                    card_parts.append(f'    <div class="fallback-key">{html.escape(key, quote=False)}</div>')
                    card_parts.append(f'    <div class="fallback-val">{html.escape(value, quote=False)}</div>')
                card_parts.append('  </div>')

        # Urgency badge
        if urgency:
            card_parts.append(f'  <span class="urgency-badge {html.escape(urgency, quote=False)}">{html.escape(urgency, quote=False)}</span>')

        card_parts.append('</div>')

        return '\n'.join(card_parts)

    except Exception as e:
        # Fallback render failures should not crash the dispatch flow
        logger.error(f"Fallback card render failed: {e}")
        # Return minimal safe fallback HTML
        return f'<div class="builtin-card fallback-card" data-builtin="fallback"><p class="fallback-summary">{html.escape(summary or "Result", quote=False)}</p></div>'


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_renderer: Optional[HotPathRenderer] = None


def get_renderer(
    library: Optional[ComponentLibrary] = None,
    reset: bool = False,
) -> HotPathRenderer:
    """Get or create the process-wide hot-path renderer singleton.

    Pass ``library=`` (and ``reset=True``) to rebind it — how tests point the
    renderer at an isolated component DB without touching the production
    ``data/components.db`` singleton.
    """
    global _renderer
    if _renderer is None or reset or library is not None:
        _renderer = HotPathRenderer(library=library)
    return _renderer
