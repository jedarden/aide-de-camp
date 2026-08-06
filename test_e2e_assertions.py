#!/usr/bin/env python3
"""
Store-level assertions for E2E test verification.

Verifies the backend state after the E2E test passes:
1. SSE result event carries non-empty `summary` and `data` fields
2. Intent row reaches status `resolved` in session store (data/session.db, intents table)
3. A result row exists (results table)

Usage: python3 test_e2e_assertions.py <session_id> <intent_id> <topic_id> <sse_result_data>
"""

import sys
import json
import aiosqlite
from pathlib import Path
from typing import Optional


DEFAULT_DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")


async def verify_sse_event_structure(sse_result_data: dict) -> tuple[bool, str]:
    """
    Verify SSE event payload structure.

    Checks that the result_created event contains:
    - Non-empty `summary` field
    - Non-empty `data` field
    - Required `intent_id` and `topic_id` fields

    Args:
        sse_result_data: The data dictionary from the SSE result_created event

    Returns:
        (success: bool, message: str)
    """
    # Check required fields
    required_fields = ["intent_id", "topic_id"]
    for field in required_fields:
        if field not in sse_result_data:
            return False, f"Missing required field: {field}"

    # Check for summary field (should be present in result)
    if "summary" not in sse_result_data:
        return False, "Missing 'summary' field in SSE result data"

    summary = sse_result_data.get("summary", "")
    if not summary or not isinstance(summary, str) or summary.strip() == "":
        return False, f"Summary field is empty or invalid: {repr(summary)}"

    # Check for data field (should be present and contain result data)
    if "data" not in sse_result_data:
        return False, "Missing 'data' field in SSE result data"

    data = sse_result_data.get("data")
    if data is None or not isinstance(data, dict) or len(data) == 0:
        return False, f"Data field is empty or invalid: {repr(data)}"

    return True, f"✓ SSE event structure valid (summary={len(summary)} chars, data={len(data)} fields)"


async def verify_intent_status(
    db_path: Path,
    intent_id: str,
    expected_status: str = "resolved"
) -> tuple[bool, str]:
    """
    Verify intent row reaches expected status in session store.

    Queries the intents table to verify:
    - Intent row exists
    - Status is `resolved` (or expected_status)

    Args:
        db_path: Path to SQLite database
        intent_id: Intent ID to verify
        expected_status: Expected status value (default: "resolved")

    Returns:
        (success: bool, message: str)
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, status, resolved_at FROM intents WHERE id = ?",
                (intent_id,)
            ) as cursor:
                row = await cursor.fetchone()

                if not row:
                    return False, f"Intent row not found in database: {intent_id}"

                intent = dict(row)
                actual_status = intent.get("status")

                if actual_status != expected_status:
                    return False, (
                        f"Intent status mismatch: expected '{expected_status}', "
                        f"got '{actual_status}'"
                    )

                resolved_at = intent.get("resolved_at")
                if resolved_at is None:
                    return False, f"Intent has status 'resolved' but resolved_at is NULL"

                return True, f"✓ Intent status is 'resolved' (resolved_at={resolved_at})"

    except Exception as e:
        return False, f"Database error verifying intent status: {e}"


async def verify_result_exists(
    db_path: Path,
    intent_id: str,
    topic_id: str
) -> tuple[bool, str]:
    """
    Verify a result row exists in the session store.

    Queries the results table to verify:
    - Result row exists for the given intent_id and/or topic_id
    - Result has non-empty summary and data fields

    Args:
        db_path: Path to SQLite database
        intent_id: Intent ID to look up result for
        topic_id: Topic ID to look up result for

    Returns:
        (success: bool, message: str)
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # Look for result by intent_id and topic_id
            async with db.execute(
                """SELECT id, summary, data, created_at
                   FROM results
                   WHERE intent_id = ? AND topic_id = ?
                   LIMIT 1""",
                (intent_id, topic_id)
            ) as cursor:
                row = await cursor.fetchone()

                if not row:
                    return False, (
                        f"Result row not found in database for intent_id={intent_id}, "
                        f"topic_id={topic_id}"
                    )

                result = dict(row)

                # Verify summary field
                summary = result.get("summary", "")
                if not summary or not isinstance(summary, str) or summary.strip() == "":
                    return False, f"Result summary field is empty or invalid"

                # Verify data field (stored as JSON string)
                data_json = result.get("data", "")
                if not data_json or not isinstance(data_json, str):
                    return False, f"Result data field is missing or invalid type"

                try:
                    data = json.loads(data_json)
                    if not isinstance(data, dict) or len(data) == 0:
                        return False, f"Result data is empty or not a dict"
                except json.JSONDecodeError as e:
                    return False, f"Result data is not valid JSON: {e}"

                created_at = result.get("created_at")
                return True, (
                    f"✓ Result row exists (id={result['id']}, "
                    f"summary={len(summary)} chars, data={len(data)} fields, "
                    f"created_at={created_at})"
                )

    except Exception as e:
        return False, f"Database error verifying result exists: {e}"


async def run_all_assertions(
    session_id: str,
    intent_id: str,
    topic_id: str,
    sse_result_data: dict,
    db_path: Path = DEFAULT_DB_PATH
) -> tuple[bool, list[str]]:
    """
    Run all store-level assertions.

    Args:
        session_id: Session ID (for logging/context)
        intent_id: Intent ID from the test
        topic_id: Topic ID from the test
        sse_result_data: The SSE result event data dict
        db_path: Path to SQLite database

    Returns:
        (all_passed: bool, messages: list[str])
    """
    messages = []
    all_passed = True

    print("=" * 60)
    print(f"Running store-level assertions for session {session_id}")
    print("=" * 60)

    # 1. Verify SSE event structure
    print("\n1. Verifying SSE event structure...")
    success, msg = await verify_sse_event_structure(sse_result_data)
    messages.append(f"  {'✓' if success else '✗'} SSE structure: {msg}")
    if not success:
        all_passed = False
    print(f"   {msg}")

    # 2. Verify intent status
    print(f"\n2. Verifying intent status (intent_id={intent_id})...")
    success, msg = await verify_intent_status(db_path, intent_id, "resolved")
    messages.append(f"  {'✓' if success else '✗'} Intent status: {msg}")
    if not success:
        all_passed = False
    print(f"   {msg}")

    # 3. Verify result exists
    print(f"\n3. Verifying result row exists (topic_id={topic_id})...")
    success, msg = await verify_result_exists(db_path, intent_id, topic_id)
    messages.append(f"  {'✓' if success else '✗'} Result exists: {msg}")
    if not success:
        all_passed = False
    print(f"   {msg}")

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL STORE ASSERTIONS PASSED")
    else:
        print("✗ SOME STORE ASSERTIONS FAILED")
    print("=" * 60)

    return all_passed, messages


async def main():
    if len(sys.argv) < 5:
        print(
            "Usage: python3 test_e2e_assertions.py <session_id> <intent_id> <topic_id> <sse_result_data_json>",
            file=sys.stderr
        )
        print(
            "\nExample: python3 test_e2e_assertions.py abc123 def456 ghi789 '{\"intent_id\":\"def\",\"topic_id\":\"ghi\",\"summary\":\"test\",\"data\":{}}'",
            file=sys.stderr
        )
        sys.exit(1)

    session_id = sys.argv[1]
    intent_id = sys.argv[2]
    topic_id = sys.argv[3]
    sse_result_data_json = sys.argv[4]

    try:
        sse_result_data = json.loads(sse_result_data_json)
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON for sse_result_data: {e}", file=sys.stderr)
        sys.exit(1)

    # Check for custom DB path
    import os
    db_path = Path(os.environ.get("ADC_DB_PATH", DEFAULT_DB_PATH))

    try:
        success, messages = await run_all_assertions(
            session_id=session_id,
            intent_id=intent_id,
            topic_id=topic_id,
            sse_result_data=sse_result_data,
            db_path=db_path
        )

        # Print summary
        print("\nAssertion Summary:")
        for msg in messages:
            print(msg)

        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"✗ Assertions failed with error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
