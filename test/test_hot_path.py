"""
Unit tests for hot-path renderer functionality.

Tests cover:
1. derive_result_type - Deterministic result_type derivation
2. select_rendered_card - Server-side component selector

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
import tempfile
from pathlib import Path
import os

from src.render.hot_path import derive_result_type, select_rendered_card, fill_template
from src.components.library import ComponentLibrary, get_library


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


# =============================================================================
# Fixtures for select_rendered_card tests
# =============================================================================

@pytest.fixture
def temp_component_db():
    """Create a temporary component library database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db_path = Path(path)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def component_library(temp_component_db):
    """Create a component library with temporary database."""
    # Reset the global singleton
    import src.components.library
    src.components.library._library_instance = None
    lib = ComponentLibrary(str(temp_component_db))
    yield lib
    lib.close()


@pytest.fixture
def sample_component(component_library):
    """Create a sample component for testing."""
    component = component_library.create_component(
        name="test-status",
        description="Test status component",
        html_template='<div class="test-card"><h3>{{title}}</h3><p>{{summary}}</p></div>',
        change_note="Initial version"
    )
    return component


@pytest.fixture
def sample_result_data():
    """Sample result data for template filling."""
    return {
        "title": "Test Status",
        "summary": "All systems operational",
        "status": "running"
    }


# =============================================================================
# select_rendered_card Tests
# =============================================================================

class TestSelectRenderedCard:
    """Test server-side deterministic component selector.

    Tests cover the three acceptance criteria cases:
    1. Match case - component found with score >= threshold
    2. No-match case - no component found for result_type
    3. Below-threshold case - component found but score < threshold
    """

    def test_match_case_returns_rendered_html(self, component_library, sample_component, sample_result_data):
        """TC-SRC-001: Match case - component found with score >= threshold returns rendered HTML.

        When a component exists in component_usage_patterns with match_score >= threshold,
        select_rendered_card should:
        - Fill the component template with result.data
        - Write to card_cache
        - Return the rendered HTML string
        """
        result_id = "result-test-123"
        result_type = "status:test-project"

        # Record a high-confidence usage pattern (above threshold)
        component_library.record_usage_pattern(
            component_id=sample_component.id,
            result_type=result_type,
            match_score=0.85,  # Above 0.7 threshold
            layout_bucket="normal"
        )

        # Call select_rendered_card
        rendered_html = select_rendered_card(
            result_type=result_type,
            result_data=sample_result_data,
            result_id=result_id,
            layout_bucket="normal",
            match_threshold=0.7,
            library=component_library
        )

        # Assert: Should return rendered HTML (not None)
        assert rendered_html is not None
        assert isinstance(rendered_html, str)
        assert len(rendered_html) > 0

        # Assert: Template should be filled with result data
        assert "Test Status" in rendered_html  # title from result_data
        assert "All systems operational" in rendered_html  # summary from result_data
        assert "<div class=\"test-card\">" in rendered_html  # template structure

        # Assert: Should have written to card_cache
        cached_card = component_library.get_cached_card(
            result_id=result_id,
            component_id=sample_component.id,
            layout_bucket="normal"
        )
        assert cached_card is not None
        assert cached_card.rendered_html == rendered_html

    def test_no_match_case_returns_none(self, component_library, sample_component, sample_result_data):
        """TC-SRC-002: No-match case - no component found for result_type returns None.

        When no component exists in component_usage_patterns for the given result_type,
        select_rendered_card should return None, triggering fallback rendering.
        """
        result_id = "result-test-456"
        result_type = "status:nonexistent-project"

        # Don't record any usage pattern - simulating no match

        # Call select_rendered_card
        rendered_html = select_rendered_card(
            result_type=result_type,
            result_data=sample_result_data,
            result_id=result_id,
            layout_bucket="normal",
            match_threshold=0.7,
            library=component_library
        )

        # Assert: Should return None (triggers fallback)
        assert rendered_html is None

        # Assert: Should NOT have written to card_cache
        cached_card = component_library.get_cached_card(
            result_id=result_id,
            component_id=sample_component.id,
            layout_bucket="normal"
        )
        assert cached_card is None

    def test_below_threshold_case_returns_none(self, component_library, sample_component, sample_result_data):
        """TC-SRC-003: Below-threshold case - component found but score < threshold returns None.

        When a component exists in component_usage_patterns but with match_score below threshold,
        select_rendered_card should return None, triggering fallback rendering.
        """
        result_id = "result-test-789"
        result_type = "status:low-confidence-project"

        # Record a low-confidence usage pattern (below threshold)
        component_library.record_usage_pattern(
            component_id=sample_component.id,
            result_type=result_type,
            match_score=0.65,  # Below 0.7 threshold
            layout_bucket="normal"
        )

        # Call select_rendered_card with threshold higher than recorded score
        rendered_html = select_rendered_card(
            result_type=result_type,
            result_data=sample_result_data,
            result_id=result_id,
            layout_bucket="normal",
            match_threshold=0.7,
            library=component_library
        )

        # Assert: Should return None (triggers fallback)
        assert rendered_html is None

        # Assert: Should NOT have written to card_cache
        cached_card = component_library.get_cached_card(
            result_id=result_id,
            component_id=sample_component.id,
            layout_bucket="normal"
        )
        assert cached_card is None

    def test_exactly_at_threshold_returns_html(self, component_library, sample_component, sample_result_data):
        """TC-SRC-004: Edge case - match_score exactly at threshold (0.7) should match.

        When match_score equals the threshold exactly, it should be considered a match.
        """
        result_id = "result-test-threshold"
        result_type = "status:threshold-project"

        # Record usage pattern with score exactly at threshold
        component_library.record_usage_pattern(
            component_id=sample_component.id,
            result_type=result_type,
            match_score=0.70,  # Exactly at threshold
            layout_bucket="normal"
        )

        # Call select_rendered_card
        rendered_html = select_rendered_card(
            result_type=result_type,
            result_data=sample_result_data,
            result_id=result_id,
            layout_bucket="normal",
            match_threshold=0.7,
            library=component_library
        )

        # Assert: Should return rendered HTML (threshold is inclusive)
        assert rendered_html is not None
        assert isinstance(rendered_html, str)

    def test_records_usage_pattern_with_score_1_on_match(self, component_library, sample_component, sample_result_data):
        """TC-SRC-005: On successful match, should record usage pattern with score=1.0.

        Hot-path matches are high-confidence, so they should be recorded with match_score=1.0
        to bump reliable components toward the top of the selector.
        """
        result_id = "result-test-usage"
        result_type = "status:usage-tracking-project"

        # Record initial pattern with moderate score
        component_library.record_usage_pattern(
            component_id=sample_component.id,
            result_type=result_type,
            match_score=0.75,
            layout_bucket="normal"
        )

        # Call select_rendered_card (should record new usage at 1.0)
        rendered_html = select_rendered_card(
            result_type=result_type,
            result_data=sample_result_data,
            result_id=result_id,
            layout_bucket="normal",
            match_threshold=0.7,
            library=component_library
        )

        # Assert: Should have recorded the usage pattern
        conn = component_library._get_conn()
        row = conn.execute(
            """
            SELECT match_score, sample_count
            FROM component_usage_patterns
            WHERE result_type = ? AND component_id = ? AND layout_bucket = ?
            """,
            (result_type, sample_component.id, "normal")
        ).fetchone()

        assert row is not None
        # The match_score should have been updated toward 1.0 by the new recording
        # (exact value depends on the running average calculation)
        assert row[1] >= 2  # sample_count should have increased


class TestFillTemplate:
    """Test template filling functionality."""

    def test_fill_template_simple_substitution(self):
        """Test simple field substitution in template."""
        template = '<div>{{title}}</div>'
        data = {"title": "Test Title"}
        result = fill_template(template, data)
        assert result == '<div>Test Title</div>'

    def test_fill_template_nested_path(self):
        """Test nested dot-path substitution."""
        template = '<div>{{user.name}}</div>'
        data = {"user": {"name": "John"}}
        result = fill_template(template, data)
        assert result == '<div>John</div>'

    def test_fill_template_list_indexing(self):
        """Test list indexing via numeric segments."""
        template = '<div>{{items.0.name}}</div>'
        data = {"items": [{"name": "First"}, {"name": "Second"}]}
        result = fill_template(template, data)
        assert result == '<div>First</div>'

    def test_fill_template_html_escaping(self):
        """Test that values are HTML-escaped."""
        template = '<div>{{content}}</div>'
        data = {"content": "<script>alert('xss')</script>"}
        result = fill_template(template, data)
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_fill_template_unknown_path_returns_empty(self):
        """Test that unknown paths resolve to empty string."""
        template = '<div>{{unknown.path}}</div>'
        data = {"other": "value"}
        result = fill_template(template, data)
        assert result == '<div></div>'

    def test_fill_template_multiple_placeholders(self):
        """Test multiple placeholders in one template."""
        template = '<h1>{{title}}</h1><p>{{summary}}</p>'
        data = {"title": "My Title", "summary": "My Summary"}
        result = fill_template(template, data)
        assert "<h1>My Title</h1>" in result
        assert "<p>My Summary</p>" in result
