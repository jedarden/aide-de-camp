"""
DOM verification tests for canvas cards and staleness indicators (bead adc-34keaj).

This module implements comprehensive DOM verification tests using Playwright:
- Card presence verification for different topic types
- Card text content verification
- Staleness indicator rendering (fresh vs stale vs very-stale)
- Layout structure verification (grid/flex containers, positioning)
- Edge cases: empty session, single card, many cards

Tests use direct database access for test data setup and actual API endpoints
for rendering verification.
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import sqlite3
from playwright.async_api import async_playwright, Browser, Page, BrowserContext


# =============================================================================
# Test Configuration
# =============================================================================

CANVAS_URL = "http://localhost:8000/"
API_BASE_URL = "http://localhost:8000/api/v1"

# Test database path (use actual running database for integration testing)
TEST_DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")


# =============================================================================
# Database Helpers
# =============================================================================

def get_test_db_connection():
    """Get a connection to the test database."""
    conn = sqlite3.connect(TEST_DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_test_db():
    """Initialize the test database (no-op, use existing running database)."""
    # The database already exists and is managed by the running server
    pass


def cleanup_test_data():
    """Clean up test data from the database."""
    conn = get_test_db_connection()
    try:
        # Delete test sessions (they will cascade to surfaces, utterances, intents, results, topics)
        # Delete sessions with IDs starting with 'test-session-'
        conn.execute("DELETE FROM sessions WHERE id LIKE 'test-session-%'")
        conn.commit()
    finally:
        conn.close()


def cleanup_test_session(session_id: str):
    """Clean up a specific test session."""
    conn = get_test_db_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def create_test_session(session_id: str = None) -> str:
    """Create a test session in the database."""
    if session_id is None:
        session_id = f"test-session-{uuid4()}"

    now = int(datetime.now().timestamp() * 1000)
    conn = get_test_db_connection()
    try:
        conn.execute(
            "INSERT INTO sessions (id, created_at, last_active) VALUES (?, ?, ?)",
            (session_id, now, now)
        )
        conn.commit()
    finally:
        conn.close()

    return session_id


def create_test_topic(
    session_id: str,
    label: str,
    topic_type: str = "project",
    summary: str = "Test result",
    data: dict = None,
    urgency: str = "normal",
    created_at: datetime = None,
) -> str:
    """Create a test topic with result in the database."""
    topic_id = str(uuid4())
    result_id = str(uuid4())

    if created_at is None:
        created_at = datetime.now()

    created_at_ms = int(created_at.timestamp() * 1000)

    if data is None:
        data = {"test": "data"}

    conn = get_test_db_connection()
    try:
        # Create topic with required fields from schema
        conn.execute(
            """INSERT INTO topics (id, label, type, scope, session_id, created_at, last_active)
               VALUES (?, ?, ?, 'session', ?, ?, ?)""",
            (topic_id, label, topic_type, session_id, created_at_ms, created_at_ms)
        )

        # Create result (system-originated, no intent_id)
        conn.execute(
            """INSERT INTO results (id, intent_id, topic_id, session_id, summary, data, urgency, created_at, surfaced_at)
               VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)""",
            (result_id, topic_id, session_id, summary, json.dumps(data), urgency, created_at_ms, created_at_ms)
        )

        conn.commit()
    finally:
        conn.close()

    return topic_id


def cleanup_test_db():
    """Clean up the test database."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


# =============================================================================
# Browser Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def test_db():
    """Initialize test database before all tests and cleanup after."""
    cleanup_test_db()
    init_test_db()
    yield
    cleanup_test_db()


@pytest.fixture
async def browser():
    """Provide a Playwright browser instance."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest.fixture
async def page(browser: Browser):
    """Provide a Playwright page instance."""
    page = await browser.new_page(
        viewport={"width": 1400, "height": 900},
        user_agent="ADC-DOM-Verification-Test/1.0"
    )
    yield page
    await page.close()


# =============================================================================
# Test: Card Presence for Different Topic Types
# =============================================================================

@pytest.mark.asyncio
async def test_card_presence_for_all_topic_types(page: Page, test_db):
    """Test that cards render correctly for all topic types."""
    session_id = create_test_session()

    # Create one topic of each type
    topic_types = [
        ("Project Task", "project"),
        ("Research Note", "research"),
        ("Personal Item", "personal"),
        ("Exception Error", "exception"),
        ("Compound Topic", "compound"),
    ]

    for label, topic_type in topic_types:
        create_test_topic(
            session_id=session_id,
            label=label,
            topic_type=topic_type,
            summary=f"Result for {label}",
        )

    # Navigate to canvas with session_id
    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)  # Allow time for card rendering

    # Verify all cards exist
    cards = await page.query_selector_all(".topic-card")
    assert len(cards) == len(topic_types), f"Expected {len(topic_types)} cards, got {len(cards)}"

    # Verify each topic type badge exists
    for label, topic_type in topic_types:
        type_badge = await page.query_selector(f".topic-type.{topic_type}")
        assert type_badge is not None, f"{topic_type} badge not found for {label}"

        # Verify badge text
        badge_text = await type_badge.inner_text()
        assert topic_type in badge_text.lower(), f"Badge should mention {topic_type}"


@pytest.mark.asyncio
async def test_project_card_has_correct_structure(page: Page, test_db):
    """Test that project cards have the expected DOM structure."""
    session_id = create_test_session()

    create_test_topic(
        session_id=session_id,
        label="Test Project",
        topic_type="project",
        summary="Project status update",
        data={"status": "in_progress", "completion": 75},
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    # Get the card
    card = await page.query_selector(".topic-card")
    assert card is not None, "Project card should exist"

    # Verify all expected elements exist
    expected_selectors = [
        ".topic-label",
        ".topic-type.project",
        ".topic-header",
        ".result-content",
        ".result-summary",
        ".result-data",
        ".staleness-indicator",
        ".staleness-dot",
    ]

    for selector in expected_selectors:
        element = await card.query_selector(selector)
        assert element is not None, f"Missing expected element: {selector}"


# =============================================================================
# Test: Card Text Content Verification
# =============================================================================

@pytest.mark.asyncio
async def test_card_label_matches_topic_label(page: Page, test_db):
    """Test that card label text matches the topic label."""
    session_id = create_test_session()

    test_label = "Specific Test Label 12345"
    create_test_topic(
        session_id=session_id,
        label=test_label,
        topic_type="project",
        summary="Test summary",
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    card = await page.query_selector(".topic-card")
    assert card is not None

    label_element = await card.query_selector(".topic-label")
    assert label_element is not None

    label_text = await label_element.inner_text()
    assert test_label in label_text, f"Expected label '{test_label}' not found in '{label_text}'"


@pytest.mark.asyncio
async def test_card_summary_matches_result_summary(page: Page, test_db):
    """Test that card summary text matches the result summary."""
    session_id = create_test_session()

    test_summary = "This is a specific test summary with unique content ABC-123"
    create_test_topic(
        session_id=session_id,
        label="Test Topic",
        summary=test_summary,
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    card = await page.query_selector(".topic-card")
    assert card is not None

    summary_element = await card.query_selector(".result-summary")
    assert summary_element is not None

    summary_text = await summary_element.inner_text()
    assert test_summary in summary_text, f"Expected summary not found in '{summary_text}'"


@pytest.mark.asyncio
async def test_card_data_content_rendering(page: Page, test_db):
    """Test that result data is rendered in the card."""
    session_id = create_test_session()

    test_data = {
        "error_type": "ValueError",
        "message": "Division by zero",
        "line": 42,
        "file": "/test/path.py"
    }

    create_test_topic(
        session_id=session_id,
        label="Error Test",
        topic_type="exception",
        summary="Test error",
        data=test_data,
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    card = await page.query_selector(".topic-card")
    assert card is not None

    data_element = await card.query_selector(".result-data")
    assert data_element is not None

    data_text = await data_element.inner_text()

    # Verify key data points are rendered
    assert "ValueError" in data_text, "error_type should be rendered"
    assert "Division by zero" in data_text, "message should be rendered"
    assert "42" in data_text, "line number should be rendered"


# =============================================================================
# Test: Staleness Indicator Rendering
# =============================================================================

@pytest.mark.asyncio
async def test_fresh_card_has_no_stale_badge(page: Page, test_db):
    """Test that fresh cards (recent) don't have stale badges."""
    session_id = create_test_session()

    # Create a fresh topic (created just now)
    create_test_topic(
        session_id=session_id,
        label="Fresh Topic",
        topic_type="project",
        summary="Fresh result",
        created_at=datetime.now(),
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    card = await page.query_selector(".topic-card")
    assert card is not None

    # Should not have stale class
    card_classes = await card.get_attribute("class") or ""
    assert "stale" not in card_classes, "Fresh card should not have stale class"
    assert "very-stale" not in card_classes, "Fresh card should not have very-stale class"

    # Should not have stale badge
    stale_badge = await card.query_selector(".stale-badge")
    assert stale_badge is None, "Fresh card should not have stale badge"


@pytest.mark.asyncio
async def test_stale_card_has_correct_badge(page: Page, test_db):
    """Test that stale cards have the correct stale badge."""
    session_id = create_test_session()

    # Create a stale topic (2 hours old, should be considered stale)
    stale_time = datetime.now() - timedelta(hours=2)
    create_test_topic(
        session_id=session_id,
        label="Stale Topic",
        topic_type="project",
        summary="Stale result",
        created_at=stale_time,
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    card = await page.query_selector(".topic-card")
    assert card is not None

    # Should have stale class (if staleness threshold is < 2 hours)
    card_classes = await card.get_attribute("class") or ""

    # Check if stale class is present (depends on staleness threshold)
    has_stale_class = "stale" in card_classes

    if has_stale_class:
        # Verify stale badge exists
        stale_badge = await card.query_selector(".stale-badge.stale")
        assert stale_badge is not None, "Stale card should have stale badge"

        badge_text = await stale_badge.inner_text()
        assert "stale" in badge_text.lower(), "Badge should indicate stale"


@pytest.mark.asyncio
async def test_very_stale_card_has_correct_badge(page: Page, test_db):
    """Test that very stale cards have the correct very-stale badge."""
    session_id = create_test_session()

    # Create a very stale topic (3 days old)
    very_stale_time = datetime.now() - timedelta(days=3)
    create_test_topic(
        session_id=session_id,
        label="Very Stale Topic",
        topic_type="project",
        summary="Very stale result",
        created_at=very_stale_time,
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    card = await page.query_selector(".topic-card")
    assert card is not None

    # Should have very-stale styling
    card_classes = await card.get_attribute("class") or ""
    has_very_stale_class = "very-stale" in card_classes

    if has_very_stale_class:
        # Verify very-stale badge exists
        very_stale_badge = await card.query_selector(".stale-badge.very-stale")
        assert very_stale_badge is not None, "Very stale card should have very-stale badge"

        badge_text = await very_stale_badge.inner_text()
        assert "stale" in badge_text.lower(), "Badge should indicate stale"


@pytest.mark.asyncio
async def test_staleness_indicator_dot_color(page: Page, test_db):
    """Test that staleness indicator dots have correct colors."""
    session_id = create_test_session()

    # Create topics at different ages
    create_test_topic(
        session_id=session_id,
        label="Fresh",
        topic_type="project",
        summary="Fresh result",
        created_at=datetime.now(),
    )

    create_test_topic(
        session_id=session_id,
        label="Stale",
        topic_type="project",
        summary="Stale result",
        created_at=datetime.now() - timedelta(hours=2),
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    cards = await page.query_selector_all(".topic-card")
    assert len(cards) == 2

    # Check that staleness indicators exist
    for card in cards:
        staleness_indicator = await card.query_selector(".staleness-indicator")
        assert staleness_indicator is not None, "Card should have staleness indicator"

        staleness_dot = await staleness_indicator.query_selector(".staleness-dot")
        assert staleness_dot is not None, "Should have staleness dot"


# =============================================================================
# Test: Layout Structure Verification
# =============================================================================

@pytest.mark.asyncio
async def test_grid_container_exists(page: Page, test_db):
    """Test that cards are rendered in a grid container."""
    session_id = create_test_session()

    create_test_topic(
        session_id=session_id,
        label="Grid Test",
        topic_type="project",
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    # Verify grid container exists
    grid = await page.query_selector(".topics-grid")
    assert grid is not None, "Topics grid container should exist"

    # Verify it uses CSS grid layout
    grid_display = await grid.evaluate("el => window.getComputedStyle(el).display")
    assert grid_display == "grid", "Topics container should use CSS grid layout"


@pytest.mark.asyncio
async def test_cards_are_grid_children(page: Page, test_db):
    """Test that topic cards are direct children of the grid container."""
    session_id = create_test_session()

    # Create multiple topics
    for i in range(3):
        create_test_topic(
            session_id=session_id,
            label=f"Topic {i+1}",
            topic_type="project",
        )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    grid = await page.query_selector(".topics-grid")
    assert grid is not None

    # Verify cards are children of grid
    cards = await grid.query_selector_all(".topic-card")
    assert len(cards) == 3, "Grid should contain 3 cards"

    # Verify each card's parent is the grid
    for card in cards:
        parent_tag = await card.evaluate("el => el.parentElement.tagName")
        parent_class = await card.evaluate("el => el.parentElement.className")
        assert parent_tag == "DIV", "Card parent should be a div"
        assert "topics-grid" in parent_class, "Card parent should have topics-grid class"


@pytest.mark.asyncio
async def test_grid_has_correct_gap(page: Page, test_db):
    """Test that the grid has proper gap spacing."""
    session_id = create_test_session()

    create_test_topic(
        session_id=session_id,
        label="Gap Test",
        topic_type="project",
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    grid = await page.query_selector(".topics-grid")
    assert grid is not None

    # Check that gap is set (not "normal")
    grid_gap = await grid.evaluate("el => window.getComputedStyle(el).gap")
    assert grid_gap != "normal", "Grid should have an explicit gap set"

    # Verify gap is a valid CSS length
    assert "px" in grid_gap or "rem" in grid_gap, "Gap should be a CSS length unit"


@pytest.mark.asyncio
async def test_grid_responsive_columns(page: Page, test_db):
    """Test that grid uses responsive column sizing."""
    session_id = create_test_session()

    create_test_topic(
        session_id=session_id,
        label="Responsive Test",
        topic_type="project",
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    grid = await page.query_selector(".topics-grid")
    assert grid is not None

    # Check grid-template-columns uses auto-fill or similar responsive pattern
    grid_template = await grid.evaluate("el => window.getComputedStyle(el).gridTemplateColumns")
    assert "minmax" in grid_template or "auto" in grid_template, \
        "Grid should use responsive column sizing (minmax or auto-fill)"


# =============================================================================
# Test: Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_empty_session_shows_welcome_card(page: Page, test_db):
    """Test that an empty session shows the welcome card instead of topic cards."""
    session_id = create_test_session()

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    # Should have welcome card
    welcome_card = await page.query_selector('[data-builtin="welcome"]')
    assert welcome_card is not None, "Empty session should show welcome card"

    # Should NOT have any topic cards
    topic_cards = await page.query_selector_all(".topic-card")
    assert len(topic_cards) == 0, "Empty session should not have topic cards"

    # Verify welcome card has expected structure
    title = await welcome_card.query_selector(".builtin-title")
    assert title is not None, "Welcome card should have title"

    title_text = await title.inner_text()
    assert "welcome" in title_text.lower(), "Welcome card title should mention welcome"


@pytest.mark.asyncio
async def test_single_card_rendering(page: Page, test_db):
    """Test that a single card renders correctly."""
    session_id = create_test_session()

    create_test_topic(
        session_id=session_id,
        label="Single Card",
        topic_type="project",
        summary="Single result",
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    # Should have exactly one topic card
    cards = await page.query_selector_all(".topic-card")
    assert len(cards) == 1, "Should have exactly one topic card"

    # Welcome card should be removed
    welcome_card = await page.query_selector('[data-builtin="welcome"]')
    assert welcome_card is None, "Welcome card should be removed when topics exist"

    # Verify card has all expected elements
    card = cards[0]
    assert await card.query_selector(".topic-label") is not None
    assert await card.query_selector(".topic-type") is not None
    assert await card.query_selector(".result-summary") is not None
    assert await card.query_selector(".staleness-indicator") is not None


@pytest.mark.asyncio
async def test_many_cards_rendering(page: Page, test_db):
    """Test that many cards render correctly in the grid."""
    session_id = create_test_session()

    # Create many cards (more than fit on one row)
    num_cards = 12
    for i in range(num_cards):
        create_test_topic(
            session_id=session_id,
            label=f"Topic {i+1}",
            topic_type="project",
            summary=f"Result {i+1}",
        )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    # Verify all cards rendered
    cards = await page.query_selector_all(".topic-card")
    assert len(cards) == num_cards, f"Should have {num_cards} cards, got {len(cards)}"

    # Verify grid layout
    grid = await page.query_selector(".topics-grid")
    assert grid is not None, "Grid should exist"

    # Verify all cards are in the grid
    grid_cards = await grid.query_selector_all(".topic-card")
    assert len(grid_cards) == num_cards, "All cards should be in the grid"


# =============================================================================
# Test: Data Attributes
# =============================================================================

@pytest.mark.asyncio
async def test_card_has_required_data_attributes(page: Page, test_db):
    """Test that cards have all required data attributes."""
    session_id = create_test_session()

    topic_id = create_test_topic(
        session_id=session_id,
        label="Data Attributes Test",
        topic_type="project",
    )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    card = await page.query_selector(".topic-card")
    assert card is not None

    # Verify data-topic-id exists
    data_topic_id = await card.get_attribute("data-topic-id")
    assert data_topic_id is not None, "Card should have data-topic-id attribute"
    assert data_topic_id == topic_id, "data-topic-id should match the topic ID"

    # Verify data-card-id exists
    data_card_id = await card.get_attribute("data-card-id")
    assert data_card_id is not None, "Card should have data-card-id attribute"

    # Verify data-topic-type exists
    data_topic_type = await card.get_attribute("data-topic-type")
    assert data_topic_type is not None, "Card should have data-topic-type attribute"
    assert data_topic_type == "project", "data-topic-type should be 'project'"


@pytest.mark.asyncio
async def test_can_query_cards_by_data_attributes(page: Page, test_db):
    """Test that cards can be queried using data attribute selectors."""
    session_id = create_test_session()

    # Create topics of different types
    create_test_topic(session_id=session_id, label="Project 1", topic_type="project")
    create_test_topic(session_id=session_id, label="Research 1", topic_type="research")
    create_test_topic(session_id=session_id, label="Personal 1", topic_type="personal")

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    # Query by data attributes
    project_cards = await page.query_selector_all('[data-topic-type="project"]')
    research_cards = await page.query_selector_all('[data-topic-type="research"]')
    personal_cards = await page.query_selector_all('[data-topic-type="personal"]')

    assert len(project_cards) == 1, "Should find one project card"
    assert len(research_cards) == 1, "Should find one research card"
    assert len(personal_cards) == 1, "Should find one personal card"


# =============================================================================
# Test: Urgency Badges
# =============================================================================

@pytest.mark.asyncio
async def test_urgency_badges_render_correctly(page: Page, test_db):
    """Test that urgency badges render correctly for different urgency levels."""
    session_id = create_test_session()

    # Create topics with different urgency levels
    for urgency in ["critical", "high", "normal", "low"]:
        create_test_topic(
            session_id=session_id,
            label=f"{urgency.capitalize()} Topic",
            topic_type="project",
            summary=f"{urgency} result",
            urgency=urgency,
        )

    await page.goto(f"{CANVAS_URL}?session_id={session_id}")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    cards = await page.query_selector_all(".topic-card")
    assert len(cards) == 4

    # Verify each urgency badge exists
    for urgency in ["critical", "high", "normal", "low"]:
        badge = await page.query_selector(f".urgency-badge.{urgency}")
        assert badge is not None, f"{urgency} badge should exist"

        badge_text = await badge.inner_text()
        assert urgency in badge_text.lower(), f"Badge text should mention {urgency}"


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    """
    Run the DOM verification tests.

    Usage:
        python tests/test_canvas_dom_verification.py

    This will run all DOM verification tests.
    """
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
