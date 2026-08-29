#!/usr/bin/env python3
"""
Provision Telegram bot credentials for aide-de-camp.

This script checks the current state of Telegram bot credentials in OpenBao
and guides you through the provisioning process if they're missing.

Security: Credentials are piped directly to OpenBao and never appear in logs.
"""

import os
import sys
import getpass
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.openbao import OpenBaoClient


def check_openbao_connection() -> bool:
    """Check if OpenBao is accessible using the configured endpoint."""
    try:
        # The OpenBao client uses traefik-ardenone-cluster:8200 by default
        # and reads OPENBAO_TOKEN from environment
        client = OpenBaoClient()

        # Try to check if a test path exists (will fail auth but prove connectivity)
        # We can't do real auth checks without a token, but we can test the URL
        import hvac
        test_client = hvac.Client(
            url=client.url,
            verify=False,
        )
        # Just try to connect - will fail if unreachable
        test_client.secrets.kv.v2.read_secret_version(path="nonexistent-test-path")
        return True
    except hvac.exceptions.InvalidPath:
        # Path doesn't exist, but we connected successfully
        return True
    except hvac.exceptions.Forbidden:
        # Auth failed, but we connected
        return True
    except Exception as e:
        print(f"❌ Cannot connect to OpenBao at {client.url}: {e}")
        return False


def check_bot_token(client: OpenBaoClient) -> bool:
    """Check if the bot token exists in OpenBao."""
    exists = client.check_secret_exists("secret/ardenone-cluster/aide-de-camp/telegram_bot_token")
    return exists


def provision_bot_token(client: OpenBaoClient) -> bool:
    """Guide user through provisioning the bot token."""
    print("\n📝 Bot Token Provisioning")
    print("=" * 40)
    print("\nTo create a Telegram bot:")
    print("1. Open Telegram and search for @BotFather")
    print("2. Send /newbot")
    print("3. Follow the prompts to create your bot")
    print("4. Copy the bot token (format: 1234567890:ABCDEF...)")

    bot_token = getpass.getpass("\n🔑 Paste your bot token (will not echo to screen): ")

    if not bot_token:
        print("❌ No token provided")
        return False

    # Store using hvac directly (bypasses the OpenBaoClient to use put API)
    import hvac

    try:
        hvac_client = hvac.Client(
            url=client.url,
            token=client.token,
            verify=False,
        )

        # Store the secret - token goes in the body, never in logs
        hvac_client.secrets.kv.v2.create_or_update_secret(
            path="ardenone-cluster/aide-de-camp/telegram_bot_token",
            secret={"token": bot_token},
        )

        print("✅ Bot token stored successfully in OpenBao")
        print(f"   Path: secret/ardenone-cluster/aide-de-camp/telegram_bot_token")

        # Verify without reading the value
        if check_bot_token(client):
            print("✅ Storage verified")
            return True
        else:
            print("❌ Storage verification failed")
            return False

    except Exception as e:
        print(f"❌ Failed to store bot token: {e}")
        return False


def test_bot_token(client: OpenBaoClient) -> bool:
    """Test if the bot token works with the Telegram API."""
    try:
        token = client.get_secret("secret/ardenone-cluster/aide-de-camp/telegram_bot_token", field="token")
        if not token:
            print("❌ Bot token not found in OpenBao")
            return False

        # Test the token via Telegram API
        import httpx
        response = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10.0)

        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                bot_info = data.get("result", {})
                print(f"✅ Bot token is valid")
                print(f"   Bot: @{bot_info.get('username')} ({bot_info.get('first_name')})")
                return True
            else:
                print(f"❌ Bot token invalid: {data.get('description', 'Unknown error')}")
                return False
        else:
            print(f"❌ Telegram API error: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Failed to test bot token: {e}")
        return False


def guide_chat_id_extraction(client: OpenBaoClient, bot_token: str) -> str:
    """Guide user through extracting and storing their chat ID."""
    print("\n📝 Chat ID Extraction")
    print("=" * 40)
    print("\nTo get your chat ID:")
    print("1. Find your bot in Telegram (search for @your_bot_username)")
    print("2. Send /start or any message to the bot")
    print("3. Your chat ID will appear in the bot's updates")

    try:
        import httpx

        # Check for recent updates
        response = httpx.get(
            f"https://api.telegram.org/bot{bot_token}/getUpdates",
            params={"limit": 10},
            timeout=10.0,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                updates = data.get("result", [])

                if not updates:
                    print("\n⚠️  No updates found.")
                    print("Please send a message to your bot first, then run this check again.")
                    return None

                # Extract chat ID from the most recent message
                latest_update = updates[-1]
                message = latest_update.get("message", {})
                chat = message.get("chat", {})

                if chat:
                    chat_id = chat.get("id")
                    print(f"\n✅ Found chat ID: {chat_id}")
                    print(f"   Chat type: {chat.get('type')}")
                    if "first_name" in chat:
                        print(f"   Name: {chat.get('first_name')}")
                    if "username" in chat:
                        print(f"   Username: @{chat.get('username')}")

                    return str(chat_id)
                else:
                    print("❌ No chat information found in updates")
                    return None
            else:
                print(f"❌ Telegram API error: {data.get('description', 'Unknown error')}")
                return None
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Failed to fetch updates: {e}")
        return None


def store_chat_id(client: OpenBaoClient, chat_id: str) -> bool:
    """Store the chat ID in OpenBao."""
    try:
        import hvac

        hvac_client = hvac.Client(
            url=client.url,
            token=client.token,
            verify=False,
        )

        # Store the chat ID
        hvac_client.secrets.kv.v2.create_or_update_secret(
            path="ardenone-cluster/aide-de-camp/telegram_chat_id",
            secret={"chat_id": chat_id},
        )

        print(f"✅ Chat ID stored in OpenBao")
        print(f"   Path: secret/ardenone-cluster/aide-de-camp/telegram_chat_id")

        # Verify storage
        stored = client.get_secret("secret/ardenone-cluster/aide-de-camp/telegram_chat_id", field="chat_id")
        if stored == chat_id:
            print("✅ Chat ID verification successful")
            return True
        else:
            print("❌ Chat ID verification failed")
            return False

    except Exception as e:
        print(f"❌ Failed to store chat ID: {e}")
        return False


def print_next_steps(chat_id: str):
    """Print next steps for configuration."""
    print("\n🎉 Provisioning Complete!")
    print("=" * 40)
    print("\nYour Telegram credentials are now stored in OpenBao.")
    print("\nNext steps:")
    print("\n1. Update your systemd service environment:")
    print(f"   Edit ~/.config/systemd/user/aide-de-camp.service")
    print(f"   Uncomment and set:")
    print(f"   Environment=ADC_TELEGRAM_CHAT_ID={chat_id}")
    print("\n2. Reload and restart the service:")
    print("   systemctl --user daemon-reload")
    print("   systemctl --user restart aide-de-camp")
    print("\n3. Verify the integration:")
    print("   curl -s http://localhost:8000/api/v1/status/telegram | jq .")
    print("\n4. Test by triggering an exception-class result with no canvas active.")


def main():
    """Main provisioning workflow."""
    print("🤖 aide-de-camp Telegram Bot Credentials Provisioning")
    print("=" * 60)

    # Check OpenBao connection
    print("\n📡 Checking OpenBao connectivity...")
    if not check_openbao_connection():
        print("\n❌ Cannot connect to OpenBao. Please check your configuration.")
        print("   Required: OPENBAO_URL and OPENBAO_TOKEN environment variables")
        sys.exit(1)

    print("✅ OpenBao connection successful")

    # Initialize OpenBao client
    client = OpenBaoClient()

    # Check current state
    print("\n🔍 Checking current credential state...")

    bot_token_exists = check_bot_token(client)
    if bot_token_exists:
        print("✅ Bot token exists in OpenBao")
        token_valid = test_bot_token(client)
    else:
        print("❌ Bot token not found in OpenBao")
        token_valid = False

    # Provision bot token if needed
    if not bot_token_exists or not token_valid:
        print("\n⚠️  Bot token provisioning required")
        if not provision_bot_token(client):
            sys.exit(1)

    # Get bot token for chat ID extraction
    bot_token = client.get_secret("secret/ardenone-cluster/aide-de-camp/telegram_bot_token", field="token")
    if not bot_token:
        print("❌ Failed to retrieve bot token for chat ID extraction")
        sys.exit(1)

    # Extract and store chat ID
    print("\n🔍 Checking chat ID...")
    chat_id = client.get_secret("secret/ardenone-cluster/aide-de-camp/telegram_chat_id", field="chat_id")

    if chat_id:
        print(f"✅ Chat ID already configured: {chat_id}")
    else:
        print("❌ Chat ID not found in OpenBao")
        chat_id = guide_chat_id_extraction(client, bot_token)

        if chat_id:
            if not store_chat_id(client, chat_id):
                print("\n⚠️  Chat ID extraction succeeded but storage failed")
                print("   You can manually set ADC_TELEGRAM_CHAT_ID in the service file")
        else:
            print("\n⚠️  Could not extract chat ID automatically")
            print("   To manually get your chat ID:")
            print("   1. Send a message to your bot")
            print("   2. Visit: https://api.telegram.org/bot<BOT_TOKEN>/getUpdates")
            print("   3. Find your chat_id in the response")

    # Print next steps
    if chat_id:
        print_next_steps(chat_id)
    else:
        print("\n⚠️  Partial provisioning: Bot token configured, but chat ID is missing")
        print("   The bot will start but will not send messages until chat ID is set")


if __name__ == "__main__":
    main()
