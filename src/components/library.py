"""
Component Library for aide-de-camp.

Manages UI components, their versions, and the card cache.
Provides component selection and rendering services.
"""

import sqlite3
import json
import time
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Component:
    """A UI component template."""
    id: str
    name: str
    description: str
    html_template: str
    version: int
    created_at: int
    last_used: Optional[int]
    usage_count: int


@dataclass
class ComponentVersion:
    """A specific version of a component."""
    component_id: str
    version: int
    html_template: str
    created_at: int
    change_note: Optional[str]


@dataclass
class CachedCard:
    """A cached rendered card."""
    result_id: str
    component_id: str
    component_version: int
    layout_bucket: str
    rendered_html: str
    created_at: int


class ComponentLibrary:
    """
    Manages the component library database.

    Provides:
    - Component storage and versioning
    - Card caching
    - Component selection based on result types
    - Cache invalidation
    """

    LAYOUT_BUCKETS = ['compact', 'normal', 'expanded']

    def __init__(self, db_path: str):
        """
        Initialize the component library.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create database connection with WAL mode."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _ensure_schema(self):
        """Ensure database schema exists."""
        schema_path = Path(__file__).parent.parent.parent / 'data' / 'schema.sql'
        if schema_path.exists():
            with open(schema_path) as f:
                schema = f.read()
            conn = self._get_conn()
            conn.executescript(schema)
            conn.commit()

    def create_component(
        self,
        name: str,
        description: str,
        html_template: str,
        change_note: str = "Initial version"
    ) -> Component:
        """
        Create a new component.

        Args:
            name: Component name (e.g., "pod-status")
            description: What result types this handles
            html_template: The HTML/CSS template
            change_note: Reason for this version

        Returns:
            The created Component
        """
        import uuid
        component_id = f"comp-{uuid.uuid4().hex[:12]}"
        created_at = int(time.time())

        conn = self._get_conn()

        # Create component
        conn.execute(
            """
            INSERT INTO components (id, name, description, html_template, version, created_at, usage_count)
            VALUES (?, ?, ?, ?, 1, ?, 0)
            """,
            (component_id, name, description, html_template, created_at)
        )

        # Create version history
        conn.execute(
            """
            INSERT INTO component_versions (component_id, version, html_template, created_at, change_note)
            VALUES (?, 1, ?, ?, ?)
            """,
            (component_id, html_template, created_at, change_note)
        )

        conn.commit()

        return Component(
            id=component_id,
            name=name,
            description=description,
            html_template=html_template,
            version=1,
            created_at=created_at,
            last_used=None,
            usage_count=0
        )

    def get_component(self, component_id: str) -> Optional[Component]:
        """Get a component by ID."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, name, description, html_template, version, created_at, last_used, usage_count "
            "FROM components WHERE id = ?",
            (component_id,)
        ).fetchone()

        if row:
            return Component(
                id=row[0],
                name=row[1],
                description=row[2],
                html_template=row[3],
                version=row[4],
                created_at=row[5],
                last_used=row[6],
                usage_count=row[7]
            )
        return None

    def find_best_component(
        self,
        result_type: str,
        result_data: Dict[str, Any]
    ) -> Optional[Component]:
        """
        Find the best-fit component for a result.

        Uses semantic matching on component descriptions and
        historical usage patterns.

        Args:
            result_type: The type of result (e.g., "pod-status")
            result_data: The structured result data

        Returns:
            The best matching Component, or None if no good match
        """
        conn = self._get_conn()

        # First, check usage patterns for this exact result type
        pattern_row = conn.execute(
            """
            SELECT component_id, match_score
            FROM component_usage_patterns
            WHERE result_type = ?
            ORDER BY match_score DESC, sample_count DESC
            LIMIT 1
            """,
            (result_type,)
        ).fetchone()

        if pattern_row and pattern_row[1] >= 0.7:  # 70% confidence threshold
            component = self.get_component(pattern_row[0])
            if component:
                return component

        # Fallback: semantic search on component descriptions
        # (In production, this would use embeddings. For now, use simple keyword match)
        components = conn.execute(
            "SELECT id, name, description FROM components WHERE usage_count > 0"
        ).fetchall()

        best_component = None
        best_score = 0.0

        for comp_id, name, description in components:
            score = self._semantic_score(result_type, name, description)
            if score > best_score:
                best_score = score
                best_component = self.get_component(comp_id)

        # Only return if we have reasonable confidence
        if best_score >= 0.5:
            return best_component

        return None

    def select_component_for_result_type(
        self,
        result_type: str,
        match_threshold: float = 0.7,
    ) -> Optional[Component]:
        """Deterministic hot-path selection — the dispatch card selector.

        Returns the highest-``match_score`` component mapped to ``result_type``
        in ``component_usage_patterns`` whose score clears ``match_threshold``,
        or None. No LLM, no semantic fallback, no generation (plan: The Hot Path
        / UI-Regen Agent — "highest match_score in component_usage_patterns for
        the result_type, no LLM call"). A None return is the signal that the
        result must fall to the built-in generic fallback card.

        Distinct from :meth:`find_best_component`, which the *async* UI-regen
        agent uses to steward the library (it may fall back to semantic search
        and ultimately generate a new component). The hot path must never do
        either — it only reads the recorded mappings.
        """
        conn = self._get_conn()
        pattern_row = conn.execute(
            """
            SELECT component_id, match_score
            FROM component_usage_patterns
            WHERE result_type = ? AND match_score >= ?
            ORDER BY match_score DESC, sample_count DESC
            LIMIT 1
            """,
            (result_type, match_threshold),
        ).fetchone()

        if not pattern_row:
            return None

        return self.get_component(pattern_row[0])

    def _semantic_score(self, result_type: str, comp_name: str, comp_description: str) -> float:
        """
        Calculate semantic match score.

        Simple keyword-based scoring. In production, use embeddings.
        """
        result_type_lower = result_type.lower()
        comp_name_lower = comp_name.lower()
        comp_desc_lower = comp_description.lower()

        score = 0.0

        # Exact name match
        if result_type_lower == comp_name_lower:
            return 1.0

        # Name contains result type
        if result_type_lower in comp_name_lower:
            score += 0.7

        # Description contains keywords from result type
        result_keywords = result_type_lower.replace('-', ' ').split()
        for keyword in result_keywords:
            if keyword in comp_desc_lower:
                score += 0.1

        return min(score, 1.0)

    def update_component(
        self,
        component_id: str,
        html_template: str,
        change_note: str
    ) -> Optional[Component]:
        """
        Update a component to a new version.

        Invalidates all cached cards using this component.

        Args:
            component_id: The component to update
            html_template: The new template
            change_note: Why this change was made

        Returns:
            The updated Component, or None if not found
        """
        conn = self._get_conn()

        # Get current version
        row = conn.execute(
            "SELECT version FROM components WHERE id = ?",
            (component_id,)
        ).fetchone()

        if not row:
            return None

        new_version = row[0] + 1
        now = int(time.time())

        # Update component
        conn.execute(
            """
            UPDATE components
            SET html_template = ?, version = ?, last_used = ?
            WHERE id = ?
            """,
            (html_template, new_version, now, component_id)
        )

        # Add version history
        conn.execute(
            """
            INSERT INTO component_versions (component_id, version, html_template, created_at, change_note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (component_id, new_version, html_template, now, change_note)
        )

        # Invalidate cached cards
        conn.execute(
            "DELETE FROM card_cache WHERE component_id = ?",
            (component_id,)
        )

        conn.commit()

        return self.get_component(component_id)

    def cache_card(
        self,
        result_id: str,
        component_id: str,
        component_version: int,
        layout_bucket: str,
        rendered_html: str
    ):
        """
        Cache a rendered card.

        Args:
            result_id: The result this card renders
            component_id: The component used
            component_version: The component version
            layout_bucket: The layout bucket
            rendered_html: The rendered HTML
        """
        if layout_bucket not in self.LAYOUT_BUCKETS:
            raise ValueError(f"Invalid layout bucket: {layout_bucket}")

        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO card_cache
            (result_id, component_id, component_version, layout_bucket, rendered_html, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (result_id, component_id, component_version, layout_bucket, rendered_html, int(time.time()))
        )
        conn.commit()

        # Update component usage stats
        conn.execute(
            """
            UPDATE components
            SET usage_count = usage_count + 1, last_used = ?
            WHERE id = ?
            """,
            (int(time.time()), component_id)
        )
        conn.commit()

    def get_cached_card(
        self,
        result_id: str,
        component_id: str,
        layout_bucket: str
    ) -> Optional[CachedCard]:
        """Get a cached card if it exists and is up-to-date."""
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT result_id, component_id, component_version, layout_bucket, rendered_html, created_at
            FROM card_cache
            WHERE result_id = ? AND component_id = ? AND layout_bucket = ?
            """,
            (result_id, component_id, layout_bucket)
        ).fetchone()

        if row:
            return CachedCard(
                result_id=row[0],
                component_id=row[1],
                component_version=row[2],
                layout_bucket=row[3],
                rendered_html=row[4],
                created_at=row[5]
            )
        return None

    def invalidate_result(self, result_id: str):
        """Invalidate all cached cards for a result."""
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM card_cache WHERE result_id = ?",
            (result_id,)
        )
        conn.commit()

    def record_usage_pattern(
        self,
        component_id: str,
        result_type: str,
        match_score: float
    ):
        """
        Record a component usage pattern for future matching.

        Args:
            component_id: The component that was used
            result_type: The type of result it rendered
            match_score: How well it matched (0-1)
        """
        conn = self._get_conn()
        now = int(time.time())

        conn.execute(
            """
            INSERT INTO component_usage_patterns (component_id, result_type, match_score, sample_count, last_matched)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(component_id, result_type)
            DO UPDATE SET
                match_score = (match_score * sample_count + ?) / (sample_count + 1),
                sample_count = sample_count + 1,
                last_matched = ?
            """,
            (component_id, result_type, match_score, now, match_score, now)
        )
        conn.commit()

    def list_components(self, limit: int = 50) -> List[Component]:
        """List all components, ordered by usage."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT id, name, description, html_template, version, created_at, last_used, usage_count
            FROM components
            ORDER BY usage_count DESC, last_used DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

        return [
            Component(
                id=row[0],
                name=row[1],
                description=row[2],
                html_template=row[3],
                version=row[4],
                created_at=row[5],
                last_used=row[6],
                usage_count=row[7]
            )
            for row in rows
        ]

    def get_component_history(self, component_id: str) -> List[ComponentVersion]:
        """Get version history for a component."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT component_id, version, html_template, created_at, change_note
            FROM component_versions
            WHERE component_id = ?
            ORDER BY version DESC
            """,
            (component_id,)
        ).fetchone()

        return [
            ComponentVersion(
                component_id=row[0],
                version=row[1],
                html_template=row[2],
                created_at=row[3],
                change_note=row[4]
            )
            for row in rows
        ]

    def rollback_component(self, component_id: str, to_version: int) -> Optional[Component]:
        """
        Rollback a component to a previous version.

        Args:
            component_id: The component to rollback
            to_version: The version to rollback to

        Returns:
            The rolled-back Component, or None if not found
        """
        conn = self._get_conn()

        # Get the target version
        row = conn.execute(
            """
            SELECT html_template FROM component_versions
            WHERE component_id = ? AND version = ?
            """,
            (component_id, to_version)
        ).fetchone()

        if not row:
            return None

        html_template = row[0]

        # Rollback by updating with the old template as a new version
        return self.update_component(
            component_id,
            html_template,
            f"Rollback to version {to_version}"
        )

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# Singleton instance for the application
_library_instance: Optional[ComponentLibrary] = None


def get_library(db_path: str = '/home/coding/aide-de-camp/data/components.db') -> ComponentLibrary:
    """Get or create the component library singleton."""
    global _library_instance
    if _library_instance is None:
        _library_instance = ComponentLibrary(db_path)
    return _library_instance
