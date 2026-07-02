"""
Telegram fallback surface integration.

Integrates with telegram-claude-bridge to provide an always-available
fallback surface for results and exceptions.
"""

import logging
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

    def __init__(self, bridge_url: str | None = None):
        import os
        self.bridge_url = bridge_url or os.getenv(
            "ADC_TELEGRAM_BRIDGE_URL", self.DEFAULT_BRIDGE_URL
        )

    async def send_message(
        self,
        chat_id: int | str,
        message: str,
        parse_mode: str = "Markdown",
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
                    return True
                else:
                    logger.warning(
                        f"Failed to send Telegram message: {response.status_code} - {response.text}"
                    )
                    return False

        except httpx.RequestError as e:
            logger.error(f"Request error sending to Telegram: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending to Telegram: {e}")
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

        Exceptions are formatted prominently and may include action buttons.
        """
        message = self._format_exception_message(exception)
        return await self.send_message(session_id, message, parse_mode="Markdown")

    async def send_workload_summary(
        self,
        session_id: str,
        summary: dict,
    ) -> bool:
        """
        Send a workload summary to Telegram.

        Sent when a user reconnects after being away.
        """
        message = self._format_workload_summary(summary)
        return await self.send_message(session_id, message)

    async def register_surface(self, session_id: str, telegram_chat_id: str) -> bool:
        """
        Register a Telegram surface for a session.

        Called when a Telegram user starts a conversation.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.bridge_url}/register_surface",
                    json={
                        "session_id": session_id,
                        "chat_id": telegram_chat_id,
                    },
                    timeout=10.0,
                )

                return response.status_code == 200

        except Exception as e:
            logger.error(f"Error registering Telegram surface: {e}")
            return False

    async def check_bridge_available(self) -> bool:
        """Check if telegram-claude-bridge is available."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.bridge_url}/health",
                    timeout=5.0,
                )
                return response.status_code == 200
        except Exception:
            return False

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
