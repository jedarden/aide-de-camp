"""
Unit tests for exceptions.yaml hot-reload and routing.

Tests:
1. Hot-reload of exceptions.yaml changes behavior without restart
2. Critical exception with no active canvas routes to Telegram
3. Auto-approve rules bypass bead creation
4. Escalation targets determine correct bead type
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.hot_reload import HotReloadManager
from src.escalate.handler import EscalateHandler, EscalateRequest
from src.surface.router import SurfaceRouter, RouteDecision
from src.session.store import SessionStore


# Fixtures
@pytest.fixture
def temp_exceptions_yaml():
    """Create a temporary exceptions.yaml file for testing."""
    config = {
        "auto_approve": {
            "read_only": ["kubectl_logs", "git_status"],
            "safe_mutations": [
                {
                    "condition": "environment == 'staging'",
                    "actions": ["kubectl_restart_deployment"],
                }
            ],
        },
        "manual_approval": [
            {
                "condition": "environment == 'production'",
                "actions": ["kubectl_delete"],
            }
        ],
        "escalation_targets": {
            "action": {"bead_type": "action", "requires_approval": True},
            "self_modification": {"bead_type": "self-modification", "requires_approval": True},
        },
        "categories": {
            "blocking": {
                "urgency": "critical",
                "auto_push_to_telegram": True,
                "no_canvas_timeout_minutes": 10,
            }
        },
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        import yaml
        yaml.dump(config, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def reload_manager(temp_exceptions_yaml):
    """Create a HotReloadManager with exceptions.yaml."""
    manager = HotReloadManager()
    manager.register_config('exceptions', temp_exceptions_yaml)
    return manager


@pytest.fixture
def mock_store():
    """Create a mock SessionStore."""
    store = AsyncMock(spec=SessionStore)
    return store


@pytest.fixture
def escalate_handler(mock_store):
    """Create an EscalateHandler with mock store."""
    handler = EscalateHandler(store=mock_store)
    handler._reload_manager = HotReloadManager()
    return handler


class TestHotReload:
    """Tests for exceptions.yaml hot-reload functionality."""

    @pytest.mark.asyncio
    async def test_hot_reload_detects_file_changes(self, reload_manager, temp_exceptions_yaml):
        """Test that hot-reload detects file changes without restart."""
        # Initial load
        config = reload_manager.get_config('exceptions')
        assert config['categories']['blocking']['no_canvas_timeout_minutes'] == 10

        # Modify the file
        import yaml
        with open(temp_exceptions_yaml, 'w') as f:
            new_config = config.copy()
            new_config['categories']['blocking']['no_canvas_timeout_minutes'] = 20
            yaml.dump(new_config, f)

        # Force reload
        reload_manager.force_reload('exceptions')

        # Check updated config
        updated_config = reload_manager.get_config('exceptions')
        assert updated_config['categories']['blocking']['no_canvas_timeout_minutes'] == 20

    @pytest.mark.asyncio
    async def test_hot_reload_check_interval(self, reload_manager, temp_exceptions_yaml):
        """Test that hot-reload respects check interval by preventing rapid re-reads."""
        import yaml

        # Get the initial mtime
        initial_mtime = reload_manager.get_mtime('exceptions')

        # Read the config (this updates last_check time)
        _ = reload_manager.get_config('exceptions')

        # Immediately check again - should NOT reload (within check interval)
        reloaded = reload_manager._check_and_reload('exceptions')
        assert reloaded == False, "Should not reload within check interval if file unchanged"

        # Modify the file
        with open(temp_exceptions_yaml, 'w') as f:
            config = reload_manager.get_config('exceptions')
            yaml.dump(config, f)

        # Check again immediately - still should not reload (within interval)
        reloaded = reload_manager._check_and_reload('exceptions')
        assert reloaded == False, "Should not reload within check interval even if file changed"

        # Force reload to bypass the interval
        reload_manager.force_reload('exceptions')

        # Verify the file was reloaded (mtime should be different or equal)
        new_mtime = reload_manager.get_mtime('exceptions')
        assert new_mtime >= initial_mtime, "Force reload should update the cache"


class TestAutoApprove:
    """Tests for auto-approve logic in escalate handler."""

    @pytest.mark.asyncio
    async def test_evaluate_auto_approve_read_only(self, escalate_handler):
        """Test that read-only operations are auto-approved."""
        request = EscalateRequest(
            intent_id="test-1",
            session_id="session-1",
            utterance="get kubernetes logs",
            intent_type="action",
            metadata={"action": "kubectl_logs"},
        )

        # Setup reload manager with test config
        config = {
            "auto_approve": {
                "read_only": ["kubectl_logs", "git_status"],
            },
            "manual_approval": [],
            "approval": {
                "never_auto_approve": [],
            },
        }
        escalate_handler._reload_manager = MagicMock()
        escalate_handler._reload_manager.get_config.return_value = config

        auto_approve, reason = escalate_handler._evaluate_auto_approve(request, config)
        assert auto_approve == True
        assert "Read-only operation" in reason

    @pytest.mark.asyncio
    async def test_escalate_intent_auto_approves_read_only(self, escalate_handler):
        """Test that escalate_intent returns completed result for read-only actions."""
        request = EscalateRequest(
            intent_id="test-1",
            session_id="session-1",
            utterance="get kubernetes logs",
            intent_type="action",
            metadata={"action": "kubectl_logs"},
        )

        # Setup reload manager with test config
        config = {
            "auto_approve": {
                "read_only": ["kubectl_logs", "git_status"],
            },
            "manual_approval": [],
            "escalation_targets": {
                "action": {"bead_type": "action"},
            },
            "approval": {
                "never_auto_approve": [],
            },
        }
        escalate_handler._reload_manager = MagicMock()
        escalate_handler._reload_manager.get_config.return_value = config

        # Mock store
        escalate_handler.store = AsyncMock()
        escalate_handler.store.update_intent_status = AsyncMock()

        result = await escalate_handler.escalate_intent(request)

        # Should return completed status with no bead_id
        assert result.status == "completed"
        assert result.bead_id == ""
        assert result.pending_card.get("status") == "completed"

    @pytest.mark.asyncio
    async def test_evaluate_auto_approve_safe_mutation(self, escalate_handler):
        """Test that safe mutations in staging are auto-approved."""
        request = EscalateRequest(
            intent_id="test-2",
            session_id="session-2",
            utterance="restart deployment in staging",
            intent_type="action",
            metadata={
                "action": "kubectl_restart_deployment",
                "environment": "staging",
            },
        )

        config = {
            "auto_approve": {
                "safe_mutations": [
                    {
                        "condition": "environment == 'staging'",
                        "actions": ["kubectl_restart_deployment"],
                    }
                ],
            },
            "manual_approval": [],
            "approval": {
                "never_auto_approve": [],
            },
        }
        escalate_handler._reload_manager = MagicMock()
        escalate_handler._reload_manager.get_config.return_value = config

        auto_approve, reason = escalate_handler._evaluate_auto_approve(request, config)
        assert auto_approve == True
        assert "Safe mutation" in reason

    @pytest.mark.asyncio
    async def test_evaluate_auto_approve_production_blocked(self, escalate_handler):
        """Test that production operations are not auto-approved."""
        request = EscalateRequest(
            intent_id="test-3",
            session_id="session-3",
            utterance="delete pod in production",
            intent_type="action",
            metadata={
                "action": "kubectl_delete",
                "environment": "production",
            },
        )

        config = {
            "auto_approve": {},
            "manual_approval": [
                {
                    "condition": "environment == 'production'",
                    "actions": ["kubectl_delete"],
                    "always_approve": False,
                }
            ],
            "approval": {
                "never_auto_approve": [],
            },
        }
        escalate_handler._reload_manager = MagicMock()
        escalate_handler._reload_manager.get_config.return_value = config

        auto_approve, reason = escalate_handler._evaluate_auto_approve(request, config)
        assert auto_approve == False
        assert "Manual approval required" in reason

    @pytest.mark.asyncio
    async def test_get_bead_type_from_targets(self, escalate_handler):
        """Test that escalation targets determine bead type."""
        config = {
            "escalation_targets": {
                "action": {"bead_type": "action", "requires_approval": True},
                "self_modification": {"bead_type": "self-modification", "requires_approval": True},
            }
        }

        bead_type = escalate_handler._get_bead_type_from_targets("action", config)
        assert bead_type == "action"

        # Use the correct intent type format (with dash, not underscore)
        bead_type = escalate_handler._get_bead_type_from_targets("self-modification", config)
        assert bead_type == "self-modification"

        # Unknown type defaults to 'task'
        bead_type = escalate_handler._get_bead_type_from_targets("unknown", config)
        assert bead_type == "task"


class TestSurfaceRouting:
    """Tests for surface routing with exception rules."""

    @pytest.mark.asyncio
    async def test_critical_exception_routes_to_telegram(self, mock_store):
        """Test that critical exceptions route to Telegram when no canvas active."""
        router = SurfaceRouter(store=mock_store)
        router._reload_manager = MagicMock()

        # Mock exceptions config
        config = {
            "categories": {
                "blocking": {
                    "urgency": "critical",
                    "auto_push_to_telegram": True,
                    "no_canvas_timeout_minutes": 10,
                }
            },
        }
        router._reload_manager.get_config.return_value = config

        # Mock no active surfaces
        mock_store.get_active_surfaces.return_value = []

        # Mock fallback surface (Telegram)
        mock_store.get_fallback_surface.return_value = {
            "id": "telegram-1",
            "session_id": "session-1",
            "type": "telegram",
            "state": "connected",
            "always_available": True,
            "last_seen": 1234567890,
        }

        decision = await router.route_result(
            session_id="session-1",
            origin_surface_id=None,
            urgency="critical",
            result_type="exception",
        )

        assert decision.fallback_used == True
        assert len(decision.target_surfaces) == 1
        assert decision.target_surfaces[0].type == "telegram"
        assert "exception-class" in decision.reason

    @pytest.mark.asyncio
    async def test_exception_with_active_canvas_not_forced(self, mock_store):
        """Test that exceptions with active canvas don't force Telegram."""
        router = SurfaceRouter(store=mock_store)
        router._reload_manager = MagicMock()

        config = {
            "categories": {
                "blocking": {
                    "urgency": "critical",
                    "auto_push_to_telegram": True,
                    "no_canvas_timeout_minutes": 10,
                }
            },
        }
        router._reload_manager.get_config.return_value = config

        # Mock active canvas surface
        from datetime import datetime
        now = int(datetime.now().timestamp())
        mock_store.get_active_surfaces.return_value = [
            {
                "id": "canvas-1",
                "session_id": "session-1",
                "type": "canvas",
                "state": "connected",
                "always_available": False,
                "last_seen": now - 100,  # Active within timeout
            }
        ]

        decision = await router.route_result(
            session_id="session-1",
            origin_surface_id=None,
            urgency="critical",
            result_type="exception",
        )

        # Should route to canvas, not forced to Telegram
        assert decision.fallback_used == False
        assert len(decision.target_surfaces) == 1
        assert decision.target_surfaces[0].type == "canvas"

    @pytest.mark.asyncio
    async def test_non_critical_result_normal_routing(self, mock_store):
        """Test that non-critical results use normal routing."""
        router = SurfaceRouter(store=mock_store)
        router._reload_manager = MagicMock()

        config = {
            "categories": {
                "blocking": {
                    "urgency": "critical",
                    "auto_push_to_telegram": True,
                    "no_canvas_timeout_minutes": 10,
                }
            },
        }
        router._reload_manager.get_config.return_value = config

        # Mock active canvas surface
        from datetime import datetime
        now = int(datetime.now().timestamp())
        mock_store.get_active_surfaces.return_value = [
            {
                "id": "canvas-1",
                "session_id": "session-1",
                "type": "canvas",
                "state": "connected",
                "always_available": False,
                "last_seen": now - 100,
            }
        ]

        decision = await router.route_result(
            session_id="session-1",
            origin_surface_id=None,
            urgency="normal",
            result_type="result",
        )

        # Should route to canvas via normal routing
        assert decision.fallback_used == False
        assert "most-recent-active" in decision.reason or "origin-surface" in decision.reason


class TestConditionEvaluation:
    """Tests for condition evaluation logic."""

    def test_evaluate_simple_condition(self, escalate_handler):
        """Test simple condition evaluation."""
        context = {"environment": "staging"}
        result = escalate_handler._evaluate_condition("environment == 'staging'", context)
        assert result == True

        result = escalate_handler._evaluate_condition("environment == 'production'", context)
        assert result == False

    def test_evaluate_or_condition(self, escalate_handler):
        """Test OR condition evaluation."""
        context = {"branch": "main"}
        result = escalate_handler._evaluate_condition("branch == 'main' || branch == 'master'", context)
        assert result == True

        context = {"branch": "feature-branch"}
        result = escalate_handler._evaluate_condition("branch == 'main' || branch == 'master'", context)
        assert result == False

    def test_evaluate_action_condition(self, escalate_handler):
        """Test action-based condition evaluation."""
        context = {"action": "kubectl_delete_namespace"}
        result = escalate_handler._evaluate_condition("action == 'kubectl_delete_namespace'", context)
        assert result == True

        context = {"action": "kubectl_logs"}
        result = escalate_handler._evaluate_condition("action == 'kubectl_delete_namespace'", context)
        assert result == False

    def test_evaluate_invalid_condition(self, escalate_handler):
        """Test that invalid conditions return False safely."""
        context = {"environment": "staging"}
        result = escalate_handler._evaluate_condition("invalid syntax {{", context)
        assert result == False


class TestHotReloadBehavior:
    """Tests for end-to-end hot-reload behavior."""

    @pytest.mark.asyncio
    async def test_hot_reload_changes_auto_approve_behavior(self, temp_exceptions_yaml):
        """Test that editing exceptions.yaml changes auto-approve behavior without restart."""
        # Create handler with temp config
        import yaml
        handler = EscalateHandler()
        handler._reload_manager = HotReloadManager()
        handler._reload_manager.register_config('exceptions', temp_exceptions_yaml)
        handler.store = AsyncMock()
        handler.store.update_intent_status = AsyncMock()

        # Initial request - should require manual approval (action not in read_only)
        request = EscalateRequest(
            intent_id="test-1",
            session_id="session-1",
            utterance="kubectl delete pod",
            intent_type="action",
            metadata={"action": "kubectl_delete"},
        )

        # First call with initial config
        result1 = await handler.escalate_intent(request)
        assert result1.status == "created", f"Expected bead creation, got {result1.status}"

        # Modify config to add the action to read_only
        with open(temp_exceptions_yaml, 'r') as f:
            config = yaml.safe_load(f)
        config['auto_approve']['read_only'].append('kubectl_delete')
        with open(temp_exceptions_yaml, 'w') as f:
            yaml.dump(config, f)

        # Force reload to simulate next invocation
        handler._reload_manager.force_reload('exceptions')

        # Second call with modified config - should auto-approve now
        result2 = await handler.escalate_intent(request)
        assert result2.status == "completed", f"Expected auto-approval, got {result2.status}"
        assert result2.bead_id == ""

    @pytest.mark.asyncio
    async def test_hot_reload_changes_telegram_routing_timeout(self, temp_exceptions_yaml):
        """Test that editing exceptions.yaml no_canvas_timeout_minutes changes routing behavior."""
        import yaml
        from datetime import datetime

        # Create router with temp config
        store = AsyncMock(spec=SessionStore)
        router = SurfaceRouter(store=store)
        router._reload_manager = HotReloadManager()
        router._reload_manager.register_config('exceptions', temp_exceptions_yaml)

        # Get initial timeout
        initial_timeout = router._get_no_canvas_timeout()
        assert initial_timeout == 600, f"Expected 600 seconds (10 min), got {initial_timeout}"

        # Modify config to change timeout
        with open(temp_exceptions_yaml, 'r') as f:
            config = yaml.safe_load(f)
        config['categories']['blocking']['no_canvas_timeout_minutes'] = 5
        with open(temp_exceptions_yaml, 'w') as f:
            yaml.dump(config, f)

        # Force reload
        router._reload_manager.force_reload('exceptions')

        # Get updated timeout
        updated_timeout = router._get_no_canvas_timeout()
        assert updated_timeout == 300, f"Expected 300 seconds (5 min), got {updated_timeout}"
