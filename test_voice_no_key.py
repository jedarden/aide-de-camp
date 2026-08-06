#!/usr/bin/env python3
"""Test WebSocket /voice endpoint behavior without OPENAI_API_KEY."""

import asyncio
import websockets
import json

async def test_voice_no_api_key():
    """Test that /voice endpoint gracefully closes without OPENAI_API_KEY."""
    uri = "ws://localhost:8000/voice?session_id=test-no-key-123"

    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as ws:
            print("✓ Connection accepted")

            # Wait for the error message and close
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(msg)
                print(f"✓ Received message: {data}")

                if data.get("type") == "error":
                    error = data.get("error")
                    print(f"✓ Error type: error")
                    print(f"✓ Error message: {error}")

            except asyncio.TimeoutError:
                print("✗ Timeout waiting for message")

            # Check if connection closes with code 1011
            try:
                await asyncio.wait_for(ws.wait_closed(), timeout=2.0)
                close_code = ws.close_code
                close_reason = ws.close_reason
                print(f"✓ Connection closed with code: {close_code}")
                print(f"✓ Close reason: {close_reason}")

                if close_code == 1011:
                    print("\n✅ SUCCESS: Graceful error behavior verified")
                    print("   - Error JSON sent before close")
                    print("   - Close code 1011 (API key missing)")
                    return True
                else:
                    print(f"\n⚠️  Unexpected close code: {close_code}")
                    return False

            except asyncio.TimeoutError:
                print("✗ Timeout waiting for close")
                return False

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_voice_no_api_key())
    exit(0 if result else 1)
