"""
Unit tests for result_type derivation logic (bead adc-35zq).

Tests the derive_result_type function covering all three derivation branches:
- Intent-derived results: {intent_type}:{project_slug}
- Lookup threads: lookup:{lookup_kind}:{project_slug}
- Monitoring-originated results: monitoring:{project_slug}

Also tests edge cases: None values, missing project_slug fallback to 'general',
and determinism (same inputs always produce same output).
"""

import pytest

from src.render.hot_path import derive_result_type


class TestDeriveResultType:
    """Test derive_result_type function for all derivation branches."""

    # --- Intent-derived results ------------------------------------------------

    @pytest.mark.parametrize(
        "intent_type,project_slug,expected",
        [
            # Basic intent types with project slug
            ("status", "ibkr-mcp", "status:ibkr-mcp"),
            ("action", "options-pipeline", "action:options-pipeline"),
            ("brainstorm", "aide-de-camp", "brainstorm:aide-de-camp"),
            ("reminder", "general", "reminder:general"),
            ("self-modification", "aide-de-camp", "self-modification:aide-de-camp"),
            ("monitoring-config", "general", "monitoring-config:general"),
            ("task-profile", "aide-de-camp", "task-profile:aide-de-camp"),
            ("clarification", "general", "clarification:general"),
            ("stuck", "ibkr-mcp", "stuck:ibkr-mcp"),
        ],
    )
    def test_intent_derived_with_project_slug(self, intent_type, project_slug, expected):
        """Test intent-derived result_type with project_slug."""
        result = derive_result_type(
            intent_type=intent_type,
            project_slug=project_slug,
            lookup_kind=None,
        )
        assert result == expected

    def test_intent_derived_fallback_to_general(self):
        """Test that missing project_slug collapses to 'general'."""
        result = derive_result_type(
            intent_type="status",
            project_slug=None,
            lookup_kind=None,
        )
        assert result == "status:general"

    def test_intent_derived_missing_intent_type_fallback(self):
        """Test that missing intent_type falls back to 'status'."""
        result = derive_result_type(
            intent_type=None,
            project_slug="ibkr-mcp",
            lookup_kind=None,
        )
        assert result == "status:ibkr-mcp"

    def test_intent_derived_both_none(self):
        """Test that both None produces 'status:general'."""
        result = derive_result_type(
            intent_type=None,
            project_slug=None,
            lookup_kind=None,
        )
        assert result == "status:general"

    # --- Lookup threads --------------------------------------------------------

    @pytest.mark.parametrize(
        "intent_type,lookup_kind,project_slug,expected",
        [
            # Lookup intents with different kinds
            ("lookup", "logs", "ibkr-mcp", "lookup:logs:ibkr-mcp"),
            ("lookup", "config", "ibkr-mcp", "lookup:config:ibkr-mcp"),
            ("lookup", "docs", "aide-de-camp", "lookup:docs:aide-de-camp"),
            ("lookup", "logs", "options-pipeline", "lookup:logs:options-pipeline"),
            ("lookup", "metrics", "monitoring-system", "lookup:metrics:monitoring-system"),
        ],
    )
    def test_lookup_with_kind_and_project(self, intent_type, lookup_kind, project_slug, expected):
        """Test lookup result_type with lookup_kind and project_slug."""
        result = derive_result_type(
            intent_type=intent_type,
            project_slug=project_slug,
            lookup_kind=lookup_kind,
        )
        assert result == expected

    def test_lookup_without_kind_uses_basic_format(self):
        """Test that lookup without lookup_kind uses basic intent format."""
        # When lookup_kind is None, it should fall back to basic format
        result = derive_result_type(
            intent_type="lookup",
            project_slug="ibkr-mcp",
            lookup_kind=None,
        )
        assert result == "lookup:ibkr-mcp"

    def test_lookup_with_kind_no_project_slug(self):
        """Test lookup with lookup_kind but no project_slug."""
        result = derive_result_type(
            intent_type="lookup",
            project_slug=None,
            lookup_kind="logs",
        )
        assert result == "lookup:logs:general"

    # --- Monitoring-originated results -----------------------------------------

    def test_monitoring_with_project_slug(self):
        """Test monitoring-originated result_type with project_slug."""
        result = derive_result_type(
            intent_type="monitoring",
            project_slug="ibkr-mcp",
            lookup_kind=None,
        )
        assert result == "monitoring:ibkr-mcp"

    def test_monitoring_without_project_slug(self):
        """Test monitoring-originated result_type without project_slug."""
        result = derive_result_type(
            intent_type="monitoring",
            project_slug=None,
            lookup_kind=None,
        )
        assert result == "monitoring:general"

    def test_monitoring_ignores_lookup_kind(self):
        """Test that monitoring intent_type ignores lookup_kind parameter."""
        # Even with lookup_kind set, monitoring should use monitoring:{slug}
        result = derive_result_type(
            intent_type="monitoring",
            project_slug="options-pipeline",
            lookup_kind="logs",  # Should be ignored for monitoring
        )
        assert result == "monitoring:options-pipeline"

    # --- Determinism tests -----------------------------------------------------

    @pytest.mark.parametrize(
        "intent_type,project_slug,lookup_kind",
        [
            ("status", "ibkr-mcp", None),
            ("lookup", "logs", "ibkr-mcp"),
            ("monitoring", "options-pipeline", None),
            (None, None, None),
            ("action", None, None),
            ("lookup", None, None),
        ],
    )
    def test_determinism_same_inputs_same_output(self, intent_type, project_slug, lookup_kind):
        """Test that derive_result_type is deterministic: same inputs always produce same output."""
        result1 = derive_result_type(intent_type, project_slug, lookup_kind)
        result2 = derive_result_type(intent_type, project_slug, lookup_kind)
        result3 = derive_result_type(intent_type, project_slug, lookup_kind)

        assert result1 == result2 == result3

    # --- Edge cases -----------------------------------------------------------

    def test_empty_string_project_slug(self):
        """Test handling of empty string project_slug."""
        # Empty string is treated as falsy, should fallback to 'general'
        result = derive_result_type(
            intent_type="status",
            project_slug="",
            lookup_kind=None,
        )
        assert result == "status:general"

    def test_empty_string_lookup_kind(self):
        """Test handling of empty string lookup_kind."""
        # Empty string lookup_kind is falsy, should use basic format
        result = derive_result_type(
            intent_type="lookup",
            project_slug="ibkr-mcp",
            lookup_kind="",
        )
        assert result == "lookup:ibkr-mcp"

    def test_all_empty_strings(self):
        """Test handling of all empty string parameters."""
        result = derive_result_type(
            intent_type="",
            project_slug="",
            lookup_kind="",
        )
        # Empty intent_type is falsy, so falls back to 'status'
        # Empty project_slug falls back to 'general'
        assert result == "status:general"

    # --- Per-thread granularity verification -----------------------------------

    def test_per_thread_not_per_source_granularity(self):
        """
        Verify that result_type is per-intent-thread, not per-fetch-source.

        The derive_result_type function produces one key per intent thread
        (based on intent_type, project_slug, and optional lookup_kind), NOT
        per fetch source. Multiple fetch sources for the same intent thread
        would all use the same result_type.

        This test documents that granularity is at the thread level, which is
        correct per the plan: "one result_type per intent thread (the aggregated
        thread card), never per fetch source."
        """
        # Same intent thread parameters should produce same result_type
        # regardless of how many fetch sources are involved
        thread_params = {
            "intent_type": "status",
            "project_slug": "ibkr-mcp",
            "lookup_kind": None,
        }

        # All these represent different fetch sources for the same thread
        # but they all derive the same result_type
        result_type_1 = derive_result_type(**thread_params)
        result_type_2 = derive_result_type(**thread_params)
        result_type_3 = derive_result_type(**thread_params)

        assert result_type_1 == result_type_2 == result_type_3 == "status:ibkr-mcp"

    # --- Integration-style scenarios -----------------------------------------

    def test_real_world_status_intent_ibkr(self):
        """Test a real-world status intent for ibkr-mcp project."""
        result = derive_result_type(
            intent_type="status",
            project_slug="ibkr-mcp",
            lookup_kind=None,
        )
        assert result == "status:ibkr-mcp"

    def test_real_world_lookup_logs_intent(self):
        """Test a real-world lookup logs intent for options-pipeline."""
        result = derive_result_type(
            intent_type="lookup",
            project_slug="options-pipeline",
            lookup_kind="logs",
        )
        assert result == "lookup:logs:options-pipeline"

    def test_real_world_monitoring_pipeline(self):
        """Test a real-world monitoring intent for a pipeline."""
        result = derive_result_type(
            intent_type="monitoring",
            project_slug="options-pipeline",
            lookup_kind=None,
        )
        assert result == "monitoring:options-pipeline"

    def test_real_world_task_profile_implementation(self):
        """Test a real-world task-profile intent for implementation work."""
        result = derive_result_type(
            intent_type="task-profile",
            project_slug="aide-de-camp",
            lookup_kind=None,
        )
        assert result == "task-profile:aide-de-camp"
