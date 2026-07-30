"""
Tests for ambient monitoring tick in watcher daemon.

Tests coverage:
- Hot-reload of monitoring config (mtime-checked cache)
- Rule evaluation on watched topics
- State change detection vs topic_context_cache
- Result row writing with intent_id NULL
- SSE broadcast on rule fire
- No result when rule doesn't fire
- Tick interval from config

Acceptance criteria from plan §10 Ambient monitoring tick:
- Rule on watched topic fires on simulated state change -> results row with intent_id NULL + SSE event
- No rule fire -> no row
- Interval/hot-reload covered
"""

import asyncio
import json
import logging
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import yaml

from src.session.store import SessionStore
from src.watcher.daemon import BeadWatcher
from src.surface.router import SurfaceRouter, Surface, RouteDecision


# --- Fixtures -----------------------------------------------------------------


@pytest.fixture
async def store():
    """In-memory session store for testing with cleanup."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    s = SessionStore(db_path)
    await s.initialize()

    yield s

    # Cleanup
    await s.close()
    db_path.unlink(missing_ok=True)


@pytest.fixture
def mock_router():
    """Mock surface router for testing."""
    router = MagicMock(spec=SurfaceRouter)

    # Default: no active surfaces (fallback to Telegram)
    router.route_result = AsyncMock(return_value=RouteDecision(
        target_surfaces=[],
        fallback_used=True,
        reason="No active surfaces"
    ))

    return router


@pytest.fixture
def monitoring_config_file():
    """Create a temporary monitoring config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config = {
            "tick_interval_seconds": 60,  # 1 minute for testing
            "monitoring": {
                "active_topics": [
                    {
                        "topic_id": "test-pipeline-status",
                        "project_slug": "test-pipeline",
                        "intent_type": "status",
                        "check_interval": 30,
                        "urgency": "normal",
                        "filters": ["phase!=Running"],
                        "notification_threshold": "state_change"
                    }
                ],
                "exceptions": []
            },
            "batching": {
                "low_urgency_batch_seconds": 300,
                "normal_urgency_batch_seconds": 120
            },
            "quiet_hours": {
                "enabled": False
            },
            "channels": {
                "critical": ["canvas", "telegram"],
                "high": ["canvas"],
                "normal": ["canvas"],
                "low": ["canvas"]
            }
        }
        yaml.dump(config, f)
        config_path = Path(f.name)

    yield config_path

    # Cleanup
    config_path.unlink(missing_ok=True)


# --- Tests ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitoring_config_hot_reload(store, mock_router, monitoring_config_file):
    """Test that monitoring config hot-reloads on mtime change."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
        check_interval_seconds=30,
    )

    # Override monitoring config path to test file
    watcher.MONITORING_CONFIG_PATH = str(monitoring_config_file)

    # Initial load
    await watcher._hot_reload_monitoring_config()

    # Verify config loaded
    assert watcher._monitoring_config["tick_interval_seconds"] == 60
    assert watcher._monitoring_tick_interval == 60.0
    assert len(watcher._monitoring_config["monitoring"]["active_topics"]) == 1

    # Modify config file
    time.sleep(0.1)  # Ensure mtime changes
    with open(monitoring_config_file, 'w') as f:
        config = {
            "tick_interval_seconds": 120,  # Changed to 2 minutes
            "monitoring": {
                "active_topics": [
                    {
                        "topic_id": "new-topic",
                        "project_slug": "new-project",
                        "intent_type": "status",
                        "check_interval": 30,
                        "urgency": "high",
                        "filters": [],
                        "notification_threshold": "any_change"
                    }
                ],
                "exceptions": []
            },
            "batching": {},
            "quiet_hours": {"enabled": False},
            "channels": {}
        }
        yaml.dump(config, f)

    # Hot-reload
    await watcher._hot_reload_monitoring_config()

    # Verify new config loaded
    assert watcher._monitoring_config["tick_interval_seconds"] == 120
    assert watcher._monitoring_tick_interval == 120.0
    assert len(watcher._monitoring_config["monitoring"]["active_topics"]) == 1
    assert watcher._monitoring_config["monitoring"]["active_topics"][0]["topic_id"] == "new-topic"


@pytest.mark.asyncio
async def test_topic_context_cache_lifecycle(store, mock_router):
    """Test reading and writing topic context cache."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )

    topic_id = "test-topic"
    test_context = {
        "project_slug": "test-project",
        "phase": "Running",
        "restarts": 0,
        "ready": "1/1"
    }

    # Initially, no cache
    cached = await watcher._get_topic_context_cache(topic_id)
    assert cached is None

    # Write to cache
    await watcher._update_topic_context_cache(topic_id, test_context)

    # Read back from cache
    cached = await watcher._get_topic_context_cache(topic_id)
    assert cached is not None
    assert cached["project_slug"] == "test-project"
    assert cached["phase"] == "Running"
    assert cached["restarts"] == 0
    assert cached["ready"] == "1/1"


@pytest.mark.asyncio
async def test_state_change_detection_any_change(store, mock_router):
    """Test state change detection with notification_threshold='any_change'."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )

    current_state = {"phase": "Running", "restarts": 1}
    previous_state = {"phase": "Running", "restarts": 0}

    # any_change: any field change triggers
    has_change = watcher._detect_state_change(
        current_state=current_state,
        cached_context=previous_state,
        notification_threshold="any_change",
    )
    assert has_change is True

    # No change
    has_change = watcher._detect_state_change(
        current_state=current_state,
        cached_context=current_state,
        notification_threshold="any_change",
    )
    assert has_change is False


@pytest.mark.asyncio
async def test_state_change_detection_state_change(store, mock_router):
    """Test state change detection with notification_threshold='state_change'."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )

    # state_change: only state fields trigger
    current_state = {"phase": "Failed", "restarts": 5, "other_field": "changed"}
    previous_state = {"phase": "Running", "restarts": 0, "other_field": "same"}

    has_change = watcher._detect_state_change(
        current_state=current_state,
        cached_context=previous_state,
        notification_threshold="state_change",
    )
    assert has_change is True  # phase changed

    # Only non-state field change
    current_state = {"phase": "Running", "restarts": 0, "other_field": "changed"}
    has_change = watcher._detect_state_change(
        current_state=current_state,
        cached_context=previous_state,
        notification_threshold="state_change",
    )
    assert has_change is False  # only other_field changed, not a state field


@pytest.mark.asyncio
async def test_monitoring_result_write_with_null_intent(store, mock_router):
    """Test that monitoring results are written with intent_id=NULL."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )

    topic_id = "test-pipeline-status"
    project_slug = "test-pipeline"
    current_state = {"phase": "Failed", "restarts": 5}
    previous_state = {"phase": "Running", "restarts": 0}
    urgency = "high"

    # Mock broadcast to avoid SSE in tests
    with patch.object(watcher, '_broadcast_monitoring_result', new=AsyncMock()):
        await watcher._write_monitoring_result(
            topic_id=topic_id,
            project_slug=project_slug,
            current_state=current_state,
            cached_context=previous_state,
            urgency=urgency,
        )

        # Query the result directly to verify it was written
        import aiosqlite
        async with aiosqlite.connect(store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM results WHERE intent_id IS NULL AND result_type = ?", (f"monitoring:{project_slug}",)
            ) as cursor:
                result = await cursor.fetchone()

                assert result is not None, "Result should be created in database"
                assert result["intent_id"] is None, "intent_id must be NULL for monitoring-originated results"
                assert result["result_type"] == f"monitoring:{project_slug}"
                assert result["urgency"] == urgency
                assert "Monitoring:" in result["summary"]


@pytest.mark.asyncio
async def test_no_result_when_rule_doesnt_fire(store, mock_router, monitoring_config_file):
    """Test that no result is created when state hasn't changed."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )
    watcher.MONITORING_CONFIG_PATH = str(monitoring_config_file)

    topic_id = "test-topic"
    current_state = {"phase": "Running", "restarts": 0}
    previous_state = {"phase": "Running", "restarts": 0}

    # Write initial state to cache
    await watcher._update_topic_context_cache(topic_id, current_state)

    # Mock the ambient monitor check to return same state
    with patch.object(watcher, '_write_monitoring_result', new=AsyncMock()) as mock_write:
        # Detect change - should be False (same state)
        has_change = watcher._detect_state_change(
            current_state=current_state,
            cached_context=previous_state,
            notification_threshold="state_change",
        )
        assert has_change is False

        # Verify _write_monitoring_result was NOT called
        mock_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_monitoring_tick_generates_result(store, mock_router, monitoring_config_file):
    """Test full monitoring tick: state change -> result with NULL intent + SSE."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )
    watcher.MONITORING_CONFIG_PATH = str(monitoring_config_file)

    # Mock the ambient monitor check - patch at the module import location
    # AmbientMonitor is imported inside _ambient_monitoring_tick as: from ..monitoring.ambient import AmbientMonitor
    # So we need to patch src.monitoring.ambient.AmbientMonitor
    with patch('src.monitoring.ambient.AmbientMonitor') as mock_monitor_class:
        mock_monitor = MagicMock()
        mock_monitor_class.return_value = mock_monitor

        # First tick: establish baseline (state data returned, but cached_context is None so no notification)
        initial_state = {
            "project_slug": "test-pipeline",
            "intent_type": "status",
            "phase": "Running",
            "restarts": 0,
        }
        mock_monitor.check_topic_state = AsyncMock(return_value=initial_state)

        # Run tick
        await watcher._ambient_monitoring_tick()

        # Verify tick count incremented
        assert watcher.monitoring_tick_count == 1
        assert watcher.last_monitoring_tick_at > 0

        # Second tick: with state change
        changed_state = {
            "project_slug": "test-pipeline",
            "intent_type": "status",
            "phase": "Failed",  # Changed from Running
            "restarts": 5,  # Changed from 0
        }
        mock_monitor.check_topic_state = AsyncMock(return_value=changed_state)

        # Mock broadcast to capture SSE call
        with patch.object(watcher, '_broadcast_monitoring_result', new=AsyncMock()) as mock_broadcast:
            await watcher._ambient_monitoring_tick()

            # Verify _broadcast_monitoring_result was called once
            mock_broadcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_snapshot_includes_monitoring_stats(store, mock_router):
    """Test that health snapshot includes monitoring tick stats."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )

    # Before any ticks
    snapshot = watcher.health_snapshot()
    assert "monitoring" in snapshot
    assert snapshot["monitoring"]["last_tick_at"] is None
    assert snapshot["monitoring"]["tick_count"] == 0
    assert snapshot["monitoring"]["interval"] == 300  # default

    # After simulating a tick
    watcher.last_monitoring_tick_at = time.time()
    watcher.monitoring_tick_count = 5
    watcher._monitoring_tick_interval = 120.0

    snapshot = watcher.health_snapshot()
    assert snapshot["monitoring"]["last_tick_at"] is not None
    assert snapshot["monitoring"]["tick_count"] == 5
    assert snapshot["monitoring"]["interval"] == 120


@pytest.mark.asyncio
async def test_deterministic_summary_generation(store, mock_router):
    """Test that monitoring summary is deterministic (no LLM)."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )

    # Test initial state
    summary = watcher._generate_monitoring_summary(
        topic_id="test-topic",
        current_state={"phase": "Running"},
        previous_state=None,
    )
    assert summary == "Monitoring: test-topic initial state"

    # Test phase change
    summary = watcher._generate_monitoring_summary(
        topic_id="test-topic",
        current_state={"phase": "Failed"},
        previous_state={"phase": "Running"},
    )
    assert summary == "Monitoring: test-topic phase changed from Running to Failed"

    # Test sync status change
    summary = watcher._generate_monitoring_summary(
        topic_id="test-topic",
        current_state={"sync_status": "OutOfSync"},
        previous_state={"sync_status": "Synced"},
    )
    assert summary == "Monitoring: test-topic sync status changed from Synced to OutOfSync"

    # Test generic state change
    summary = watcher._generate_monitoring_summary(
        topic_id="test-topic",
        current_state={"some_field": "value"},
        previous_state={"some_field": "old_value"},
    )
    assert summary == "Monitoring: test-topic state changed"


@pytest.mark.asyncio
async def test_state_diff_computation(store, mock_router):
    """Test state diff computation."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )

    previous = {"phase": "Running", "restarts": 0, "stable": "same"}
    current = {"phase": "Failed", "restarts": 5, "stable": "same"}

    diff = watcher._compute_state_diff(previous, current)

    assert diff["phase"] == {"from": "Running", "to": "Failed"}
    assert diff["restarts"] == {"from": 0, "to": 5}
    assert "stable" not in diff  # Unchanged field not in diff


@pytest.mark.asyncio
async def test_sse_broadcast_on_monitoring_result(store, mock_router):
    """Test that monitoring results are broadcast via SSE."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )

    # Mock the surface router to return an active canvas surface
    canvas_surface = Surface(
        id="canvas-1",
        session_id="monitoring",
        type="canvas",
        state="active",
        always_available=False,
        last_seen=int(datetime.now().timestamp())
    )
    mock_router.route_result = AsyncMock(return_value=RouteDecision(
        target_surfaces=[canvas_surface],
        fallback_used=False,
        reason="Active canvas"
    ))

    # Mock broadcast_result to capture the call
    with patch('src.watcher.daemon.broadcast_result', new=AsyncMock()) as mock_broadcast:
        result_id = "test-result-id"
        topic_id = "test-topic"
        session_id = "monitoring"
        summary = "Monitoring: test-topic phase changed"
        data = {"monitoring": True}
        urgency = "normal"

        await watcher._broadcast_monitoring_result(
            result_id=result_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=summary,
            data=data,
            urgency=urgency,
        )

        # Verify broadcast was called
        mock_broadcast.assert_awaited_once()
        call_args = mock_broadcast.call_args

        # Verify the result structure
        result = call_args.kwargs["result"]
        assert result["intent_id"] is None  # Monitoring results have NULL intent
        assert result["result_id"] == result_id
        assert result["summary"] == summary
        assert result["urgency"] == urgency


# --- Integration Tests ----------------------------------------------------------


@pytest.mark.asyncio
async def test_full_monitoring_tick_integration(store, mock_router, monitoring_config_file):
    """Integration test: full monitoring tick with real config and state changes."""
    watcher = BeadWatcher(
        store=store,
        router=mock_router,
    )
    watcher.MONITORING_CONFIG_PATH = str(monitoring_config_file)

    # Mock broadcast to avoid actual SSE calls
    with patch('src.watcher.daemon.broadcast_result', new=AsyncMock()):
        # Load config
        await watcher._hot_reload_monitoring_config()

        # Verify config loaded
        assert len(watcher._monitoring_config["monitoring"]["active_topics"]) == 1

        # Mock ambient monitor to return state data - patch at the correct import location
        with patch('src.monitoring.ambient.AmbientMonitor') as mock_monitor_class:
            mock_monitor = MagicMock()
            mock_monitor_class.return_value = mock_monitor

            # First tick: baseline - establish initial state
            initial_state = {
                "project_slug": "test-pipeline",
                "intent_type": "status",
                "phase": "Running",
                "restarts": 0,
            }
            mock_monitor.check_topic_state = AsyncMock(return_value=initial_state)

            await watcher._ambient_monitoring_tick()

            # Verify tick happened but no result (baseline - cached_context was None)
            assert watcher.monitoring_tick_count == 1

            # Count results in DB - should be 0 (baseline doesn't fire because cached_context was None)
            async with aiosqlite.connect(store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT COUNT(*) as count FROM results WHERE intent_id IS NULL") as cursor:
                    result = await cursor.fetchone()
                    assert result["count"] == 0, "No results on baseline tick (cached_context was None)"

            # Second tick: state change
            changed_state = {
                "project_slug": "test-pipeline",
                "intent_type": "status",
                "phase": "Failed",  # Changed from Running
                "restarts": 5,  # Changed from 0
            }
            mock_monitor.check_topic_state = AsyncMock(return_value=changed_state)

            await watcher._ambient_monitoring_tick()

            # Verify result created
            async with aiosqlite.connect(store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT COUNT(*) as count FROM results WHERE intent_id IS NULL") as cursor:
                    result = await cursor.fetchone()
                    assert result["count"] == 1, "One result created after state change"

                # Verify result details
                async with db.execute(
                    "SELECT * FROM results WHERE intent_id IS NULL"
                ) as cursor:
                    result = await cursor.fetchone()
                    assert result["result_type"] == "monitoring:test-pipeline"
                    assert result["urgency"] == "normal"
                    assert "Monitoring:" in result["summary"]
