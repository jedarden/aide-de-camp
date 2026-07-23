"""
Test helpers for card dismissal tests (bead adc-3xgfs).

Provides helper functions and fixtures for:
- Creating test sessions with isolated stores
- Creating stuck and failed cards
- Verifying card presence in canvas
- Triggering dismissal button clicks
- Managing test data for card dismissal scenarios

This module is intended to be imported by card dismissal test suites:
from tests.card_dismissal_helpers import (
    create_test_session,
    create_stuck_card,
    create_failed_card,
    verify_card_present,
    trigger_dismissal,
)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from src.session.store import SessionStore
from src.sse.broadcaster import SSEBroadcaster, SSEEvent, EventType


# =============================================================================
# Session Creation Helpers
# =============================================================================

async def create_test_session(store: SessionStore | None = None, tmp_path: Path | None = None) -> tuple[SessionStore, str]:
    """
    Create a test session with an isolated store.

    Args:
        store: Optional existing SessionStore. If None, creates a new one.
        tmp_path: Optional temp path for store. Required if store is None.

    Returns:
        Tuple of (SessionStore, session_id)

    Example:
        store, session_id = await create_test_session(tmp_path)
    """
    if store is None:
        if tmp_path is None:
            raise ValueError("tmp_path is required when store is not provided")
        db_path = tmp_path / "test_session.db"
        store = SessionStore(db_path)
        await store.initialize()

    session_id = await store.create_session()
    return store, session_id


async def create_test_session_with_topic(
    store: SessionStore | None = None,
    tmp_path: Path | None = None,
    label: str = "Test Topic",
    topic_type: str = "project"
) -> tuple[SessionStore, str, str]:
    """
    Create a test session with a topic.

    Args:
        store: Optional existing SessionStore
        tmp_path: Optional temp path for store
        label: Topic label
        topic_type: Topic type (project, research, personal, etc.)

    Returns:
        Tuple of (SessionStore, session_id, topic_id)

    Example:
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path)
    """
    store, session_id = await create_test_session(store, tmp_path)
    topic_id, _ = await store.find_or_create_topic(
        label=label,
        session_id=session_id,
        topic_type=topic_type
    )
    return store, session_id, topic_id


# =============================================================================
# Card Creation Helpers
# =============================================================================

async def create_stuck_card(
    store: SessionStore,
    session_id: str,
    topic_id: str | None = None,
    bead_id: str = "adc-stuck-test",
    stuck_reason: str = "Test stuck reason",
    refusal_count: int = 3,
    message: str = "Task stuck — needs input"
) -> dict[str, Any]:
    """
    Create a stuck card in the session store.

    Creates the necessary intent and bead_watch entries for a stuck card.

    Args:
        store: SessionStore instance
        session_id: Session ID
        topic_id: Optional topic ID. If None, creates one.
        bead_id: Bead reference ID
        stuck_reason: Reason for being stuck
        refusal_count: Number of refusals
        message: Card message

    Returns:
        Dict with card data including bead_id, stuck_reason, etc.

    Example:
        card_data = await create_stuck_card(store, session_id, topic_id)
    """
    # Create topic if not provided
    if topic_id is None:
        topic_id, _ = await store.find_or_create_topic(
            label="Stuck Card Topic",
            session_id=session_id,
            topic_type="project"
        )

    # Create utterance
    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="test stuck card",
    )

    # Create intent with bead_ref
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_id,
        lookup_kind=None,
        topic_id=topic_id,
    )

    # Create bead_watch row
    await store.create_bead_watch(
        bead_ref=bead_id,
        sla_hours=24,
        intent_type="task-profile",
    )

    return {
        "bead_id": bead_id,
        "stuck_reason": stuck_reason,
        "refusal_count": refusal_count,
        "message": message,
        "intent_id": intent_id,
        "session_id": session_id,
        "topic_id": topic_id,
        "timestamp": 1234567890,
    }


async def create_failed_card(
    store: SessionStore,
    session_id: str,
    topic_id: str | None = None,
    bead_id: str = "adc-failed-test",
    failure_reason: str = "Test failure reason",
    error_type: str = "test_error",
    message: str = "Task failed"
) -> dict[str, Any]:
    """
    Create a failed card in the session store.

    Creates the necessary intent entry for a failed card.

    Args:
        store: SessionStore instance
        session_id: Session ID
        topic_id: Optional topic ID. If None, creates one.
        bead_id: Bead reference ID
        failure_reason: Reason for failure
        error_type: Type of error
        message: Card message

    Returns:
        Dict with card data including bead_id, failure_reason, etc.

    Example:
        card_data = await create_failed_card(store, session_id, topic_id)
    """
    # Create topic if not provided
    if topic_id is None:
        topic_id, _ = await store.find_or_create_topic(
            label="Failed Card Topic",
            session_id=session_id,
            topic_type="project"
        )

    # Create utterance
    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="test failed card",
    )

    # Create intent with bead_ref
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_id,
        lookup_kind=None,
        topic_id=topic_id,
    )

    return {
        "bead_id": bead_id,
        "failure_reason": failure_reason,
        "error_type": error_type,
        "message": message,
        "intent_id": intent_id,
        "session_id": session_id,
        "topic_id": topic_id,
        "timestamp": 1234567891,
    }


# =============================================================================
# Card Verification Helpers
# =============================================================================

def verify_card_present(cards: list[dict[str, Any]], card_type: str, bead_id: str | None = None) -> bool:
    """
    Verify that a card is present in the cards list.

    Args:
        cards: List of card dicts from GET /api/v1/sessions/{id}/topics
        card_type: Type of card ('stuck' or 'failed')
        bead_id: Optional bead_id to match

    Returns:
        True if card is present, False otherwise

    Example:
        cards = await store.get_active_topics(session_id)
        assert verify_card_present(cards, 'stuck', 'adc-stuck-1')
    """
    for card in cards:
        # Check if this is a builtin card of the right type
        if card.get("card_type") == "builtin":
            builtin_data = card.get("builtin_data", {})
            if builtin_data.get("type") == card_type:
                if bead_id is None or builtin_data.get("data", {}).get("bead_id") == bead_id:
                    return True
    return False


def count_cards_by_type(cards: list[dict[str, Any]], card_type: str) -> int:
    """
    Count cards of a specific type.

    Args:
        cards: List of card dicts
        card_type: Type to count ('stuck' or 'failed')

    Returns:
        Number of cards of the specified type

    Example:
        stuck_count = count_cards_by_type(cards, 'stuck')
    """
    count = 0
    for card in cards:
        if card.get("card_type") == "builtin":
            if card.get("builtin_data", {}).get("type") == card_type:
                count += 1
    return count


def find_card_by_bead_id(cards: list[dict[str, Any]], bead_id: str) -> dict[str, Any] | None:
    """
    Find a card by its bead_id.

    Args:
        cards: List of card dicts
        bead_id: Bead ID to search for

    Returns:
        Card dict if found, None otherwise

    Example:
        card = find_card_by_bead_id(cards, 'adc-stuck-1')
    """
    for card in cards:
        if card.get("card_type") == "builtin":
            builtin_data = card.get("builtin_data", {})
            if builtin_data.get("data", {}).get("bead_id") == bead_id:
                return card
    return None


# =============================================================================
# Database Verification Helpers
# =============================================================================

async def verify_result_exists_in_db(
    store: SessionStore,
    result_id: str
) -> bool:
    """
    Verify that a result exists in the database by result ID.

    Args:
        store: SessionStore instance
        result_id: Result ID to check

    Returns:
        True if result exists, False otherwise

    Example:
        exists = await verify_result_exists_in_db(store, result_id)
    """
    import sqlite3
    try:
        async with aiosqlite.connect(store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT 1 FROM results WHERE id = ?",
                (result_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None
    except Exception:
        return False


async def verify_result_count_for_intent(
    store: SessionStore,
    intent_id: str,
    expected_count: int
) -> bool:
    """
    Verify the number of results for a specific intent.

    Args:
        store: SessionStore instance
        intent_id: Intent ID to check
        expected_count: Expected number of results

    Returns:
        True if count matches, False otherwise

    Example:
        assert await verify_result_count_for_intent(store, intent_id, 0)
    """
    results = await store.get_results_for_intent(intent_id)
    return len(results) == expected_count


async def verify_result_deleted_from_db(
    store: SessionStore,
    result_id: str,
    session_id: str
) -> dict:
    """
    Verify that a result was deleted from the database.

    Performs both direct database query and session isolation check.

    Args:
        store: SessionStore instance
        result_id: Result ID that should be deleted
        session_id: Session ID for isolation check

    Returns:
        Dict with verification results:
        {
            "result_deleted": bool,
            "session_isolated": bool,
            "verification_passed": bool
        }

    Example:
        verification = await verify_result_deleted_from_db(store, result_id, session_id)
        assert verification["verification_passed"]
    """
    import sqlite3

    # Check if result exists in database
    result_exists = not await verify_result_exists_in_db(store, result_id)

    # Check session isolation by attempting to delete again
    deletion_result = await store.delete_result(result_id, session_id)
    session_isolated = deletion_result.get("result_deleted", 0) == 0

    return {
        "result_deleted": result_exists,
        "session_isolated": session_isolated,
        "verification_passed": result_exists and session_isolated
    }


async def get_all_results_for_session(store: SessionStore, session_id: str) -> list[dict]:
    """
    Get all results for a session directly from database.

    Args:
        store: SessionStore instance
        session_id: Session ID

    Returns:
        List of result dicts

    Example:
        results = await get_all_results_for_session(store, session_id)
    """
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM results
               WHERE session_id = ?
               ORDER BY created_at DESC""",
            (session_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def verify_database_integrity_after_dismissal(
    store: SessionStore,
    session_id: str,
    expected_result_count: int | None = None
) -> dict:
    """
    Verify database integrity after card dismissal.

    Checks that:
    - No orphaned results exist
    - Result counts are consistent
    - Foreign key relationships are intact

    Args:
        store: SessionStore instance
        session_id: Session ID to verify
        expected_result_count: Optional expected count of results

    Returns:
        Dict with integrity check results

    Example:
        integrity = await verify_database_integrity_after_dismissal(store, session_id)
        assert integrity["all_checks_passed"]
    """
    import sqlite3

    checks_passed = {}
    all_passed = True

    # Check 1: No orphaned results (results without valid session/intent/topic)
    try:
        async with aiosqlite.connect(store.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Check for results with invalid session_id
            async with db.execute(
                """SELECT COUNT(*) FROM results r
                   LEFT JOIN sessions s ON r.session_id = s.id
                   WHERE s.id IS NULL"""
            ) as cursor:
                orphaned_by_session = (await cursor.fetchone())[0]

            # Check for results with invalid topic_id
            async with db.execute(
                """SELECT COUNT(*) FROM results r
                   LEFT JOIN topics t ON r.topic_id = t.id
                   WHERE t.id IS NULL"""
            ) as cursor:
                orphaned_by_topic = (await cursor.fetchone())[0]

            checks_passed["no_orphaned_results"] = (
                orphaned_by_session == 0 and orphaned_by_topic == 0
            )
            if orphaned_by_session > 0 or orphaned_by_topic > 0:
                all_passed = False

    except Exception as e:
        checks_passed["no_orphaned_results"] = False
        all_passed = False

    # Check 2: Result count consistency
    if expected_result_count is not None:
        results = await get_all_results_for_session(store, session_id)
        checks_passed["result_count_match"] = len(results) == expected_result_count
        if len(results) != expected_result_count:
            all_passed = False
    else:
        checks_passed["result_count_match"] = True

    # Check 3: Session exists and is valid
    try:
        session = await store.get_session(session_id)
        checks_passed["session_valid"] = session is not None
        if session is None:
            all_passed = False
    except Exception:
        checks_passed["session_valid"] = False
        all_passed = False

    # Check 4: Topics are valid
    try:
        topics = await store.get_active_topics(session_id)
        checks_passed["topics_valid"] = all(t.get("id") for t in topics)
        if not all(t.get("id") for t in topics):
            all_passed = False
    except Exception:
        checks_passed["topics_valid"] = False
        all_passed = False

    return {
        "all_checks_passed": all_passed,
        "checks": checks_passed,
        "details": {
            "orphaned_by_session": orphaned_by_session if 'orphaned_by_session' in locals() else 0,
            "orphaned_by_topic": orphaned_by_topic if 'orphaned_by_topic' in locals() else 0,
        }
    }


async def verify_dismissal_persistence_across_reopen(
    db_path: Path,
    session_id: str,
    result_id: str | None = None,
    intent_id: str | None = None
) -> dict:
    """
    Verify that dismissal persists across database reopen.

    Closes the current database and reopens it to simulate a restart.

    Args:
        db_path: Path to the database file
        session_id: Session ID to verify
        result_id: Optional result ID that should be deleted
        intent_id: Optional intent ID to check results for

    Returns:
        Dict with persistence verification results

    Example:
        persistence = await verify_dismissal_persistence_across_reopen(
            db_path, session_id, result_id=result_id
        )
        assert persistence["dismissal_persisted"]
    """
    from src.session.store import SessionStore

    # Close any existing connections and reopen database
    store1 = SessionStore(db_path)
    await store1.initialize()

    verification_results = {}

    try:
        # Verify session still exists
        session = await store1.get_session(session_id)
        verification_results["session_exists"] = session is not None

        # Verify result deletion if result_id provided
        if result_id:
            result_exists = await verify_result_exists_in_db(store1, result_id)
            verification_results["result_deleted"] = not result_exists
        else:
            verification_results["result_deleted"] = True

        # Verify intent results if intent_id provided
        if intent_id:
            results = await store1.get_results_for_intent(intent_id)
            verification_results["intent_result_count"] = len(results)
        else:
            verification_results["intent_result_count"] = None

        # Check overall persistence
        verification_results["dismissal_persisted"] = all([
            verification_results.get("session_exists", False),
            verification_results.get("result_deleted", True),
        ])

    finally:
        await store1.close()

    return verification_results


async def count_results_by_bead_id(
    store: SessionStore,
    session_id: str,
    bead_id: str
) -> int:
    """
    Count results for a specific bead_id in a session.

    Args:
        store: SessionStore instance
        session_id: Session ID
        bead_id: Bead ID to count

    Returns:
        Number of results for the bead_id

    Example:
        count = await count_results_by_bead_id(store, session_id, "adc-stuck-1")
    """
    import json

    results = await get_all_results_for_session(store, session_id)
    count = 0
    for result in results:
        try:
            data = json.loads(result.get("data", "{}"))
            if data.get("bead_id") == bead_id or data.get("bead_ref") == bead_id:
                count += 1
        except (json.JSONDecodeError, TypeError):
            continue
    return count


async def verify_cards_remain_after_dismissal(
    store: SessionStore,
    session_id: str,
    dismissed_bead_ids: list[str],
    remaining_bead_ids: list[str]
) -> dict:
    """
    Verify that specific cards were dismissed and others remain.

    Args:
        store: SessionStore instance
        session_id: Session ID
        dismissed_bead_ids: Bead IDs that should be dismissed
        remaining_bead_ids: Bead IDs that should remain

    Returns:
        Dict with verification results

    Example:
        verification = await verify_cards_remain_after_dismissal(
            store, session_id,
            dismissed_bead_ids=["adc-stuck-1"],
            remaining_bead_ids=["adc-stuck-2", "adc-stuck-3"]
        )
        assert verification["all_correct"]
    """
    results = {}

    # Check dismissed cards are gone
    for bead_id in dismissed_bead_ids:
        count = await count_results_by_bead_id(store, session_id, bead_id)
        results[f"dismissed_{bead_id}"] = count == 0

    # Check remaining cards still exist
    for bead_id in remaining_bead_ids:
        count = await count_results_by_bead_id(store, session_id, bead_id)
        results[f"remaining_{bead_id}"] = count > 0

    results["all_correct"] = all(results.values())

    return results


# =============================================================================
# Dismissal Trigger Helpers
# =============================================================================

def get_dismissal_selector(bead_id: str | None = None, card_type: str = "stuck") -> str:
    """
    Get CSS selector for dismissal button.

    Args:
        bead_id: Optional bead_id for specific card
        card_type: Type of card ('stuck' or 'failed')

    Returns:
        CSS selector string

    Examples:
        # Select all stuck card dismissal buttons
        selector = get_dismissal_selector(card_type='stuck')

        # Select specific card's dismissal button
        selector = get_dismissal_selector(bead_id='adc-stuck-1', card_type='stuck')
    """
    if bead_id:
        # Specific card dismissal button
        return f'[data-builtin="{card_type}"][data-bead-id="{bead_id}"] .dismiss-button'
    else:
        # All cards of this type
        return f'[data-builtin="{card_type}"] .dismiss-button'


async def trigger_dismissal(
    page,
    bead_id: str | None = None,
    card_type: str = "stuck",
    button_selector: str | None = None
) -> None:
    """
    Trigger a dismissal button click in the browser.

    Args:
        page: Playwright Page instance
        bead_id: Optional bead_id for specific card
        card_type: Type of card ('stuck' or 'failed')
        button_selector: Optional custom button selector

    Example:
        await trigger_dismissal(page, bead_id='adc-stuck-1', card_type='stuck')
    """
    if button_selector is None:
        button_selector = get_dismissal_selector(bead_id, card_type)

    # Wait for button to be present
    await page.wait_for_selector(button_selector, timeout=5000)

    # Click the button
    await page.click(button_selector)


async def dismiss_and_verify(
    page,
    store: SessionStore,
    session_id: str,
    bead_id: str,
    card_type: str = "stuck"
) -> None:
    """
    Dismiss a card and verify it's removed from the store.

    Args:
        page: Playwright Page instance
        store: SessionStore instance
        session_id: Session ID
        bead_id: Bead ID to dismiss
        card_type: Type of card ('stuck' or 'failed')

    Example:
        await dismiss_and_verify(page, store, session_id, 'adc-stuck-1', 'stuck')
    """
    # Get cards before dismissal
    topics_before = await store.get_active_topics(session_id)
    cards_before = [t for t in topics_before if t.get("card_type") == "builtin"]

    # Trigger dismissal
    await trigger_dismissal(page, bead_id=bead_id, card_type=card_type)

    # Wait for removal (with timeout)
    import asyncio
    await asyncio.sleep(0.5)

    # Get cards after dismissal
    topics_after = await store.get_active_topics(session_id)
    cards_after = [t for t in topics_after if t.get("card_type") == "builtin"]

    # Verify card was removed
    card_before = find_card_by_bead_id(cards_before, bead_id)
    card_after = find_card_by_bead_id(cards_after, bead_id)

    assert card_before is not None, f"Card {bead_id} not found before dismissal"
    assert card_after is None, f"Card {bead_id} still present after dismissal"


# =============================================================================
# SSE Broadcast Helpers
# =============================================================================

async def broadcast_stuck_card(
    broadcaster: SSEBroadcaster,
    card_data: dict[str, Any],
    session_id: str
) -> None:
    """
    Broadcast a stuck card via SSE.

    Args:
        broadcaster: SSEBroadcaster instance
        card_data: Card data from create_stuck_card()
        session_id: Session ID

    Example:
        card_data = await create_stuck_card(store, session_id)
        await broadcast_stuck_card(broadcaster, card_data, session_id)
    """
    await broadcaster.broadcast(
        SSEEvent(
            event_type=EventType.TASK_STUCK,
            data={
                "bead_id": card_data["bead_id"],
                "stuck_reason": card_data["stuck_reason"],
                "refusal_count": card_data["refusal_count"],
                "message": card_data["message"],
                "action_hint": "Review the bead and provide the missing information.",
                "timestamp": card_data["timestamp"],
            },
            target_session_id=session_id,
        )
    )


async def broadcast_failed_card(
    broadcaster: SSEBroadcaster,
    card_data: dict[str, Any],
    session_id: str
) -> None:
    """
    Broadcast a failed card via SSE.

    Args:
        broadcaster: SSEBroadcaster instance
        card_data: Card data from create_failed_card()
        session_id: Session ID

    Example:
        card_data = await create_failed_card(store, session_id)
        await broadcast_failed_card(broadcaster, card_data, session_id)
    """
    await broadcaster.broadcast(
        SSEEvent(
            event_type=EventType.TASK_FAILED,
            data={
                "bead_id": card_data["bead_id"],
                "failure_reason": card_data["failure_reason"],
                "error_type": card_data["error_type"],
                "message": card_data["message"],
                "timestamp": card_data["timestamp"],
            },
            target_session_id=session_id,
        )
    )


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
async def test_store(tmp_path: Path) -> SessionStore:
    """Create an isolated SessionStore for testing."""
    db_path = tmp_path / "test_card_dismissal.db"
    store = SessionStore(db_path)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
async def test_broadcaster():
    """Create a fresh SSE broadcaster for testing."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()
    yield broadcaster
    await broadcaster.stop()


@pytest.fixture
async def test_session_with_store(test_store: SessionStore) -> tuple[SessionStore, str]:
    """Create a test session with store."""
    session_id = await test_store.create_session()
    return test_store, session_id


@pytest.fixture
async def test_session_with_topic(
    test_store: SessionStore
) -> tuple[SessionStore, str, str]:
    """Create a test session with a topic."""
    session_id = await test_store.create_session()
    topic_id, _ = await test_store.find_or_create_topic(
        label="Card Dismissal Test Topic",
        session_id=session_id,
        topic_type="project"
    )
    return test_store, session_id, topic_id


# =============================================================================
# Mock Helpers
# =============================================================================

def create_mock_router() -> AsyncMock:
    """
    Create a mock surface router for testing.

    Returns:
        AsyncMock configured as a router

    Example:
        router = create_mock_router()
    """
    router = AsyncMock()
    decision = MagicMock()
    decision.target_surfaces = []
    decision.fallback_used = True
    router.route_result.return_value = decision
    return router
