"""
Headless DOM test for canvas granularity: one card per (topic, result_type) pair.

Acceptance criteria:
- Status then brainstorm on one topic -> two coexisting cards (different card_ids)
- lookup:logs and lookup:config cards coexist (different card_ids)
- Card dataset includes card_id attribute for in-place updates

This test uses the canvas DOM runner to verify the rendering contract headlessly.
"""
import pytest
from tests.e2e.canvas_render import node_available, render_cards, render_card

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


def _topic_card_data(
    card_id: str = "topic-123::status:test-project",
    topic_id: str = "topic-123",
    topic_label: str = "Test Project",
    topic_type: str = "project",
    result_type: str = "status:test-project",
    summary: str = "Test summary",
    staleness_seconds: int = 5,
) -> dict:
    """Build topic card data matching GET /api/v1/sessions/{id}/topics response."""
    return {
        "card_id": card_id,
        "topic": {
            "id": topic_id,
            "label": topic_label,
            "type": topic_type,
        },
        "result_type": result_type,
        "latest_result": {
            "summary": summary,
            "urgency": "normal",
        },
        "staleness": {
            "seconds": staleness_seconds,
            "level": "fresh",
        },
    }


class TestCanvasGranularity:
    """Test canvas granularity: one card per (topic, result_type) pair."""

    def test_card_has_card_id_dataset_attribute(self):
        """Each rendered card should have a data-card-id attribute."""
        card_data = _topic_card_data(
            card_id="topic-123::status:test-project",
            result_type="status:test-project",
        )
        result = render_card(card_data)

        assert "cardId" in result["dataset"], \
            "Card should have cardId in dataset for in-place updates"
        assert result["dataset"]["cardId"] == "topic-123::status:test-project", \
            "cardId should match the card_id from the response"

    def test_status_and_brainstorm_have_different_card_ids(self):
        """Status and brainstorm cards on the same topic should have different card_ids."""
        topic_id = "topic-123"
        cards = [
            _topic_card_data(
                card_id=f"{topic_id}::status:test-project",
                topic_id=topic_id,
                result_type="status:test-project",
                summary="Status: All systems go",
            ),
            _topic_card_data(
                card_id=f"{topic_id}::brainstorm:test-project",
                topic_id=topic_id,
                result_type="brainstorm:test-project",
                summary="Brainstorm: Consider these options...",
            ),
        ]

        results = render_cards(cards)

        assert len(results) == 2, "Should render two separate cards"
        card_ids = {r["dataset"]["cardId"] for r in results}
        assert len(card_ids) == 2, "Each card should have a unique card_id"
        assert "topic-123::status:test-project" in card_ids
        assert "topic-123::brainstorm:test-project" in card_ids

    def test_lookup_logs_and_config_have_different_card_ids(self):
        """Lookup logs and config cards for the same topic should have different card_ids."""
        topic_id = "topic-456"
        cards = [
            _topic_card_data(
                card_id=f"{topic_id}::lookup:logs:test-project",
                topic_id=topic_id,
                result_type="lookup:logs:test-project",
                summary="Logs: Recent pod activity",
            ),
            _topic_card_data(
                card_id=f"{topic_id}::lookup:config:test-project",
                topic_id=topic_id,
                result_type="lookup:config:test-project",
                summary="Config: Deployment settings",
            ),
        ]

        results = render_cards(cards)

        assert len(results) == 2, "Should render two separate cards"
        card_ids = {r["dataset"]["cardId"] for r in results}
        assert len(card_ids) == 2, "Each card should have a unique card_id"
        assert "topic-456::lookup:logs:test-project" in card_ids
        assert "topic-456::lookup:config:test-project" in card_ids

    def test_both_cards_have_same_topic_id(self):
        """Different result_types on the same topic should share the same topic_id."""
        topic_id = "topic-789"
        cards = [
            _topic_card_data(
                card_id=f"{topic_id}::status:test-project",
                topic_id=topic_id,
                result_type="status:test-project",
            ),
            _topic_card_data(
                card_id=f"{topic_id}::brainstorm:test-project",
                topic_id=topic_id,
                result_type="brainstorm:test-project",
            ),
        ]

        results = render_cards(cards)

        topic_ids = {r["dataset"]["topicId"] for r in results}
        assert len(topic_ids) == 1, "Both cards should share the same topic_id"
        assert topic_id in topic_ids

    def test_in_place_update_same_card_id(self):
        """Second result with same (topic, result_type) should use same card_id."""
        topic_id = "topic-999"
        result_type = "status:test-project"
        card_id = f"{topic_id}::{result_type}"

        # First result
        first_card = _topic_card_data(
            card_id=card_id,
            topic_id=topic_id,
            result_type=result_type,
            summary="Status: Running",
        )

        # Second result with same topic and result_type (simulating in-place update)
        second_card = _topic_card_data(
            card_id=card_id,  # Same card_id = same (topic, result_type) pair
            topic_id=topic_id,
            result_type=result_type,
            summary="Status: Updated",  # Different content
        )

        first_render = render_card(first_card)
        second_render = render_card(second_card)

        # Both should have the same card_id
        assert first_render["dataset"]["cardId"] == card_id
        assert second_render["dataset"]["cardId"] == card_id

        # Both should have the same topic_id
        assert first_render["dataset"]["topicId"] == topic_id
        assert second_render["dataset"]["topicId"] == topic_id


if __name__ == "__main__":
    # Run tests directly
    import sys
    pytest.main([__file__, "-v", "-s"] + sys.argv[1:])
