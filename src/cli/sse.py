"""
Server-Sent Events (SSE) streaming utilities.

Provides utilities for parsing and handling SSE streams from the aide-de-camp server.
"""

import asyncio
import json
from typing import AsyncIterator, Dict, Any


def parse_sse_line(line: str) -> tuple[str, str | None]:
    """
    Parse a single SSE line.

    Returns (event_type, data) tuple.
    """
    line = line.strip()
    if not line:
        return ("", None)

    if line.startswith("event:"):
        return (line[6:].strip(), None)
    elif line.startswith("data:"):
        return ("data", line[5:].strip())
    elif line.startswith("id:"):
        return ("id", line[4:].strip())
    elif line.startswith("retry:"):
        return ("retry", line[6:].strip())

    return ("", None)


async def parse_sse_stream(lines: AsyncIterator[str]) -> AsyncIterator[Dict[str, Any]]:
    """
    Parse SSE stream into event dictionaries.

    Yields dictionaries with 'event' and 'data' keys.
    """
    current_event = ""
    current_data_lines = []

    async for line in lines:
        if not line:
            continue

        event_type, value = parse_sse_line(line)

        if event_type and event_type not in ("data", "id", "retry"):
            # New event type
            current_event = event_type
            current_data_lines = []
        elif event_type == "data":
            current_data_lines.append(value)

        # Empty line marks end of event
        if not line.strip():
            if current_event and current_data_lines:
                data_str = "\n".join(current_data_lines)
                try:
                    data = json.loads(data_str) if data_str else {}
                except json.JSONDecodeError:
                    data = {"raw": data_str}
                yield {"event": current_event, "data": data}
            current_event = ""
            current_data_lines = []


def format_sse_event(event: Dict[str, Any]) -> str:
    """
    Format an SSE event for terminal display.

    Returns a formatted string suitable for printing to stdout.
    """
    event_type = event.get("event", "unknown")
    data = event.get("data", {})

    if event_type == "connected":
        return f"\n✓ Connected to session {data.get('session_id', 'unknown')}\n"

    elif event_type == "workload_summary":
        pending = data.get("pending_intents", 0)
        active = data.get("active_topics", 0)
        return f"📊 Workload: {pending} pending intents, {active} active topics\n"

    elif event_type == "topic_cards":
        cards = data.get("cards", [])
        if cards:
            card_lines = ["\n📌 Active Topics:"]
            for card in cards:
                label = card.get("label", "unknown")
                staleness = card.get("staleness_hours", 0)
                if staleness < 1:
                    staleness_str = "🟢 fresh"
                elif staleness < 24:
                    staleness_str = f"🟡 {int(staleness)}h old"
                else:
                    staleness_str = f"🔴 {int(staleness)}h old"
                card_lines.append(f"  • {label} ({staleness_str})")
            return "\n".join(card_lines) + "\n"

    elif event_type == "result_created":
        summary = data.get("summary", "")
        urgency = data.get("urgency", "normal")
        urgency_symbols = {
            "critical": "🔴",
            "high": "🟠",
            "normal": "🟢",
            "low": "⚪",
        }
        symbol = urgency_symbols.get(urgency, "⚪")
        return f"\n{symbol} {summary}\n"

    elif event_type == "intent_status":
        intent_id = data.get("intent_id", "unknown")[:8]
        status = data.get("status", "unknown")
        return f"🔄 Intent {intent_id}: {status}\n"

    elif event_type == "error":
        error_msg = data.get("error", "Unknown error")
        return f"\n❌ Error: {error_msg}\n"

    return f"📡 {event_type}: {json.dumps(data, indent=2)}\n"
