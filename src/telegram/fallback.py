"""
Telegram fallback surface integration.

Integrates with telegram-claude-bridge to provide an always-available
fallback surface for results and exceptions.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class TelegramFallback:
    """
    Telegram surface integration using telegram-claude-bridge.

    telegram-claude-bridge runs on the Tailscale mesh at:
    http://telegram-claude-bridge:8000

    This module provides:
    - Message sending to active sessions
    - Result delivery when no other surface is available
    - Exception push for critical/high urgency items
    """

    # telegram-claude-bridge endpoint (Tailscale mesh)
    # Configurable via ADC_TELEGRAM_BRIDGE_URL env var
    DEFAULT_BRIDGE_URL = "http://telegram-claude-bridge:8000"
    # Minimum spacing (seconds) between repeated-failure DEBUG summaries, so a
    # sustained outage cannot spam the log. Configurable via the
    # ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS env var.
    DEFAULT_FAILURE_LOG_INTERVAL_SECONDS = 300.0

    def __init__(
        self,
        bridge_url: str | None = None,
        failure_log_interval_seconds: float | None = None,
    ):
        import os
        self.bridge_url = bridge_url or os.getenv(
            "ADC_TELEGRAM_BRIDGE_URL", self.DEFAULT_BRIDGE_URL
        )
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

        # First-failure record: flat instance vars on the singleton, per-startup,
        # no persistence. Exactly one WARNING is emitted per process startup.
        self._has_logged_first_failure: bool = False
        self._failure_count: int = 0
        self._first_failure_timestamp: Optional[datetime] = None  # set-once
        self._last_failure_timestamp: Optional[datetime] = None  # updated every failure

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

    async def send_message(
        self,
        chat_id: int | str,
        message: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """
        Send a message to a Telegram chat.

        Args:
            chat_id: Telegram chat ID (int or str)
            message: Message text to send
            parse_mode: Parse mode for formatting (Markdown, HTML, etc.)

        Returns:
            True if successful, False otherwise.
        """
        try:
            async with httpx.AsyncClient() as client:
                # telegram-claude-bridge proxy API uses /send endpoint
                # Contract: {chat_id, text, parse_mode?, thread_id?, reply_to_message_id?}
                response = await client.post(
                    f"{self.bridge_url}/send",
                    json={
                        "chat_id": int(chat_id) if isinstance(chat_id, str) else chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                    },
                    timeout=10.0,
                )

                if response.status_code == 200:
                    logger.info(f"Sent Telegram message to chat {chat_id}")
                    self._is_reachable = True  # Update reachability state
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

        NOTE: This method requires a session→telegram_chat_id mapping which is not
        currently implemented. telegram-claude-bridge uses pull-based architecture
        (manages sessions internally per forum topic), not push-based message delivery.
        """
        logger.warning(
            f"send_exception() called for session {session_id} - "
            f"session→telegram_chat mapping not implemented. "
            f"telegram-claude-bridge uses pull-based architecture."
        )
        return False

    async def send_workload_summary(
        self,
        session_id: str,
        summary: dict,
    ) -> bool:
        """
        Send a workload summary to Telegram.

        NOTE: This method requires a session→telegram_chat_id mapping which is not
        currently implemented. telegram-claude-bridge uses pull-based architecture
        (manages sessions internally per forum topic), not push-based message delivery.
        """
        logger.warning(
            f"send_workload_summary() called for session {session_id} - "
            f"session→telegram_chat mapping not implemented. "
            f"telegram-claude-bridge uses pull-based architecture."
        )
        return False

    async def register_surface(self, session_id: str, telegram_chat_id: str) -> bool:
        """
        Register a Telegram surface for a session.

        Called when a Telegram user starts a conversation.

        NOTE: The /register_surface endpoint does NOT exist in telegram-claude-bridge.
        This method is a no-op stub for API compatibility. telegram-claude-bridge
        uses a pull-based architecture where it manages sessions internally per forum topic,
        not a push-based model where external systems register delivery surfaces.

        Returns True for compatibility (pretends registration succeeded).
        """
        logger.warning(
            f"register_surface() called for session {session_id} - "
            f"telegram-claude-bridge does not support surface registration. "
            f"This is a no-op stub."
        )
        return True

    async def check_bridge_available(self) -> bool:
        """Check if telegram-claude-bridge is available."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.bridge_url}/health",
                    timeout=5.0,
                )
                is_available = response.status_code == 200
                self._is_reachable = is_available
                return is_available
        except Exception:
            self._is_reachable = False
            return False

    def get_bridge_status(self) -> dict:
        """
        Get the current bridge status.

        Lock-free read: single-field atomic reads; monitoring tolerates staleness.

        Returns:
            Dict with keys:
            - reachable: bool or None (None = unknown yet)
            - bridge_url: str
            - failure_count: int
            - has_logged_first_failure: bool
            - first_failure_timestamp: ISO-8601 string or None
            - last_failure_timestamp: ISO-8601 string or None
            - failure_log_interval_seconds: float (configured rate-limit window)
            - failures_since_last_log: int (dedup counter for the current window)
        """
        return {
            "reachable": self._is_reachable,
            "bridge_url": self.bridge_url,
            "failure_count": self._failure_count,
            "has_logged_first_failure": self._has_logged_first_failure,
            "first_failure_timestamp": self._first_failure_timestamp.isoformat()
            if self._first_failure_timestamp else None,
            "last_failure_timestamp": self._last_failure_timestamp.isoformat()
            if self._last_failure_timestamp else None,
            "failure_log_interval_seconds": self._failure_log_interval_seconds,
            "failures_since_last_log": self._failures_since_last_log,
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
        repeated log has been emitted yet in this startup.
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

        Logging policy:
        - The FIRST failure after startup emits exactly one WARNING (the
          ``_has_logged_first_failure`` False→True claim, one per process startup).
        - Later failures are rate-limited: at most one DEBUG summary per
          ``_failure_log_interval_seconds`` window. Failures inside a window are
          counted silently (deduped) so a sustained outage cannot spam the log.

        ``_failure_count`` and ``_last_failure_timestamp`` are updated on every
        call regardless of whether anything is logged.

        Returns:
            True iff THIS call performed the first-failure claim (the
            ``_has_logged_first_failure`` False→True flip); False otherwise.
            "First" is the winner of the claim, not a timestamp comparison.
        """
        now = datetime.now()
        self._is_reachable = False
        self._failure_count += 1
        self._last_failure_timestamp = now
        self._failures_since_last_log += 1

        if error is not None:
            error_type = type(error).__name__
            message = str(error) or error_context or "unknown error"
        else:
            error_type = "HTTPError"
            message = error_context or "unknown error"

        if not self._has_logged_first_failure:
            # First failure after startup — WARNING with error type + message.
            self._has_logged_first_failure = True
            self._first_failure_timestamp = now
            # Seed the rate-limit window so the WARNING is not immediately
            # followed by a DEBUG storm.
            self._last_repeated_log_timestamp = now
            self._failures_since_last_log = 0
            logger.warning(
                f"First Telegram send failure detected at {self.bridge_url}. "
                f"Error type: {error_type}. Error: {message}. "
                f"Subsequent failures are rate-limited (one DEBUG summary per "
                f"{self._failure_log_interval_seconds:g}s)."
            )
            return True

        # Repeated failure — emit a DEBUG summary only when the rate-limit window
        # has elapsed; otherwise count it silently to avoid log spam.
        if self._repeated_log_cooldown_elapsed(now):
            batch = self._failures_since_last_log  # failures accumulated since last log
            logger.debug(
                f"Repeated Telegram send failures: {batch} failure(s) since last "
                f"log (total {self._failure_count}) at {self.bridge_url}. "
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
            self._first_failure_timestamp = None
            self._last_repeated_log_timestamp = None
            self._failures_since_last_log = 0

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
