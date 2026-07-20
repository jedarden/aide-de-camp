"""
Regression tests for the bead watcher daemon (fixes for bead adc-5wtm).

The BeadWatcher was a complete silent no-op for two reasons:
1. It watched `.beads/beads.jsonl` -- a file that has never existed. The real
   bead-forge (bf) checkpoint is `.beads/issues.jsonl`.
2. It read routing metadata from a nonexistent nested `metadata` object. bf
   issues have a flat `labels` array; escalate/handler.py encodes session_id,
   origin_surface_id, urgency, etc. as `key=value` label strings.

These tests pin the contract: the checkpoint path, label-based metadata
extraction, terminal-status handling (closed AND resolved), and that a closed
bead carrying a `session_id=...` label actually reaches the surface router
instead of early-returning.

No live SSE / Telegram / LLM calls: the surface router is an AsyncMock and we
assert on the routing attempt (route_result call kwargs).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.surface.router import RouteDecision
from src.telegram.fallback import TelegramFallback
from src.watcher.daemon import BeadWatcher

# --- fixtures ---------------------------------------------------------------

def _bead(
    bead_id: str = "adc-test1",
    status: str = "closed",
    labels: list[str] | None = None,
    description: str = "## Task\nDo the thing.\n\n## Acceptance Criteria\n- done",
    title: str = "Test bead",
    issue_type: str = "task",
) -> dict:
    """A schema-accurate bf issue (matches head -1 .beads/issues.jsonl)."""
    if labels is None:
        # The exact encoding escalate/handler.py's _create_bead writes.
        labels = [
            "created_at=1782995355",
            "intent_id=test-intent-1",
            "intent_type=action",
            "session_id=test-session-1",
            "origin_surface_id=surf-abc",
            "urgency=high",
        ]
    return {
        "id": bead_id,
        "title": title,
        "description": description,
        "design": "",
        "acceptance_criteria": "",
        "notes": "",
        "status": status,
        "priority": 2,
        "issue_type": issue_type,
        "assignee": "claude-code-glm-5-adc-p1",
        "created_at": "2026-07-03T00:06:28.417289564Z",
        "updated_at": "2026-07-19T22:42:37.385045363Z",
        "closed_at": "2026-07-19T22:42:37.385045363Z",
        "close_reason": "Completed",
        "source_repo": ".",
        "compaction_level": 0,
        "labels": labels,
        "dependencies": [],
    }


def _write_checkpoint(path: Path, beads: list[dict]) -> Path:
    """Write beads as JSONL (one JSON object per line)."""
    with open(path, "w") as f:
        for bead in beads:
            f.write(json.dumps(bead) + "\n")
    return path


@pytest.fixture
def router():
    """
    Mock surface router whose route_result returns an empty decision -- so the
    watcher reaches the routing call (proving it passed the no-session_id early
    return) but performs no SSE / Telegram side effects.
    """
    r = MagicMock()
    r.route_result = AsyncMock(
        return_value=RouteDecision(
            target_surfaces=[],
            reason="no-surface-available",
            fallback_used=False,
        )
    )
    return r


@pytest.fixture
def store():
    """The watcher stores this but never calls into it on the read/process path."""
    return MagicMock()


def _watcher(store, router, tmp_path, beads):
    checkpoint = _write_checkpoint(tmp_path / "issues.jsonl", beads)
    return BeadWatcher(store, router, beads_jsonl=str(checkpoint))


# --- path regression --------------------------------------------------------

class TestCheckpointPath:
    """The default checkpoint path is the real bf issues.jsonl (adc-5wtm bug #1)."""

    def test_default_beads_jsonl_is_real_issues_checkpoint(self):
        # Must be the real file, absolute (server may launch from any CWD), and
        # NOT the never-existed ".beads/beads.jsonl".
        assert BeadWatcher.BEADS_JSONL == "/home/coding/aide-de-camp/.beads/issues.jsonl"
        assert "beads.jsonl" != BeadWatcher.BEADS_JSONL.split("/")[-1] or "issues" in BeadWatcher.BEADS_JSONL

    def test_constructor_override_respected(self, store, router, tmp_path):
        scratch = str(tmp_path / "scratch.jsonl")
        w = BeadWatcher(store, router, beads_jsonl=scratch)
        assert w._beads_jsonl == scratch

    def test_real_checkpoint_file_exists(self):
        """The path we point at must actually exist on disk."""
        assert Path(BeadWatcher.BEADS_JSONL).exists(), (
            f"{BeadWatcher.BEADS_JSONL} does not exist -- watcher would no-op"
        )


# --- metadata extraction ----------------------------------------------------

class TestExtractMetadata:
    """Routing metadata is parsed from the flat labels array, not a metadata obj."""

    def test_parses_key_value_labels(self, store, router):
        w = BeadWatcher(store, router)
        meta = w._extract_metadata(_bead(labels=[
            "session_id=session-1",
            "origin_surface_id=surf-xyz",
            "intent_id=test-1",
            "intent_type=action",
            "urgency=critical",
            "created_at=1782995355",
        ]))
        assert meta["session_id"] == "session-1"
        assert meta["origin_surface_id"] == "surf-xyz"
        assert meta["urgency"] == "critical"
        assert meta["intent_id"] == "test-1"
        assert meta["created_at"] == "1782995355"

    def test_ignores_non_equals_labels(self, store, router):
        """Labels like `deferred`, `split-child`, and `failure-count:1` are skipped."""
        meta = BeadWatcher(store, router)._extract_metadata(_bead(labels=[
            "session_id=session-1",
            "deferred",
            "split-child",
            "failure-count:1",
        ]))
        assert meta == {"session_id": "session-1"}

    def test_no_labels_key_returns_empty(self, store, router):
        bead = _bead()
        del bead["labels"]
        assert BeadWatcher(store, router)._extract_metadata(bead) == {}

    def test_no_metadata_object_exists_on_real_schema(self, store, router):
        """Sanity: a real bf bead has no nested `metadata` key to read from."""
        bead = _bead()
        assert "metadata" not in bead

    def test_value_containing_equals_kept_intact(self, store, router):
        """partition on first '=' only -- a '=' inside the value is preserved."""
        meta = BeadWatcher(store, router)._extract_metadata(_bead(labels=[
            "session_id=a=b=c",
        ]))
        assert meta == {"session_id": "a=b=c"}


# --- routing: the core regression ------------------------------------------

class TestRouting:
    """A closed bead with a session_id label reaches the router (adc-5wtm core)."""

    async def test_closed_bead_with_session_label_routes(self, store, router, tmp_path):
        w = _watcher(store, router, tmp_path, [_bead(bead_id="adc-c1", status="closed")])
        await w._check_for_events()

        router.route_result.assert_awaited_once()
        kwargs = router.route_result.await_args.kwargs
        assert kwargs["session_id"] == "test-session-1"
        assert kwargs["origin_surface_id"] == "surf-abc"
        assert kwargs["urgency"] == "high"

    async def test_resolved_bead_also_routes(self, store, router, tmp_path):
        """`resolved` is a terminal status and must also trigger delivery."""
        w = _watcher(store, router, tmp_path, [_bead(bead_id="adc-r1", status="resolved")])
        await w._check_for_events()
        router.route_result.assert_awaited_once()
        assert router.route_result.await_args.kwargs["session_id"] == "test-session-1"

    async def test_bead_without_session_label_skips_routing(self, store, router, tmp_path):
        """A closed bead with no session_id label must NOT route (early return)."""
        bead = _bead(
            bead_id="adc-nosess",
            status="closed",
            labels=["split-child"],  # no session_id= label
        )
        w = _watcher(store, router, tmp_path, [bead])
        await w._check_for_events()
        router.route_result.assert_not_awaited()

    async def test_non_terminal_bead_does_not_route(self, store, router, tmp_path):
        """An open bead -- even with a session_id label -- is not delivered."""
        w = _watcher(store, router, tmp_path, [_bead(bead_id="adc-open", status="open")])
        await w._check_for_events()
        router.route_result.assert_not_awaited()

    async def test_missing_checkpoint_no_op(self, store, router, tmp_path):
        """A missing checkpoint file does not crash and does not route."""
        w = BeadWatcher(store, router, beads_jsonl=str(tmp_path / "nope.jsonl"))
        await w._check_for_events()  # must not raise
        router.route_result.assert_not_awaited()

    async def test_does_not_redeliver_same_bead_across_ticks(
        self, store, router, tmp_path
    ):
        """Re-reading the (rewritten-on-flush) checkpoint dedups via _processed_beads."""
        w = _watcher(store, router, tmp_path, [_bead(bead_id="adc-dd", status="closed")])
        await w._check_for_events()
        await w._check_for_events()  # second tick: file unchanged, bead already processed
        assert router.route_result.await_count == 1

    async def test_bead_closing_between_ticks_is_delivered(
        self, store, router, tmp_path
    ):
        """
        bf rewrites the whole checkpoint on flush (not append-only). A bead that
        was open at tick 1 and closed at tick 2 must be delivered -- this is why
        we re-read the whole file instead of tracking a byte offset.
        """
        checkpoint = tmp_path / "issues.jsonl"
        _write_checkpoint(checkpoint, [_bead(bead_id="adc-flip", status="open")])
        w = BeadWatcher(store, router, beads_jsonl=str(checkpoint))

        await w._check_for_events()
        router.route_result.assert_not_awaited()

        # bf flush rewrites the file with the bead now closed.
        _write_checkpoint(checkpoint, [_bead(bead_id="adc-flip", status="closed")])
        await w._check_for_events()
        router.route_result.assert_awaited_once()
        assert router.route_result.await_args.kwargs["session_id"] == "test-session-1"


# --- result extraction uses real bf schema ---------------------------------

class TestExtractResult:
    """Result body comes from `description` and type from `issue_type` (not body/type)."""

    async def test_uses_description_as_body(self, store, router):
        bead = _bead(
            description="## Task\nDetailed body content for the bead.",
            issue_type="task",
        )
        result = await BeadWatcher(store, router)._extract_result_from_bead(bead, "s1")
        assert "Detailed body content" in result["summary"]
        assert result["data"]["description"] == "## Task\nDetailed body content for the bead."
        assert result["data"]["issue_type"] == "task"
        # Old broken field names must not leak through.
        assert "body" not in result["data"]
        assert "type" not in result["data"]

    async def test_falls_back_to_title_when_no_description(self, store, router):
        bead = _bead(title="Just a title")
        bead["description"] = ""
        bead["notes"] = ""
        result = await BeadWatcher(store, router)._extract_result_from_bead(bead, "s1")
        assert result["summary"] == "Just a title"

    async def test_urgency_from_labels(self, store, router):
        bead = _bead(labels=["session_id=s1", "urgency=critical"])
        result = await BeadWatcher(store, router)._extract_result_from_bead(bead, "s1")
        assert result["urgency"] == "critical"


# --- Telegram delivery via the shared fallback (adc-372c) ------------------

class TestSendToTelegram:
    """_send_to_telegram routes through TelegramFallback instead of being a no-op.

    adc-372c: the bead watcher's bead-close → Telegram path used to log a
    warning and return without ever calling the bridge. It now delivers via the
    shared TelegramFallback.send_message using the configured chat_id, with the
    same graceful no-op-when-unconfigured behavior as send_exception().
    """

    @staticmethod
    def _fallback_with_chat_id(chat_id, send_return=True):
        """A TelegramFallback whose send_message is replaced with a capturing fake."""
        fb = TelegramFallback(chat_id=chat_id, bridge_url="http://test-bridge:8000")
        sent = []

        async def fake_send_message(chat_id, message, parse_mode="HTML"):
            sent.append((chat_id, message, parse_mode))
            return send_return

        fb.send_message = fake_send_message
        return fb, sent

    async def test_delivers_to_configured_chat_id(self, store, router):
        fb, sent = self._fallback_with_chat_id(chat_id=4242)
        w = BeadWatcher(store, router, telegram_fallback=fb)

        result = {
            "summary": "Bead adc-1 done",
            "urgency": "normal",
            "data": {"bead_id": "adc-1"},
        }
        ok = await w._send_to_telegram(result, "session-1")

        assert ok is True
        assert len(sent) == 1
        assert sent[0][0] == 4242  # routed to the configured chat id
        # Body is produced by _format_telegram_message.
        assert "Bead adc-1 done" in sent[0][1]

    async def test_returns_false_on_bridge_failure(self, store, router):
        """A real call is made; the bridge's failure propagates, not a hard-coded value."""
        fb, sent = self._fallback_with_chat_id(chat_id=1, send_return=False)
        w = BeadWatcher(store, router, telegram_fallback=fb)

        ok = await w._send_to_telegram({"summary": "hi"}, "session-1")

        assert ok is False
        assert len(sent) == 1  # the call was actually attempted

    async def test_no_op_without_chat_id(self, store, router, caplog):
        """No chat id configured → graceful WARNING + False, no send attempted."""
        fb = TelegramFallback(bridge_url="http://test-bridge:8000")
        assert fb.chat_id is None
        # Sentinel: if delivery were attempted, this would raise.
        async def boom(*a, **kw):
            raise AssertionError("send_message must not be called when chat_id is None")
        fb.send_message = boom
        w = BeadWatcher(store, router, telegram_fallback=fb)

        with caplog.at_level("WARNING"):
            ok = await w._send_to_telegram({"summary": "hi"}, "session-1")

        assert ok is False
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "ADC_TELEGRAM_CHAT_ID" in warnings[0].message

    async def test_uses_injected_fallback_not_singleton(self, store, router, monkeypatch):
        """The injected fallback wins over the module singleton."""
        # Poison the singleton so any accidental use of it is caught.
        async def boom(*a, **kw):
            raise AssertionError("injected fallback must be used, not the singleton")
        import src.watcher.daemon as daemon_mod
        singleton = TelegramFallback(chat_id=1)
        singleton.send_message = boom
        monkeypatch.setattr(daemon_mod, "get_telegram_fallback", lambda: singleton)

        fb, sent = self._fallback_with_chat_id(chat_id=4242)
        w = BeadWatcher(store, router, telegram_fallback=fb)

        ok = await w._send_to_telegram({"summary": "hi"}, "session-1")

        assert ok is True
        assert sent[0][0] == 4242  # the injected fallback delivered
