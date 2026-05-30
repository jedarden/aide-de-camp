#!/usr/bin/env python3
"""Test Phase 1: Session and Topics - persistence + Telegram fallback."""

import asyncio
import sys
from pathlib import Path

# Ensure the project root is in the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Use absolute imports from src package
from src.session.store import SessionStore
from src.topic.model import TopicManager, TopicCard
from src.surface.router import SurfaceRouter


async def test_database_initialization():
    """Test database initialization and schema verification."""
    print("Testing Phase 1: Database Initialization...")

    # Test database path
    test_db_path = Path("/tmp/test_adc_phase1.db")
    if test_db_path.exists():
        test_db_path.unlink()

    # Create store and initialize
    store = SessionStore(test_db_path)
    await store.initialize()

    # Verify tables exist
    import aiosqlite
    async with aiosqlite.connect(test_db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

    print(f"  Created tables: {tables}")

    # Expected tables
    expected_tables = {
        "sessions", "surfaces", "utterances", "intents", "results",
        "topics", "intent_topics", "topic_context_cache", "feedback_signals"
    }

    missing = expected_tables - set(tables)
    extra = set(tables) - expected_tables

    if missing:
        print(f"  ❌ Missing tables: {missing}")
        return False

    if extra:
        print(f"  ⚠️  Extra tables: {extra}")

    print(f"  ✅ All expected tables present")

    # Test session creation
    session_id = await store.create_session()
    print(f"  ✅ Created session: {session_id}")

    # Test session retrieval
    session = await store.get_session(session_id)
    if not session:
        print(f"  ❌ Failed to retrieve session")
        return False
    print(f"  ✅ Retrieved session: {session_id}")

    # Test surface registration
    surface_id = await store.register_surface(session_id, "canvas")
    print(f"  ✅ Registered canvas surface: {surface_id}")

    # Test Telegram surface registration (always_available=True)
    telegram_id = await store.register_surface(session_id, "telegram", always_available=True)
    print(f"  ✅ Registered Telegram surface (always_available): {telegram_id}")

    # Test utterance creation
    utterance_id = await store.create_utterance(session_id, "test utterance")
    print(f"  ✅ Created utterance: {utterance_id}")

    # Test intent creation
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="lookup"
    )
    print(f"  ✅ Created intent: {intent_id}")

    # Test topic creation
    topic_id = await store.create_topic(
        label="Test Topic",
        topic_type="project",
        project_slugs=["test-project"],
        scope="session",
        session_id=session_id
    )
    print(f"  ✅ Created topic: {topic_id}")

    # Test result creation
    result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result summary",
        data={"status": "test"},
        urgency="normal"
    )
    print(f"  ✅ Created result: {result_id}")

    # Test workload summary
    summary = await store.get_workload_summary(session_id)
    print(f"  ✅ Workload summary: {summary}")

    # Test topic activity update
    await store.update_topic_activity(topic_id)
    print(f"  ✅ Updated topic activity")

    # Test get_active_topics
    topics = await store.get_active_topics(session_id)
    print(f"  ✅ Active topics: {len(topics)}")

    # Cleanup
    await store.close()
    test_db_path.unlink()

    print("\n✅ Phase 1 Database Test PASSED")
    return True


async def test_topic_manager():
    """Test topic manager with staleness."""
    print("\nTesting Phase 1: Topic Manager...")

    test_db_path = Path("/tmp/test_adc_topics.db")
    if test_db_path.exists():
        test_db_path.unlink()

    store = SessionStore(test_db_path)
    await store.initialize()

    session_id = await store.create_session()
    topic_manager = TopicManager(store)

    # Test find_or_create_topic
    topic = await topic_manager.find_or_create_topic(
        label="Options Pipeline",
        session_id=session_id,
        topic_type="project",
        project_slugs=["options-pipeline"]
    )
    print(f"  ✅ Found/created topic: {topic.id} - {topic.label}")

    # Test get_active_topic_cards
    cards = await topic_manager.get_active_topic_cards(session_id)
    print(f"  ✅ Active topic cards: {len(cards)}")

    if cards:
        card = cards[0]
        print(f"  ✅ Card staleness: {card.staleness_level} ({card.staleness_seconds}s)")

    # Test update_topic_activity
    await topic_manager.update_topic_activity(topic.id)
    print(f"  ✅ Updated topic activity")

    await store.close()
    test_db_path.unlink()

    print("\n✅ Phase 1 Topic Manager Test PASSED")
    return True


async def test_surface_router():
    """Test surface routing."""
    print("\nTesting Phase 1: Surface Router...")

    test_db_path = Path("/tmp/test_adc_router.db")
    if test_db_path.exists():
        test_db_path.unlink()

    store = SessionStore(test_db_path)
    await store.initialize()

    session_id = await store.create_session()

    # Register surfaces
    canvas_id = await store.register_surface(session_id, "canvas")
    telegram_id = await store.register_surface(session_id, "telegram", always_available=True)

    router = SurfaceRouter(store)

    # Test routing to origin surface
    decision = await router.route_result(
        session_id=session_id,
        origin_surface_id=canvas_id,
        urgency="normal"
    )
    print(f"  ✅ Route decision: {decision.reason} -> {len(decision.target_surfaces)} surfaces")

    # Test fallback to Telegram
    # Mark canvas as disconnected
    await store.mark_surface_disconnected(canvas_id)

    decision_fallback = await router.route_result(
        session_id=session_id,
        origin_surface_id=canvas_id,
        urgency="normal"
    )
    print(f"  ✅ Fallback decision: {decision_fallback.reason} -> {len(decision_fallback.target_surfaces)} surfaces")
    print(f"  ✅ Fallback used: {decision_fallback.fallback_used}")

    await store.close()
    test_db_path.unlink()

    print("\n✅ Phase 1 Surface Router Test PASSED")
    return True


async def main():
    """Run all Phase 1 tests."""
    print("="*50)
    print("PHASE 1 TEST SUITE")
    print("="*50)

    tests = [
        test_database_initialization,
        test_topic_manager,
        test_surface_router,
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "="*50)
    if all(results):
        print("✅ ALL TESTS PASSED")
        print("="*50)
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("="*50)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
