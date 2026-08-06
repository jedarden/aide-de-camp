"""
Telegram fallback surface integration.

Direct Telegram Bot API integration for delivering results and exceptions
to a fixed chat_id. Per ADR-1 (2026-07-20), this is decoupled from
telegram-claude-bridge and uses the Telegram Bot API directly.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx

from .state_tracker import BridgeState

logger = logging.getLogger(__name__)


class TelegramFallback:
    """
    Telegram Bot API integration for aide-de-camp.

    This module provides:
    - Message sending to a fixed chat_id
    - Result delivery when no other surface is available
    - Exception push for critical/high urgency items

    Per ADR-1, this is a direct Telegram Bot API integration, not coupled
    to telegram-claude-bridge. All messages go to one configured chat_id.
    """

    # Telegram Bot API endpoint
    TELEGRAM_API_BASE = "https://api.telegram.org"
    # Minimum spacing (seconds) between repeated-failure DEBUG summaries, so a
    # sustained outage cannot spam the log. Configurable via the
    # ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS env var.
    DEFAULT_FAILURE_LOG_INTERVAL_SECONDS = 300.0

    def __init__(
        self,
        bot_token: str | None = None,
        failure_log_interval_seconds: float | None = None,
        chat_id: str | int | None = None,
    ):
        import os
        # Telegram bot token. Resolution order:
        # constructor arg → ADC_TELEGRAM_BOT_TOKEN env var → None.
        # None (default) means all push methods gracefully no-op with a WARNING
        # rather than hard-failing, preserving the pre-config behavior.
        self.bot_token = bot_token or os.getenv("ADC_TELEGRAM_BOT_TOKEN") or None

        # Telegram chat ID for the single user of this personal app (plan.md
        # Tech Stack: "single-user app"). There is intentionally NO multi-user
        # session→chat mapping -- one configured chat id is all the routing
        # exception/workload/bead-close pushes need. Resolution order:
        # constructor arg → ADC_TELEGRAM_CHAT_ID env var → None.
        # None (default) means the push methods gracefully no-op with a WARNING
        # rather than hard-failing, preserving the pre-config behavior.
        if chat_id is not None:
            self.chat_id = chat_id
        else:
            self.chat_id = os.getenv("ADC_TELEGRAM_CHAT_ID") or None

        # Rate-limit window for repeated-failure DEBUG logs. Resolution order:
        # constructor arg → ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS env var
        # → DEFAULT_FAILURE_LOG_INTERVAL_SECONDS. Invalid env values fall back
        # to the default rather than crashing the singleton on startup.
        interval = failure_log_interval_seconds
        if interval is None:
            env_val = os.getenv("ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS")
            try:
                interval = float(env_val) if env_val else self.DEFAULT_FAILURE_LOG_INTERVAL_SECONDS
            except (TypeError, ValueError):
                interval = self.DEFAULT_FAILURE_LOG_INTERVAL_SECONDS
        self._failure_log_interval_seconds: float = float(interval)

        # Reachability — a separate logical object; its OTHER writers (send success
        # below, and the health check) are intentionally NOT under the failure lock.
        self._is_reachable = None  # None = unknown, True = reachable, False = unreachable
        # When reachability was last determined (startup probe or a reactive
        # send success/failure). Mirrors every write to _is_reachable via
        # _set_reachable(); None until the first determination. Exposed in the
        # /api/v1/status/telegram payload as ``last_check_time``.
        self._last_check_time: Optional[datetime] = None

        # First-failure record: flat instance vars on the singleton, per-startup,
        # no persistence. Exactly one WARNING is emitted per process startup.
        self._has_logged_first_failure: bool = False
        self._has_failed_since_startup: bool = False  # adc-2r8hh: simple failure flag
        self._failure_count: int = 0
        self._first_failure_timestamp: Optional[datetime] = None  # set-once
        self._last_failure_timestamp: Optional[datetime] = None  # updated every failure

        # Distinct failure types already logged (WARNING'd) this startup. Drives
        # per-failure-type dedup (adc-15u0): a type NOT in this set is logged
        # immediately and independently, so a new failure type is never swallowed
        # by the ongoing-outage cooldown. Cleared by reset_first_failure_state.
        self._seen_failure_types: set[str] = set()

        # Rate-limit / dedup window for repeated-failure logs. Failures that occur
        # inside a quiet window are counted silently; when the window elapses one
        # DEBUG summary is emitted reporting the burst size, then a new window
        # starts. `_last_repeated_log_timestamp` is seeded by the first-failure
        # WARNING so it is not immediately followed by a DEBUG storm.
        self._last_repeated_log_timestamp: Optional[datetime] = None
        self._failures_since_last_log: int = 0

        # Serializes the first-failure claim-and-set. The critical section
        # (_record_failure_locked) is await-free on purpose so the read-then-set
        # of the flag cannot be interleaved by another coroutine.
        self._first_failure_lock: asyncio.Lock = asyncio.Lock()

        # Bridge state tracker for reachability and failure deduplication
        self._state_tracker = BridgeState()

    async def send_message(
        self,
        chat_id: int | str,
        message: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """
        Send a message to a Telegram chat via the Bot API.

        Args:
            chat_id: Telegram chat ID (int or str)
            message: Message text to send
            parse_mode: Parse mode for formatting (Markdown, HTML, etc.)

        Returns:
            True if successful, False otherwise.
        """
        if self.bot_token is None:
            logger.warning(
                f"send_message() called - no Telegram bot token configured "
                f"(set ADC_TELEGRAM_BOT_TOKEN). Message send skipped."
            )
            return False

        try:
            async with httpx.AsyncClient() as client:
                # Telegram Bot API sendMessage endpoint
                # https://core.telegram.org/bots/api#sendmessage
                response = await client.post(
                    f"{self.TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage",
                    json={
                        "chat_id": int(chat_id) if isinstance(chat_id, str) else chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                    },
                    timeout=10.0,
                )

                if response.status_code == 200:
                    logger.info(f"Sent Telegram message to chat {chat_id}")
                    # Update reachability state - reset state tracker if was unreachable
                    if not self._state_tracker.is_reachable:
                        self._state_tracker.mark_as_reachable()
                    self._set_reachable(True)  # Update reachability state
                    return True
                else:
                    error_msg = f"status {response.status_code} - {response.text}"
                    await self._handle_send_failure(error_context=error_msg)
                    return False

        except httpx.RequestError as e:
            await self._handle_send_failure(error=e)
            return False
        except Exception as e:
            await self._handle_send_failure(error=e)
            return False

    async def send_result(self, chat_id: int | str, result: dict) -> bool:
        """
        Send a structured result to Telegram.

        Args:
            chat_id: Telegram chat ID
            result: Result dict with keys: summary, urgency, data

        Formats the result as a readable message and sends it.
        """
        message = self._format_result_message(result)
        return await self.send_message(chat_id, message)

    async def send_exception(
        self,
        session_id: str,
        exception: dict,
    ) -> bool:
        """
        Send an exception to Telegram for human attention.

        Routes to the single configured chat id (ADC_TELEGRAM_CHAT_ID). When no
        chat id is configured this is a graceful no-op: a WARNING is logged and
        False is returned, matching the pre-config behavior. When configured, the
        exception is formatted via ``_format_exception_message`` and delivered
        through ``send_message``, returning the bridge's real success/failure.
        """
        if self.chat_id is None:
            logger.warning(
                f"send_exception() called for session {session_id} - "
                f"no Telegram chat id configured (set ADC_TELEGRAM_CHAT_ID). "
                f"Exception push skipped."
            )
            return False

        message = self._format_exception_message(exception)
        return await self.send_message(self.chat_id, message)

    async def send_workload_summary(
        self,
        session_id: str,
        summary: dict,
    ) -> bool:
        """
        Send a workload summary to Telegram.

        Routes to the single configured chat id (ADC_TELEGRAM_CHAT_ID). When no
        chat id is configured this is a graceful no-op: a WARNING is logged and
        False is returned, matching the pre-config behavior. When configured, the
        summary is formatted via ``_format_workload_summary`` and delivered
        through ``send_message``, returning the bridge's real success/failure.
        """
        if self.chat_id is None:
            logger.warning(
                f"send_workload_summary() called for session {session_id} - "
                f"no Telegram chat id configured (set ADC_TELEGRAM_CHAT_ID). "
                f"Workload summary push skipped."
            )
            return False

        message = self._format_workload_summary(summary)
        return await self.send_message(self.chat_id, message)


    async def check_telegram_available(self) -> bool:
        """Check if Telegram Bot API (bridge) is available.

        Uses the getMe endpoint to verify bot token validity and bridge
        reachability. Timeout is set to 2.5 seconds to avoid blocking
        application startup.

        Returns:
            True if the bridge is reachable, False otherwise.
        """
        if self.bot_token is None:
            self._state_tracker.mark_as_unreachable(datetime.now())
            self._set_reachable(False)
            return False

        try:
            async with httpx.AsyncClient() as client:
                # Use getMe endpoint to verify bot token validity
                # https://core.telegram.org/bots/api#getme
                response = await client.get(
                    f"{self.TELEGRAM_API_BASE}/bot{self.bot_token}/getMe",
                    timeout=2.5,
                )
                is_available = response.status_code == 200
                if is_available:
                    self._state_tracker.mark_as_reachable()
                else:
                    self._state_tracker.mark_as_unreachable(datetime.now())
                self._set_reachable(is_available)
                return is_available
        except Exception:
            self._state_tracker.mark_as_unreachable(datetime.now())
            self._set_reachable(False)
            return False

    def _set_reachable(self, value: bool, *, now: Optional[datetime] = None) -> None:
        """Record a reachability determination and when it was made.

        Centralizes every write to ``_is_reachable`` so ``last_check_time``
        always reflects the most recent determination — whether it came from
        the startup health probe (``check_bridge_available``) or a reactive
        update during ``send_message`` (success → True, failure → False).

        Args:
            value: The reachability value to record.
            now: Optional precomputed timestamp to reuse (the failure path
                already computes one); defaults to ``datetime.now()``.
        """
        self._is_reachable = value
        self._last_check_time = now or datetime.now()

    def get_status(self) -> dict:
        """
        Get the current Telegram integration status.

        Lock-free read: single-field atomic reads; monitoring tolerates staleness.

        Returns:
            Dict with keys:
            - reachable: bool or None (None = unknown yet)
            - bot_configured: bool (whether bot_token is set)
            - chat_id_configured: bool (whether chat_id is set)
            - chat_id: str or None
            - last_check_time: ISO-8601 string or None (when reachability was
              last determined, via the startup probe or a reactive send)
            - failure_count: int
            - has_logged_first_failure: bool
            - has_failed_since_startup: bool (adc-2r8hh: flag tracking if any
              failure occurred since service start)
            - first_failure_timestamp: ISO-8601 string or None
            - last_failure_timestamp: ISO-8601 string or None
            - failure_log_interval_seconds: float (configured rate-limit window)
            - failures_since_last_log: int (dedup counter for the current window)
            - seen_failure_types: list[str] (distinct failure types logged this
              startup; per-type dedup — adc-15u0)
            - distinct_failure_types: int (len of seen_failure_types)
        """
        return {
            "reachable": self._is_reachable,
            "bot_configured": self.bot_token is not None,
            "chat_id_configured": self.chat_id is not None,
            "chat_id": self.chat_id,
            "last_check_time": self._last_check_time.isoformat()
            if self._last_check_time else None,
            "failure_count": self._failure_count,
            "has_logged_first_failure": self._has_logged_first_failure,
            "has_failed_since_startup": self._has_failed_since_startup,
            "first_failure_timestamp": self._first_failure_timestamp.isoformat()
            if self._first_failure_timestamp else None,
            "last_failure_timestamp": self._last_failure_timestamp.isoformat()
            if self._last_failure_timestamp else None,
            "failure_log_interval_seconds": self._failure_log_interval_seconds,
            "failures_since_last_log": self._failures_since_last_log,
            "seen_failure_types": sorted(self._seen_failure_types),
            "distinct_failure_types": len(self._seen_failure_types),
        }

    async def _handle_send_failure(
        self,
        error: Exception | None = None,
        error_context: str = "",
    ) -> None:
        """Reactive detection entry for a Telegram send failure.

        Called only from ``send_message``'s failure branches. Logs a WARNING that
        includes the error type and message on the FIRST failure after startup;
        every later failure in the startup is logged at DEBUG only. Exactly one
        WARNING is emitted per process startup.

        Args:
            error: The exception that caused the failure, if any. Its type name
                and message are included in the log. ``None`` for non-2xx HTTP
                responses (httpx does not raise for those).
            error_context: Free-form context (e.g. ``"status 500 - ..."``) used as
                the message when no exception is available, or to enrich one.
        """
        async with self._first_failure_lock:
            self._record_failure_locked(error=error, error_context=error_context)

    def _repeated_log_cooldown_elapsed(self, now: datetime) -> bool:
        """True if the rate-limit window has elapsed and a DEBUG summary may be logged.

        Caller MUST hold ``_first_failure_lock``. Returns True immediately when no
        repeated log has been emitted yet in this startup, or when the timestamp
        is None (first failure hasn't started the rate-limit window yet).
        """
        if self._last_repeated_log_timestamp is None:
            return True
        elapsed = (now - self._last_repeated_log_timestamp).total_seconds()
        return elapsed >= self._failure_log_interval_seconds

    def _record_failure_locked(
        self,
        error: Exception | None = None,
        error_context: str = "",
    ) -> bool:
        """Record a failure and emit the appropriate (rate-limited) log line.

        Caller MUST hold ``_first_failure_lock``. Sync on purpose — no ``await``
        inside, so the read-then-set of the flags cannot be interleaved by
        another coroutine.

        Logging policy (per-failure-type dedup, adc-15u0):
        - The FIRST failure after startup emits exactly one WARNING (the
          ``_has_logged_first_failure`` False→True claim, one per process startup)
          and seeds that failure type's dedup window.
        - A later failure of a NEW type (one not in ``_seen_failure_types``) is
          logged immediately and independently with its own WARNING, so a
          different failure type is never swallowed by the ongoing-outage
          cooldown. It also (re)seeds the rate-limit window.
        - A later failure of an already-seen type is rate-limited: at most one
          DEBUG summary per ``_failure_log_interval_seconds`` window. Failures
          inside a window are counted silently (deduped) so a sustained outage
          cannot spam the log.

        ``_failure_count`` and ``_last_failure_timestamp`` are updated on every
        call regardless of whether anything is logged.

        Returns:
            True iff THIS call performed the first-failure claim (the
            ``_has_logged_first_failure`` False→True flip); False otherwise.
            "First" is the winner of the claim, not a timestamp comparison.
        """
        now = datetime.now()
        self._set_reachable(False, now=now)

        # Update state tracker for reachability and deduplication
        self._state_tracker.mark_as_unreachable(now)

        # Log WARNING on first failure after bridge was reachable
        # This uses the state tracker to prevent duplicate warnings per failure streak
        if self._state_tracker.should_log_failure():
            if error is not None:
                error_type = type(error).__name__
                message = str(error) or error_context or "unknown error"
                logger.warning(
                    f"Telegram bridge unreachable: send failed. "
                    f"Error type: {error_type}. Error: {message}. "
                    f"Bridge may be down or network issue."
                )
            else:
                message = error_context or "unknown error"
                logger.warning(
                    f"Telegram bridge unreachable: send failed. "
                    f"Error: {message}. Bridge may be down or network issue."
                )

        self._failure_count += 1
        self._last_failure_timestamp = now
        self._failures_since_last_log += 1

        if error is not None:
            error_type = type(error).__name__
            message = str(error) or error_context or "unknown error"
        else:
            error_type = "HTTPError"
            message = error_context or "unknown error"

        is_new_failure_type = error_type not in self._seen_failure_types

        if not self._has_logged_first_failure:
            # First failure after startup — WARNING with error type + message.
            # This is the single per-startup "umbrella" WARNING (adc-hyqc); it
            # also records + seeds this failure type's dedup window.
            # Skip if state tracker already logged this failure streak
            if not self._state_tracker._last_failure_logged:
                self._has_logged_first_failure = True
                self._has_failed_since_startup = True  # adc-2r8hh: mark that a failure occurred
                self._first_failure_timestamp = now
                self._seen_failure_types.add(error_type)
                # Start the rate-limit window from now
                self._last_repeated_log_timestamp = now
                self._failures_since_last_log = 0
                logger.warning(
                    f"Telegram bridge unreachable: send failed. "
                    f"Error type: {error_type}. Error: {message}. "
                    f"Subsequent failures of the same type are rate-limited (one "
                    f"DEBUG summary per {self._failure_log_interval_seconds:g}s); "
                    f"a different failure type is logged independently."
                )
                return True
            else:
                # State tracker already logged, just mark startup flags without duplicate WARNING
                self._has_logged_first_failure = True
                self._has_failed_since_startup = True
                self._first_failure_timestamp = now
                self._seen_failure_types.add(error_type)
                self._last_repeated_log_timestamp = now
                self._failures_since_last_log = 0
                return True

        if is_new_failure_type:
            # A DIFFERENT failure type appeared during an ongoing outage. Log it
            # immediately and independently so it is never swallowed by the
            # same-type cooldown (adc-15u0: per-failure-type dedup). (Re)seed the
            # rate-limit window so this type's immediate repeats are deduped.
            self._seen_failure_types.add(error_type)
            self._last_repeated_log_timestamp = now
            # Reset the counter for the new failure type, starting from this one
            self._failures_since_last_log = 0
            logger.warning(
                f"New Telegram send failure type during ongoing outage: "
                f"{error_type}. Error: {message}. "
                f"Logged independently of the "
                f"{self._failure_log_interval_seconds:g}s same-type cooldown. "
                f"(Total failures: {self._failure_count}; distinct failure "
                f"types: {len(self._seen_failure_types)}.)"
            )
            return False

        # Repeated failure of an already-seen type — emit a DEBUG summary only
        # when the rate-limit window has elapsed; otherwise count it silently to
        # avoid log spam.
        if self._repeated_log_cooldown_elapsed(now):
            batch = self._failures_since_last_log  # failures accumulated since last log
            # Only log if there are actual failures to report (avoid empty logs)
            if batch > 0:
                logger.debug(
                    f"Repeated Telegram send failures: {batch} failure(s) since last "
                    f"log (total {self._failure_count}). "
                    f"Latest error type: {error_type}. Error: {message}."
                )
                self._last_repeated_log_timestamp = now
                self._failures_since_last_log = 0

        return False

    async def reset_first_failure_state(self) -> None:
        """Re-arm first-failure detection.

        Resets the claim flag, the first-failure timestamp, and the rate-limit
        window under the lock, so the next failure is treated as "first" again
        and starts a fresh quiet period. Used by tests and by future
        recovery-based reset hooks. The diagnostic counters
        (``_failure_count``, ``_last_failure_timestamp``) are intentionally
        retained.
        """
        async with self._first_failure_lock:
            self._has_logged_first_failure = False
            self._has_failed_since_startup = False  # adc-2r8hh: reset the failure flag
            self._first_failure_timestamp = None
            self._last_repeated_log_timestamp = None
            self._failures_since_last_log = 0
            # Re-arm per-type dedup so the next failure (even of a previously
            # seen type) is treated as a fresh first occurrence.
            self._seen_failure_types.clear()

    def _format_result_message(self, result: dict) -> str:
        """Format a result as a Telegram message."""
        summary = result.get("summary", "Result available")
        urgency = result.get("urgency", "normal")

        emoji_map = {
            "critical": "🚨",
            "high": "⚠️",
            "normal": "📌",
            "low": "💬",
        }

        emoji = emoji_map.get(urgency, "📌")

        lines = [
            f"{emoji} *{summary}*",
            "",
        ]

        # Add detail from data
        data = result.get("data", {})

        if "bead_id" in data:
            lines.append(f"📝 Bead: `{data['bead_id']}`")

        if "title" in data:
            lines.append(f"📋 {data['title']}")

        if "status" in data:
            lines.append(f"✅ Status: {data['status']}")

        # Add truncated body if available
        if "body" in data and data["body"]:
            body = data["body"]
            if len(body) > 300:
                body = body[:300] + "..."
            lines.append("")
            lines.append(f"📄 {body}")

        return "\n".join(lines)

    def _format_exception_message(self, exception: dict) -> str:
        """Format an exception as a prominent Telegram message."""
        title = exception.get("title", "Attention Required")
        urgency = exception.get("urgency", "normal")
        context = exception.get("context", "")
        options = exception.get("options", [])

        emoji_map = {
            "critical": "🚨",
            "high": "⚠️",
            "normal": "🔔",
        }

        emoji = emoji_map.get(urgency, "🔔")

        lines = [
            f"{emoji} *{title}*",
            "",
        ]

        if context:
            lines.append(f"📝 {context}")
            lines.append("")

        if options:
            lines.append("🔹 Options:")
            for i, option in enumerate(options, 1):
                lines.append(f"  {i}. {option}")

        lines.append("")
        lines.append("Reply with your choice or type a custom response.")

        return "\n".join(lines)

    def _format_workload_summary(self, summary: dict) -> str:
        """Format a workload summary as a Telegram message."""
        pending = summary.get("pending_intents", 0)
        new_results = summary.get("new_results", 0)
        exceptions = summary.get("unresolved_exceptions", 0)

        lines = [
            "📊 *Workload Summary*",
            "",
        ]

        if pending > 0:
            lines.append(f"⏳ Pending intents: {pending}")

        if new_results > 0:
            lines.append(f"📌 New results: {new_results}")

        if exceptions > 0:
            lines.append(f"🚨 Unresolved exceptions: {exceptions}")

        if not any([pending, new_results, exceptions]):
            lines.append("✨ All caught up!")

        return "\n".join(lines)


# Global Telegram fallback instance
_telegram_fallback: Optional[TelegramFallback] = None


def get_telegram_fallback() -> TelegramFallback:
    """Get or create the global Telegram fallback instance."""
    global _telegram_fallback
    if _telegram_fallback is None:
        _telegram_fallback = TelegramFallback()
    return _telegram_fallback
