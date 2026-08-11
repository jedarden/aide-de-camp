"""
Confirmed Deletions Storage Module

This module handles documenting and storing confirmed pod deletions for use by
the deletion execution step. It provides persistent storage of confirmed deletions
with timestamps and user responses.

Usage:
    from src.confirmations.confirmed_deletions import document_confirmed_deletion, get_latest_confirmed_deletion

    # Document a confirmed deletion
    await document_confirmed_deletion(
        pod_name="pbx-web-5ff68464d-mkn8n",
        namespace="default",
        cluster="iad-ci",
        user_response="yes",
        confirmation_id="abc-123"
    )

    # Retrieve the latest confirmed deletion for execution
    deletion = get_latest_confirmed_deletion()
    if deletion:
        execute_pod_deletion(deletion['pod_name'], deletion['namespace'], deletion['cluster'])
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any
import logging

from ..utils.atomic_write import atomic_append

logger = logging.getLogger(__name__)

# Storage file path
CONFIRMED_DELETIONS_DIR = Path("data/confirmed-deletions")
CONFIRMED_DELETIONS_LOG = CONFIRMED_DELETIONS_DIR / "confirmed-pods.jsonl"


def document_confirmed_deletion(
    pod_name: str,
    namespace: str,
    cluster: str,
    user_response: str,
    confirmation_id: str,
    intent_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Document a confirmed pod deletion with timestamp and store for deletion step.

    Args:
        pod_name: Name of the pod confirmed for deletion
        namespace: Kubernetes namespace where the pod resides
        cluster: Cluster identifier (e.g., 'iad-ci')
        user_response: User's confirmation response ('yes', 'no', or exact pod name)
        confirmation_id: Unique identifier for the confirmation prompt
        intent_id: Optional associated intent ID
        session_id: Optional associated session ID

    Returns:
        Dict containing the documented deletion record with metadata

    Raises:
        IOError: If unable to write to the log file
        ValueError: If required parameters are missing
    """
    # Validate required parameters
    if not pod_name:
        raise ValueError("pod_name is required")
    if not user_response:
        raise ValueError("user_response is required")
    if not confirmation_id:
        raise ValueError("confirmation_id is required")

    # Create ISO 8601 timestamp
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build the deletion record
    deletion_record = {
        "timestamp": timestamp,
        "pod_name": pod_name,
        "namespace": namespace,
        "cluster": cluster,
        "user_response": user_response,
        "confirmation_id": confirmation_id,
        "intent_id": intent_id,
        "session_id": session_id,
        "status": "confirmed" if user_response.lower() == "yes" or user_response == pod_name else "rejected"
    }

    # Append to log file atomically (one JSON record per line)
    # Note: Uses atomic_append utility to prevent partial writes and corruption
    # The atomic_append ensures complete writes even during crashes or concurrent access
    try:
        atomic_append(
            CONFIRMED_DELETIONS_LOG,
            json.dumps(deletion_record) + "\n",
            mode='a'
        )
        logger.info(f"Documented confirmed deletion: pod={pod_name}, response={user_response}, timestamp={timestamp}")
    except (OSError, PermissionError) as e:
        # Handle atomic append failures with specific error types
        logger.error(f"Atomic append failed for confirmed deletion log {CONFIRMED_DELETIONS_LOG}: {type(e).__name__}: {e}")
        raise IOError(f"Failed to document confirmed deletion in log: {e}") from e
    except (TypeError, ValueError) as e:
        # Handle JSON serialization errors
        logger.error(f"JSON serialization failed for confirmed deletion record: {e}")
        raise ValueError(f"Invalid deletion record format: {e}") from e

    return deletion_record


def get_latest_confirmed_deletion() -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recent confirmed deletion record for execution.

    Returns:
        Dict containing the latest confirmed deletion record, or None if no confirmed deletions exist.
        Only returns records with status='confirmed' (user said 'yes' or exact pod name).
    """
    if not CONFIRMED_DELETIONS_LOG.exists():
        return None

    latest_record = None
    latest_timestamp = None

    try:
        with open(CONFIRMED_DELETIONS_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)

                    # Only return confirmed deletions (not rejected ones)
                    if record.get("status") != "confirmed":
                        continue

                    timestamp = record.get("timestamp")
                    if timestamp and (latest_timestamp is None or timestamp > latest_timestamp):
                        latest_timestamp = timestamp
                        latest_record = record
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed line in confirmed deletions log: {e}")
                    continue
    except IOError as e:
        logger.error(f"Failed to read confirmed deletions log: {e}")
        return None

    return latest_record


def get_confirmed_deletion_by_confirmation_id(confirmation_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific confirmed deletion record by confirmation ID.

    Args:
        confirmation_id: The unique identifier for the confirmation prompt

    Returns:
        Dict containing the confirmed deletion record, or None if not found
    """
    if not CONFIRMED_DELETIONS_LOG.exists():
        return None

    try:
        with open(CONFIRMED_DELETIONS_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                    if record.get("confirmation_id") == confirmation_id:
                        return record
                except json.JSONDecodeError:
                    continue
    except IOError as e:
        logger.error(f"Failed to read confirmed deletions log: {e}")

    return None


def list_all_confirmed_deletions(limit: Optional[int] = None) -> list[Dict[str, Any]]:
    """
    List all confirmed deletion records, optionally limited to the most recent N.

    Args:
        limit: Maximum number of records to return (most recent first). If None, returns all.

    Returns:
        List of confirmed deletion records, sorted by timestamp descending (newest first).
        Only includes records with status='confirmed'.
    """
    if not CONFIRMED_DELETIONS_LOG.exists():
        return []

    records = []

    try:
        with open(CONFIRMED_DELETIONS_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                    if record.get("status") == "confirmed":
                        records.append(record)
                except json.JSONDecodeError:
                    continue
    except IOError as e:
        logger.error(f"Failed to read confirmed deletions log: {e}")
        return []

    # Sort by timestamp descending (newest first)
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

    if limit is not None:
        records = records[:limit]

    return records


def get_deletion_count() -> Dict[str, int]:
    """
    Get statistics about confirmed deletions.

    Returns:
        Dict with counts: total_confirmed, total_rejected, total_records
    """
    confirmed = 0
    rejected = 0

    if not CONFIRMED_DELETIONS_LOG.exists():
        return {"total_confirmed": 0, "total_rejected": 0, "total_records": 0}

    try:
        with open(CONFIRMED_DELETIONS_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                    status = record.get("status", "")
                    if status == "confirmed":
                        confirmed += 1
                    elif status == "rejected":
                        rejected += 1
                except json.JSONDecodeError:
                    continue
    except IOError as e:
        logger.error(f"Failed to read confirmed deletions log: {e}")

    return {
        "total_confirmed": confirmed,
        "total_rejected": rejected,
        "total_records": confirmed + rejected
    }
