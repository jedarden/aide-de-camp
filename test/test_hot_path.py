"""
Unit tests for derive_result_type in the hot-path renderer.

Tests cover all derivation scenarios and edge cases for the deterministic
result_type derivation that powers component selection.

Derivation branches:
- intent-derived: "{intent_type}:{project_slug}"
- lookup with kind: "lookup:{lookup_kind}:{project_slug}"
- monitoring: "monitoring:{project_slug}"

Edge cases:
- None values for intent_type, project_slug, lookup_kind
- Empty strings
- Missing fields
"""

import pytest

from src.render.hot_path import derive_result_type


# =============================================================================
# Monitoring Branch Tests
# =============================================================================

class TestMonitoringBranch:
    """Test the monitoring intent branch: 'monitoring:{slug}'"""

    def test_monitoring_with_project_slug(self):
        """Monitoring intent with project_slug should produce 'monitoring:{slug}'"""
        result = derive_result_type(
            intent_type="monitoring",
            project_slug="ibkr-mcp"
        )
        assert result == "monitoring:ibkr-mcp"

    def test_monitoring_without_project_slug(self):
        """Monitoring intent without project_slug should default to 'monitoring:general'"""
        result = derive_result_type(
            intent_type="monitoring",
            project_slug=None
        )
        assert result == "monitoring:general"

    def test_monitoring_ignores_lookup_kind(self):
        """Monitoring branch should ignore lookup_kind even if provided"""
        result = derive_result_type(
            intent_type="monitoring",
            project_slug="ibkr-mcp",
            lookup_kind="logs"
        )
        assert result == "monitoring:ibkr-mcp"

    def test_monitoring_empty_project_slug(self):
        """Monitoring with empty project_slug should become 'monitoring:general'"""
        # Empty string is falsy but not None - should still use "general"
        result = derive_result_type(
            intent_type="monitoring",
            project_slug=""
        )
        assert result == "monitoring:general"


# =============================================================================
# Lookup Branch Tests
# =============================================================================

class TestLookupBranch:
    """Test the lookup intent branch with lookup_kind: 'lookup:{kind}:{slug}'"""

    def test_lookup_with_kind_and_project(self):
        """Lookup with kind and project should produce 'lookup:{kind}:{slug}'"""
        result = derive_result_type(
            intent_type="lookup",
            project_slug="ibkr-mcp",
            lookup_kind="logs"
        )
        assert result == "lookup:logs:ibkr-mcp"

    def test_lookup_config_kind(self):
        """Different lookup kinds should produce different result_types"""
        result = derive_result_type(
            intent_type="lookup",
            project_slug="ibkr-mcp",
            lookup_kind="config"
        )
        assert result == "lookup:config:ibkr-mcp"

    def test_lookup_without_project_slug(self):
        """Lookup without project_slug should default to 'lookup:{kind}:general'"""
        result = derive_result_type(
            intent_type="lookup",
            project_slug=None,
            lookup_kind="logs"
        )
        assert result == "lookup:logs:general"

    def test_lookup_with_empty_project_slug(self):
        """Lookup with empty project_slug should use 'general'"""
        result = derive_result_type(
            intent_type="lookup",
            project_slug="",
            lookup_kind="logs"
        )
        assert result == "lookup:logs:general"

    def test_lookup_without_kind_falls_to_default_branch(self):
        """Lookup without lookup_kind should fall to default branch: 'lookup:{slug}'"""
        result = derive_result_type(
            intent_type="lookup",
            project_slug="ibkr-mcp",
            lookup_kind=None
        )
        assert result == "lookup:ibkr-mcp"


# =============================================================================
# Default Intent Branch Tests
# =============================================================================

class TestDefaultIntentBranch:
    """Test the default intent branch: '{intent_type}:{slug}'"""

    def test_status_intent_with_project(self):
        """Status intent with project should produce 'status:{slug}'"""
        result = derive_result_type(
            intent_type="status",
            project_slug="options-pipeline"
        )
        assert result == "status:options-pipeline"

    def test_action_intent_with_project(self):
        """Action intent with project should produce 'action:{slug}'"""
        result = derive_result_type(
            intent_type="action",
            project_slug="botburrow"
        )
        assert result == "action:botburrow"

    def test_research_intent_with_project(self):
        """Research intent with project should produce 'research:{slug}'"""
        result = derive_result_type(
            intent_type="research",
            project_slug="nixos-asterisk"
        )
        assert result == "research:nixos-asterisk"

    def test_intent_without_project_slug(self):
        """Any intent without project_slug should default to '{itype}:general'"""
        result = derive_result_type(
            intent_type="status",
            project_slug=None
        )
        assert result == "status:general"

    def test_intent_with_empty_project_slug(self):
        """Any intent with empty project_slug should use 'general'"""
        result = derive_result_type(
            intent_type="action",
            project_slug=""
        )
        assert result == "action:general"


# =============================================================================
# Per-Thread Granularity Tests
# =============================================================================

class TestPerThreadGranularity:
    """Test that result_type is per-thread, not per-source."""

    def test_same_intent_different_projects_produce_different_keys(self):
        """Same intent_type but different projects should produce different result_types."""
        result1 = derive_result_type(
            intent_type="status",
            project_slug="project-a"
        )
        result2 = derive_result_type(
            intent_type="status",
            project_slug="project-b"
        )
        assert result1 != result2
        assert result1 == "status:project-a"
        assert result2 == "status:project-b"

    def test_lookup_different_kinds_produce_different_keys(self):
        """Same project but different lookup kinds should produce different result_types."""
        result1 = derive_result_type(
            intent_type="lookup",
            project_slug="ibkr-mcp",
            lookup_kind="logs"
        )
        result2 = derive_result_type(
            intent_type="lookup",
            project_slug="ibkr-mcp",
            lookup_kind="config"
        )
        assert result1 != result2
        assert result1 == "lookup:logs:ibkr-mcp"
        assert result2 == "lookup:config:ibkr-mcp"

    def test_different_intents_same_project_produce_different_keys(self):
        """Different intent_types for same project should produce different result_types."""
        result1 = derive_result_type(
            intent_type="status",
            project_slug="shared-project"
        )
        result2 = derive_result_type(
            intent_type="action",
            project_slug="shared-project"
        )
        assert result1 != result2
        assert result1 == "status:shared-project"
        assert result2 == "action:shared-project"


# =============================================================================
# Determinism Tests
# =============================================================================

class TestDeterminism:
    """Test that derive_result_type is deterministic."""

    def test_determinism_monitoring(self):
        """Same inputs to monitoring branch should always produce same output."""
        inputs = {
            "intent_type": "monitoring",
            "project_slug": "test-project",
            "lookup_kind": None
        }
        result1 = derive_result_type(**inputs)
        result2 = derive_result_type(**inputs)
        result3 = derive_result_type(**inputs)
        assert result1 == result2 == result3 == "monitoring:test-project"

    def test_determinism_lookup(self):
        """Same inputs to lookup branch should always produce same output."""
        inputs = {
            "intent_type": "lookup",
            "project_slug": "ibkr-mcp",
            "lookup_kind": "logs"
        }
        result1 = derive_result_type(**inputs)
        result2 = derive_result_type(**inputs)
        result3 = derive_result_type(**inputs)
        assert result1 == result2 == result3 == "lookup:logs:ibkr-mcp"

    def test_determinism_default(self):
        """Same inputs to default branch should always produce same output."""
        inputs = {
            "intent_type": "status",
            "project_slug": "options-pipeline",
            "lookup_kind": None
        }
        result1 = derive_result_type(**inputs)
        result2 = derive_result_type(**inputs)
        result3 = derive_result_type(**inputs)
        assert result1 == result2 == result3 == "status:options-pipeline"

    def test_determinism_with_none_values(self):
        """Determinism with None values should be consistent."""
        inputs = {
            "intent_type": None,
            "project_slug": None,
            "lookup_kind": None
        }
        result1 = derive_result_type(**inputs)
        result2 = derive_result_type(**inputs)
        assert result1 == result2 == "status:general"


# =============================================================================
# Edge Cases and None Value Handling
# =============================================================================

class TestEdgeCases:
    """Test edge cases with None values, empty strings, and missing fields."""

    def test_all_none_values(self):
        """All None values should produce 'status:general'"""
        result = derive_result_type(
            intent_type=None,
            project_slug=None,
            lookup_kind=None
        )
        assert result == "status:general"

    def test_none_intent_type_with_project(self):
        """None intent_type with project_slug should use 'status' as default."""
        result = derive_result_type(
            intent_type=None,
            project_slug="my-project",
            lookup_kind=None
        )
        assert result == "status:my-project"

    def test_none_intent_type_without_project(self):
        """None intent_type without project_slug should produce 'status:general'."""
        result = derive_result_type(
            intent_type=None,
            project_slug=None,
            lookup_kind=None
        )
        assert result == "status:general"

    def test_empty_intent_type_string(self):
        """Empty string intent_type should be treated as falsy, defaulting to 'status'."""
        result = derive_result_type(
            intent_type="",
            project_slug="test-project",
            lookup_kind=None
        )
        # Empty string is falsy, so it defaults to "status"
        assert result == "status:test-project"

    def test_empty_all_strings(self):
        """All empty strings should produce 'status:general'."""
        result = derive_result_type(
            intent_type="",
            project_slug="",
            lookup_kind=""
        )
        assert result == "status:general"

    def test_lookup_with_none_kind(self):
        """Lookup with None lookup_kind should fall to default branch."""
        result = derive_result_type(
            intent_type="lookup",
            project_slug="test-project",
            lookup_kind=None
        )
        assert result == "lookup:test-project"

    def test_lookup_with_empty_kind(self):
        """Lookup with empty string lookup_kind should fall to default branch."""
        result = derive_result_type(
            intent_type="lookup",
            project_slug="test-project",
            lookup_kind=""
        )
        assert result == "lookup:test-project"

    def test_case_sensitivity(self):
        """result_type should be case-sensitive."""
        result1 = derive_result_type(
            intent_type="status",
            project_slug="MyProject"
        )
        result2 = derive_result_type(
            intent_type="status",
            project_slug="myproject"
        )
        # These should be different (case-sensitive)
        assert result1 != result2

    def test_special_characters_in_slug(self):
        """Special characters in project_slug should be preserved."""
        result = derive_result_type(
            intent_type="status",
            project_slug="my-project_v2"
        )
        assert result == "status:my-project_v2"

    def test_numeric_string_intent(self):
        """Numeric string as intent_type should be preserved."""
        result = derive_result_type(
            intent_type="123",
            project_slug="test"
        )
        assert result == "123:test"


# =============================================================================
# Real-World Scenarios
# =============================================================================

class TestRealWorldScenarios:
    """Test real-world usage scenarios from the codebase."""

    def test_ambient_monitoring_row(self):
        """Test ambient monitoring row creation from monitoring/ambient.py"""
        result = derive_result_type(
            intent_type="monitoring",
            project_slug="botburrow"
        )
        assert result == "monitoring:botburrow"

    def test_intent_router_status(self):
        """Test intent router status classification"""
        result = derive_result_type(
            intent_type="status",
            project_slug="options-pipeline"
        )
        assert result == "status:options-pipeline"

    def test_intent_router_lookup_logs(self):
        """Test intent router lookup with logs kind"""
        result = derive_result_type(
            intent_type="lookup",
            project_slug="ibkr-mcp",
            lookup_kind="logs"
        )
        assert result == "lookup:logs:ibkr-mcp"

    def test_general_status_no_project(self):
        """Test general status without specific project"""
        result = derive_result_type(
            intent_type="status",
            project_slug=None
        )
        assert result == "status:general"

    def test_stuck_card_preserves_original_result_type(self):
        """Verify stuck escalation preserves original result_type by re-deriving.

        When a card becomes stuck, the escalate handler re-derives result_type
        from the original intent classification (not the "stuck" state).
        """
        # Original status classification
        original_result = derive_result_type(
            intent_type="status",
            project_slug="options-pipeline"
        )
        assert original_result == "status:options-pipeline"

        # Re-derivation should produce the same result
        rederived = derive_result_type(
            intent_type="status",
            project_slug="options-pipeline"
        )
        assert rederived == original_result
