#!/usr/bin/env python3
"""
Demo script for the confirmed deletions storage system.

This demonstrates documenting and retrieving confirmed pod deletions.
Run this to verify the system is working correctly.
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from src.confirmations.confirmed_deletions import (
    document_confirmed_deletion,
    get_latest_confirmed_deletion,
    get_confirmed_deletion_by_confirmation_id,
    list_all_confirmed_deletions,
    get_deletion_count
)


async def main():
    print("=== Confirmed Deletions Storage Demo ===\n")

    # Sample data representing a validated confirmation
    sample_confirmation = {
        "pod_name": "pbx-web-5ff68464d-mkn8n",
        "namespace": "default",
        "cluster": "iad-ci",
        "user_response": "yes",
        "confirmation_id": "demo-conf-001",
        "intent_id": "intent-demo-123",
        "session_id": "session-demo-456"
    }

    print("1. Documenting a confirmed deletion...")
    print(f"   Pod: {sample_confirmation['pod_name']}")
    print(f"   User Response: {sample_confirmation['user_response']}")
    print(f"   Confirmation ID: {sample_confirmation['confirmation_id']}\n")

    try:
        record = document_confirmed_deletion(**sample_confirmation)
        print(f"   ✅ Successfully documented deletion")
        print(f"   Timestamp: {record['timestamp']}")
        print(f"   Status: {record['status']}\n")
    except Exception as e:
        print(f"   ❌ Error documenting deletion: {e}\n")
        return

    print("2. Retrieving the latest confirmed deletion...")
    latest = get_latest_confirmed_deletion()
    if latest:
        print(f"   ✅ Found latest confirmed deletion:")
        print(f"   Pod: {latest['pod_name']}")
        print(f"   Namespace: {latest['namespace']}")
        print(f"   Cluster: {latest['cluster']}")
        print(f"   User Response: {latest['user_response']}")
        print(f"   Timestamp: {latest['timestamp']}\n")
    else:
        print("   ❌ No confirmed deletions found\n")

    print("3. Retrieving by confirmation ID...")
    by_id = get_confirmed_deletion_by_confirmation_id(sample_confirmation['confirmation_id'])
    if by_id:
        print(f"   ✅ Found deletion by ID:")
        print(f"   Confirmation ID: {by_id['confirmation_id']}")
        print(f"   Pod: {by_id['pod_name']}")
        print(f"   Status: {by_id['status']}\n")
    else:
        print("   ❌ Deletion not found by ID\n")

    print("4. Listing all confirmed deletions (last 5)...")
    all_deletions = list_all_confirmed_deletions(limit=5)
    print(f"   Found {len(all_deletions)} confirmed deletion(s):")
    for i, deletion in enumerate(all_deletions, 1):
        print(f"   {i}. {deletion['timestamp']} - {deletion['pod_name']} ({deletion['status']})\n")

    print("5. Getting deletion statistics...")
    stats = get_deletion_count()
    print(f"   Total Confirmed: {stats['total_confirmed']}")
    print(f"   Total Rejected: {stats['total_rejected']}")
    print(f"   Total Records: {stats['total_records']}\n")

    print("6. Verifying persistent storage...")
    log_file = Path("data/confirmed-deletions/confirmed-pods.jsonl")
    if log_file.exists():
        print(f"   ✅ Log file exists: {log_file}")
        with open(log_file, "r") as f:
            lines = f.readlines()
        print(f"   Total lines in log: {len(lines)}")
        if lines:
            print(f"   Last entry: {lines[-1].strip()}\n")
    else:
        print(f"   ❌ Log file not found: {log_file}\n")

    print("=== Demo Complete ===")
    print("\nThe confirmed deletions storage system is ready for use.")
    print("The deletion execution step can now:")
    print("  • Call get_latest_confirmed_deletion() to retrieve pod details")
    print("  • Use the pod_name, namespace, and cluster for execution")
    print("  • Access the confirmation_id for audit trail")


if __name__ == "__main__":
    asyncio.run(main())
