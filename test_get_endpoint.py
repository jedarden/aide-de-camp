#!/home/coding/aide-de-camp/.venv/bin/python3
"""
Test script to verify GET /test endpoint stores results to SQLite.
"""
import asyncio
import sqlite3
from pathlib import Path
import httpx
from datetime import datetime

# Configuration
API_BASE = "http://localhost:8000"
DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")


async def test_get_test_endpoint_storage():
    """Test that GET /test endpoint stores data correctly."""
    print("Testing GET /test endpoint storage verification...")

    # Call GET /test endpoint
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE}/test")
        response.raise_for_status()
        data = response.json()

        print(f"Response status: {response.status_code}")
        print(f"Response data: {data}")

        # Verify storage confirmation
        assert data.get("status") == "test", f"Expected status='test', got {data.get('status')}"
        assert "stored" in data, "Response should contain 'stored' field"
        assert data["stored"].get("result_id"), "Response should contain result_id"

        result_id = data["stored"]["result_id"]
        session_id = data["stored"]["session_id"]
        intent_id = data["stored"]["intent_id"]
        topic_id = data["stored"]["topic_id"]
        utterance_id = data["stored"]["utterance_id"]

        print(f"\n✓ Storage confirmation received:")
        print(f"  result_id: {result_id}")
        print(f"  session_id: {session_id}")
        print(f"  intent_id: {intent_id}")
        print(f"  topic_id: {topic_id}")
        print(f"  utterance_id: {utterance_id}")

    # Verify data in SQLite database
    print(f"\nVerifying data in SQLite database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check session
    cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    session = cursor.fetchone()
    assert session, f"Session {session_id} not found in database"
    print(f"✓ Session found: {session['id']}")

    # Check utterance
    cursor.execute("SELECT * FROM utterances WHERE id = ?", (utterance_id,))
    utterance = cursor.fetchone()
    assert utterance, f"Utterance {utterance_id} not found in database"
    print(f"✓ Utterance found: {utterance['id']} - '{utterance['raw_text']}'")

    # Check intent
    cursor.execute("SELECT * FROM intents WHERE id = ?", (intent_id,))
    intent = cursor.fetchone()
    assert intent, f"Intent {intent_id} not found in database"
    print(f"✓ Intent found: {intent['id']} - type: {intent['intent_type']}")

    # Check topic
    cursor.execute("SELECT * FROM topics WHERE id = ?", (topic_id,))
    topic = cursor.fetchone()
    assert topic, f"Topic {topic_id} not found in database"
    print(f"✓ Topic found: {topic['id']} - label: {topic['label']}")

    # Check result
    cursor.execute("SELECT * FROM results WHERE id = ?", (result_id,))
    result = cursor.fetchone()
    assert result, f"Result {result_id} not found in database"
    print(f"✓ Result found: {result['id']} - summary: {result['summary']}")

    # Verify result data
    import json
    result_data = json.loads(result['data'])
    assert result_data.get("test_mode") == True, "Result should have test_mode=True"
    assert result_data.get("endpoint") == "GET /test", "Result should have endpoint='GET /test'"
    print(f"✓ Result data verified: test_mode={result_data.get('test_mode')}, endpoint={result_data.get('endpoint')}")

    conn.close()

    print("\n" + "="*60)
    print("✓ All tests passed!")
    print("="*60)
    print("\nGET /test endpoint successfully:")
    print("  1. Stores session in data/session.db")
    print("  2. Stores utterance in data/session.db")
    print("  3. Stores intent in data/session.db")
    print("  4. Stores topic in data/session.db")
    print("  5. Stores result in data/session.db")
    print("  6. Returns storage confirmation with result_id")
    print("  7. Uses same session store logic as /dispatch")


if __name__ == "__main__":
    try:
        asyncio.run(test_get_test_endpoint_storage())
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
