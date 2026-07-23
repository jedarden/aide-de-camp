"""
Session store implementation using SQLite with WAL mode.

Stores sessions, surfaces, utterances, intents, results, topics, and intent_topics.
Provides concurrent read access with serialized writes via WAL mode.
"""

import logging
import os

import aiosqlite
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

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
    primary_surface_id TEXT,
    reformulation_count INTEGER DEFAULT 0
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
    lookup_kind  TEXT,  -- lookup intents only: 'logs' | 'config' | 'docs' (router-emitted; see Intent Router). NULL otherwise
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
    intent_id   TEXT,  -- NULL for monitoring-originated results (system-originated, no utterance)
    topic_id    TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    summary     TEXT NOT NULL,
    data        TEXT NOT NULL,  -- JSON
    urgency     TEXT NOT NULL CHECK(urgency IN ('critical', 'high', 'normal', 'low')) DEFAULT 'normal',
    result_type TEXT,  -- deterministic card-selector key, set at result-write time:
                       -- "{intent_type}:{project_slug}" for intent-derived results — one per
                       -- intent thread (the aggregated thread card); lookup threads insert the
                       -- intent's lookup_kind: "lookup:{lookup_kind}:{project_slug}";
                       -- "monitoring:{project_slug}" for monitoring-originated rows. The hot-path
                       -- component lookup keys on this column, no LLM (see UI-Regen Agent /
                       -- component_usage_patterns).
    card_fallback INTEGER NOT NULL DEFAULT 0 CHECK(card_fallback IN (0, 1)),  -- 1 when no component matched this result_type (or below threshold): the client renders the built-in generic fallback card (see Component Library → Built-in generic fallback card). 0 when a real component rendered it (card_cache holds the rendered HTML).
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

-- Per-stage latency capture for every dispatch (Latency Budget & Instrumentation).
-- Keyed by the intent *thread* id (routed_intent.intent_id — the same id the
-- fetch/synthesize/escalate strands and the results row use), NOT the
-- intents.id the caller mints in create_intent(). router_ms is shared across
-- every intent thread from the same utterance; escalate_ms is NULL for hot-path
-- dispatches; stt_ms/first_render_ms are client-reported and NULL when the
-- client never reports them. synthesize_first_token_ms is NULL until the
-- synthesize strand streams (the non-streaming call_simple path can't measure
-- first token separately) — see src/instrument/timings.py.
CREATE TABLE IF NOT EXISTS dispatch_timings (
    intent_id                 TEXT PRIMARY KEY,
    router_ms                 INTEGER,
    fetch_first_source_ms     INTEGER,
    fetch_total_ms            INTEGER,
    synthesize_first_token_ms INTEGER,
    synthesize_total_ms       INTEGER,
    escalate_ms               INTEGER,
    sse_emit_ms               INTEGER,
    stt_ms                    INTEGER,
    first_render_ms           INTEGER,
    created_at                INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dispatch_timings_created ON dispatch_timings(created_at);

-- Bead watch table: circuit breaker tracking for async beads
-- Persistence layer for the async-path circuit breaker (plan §10 The Async Path).
-- Tracks open beads watched by the BeadWatcher, recording refusal counts,
-- last refusal reasons, SLA deadlines, and fencing state. All state is persisted
-- so a watcher restart loses nothing -- breaker state lives in the database,
-- not only in memory.
CREATE TABLE IF NOT EXISTS bead_watch (
    bead_ref           TEXT PRIMARY KEY,  -- References bead ID (intents.bead_ref)
    refusal_count      INTEGER NOT NULL DEFAULT 0,  -- Number of REFUSED: comments seen
    last_refusal_reason TEXT,  -- Most recent refusal reason
    last_refusal_at    INTEGER,  -- Timestamp of most recent refusal
    comment_high_water INTEGER NOT NULL DEFAULT -1,  -- Latest comment index processed (-1 = none)
    sla_deadline       INTEGER NOT NULL,  -- Unix timestamp when SLA expires
    sla_flagged_at     INTEGER,  -- Timestamp when SLA was flagged (NULL if not flagged)
    fenced_at          INTEGER,  -- Timestamp when bead was fenced to status=blocked (NULL if not fenced)
    created_at         INTEGER NOT NULL  -- When this watch row was created
);

CREATE INDEX IF NOT EXISTS idx_bead_watch_sla_deadline ON bead_watch(sla_deadline);
CREATE INDEX IF NOT EXISTS idx_bead_watch_fenced ON bead_watch(fenced_at);

-- Pending bead approvals: beads awaiting user approval before creation
-- Stores approval card data for action/self_modification/monitoring_config beads
-- that passed validation but require explicit user approval.
CREATE TABLE IF NOT EXISTS pending_bead_approvals (
    id                  TEXT PRIMARY KEY,  -- UUID for this approval request
    intent_id           TEXT NOT NULL,  -- Reference to the intent that created this request
    session_id          TEXT NOT NULL,  -- Session for this approval
    bead_body           TEXT NOT NULL,  -- The bead body awaiting approval
    bead_type           TEXT NOT NULL,  -- Bead type (action, self_modification, monitoring_config)
    validation_result   TEXT NOT NULL,  -- JSON: ValidationResult with approval details
    utterance           TEXT NOT NULL,  -- Original user utterance
    project_slug        TEXT,  -- Optional project slug
    topic_id            TEXT,  -- Optional topic ID
    created_at          INTEGER NOT NULL,  -- When the approval was requested
    expires_at          INTEGER NOT NULL,  -- When this approval request expires
    status              TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')) DEFAULT 'pending',
    FOREIGN KEY (intent_id) REFERENCES intents(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pending_approvals_session ON pending_bead_approvals(session_id);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_intent ON pending_bead_approvals(intent_id);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_status ON pending_bead_approvals(status);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_expires ON pending_bead_approvals(expires_at);

-- Card cache: pre-rendered HTML for result components
-- Stores server-side rendered HTML for result/component/layout combinations.
-- Primary key (result_id, component_id, layout_bucket) allows multiple cached
-- variations per result (e.g., different layouts). Populated after component
-- selection to avoid repeated rendering for the same result.
CREATE TABLE IF NOT EXISTS card_cache (
    result_id      TEXT NOT NULL,
    component_id   TEXT NOT NULL,
    layout_bucket  TEXT NOT NULL,
    rendered_html  TEXT NOT NULL,
    created_at     INTEGER NOT NULL,
    PRIMARY KEY (result_id, component_id, layout_bucket)
);

CREATE INDEX IF NOT EXISTS idx_card_cache_result_id ON card_cache(result_id);
"""

# The set of dispatch_timings timing columns record_dispatch_timings() may set.
# intent_id/created_at are handled explicitly (PK / insert-only timestamp).
DISPATCH_TIMING_COLUMNS = (
    "router_ms",
    "fetch_first_source_ms",
    "fetch_total_ms",
    "synthesize_first_token_ms",
    "synthesize_total_ms",
    "escalate_ms",
    "sse_emit_ms",
    "stt_ms",
    "first_render_ms",
)

# Valid intent status values (plan §10 The Async Path: stuck/failed added for circuit breaker)
INTENT_STATUSES = ('pending', 'dispatched', 'resolved', 'cancelled', 'stuck', 'failed')

# Default SLA hours per intent type (plan §10 The Async Path: Visible Aging)
# task-profile: 6h (async bead-backed tasks)
# hot-path intents: 30s (budget is 3s, flag at 10x for aged pending)
DEFAULT_SLA_HOURS: dict[str, float] = {
    "task-profile": 6.0,  # 6 hours for async bead-backed tasks
    "status": 0.008,     # 30 seconds for hot-path status intents
    "action": 0.008,     # 30 seconds for hot-path action intents
    "lookup": 0.008,     # 30 seconds for hot-path lookup intents
    "brainstorm": 0.5,   # 30 minutes for brainstorm (may need user iteration)
    "reminder": 24.0,    # 24 hours for reminders
}

# Circuit breaker thresholds (plan §10 The Async Path)
CIRCUIT_BREAKER_REFUSAL_THRESHOLD = 3  # Fence after N refusals
CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS = 24.0  # Fence after N hours without progress


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

            # Additive migrations: CREATE TABLE IF NOT EXISTS above creates new
            # columns only for freshly-made DBs; an existing data/session.db
            # (e.g. the live Hetzner box) keeps its old column set and must be
            # ALTERed. Each statement is guarded by a PRAGMA table_info probe so
            # it is idempotent and never re-runs once the column exists.
            await self._migrate_additive_columns(db)

    @staticmethod
    async def _migrate_additive_columns(db: aiosqlite.Connection) -> None:
        """Idempotently add columns introduced after the initial schema."""
        async with db.execute("PRAGMA table_info(results)") as cur:
            result_cols = {row[1] for row in await cur.fetchall()}
        if "result_type" not in result_cols:
            await db.execute("ALTER TABLE results ADD COLUMN result_type TEXT")
        if "card_fallback" not in result_cols:
            await db.execute(
                "ALTER TABLE results ADD COLUMN card_fallback INTEGER NOT NULL DEFAULT 0"
            )

        async with db.execute("PRAGMA table_info(intents)") as cur:
            intent_cols = {row[1] for row in await cur.fetchall()}
        if "lookup_kind" not in intent_cols:
            await db.execute("ALTER TABLE intents ADD COLUMN lookup_kind TEXT")

        # Migrate intents.status CHECK constraint to include 'stuck' and 'failed'
        # SQLite doesn't support ALTER CONSTRAINT, so we need to recreate the table
        # First, check if the table still has the old constraint (without stuck/failed)
        await SessionStore._migrate_intents_status_enum(db)

        # Migrate results.intent_id to allow NULL for monitoring-originated results
        await SessionStore._migrate_results_intent_id_nullable(db)

        # Migrate bead_watch.comment_high_water default from 0 to -1
        await SessionStore._migrate_bead_watch_comment_high_water(db)

        # Migrate sessions table to add reformulation_count column
        await SessionStore._migrate_sessions_reformulation_count(db)

        await db.commit()

    @staticmethod
    async def _migrate_intents_status_enum(db: aiosqlite.Connection) -> None:
        """Migrate intents table to support 'stuck' and 'failed' status values.

        Plan §10 The Async Path: extend intents status enum with stuck/failed.
        SQLite doesn't support ALTER CONSTRAINT, so we recreate the table.
        """
        # Check if migration is needed by looking for 'stuck' in the schema
        async with db.execute("PRAGMA table_info(intents)") as cur:
            cols = await cur.fetchall()
            status_col = None
            for col in cols:
                if col[1] == "status":
                    status_col = col
                    break

        # If no status column or already has stuck/failed, skip migration
        if not status_col:
            return

        # Check if the CHECK constraint already includes stuck/failed
        # by inspecting the SQL for the intents table
        async with db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='intents'"
        ) as cur:
            table_sql = await cur.fetchone()
            if table_sql and ("'stuck'" in table_sql[0] or "'failed'" in table_sql[0]):
                # Already migrated
                return

        # Migration needed: recreate table with new constraint
        logger.info("Migrating intents.status to include 'stuck' and 'failed' values")

        # Begin transaction for data migration
        await db.execute("BEGIN IMMEDIATE TRANSACTION")

        try:
            # Create new table with updated constraint
            await db.execute("""
                CREATE TABLE intents_new (
                    id           TEXT PRIMARY KEY,
                    utterance_id TEXT NOT NULL,
                    session_id   TEXT NOT NULL,
                    topic_id     TEXT,
                    project_slug TEXT,
                    intent_type  TEXT NOT NULL,
                    lookup_kind  TEXT,
                    status       TEXT NOT NULL CHECK(status IN ('pending', 'dispatched', 'resolved', 'cancelled', 'stuck', 'failed')) DEFAULT 'pending',
                    bead_ref     TEXT,
                    created_at   INTEGER NOT NULL,
                    resolved_at  INTEGER,
                    FOREIGN KEY (utterance_id) REFERENCES utterances(id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE SET NULL
                )
            """)

            # Copy data from old table to new table
            await db.execute("""
                INSERT INTO intents_new
                SELECT id, utterance_id, session_id, topic_id, project_slug,
                       intent_type, lookup_kind, status, bead_ref, created_at, resolved_at
                FROM intents
            """)

            # Recreate indexes
            await db.execute("DROP INDEX IF EXISTS idx_intents_session")
            await db.execute("DROP INDEX IF EXISTS idx_intents_topic")
            await db.execute("DROP INDEX IF EXISTS idx_intents_status")

            await db.execute("CREATE INDEX idx_intents_session ON intents_new(session_id)")
            await db.execute("CREATE INDEX idx_intents_topic ON intents_new(topic_id)")
            await db.execute("CREATE INDEX idx_intents_status ON intents_new(status)")

            # Drop old table and rename new table
            await db.execute("DROP TABLE intents")
            await db.execute("ALTER TABLE intents_new RENAME TO intents")

            await db.commit()
            logger.info("Migration complete: intents.status now supports 'stuck' and 'failed'")

        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to migrate intents.status: {e}")
            raise

    @staticmethod
    async def _migrate_results_intent_id_nullable(db: aiosqlite.Connection) -> None:
        """Migrate results table to allow NULL intent_id for monitoring-originated results.

        Plan §10 Bead Watcher: monitoring-originated results have intent_id=NULL.
        SQLite doesn't support ALTER COLUMN to drop NOT NULL, so we recreate the table.
        """
        # Check if migration is needed by inspecting the results table schema
        async with db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='results'"
        ) as cur:
            table_sql = await cur.fetchone()
            if not table_sql:
                return  # Table doesn't exist yet

            # If intent_id is already nullable (NOT NULL not present), skip migration
            if "intent_id   TEXT," in table_sql[0] or "intent_id TEXT," in table_sql[0]:
                if "NOT NULL" not in table_sql[0].split("intent_id")[1].split(",")[0]:
                    # Already migrated
                    return

        # Migration needed: recreate table with nullable intent_id
        logger.info("Migrating results.intent_id to allow NULL for monitoring-originated results")

        # Begin transaction for data migration
        await db.execute("BEGIN IMMEDIATE TRANSACTION")

        try:
            # Create new table with nullable intent_id
            await db.execute("""
                CREATE TABLE results_new (
                    id          TEXT PRIMARY KEY,
                    intent_id   TEXT,
                    topic_id    TEXT NOT NULL,
                    session_id  TEXT NOT NULL,
                    summary     TEXT NOT NULL,
                    data        TEXT NOT NULL,
                    urgency     TEXT NOT NULL CHECK(urgency IN ('critical', 'high', 'normal', 'low')) DEFAULT 'normal',
                    result_type TEXT,
                    card_fallback INTEGER NOT NULL DEFAULT 0 CHECK(card_fallback IN (0, 1)),
                    created_at  INTEGER NOT NULL,
                    surfaced_at INTEGER,
                    acked_at    INTEGER,
                    previous_result_id TEXT,
                    diff_summary TEXT,
                    diff_data    TEXT,
                    FOREIGN KEY (intent_id) REFERENCES intents(id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
                    FOREIGN KEY (previous_result_id) REFERENCES results(id) ON DELETE SET NULL
                )
            """)

            # Copy data from old table to new table - explicit column mapping
            # to handle different column orders between old and new schemas
            await db.execute("""
                INSERT INTO results_new (id, intent_id, topic_id, session_id, summary, data, urgency, result_type, card_fallback, created_at, surfaced_at, acked_at, previous_result_id, diff_summary, diff_data)
                SELECT id, intent_id, topic_id, session_id, summary, data, urgency,
                       COALESCE(result_type, 'default') AS result_type,
                       COALESCE(card_fallback, 0) AS card_fallback,
                       created_at, surfaced_at, acked_at, previous_result_id, diff_summary, diff_data
                FROM results
            """)

            # Recreate indexes
            await db.execute("DROP INDEX IF EXISTS idx_results_session")
            await db.execute("DROP INDEX IF EXISTS idx_results_topic")
            await db.execute("DROP INDEX IF EXISTS idx_results_created")
            await db.execute("DROP INDEX IF EXISTS idx_results_previous")

            await db.execute("CREATE INDEX idx_results_session ON results_new(session_id)")
            await db.execute("CREATE INDEX idx_results_topic ON results_new(topic_id)")
            await db.execute("CREATE INDEX idx_results_created ON results_new(created_at)")
            await db.execute("CREATE INDEX idx_results_previous ON results_new(previous_result_id)")

            # Drop old table and rename new table
            await db.execute("DROP TABLE results")
            await db.execute("ALTER TABLE results_new RENAME TO results")

            await db.commit()
            logger.info("Migration complete: results.intent_id now allows NULL")
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to migrate results.intent_id: {e}")
            raise

    @staticmethod
    async def _migrate_bead_watch_comment_high_water(db: aiosqlite.Connection) -> None:
        """Migrate bead_watch.comment_high_water default from 0 to -1.

        The initial schema had DEFAULT 0, which meant the first comment (index 0)
        was skipped on the first check. With DEFAULT -1, no comments are skipped
        initially, and only comments with index > comment_high_water are processed.
        SQLite doesn't support ALTER COLUMN DEFAULT, so we recreate the table.
        """
        # Check if migration is needed by inspecting the bead_watch table schema
        async with db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='bead_watch'"
        ) as cur:
            table_sql = await cur.fetchone()
            if not table_sql:
                return  # Table doesn't exist yet

            # If comment_high_water already has DEFAULT -1, skip migration
            if "DEFAULT -1" in table_sql[0]:
                # Already migrated
                return

        # Migration needed: recreate table with new default
        logger.info("Migrating bead_watch.comment_high_water default from 0 to -1")

        # Begin transaction for data migration
        await db.execute("BEGIN IMMEDIATE TRANSACTION")

        try:
            # Create new table with DEFAULT -1
            await db.execute("""
                CREATE TABLE bead_watch_new (
                    bead_ref           TEXT PRIMARY KEY,
                    refusal_count      INTEGER NOT NULL DEFAULT 0,
                    last_refusal_reason TEXT,
                    last_refusal_at    INTEGER,
                    comment_high_water INTEGER NOT NULL DEFAULT -1,
                    sla_deadline       INTEGER NOT NULL,
                    sla_flagged_at     INTEGER,
                    fenced_at          INTEGER,
                    created_at         INTEGER NOT NULL
                )
            """)

            # Copy data from old table to new table
            # Existing rows with comment_high_water=0 are migrated as-is
            # (they represent "comment 0 has been processed", which is valid)
            await db.execute("""
                INSERT INTO bead_watch_new
                SELECT * FROM bead_watch
            """)

            # Recreate indexes
            await db.execute("DROP INDEX IF EXISTS idx_bead_watch_sla_deadline")
            await db.execute("DROP INDEX IF EXISTS idx_bead_watch_fenced")

            await db.execute("CREATE INDEX idx_bead_watch_sla_deadline ON bead_watch_new(sla_deadline)")
            await db.execute("CREATE INDEX idx_bead_watch_fenced ON bead_watch_new(fenced_at)")

            # Drop old table and rename new table
            await db.execute("DROP TABLE bead_watch")
            await db.execute("ALTER TABLE bead_watch_new RENAME TO bead_watch")

            await db.commit()
            logger.info("Migration complete: bead_watch.comment_high_water default is now -1")
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to migrate bead_watch.comment_high_water: {e}")
            raise

    @staticmethod
    async def _migrate_sessions_reformulation_count(db: aiosqlite.Connection) -> None:
        """Migrate sessions table to add reformulation_count column.

        Tracks re-formulation attempts per session to prevent infinite loops.
        """
        # Check if migration is needed by inspecting the sessions table schema
        async with db.execute("PRAGMA table_info(sessions)") as cur:
            session_cols = {row[1] for row in await cur.fetchall()}

        if "reformulation_count" in session_cols:
            # Already migrated
            return

        # Migration needed: add reformulation_count column
        logger.info("Migrating sessions table to add reformulation_count column")

        try:
            await db.execute(
                "ALTER TABLE sessions ADD COLUMN reformulation_count INTEGER DEFAULT 0"
            )
            logger.info("Migration complete: sessions.reformulation_count column added")
        except Exception as e:
            logger.error(f"Failed to migrate sessions.reformulation_count: {e}")
            raise

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

    async def get_reformulation_count(self, session_id: str) -> int:
        """Get the re-formulation attempt count for a session."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT reformulation_count FROM sessions WHERE id = ?",
                (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row["reformulation_count"] if row["reformulation_count"] else 0
                return 0

    async def increment_reformulation_count(self, session_id: str) -> int:
        """Increment the re-formulation attempt count for a session.

        Returns the new count.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # First get current count
            current_count = await self.get_reformulation_count(session_id)
            new_count = current_count + 1

            # Update the count
            await db.execute(
                "UPDATE sessions SET reformulation_count = ? WHERE id = ?",
                (new_count, session_id)
            )
            await db.commit()

            logger.info(f"Incremented reformulation_count for session {session_id} to {new_count}")
            return new_count

    async def reset_reformulation_count(self, session_id: str) -> None:
        """Reset the re-formulation attempt count for a session.

        Called when a valid bead is successfully created, allowing the session
        to attempt re-formulation again for future intents.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET reformulation_count = 0 WHERE id = ?",
                (session_id,)
            )
            await db.commit()
            logger.info(f"Reset reformulation_count for session {session_id}")

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
            # dispatch_timings is keyed by the intent *thread* id
            # (routed_intent.intent_id), which differs from intents.id for the
            # current router path (see the table comment in SCHEMA_SQL), so this
            # is best-effort: it catches rows keyed by the store intent id, while
            # thread-keyd rows survive until the thread id is known to the caller.
            await db.execute(
                "DELETE FROM dispatch_timings WHERE intent_id IN "
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
        lookup_kind: str | None = None,
        topic_id: str | None = None,
    ) -> str:
        """Create a new intent and return its ID."""
        intent_id = str(uuid4())
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO intents
                   (id, utterance_id, session_id, project_slug, intent_type, lookup_kind, bead_ref, topic_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (intent_id, utterance_id, session_id, project_slug, intent_type, lookup_kind, bead_ref, topic_id, now)
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

    async def update_intent_type_and_status(
        self,
        intent_id: str,
        intent_type: str | None,
        status: str | None,
        resolved_at: int | None = None,
    ) -> None:
        """Update both intent type and status.

        Args:
            intent_id: The intent ID to update
            intent_type: New intent type (None = don't update)
            status: New status (None = don't update)
            resolved_at: Resolved timestamp (None = don't update unless status is resolved)
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Build update dynamically based on which values are provided
            updates = []
            params = []

            if intent_type is not None:
                updates.append("intent_type = ?")
                params.append(intent_type)

            if status is not None:
                updates.append("status = ?")
                params.append(status)
                # Auto-set resolved_at when status is resolved and resolved_at is None
                if resolved_at is None and status == "resolved":
                    resolved_at = int(datetime.now().timestamp())

            if resolved_at is not None:
                updates.append("resolved_at = ?")
                params.append(resolved_at)

            if not updates:
                # Nothing to update
                return

            params.append(intent_id)
            query = f"UPDATE intents SET {', '.join(updates)} WHERE id = ?"
            await db.execute(query, params)
            await db.commit()

    async def update_intent_topic(
        self,
        intent_id: str,
        topic_id: str | None,
    ) -> None:
        """Update intent's primary topic.

        Args:
            intent_id: The intent ID to update
            topic_id: New topic ID (None = don't update)
        """
        if topic_id is None:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE intents SET topic_id = ? WHERE id = ?",
                (topic_id, intent_id)
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

    async def get_intent_by_bead_ref(self, bead_ref: str) -> Optional[dict]:
        """Get intent by bead reference where status is tracked.

        Returns intent row WHERE bead_ref == <bead_ref> AND status IN
        ('pending', 'dispatched', 'stuck'), or None if no match.
        Used by the bead watcher to resolve closed beads to their
        original intent context.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM intents
                   WHERE bead_ref = ? AND status IN ('pending', 'dispatched', 'stuck')
                   LIMIT 1""",
                (bead_ref,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_intent(self, intent_id: str) -> Optional[dict]:
        """Get intent by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM intents WHERE id = ? LIMIT 1""",
                (intent_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    # Result operations
    async def create_result(
        self,
        intent_id: str | None,
        topic_id: str,
        session_id: str,
        summary: str,
        data: dict,
        urgency: str = "normal",
        result_type: str | None = None,
        card_fallback: bool = False,
        previous_result_id: str | None = None,
        diff_summary: str | None = None,
        diff_data: dict | None = None,
    ) -> str:
        """Create a new result and return its ID.

        Args:
            intent_id: Intent thread ID (None for monitoring-originated results)
            topic_id: Topic ID
            session_id: Session ID
            summary: Result summary
            data: Result data (dict)
            urgency: Urgency level
            result_type: Result type for component selection (e.g., 'monitoring:{project_slug}')
            card_fallback: True when no component matched (client renders built-in fallback card)
            previous_result_id: Previous result ID for diff
            diff_summary: Human-readable diff summary
            diff_data: Detailed diff data
        """
        import json
        result_id = str(uuid4())
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO results
                   (id, intent_id, topic_id, session_id, summary, data, urgency, result_type, card_fallback, created_at, surfaced_at,
                    previous_result_id, diff_summary, diff_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result_id, intent_id, topic_id, session_id, summary, json.dumps(data),
                    urgency, result_type, 1 if card_fallback else 0, now, now,
                    previous_result_id, diff_summary,
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

    async def get_results_for_intent(self, intent_id: str) -> list[dict]:
        """Get all results for a specific intent."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM results
                   WHERE intent_id = ?
                   ORDER BY created_at DESC""",
                (intent_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_all_results(self) -> list[dict]:
        """Get all results in the database."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM results ORDER BY created_at DESC"""
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def update_result_card_fallback(self, result_id: str, card_fallback: bool) -> None:
        """Update a result's card_fallback flag.

        Args:
            result_id: The result ID to update
            card_fallback: True if using generic fallback card, False if component rendered
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE results SET card_fallback = ? WHERE id = ?",
                (1 if card_fallback else 0, result_id)
            )
            await db.commit()

    async def delete_result(self, result_id: str, session_id: str) -> dict:
        """Delete a result by ID, ensuring it belongs to the specified session.

        Returns a dict with 'result_deleted' count (0 or 1).
        This provides session isolation - a result can only be deleted by its owning session.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Use WHERE session_id to ensure session isolation
            cursor = await db.execute(
                """DELETE FROM results WHERE id = ? AND session_id = ?""",
                (result_id, session_id)
            )
            await db.commit()
            return {"result_deleted": cursor.rowcount}

    # Card cache operations
    async def write_card_cache(
        self,
        result_id: str,
        component_id: str,
        layout_bucket: str,
        rendered_html: str,
    ) -> None:
        """Write rendered HTML to card cache.

        Stores pre-rendered HTML for a specific result/component/layout combination.
        Uses INSERT OR REPLACE to update existing cache entries.

        Args:
            result_id: The result ID
            component_id: The component ID that rendered this HTML
            layout_bucket: The layout bucket used for rendering
            rendered_html: The pre-rendered HTML content
        """
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO card_cache
                   (result_id, component_id, layout_bucket, rendered_html, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (result_id, component_id, layout_bucket, rendered_html, now)
            )
            await db.commit()

    async def get_card_cache(self, result_id: str) -> list[dict]:
        """Get all cached HTML entries for a result.

        Returns a list of cached entries, each containing:
        - result_id
        - component_id
        - layout_bucket
        - rendered_html
        - created_at

        Args:
            result_id: The result ID to fetch cache for

        Returns:
            List of cache entries (empty list if none found)
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT result_id, component_id, layout_bucket, rendered_html, created_at
                   FROM card_cache
                   WHERE result_id = ?
                   ORDER BY created_at DESC""",
                (result_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_card_cache_entry(
        self,
        result_id: str,
        component_id: str,
        layout_bucket: str,
    ) -> Optional[dict]:
        """Get a specific cached HTML entry.

        Returns the cache entry matching all three keys, or None if not found.

        Args:
            result_id: The result ID
            component_id: The component ID
            layout_bucket: The layout bucket

        Returns:
            Cache entry dict or None
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT result_id, component_id, layout_bucket, rendered_html, created_at
                   FROM card_cache
                   WHERE result_id = ? AND component_id = ? AND layout_bucket = ?""",
                (result_id, component_id, layout_bucket)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def invalidate_card_cache(self, result_id: str) -> int:
        """Invalidate all cache entries for a result.

        Deletes all cached HTML for the given result_id.

        Args:
            result_id: The result ID to invalidate cache for

        Returns:
            Number of entries deleted
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM card_cache WHERE result_id = ?",
                (result_id,)
            )
            await db.commit()
            return cursor.rowcount

    async def invalidate_card_cache_entry(
        self,
        result_id: str,
        component_id: str,
        layout_bucket: str,
    ) -> int:
        """Invalidate a specific cache entry.

        Deletes the cache entry matching all three keys.

        Args:
            result_id: The result ID
            component_id: The component ID
            layout_bucket: The layout bucket

        Returns:
            Number of entries deleted (0 or 1)
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """DELETE FROM card_cache
                   WHERE result_id = ? AND component_id = ? AND layout_bucket = ?""",
                (result_id, component_id, layout_bucket)
            )
            await db.commit()
            return cursor.rowcount

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
        scope: str = "session",
    ) -> tuple[str, bool]:
        """Find existing topic by label, scope, and session, or create new. Returns (topic_id, created).

        Args:
            label: Topic label
            session_id: Current session ID (used for session-scoped topics)
            topic_type: Topic type ('project', 'research', 'personal', 'exception', 'compound', 'adhoc')
            project_slugs: List of project slugs for this topic
            scope: Topic scope ('session', 'cross-session', 'global')

        For cross-session topics (scope='cross-session'), finds by label regardless of session.
        For session-scoped topics, finds by label within the current session.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            if scope == "cross-session":
                # For cross-session topics, find by label with cross-session scope
                async with db.execute(
                    """SELECT id FROM topics
                       WHERE label = ? AND scope = 'cross-session' AND session_id IS NULL AND archived_at IS NULL
                       LIMIT 1""",
                    (label,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row[0], False
            else:
                # For session-scoped topics, find by label within the current session
                async with db.execute(
                    """SELECT id FROM topics
                       WHERE label = ? AND scope = 'session' AND session_id = ? AND archived_at IS NULL
                       LIMIT 1""",
                    (label, session_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row[0], False

        # Create new topic with specified scope
        # Cross-session topics have session_id = NULL
        topic_session_id = None if scope == "cross-session" else session_id
        topic_id = await self.create_topic(label, topic_type, project_slugs, scope, topic_session_id)
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

    async def get_previous_result_for_diff(
        self,
        topic_id: str,
        result_type: str,
    ) -> Optional[dict]:
        """
        Get the previous result for diff computation on a (topic_id, result_type) pair.

        Cross-session search: finds the most recent result for the same topic and result_type,
        regardless of session. This supports pure lineage tracking for previous_result_id.

        The diff strip rendering is session-scoped (handled by callers) - this method only
        provides the lineage reference.

        Args:
            topic_id: The topic ID to search within
            result_type: The result type to match (e.g., 'status:pbx-web', 'lookup:logs:whisper-stt')

        Returns:
            The most recent result dict matching the topic and result_type, or None if no match
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM results
                   WHERE topic_id = ? AND result_type = ?
                   ORDER BY created_at DESC, id DESC
                   LIMIT 1""",
                (topic_id, result_type)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_latest_results_by_type(
        self, session_id: str
    ) -> list[dict]:
        """
        Get the latest result for each (topic_id, result_type) pair in a session.

        Returns one result per distinct result_type per topic, enabling
        granular canvas rendering where different result_types on the same
        topic coexist (e.g., status + brainstorm cards).

        Session-scoped display: results are filtered by session_id, so a fresh
        session shows only its own results, not results from previous sessions
        even on cross-session topics. The topic itself may be cross-session,
        but result display is always session-scoped.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT ranked.* FROM (
                    SELECT r.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY r.topic_id, r.result_type
                            ORDER BY r.created_at DESC
                        ) as rn
                    FROM results r
                    JOIN topics t ON r.topic_id = t.id
                    WHERE (t.session_id = ? OR t.scope IN ('cross-session', 'global'))
                      AND t.archived_at IS NULL
                      AND r.session_id = ?
                ) ranked
                WHERE rn = 1
                ORDER BY
                    ranked.topic_id,
                    ranked.created_at DESC""",
                (session_id, session_id)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

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

    # Dispatch timing operations (Latency Budget & Instrumentation)
    async def record_dispatch_timings(
        self,
        intent_id: str,
        **fields: int | None,
    ) -> None:
        """Persist per-stage timings for one dispatch intent thread.

        Upserts the row so the same intent_id can be written incrementally:
        process_intent() records the server-side stages it measures, the
        dispatch caller records sse_emit_ms after the SSE broadcast, and the
        /api/v1/timings endpoint records client-reported stt_ms/first_render_ms.
        Only columns passed with a non-NULL value are touched, so a later
        partial write never clobbers a stage an earlier write already set.
        ``created_at`` is stamped once on insert and never overwritten.
        """
        cols = {
            k: v for k, v in fields.items()
            if k in DISPATCH_TIMING_COLUMNS and v is not None
        }
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            # Ensure the row exists (created_at set once, on first write).
            await db.execute(
                "INSERT OR IGNORE INTO dispatch_timings (intent_id, created_at) VALUES (?, ?)",
                (intent_id, now),
            )
            if cols:
                set_clause = ", ".join(f"{c} = ?" for c in cols)
                params = [*cols.values(), intent_id]
                await db.execute(
                    f"UPDATE dispatch_timings SET {set_clause} WHERE intent_id = ?",
                    params,
                )
            await db.commit()

    async def get_dispatch_timings(self, intent_id: str) -> Optional[dict]:
        """Get the dispatch_timings row for one intent thread, or None."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM dispatch_timings WHERE intent_id = ?",
                (intent_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_latency_percentiles(self, since: int | None = None) -> dict:
        """Aggregate p50/p95 per stage across dispatch_timings rows.

        Returns ``{stage: {"p50": ms, "p95": ms, "count": n}}`` for every stage
        that has at least one non-NULL value. NULLs are skipped per stage (so a
        stage not yet captured for any dispatch simply doesn't appear). Pass
        ``since`` (a unix timestamp) to window to recent dispatches only — the
        latency-baseline bead consumes the un-windowed call to fill the plan's
        global Measured p50/p95 columns.

        Percentiles are nearest-rank (ceil(q/100 * n)), computed in Python
        because SQLite has no built-in percentile.
        """
        from ..instrument.timings import percentiles

        result: dict[str, dict] = {}
        async with aiosqlite.connect(self.db_path) as db:
            for stage in DISPATCH_TIMING_COLUMNS:
                if since is not None:
                    query = (
                        f"SELECT {stage} FROM dispatch_timings "
                        f"WHERE {stage} IS NOT NULL AND created_at >= ? "
                        f"ORDER BY {stage}"
                    )
                    params: tuple = (since,)
                else:
                    query = (
                        f"SELECT {stage} FROM dispatch_timings "
                        f"WHERE {stage} IS NOT NULL ORDER BY {stage}"
                    )
                    params = ()
                async with db.execute(query, params) as cursor:
                    values = [row[0] for row in await cursor.fetchall()]
                if not values:
                    continue
                pct = percentiles(values, qs=(50, 95))
                result[stage] = {
                    "p50": pct[50],
                    "p95": pct[95],
                    "count": len(values),
                }
        return result

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
        result_type: str | None = None,
        card_fallback: bool = False,
    ) -> tuple[str, bool]:
        """
        Create a new result with session-scoped diff computation.

        Returns (result_id, has_diff).

        Implements the plan's topic scope vs. session scope requirements:
        - previous_result_id is pure lineage (set from cross-session result of same type)
        - Diff strip renders ONLY when previous result is from the current session
        - A status result never diffs against a brainstorm result (different result_type)

        Args:
            intent_id: Intent thread ID
            topic_id: Topic ID
            session_id: Session ID
            summary: Result summary
            data: Result data (dict)
            urgency: Urgency level
            result_type: Result type for component selection (e.g., 'status:pbx-web')
            card_fallback: True when no component matched (client renders built-in fallback card)
        """
        from ..diff.engine import get_diff_engine

        # Get previous result for this (topic_id, result_type) pair
        # Cross-session search for lineage tracking
        previous_result = None
        if result_type:
            previous_result = await self.get_previous_result_for_diff(topic_id, result_type)

        # Set previous_result_id for lineage (always set when found, cross-session)
        # This supports the plan's "pure lineage" requirement
        previous_result_id = previous_result["id"] if previous_result else None

        # Compute diff ONLY when previous result is from the CURRENT session
        # This ensures seed-run diffs are suppressed but in-session diffs work
        diff_summary = None
        diff_data = None
        has_diff = False

        if previous_result and previous_result.get("session_id") == session_id:
            diff_engine = get_diff_engine()

            # Parse previous result's data (it's stored as JSON string in DB)
            import json
            previous_data = json.loads(previous_result.get("data", "{}"))

            diff_result = await diff_engine.compute_diff(
                topic_id=topic_id,
                previous_result={"data": previous_data},
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

        # Create the result with diff data (or without if cross-session)
        result_id = await self.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=summary,
            data=data,
            urgency=urgency,
            result_type=result_type,
            card_fallback=card_fallback,
            previous_result_id=previous_result_id,
            diff_summary=diff_summary,
            diff_data=diff_data,
        )

        return result_id, has_diff

    # Bead watch operations (circuit breaker tracking)

    async def create_bead_watch(
        self,
        bead_ref: str,
        sla_hours: float | None = None,
        intent_type: str = "task-profile",
    ) -> None:
        """Create a bead watch row for circuit breaker tracking.

        Args:
            bead_ref: The bead ID to watch
            sla_hours: SLA in hours (defaults to intent type's SLA)
            intent_type: Intent type for SLA default lookup
        """
        from datetime import datetime
        import json

        # Resolve SLA deadline
        if sla_hours is None:
            sla_hours = DEFAULT_SLA_HOURS.get(intent_type, 6.0)
        now = int(datetime.now().timestamp())
        sla_deadline = int(now + (sla_hours * 3600))

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO bead_watch
                   (bead_ref, refusal_count, comment_high_water, sla_deadline, created_at)
                   VALUES (?, 0, -1, ?, ?)""",
                (bead_ref, sla_deadline, now),
            )
            await db.commit()

    async def get_bead_watch(self, bead_ref: str) -> Optional[dict]:
        """Get bead watch row by bead_ref."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bead_watch WHERE bead_ref = ?",
                (bead_ref,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_bead_watch_refusal(
        self,
        bead_ref: str,
        refusal_reason: str,
        comment_index: int,
        refusal_count_add: int = 1,
    ) -> None:
        """Update bead watch with a new refusal.

        Args:
            bead_ref: The bead ID
            refusal_reason: The refusal reason from REFUSED: comment
            comment_index: The comment high-water mark to advance to
            refusal_count_add: Number of refusals to add (default 1, but can be higher
                              if multiple refusals are found in one tick)
        """
        from datetime import datetime

        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            # Increment refusal_count by refusal_count_add, update last_refusal_*, advance high-water
            await db.execute(
                """UPDATE bead_watch
                   SET refusal_count = refusal_count + ?,
                       last_refusal_reason = ?,
                       last_refusal_at = ?,
                       comment_high_water = ?
                   WHERE bead_ref = ?""",
                (refusal_count_add, refusal_reason, now, comment_index, bead_ref),
            )
            await db.commit()

    async def update_bead_watch_comment_high_water(
        self,
        bead_ref: str,
        comment_index: int,
    ) -> None:
        """Update only the comment high-water mark (for non-refusal comments)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE bead_watch SET comment_high_water = ? WHERE bead_ref = ?",
                (comment_index, bead_ref),
            )
            await db.commit()

    async def fence_bead(self, bead_ref: str) -> None:
        """Mark a bead as fenced (circuit breaker tripped).

        Sets fenced_at timestamp. Caller is responsible for:
        - Running `bf update --status blocked` on the bead
        - Setting intent status to 'stuck'
        - Creating a stuck card
        """
        from datetime import datetime

        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE bead_watch SET fenced_at = ? WHERE bead_ref = ?",
                (now, bead_ref),
            )
            await db.commit()

    async def flag_sla(self, bead_ref: str) -> None:
        """Mark SLA as flagged (bead past its deadline)."""
        from datetime import datetime

        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE bead_watch SET sla_flagged_at = ? WHERE bead_ref = ?",
                (now, bead_ref),
            )
            await db.commit()

    async def get_open_watched_beads(self) -> list[dict]:
        """Get all watched beads that are not yet fenced.

        Returns list of bead_ref, sla_deadline, refusal_count, etc.
        for all beads where fenced_at IS NULL.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM bead_watch
                   WHERE fenced_at IS NULL
                   ORDER BY created_at DESC""",
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_beads_past_sla(self) -> list[dict]:
        """Get all watched beads that have passed their SLA deadline but not yet flagged.

        Returns beads where sla_deadline < now AND sla_flagged_at IS NULL.
        """
        from datetime import datetime

        now = int(datetime.now().timestamp())
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM bead_watch
                   WHERE sla_deadline < ? AND sla_flagged_at IS NULL
                   ORDER BY sla_deadline ASC""",
                (now,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_beads_needing_fencing(self) -> list[dict]:
        """Get beads that meet fencing criteria but are not yet fenced.

        Returns beads where either:
        - refusal_count >= 3 (CIRCUIT_BREAKER_REFUSAL_THRESHOLD)
        - OR age > 24h without progress (CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS)

        Age is computed as: (now - last_refusal_at) > threshold when there are refusals,
        or (now - created_at) > threshold when there are no refusals yet.
        """
        from datetime import datetime

        now = int(datetime.now().timestamp())
        age_threshold_seconds = int(CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS * 3600)
        refusal_threshold = CIRCUIT_BREAKER_REFUSAL_THRESHOLD

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Beads needing fencing based on refusal count OR age
            # Age logic: if last_refusal_at is set, check time since last refusal;
            # otherwise check time since creation.
            async with db.execute(
                f"""SELECT * FROM bead_watch
                   WHERE fenced_at IS NULL
                     AND (
                       refusal_count >= {refusal_threshold}
                       OR (
                         CASE
                           WHEN last_refusal_at IS NOT NULL
                           THEN ({now} - last_refusal_at) > {age_threshold_seconds}
                           ELSE ({now} - created_at) > {age_threshold_seconds}
                         END
                       )
                     )
                   ORDER BY created_at DESC""",
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def delete_bead_watch(self, bead_ref: str) -> None:
        """Delete a bead watch row (when bead is closed/resolved)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM bead_watch WHERE bead_ref = ?",
                (bead_ref,),
            )
            await db.commit()

    async def get_fenced_beads_for_session(self, session_id: str) -> list[dict]:
        """Get all fenced beads for a session.

        Returns bead_watch rows where fenced_at IS NOT NULL and the bead
        is associated with an intent from the given session.

        Args:
            session_id: The session ID to filter by

        Returns:
            List of fenced bead_watch rows with intent context
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT bw.*, i.id as intent_id, i.topic_id, i.project_slug
                   FROM bead_watch bw
                   INNER JOIN intents i ON i.bead_ref = bw.bead_ref
                   WHERE i.session_id = ? AND bw.fenced_at IS NOT NULL
                   ORDER BY bw.fenced_at DESC""",
                (session_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_pending_approval(
        self,
        intent_id: str,
        session_id: str,
        bead_body: str,
        bead_type: str,
        validation_result: dict,
        utterance: str,
        project_slug: str | None = None,
        topic_id: str | None = None,
        expires_seconds: int = 3600,
    ) -> str:
        """Create a pending bead approval request.

        Args:
            intent_id: The intent that triggered this approval
            session_id: The session for this approval
            bead_body: The bead body awaiting approval
            bead_type: The bead type (action, self_modification, etc.)
            validation_result: The validation result as a dict
            utterance: Original user utterance
            project_slug: Optional project slug
            topic_id: Optional topic ID
            expires_seconds: Seconds until approval expires (default 1 hour)

        Returns:
            The approval ID
        """
        approval_id = str(uuid4())
        now = int(datetime.now().timestamp())
        expires_at = now + expires_seconds

        import json
        validation_json = json.dumps(validation_result)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO pending_bead_approvals
                   (id, intent_id, session_id, bead_body, bead_type, validation_result,
                    utterance, project_slug, topic_id, created_at, expires_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval_id,
                    intent_id,
                    session_id,
                    bead_body,
                    bead_type,
                    validation_json,
                    utterance,
                    project_slug,
                    topic_id,
                    now,
                    expires_at,
                    "pending",
                ),
            )
            await db.commit()

        return approval_id

    async def get_pending_approval(self, approval_id: str) -> Optional[dict]:
        """Get a pending approval by ID.

        Args:
            approval_id: The approval ID

        Returns:
            The approval data or None if not found
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM pending_bead_approvals WHERE id = ?""",
                (approval_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None

    async def get_pending_approvals_for_session(self, session_id: str) -> list[dict]:
        """Get all pending approvals for a session.

        Args:
            session_id: The session ID

        Returns:
            List of pending approval data
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM pending_bead_approvals
                   WHERE session_id = ? AND status = 'pending' AND expires_at > ?
                   ORDER BY created_at DESC""",
                (session_id, int(datetime.now().timestamp())),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def update_approval_status(self, approval_id: str, status: str) -> None:
        """Update the status of a pending approval.

        Args:
            approval_id: The approval ID
            status: New status ('approved' or 'rejected')
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE pending_bead_approvals SET status = ? WHERE id = ?",
                (status, approval_id),
            )
            await db.commit()

    async def delete_expired_approvals(self) -> int:
        """Delete expired pending approvals.

        Returns:
            Number of approvals deleted
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """DELETE FROM pending_bead_approvals
                   WHERE expires_at <= ?""",
                (int(datetime.now().timestamp()),),
            )
            await db.commit()
            return cursor.rowcount


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
