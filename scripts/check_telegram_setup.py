#!/usr/bin/env python3
"""
Check current Telegram setup status in OpenBao.

This script uses the OpenBao Python client to check if credentials exist.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.openbao import OpenBaoClient


def main():
    print("🔍 Checking Telegram Bot Credentials Status")
    print("=" * 50)

    # Initialize client
    client = OpenBaoClient()

    print(f"\nOpenBao URL: {client.url}")
    print(f"OpenBao Token: {'✅ Set' if client.token else '❌ Not set'}")

    if not client.token:
        print("\n❌ OPENBAO_TOKEN environment variable not set")
        print("   Please run: export OPENBAO_TOKEN=<your-token>")
        sys.exit(1)

    # Check bot token
    print("\n📝 Bot Token:")
    print("   Path: secret/ardenone-cluster/aide-de-camp/telegram_bot_token")

    bot_token_exists = client.check_secret_exists("secret/ardenone-cluster/aide-de-camp/telegram_bot_token")
    if bot_token_exists:
        print("   Status: ✅ Exists")
        # Try to retrieve and validate
        try:
            import httpx
            token = client.get_secret("secret/ardenone-cluster/aide-de-camp/telegram_bot_token", field="token")
            if token:
                response = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        bot_info = data.get("result", {})
                        print(f"   Bot: @{bot_info.get('username')} ({bot_info.get('first_name')})")
                        print(f"   Valid: ✅ Yes")
                    else:
                        print(f"   Valid: ❌ No - {data.get('description')}")
                else:
                    print(f"   Valid: ❌ HTTP {response.status_code}")
            else:
                print("   Valid: ❌ Could not retrieve token")
        except Exception as e:
            print(f"   Valid: ❌ Error - {e}")
    else:
        print("   Status: ❌ Not found")

    # Check chat ID
    print("\n💬 Chat ID:")
    print("   Path: secret/ardenone-cluster/aide-de-camp/telegram_chat_id")

    chat_id_exists = client.check_secret_exists("secret/ardenone-cluster/aide-de-camp/telegram_chat_id")
    if chat_id_exists:
        chat_id = client.get_secret("secret/ardenone-cluster/aide-de-camp/telegram_chat_id", field="chat_id")
        print(f"   Status: ✅ Exists")
        print(f"   Chat ID: {chat_id}")
    else:
        print("   Status: ❌ Not found")

    # Summary
    print("\n" + "=" * 50)
    if bot_token_exists and chat_id_exists:
        print("✅ All credentials configured - ready to use")
        print("\nTo test: systemctl --user restart aide-de-camp")
        print("Then: curl -s http://localhost:8000/api/v1/status/telegram | jq .")
    elif bot_token_exists:
        print("⚠️  Bot token configured, but chat ID missing")
        print("\nTo add chat ID, send a message to your bot then run:")
        print("  python scripts/extract_and_store_chat_id.py")
    else:
        print("❌ Credentials not configured")
        print("\nTo provision, run:")
        print("  python scripts/provision_telegram_credentials.py")
        print("\nOr follow manual steps in:")
        print("  docs/notes/openbao-telegram-token-storage.md")


if __name__ == "__main__":
    main()
