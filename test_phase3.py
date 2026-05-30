#!/usr/bin/env python3
"""
Phase 3 Tests: Responsiveness - ambient monitoring + pre-warmed context

Tests for:
- Ambient monitoring state change detection
- Diff-aware results
- Pre-warmed context refresh
- Multi-turn conversation tracking
- Speculative pre-fetch
- Notification batching in audio mode
- Implicit feedback signal tracking
"""

import asyncio
import tempfile
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def test_conversation_tracker():
    """Test multi-turn conversation tracking."""
    from src.conversation.tracker import get_conversation_tracker

    tracker = get_conversation_tracker()
    session_id = "test-session-1"

    # Record first turn
    turn1 = await tracker.record_turn(
        session_id=session_id,
        utterance="What's the status of options-pipeline?",
        primary_topic_id="topic-1",
        is_follow_up=False,
    )

    # Check focus
    focus = tracker.get_focus(session_id)
    assert focus is not None, "Focus should be set after first turn"
    assert focus.primary_topic_id == "topic-1", "Focus should be on topic-1"

    # Detect follow-up
    is_follow_up, suggested = await tracker.detect_follow_up(
        session_id=session_id,
        utterance="why is it slow?",
        detected_topics=["topic-1"],
    )

    assert is_follow_up, "Should detect follow-up with pronoun"
    assert suggested == "topic-1", "Should suggest current focus topic"

    print("✓ Conversation tracker test passed")


async def test_prefetcher():
    """Test speculative prefetcher."""
    from src.context.prefetch import get_prefetcher, FollowUpPattern

    prefetcher = get_prefetcher()
    topic_id = "test-topic-1"
    project_slugs = ["options-pipeline"]

    # Analyze utterance for prefetch predictions
    predictions = await prefetcher.analyze_utterance(
        session_id="test-session",
        utterance="how long until it finishes?",
        topic_id=topic_id,
        project_slugs=project_slugs,
        intent_type="status",
    )

    assert len(predictions) > 0, "Should generate predictions"
    assert any(p.pattern == FollowUpPattern.HOW_LONG for p in predictions), "Should detect HOW_LONG pattern"

    # Test cache
    prefetcher.get_prefetch_data(topic_id, FollowUpPattern.HOW_LONG)

    print("✓ Prefetcher test passed")


async def test_diff_engine():
    """Test diff engine for result comparison."""
    from src.diff.engine import get_diff_engine

    engine = get_diff_engine()

    topic_id = "test-topic-2"

    # Test first result (no previous state)
    diff1 = await engine.compute_diff(
        topic_id=topic_id,
        previous_result=None,
        current_result={
            "data": {
                "phase": "Running",
                "ready": "1/1",
                "restarts": 0,
            }
        },
    )

    assert not diff1.has_changes, "First result should have no changes"

    # Cache the result
    engine.cache_previous_result(topic_id, {"data": {"phase": "Running", "ready": "1/1", "restarts": 0}})

    # Test second result with changes
    diff2 = await engine.compute_diff(
        topic_id=topic_id,
        previous_result={"data": {"phase": "Running", "ready": "1/1", "restarts": 0, "age": "10m"}},
        current_result={
            "data": {
                "phase": "Failed",
                "ready": "0/1",
                "restarts": 5,
                "age": "12m",
            }
        },
    )

    assert diff2.has_changes, "Should detect changes"
    assert len(diff2.fields) == 4, "Should detect 4 changed fields (phase, ready, restarts, age)"
    assert "Failed" in diff2.change_summary, "Summary should include new phase"

    print("✓ Diff engine test passed")


async def test_batching():
    """Test notification batching for audio mode."""
    from src.realtime.batching import get_result_batcher, Urgency

    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""
batching:
  low_urgency_batch_seconds: 5
  normal_urgency_batch_seconds: 2
quiet_hours:
  enabled: false
""")
        config_path = Path(f.name)

    try:
        batcher = get_result_batcher(config_path)

        # Track narrated results
        narrated = []

        async def narrate_callback(results):
            narrated.extend(results)

        batcher.set_narrate_callback(narrate_callback)

        # Queue critical result - should narrate immediately
        await batcher.queue_result(
            result_id="crit-1",
            intent_id="intent-1",
            topic_id="topic-1",
            summary="Critical failure",
            data={},
            urgency="critical",
        )

        assert len(narrated) == 1, "Critical result should narrate immediately"
        assert narrated[0].urgency == Urgency.CRITICAL, "Should be critical urgency"

        # Queue normal result - should batch
        narrated.clear()
        await batcher.queue_result(
            result_id="norm-1",
            intent_id="intent-2",
            topic_id="topic-1",
            summary="Normal update",
            data={},
            urgency="normal",
        )

        # Wait for batch timer
        await asyncio.sleep(2.5)

        assert len(narrated) > 0, "Normal result should narrate after batch window"

        print("✓ Batching test passed")

    finally:
        config_path.unlink()


async def test_feedback_signals():
    """Test implicit feedback signal tracking."""
    from src.feedback.signals import get_feedback_tracker, SignalType

    tracker = get_feedback_tracker()
    session_id = "test-session-signals"
    result_id = "test-result-1"

    # Track result creation
    await tracker.track_result_created(result_id, session_id, "topic-1")

    # Track result acknowledgment
    signal = await tracker.track_result_acknowledged(
        result_id=result_id,
        session_id=session_id,
        surface_type="audio",
    )

    assert signal is not None, "Should generate ack_speed signal"
    assert signal.signal_type == SignalType.ACK_SPEED, "Should be ack_speed type"
    assert signal.data["quality"] == "positive", "Fast ack should be positive"

    print("✓ Feedback signals test passed")


async def test_context_warmer():
    """Test context warmer for active topics."""
    from src.context.warmer import get_context_warmer, ContextBundle

    warmer = get_context_warmer()

    # Create a context bundle
    bundle = ContextBundle(
        topic_id="test-topic-1",
        project_slugs=["options-pipeline"],
        kubectl_status={"pods": [{"name": "pod-1"}]},
    )

    # Check validity
    assert bundle.is_valid(), "Fresh bundle should be valid"

    # Test serialization
    bundle_dict = bundle.to_dict()
    assert "topic_id" in bundle_dict, "Bundle should serialize"
    assert "kubectl_status" in bundle_dict, "Bundle should include kubectl_status"

    # Test deserialization
    restored = ContextBundle.from_dict(bundle_dict)
    assert restored.topic_id == bundle.topic_id, "Should restore topic_id"

    print("✓ Context warmer test passed")


async def test_ambient_monitor():
    """Test ambient monitoring configuration loading."""
    from src.monitoring.ambient import get_ambient_monitor

    monitor = get_ambient_monitor()

    # Load config
    config = await monitor.load_config()

    assert len(config.active_topics) > 0, "Should have active topics"
    assert config.batching is not None, "Should have batching config"

    # Check batching rules
    assert config.batching["low_urgency_batch_seconds"] > 0, "Should have low urgency batch window"
    assert config.batching["normal_urgency_batch_seconds"] > 0, "Should have normal urgency batch window"

    # Check quiet hours
    assert config.quiet_hours is not None, "Should have quiet hours config"

    print("✓ Ambient monitor test passed")


async def main():
    """Run all Phase 3 tests."""
    tests = [
        ("Conversation Tracker", test_conversation_tracker),
        ("Prefetcher", test_prefetcher),
        ("Diff Engine", test_diff_engine),
        ("Batching", test_batching),
        ("Feedback Signals", test_feedback_signals),
        ("Context Warmer", test_context_warmer),
        ("Ambient Monitor", test_ambient_monitor),
    ]

    print("Running Phase 3 Tests...")
    print("=" * 50)

    for name, test_func in tests:
        try:
            await test_func()
        except AssertionError as e:
            print(f"✗ {name} test failed: {e}")
        except Exception as e:
            print(f"✗ {name} test error: {e}")
            import traceback
            traceback.print_exc()

    print("=" * 50)
    print("Phase 3 Tests Complete!")


if __name__ == "__main__":
    asyncio.run(main())
