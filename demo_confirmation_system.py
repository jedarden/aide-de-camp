#!/usr/bin/env .venv/bin/python3
"""
Demo script to test the confirmation prompt system.

This script demonstrates:
1. Creating a confirmation prompt
2. Displaying it to the user
3. Capturing user response
4. Getting confirmation for validation
"""

import asyncio
import sys
from src.confirmations.prompts import (
    get_confirmation_manager,
    create_pod_deletion_confirmation,
    display_confirmation_prompt,
    capture_confirmation_response,
    get_confirmation_for_validation,
)


async def demo_confirmation_flow():
    """Demonstrate the complete confirmation flow."""
    print("🧪 Confirmation Prompt System Demo")
    print("=" * 60)
    print()

    # Test data
    intent_id = "test-intent-123"
    session_id = "test-session-456"
    pod_name = "pbx-web-5ff68464d-mkn8n"
    namespace = "default"
    cluster = "iad-ci"

    try:
        # Step 1: Create confirmation prompt
        print("📋 Step 1: Creating confirmation prompt...")
        confirmation = await create_pod_deletion_confirmation(
            intent_id=intent_id,
            session_id=session_id,
            pod_name=pod_name,
            namespace=namespace,
            cluster=cluster,
        )

        print(f"✅ Confirmation created: {confirmation['confirmation_id']}")
        print(f"   Question: {confirmation['question']}")
        print()

        # Step 2: Display confirmation prompt
        print("📢 Step 2: Displaying confirmation prompt...")
        message = await display_confirmation_prompt(confirmation['confirmation_id'])
        print(message)
        print()

        # Step 3: Simulate user response (for demo purposes)
        print("👤 Step 3: Simulating user response...")
        print("(In real usage, this would come from API endpoint)")
        test_response = input("Enter your response (yes/no/pod-name): ").strip()

        # Step 4: Capture response
        print(f"\n💾 Step 4: Capturing response '{test_response}'...")
        result = await capture_confirmation_response(
            confirmation_id=confirmation['confirmation_id'],
            response=test_response,
        )

        print(f"✅ Response captured at: {result['responded_at']}")
        print()

        # Step 5: Get confirmation for validation
        print("🔍 Step 5: Getting confirmation for validation...")
        validation_data = await get_confirmation_for_validation(
            confirmation['confirmation_id']
        )

        print("✅ Validation data retrieved:")
        print(f"   Question: {validation_data['question']}")
        print(f"   Response: {validation_data['response']}")
        print(f"   Status: {validation_data['status']}")
        print(f"   Created: {validation_data['created_at']}")
        print(f"   Responded: {validation_data['responded_at']}")
        print()

        print("✅ Demo completed successfully!")
        print()
        print("📝 Summary:")
        print("   - Confirmation prompt created ✓")
        print("   - Question displayed to user ✓")
        print("   - User response captured ✓")
        print("   - Data ready for validation ✓")

        return True

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    try:
        success = asyncio.run(demo_confirmation_flow())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo cancelled by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()