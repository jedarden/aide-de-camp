"""Tests for the database-backed test-data teardown helpers."""

import aiosqlite
import pytest

from src.test.utilities import (
    cleanup_test_data,
    cleanup_test_sessions,
    cleanup_test_topics,
)


async def _count(store, table: str, column: str, value: str) -> int:
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",  # noqa: S608
            (value,),
        ) as cursor:
            row = await cursor.fetchone()
    return int(row[0]) if row else 0


@pytest.mark.asyncio
async def test_cleanup_test_sessions_removes_session_and_related_topic(
    test_db_store, test_data_cleanup
):
    session_id = await test_db_store.create_session("cleanup-session")
    await test_db_store.create_topic(
        label="cleanup topic", session_id=session_id
    )
    test_data_cleanup.add_session(session_id)

    await test_data_cleanup.cleanup()

    assert await _count(test_db_store, "sessions", "id", session_id) == 0
    assert await _count(test_db_store, "topics", "session_id", session_id) == 0


@pytest.mark.asyncio
async def test_cleanup_test_topics_removes_topic_owned_rows_but_keeps_session(
    test_db_store,
):
    session_id = await test_db_store.create_session("topic-cleanup-session")
    topic_id = await test_db_store.create_topic(
        label="topic to remove", session_id=session_id
    )
    await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="test result",
        data={"test": True},
    )

    await cleanup_test_topics(test_db_store, [topic_id])

    assert await _count(test_db_store, "topics", "id", topic_id) == 0
    assert await _count(test_db_store, "results", "topic_id", topic_id) == 0
    assert await _count(test_db_store, "sessions", "id", session_id) == 1


@pytest.mark.asyncio
async def test_cleanup_test_data_removes_session_and_topic_batches(test_db_store):
    session_id = await test_db_store.create_session("batch-session")
    topic_id = await test_db_store.create_topic(
        label="batch topic", session_id=session_id
    )

    summary = await cleanup_test_data(
        test_db_store,
        session_ids=[session_id],
        topic_ids=[topic_id],
    )

    assert summary["sessions"][session_id]["session_removed"] == 1
    assert await _count(test_db_store, "sessions", "id", session_id) == 0
    assert await _count(test_db_store, "topics", "id", topic_id) == 0


@pytest.mark.asyncio
async def test_cleanup_is_idempotent_for_missing_ids(test_db_store):
    await cleanup_test_sessions(test_db_store, ["missing-session"])
    await cleanup_test_topics(test_db_store, ["missing-topic"])


@pytest.mark.parametrize(
    "cleanup_test_data",
    [{"session_ids": ["fixture-session"]}],
    indirect=True,
)
@pytest.mark.asyncio
async def test_cleanup_fixture_accepts_initial_id_lists(
    test_db_store, cleanup_test_data
):
    await test_db_store.create_session("fixture-session")
    assert await _count(test_db_store, "sessions", "id", "fixture-session") == 1
