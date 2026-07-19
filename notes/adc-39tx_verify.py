"""
Runtime verification — bead adc-39tx.

Goal: confirm the WARNING log fires only on the FIRST Telegram send failure,
not on subsequent ones, and that it carries error type + message.

This drives the real ``TelegramFallback.send_message`` HTTP code path (not the
``_handle_send_failure`` helper in isolation) against an unreachable bridge URL.
A closed local port gives a connection-refused error -> ``httpx.ConnectError``
(a ``RequestError``), which is the same branch real production traffic hits when
the bridge is down. We attach a capturing handler to the module logger and
assert the WARNING/DEBUG distribution across three consecutive failures.
"""

import asyncio
import logging

from src.telegram.fallback import TelegramFallback

CAPTURED: list[tuple[str, str, str]] = []  # (level, logger_name, message)


class CaptureHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        CAPTURED.append((record.levelname, record.name, record.getMessage()))


async def main() -> None:
    logger = logging.getLogger("src.telegram.fallback")
    logger.addHandler(CaptureHandler())
    logger.setLevel(logging.DEBUG)

    # Unreachable host: connection refused -> httpx.ConnectError (RequestError),
    # i.e. the `except httpx.RequestError as e` branch in send_message.
    fallback = TelegramFallback(bridge_url="http://127.0.0.1:1")

    returned: list[bool] = []
    for i in range(3):
        ok = await fallback.send_message(chat_id=123, message=f"probe {i}")
        returned.append(ok)

    warnings = [c for c in CAPTURED if c[0] == "WARNING"]
    debugs = [c for c in CAPTURED if c[0] == "DEBUG"]

    print("send_message returned:", returned)
    print(f"WARNING count: {len(warnings)}")
    print(f"DEBUG count:   {len(debugs)}")
    print("---- WARNING records ----")
    for level, name, msg in warnings:
        print(f"[{level}] {name}: {msg}")
    print("---- DEBUG records ----")
    for level, name, msg in debugs:
        print(f"[{level}] {name}: {msg}")
    print(f"failure_count (instance): {fallback._failure_count}")
    print(f"has_logged_first_failure: {fallback._has_logged_first_failure}")

    # ---- Assertions (the acceptance criteria) ----
    assert returned == [False, False, False], f"all three sends must fail: {returned}"
    assert len(warnings) == 1, f"expected exactly 1 WARNING, got {len(warnings)}"
    assert len(debugs) == 2, f"expected exactly 2 DEBUG, got {len(debugs)}"
    warn_msg = warnings[0][2]
    assert "First Telegram send failure detected" in warn_msg, warn_msg
    assert "ConnectError" in warn_msg, f"error type missing: {warn_msg}"  # error_type
    assert "Subsequent failures will be logged at DEBUG level only" in warn_msg, warn_msg
    assert "Repeated Telegram send failure" in debugs[0][2], debugs[0][2]
    assert fallback._failure_count == 3, fallback._failure_count

    print("\nVERIFICATION PASSED: exactly one WARNING on first failure; "
          "subsequent failures logged at DEBUG only.")


if __name__ == "__main__":
    asyncio.run(main())
