#!/usr/bin/env python3
"""
Demo script showing how to use canvas test data injection utilities.

This script demonstrates:
1. Creating test sessions
2. Injecting test utterances
3. Creating synthetic results
4. Retrieving topics
5. Cleaning up test data
"""
import asyncio
from src.test.utilities import (
    TestSessionClient,
    TestDataBuilder,
    TestFixture,
)


async def demo_basic_usage():
    """Demonstrate basic usage of the test utilities."""
    print("\n=== Demo: Basic Usage ===\n")

    async with TestSessionClient() as client:
        # Create a test session
        session = await client.create_session()
        print(f"Created session: {session['session_id']}")
        print(f"Created surface: {session['surface_id']}")

        # Dispatch a test utterance
        response = await client.dispatch_utterance(
            utterance="check the system status",
            session_id=session["session_id"],
            surface_id=session["surface_id"],
        )
        print(f"Dispatched utterance: {response['utterance_id']}")
        print(f"Intent count: {response['intent_count']}")

        # Get topics
        topics = await client.get_session_topics(session["session_id"])
        print(f"Topics count: {len(topics['cards'])}")

        # Cleanup happens automatically when exiting context


async def demo_synthetic_results():
    """Demonstrate creating synthetic test results."""
    print("\n=== Demo: Synthetic Results ===\n")

    async with TestSessionClient() as client:
        session = await client.create_session()

        # Create a synthetic result
        result = await client.create_synthetic_result(
            session_id=session["session_id"],
            surface_id=session["surface_id"],
        )
        print(f"Created synthetic result: {result['result_id']}")
        print(f"Result status: {result['status']}")
        print(f"Topic: {result['topic_id']}")


async def demo_custom_test_data():
    """Demonstrate creating custom test data."""
    print("\n=== Demo: Custom Test Data ===\n")

    # Build custom test data
    test_data = TestDataBuilder.build_synthetic_data(
        utterance="check the pipeline health",
        project_slug="test-pipeline",
        intent_type="status",
        topic_label="Pipeline Health Check",
        topic_type="project",
        summary="Pipeline is running normally",
        urgency="normal",
        result_type="status",
    )
    print(f"Built test data: {test_data['topic_label']}")

    async with TestSessionClient() as client:
        session = await client.create_session()

        result = await client.create_synthetic_result(
            session_id=session["session_id"],
            test_data=test_data,
        )
        print(f"Created custom result: {result['summary']}")


async def demo_multi_topic_injection():
    """Demonstrate injecting multiple topics into a session."""
    print("\n=== Demo: Multi-Topic Injection ===\n")

    async with TestFixture() as fixture:
        print(f"Test session: {fixture.session_id}")
        print(f"Test surface: {fixture.surface_id}")

        # Create multiple topics
        topics_to_create = [
            {"topic_label": "System Status", "summary": "System is healthy"},
            {"topic_label": "Recent Logs", "summary": "No errors found"},
            {"topic_label": "Pipeline Health", "summary": "Pipeline running"},
        ]

        for topic_spec in topics_to_create:
            await fixture.create_synthetic(topic_spec)
            print(f"Created topic: {topic_spec['topic_label']}")

        # Get all topics
        topics = await fixture.get_topics()
        print(f"\nTotal topics in session: {len(topics['cards'])}")

        # Display topics
        for card in topics['cards']:
            print(f"  - {card.get('label', 'Unknown')}: {card.get('summary', 'No summary')}")


async def demo_test_data_builder():
    """Demonstrate the TestDataBuilder utility."""
    print("\n=== Demo: Test Data Builder ===\n")

    # Build different types of test data
    status_data = TestDataBuilder.build_synthetic_data(
        utterance="check status",
        intent_type="status",
        topic_label="Status Check",
    )
    print(f"Status data: {status_data['intent_type']}")

    # Build multi-intent scenario
    scenarios = TestDataBuilder.build_multi_intent_scenario()
    print(f"Multi-intent scenarios: {len(scenarios)}")
    for scenario in scenarios:
        print(f"  - {scenario['name']}: {scenario['expected_intent_count']} intents")


async def demo_database_isolation():
    """Demonstrate database isolation utilities."""
    print("\n=== Demo: Database Isolation ===\n")

    from src.test.utilities import TestDatabaseIsolation

    # Create a temporary database path
    temp_path = TestDatabaseIsolation.create_temp_db_path()
    print(f"Temp DB path: {temp_path}")

    # Get in-memory connection string
    conn_str = TestDatabaseIsolation.create_in_memory_db_connection_string()
    print(f"In-memory DB: {conn_str}")

    # Clean up
    import shutil
    if temp_path.parent.exists():
        shutil.rmtree(temp_path.parent, ignore_errors=True)
        print("Cleaned up temp directory")


async def main():
    """Run all demos."""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   Canvas Test Data Injection Utilities Demo                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    try:
        await demo_basic_usage()
        await demo_synthetic_results()
        await demo_custom_test_data()
        await demo_multi_topic_injection()
        await demo_test_data_builder()
        await demo_database_isolation()

        print("\n✅ All demos completed successfully!")
        print("\nNote: This demo assumes the ADC server is running on")
        print("      http://localhost:8000. Start the server first with:")
        print("      .venv/bin/python -m src.main")

    except Exception as e:
        print(f"\n❌ Error running demo: {e}")
        print("\nMake sure the ADC server is running:")
        print("  .venv/bin/python -m src.main")


if __name__ == "__main__":
    asyncio.run(main())
