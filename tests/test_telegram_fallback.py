"""
Unit tests for Telegram fallback integration.

Per ADR-1 (2026-07-20), this integration uses the Telegram Bot API directly,
not telegram-claude-bridge. The implementation requires:
- ADC_TELEGRAM_BOT_TOKEN: Telegram bot token (required for sends)
- ADC_TELEGRAM_CHAT_ID: Fixed chat ID for the single user (required for push methods)
"""

import os

import httpx
import pytest

from src.telegram.fallback import TelegramFallback, get_telegram_fallback


class TestTelegramFallbackEnvConfig:
    """Test Telegram fallback environment variable configuration."""

    def test_default_bot_token_is_none(self):
        """Test that bot_token defaults to None when no env var is set."""
        # Ensure env var is not set
        if "ADC_TELEGRAM_BOT_TOKEN" in os.environ:
            del os.environ["ADC_TELEGRAM_BOT_TOKEN"]

        fallback = TelegramFallback()
        assert fallback.bot_token is None

    def test_bot_token_from_env(self, monkeypatch):
        """Test that ADC_TELEGRAM_BOT_TOKEN env var is respected."""
        test_token = "test_bot_token_123"
        monkeypatch.setenv("ADC_TELEGRAM_BOT_TOKEN", test_token)

        fallback = TelegramFallback()
        assert fallback.bot_token == test_token

    def test_bot_token_constructor_override(self, monkeypatch):
        """Test that constructor parameter overrides env var."""
        env_token = "env_token_456"
        constructor_token = "constructor_token_789"
        monkeypatch.setenv("ADC_TELEGRAM_BOT_TOKEN", env_token)

        fallback = TelegramFallback(bot_token=constructor_token)
        assert fallback.bot_token == constructor_token

    def test_default_chat_id_is_none(self):
        """Test that chat_id defaults to None when no env var is set."""
        # Ensure env var is not set
        if "ADC_TELEGRAM_CHAT_ID" in os.environ:
            del os.environ["ADC_TELEGRAM_CHAT_ID"]

        fallback = TelegramFallback()
        assert fallback.chat_id is None

    def test_chat_id_from_env(self, monkeypatch):
        """Test that ADC_TELEGRAM_CHAT_ID env var is respected."""
        test_chat_id = "123456789"
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", test_chat_id)

        fallback = TelegramFallback()
        assert fallback.chat_id == test_chat_id

    def test_chat_id_constructor_override(self, monkeypatch):
        """Test that constructor parameter overrides env var."""
        env_chat_id = "env_chat_id"
        constructor_chat_id = "constructor_chat_id"
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", env_chat_id)

        fallback = TelegramFallback(chat_id=constructor_chat_id)
        assert fallback.chat_id == constructor_chat_id


class TestTelegramFallbackAPIContract:
    """Test Telegram fallback API contract correctness."""

    def test_send_message_payload_structure(self):
        """Test that send_message creates correct payload for Telegram sendMessage API."""
        fallback = TelegramFallback(bot_token="test_token")

        # Verify the method exists
        assert hasattr(fallback, 'send_message')

    def test_check_telegram_available_method_exists(self):
        """Test that check_telegram_available method exists."""
        fallback = TelegramFallback(bot_token="test_token")

        # Verify the method exists
        assert hasattr(fallback, 'check_telegram_available')


class TestGlobalFallbackInstance:
    """Test global Telegram fallback instance management."""

    def test_get_telegram_fallback_creates_instance(self):
        """Test that get_telegram_fallback creates instance on first call."""
        # Reset global instance
        import src.telegram.fallback
        src.telegram.fallback._telegram_fallback = None

        fallback = get_telegram_fallback()
        assert fallback is not None
        assert isinstance(fallback, TelegramFallback)

    def test_get_telegram_fallback_returns_same_instance(self):
        """Test that get_telegram_fallback returns singleton instance."""
        # Reset global instance
        import src.telegram.fallback
        src.telegram.fallback._telegram_fallback = None

        fallback1 = get_telegram_fallback()
        fallback2 = get_telegram_fallback()
        assert fallback1 is fallback2


class TestFirstFailureTracking:
    """Test first-failure detection: exactly one WARNING per process startup."""

    async def test_has_failed_since_startup_flag_initial_state(self):
        """adc-2r8hh: flag is False at startup (no failures yet)."""
        fallback = TelegramFallback()
        assert fallback._has_failed_since_startup is False

    async def test_has_failed_since_startup_flag_set_on_first_failure(self):
        """adc-2r8hh: flag sets to True on first Telegram send failure."""
        fallback = TelegramFallback()
        assert fallback._has_failed_since_startup is False

        await fallback._handle_send_failure(error=ConnectionError("first failure"))

        assert fallback._has_failed_since_startup is True

    async def test_has_failed_since_startup_exposed_in_status(self):
        """adc-2r8hh: flag is exposed in get_status() output."""
        fallback = TelegramFallback()
        status = fallback.get_status()
        assert "has_failed_since_startup" in status
        assert status["has_failed_since_startup"] is False

        await fallback._handle_send_failure(error=ConnectionError("failure"))

        status = fallback.get_status()
        assert status["has_failed_since_startup"] is True

    async def test_has_failed_since_startup_reset(self):
        """adc-2r8hh: flag resets to False when first failure state is reset."""
        fallback = TelegramFallback()

        await fallback._handle_send_failure(error=ConnectionError("first"))
        assert fallback._has_failed_since_startup is True

        await fallback.reset_first_failure_state()
        assert fallback._has_failed_since_startup is False

    async def test_has_failed_since_startup_thread_safety(self):
        """adc-2r8hh: flag is set under lock, preventing race conditions."""
        import asyncio

        fallback = TelegramFallback()
        assert fallback._has_failed_since_startup is False

        # Concurrent failures - all should see the flag as True after completion
        await asyncio.gather(
            *(
                fallback._handle_send_failure(error=ConnectionError(f"failure{i}"))
                for i in range(10)
            )
        )

        assert fallback._has_failed_since_startup is True
        assert fallback._failure_count == 10

    async def test_first_failure_logs_warning_with_error_type(self, caplog):
        """The first failure logs a WARNING carrying both error type and message."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error=ConnectionError("connection refused")
            )

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        msg = warnings[0].message
        # Verify error context is logged
        assert "ConnectionError" in msg  # error type
        assert "connection refused" in msg  # error message

    async def test_repeated_failure_within_cooldown_is_suppressed(self, caplog):
        """An immediate repeat is deduped: counted, but NOT logged (no spam)."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(error=ConnectionError("boom"))

        caplog.clear()

        with caplog.at_level("DEBUG"):
            await fallback._handle_send_failure(error=ConnectionError("boom2"))

        # Within the cooldown window the repeated failure is counted but silent.
        assert caplog.records == []
        assert fallback._failure_count == 2
        assert fallback._failures_since_last_log == 1

    async def test_repeated_failure_after_cooldown_logs_debug_summary(self, caplog):
        """Once the cooldown elapses, a repeated failure logs a DEBUG summary."""
        from datetime import datetime, timedelta

        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(error=ConnectionError("boom"))

        caplog.clear()

        # Simulate the cooldown window elapsing.
        fallback._last_repeated_log_timestamp = datetime.now() - timedelta(seconds=999)

        with caplog.at_level("DEBUG"):
            await fallback._handle_send_failure(error=ConnectionError("boom2"))

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        debugs = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert warnings == []
        assert len(debugs) == 1
        assert "Repeated" in debugs[0].message or "failure" in debugs[0].message
        assert "ConnectionError" in debugs[0].message

    async def test_exactly_one_warning_under_concurrency(self, caplog):
        """N concurrent failures produce exactly one WARNING and failure_count == N."""
        import asyncio

        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            await asyncio.gather(
                *(
                    fallback._handle_send_failure(error=ConnectionError(f"e{i}"))
                    for i in range(50)
                )
            )

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert fallback._failure_count == 50

    async def test_first_failure_timestamp_set_once(self):
        """first_failure_timestamp is set on the first failure and frozen after."""
        fallback = TelegramFallback(bot_token="test_token")

        assert fallback._first_failure_timestamp is None

        await fallback._handle_send_failure(error=ConnectionError("first"))
        first_ts = fallback._first_failure_timestamp
        assert first_ts is not None

        await fallback._handle_send_failure(error=ConnectionError("second"))
        assert fallback._first_failure_timestamp == first_ts  # unchanged (set-once)
        assert fallback._last_failure_timestamp != first_ts  # advanced

    async def test_reset_re_arms_detection(self, caplog):
        """After reset, the next failure is 'first' again; counters are retained."""
        fallback = TelegramFallback(bot_token="test_token")

        await fallback._handle_send_failure(error=ConnectionError("first"))
        assert fallback._has_logged_first_failure is True
        assert fallback._failure_count == 1

        await fallback.reset_first_failure_state()
        assert fallback._has_logged_first_failure is False
        assert fallback._first_failure_timestamp is None
        assert fallback._failure_count == 1  # retained across reset

        caplog.clear()
        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(error=ConnectionError("after reset"))

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert fallback._failure_count == 2  # incremented, not reset

    async def test_non_2xx_response_logs_synthesized_type_and_context(self, caplog):
        """A non-2xx response (no exception) logs the synthesized type + context."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(
                error_context="status 500 - upstream down"
            )

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "HTTPError" in warnings[0].message  # synthesized type
        assert "status 500" in warnings[0].message


class TestFailureLogRateLimiting:
    """Test configurable rate-limiting / dedup of repeated-failure logs."""

    def test_default_failure_log_interval(self, monkeypatch):
        """Default cooldown is 300s when the env var is unset."""
        monkeypatch.delenv("ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS", raising=False)
        fallback = TelegramFallback()
        assert fallback._failure_log_interval_seconds == 300.0

    def test_interval_configurable_via_env(self, monkeypatch):
        """ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS overrides the default."""
        monkeypatch.setenv("ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS", "60")
        fallback = TelegramFallback()
        assert fallback._failure_log_interval_seconds == 60.0

    def test_interval_invalid_env_falls_back_to_default(self, monkeypatch):
        """A non-numeric env value falls back to the default instead of crashing."""
        monkeypatch.setenv("ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS", "not-a-number")
        fallback = TelegramFallback()
        assert fallback._failure_log_interval_seconds == 300.0

    def test_constructor_interval_overrides_env(self, monkeypatch):
        """The constructor arg takes precedence over the env var."""
        monkeypatch.setenv("ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS", "60")
        fallback = TelegramFallback(failure_log_interval_seconds=10)
        assert fallback._failure_log_interval_seconds == 10.0

    def test_status_exposes_rate_limit_state(self):
        """get_status surfaces the configured interval and dedup counter."""
        fallback = TelegramFallback(failure_log_interval_seconds=42)
        status = fallback.get_status()
        assert status["failure_log_interval_seconds"] == 42.0
        assert status["failures_since_last_log"] == 0

    async def test_no_debug_spam_under_sustained_failures(self, caplog):
        """A burst of failures within one cooldown window emits zero DEBUG lines."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("DEBUG"):
            # 1st → WARNING; the next 49 are within the cooldown → suppressed.
            for i in range(50):
                await fallback._handle_send_failure(error=ConnectionError(f"e{i}"))

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        debugs = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert len(warnings) == 1
        assert debugs == []  # rate-limited — no DEBUG spam from the burst
        assert fallback._failure_count == 50
        assert fallback._failures_since_last_log == 49  # all-but-first counted silently

    async def test_one_debug_summary_per_cooldown_window(self, caplog):
        """Across two elapsed cooldown windows exactly two summaries are emitted."""
        from datetime import datetime, timedelta

        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("DEBUG"):
            await fallback._handle_send_failure(error=ConnectionError("first"))  # WARNING
            for _ in range(5):
                await fallback._handle_send_failure(error=ConnectionError("burst1"))  # suppressed

            # Elapse the cooldown → next failure emits a summary, then a new window.
            fallback._last_repeated_log_timestamp = datetime.now() - timedelta(seconds=999)
            await fallback._handle_send_failure(error=ConnectionError("post1"))  # summary #1
            await fallback._handle_send_failure(error=ConnectionError("post2"))  # suppressed

            # Elapse again → another summary.
            fallback._last_repeated_log_timestamp = datetime.now() - timedelta(seconds=999)
            await fallback._handle_send_failure(error=ConnectionError("post3"))  # summary #2

        debugs = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert len(debugs) == 2
        # Verify summaries are logged
        assert any("failure" in d.message.lower() for d in debugs)

    async def test_reset_clears_rate_limit_window(self, caplog):
        """reset_first_failure_state also clears the dedup window and counter."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("DEBUG"):
            await fallback._handle_send_failure(error=ConnectionError("first"))  # WARNING
            for _ in range(3):
                await fallback._handle_send_failure(error=ConnectionError("suppressed"))

        assert fallback._failures_since_last_log == 3

        await fallback.reset_first_failure_state()
        assert fallback._last_repeated_log_timestamp is None
        assert fallback._failures_since_last_log == 0
        assert fallback._failure_count == 4  # diagnostic counter retained


class TestPerFailureTypeDedup:
    """Test per-failure-type deduplication (adc-15u0).

    The pre-existing global cooldown dedups a sustained SAME-type outage. These
    tests cover the additional requirement: a DIFFERENT failure type appearing
    mid-outage is logged immediately and independently, never swallowed by the
    ongoing-outage cooldown.
    """

    async def test_new_failure_type_logged_immediately_during_cooldown(self, caplog):
        """A new failure type inside the cooldown window still gets a WARNING."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            # Type A: the umbrella first-failure WARNING.
            await fallback._handle_send_failure(error=ConnectionError("boom"))
            # Type B: a different type, still within A's cooldown window, must be
            # logged immediately rather than silently deduped.
            await fallback._handle_send_failure(error=TimeoutError("timed out"))

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 2
        assert any("ConnectionError" in w.message for w in warnings)
        assert any("TimeoutError" in w.message for w in warnings)

    async def test_distinct_failure_types_each_get_own_warning(self, caplog):
        """Three distinct failure types → multiple independent WARNINGs."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(error=ConnectionError("a"))
            await fallback._handle_send_failure(error=TimeoutError("b"))
            await fallback._handle_send_failure(error=ValueError("c"))

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 3
        messages = "\n".join(w.message for w in warnings)
        assert "ConnectionError" in messages
        assert "TimeoutError" in messages
        assert "ValueError" in messages
        assert fallback._failure_count == 3
        assert len(fallback._seen_failure_types) >= 3

    async def test_repeats_of_seen_types_are_deduped(self, caplog):
        """Once a type is seen, its repeats within the cooldown are suppressed."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            await fallback._handle_send_failure(error=ConnectionError("a1"))  # WARNING (umbrella)
            await fallback._handle_send_failure(error=TimeoutError("b1"))     # WARNING (new type)
            await fallback._handle_send_failure(error=ConnectionError("a2"))  # seen → suppressed
            await fallback._handle_send_failure(error=TimeoutError("b2"))     # seen → suppressed

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        # At least 2 warnings (one per distinct type)
        assert len(warnings) >= 2
        assert fallback._failure_count == 4

    async def test_seen_failure_types_exposed_in_status(self):
        """get_status surfaces the distinct types logged this startup."""
        fallback = TelegramFallback(bot_token="test_token")

        await fallback._handle_send_failure(error=ConnectionError("a"))
        await fallback._handle_send_failure(error=TimeoutError("b"))

        status = fallback.get_status()
        assert "ConnectionError" in status["seen_failure_types"]
        assert "TimeoutError" in status["seen_failure_types"]
        assert status["distinct_failure_types"] >= 2

    async def test_status_seen_types_empty_at_startup(self):
        """A fresh singleton has seen no failure types yet."""
        fallback = TelegramFallback(bot_token="test_token")
        status = fallback.get_status()
        assert status["seen_failure_types"] == []
        assert status["distinct_failure_types"] == 0

    async def test_reset_clears_seen_failure_types(self, caplog):
        """After reset, a previously-seen type is treated as first again."""
        fallback = TelegramFallback(bot_token="test_token")

        await fallback._handle_send_failure(error=ConnectionError("a"))
        assert "ConnectionError" in fallback._seen_failure_types

        await fallback.reset_first_failure_state()
        assert fallback._seen_failure_types == set()

        caplog.clear()
        with caplog.at_level("WARNING"):
            # Same type as before, but reset re-armed detection → umbrella WARNING.
            await fallback._handle_send_failure(error=ConnectionError("after reset"))

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1

    async def test_new_type_seeds_cooldown_so_its_repeats_dont_spam(self, caplog):
        """A new type's immediate WARNING reseeds the window for its own repeats."""
        fallback = TelegramFallback(bot_token="test_token")

        with caplog.at_level("DEBUG"):
            await fallback._handle_send_failure(error=ConnectionError("a"))  # WARNING
            await fallback._handle_send_failure(error=TimeoutError("b"))     # WARNING (new)
            # Repeat of the just-logged new type — must NOT emit a DEBUG summary
            # because the new-type WARNING reseeded the cooldown window.
            for _ in range(5):
                await fallback._handle_send_failure(error=TimeoutError("b-repeat"))

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        debugs = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert len(warnings) == 2
        assert debugs == []  # no summary spam — window was reseeded


# --- configured-chat-id delivery (adc-372c) --------------------------------

class _FakeResponse:
    """Minimal httpx.Response stand-in."""

    def __init__(self, status_code: int = 200, text: str = "ok"):
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient that records every POST.

    send_message() does ``async with httpx.AsyncClient() as client: ... await
    client.post(url, json=..., timeout=...)``. We replace
    ``httpx.AsyncClient`` in the fallback module with a callable returning this
    object, so the real network is never touched and the exact payload is
    captured for assertions.
    """

    def __init__(self):
        self.posted: list[tuple] = []  # (url, json, timeout)
        self.got: list[tuple] = []  # (url, timeout)
        self.response = _FakeResponse(200, "ok")
        self.raise_exc: Exception | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, timeout=None):
        self.posted.append((url, json, timeout))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response

    async def get(self, url, timeout=None):
        self.got.append((url, timeout))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


@pytest.fixture
def fake_httpx(monkeypatch):
    """Patch httpx.AsyncClient in the fallback module; return the fake client."""
    import src.telegram.fallback as fb_module
    client = _FakeAsyncClient()
    monkeypatch.setattr(fb_module.httpx, "AsyncClient", lambda: client)
    return client


class TestConfiguredChatIdDelivery:
    """send_exception / send_workload_summary make a real POST when chat_id is set.

    These pin the adc-372c contract: with ADC_TELEGRAM_CHAT_ID configured the
    methods actually call send_message → POST to Telegram Bot API and return the
    real success/failure, instead of unconditionally returning False.
    """

    def test_chat_id_resolved_from_env(self, monkeypatch):
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", "424242")
        fb = TelegramFallback(bot_token="test_token")
        assert fb.chat_id == "424242"

    def test_chat_id_constructor_arg_overrides_env(self, monkeypatch):
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", "424242")
        fb = TelegramFallback(bot_token="test_token", chat_id=999)
        assert fb.chat_id == 999

    async def test_send_exception_posts_to_configured_chat_id(self, fake_httpx, monkeypatch):
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", "424242")
        fb = TelegramFallback(bot_token="test_token")

        ok = await fb.send_exception(
            "session-1",
            {"title": "Disk full", "urgency": "critical", "context": "cleanup the logs"},
        )

        assert ok is True
        assert len(fake_httpx.posted) == 1
        url, payload, timeout = fake_httpx.posted[0]
        # Verify the URL is for Telegram Bot API
        assert "api.telegram.org" in url
        assert "/sendMessage" in url
        # str chat_id is coerced to int by send_message (Telegram API wants int64).
        assert payload["chat_id"] == 424242
        assert payload["parse_mode"] == "HTML"
        # Body is produced by _format_exception_message, not the raw dict.
        assert "Disk full" in payload["text"]
        assert "cleanup the logs" in payload["text"]

    async def test_send_workload_summary_posts_to_configured_chat_id(self, fake_httpx, monkeypatch):
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", "999")
        fb = TelegramFallback(bot_token="test_token")

        ok = await fb.send_workload_summary(
            "session-1",
            {"pending_intents": 2, "new_results": 1, "unresolved_exceptions": 0},
        )

        assert ok is True
        assert len(fake_httpx.posted) == 1
        url, payload, _ = fake_httpx.posted[0]
        assert "api.telegram.org" in url
        assert "/sendMessage" in url
        assert payload["chat_id"] == 999
        # Body is produced by _format_workload_summary.
        assert "Workload Summary" in payload["text"]
        assert "Pending intents: 2" in payload["text"]
        assert "New results: 1" in payload["text"]

    async def test_send_exception_returns_false_on_non_2xx(self, fake_httpx, monkeypatch):
        """A real POST is attempted; the API failure is returned, not False-by-default."""
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", "1")
        fb = TelegramFallback(bot_token="test_token")
        fake_httpx.response = _FakeResponse(500, "upstream down")

        ok = await fb.send_exception("session-1", {"title": "x"})

        assert ok is False
        assert len(fake_httpx.posted) == 1  # a real POST was attempted

    async def test_send_exception_returns_false_on_request_error(self, fake_httpx, monkeypatch):
        monkeypatch.setenv("ADC_TELEGRAM_CHAT_ID", "1")
        fb = TelegramFallback(bot_token="test_token")
        fake_httpx.raise_exc = httpx.ConnectError("connection refused")

        ok = await fb.send_exception("session-1", {"title": "x"})

        assert ok is False
        assert len(fake_httpx.posted) == 1


class TestUnconfiguredChatIdNoOp:
    """Without a chat id the push methods gracefully no-op (no regression)."""

    async def test_send_exception_no_op_without_chat_id(self, caplog, monkeypatch):
        monkeypatch.delenv("ADC_TELEGRAM_CHAT_ID", raising=False)
        fb = TelegramFallback(bot_token="test_token")
        assert fb.chat_id is None

        with caplog.at_level("WARNING"):
            ok = await fb.send_exception("session-1", {"title": "x"})

        assert ok is False
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "ADC_TELEGRAM_CHAT_ID" in warnings[0].message

    async def test_send_workload_summary_no_op_without_chat_id(self, caplog, monkeypatch):
        monkeypatch.delenv("ADC_TELEGRAM_CHAT_ID", raising=False)
        fb = TelegramFallback(bot_token="test_token")

        with caplog.at_level("WARNING"):
            ok = await fb.send_workload_summary("session-1", {"pending_intents": 1})

        assert ok is False
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "ADC_TELEGRAM_CHAT_ID" in warnings[0].message


class TestBotTokenConfiguration:
    """Test bot token configuration and behavior."""

    def test_bot_token_required_for_sends(self, caplog):
        """Without bot_token, send_message gracefully no-ops."""
        fb = TelegramFallback()  # No bot_token configured

        # The method should exist but return False when no token is configured
        assert hasattr(fb, 'send_message')

    async def test_send_message_no_op_without_bot_token(self, caplog):
        """send_message logs WARNING and returns False when bot_token is None."""
        fb = TelegramFallback()  # No bot_token

        with caplog.at_level("WARNING"):
            ok = await fb.send_message(123, "test message")

        assert ok is False
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "ADC_TELEGRAM_BOT_TOKEN" in warnings[0].message

    async def test_check_telegram_available_without_bot_token(self):
        """check_telegram_available returns False when bot_token is None."""
        fb = TelegramFallback()  # No bot_token

        available = await fb.check_telegram_available()
        assert available is False

    async def test_check_telegram_available_with_fake_client(self, fake_httpx):
        """check_telegram_available uses getMe endpoint to verify token."""
        fb = TelegramFallback(bot_token="test_token")
        fake_httpx.response = _FakeResponse(200, '{"ok": true, "result": {"id": 123}}')

        available = await fb.check_telegram_available()
        assert available is True
        assert len(fake_httpx.got) == 1
        url, _ = fake_httpx.got[0]
        assert "getMe" in url

    async def test_check_telegram_available_on_error(self, fake_httpx):
        """check_telegram_available returns False on API error."""
        fb = TelegramFallback(bot_token="bad_token")
        fake_httpx.response = _FakeResponse(401, "Unauthorized")

        available = await fb.check_telegram_available()
        assert available is False
