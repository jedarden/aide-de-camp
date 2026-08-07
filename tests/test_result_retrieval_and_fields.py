#!/usr/bin/env python3
"""
Comprehensive tests for result retrieval and field validation.

Tests verify:
1. All result fields are retrievable
2. Result queries by different criteria (by ID, topic, session, intent)
3. Result edge cases (empty fields, null values, special characters)
4. Result field validation (urgency values, data format)
5. Result update scenarios (card_fallback, surfaced_at, acked_at)
6. Result relationships and constraints

Uses the test infrastructure from adc-2v8ae7 and builds on patterns from
previous tests (adc-2fquah, adc-v3wqmz).
"""

import asyncio
import json
import pytest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite

from src.session.store import SessionStore


# ============================================================================
# Basic Result Field Retrieval Tests
# ============================================================================

@pytest.mark.asyncio
async def test_result_all_fields_retrievable(in_memory_db_store, in_memory_db_session_id):
    """Test that all result fields are correctly stored and retrievable."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    # Create a topic for the result
    topic_id = await store.create_topic(
        label="Test Topic",
        topic_type="project",
        project_slugs=["test-project"],
        scope="session",
        session_id=session_id
    )

    # Create an intent for the result
    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test utterance"
    )
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="status"
    )

    # Create a result with all fields populated
    result_data = {
        "test_field": "test_value",
        "nested": {
            "field": "nested_value"
        },
        "array": [1, 2, 3]
    }

    created_at = int(datetime.now().timestamp())
    result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result with all fields",
        data=result_data,
        urgency="high",
        result_type="status:test-project",
        card_fallback=False,
        previous_result_id=None,
        diff_summary="No previous result",
        diff_data={"changes": ["initial"]}
    )

    # Retrieve the result
    result = await store.get_result(result_id)

    # Verify all fields are retrievable
    assert result is not None, "Result should be retrievable"
    assert result["id"] == result_id, "Result ID should match"
    assert result["intent_id"] == intent_id, "Intent ID should match"
    assert result["topic_id"] == topic_id, "Topic ID should match"
    assert result["session_id"] == session_id, "Session ID should match"
    assert result["summary"] == "Test result with all fields", "Summary should match"
    assert result["urgency"] == "high", "Urgency should match"
    assert result["result_type"] == "status:test-project", "Result type should match"
    assert result["card_fallback"] == 0, "Card fallback should be 0 (False)"
    assert result["surfaced_at"] is not None, "Surfaced_at should be set automatically"
    assert result["previous_result_id"] is None, "Previous result ID should be None"
    assert result["diff_summary"] == "No previous result", "Diff summary should match"

    # Verify data field is valid JSON
    retrieved_data = json.loads(result["data"])
    assert retrieved_data == result_data, "Data field should contain original data"

    # Verify created_at is a reasonable timestamp
    assert result["created_at"] >= created_at, "Created_at should be set"


@pytest.mark.asyncio
async def test_result_with_optional_null_fields(in_memory_db_store, in_memory_db_session_id):
    """Test result creation and retrieval with NULL optional fields."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    # Create topic
    topic_id = await store.create_topic(
        label="Null Fields Test",
        session_id=session_id
    )

    # Create result with minimal required fields (all optional fields as None/null)
    result_id = await store.create_result(
        intent_id=None,  # Monitoring-originated result (no intent)
        topic_id=topic_id,
        session_id=session_id,
        summary="Minimal result",
        data={"minimal": True},
        urgency="normal",
        result_type=None,  # Optional
        card_fallback=False,
        previous_result_id=None,  # Optional
        diff_summary=None,  # Optional
        diff_data=None  # Optional
    )

    # Retrieve and verify NULL fields are handled correctly
    result = await store.get_result(result_id)

    assert result is not None, "Result should be retrievable"
    assert result["intent_id"] is None, "Intent ID should be NULL for monitoring results"
    assert result["result_type"] is None, "Result type should be NULL when not provided"
    assert result["previous_result_id"] is None, "Previous result ID should be NULL"
    assert result["diff_summary"] is None, "Diff summary should be NULL"
    assert result["diff_data"] is None, "Diff data should be NULL"
    assert result["surfaced_at"] is not None, "Surfaced_at should be set even for minimal results"


@pytest.mark.asyncio
async def test_result_urgency_validation(in_memory_db_store, in_memory_db_session_id):
    """Test that result urgency field accepts all valid values."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    # Create topic
    topic_id = await store.create_topic(
        label="Urgency Validation Test",
        session_id=session_id
    )

    valid_urgency_values = ["critical", "high", "normal", "low"]

    for urgency in valid_urgency_values:
        result_id = await store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary=f"Test urgency {urgency}",
            data={"urgency": urgency},
            urgency=urgency
        )

        result = await store.get_result(result_id)
        assert result["urgency"] == urgency, f"Urgency {urgency} should be stored and retrieved"


# ============================================================================
# Result Query Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_results_for_intent(in_memory_db_store, in_memory_db_session_id):
    """Test retrieving results by intent ID."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    # Create topic and intent
    topic_id = await store.create_topic(
        label="Intent Results Test",
        session_id=session_id
    )

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test utterance"
    )
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="status"
    )

    # Create multiple results for the same intent
    result_ids = []
    for i in range(3):
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=f"Result {i+1}",
            data={"index": i}
        )
        result_ids.append(result_id)

    # Retrieve results by intent
    results = await store.get_results_for_intent(intent_id)

    assert len(results) == 3, "Should retrieve all 3 results for the intent"
    assert results[0]["intent_id"] == intent_id, "Results should belong to the intent"

    # Results should be ordered by created_at DESC
    # The last created result should be first
    assert results[0]["id"] == result_ids[2], "Results should be ordered by created_at DESC"


@pytest.mark.asyncio
async def test_get_all_results(in_memory_db_store, in_memory_db_session_id):
    """Test retrieving all results from the database."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    # Create multiple topics and results
    topic_ids = []
    for i in range(2):
        topic_id = await store.create_topic(
            label=f"Topic {i+1}",
            session_id=session_id
        )
        topic_ids.append(topic_id)

        # Create results for each topic
        await store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary=f"Topic {i+1} Result",
            data={"topic_index": i}
        )

    # Get all results
    all_results = await store.get_all_results()

    assert len(all_results) >= 2, "Should retrieve at least the 2 results we created"
    assert all_results[0]["summary"] == "Topic 2 Result", "Results should be ordered by created_at DESC"


@pytest.mark.asyncio
async def test_get_unsurfed_results(in_memory_db_store, in_memory_db_session_id):
    """Test retrieving unsurfed results (results with surfaced_at = NULL)."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    # Create topic
    topic_id = await store.create_topic(
        label="Unsurfed Results Test",
        session_id=session_id
    )

    # Create results (they will have surfaced_at set by create_result)
    result_ids = []
    for i in range(3):
        result_id = await store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary=f"Result {i+1}",
            data={"index": i}
        )
        result_ids.append(result_id)

    # Initially, all results should be surfaced (create_result sets surfaced_at)
    unsurfed = await store.get_unsurfed_results(session_id)
    assert len(unsurfed) == 0, "Initially all results should be surfaced"

    # Manually set surfaced_at to NULL for some results to simulate unsurfed state
    async with aiosqlite.connect(store.db_path) as db:
        await db.execute(
            "UPDATE results SET surfaced_at = NULL WHERE id = ?",
            (result_ids[0],)
        )
        await db.execute(
            "UPDATE results SET surfaced_at = NULL WHERE id = ?",
            (result_ids[1],)
        )
        await db.commit()

    # Now should have 2 unsurfed results
    unsurfed = await store.get_unsurfed_results(session_id)
    assert len(unsurfed) == 2, "Should retrieve 2 unsurfed results"

    # Unsurfed results should be ordered by created_at ASC
    unsurfed_ids = [r["id"] for r in unsurfed]
    assert result_ids[0] in unsurfed_ids, "First result should be in unsurfed list"
    assert result_ids[1] in unsurfed_ids, "Second result should be in unsurfed list"


# ============================================================================
# Result Edge Cases Tests
# ============================================================================

@pytest.mark.asyncio
async def test_result_with_empty_summary(in_memory_db_store, in_memory_db_session_id):
    """Test result with empty string summary (edge case)."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Empty Summary Test",
        session_id=session_id
    )

    # Create result with empty summary
    result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="",  # Empty summary
        data={"test": "data"}
    )

    result = await store.get_result(result_id)
    assert result["summary"] == "", "Empty summary should be stored correctly"


@pytest.mark.asyncio
async def test_result_with_complex_data_structure(in_memory_db_store, in_memory_db_session_id):
    """Test result with deeply nested and complex data structure."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Complex Data Test",
        session_id=session_id
    )

    # Create result with complex nested data
    complex_data = {
        "level1": {
            "level2": {
                "level3": {
                    "level4": {
                        "value": "deeply nested"
                    }
                },
                "array": [
                    {"item": 1},
                    {"item": 2},
                    {"item": 3}
                ]
            }
        },
        "special_chars": "Test with quotes: 'single' and \"double\"",
        "unicode": "Test unicode: café, 日本語, emoji 🎉",
        "numbers": {
            "int": 42,
            "float": 3.14159,
            "negative": -100,
            "zero": 0,
            "large": 1000000
        },
        "booleans": {
            "true_val": True,
            "false_val": False,
            "null_val": None
        }
    }

    result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Complex data structure test",
        data=complex_data
    )

    result = await store.get_result(result_id)
    retrieved_data = json.loads(result["data"])

    assert retrieved_data == complex_data, "Complex data structure should be preserved"
    assert retrieved_data["level1"]["level2"]["level3"]["level4"]["value"] == "deeply nested", "Deeply nested values should be retrievable"
    assert len(retrieved_data["level1"]["level2"]["array"]) == 3, "Arrays in nested structures should be preserved"
    assert retrieved_data["special_chars"] == "Test with quotes: 'single' and \"double\"", "Special characters should be preserved"
    assert retrieved_data["unicode"] == "Test unicode: café, 日本語, emoji 🎉", "Unicode characters should be preserved"


@pytest.mark.asyncio
async def test_result_with_large_data_payload(in_memory_db_store, in_memory_db_session_id):
    """Test result with large data payload (stress test)."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Large Payload Test",
        session_id=session_id
    )

    # Create large data payload (array with 1000 items)
    large_data = {
        "items": [{"index": i, "data": "x" * 100} for i in range(1000)],
        "metadata": {"count": 1000}
    }

    result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Large payload test",
        data=large_data
    )

    result = await store.get_result(result_id)
    retrieved_data = json.loads(result["data"])

    assert len(retrieved_data["items"]) == 1000, "Large arrays should be stored and retrieved"
    assert retrieved_data["items"][999]["index"] == 999, "Last item in large array should be accessible"


@pytest.mark.asyncio
async def test_result_card_fallback_flag(in_memory_db_store, in_memory_db_session_id):
    """Test card_fallback flag behavior."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Card Fallback Test",
        session_id=session_id
    )

    # Create result with card_fallback=False (component rendered it)
    result_id_normal = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Normal result with component",
        data={"component_used": True},
        card_fallback=False
    )

    # Create result with card_fallback=True (generic fallback card)
    result_id_fallback = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Fallback result",
        data={"component_used": False},
        card_fallback=True
    )

    # Verify card_fallback values
    result_normal = await store.get_result(result_id_normal)
    result_fallback = await store.get_result(result_id_fallback)

    assert result_normal["card_fallback"] == 0, "Normal result should have card_fallback=0"
    assert result_fallback["card_fallback"] == 1, "Fallback result should have card_fallback=1"


@pytest.mark.asyncio
async def test_result_update_card_fallback(in_memory_db_store, in_memory_db_session_id):
    """Test updating result card_fallback flag."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Update Fallback Test",
        session_id=session_id
    )

    # Create result with card_fallback=False
    result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result",
        data={"test": "data"},
        card_fallback=False
    )

    # Verify initial state
    result = await store.get_result(result_id)
    assert result["card_fallback"] == 0, "Initially card_fallback should be 0"

    # Update to card_fallback=True
    await store.update_result_card_fallback(result_id, card_fallback=True)

    # Verify update
    result = await store.get_result(result_id)
    assert result["card_fallback"] == 1, "After update, card_fallback should be 1"

    # Update back to card_fallback=False
    await store.update_result_card_fallback(result_id, card_fallback=False)

    # Verify update
    result = await store.get_result(result_id)
    assert result["card_fallback"] == 0, "After second update, card_fallback should be 0"


# ============================================================================
# Result Timestamp Tests
# ============================================================================

@pytest.mark.asyncio
async def test_result_timestamps_set_correctly(in_memory_db_store, in_memory_db_session_id):
    """Test that result timestamps (created_at, surfaced_at) are set correctly."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Timestamp Test",
        session_id=session_id
    )

    before_create = int(datetime.now().timestamp())

    result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Timestamp test",
        data={"test": "data"}
    )

    after_create = int(datetime.now().timestamp())

    result = await store.get_result(result_id)

    # Verify created_at is set and within time range
    assert result["created_at"] is not None, "created_at should be set"
    assert result["created_at"] >= before_create, "created_at should be after creation start time"
    assert result["created_at"] <= after_create, "created_at should be before creation end time"

    # Verify surfaced_at is set automatically
    assert result["surfaced_at"] is not None, "surfaced_at should be set automatically"
    assert result["surfaced_at"] >= before_create, "surfaced_at should be after creation start time"
    assert result["surfaced_at"] <= after_create, "surfaced_at should be before creation end time"

    # Verify acked_at is NULL initially
    assert result["acked_at"] is None, "acked_at should be NULL initially"


@pytest.mark.asyncio
async def test_mark_results_surfed(in_memory_db_store, in_memory_db_session_id):
    """Test marking results as surfaced."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Mark Surfaced Test",
        session_id=session_id
    )

    # Create results
    result_ids = []
    for i in range(3):
        result_id = await store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary=f"Result {i+1}",
            data={"index": i}
        )
        result_ids.append(result_id)

    # Manually set surfaced_at to NULL
    async with aiosqlite.connect(store.db_path) as db:
        for result_id in result_ids:
            await db.execute(
                "UPDATE results SET surfaced_at = NULL WHERE id = ?",
                (result_id,)
            )
        await db.commit()

    # Verify all are unsurfed
    unsurfed = await store.get_unsurfed_results(session_id)
    assert len(unsurfed) == 3, "All 3 results should be unsurfed"

    # Mark all as surfaced
    await store.mark_results_surfed(session_id)

    # Verify none are unsurfed now
    unsurfed = await store.get_unsurfed_results(session_id)
    assert len(unsurfed) == 0, "No results should be unsurfed after marking"


@pytest.mark.asyncio
async def test_mark_results_surfed_by_ids(in_memory_db_store, in_memory_db_session_id):
    """Test marking specific results as surfaced by their IDs."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Mark Surfaced By IDs Test",
        session_id=session_id
    )

    # Create results
    result_ids = []
    for i in range(3):
        result_id = await store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary=f"Result {i+1}",
            data={"index": i}
        )
        result_ids.append(result_id)

    # Manually set surfaced_at to NULL for all
    async with aiosqlite.connect(store.db_path) as db:
        for result_id in result_ids:
            await db.execute(
                "UPDATE results SET surfaced_at = NULL WHERE id = ?",
                (result_id,)
            )
        await db.commit()

    # Mark only specific results as surfaced
    await store.mark_results_surfed_by_ids(session_id, [result_ids[0], result_ids[2]])

    # Verify only the marked ones are surfaced
    unsurfed = await store.get_unsurfed_results(session_id)
    assert len(unsurfed) == 1, "Only 1 result should remain unsurfed"
    assert unsurfed[0]["id"] == result_ids[1], "The middle result should remain unsurfed"


# ============================================================================
# Result Relationship Tests
# ============================================================================

@pytest.mark.asyncio
async def test_result_intent_relationship(in_memory_db_store, in_memory_db_session_id):
    """Test result-intent relationship integrity."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    # Create complete chain: session -> utterance -> intent -> result
    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test utterance"
    )

    topic_id = await store.create_topic(
        label="Intent Relationship Test",
        session_id=session_id
    )

    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="status",
        topic_id=topic_id
    )

    result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result",
        data={"test": "data"}
    )

    # Retrieve and verify relationships
    result = await store.get_result(result_id)
    intent = await store.get_intent(intent_id)
    utterance = await store.get_utterance(utterance_id)

    assert result["intent_id"] == intent_id, "Result should reference intent"
    assert intent["utterance_id"] == utterance_id, "Intent should reference utterance"
    assert intent["topic_id"] == topic_id, "Intent should reference topic"
    assert utterance["session_id"] == session_id, "Utterance should reference session"


@pytest.mark.asyncio
async def test_result_topic_relationship(in_memory_db_store, in_memory_db_session_id):
    """Test result-topic relationship integrity."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    # Create topic
    topic_id = await store.create_topic(
        label="Topic Relationship Test",
        topic_type="project",
        project_slugs=["test-project"],
        session_id=session_id
    )

    # Create multiple results for the same topic
    for i in range(3):
        await store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary=f"Result {i+1}",
            data={"index": i}
        )

    # Get topic and verify results are associated
    topic = await store.get_topic(topic_id)
    assert topic is not None, "Topic should be retrievable"
    assert topic["id"] == topic_id, "Topic ID should match"

    # Get latest result for the topic
    latest_result = await store.get_latest_result_for_topic(topic_id)
    assert latest_result is not None, "Should have latest result for topic"
    assert latest_result["topic_id"] == topic_id, "Latest result should belong to topic"


# ============================================================================
# Result Delete Tests
# ============================================================================

@pytest.mark.asyncio
async def test_delete_result(in_memory_db_store, in_memory_db_session_id):
    """Test deleting a result by ID."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Delete Test",
        session_id=session_id
    )

    # Create result
    result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result to delete",
        data={"test": "data"}
    )

    # Verify it exists
    result = await store.get_result(result_id)
    assert result is not None, "Result should exist before deletion"

    # Delete the result
    delete_result = await store.delete_result(result_id, session_id)

    assert delete_result["result_deleted"] == 1, "Should delete 1 result"

    # Verify it's gone
    result = await store.get_result(result_id)
    assert result is None, "Result should not exist after deletion"


@pytest.mark.asyncio
async def test_delete_result_session_isolation(in_memory_db_store, in_memory_db_session_id):
    """Test that results can only be deleted by their owning session."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    # Create another session
    other_session_id = await store.create_session()

    topic_id = await store.create_topic(
        label="Session Isolation Test",
        session_id=session_id
    )

    # Create result in first session
    result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result",
        data={"test": "data"}
    )

    # Try to delete from other session (should fail)
    delete_result = await store.delete_result(result_id, other_session_id)

    assert delete_result["result_deleted"] == 0, "Should not delete result from other session"

    # Verify result still exists
    result = await store.get_result(result_id)
    assert result is not None, "Result should still exist after failed deletion"

    # Delete from correct session (should succeed)
    delete_result = await store.delete_result(result_id, session_id)

    assert delete_result["result_deleted"] == 1, "Should delete result from owning session"

    # Verify it's gone
    result = await store.get_result(result_id)
    assert result is None, "Result should not exist after successful deletion"


# ============================================================================
# Result Data Type Tests
# ============================================================================

@pytest.mark.asyncio
async def test_result_data_types_preservation(in_memory_db_store, in_memory_db_session_id):
    """Test that different data types are preserved in result data field."""
    store = in_memory_db_store
    session_id = in_memory_db_session_id

    topic_id = await store.create_topic(
        label="Data Types Test",
        session_id=session_id
    )

    # Create result with various data types
    typed_data = {
        "string": "hello world",
        "integer": 42,
        "float": 3.14159,
        "boolean_true": True,
        "boolean_false": False,
        "null_value": None,
        "empty_string": "",
        "empty_array": [],
        "empty_object": {},
        "array_mixed": [1, "two", 3.0, True, None],
        "unicode": "Hello 世界 🎉",
        "special_chars": "Tab:\t, Newline:\n, Quote:\"",  # Containing control characters
        "large_number": 9999999999999999,
        "negative_number": -12345,
        "zero": 0
    }

    result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Data types preservation test",
        data=typed_data
    )

    result = await store.get_result(result_id)
    retrieved_data = json.loads(result["data"])

    # Verify all data types are preserved
    assert retrieved_data["string"] == "hello world", "String type should be preserved"
    assert retrieved_data["integer"] == 42, "Integer type should be preserved"
    assert abs(retrieved_data["float"] - 3.14159) < 0.00001, "Float type should be preserved"
    assert retrieved_data["boolean_true"] is True, "Boolean True should be preserved"
    assert retrieved_data["boolean_false"] is False, "Boolean False should be preserved"
    assert retrieved_data["null_value"] is None, "None/null should be preserved"
    assert retrieved_data["empty_string"] == "", "Empty string should be preserved"
    assert retrieved_data["empty_array"] == [], "Empty array should be preserved"
    assert retrieved_data["empty_object"] == {}, "Empty object should be preserved"
    assert retrieved_data["array_mixed"] == [1, "two", 3.0, True, None], "Mixed array should be preserved"
    assert retrieved_data["unicode"] == "Hello 世界 🎉", "Unicode should be preserved"
    assert "\t" in retrieved_data["special_chars"], "Tab character should be preserved"
    assert "\n" in retrieved_data["special_chars"], "Newline character should be preserved"
    assert retrieved_data["large_number"] == 9999999999999999, "Large numbers should be preserved"
    assert retrieved_data["negative_number"] == -12345, "Negative numbers should be preserved"
    assert retrieved_data["zero"] == 0, "Zero should be preserved"


# ============================================================================
# Test Summary
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
