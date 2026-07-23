"""Server-side card rendering for the dispatch hot path.

The hot-path component selector lives here (plan: The Hot Path / UI-Regen Agent).
It is deterministic — a single ``component_usage_patterns`` lookup keyed on
``results.result_type``, no LLM — and is the only code on the request path that
writes ``card_cache`` and the component usage stats. The async UI-regen agent
(``src.agents.ui_regen``) is the sole writer of component *definitions*
(components / component_versions / component_tags); this module never touches
those tables (write-scope separation — see plan, Component Library).
"""

from .hot_path import (
    DEFAULT_LAYOUT_BUCKET,
    DEFAULT_MATCH_THRESHOLD,
    HotPathRenderer,
    RenderOutcome,
    derive_result_type,
    get_renderer,
)

__all__ = [
    "DEFAULT_LAYOUT_BUCKET",
    "DEFAULT_MATCH_THRESHOLD",
    "HotPathRenderer",
    "RenderOutcome",
    "derive_result_type",
    "get_renderer",
]
