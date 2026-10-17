"""Exercise the committed bead-rs ready query without a live bead database.

The live ``.beads/beads.db`` is local state and is absent from git archives.
The fixture covers the columns used by the committed SQL and representative
ready, assigned, manually blocked, and closed issues.
"""

import re
import sqlite3
from pathlib import Path

import pytest


QUERY_PATH = Path(__file__).with_name("test_bead_ready_query.sql")


def _queries() -> tuple[str, str]:
    """Read the executable statements from the committed query example."""
    sql = "\n".join(
        line for line in QUERY_PATH.read_text().splitlines()
        if not line.lstrip().startswith("--")
    )
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    assert len(statements) == 2, "Expected ready and count queries"
    return statements[0], statements[1]


@pytest.fixture
def bead_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE issues (
            id TEXT PRIMARY KEY,
            base_status TEXT NOT NULL,
            assignee TEXT,
            manual_blocked INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.executemany(
        "INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("ready-high-old", "open", None, 0, 5, "2026-01-01"),
            ("ready-high-new", "open", None, 0, 5, "2026-01-02"),
            ("ready-low", "open", None, 0, 1, "2026-01-01"),
            ("assigned", "open", "worker", 0, 5, "2026-01-01"),
            ("blocked", "open", None, 1, 5, "2026-01-01"),
            ("assigned-blocked", "open", "worker", 1, 5, "2026-01-01"),
            ("closed", "closed", None, 0, 5, "2026-01-01"),
        ],
    )
    try:
        yield conn
    finally:
        conn.close()


def test_query_uses_bead_rs_columns(bead_db):
    """The source queries must compile against the current column names."""
    columns = {row[1] for row in bead_db.execute("PRAGMA table_info(issues)")}
    assert {"base_status", "manual_blocked", "assignee"} <= columns
    assert not {"status", "blocked_by"} & columns

    for query in _queries():
        assert re.search(r"\bbase_status\b", query)
        assert re.search(r"\bmanual_blocked\b", query)
        assert not re.search(r"\b(?:status|blocked_by)\b", query)
        bead_db.execute(query).fetchall()


def test_ready_query_filters_and_orders_issues(bead_db):
    ready_query, _ = _queries()
    ids = [row[0] for row in bead_db.execute(ready_query)]
    assert ids == ["ready-high-old", "ready-high-new", "ready-low"]


def test_legacy_query_rejects_removed_columns(bead_db):
    with pytest.raises(sqlite3.OperationalError, match="no such column: status"):
        bead_db.execute(
            "SELECT id FROM issues WHERE status = 'open' "
            "AND assignee IS NULL AND blocked_by IS NOT NULL"
        ).fetchall()


def test_count_query_accounts_for_assigned_blocked_overlap(bead_db):
    _, count_query = _queries()
    total_open, ready, assigned, blocked = bead_db.execute(count_query).fetchone()
    assert (total_open, ready, assigned, blocked) == (6, 3, 2, 2)

    # An assigned issue can also be manually blocked, so those counts overlap.
    assigned_and_blocked = bead_db.execute(
        "SELECT COUNT(*) FROM issues WHERE base_status = 'open' "
        "AND assignee IS NOT NULL AND manual_blocked = 1"
    ).fetchone()[0]
    assert total_open == ready + assigned + blocked - assigned_and_blocked
