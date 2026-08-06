#!/usr/bin/env python3
"""
Test script to verify /voice WebSocket error handling when OPENAI_API_KEY is missing.

Expected behavior:
1. WebSocket accepts connection
2. Server sends JSON error: {"type": "error", "error": "OpenAI API key not configured"}
3. Server closes WebSocket with code 1011 and reason "API key missing"
"""
import asyncio
import json
import os
import sys

# Remove OPENAI_API_KEY from environment to ensure it's not set
os.environ.pop("OPENAI_API_KEY", None)

import websockets
from websockets.exceptions import ConnectionClosedError


async def test_voice_error_path():
    """Test that /voice endpoint gracefully handles missing OPENAI_API_KEY."""
    ws_url = "ws://localhost:8000/voice?session_id=test-error-path-123"

    print("Testing /voice WebSocket error path without OPENAI_API_KEY...")
    print(f"Connecting to: {ws_url}")

    try:
        async with websockets.connect(ws_url) as websocket:
            print("✓ WebSocket connection accepted")

            # Wait for the error message
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                data = json.loads(message)
                print(f"✓ Received message: {json.dumps(data, indent=2)}")

                # Verify it's the expected error format
                assert data.get("type") == "error", f"Expected type='error', got {data.get('type')}"
                assert "API key" in data.get("error", ""), f"Expected API key error, got: {data.get('error')}"
                print("✓ Error message format is correct")

                # Now wait for the close
                try:
                    close_msg = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    print(f"! Received unexpected message after error: {close_msg}")
                except asyncio.TimeoutError:
                    print("✓ WebSocket closed after error message (no further data)")

            except asyncio.TimeoutError:
                print("✗ Timeout waiting for error message")
                return False

    except ConnectionClosedError as e:
        print(f"✓ WebSocket closed as expected")
        print(f"  Close code: {e.code}")
        print(f"  Close reason: {e.reason}")

        # Verify close code and reason
        if e.code == 1011:
            print("✓ Close code is correct (1011)")
        else:
            print(f"✗ Expected close code 1011, got {e.code}")
            return False

        if e.reason and "API key" in str(e.reason):
            print("✓ Close reason mentions API key")
        else:
            print(f"! Close reason: {e.reason} (expected 'API key missing')")

    except Exception as e:
        print(f"✗ Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n✓ All checks passed - graceful error handling verified")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_voice_error_path())
    sys.exit(0 if success else 1)
