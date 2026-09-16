#!/usr/bin/env python3
"""
Test: Verify bead ready frontier query against current database schema

This test documents the schema evolution from bead-forge (bf) to bead-rs and
prevents regression of the column name mismatch that causes starvation alerts.

SCHEMA EVOLUTION:
- Old (bead-forge/bf): `status` column, `blocked_by` column (IS NOT NULL meant "has blockers")
- New (bead-rs): `base_status` column, `manual_blocked` column (0 means not blocked)

THE BUG:
The old query used `status = 'open' AND blocked_by IS NOT NULL`, which would:
1. Fail with "no such column: status" (column renamed to base_status)
2. Even if it worked, the logic is inverted: blocked_by IS NOT NULL means "HAS blockers",
   so it would return only blocked beads, excluding ready ones

THE FIX:
Use base_status and manual_blocked = 0 (where 0 means NOT blocked):
  SELECT id FROM issues
  WHERE base_status = 'open'
  AND assignee IS NULL
  AND manual_blocked = 0
  ORDER BY priority DESC, created_at ASC
"""

import sqlite3
import sys
from pathlib import Path

BEADS_DB = Path(__file__).parent.parent.parent / ".beads" / "beads.db"

def test_schema_columns_exist():
    """Verify the bead-rs schema columns exist."""
    conn = sqlite3.connect(BEADS_DB)
    cursor = conn.cursor()

    # Get the actual schema
    cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="issues"')
    schema = cursor.fetchone()[0]

    # Verify bead-rs columns exist
    assert 'base_status' in schema, "bead-rs schema must have base_status column"
    assert 'manual_blocked' in schema, "bead-rs schema must have manual_blocked column"

    # Verify old columns DON'T exist
    assert 'status' not in schema or 'base_status' in schema, \
        "Old 'status' column should not exist without base_status (bead-rs migration)"
    assert 'blocked_by' not in schema, \
        "Old 'blocked_by' column should not exist in bead-rs schema"

    conn.close()
    print("✓ Schema columns verified: base_status, manual_blocked exist")
    return True

def test_ready_query_with_correct_columns():
    """Test the CORRECT query using bead-rs columns."""
    conn = sqlite3.connect(BEADS_DB)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT id FROM issues
            WHERE base_status = 'open'
            AND assignee IS NULL
            AND manual_blocked = 0
            ORDER BY priority DESC, created_at ASC
            LIMIT 5
        ''')
        results = cursor.fetchall()
        print(f"✓ Correct query (base_status, manual_blocked=0) works: {len(results)} beads")
        return results
    except sqlite3.OperationalError as e:
        print(f"✗ Correct query failed: {e}")
        return None
    finally:
        conn.close()

def test_wrong_query_fails_gracefully():
    """Test that the WRONG query (from task description) fails with clear error."""
    conn = sqlite3.connect(BEADS_DB)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT id FROM issues
            WHERE status = 'open'
            AND assignee IS NULL
            AND blocked_by IS NOT NULL
            ORDER BY priority DESC, created_at ASC
        ''')
        results = cursor.fetchall()
        print(f"✗ WARNING: Wrong query unexpectedly succeeded (returned {len(results)} beads)")
        print("   This suggests schema has regressed to old column names!")
        return False
    except sqlite3.OperationalError as e:
        expected_error = "no such column: status"
        if expected_error in str(e):
            print(f"✓ Wrong query correctly fails with: {e}")
            return True
        else:
            print(f"✗ Wrong query failed with unexpected error: {e}")
            return False
    finally:
        conn.close()

def test_bead_count_consistency():
    """Verify bead counts add up correctly."""
    conn = sqlite3.connect(BEADS_DB)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
          COUNT(*) FILTER (WHERE base_status = 'open') as total_open,
          COUNT(*) FILTER (WHERE base_status = 'open' AND assignee IS NULL AND manual_blocked = 0) as ready_for_claiming,
          COUNT(*) FILTER (WHERE base_status = 'open' AND assignee IS NOT NULL) as assigned_open,
          COUNT(*) FILTER (WHERE base_status = 'open' AND manual_blocked = 1) as manually_blocked
        FROM issues
    ''')

    row = cursor.fetchone()
    total_open, ready, assigned, blocked = row

    print(f"\n=== Bead Status Summary ===")
    print(f"Total open beads: {total_open}")
    print(f"Ready for claiming: {ready}")
    print(f"Assigned open beads: {assigned}")
    print(f"Manually blocked: {blocked}")

    # Verify consistency: total_open should equal ready + assigned + blocked
    calculated_total = ready + assigned + blocked
    conn.close()

    if calculated_total == total_open:
        print(f"✓ Count consistency verified: {ready} + {assigned} + {blocked} = {total_open}")
        return True
    else:
        print(f"✗ Count mismatch: {ready} + {assigned} + {blocked} = {calculated_total}, but total is {total_open}")
        return False

def main():
    """Run all verification tests."""
    print("=== Bead Ready Frontier Query Verification ===\n")

    if not BEADS_DB.exists():
        print(f"✗ Beads database not found at {BEADS_DB}")
        sys.exit(1)

    tests_passed = 0
    tests_total = 4

    # Test 1: Schema columns
    if test_schema_columns_exist():
        tests_passed += 1

    # Test 2: Correct query works
    if test_ready_query_with_correct_columns() is not None:
        tests_passed += 1

    # Test 3: Wrong query fails
    if test_wrong_query_fails_gracefully():
        tests_passed += 1

    # Test 4: Count consistency
    if test_bead_count_consistency():
        tests_passed += 1

    print(f"\n=== Test Results: {tests_passed}/{tests_total} passed ===")

    if tests_passed == tests_total:
        print("✓ All tests passed! Ready frontier query is correct.")
        sys.exit(0)
    else:
        print("✗ Some tests failed. Schema or query may be incorrect.")
        sys.exit(1)

if __name__ == "__main__":
    main()
