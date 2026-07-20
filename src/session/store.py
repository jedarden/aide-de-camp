"""
Session store implementation using SQLite with WAL mode.

Stores sessions, surfaces, utterances, intents, results, topics, and intent_topics.
Provides concurrent read access with serialized writes via WAL mode.
"""

import os

import aiosqlite
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx

# Default DB path. Overridable via ADC_DB_PATH env var so tests can point at an
# isolated temp/in-memory DB instead of the production data/session.db.
DEFAULT_DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")

# Schema definition
SCHEMA_SQL = """
-- Sessions: surface-agnostic persistent entities
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    created_at      INTEGER NOT NULL,
    last_active     INTEGER NOT NULL,
    primary_surface_id TEXT
);

-- Surfaces: transient windows into sessions
CREATE TABLE IF NOT EXISTS surfaces (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    type            TEXT NOT NULL CHECK(type IN ('canvas', 'telegram', 'audio')),
    state           TEXT NOT NULL CHECK(state IN ('active', 'idle', 'disconnected')) DEFAULT 'active',
    always_available INTEGER DEFAULT 0 CHECK(always_available IN (0, 1)),
    last_seen       INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_surfaces_session ON surfaces(session_id);
CREATE INDEX IF NOT EXISTS idx_surfaces_state ON surfaces(state);

-- Utterances: raw input from user
CREATE TABLE IF NOT EXISTS utterances (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    raw_text    TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_utterances_session ON utterances(session_id);

-- Intents: parsed intent threads from utterances
CREATE TABLE IF NOT EXISTS intents (
    id           TEXT PRIMARY KEY,
    utterance_id TEXT NOT NULL,
    session_id   TEXT NOT NULL,
    topic_id     TEXT,
    project_slug TEXT,
    intent_type  TEXT NOT NULL,
    status       TEXT NOT NULL CHECK(status IN ('pending', 'dispatched', 'resolved', 'cancelled')) DEFAULT 'pending',
    bead_ref     TEXT,
    created_at   INTEGER NOT NULL,
    resolved_at  INTEGER,
    FOREIGN KEY (utterance_id) REFERENCES utterances(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_intents_session ON intents(session_id);
CREATE INDEX IF NOT EXISTS idx_intents_topic ON intents(topic_id);
CREATE INDEX IF NOT EXISTS idx_intents_status ON intents(status);

-- Results: structured data returned by agents
CREATE TABLE IF NOT EXISTS results (
    id          TEXT PRIMARY KEY,
    intent_id   TEXT NOT NULL,
    topic_id    TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    summary     TEXT NOT NULL,
    data        TEXT NOT NULL,  -- JSON
    urgency     TEXT NOT NULL CHECK(urgency IN ('critical', 'high', 'normal', 'low')) DEFAULT 'normal',
    created_at  INTEGER NOT NULL,
    surfaced_at INTEGER,
    acked_at    INTEGER,
    previous_result_id TEXT,  -- Link to previous result for diff
    diff_summary TEXT,  -- Human-readable diff summary
    diff_data    TEXT,  -- JSON: detailed field diffs
    FOREIGN KEY (intent_id) REFERENCES intents(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
    FOREIGN KEY (previous_result_id) REFERENCES results(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_results_session ON results(session_id);
CREATE INDEX IF NOT EXISTS idx_results_topic ON results(topic_id);
CREATE INDEX IF NOT EXISTS idx_results_created ON results(created_at);
CREATE INDEX IF NOT EXISTS idx_results_previous ON results(previous_result_id);

-- Topics: persistent concerns organizing intents and results
CREATE TABLE IF NOT EXISTS topics (
    id           TEXT PRIMARY KEY,
    label        TEXT NOT NULL,
    type         TEXT NOT NULL CHECK(type IN ('project', 'research', 'personal', 'exception', 'compound')) DEFAULT 'adhoc',
    project_slugs TEXT,  -- JSON array
    scope        TEXT NOT NULL CHECK(scope IN ('session', 'cross-session', 'global')) DEFAULT 'session',
    session_id   TEXT,
    created_at   INTEGER NOT NULL,
    last_active  INTEGER NOT NULL,
    archived_at  INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_topics_session ON topics(session_id);
CREATE INDEX IF NOT EXISTS idx_topics_scope ON topics(scope);
CREATE INDEX IF NOT EXISTS idx_topics_active ON topics(last_active DESC);

-- Topic context cache: pre-warmed context for active topics
CREATE TABLE IF NOT EXISTS topic_context_cache (
    topic_id     TEXT PRIMARY KEY,
    context_data TEXT NOT NULL,  -- JSON: pre-fetched context (kubectl, git, beads results)
    fetched_at  INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_context_expires ON topic_context_cache(expires_at);

-- Intent-topic many-to-many relationship
CREATE TABLE IF NOT EXISTS intent_topics (
    intent_id TEXT NOT NULL,
    topic_id  TEXT NOT NULL,
    PRIMARY KEY (intent_id, topic_id),
    FOREIGN KEY (intent_id) REFERENCES intents(id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

-- Feedback signals: implicit user behavior tracking for background analysis
CREATE TABLE IF NOT EXISTS feedback_signals (
    signal_id    TEXT PRIMARY KEY,
    signal_type  TEXT NOT NULL,
    session_id   TEXT NOT NULL,
    result_id    TEXT,
    topic_id     TEXT,
    timestamp    INTEGER NOT NULL,
    data         TEXT NOT NULL,  -- JSON: signal-specific data
    surface_type TEXT,
    processed    INTEGER DEFAULT 0 CHECK(processed IN (0, 1)),
    processed_at INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (result_id) REFERENCES results(id) ON DELETE SET NULL,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_session ON feedback_signals(session_id);
CREATE INDEX IF NOT EXISTS idx_signals_type ON feedback_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_processed ON feedback_signals(processed);
CREATE INDEX IF NOT EXISTS idx_signals_result ON feedback_signals(result_id);
"""


class SessionStore:
    """Session store with WAL mode for concurrent access."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def initialize(self) -> None:
        """Initialize database with schema and WAL mode."""
        async with aiosqlite.connect(self.db_path) as db:
            # Enable WAL mode for concurrent reads during writes
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")

            # Create schema
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    async def close(self) -> None:
        """Close database connection pool."""
        # aiosqlite uses connection-per-context, so just ensure checkpoint
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # Session operations
    async def create_session(self, session_id: str | None = None) -> str:
        """Create a new session and return its ID."""
        if not session_id:
            session_id = str(uuid4())
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO sessions (id, created_at, last_active) VALUES (?, ?, ?)",
                (session_id, now, now)
            )
            await db.commit()
        return session_id

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get session by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_session_activity(self, session_id: str) -> None:
        """Update session last_active timestamp."""
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET last_active = ? WHERE id = ?",
                (now, session_id)
            )
            await db.commit()

    async def set_primary_surface(self, session_id: str, surface_id: str) -> None:
        """Set the primary surface for a session."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET primary_surface_id = ? WHERE id = ?",
                (surface_id, session_id)
            )
            await db.commit()

    async def delete_session(self, session_id: str) -> dict:
        """Delete a session and every row tied to it. Returns a removal summary.

        Used by test teardown (DELETE /api/v1/sessions/{id}) to guarantee a
        session and all its topics/results/intents/utterances/surfaces/signal
        rows are gone. Note: SQLite FK ``ON DELETE CASCADE`` is *not* enforced
        here (``PRAGMA foreign_keys`` is never enabled), so child rows are
        deleted explicitly, in dependency order, within one transaction.

        The topics table references sessions with ``ON DELETE SET NULL``, so
        topics are *not* cascade-removed even if FKs were on — deleting them
        explicitly is required for a true clean teardown.

        Returns ``{"session_removed": 0|1, "topics_removed": <int>}``.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Count what we're about to remove (before deleting).
            async with db.execute(
                "SELECT COUNT(*) FROM topics WHERE session_id = ?", (session_id,)
            ) as cur:
                topics_removed = (await cur.fetchone())[0]
            async with db.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ) as cur:
                session_removed = 1 if await cur.fetchone() else 0

            # Children first, parents last (matches FK dependency order).
            await db.execute(
                "DELETE FROM feedback_signals WHERE session_id = ?", (session_id,)
            )
            await db.execute(
                "DELETE FROM results WHERE session_id = ?", (session_id,)
            )
            await db.execute(
                "DELETE FROM intent_topics WHERE intent_id IN "
                "(SELECT id FROM intents WHERE session_id = ?)",
                (session_id,),
            )
            await db.execute(
                "DELETE FROM intents WHERE session_id = ?", (session_id,)
            )
            await db.execute(
                "DELETE FROM utterances WHERE session_id = ?", (session_id,)
            )
            await db.execute(
                "DELETE FROM topic_context_cache WHERE topic_id IN "
                "(SELECT id FROM topics WHERE session_id = ?)",
                (session_id,),
            )
            await db.execute(
                "DELETE FROM topics WHERE session_id = ?", (session_id,)
            )
            await db.execute(
                "DELETE FROM surfaces WHERE session_id = ?", (session_id,)
            )
            await db.execute(
                "DELETE FROM sessions WHERE id = ?", (session_id,)
            )
            await db.commit()

        return {"session_removed": session_removed, "topics_removed": topics_removed}

    # Surface operations
    async def register_surface(
        self,
        session_id: str,
        surface_type: str,
        always_available: bool = False,
    ) -> str:
        """Register a new surface for a session."""
        surface_id = str(uuid4())
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO surfaces
                   (id, session_id, type, state, always_available, last_seen)
                   VALUES (?, ?, ?, 'active', ?, ?)""",
                (surface_id, session_id, surface_type, 1 if always_available else 0, now)
            )
            await db.commit()
        return surface_id

    async def update_surface_heartbeat(self, surface_id: str) -> None:
        """Update surface last_seen timestamp."""
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE surfaces SET last_seen = ?, state = 'active' WHERE id = ?",
                (now, surface_id)
            )
            await db.commit()

    async def mark_surface_disconnected(self, surface_id: str) -> None:
        """Mark a surface as disconnected."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE surfaces SET state = 'disconnected' WHERE id = ?",
                (surface_id,)
            )
            await db.commit()

    async def get_active_surfaces(self, session_id: str) -> list[dict]:
        """Get all active surfaces for a session, ordered by last_seen."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM surfaces
                   WHERE session_id = ? AND state IN ('active', 'idle')
                   ORDER BY last_seen DESC""",
                (session_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_fallback_surface(self) -> Optional[dict]:
        """Get the always-available fallback surface (Telegram)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM surfaces
                   WHERE always_available = 1 AND state != 'disconnected'
                   LIMIT 1"""
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    # Utterance operations
    async def create_utterance(self, session_id: str, raw_text: str, utterance_id: str | None = None) -> str:
        """Create a new utterance and return its ID."""
        utterance_id = utterance_id or str(uuid4())
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO utterances (id, session_id, raw_text, created_at) VALUES (?, ?, ?, ?)",
                (utterance_id, session_id, raw_text, now)
            )
            await db.commit()
        return utterance_id

    # Intent operations
    async def create_intent(
        self,
        utterance_id: str,
        session_id: str,
        project_slug: str | None,
        intent_type: str,
        bead_ref: str | None = None,
    ) -> str:
        """Create a new intent and return its ID."""
        intent_id = str(uuid4())
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO intents
                   (id, utterance_id, session_id, project_slug, intent_type, bead_ref, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (intent_id, utterance_id, session_id, project_slug, intent_type, bead_ref, now)
            )
            await db.commit()
        return intent_id

    async def update_intent_status(
        self,
        intent_id: str,
        status: str,
        resolved_at: int | None = None,
    ) -> None:
        """Update intent status."""
        async with aiosqlite.connect(self.db_path) as db:
            if resolved_at is None and status == "resolved":
                resolved_at = int(datetime.now().timestamp())
            await db.execute(
                "UPDATE intents SET status = ?, resolved_at = ? WHERE id = ?",
                (status, resolved_at, intent_id)
            )
            await db.commit()

    async def get_pending_intents(self, session_id: str) -> list[dict]:
        """Get all pending intents for a session."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM intents
                   WHERE session_id = ? AND status IN ('pending', 'dispatched')
                   ORDER BY created_at DESC""",
                (session_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # Result operations
    async def create_result(
        self,
        intent_id: str,
        topic_id: str,
        session_id: str,
        summary: str,
        data: dict,
        urgency: str = "normal",
        previous_result_id: str | None = None,
        diff_summary: str | None = None,
        diff_data: dict | None = None,
    ) -> str:
        """Create a new result and return its ID."""
        import json
        result_id = str(uuid4())
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO results
                   (id, intent_id, topic_id, session_id, summary, data, urgency, created_at, surfaced_at,
                    previous_result_id, diff_summary, diff_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result_id, intent_id, topic_id, session_id, summary, json.dumps(data),
                    urgency, now, now, previous_result_id, diff_summary,
                    json.dumps(diff_data) if diff_data else None
                )
            )
            await db.commit()
        return result_id

    async def get_unsurfed_results(self, session_id: str) -> list[dict]:
        """Get results that haven't been surfaced to the user yet."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM results
                   WHERE session_id = ? AND surfaced_at IS NULL
                   ORDER BY created_at ASC""",
                (session_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def mark_results_surfed(self, session_id: str) -> None:
        """Mark all unsurfed results as surfaced."""
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE results SET surfaced_at = ? WHERE session_id = ? AND surfaced_at IS NULL",
                (now, session_id)
            )
            await db.commit()

    async def mark_results_surfed_by_ids(self, session_id: str, result_ids: list[str]) -> None:
        """Mark specific results as surfaced."""
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            for result_id in result_ids:
                await db.execute(
                    "UPDATE results SET surfaced_at = ? WHERE id = ? AND session_id = ?",
                    (now, result_id, session_id)
                )
            await db.commit()

    # Topic operations
    async def create_topic(
        self,
        label: str,
        topic_type: str = "adhoc",
        project_slugs: list[str] | None = None,
        scope: str = "session",
        session_id: str | None = None,
    ) -> str:
        """Create a new topic and return its ID."""
        import json
        topic_id = str(uuid4())
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO topics
                   (id, label, type, project_slugs, scope, session_id, created_at, last_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (topic_id, label, topic_type, json.dumps(project_slugs or []), scope, session_id, now, now)
            )
            await db.commit()
        return topic_id

    async def find_or_create_topic(
        self,
        label: str,
        session_id: str,
        topic_type: str = "adhoc",
        project_slugs: list[str] | None = None,
    ) -> tuple[str, bool]:
        """Find existing topic by label and session, or create new. Returns (topic_id, created)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Try to find existing topic in session scope
            async with db.execute(
                """SELECT id FROM topics
                   WHERE label = ? AND scope = 'session' AND session_id = ? AND archived_at IS NULL
                   LIMIT 1""",
                (label, session_id)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0], False

        # Create new topic
        topic_id = await self.create_topic(label, topic_type, project_slugs, "session", session_id)
        return topic_id, True

    async def update_topic_activity(self, topic_id: str) -> None:
        """Update topic last_active timestamp."""
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE topics SET last_active = ? WHERE id = ?",
                (now, topic_id)
            )
            await db.commit()

    async def get_active_topics(self, session_id: str) -> list[dict]:
        """Get active topics for a session, ordered by last_active."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT t.*,
                          (SELECT COUNT(*) FROM results r WHERE r.topic_id = t.id) as result_count
                   FROM topics t
                   WHERE (t.session_id = ? OR t.scope IN ('cross-session', 'global'))
                     AND t.archived_at IS NULL
                   ORDER BY t.last_active DESC""",
                (session_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_latest_result_for_topic(self, topic_id: str) -> Optional[dict]:
        """Get the most recent result for a topic."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM results
                   WHERE topic_id = ?
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (topic_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def link_intent_to_topic(self, intent_id: str, topic_id: str) -> None:
        """Link an intent to a topic (many-to-many)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO intent_topics (intent_id, topic_id) VALUES (?, ?)",
                (intent_id, topic_id)
            )
            await db.commit()

    # Workload summary for reconnect
    async def get_workload_summary(self, session_id: str) -> dict:
        """Get summary of what happened while surface was disconnected."""
        async with aiosqlite.connect(self.db_path) as db:
            # Get pending intents
            pending_count = (await db.execute_fetchall(
                "SELECT COUNT(*) FROM intents WHERE session_id = ? AND status IN ('pending', 'dispatched')",
                (session_id,)
            ))[0][0]

            # Get new results (unsurfaced results)
            new_results = (await db.execute_fetchall(
                """SELECT COUNT(*) FROM results
                   WHERE session_id = ? AND surfaced_at IS NULL""",
                (session_id,)
            ))[0][0]

            # Get exceptions (HUMAN beads or high urgency items)
            exceptions = (await db.execute_fetchall(
                """SELECT COUNT(*) FROM results
                   WHERE session_id = ? AND urgency IN ('critical', 'high') AND acked_at IS NULL""",
                (session_id,)
            ))[0][0]

            return {
                "pending_intents": pending_count,
                "new_results": new_results,
                "unresolved_exceptions": exceptions,
            }

    # Topic context cache operations
    async def set_topic_context(
        self,
        topic_id: str,
        context_data: dict,
        ttl_seconds: int = 600,  # Default 10 minutes
    ) -> None:
        """Cache pre-fetched context for a topic."""
        import json
        now = int(datetime.now().timestamp())
        expires_at = now + ttl_seconds

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO topic_context_cache
                   (topic_id, context_data, fetched_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (topic_id, json.dumps(context_data), now, expires_at)
            )
            await db.commit()

    async def get_topic_context(self, topic_id: str) -> Optional[dict]:
        """Get cached context for a topic if still valid."""
        import json
        now = int(datetime.now().timestamp())

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT context_data, expires_at FROM topic_context_cache
                   WHERE topic_id = ? AND expires_at > ?""",
                (topic_id, now)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "context": json.loads(row["context_data"]),
                        "expires_at": row["expires_at"],
                    }
        return None

    async def invalidate_topic_context(self, topic_id: str) -> None:
        """Invalidate cached context for a topic."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM topic_context_cache WHERE topic_id = ?",
                (topic_id,)
            )
            await db.commit()

    async def cleanup_expired_context(self) -> int:
        """Remove expired context cache entries. Returns count of deleted entries."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM topic_context_cache WHERE expires_at <= ?",
                (int(datetime.now().timestamp()),)
            )
            await db.commit()
            return cursor.rowcount

    async def get_active_topic_ids(self) -> list[str]:
        """Get IDs of all active topics (recently active, not archived)."""
        # Active topics are those with activity in last hour
        one_hour_ago = int(datetime.now().timestamp()) - 3600

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT id FROM topics
                   WHERE last_active > ? AND archived_at IS NULL""",
                (one_hour_ago,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    # Feedback signal operations
    async def create_feedback_signal(
        self,
        signal_id: str,
        signal_type: str,
        session_id: str,
        result_id: str | None = None,
        topic_id: str | None = None,
        timestamp: int | None = None,
        data: dict | None = None,
        surface_type: str | None = None,
    ) -> str:
        """Create a new feedback signal and return its ID."""
        import json
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO feedback_signals
                   (signal_id, signal_type, session_id, result_id, topic_id, timestamp, data, surface_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal_id, signal_type, session_id, result_id,
                    topic_id, timestamp or now, json.dumps(data or {}),
                    surface_type
                )
            )
            await db.commit()
        return signal_id

    async def get_unprocessed_signals(
        self,
        signal_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get unprocessed feedback signals for background analysis."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = """SELECT * FROM feedback_signals WHERE processed = 0"""
            params = []

            if signal_type:
                query += " AND signal_type = ?"
                params.append(signal_type)

            query += " ORDER BY timestamp ASC LIMIT ?"
            params.append(limit)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def mark_signals_processed(
        self,
        signal_ids: list[str],
    ) -> None:
        """Mark feedback signals as processed."""
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            for signal_id in signal_ids:
                await db.execute(
                    "UPDATE feedback_signals SET processed = 1, processed_at = ? WHERE signal_id = ?",
                    (now, signal_id)
                )
            await db.commit()

    async def get_session_feedback_summary(
        self,
        session_id: str,
        since: int | None = None,
    ) -> dict:
        """Get a summary of feedback signals for a session."""
        one_hour_ago = int(datetime.now().timestamp()) - 3600

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get signal counts by type
            since_clause = since or one_hour_ago
            async with db.execute(
                """SELECT signal_type, COUNT(*) as count
                   FROM feedback_signals
                   WHERE session_id = ? AND timestamp >= ?
                   GROUP BY signal_type""",
                (session_id, since_clause)
            ) as cursor:
                type_counts = {row["signal_type"]: row["count"] for row in await cursor.fetchall()}

            # Get average ack delay
            async with db.execute(
                """SELECT AVG(CAST(data->>'ack_delay_seconds' AS INTEGER)) as avg_delay
                   FROM feedback_signals
                   WHERE session_id = ? AND signal_type = 'ack_speed' AND timestamp >= ?""",
                (session_id, since_clause)
            ) as cursor:
                row = await cursor.fetchone()
                avg_ack_delay = row["avg_delay"] if row and row["avg_delay"] else 0

            return {
                "signal_counts": type_counts,
                "avg_ack_delay_seconds": avg_ack_delay,
            }

    async def create_result_with_diff(
        self,
        intent_id: str,
        topic_id: str,
        session_id: str,
        summary: str,
        data: dict,
        urgency: str = "normal",
    ) -> tuple[str, bool]:
        """
        Create a new result with automatic diff computation.

        Returns (result_id, has_diff).

        Convenience method that automatically computes the diff against
        the previous result for the same topic (if one exists).
        """
        from ..diff.engine import get_diff_engine

        # Get previous result for this topic
        previous_result = await self.get_latest_result_for_topic(topic_id)

        # Compute diff if we have a previous result
        diff_summary = None
        diff_data = None
        has_diff = False

        if previous_result:
            diff_engine = get_diff_engine()
            diff_result = await diff_engine.compute_diff(
                topic_id=topic_id,
                previous_result=previous_result,
                current_result={"data": data},
            )

            if diff_result.has_changes:
                has_diff = True
                diff_summary = diff_result.change_summary
                diff_data = {
                    "fields": [
                        {
                            "field_name": f.field_name,
                            "old_value": f.old_value,
                            "new_value": f.new_value,
                            "change_type": f.change_type,
                        }
                        for f in diff_result.fields
                    ],
                    "summary": diff_result.summary,
                }

        # Create the result with diff data
        result_id = await self.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=summary,
            data=data,
            urgency=urgency,
            previous_result_id=previous_result["id"] if previous_result else None,
            diff_summary=diff_summary,
            diff_data=diff_data,
        )

        return result_id, has_diff


# Global session store instance
_store: SessionStore | None = None


def get_store(db_path: Path | None = None) -> SessionStore:
    """Get or create the global session store instance.

    When db_path is not given, resolves in this order:
      1. ADC_DB_PATH env var (used by tests to isolate from production data)
      2. DEFAULT_DB_PATH (data/session.db)
    """
    global _store
    if _store is None:
        if db_path is None:
            env_path = os.environ.get("ADC_DB_PATH")
            db_path = Path(env_path) if env_path else DEFAULT_DB_PATH
        _store = SessionStore(db_path)
    return _store
