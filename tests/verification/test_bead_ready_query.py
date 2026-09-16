"""
Test verification for bead ready frontier query correctness.

This test prevents regression of the schema mismatch where the legacy query
referenced non-existent columns (status, blocked_by) instead of the correct
bead-rs schema columns (base_status, manual_blocked).
"""

import sqlite3
from pathlib import Path
import sys


def test_bead_schema_columns():
    """Verify that the bead-rs schema has the expected columns."""
    db_path = Path(__file__).parent.parent.parent / ".beads" / "beads.db"

    if not db_path.exists():
        print(f"SKIP: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get actual columns
    cursor.execute("PRAGMA table_info(issues)")
    actual_columns = {row[1] for row in cursor.fetchall()}

    # Verify expected columns exist
    expected_columns = {
        'id', 'title', 'description', 'notes', 'priority', 'issue_type',
        'base_status', 'manual_blocked', 'assignee', 'created_at', 'updated_at'
    }

    missing_columns = expected_columns - actual_columns
    assert not missing_columns, f"Missing expected columns: {missing_columns}"

    # Verify legacy columns do NOT exist (prevents using wrong query)
    legacy_columns = {'status', 'blocked_by'}
    found_legacy = legacy_columns & actual_columns
    assert not found_legacy, f"Legacy columns still present: {found_legacy}"

    conn.close()
    print("✓ Schema columns verified")


def test_ready_frontier_query():
    """Verify that the corrected ready frontier query works correctly."""
    db_path = Path(__file__).parent.parent.parent / ".beads" / "beads.db"

    if not db_path.exists():
        print(f"SKIP: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Run the corrected query
    ready_query = """
    SELECT id FROM issues
    WHERE base_status = 'open'
    AND assignee IS NULL
    AND manual_blocked = 0
    ORDER BY priority DESC, created_at ASC
    """

    cursor.execute(ready_query)
    ready_beads = cursor.fetchall()

    # Verify the query doesn't error
    assert isinstance(ready_beads, list), "Query should return a list"

    # Run counts query to validate logic
    cursor.execute("""
    SELECT
      COUNT(*) FILTER (WHERE base_status = 'open') as total_open,
      COUNT(*) FILTER (WHERE base_status = 'open' AND assignee IS NULL AND manual_blocked = 0) as ready_for_claiming,
      COUNT(*) FILTER (WHERE base_status = 'open' AND assignee IS NOT NULL) as assigned_open,
      COUNT(*) FILTER (WHERE base_status = 'open' AND manual_blocked = 1) as manually_blocked
    FROM issues
    """)

    counts = cursor.fetchone()
    total_open, ready_count, assigned_count, blocked_count = counts

    # Verify counts are consistent
    assert total_open == ready_count + assigned_count + blocked_count, \
        f"Count mismatch: total_open={total_open} != ready({ready_count}) + assigned({assigned_count}) + blocked({blocked_count})"

    # Verify ready count matches query result count
    assert len(ready_beads) == ready_count, \
        f"Ready count mismatch: query returned {len(ready_beads)} but COUNT returned {ready_count}"

    conn.close()
    print(f"✓ Ready frontier query verified: {len(ready_beads)} ready beads found")


def test_legacy_query_fails():
    """Verify that the legacy query with wrong column names would fail."""
    db_path = Path(__file__).parent.parent.parent / ".beads" / "beads.db"

    if not db_path.exists():
        print(f"SKIP: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Try the legacy query that uses wrong column names
    legacy_query = """
    SELECT id FROM issues
    WHERE status = 'open'
    AND assignee IS NULL
    AND blocked_by IS NOT NULL
    ORDER BY priority DESC, created_at ASC
    """

    try:
        cursor.execute(legacy_query)
        assert False, "Legacy query should have failed with 'no such column' error"
    except sqlite3.OperationalError as e:
        assert "no such column" in str(e), f"Expected 'no such column' error, got: {e}"
        print(f"✓ Legacy query correctly fails: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    print("Running bead ready query verification tests...")
    print()

    try:
        test_bead_schema_columns()
        test_ready_frontier_query()
        test_legacy_query_fails()
        print()
        print("All tests passed ✓")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)
