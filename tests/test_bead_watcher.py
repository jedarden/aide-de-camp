"""
Regression tests for the bead watcher daemon.

Two eras of fixes are pinned here:

- adc-5wtm / adc-372c: routing metadata comes from the bead's flat `labels`
  array (not a nested `metadata` object), the result body comes from
  `description`, and Telegram delivery routes through the shared
  TelegramFallback with the configured chat_id. These contracts are
  unchanged by the detection rewrite.

- adc-qw85: detection is CLI-only (plan §10 Bead Watcher). The watcher no
  longer reads the bf workspace's private checkpoint JSONL directly; each
  tick runs `bf list --status closed --json` as a subprocess from the
  aide-de-camp beads workspace and emits only closures newer than an
  in-memory close-timestamp high-water mark. These tests pin: the CLI
  invocation config, the high-water-mark dedup semantics (baseline on the
  first tick and after any restart; only strictly-newer closures surface),
  and that every bf failure mode (missing binary, spawn error, non-zero
  exit, timeout, malformed line) is logged and non-fatal.

No live SSE / Telegram / LLM calls: the surface router is an AsyncMock and we
assert on the routing attempt (route_result call kwargs). The bf subprocess is
faked, except for one skip-gated end-to-end class that exercises the real CLI.
"""

import asyncio
import json
import logging
import shutil
import subprocess
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.surface.router import RouteDecision
from src.telegram.fallback import TelegramFallback
from src.watcher.daemon import BeadWatcher

# --- bead fixtures ----------------------------------------------------------


def _bead(
    bead_id: str = "adc-test1",
    status: str = "closed",
    closed_at: str = "2026-07-19T22:42:37.385045363Z",
    labels: list[str] | None = None,
    description: str = "## Task\nDo the thing.\n\n## Acceptance Criteria\n- done",
    title: str = "Test bead",
    issue_type: str = "task",
) -> dict:
    """A schema-accurate bf issue (matches `bf list --json` output)."""
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
        "updated_at": closed_at,
        "closed_at": closed_at,
        "close_reason": "Completed",
        "source_repo": ".",
        "compaction_level": 0,
        "labels": labels,
        "dependencies": [],
    }


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
    """Mock session store with get_intent_by_bead_ref support."""
    s = MagicMock()
    s.get_intent_by_bead_ref = AsyncMock(return_value=None)
    s.create_result = AsyncMock(return_value="result-1")
    s.update_intent_status = AsyncMock()
    return s


# --- CLI invocation config (adc-qw85) ---------------------------------------


class TestCLIConfig:
    """bf binary / workspace / timeout defaults and constructor overrides."""

    def test_defaults_point_at_real_binary_and_workspace(self, store, router):
        # bf resolves via PATH; the workspace is the aide-de-camp checkout, which
        # is this app's beads workspace (plan: Beads-Workspace Scoping).
        assert BeadWatcher.BF_BIN == "bf"
        assert BeadWatcher.BF_WORKSPACE == "/home/coding/aide-de-camp"
        assert BeadWatcher.SUBPROCESS_TIMEOUT_SECONDS == 10.0
        w = BeadWatcher(store, router)
        assert w._bf_bin == "bf"
        assert w._bf_workspace == "/home/coding/aide-de-camp"
        assert w._subprocess_timeout == 10.0

    def test_constructor_overrides(self, store, router, tmp_path):
        w = BeadWatcher(
            store,
            router,
            bf_bin="/custom/bf",
            bf_workspace=str(tmp_path),
            subprocess_timeout_seconds=3.0,
        )
        assert w._bf_bin == "/custom/bf"
        assert w._bf_workspace == str(tmp_path)
        assert w._subprocess_timeout == 3.0

    def test_no_beads_jsonl_attribute_or_param_remains(self, store, router):
        """The direct-read path is gone: no BEADS_JSONL constant, no beads_jsonl
        param, no _beads_jsonl attr (adc-qw85 acceptance: grep .beads/ is clean)."""
        assert not hasattr(BeadWatcher, "BEADS_JSONL")
        assert not hasattr(BeadWatcher, "TERMINAL_STATUSES")
        w = BeadWatcher(store, router)
        assert not hasattr(w, "_beads_jsonl")
        assert not hasattr(w, "_processed_beads")


# --- close-timestamp parsing (adc-qw85) -------------------------------------


class TestParseCloseEpoch:
    """_parse_close_epoch handles bf's nanosecond RFC3339 closed_at."""

    def test_nanosecond_with_z(self):
        # The exact form bf emits: 9 fractional digits + trailing Z.
        ts = BeadWatcher._parse_close_epoch("2026-07-22T12:47:22.595899004Z")
        assert ts == pytest.approx(1784724442.595899)

    def test_seconds_only_with_z(self):
        assert BeadWatcher._parse_close_epoch("2026-07-22T12:47:22Z") == pytest.approx(
            1784724442.0
        )

    def test_malformed_returns_none(self):
        assert BeadWatcher._parse_close_epoch("not-a-timestamp") is None
        assert BeadWatcher._parse_close_epoch("") is None
        assert BeadWatcher._parse_close_epoch(None) is None  # type: ignore[arg-type]

    def test_ordering_is_chronological(self):
        """Newer close time -> larger epoch (the HWM comparison relies on this)."""
        older = BeadWatcher._parse_close_epoch("2026-07-22T10:00:00Z")
        newer = BeadWatcher._parse_close_epoch("2026-07-22T12:47:22Z")
        assert newer > older


# --- bf subprocess wrapper: _run_bf_list_closed (adc-qw85) ------------------


class _FakeProc:
    """Stand-in for the asyncio subprocess returned by create_subprocess_exec."""

    def __init__(self, stdout=b"", stderr=b"", returncode=0, communicate_fn=None):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._communicate_fn = communicate_fn
        self.killed = False

    async def communicate(self):
        if self._communicate_fn is not None:
            return await self._communicate_fn()
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


def _patch_subprocess(monkeypatch, proc=None, *, raises=None):
    """Patch create_subprocess_exec in the daemon module to return ``proc`` (or
    raise ``raises``). Asserts the watcher invokes bf from a real workspace cwd."""
    async def fake_exec(*args, **kwargs):
        if raises is not None:
            raise raises
        assert kwargs.get("cwd") is not None, "bf must run from its workspace cwd"
        return proc

    monkeypatch.setattr("src.watcher.daemon.asyncio.create_subprocess_exec", fake_exec)


class TestRunBfListClosed:
    """The CLI subprocess wrapper: happy path + every failure mode is non-fatal."""

    async def test_parses_jsonl_records(self, store, router, monkeypatch):
        out = (
            json.dumps(_bead(bead_id="adc-a")) + "\n"
            + json.dumps(_bead(bead_id="adc-b")) + "\n"
        ).encode()
        _patch_subprocess(monkeypatch, _FakeProc(stdout=out, returncode=0))
        w = BeadWatcher(store, router)
        recs = await w._run_bf_list_closed()
        assert [r["id"] for r in recs] == ["adc-a", "adc-b"]

    async def test_missing_binary_returns_empty(self, store, router, caplog):
        # A genuinely-missing binary makes create_subprocess_exec raise
        # FileNotFoundError -- the exact production failure (binary not installed).
        w = BeadWatcher(store, router, bf_bin="/nope/does-not-exist-bf")
        with caplog.at_level(logging.ERROR, logger="src.watcher.daemon"):
            recs = await w._run_bf_list_closed()
        assert recs == []
        assert any("not found" in r.getMessage() for r in caplog.records)

    async def test_spawn_oserror_returns_empty(self, store, router, monkeypatch, caplog):
        _patch_subprocess(monkeypatch, raises=OSError("permission denied"))
        w = BeadWatcher(store, router)
        with caplog.at_level(logging.ERROR, logger="src.watcher.daemon"):
            recs = await w._run_bf_list_closed()
        assert recs == []

    async def test_nonzero_exit_returns_empty(self, store, router, monkeypatch, caplog):
        _patch_subprocess(
            monkeypatch, _FakeProc(stdout=b"", stderr=b"db locked", returncode=2)
        )
        w = BeadWatcher(store, router)
        with caplog.at_level(logging.WARNING, logger="src.watcher.daemon"):
            recs = await w._run_bf_list_closed()
        assert recs == []
        assert any("exited 2" in r.getMessage() for r in caplog.records)

    async def test_timeout_returns_empty_and_kills_proc(
        self, store, router, monkeypatch, caplog
    ):
        async def hang():
            await asyncio.Future()  # never resolves -> wait_for raises TimeoutError

        proc = _FakeProc(communicate_fn=hang)
        _patch_subprocess(monkeypatch, proc)
        w = BeadWatcher(store, router, subprocess_timeout_seconds=0.05)
        with caplog.at_level(logging.WARNING, logger="src.watcher.daemon"):
            recs = await w._run_bf_list_closed()
        assert recs == []
        assert proc.killed is True
        assert any("timed out" in r.getMessage() for r in caplog.records)

    async def test_malformed_lines_skipped_others_kept(
        self, store, router, monkeypatch, caplog
    ):
        out = (
            json.dumps(_bead(bead_id="adc-a")) + "\n"
            + "not json at all\n"
            + "{ broken json\n"
            + json.dumps(_bead(bead_id="adc-b")) + "\n"
        ).encode()
        _patch_subprocess(monkeypatch, _FakeProc(stdout=out, returncode=0))
        w = BeadWatcher(store, router)
        with caplog.at_level(logging.WARNING, logger="src.watcher.daemon"):
            recs = await w._run_bf_list_closed()
        # One malformed line must not discard the rest.
        assert [r["id"] for r in recs] == ["adc-a", "adc-b"]
        assert len([r for r in caplog.records if "unparseable" in r.getMessage()]) == 2


# --- high-water-mark detection: _poll_closed_beads (adc-qw85) ---------------


def _watcher_with_records(store, router, records, *, highwater=None):
    """A BeadWatcher whose bf subprocess is stubbed to return ``records``."""
    w = BeadWatcher(store, router)

    async def fake_run():
        return list(records)

    w._run_bf_list_closed = fake_run  # instance override; no real subprocess
    if highwater is not None:
        w._close_highwater = highwater
    return w


class TestHighWaterMark:
    """close-timestamp HWM: baseline on the first tick, emit only strictly-newer."""

    async def test_first_tick_baselines_and_emits_nothing(self, store, router):
        recs = [_bead(bead_id="adc-old", closed_at="2026-07-19T22:42:37.385045363Z")]
        w = _watcher_with_records(store, router, recs)
        assert w._close_highwater is None
        ev = await w._poll_closed_beads()
        assert ev == []
        # Baselined to the backlog's newest close time.
        assert w._close_highwater == pytest.approx(
            BeadWatcher._parse_close_epoch("2026-07-19T22:42:37.385045363Z")
        )

    async def test_emits_only_strictly_newer_closure(self, store, router):
        old = _bead(bead_id="adc-old", closed_at="2026-07-19T22:42:37Z")
        new = _bead(bead_id="adc-new", closed_at="2026-07-22T12:47:22Z")
        hw = BeadWatcher._parse_close_epoch("2026-07-19T22:42:37Z")
        w = _watcher_with_records(store, router, [old, new], highwater=hw)
        ev = await w._poll_closed_beads()
        assert [e.bead_id for e in ev] == ["adc-new"]
        # HWM advances to the newest close seen this tick.
        assert w._close_highwater == pytest.approx(
            BeadWatcher._parse_close_epoch("2026-07-22T12:47:22Z")
        )

    async def test_bead_at_or_below_hwm_not_emitted(self, store, router):
        at = _bead(bead_id="adc-at", closed_at="2026-07-22T12:47:22Z")
        below = _bead(bead_id="adc-below", closed_at="2026-07-22T12:00:00Z")
        hw = BeadWatcher._parse_close_epoch("2026-07-22T12:47:22Z")
        w = _watcher_with_records(store, router, [at, below], highwater=hw)
        assert await w._poll_closed_beads() == []  # strictly-newer only; == excluded

    async def test_same_records_second_tick_emits_nothing(self, store, router):
        rec = _bead(bead_id="adc-x", closed_at="2026-07-22T12:47:22Z")
        w = _watcher_with_records(store, router, [rec])
        assert await w._poll_closed_beads() == []  # baseline
        assert await w._poll_closed_beads() == []  # unchanged -> nothing new

    async def test_newer_closure_between_ticks_delivered(self, store, router):
        # bf re-emits the whole closed set each tick (it is not append-only);
        # a bead that closes between ticks must surface via its newer close time.
        state = {"recs": [_bead(bead_id="adc-1", closed_at="2026-07-22T10:00:00Z")]}
        w = BeadWatcher(store, router)

        async def fake_run():
            return list(state["recs"])

        w._run_bf_list_closed = fake_run
        assert await w._poll_closed_beads() == []  # baseline
        state["recs"].append(_bead(bead_id="adc-2", closed_at="2026-07-22T11:00:00Z"))
        ev = await w._poll_closed_beads()
        assert [e.bead_id for e in ev] == ["adc-2"]

    async def test_unparseable_closed_at_skipped(self, store, router, caplog):
        good = _bead(bead_id="adc-good", closed_at="2026-07-22T12:47:22Z")
        bad = _bead(bead_id="adc-bad", closed_at="not-a-timestamp")
        missing = _bead(bead_id="adc-missing")
        del missing["closed_at"]
        hw = BeadWatcher._parse_close_epoch("2026-07-22T00:00:00Z")
        w = _watcher_with_records(store, router, [bad, missing, good], highwater=hw)
        with caplog.at_level(logging.WARNING, logger="src.watcher.daemon"):
            ev = await w._poll_closed_beads()
        # Only the parseable, newer-than-HWM record surfaces; bad ones are logged.
        assert [e.bead_id for e in ev] == ["adc-good"]
        assert any("Could not parse closed_at" in r.getMessage() for r in caplog.records)

    async def test_restart_does_not_redeliver_backlog(self, store, router):
        """A fresh watcher (in-memory HWM reset on restart) re-baselines and does
        NOT re-deliver beads already closed before it started (adc-qw85)."""
        recs = [
            _bead(bead_id="adc-already", closed_at="2026-07-22T12:47:22Z"),
            _bead(bead_id="adc-older", closed_at="2026-07-22T10:00:00Z"),
        ]
        w1 = _watcher_with_records(store, router, recs)
        assert await w1._poll_closed_beads() == []  # baseline
        # Simulate process restart: new instance, same backlog.
        w2 = _watcher_with_records(store, router, recs)
        assert await w2._poll_closed_beads() == []  # re-baseline, no re-deliver


# --- metadata extraction (adc-5wtm, unchanged by the rewrite) ---------------


class TestExtractMetadata:
    """Routing metadata is parsed from the flat labels array, not a metadata obj."""

    def test_parses_key_value_labels(self, store, router):
        meta = BeadWatcher(store, router)._extract_metadata(
            _bead(
                labels=[
                    "session_id=session-1",
                    "origin_surface_id=surf-xyz",
                    "intent_id=test-1",
                    "intent_type=action",
                    "urgency=critical",
                    "created_at=1782995355",
                ]
            )
        )
        assert meta["session_id"] == "session-1"
        assert meta["origin_surface_id"] == "surf-xyz"
        assert meta["urgency"] == "critical"
        assert meta["intent_id"] == "test-1"
        assert meta["created_at"] == "1782995355"

    def test_ignores_non_equals_labels(self, store, router):
        """Labels like `deferred`, `split-child`, and `failure-count:1` are skipped."""
        meta = BeadWatcher(store, router)._extract_metadata(
            _bead(labels=["session_id=session-1", "deferred", "split-child", "failure-count:1"])
        )
        assert meta == {"session_id": "session-1"}

    def test_no_labels_key_returns_empty(self, store, router):
        bead = _bead()
        del bead["labels"]
        assert BeadWatcher(store, router)._extract_metadata(bead) == {}

    def test_no_metadata_object_exists_on_real_schema(self, store, router):
        """Sanity: a real bf bead has no nested `metadata` key to read from."""
        assert "metadata" not in _bead()

    def test_value_containing_equals_kept_intact(self, store, router):
        """partition on first '=' only -- a '=' inside the value is preserved."""
        meta = BeadWatcher(store, router)._extract_metadata(_bead(labels=["session_id=a=b=c"]))
        assert meta == {"session_id": "a=b=c"}


# --- routing: an emitted closed+session-labelled bead reaches the router -----


class TestRouting:
    """Only beads the HWM emits are processed; matching intent.bead_ref reaches routing."""

    async def test_emitted_closed_bead_with_matching_intent_routes(self, store, router):
        """A closed bead with a matching intent.bead_ref writes result, marks resolved,
        and routes to surfaces."""
        bead = _bead(bead_id="adc-c1", closed_at="2026-07-22T12:47:22Z")
        # Seed HWM below the bead's close time so the first tick emits it.
        hw = BeadWatcher._parse_close_epoch("2026-07-22T00:00:00Z")
        w = _watcher_with_records(store, router, [bead], highwater=hw)

        # Mock the intent lookup to return a tracked intent
        store.get_intent_by_bead_ref = AsyncMock(
            return_value={
                "id": "intent-1",
                "session_id": "test-session-1",
                "topic_id": "topic-1",
                "bead_ref": "adc-c1",
                "status": "pending",
            }
        )

        await w._check_for_events()

        # Verify intent was looked up by bead_ref
        store.get_intent_by_bead_ref.assert_awaited_once_with("adc-c1")

        # Verify result was created
        store.create_result.assert_awaited_once()
        kwargs = store.create_result.await_args.kwargs
        assert kwargs["intent_id"] == "intent-1"
        assert kwargs["topic_id"] == "topic-1"
        assert kwargs["session_id"] == "test-session-1"

        # Verify intent was marked resolved
        store.update_intent_status.assert_awaited_once_with("intent-1", "resolved")

        # Verify routing was called (SSE/Telegram delivery)
        router.route_result.assert_awaited_once()
        route_kwargs = router.route_result.await_args.kwargs
        assert route_kwargs["session_id"] == "test-session-1"
        assert route_kwargs["urgency"] == "high"

    async def test_emitted_bead_without_matching_intent_skips(self, store, router):
        """A closed bead with no matching intent.bead_ref is skipped (most beads)."""
        bead = _bead(
            bead_id="adc-nosess", labels=["split-child"], closed_at="2026-07-22T12:47:22Z"
        )
        hw = BeadWatcher._parse_close_epoch("2026-07-22T00:00:00Z")
        w = _watcher_with_records(store, router, [bead], highwater=hw)

        # Mock no matching intent (returns None)
        store.get_intent_by_bead_ref = AsyncMock(return_value=None)

        await w._check_for_events()

        # Verify intent lookup was attempted
        store.get_intent_by_bead_ref.assert_awaited_once_with("adc-nosess")

        # Verify no result was created and no routing happened
        store.create_result.assert_not_awaited()
        router.route_result.assert_not_awaited()

    async def test_backlog_not_routed_on_first_tick(self, store, router):
        """Baseline semantics: a pre-existing closed bead is NOT routed on the
        first tick -- prevents re-delivering the whole backlog at startup."""
        bead = _bead(bead_id="adc-backlog", closed_at="2026-07-22T12:47:22Z")
        w = _watcher_with_records(store, router, [bead])  # HWM None -> baseline
        await w._check_for_events()
        router.route_result.assert_not_awaited()

    async def test_bf_failure_tick_does_not_route(self, store, router, monkeypatch):
        """A bf subprocess failure (empty record set) means no routing this tick."""
        w = BeadWatcher(store, router)

        async def no_records():
            return []

        w._run_bf_list_closed = no_records
        await w._check_for_events()
        router.route_result.assert_not_awaited()

    async def test_bead_with_matching_intent_but_no_topic_skips_result_write(
        self, store, router, caplog
    ):
        """An intent with no topic_id cannot write a result; logs warning and skips."""
        bead = _bead(bead_id="adc-c1", closed_at="2026-07-22T12:47:22Z")
        hw = BeadWatcher._parse_close_epoch("2026-07-22T00:00:00Z")
        w = _watcher_with_records(store, router, [bead], highwater=hw)

        # Mock intent without topic_id
        store.get_intent_by_bead_ref = AsyncMock(
            return_value={
                "id": "intent-1",
                "session_id": "test-session-1",
                "topic_id": None,  # Missing topic_id
                "bead_ref": "adc-c1",
                "status": "pending",
            }
        )

        with caplog.at_level(logging.WARNING, logger="src.watcher.daemon"):
            await w._check_for_events()

        # Result was not created due to missing topic_id
        store.create_result.assert_not_awaited()
        # Warning logged about missing topic_id
        assert any("no topic_id" in r.getMessage() for r in caplog.records)


# --- result extraction uses real bf schema (adc-5wtm) -----------------------


class TestExtractResult:
    """Result body comes from `description` and type from `issue_type` (not body/type)."""

    async def test_uses_description_as_body(self, store, router):
        bead = _bead(
            description="## Task\nDetailed body content for the bead.", issue_type="task"
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


# --- Telegram delivery via the shared fallback (adc-372c) -------------------


class TestSendToTelegram:
    """_send_to_telegram routes through TelegramFallback instead of being a no-op.

    adc-372c: the bead watcher's bead-close -> Telegram path used to log a
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
        """No chat id configured -> graceful WARNING + False, no send attempted."""
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


# --- lifespan supervision, liveness, interval (adc-4afi) --------------------


class _TaskCrash(BaseException):
    """A task-killing crash.

    Subclasses BaseException (not Exception) so it escapes the watch loop's
    transient ``except Exception`` catch -- simulating a real task death that
    only the supervisor layer can recover from. Normal exceptions raised from
    ``_check_for_events`` are caught by the loop and never reach the supervisor.
    """


class TestInterval:
    """Poll interval defaults to 30s (plan §10) and is overridable.

    Resolution order: explicit constructor arg > ADC_WATCHER_CHECK_INTERVAL_SECONDS
    env > class default (30s).
    """

    def test_default_interval_is_30(self, store, router, monkeypatch):
        # Guard against a stray env var in the test environment.
        monkeypatch.delenv("ADC_WATCHER_CHECK_INTERVAL_SECONDS", raising=False)
        assert BeadWatcher.CHECK_INTERVAL_SECONDS == 30
        w = BeadWatcher(store, router)
        assert w.check_interval_seconds == 30.0

    def test_constructor_arg_overrides_default(self, store, router):
        w = BeadWatcher(store, router, check_interval_seconds=7)
        assert w.check_interval_seconds == 7.0

    def test_env_overrides_default_when_no_arg(self, store, router, monkeypatch):
        monkeypatch.setenv("ADC_WATCHER_CHECK_INTERVAL_SECONDS", "12")
        w = BeadWatcher(store, router)
        assert w.check_interval_seconds == 12.0

    def test_explicit_arg_beats_env(self, store, router, monkeypatch):
        monkeypatch.setenv("ADC_WATCHER_CHECK_INTERVAL_SECONDS", "12")
        w = BeadWatcher(store, router, check_interval_seconds=9)
        assert w.check_interval_seconds == 9.0


class TestLiveness:
    """last_tick_at / tick_count advance on every tick under normal run."""

    def test_initial_liveness_state(self, store, router):
        w = BeadWatcher(store, router)
        assert w.last_tick_at == 0.0  # 0.0 == "never ticked" sentinel
        assert w.tick_count == 0
        assert w._close_highwater is None  # HWM starts unbaselined

    async def test_loop_stamps_last_tick_at_and_increments_tick_count(
        self, store, router, monkeypatch
    ):
        w = BeadWatcher(store, router, check_interval_seconds=0.0)
        # No real subprocess: keep the tick hermetic and empty.
        async def no_records():
            return []

        w._run_bf_list_closed = no_records

        # Patch asyncio.sleep in the daemon module: the loop's interval sleep
        # (seconds < 1.0, since we set the interval to 0.0) becomes instant and
        # terminates the task after 3 completed ticks, so the test is
        # deterministic and never waits real time.
        real_sleep = asyncio.sleep
        interval_sleeps = {"n": 0}

        async def fast_sleep(seconds):
            await real_sleep(0)  # yield to the scheduler
            if seconds < 1.0:
                interval_sleeps["n"] += 1
                if interval_sleeps["n"] >= 3:
                    raise asyncio.CancelledError()  # end the watch task

        monkeypatch.setattr("src.watcher.daemon.asyncio.sleep", fast_sleep)

        await w.start()
        for _ in range(200):
            if w._supervisor_task is None or w._supervisor_task.done():
                break
            await real_sleep(0.002)
        await w.stop()

        # Each completed tick stamped liveness and bumped the counter.
        assert w.tick_count >= 3
        assert w.last_tick_at > 0.0


class TestSupervisorRestart:
    """A crashed watch task is restarted by the supervisor with growing backoff.

    adc-4afi: the old bare create_task loop caught per-iteration exceptions but
    never restarted a task that ended -- once dead it stayed dead. The supervisor
    layer now respawns it on death with exponential backoff (2s, 4s, 8s, capped).
    """

    async def test_crashed_task_restarts_with_increasing_backoff(
        self, store, router, monkeypatch, caplog
    ):
        w = BeadWatcher(store, router, check_interval_seconds=0.0)

        # Every tick crashes the task outright (escapes the transient catch).
        async def crash():
            raise _TaskCrash("forced crash")

        monkeypatch.setattr(w, "_check_for_events", crash)

        # Capture the backoff durations the supervisor requests, without really
        # sleeping. After the 3rd backoff sleep, stop the supervisor so the test
        # terminates deterministically.
        real_sleep = asyncio.sleep
        requested = []

        async def capture_sleep(seconds):
            requested.append(seconds)
            await real_sleep(0)
            if seconds >= 1.0 and sum(1 for s in requested if s >= 1.0) >= 3:
                raise asyncio.CancelledError()

        monkeypatch.setattr("src.watcher.daemon.asyncio.sleep", capture_sleep)

        with caplog.at_level(logging.WARNING, logger="src.watcher.daemon"):
            await w.start()
            for _ in range(200):
                if w._supervisor_task is None or w._supervisor_task.done():
                    break
                await real_sleep(0.002)
            await w.stop()

        backoffs = [s for s in requested if s >= 1.0]
        # Three crashes, each followed by a logged restart with growing backoff.
        assert len(backoffs) >= 3
        assert backoffs[0] == pytest.approx(2.0)
        assert backoffs[1] == pytest.approx(4.0)
        assert backoffs[2] == pytest.approx(8.0)
        assert w._restart_count >= 3
        restart_logs = [r for r in caplog.records if "restarting" in r.getMessage().lower()]
        assert len(restart_logs) >= 3

    async def test_transient_exception_does_not_trigger_restart(
        self, store, router, monkeypatch
    ):
        """A normal Exception is caught by the loop -- no supervisor restart.

        Pins the two-layer split: transient per-iteration errors stay absorbed
        by the watch loop (pre-supervisor behavior preserved); only a real task
        death reaches the supervisor. So no backoff is ever requested and the
        task keeps ticking despite the recurring error.
        """
        w = BeadWatcher(store, router, check_interval_seconds=0.0)

        async def transient():
            raise RuntimeError("transient per-iteration error")

        monkeypatch.setattr(w, "_check_for_events", transient)

        real_sleep = asyncio.sleep
        sleeps = []

        async def fast_sleep(seconds):
            sleeps.append(seconds)
            await real_sleep(0)
            if seconds < 1.0 and len([s for s in sleeps if s < 1.0]) >= 4:
                raise asyncio.CancelledError()

        monkeypatch.setattr("src.watcher.daemon.asyncio.sleep", fast_sleep)

        await w.start()
        for _ in range(200):
            if w._supervisor_task is None or w._supervisor_task.done():
                break
            await real_sleep(0.002)
        await w.stop()

        # No backoff (>= 1.0) sleep was ever requested, and the task never died.
        assert not any(s >= 1.0 for s in sleeps)
        assert w._restart_count == 0
        # The loop kept ticking -- liveness advanced despite the errors.
        assert w.tick_count >= 4


# --- real bf end-to-end (skip if bf absent) (adc-qw85) ----------------------


@pytest.fixture
def bf_workspace(tmp_path):
    """An isolated, initialized bead-forge workspace for e2e detection."""
    if not shutil.which("bf"):
        pytest.skip("bf (bead-forge) CLI not on PATH")
    ws = tmp_path / "ws"
    ws.mkdir()
    try:
        subprocess.run(
            ["bf", "init", "-w", str(ws)], check=True, capture_output=True, timeout=20
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        pytest.skip(f"could not bf init a scratch workspace: {e!r}")
    return ws


def _bf_run(ws, *args):
    """Run a bf subcommand in workspace ``ws`` and return its stdout."""
    return subprocess.run(
        ["bf", *args, "-w", str(ws)],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout


class TestRealBfEndToEnd:
    """Exercises the real CLI + parser. Pins acceptance: a closure is detected
    within one tick, and a restart does not re-deliver the backlog. Skipped when
    bf (bead-forge) is unavailable, so the suite stays hermetic elsewhere."""

    async def test_detects_new_closure_within_one_tick(self, store, router, bf_workspace):
        ws = bf_workspace
        # Pre-existing closed bead (the backlog at watcher start).
        pre = _bf_run(ws, "create", "--type", "task", "--title", "pre").strip().splitlines()[0]
        _bf_run(ws, "close", pre)

        w = BeadWatcher(store, router, bf_workspace=str(ws))
        # First tick: baseline against the backlog, emit nothing.
        assert await w._poll_closed_beads() == []

        # A bead closes after the watcher started.
        fresh = _bf_run(ws, "create", "--type", "task", "--title", "fresh").strip().splitlines()[0]
        _bf_run(ws, "close", fresh)

        # Next tick must detect the new closure and carry its close time.
        ev = await w._poll_closed_beads()
        assert [e.bead_id for e in ev] == [fresh]
        assert ev[0].timestamp > 0
        assert ev[0].event_type == "closed"

    async def test_restart_does_not_redeliver(self, store, router, bf_workspace):
        ws = bf_workspace
        bid = _bf_run(ws, "create", "--type", "task", "--title", "closed-before-start").strip().splitlines()[0]
        _bf_run(ws, "close", bid)

        w = BeadWatcher(store, router, bf_workspace=str(ws))
        assert await w._poll_closed_beads() == []  # baseline

        # New instance (restart): in-memory HWM lost -> re-baseline, no re-deliver.
        w2 = BeadWatcher(store, router, bf_workspace=str(ws))
        assert await w2._poll_closed_beads() == []
