"""
Diff engine for comparing results.

Computes semantic diffs between previous and current results for a topic.
Used by synthesize strand to generate diff-aware results.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging import getLogger
from typing import Any, Optional


logger = getLogger(__name__)


@dataclass
class FieldDiff:
    """A diff for a single field."""
    field_name: str
    old_value: Any
    new_value: Any
    change_type: str  # 'added', 'removed', 'changed', 'unchanged'


@dataclass
class ResultDiff:
    """Diff between two results."""
    has_changes: bool
    fields: list[FieldDiff]
    summary: str
    change_summary: str  # Human-readable summary of what changed
    timestamp_old: Optional[int] = None
    timestamp_new: Optional[int] = None
    time_delta_seconds: Optional[int] = None


class DiffEngine:
    """
    Computes diffs between results.

    Handles semantic comparison for different data types:
    - Status results: compare phase, health, replicas, restarts
    - List results: compare counts, items added/removed
    - Scalar results: compare values
    """

    # Fields that are considered "significant" for each result type
    SIGNIFICANT_FIELDS = {
        "status": ["phase", "health", "ready", "sync_status", "restart_count", "age"],
        "pod_status": ["phase", "ready", "restarts", "age"],
        "argo_status": ["sync_status", "health_status", "revision"],
        "ci_status": ["phase", "message", "started_at", "finished_at"],
        "git_log": ["commit_count", "latest_commit", "latest_author"],
        "bead_list": ["open_count", "closed_count", "latest_bead_id"],
    }

    def __init__(self):
        self._cache: dict[str, tuple[dict, dict]] = {}  # topic_id -> (prev_result, timestamp)

    async def compute_diff(
        self,
        topic_id: str,
        previous_result: Optional[dict],
        current_result: dict,
    ) -> ResultDiff:
        """
        Compute diff between previous and current result for a topic.

        Args:
            topic_id: The topic ID
            previous_result: The previous result data (or None if first result)
            current_result: The current result data

        Returns:
            ResultDiff with field-level changes and summary
        """
        if previous_result is None:
            # First result - no previous state to compare
            return ResultDiff(
                has_changes=False,
                fields=[],
                summary="Initial result - no previous state to compare",
                change_summary="",
                timestamp_new=current_result.get("timestamp"),
            )

        # Extract timestamps
        timestamp_old = previous_result.get("created_at")
        timestamp_new = current_result.get("created_at")
        time_delta = None
        if timestamp_old and timestamp_new:
            time_delta = timestamp_new - timestamp_old

        # Get data from results
        prev_data = previous_result.get("data", {})
        curr_data = current_result.get("data", {})

        # Infer result type from data structure
        result_type = self._infer_result_type(curr_data)

        # Compute field-level diffs
        significant_fields = self.SIGNIFICANT_FIELDS.get(result_type, [])
        fields = self._compute_field_diffs(prev_data, curr_data, significant_fields)

        # Generate summary
        has_changes = any(f.change_type != "unchanged" for f in fields)
        change_summary = self._generate_change_summary(fields, result_type)

        # Overall summary
        summary = self._generate_summary(has_changes, change_summary, time_delta)

        return ResultDiff(
            has_changes=has_changes,
            fields=fields,
            summary=summary,
            change_summary=change_summary,
            timestamp_old=timestamp_old,
            timestamp_new=timestamp_new,
            time_delta_seconds=time_delta,
        )

    def _infer_result_type(self, data: dict) -> str:
        """Infer result type from data structure."""
        if "phase" in data and "ready" in data:
            if "restarts" in data:
                return "pod_status"
            return "status"
        if "sync_status" in data:
            return "argo_status"
        if "phase" in data and "message" in data:
            return "ci_status"
        if "commits" in data or "commit_count" in data:
            return "git_log"
        if "beads" in data or "open_count" in data:
            return "bead_list"
        # For generic results, check if data looks like a status result
        if "status" in data or "health" in data or "replicas" in data:
            return "generic_status"
        return "generic"

    def _compute_field_diffs(
        self,
        prev_data: dict,
        curr_data: dict,
        significant_fields: list[str],
    ) -> list[FieldDiff]:
        """Compute field-level diffs."""
        fields = []

        # If no significant fields defined, compare all keys from both data dicts
        if not significant_fields:
            all_keys = set(prev_data.keys()) | set(curr_data.keys())
            field_names = sorted(all_keys)
        else:
            field_names = significant_fields

        for field_name in field_names:
            old_value = prev_data.get(field_name)
            new_value = curr_data.get(field_name)

            if field_name not in prev_data:
                change_type = "added"
            elif field_name not in curr_data:
                change_type = "removed"
                new_value = None  # Field was removed
            elif old_value != new_value:
                change_type = "changed"
            else:
                change_type = "unchanged"

            fields.append(FieldDiff(
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                change_type=change_type,
            ))

        return fields

    def _generate_change_summary(self, fields: list[FieldDiff], result_type: str) -> str:
        """Generate human-readable summary of changes."""
        changed_fields = [f for f in fields if f.change_type != "unchanged"]

        if not changed_fields:
            return "No significant changes"

        # Group changes by type
        additions = [f for f in changed_fields if f.change_type == "added"]
        removals = [f for f in changed_fields if f.change_type == "removed"]
        changes = [f for f in changed_fields if f.change_type == "changed"]

        parts = []

        if additions:
            parts.append(f"Added: {', '.join(f.field_name for f in additions)}")

        if removals:
            parts.append(f"Removed: {', '.join(f.field_name for f in removals)}")

        # Handle changed fields with type-specific formatting
        if changes:
            for f in changes:
                if f.field_name == "phase" and f.new_value:
                    if f.new_value.lower() in ("running", "succeeded", "healthy"):
                        parts.append(f"{f.field_name}: {f.old_value} → {f.new_value} ✓")
                    elif f.new_value.lower() in ("failed", "error", "crashloopbackoff"):
                        parts.append(f"{f.field_name}: {f.old_value} → {f.new_value} ⚠")
                    else:
                        parts.append(f"{f.field_name}: {f.old_value} → {f.new_value}")
                elif f.field_name == "restarts" and isinstance(f.new_value, int):
                    if f.new_value > f.old_value:
                        parts.append(f"{f.field_name}: {f.old_value} → {f.new_value} (+{f.new_value - f.old_value})")
                    else:
                        parts.append(f"{f.field_name}: {f.old_value} → {f.new_value}")
                elif f.field_name in ("sync_status", "health_status"):
                    parts.append(f"{f.field_name}: {f.old_value} → {f.new_value}")
                else:
                    # Generic change
                    if f.old_value is not None and f.new_value is not None:
                        parts.append(f"{f.field_name}: {f.old_value} → {f.new_value}")

        return "; ".join(parts)

    def _generate_summary(
        self,
        has_changes: bool,
        change_summary: str,
        time_delta: Optional[int],
    ) -> str:
        """Generate overall diff summary."""
        if not has_changes:
            return "No changes since last check"

        time_str = ""
        if time_delta:
            if time_delta < 60:
                time_str = f" ({time_delta} seconds ago)"
            elif time_delta < 3600:
                minutes = time_delta // 60
                time_str = f" ({minutes} minute{'s' if minutes != 1 else ''} ago)"
            else:
                hours = time_delta // 3600
                time_str = f" ({hours} hour{'s' if hours != 1 else ''} ago)"

        return f"Changes{time_str}: {change_summary}"

    def cache_previous_result(self, topic_id: str, result: dict) -> None:
        """Cache a result as the previous result for a topic."""
        timestamp = result.get("created_at", int(datetime.now(timezone.utc).timestamp()))
        self._cache[topic_id] = (result, timestamp)

    def get_cached_result(self, topic_id: str) -> Optional[dict]:
        """Get the cached previous result for a topic."""
        if topic_id in self._cache:
            result, timestamp = self._cache[topic_id]
            # Check if cache is still valid (within 1 hour)
            age = int(datetime.now(timezone.utc).timestamp()) - timestamp
            if age < 3600:
                return result
            else:
                # Cache expired
                del self._cache[topic_id]
        return None

    def clear_cache(self, topic_id: Optional[str] = None) -> None:
        """Clear cached results for a topic or all topics."""
        if topic_id:
            self._cache.pop(topic_id, None)
        else:
            self._cache.clear()


# Global diff engine instance
_diff_engine: Optional[DiffEngine] = None


def get_diff_engine() -> DiffEngine:
    """Get or create the global diff engine instance."""
    global _diff_engine
    if _diff_engine is None:
        _diff_engine = DiffEngine()
    return _diff_engine
