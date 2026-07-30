"""
Tests for POST /api/v1/patterns and GET /api/v1/patterns endpoints.

Tests component usage pattern recording and retrieval API including:
- Valid pattern data acceptance
- Upsert behavior (new and existing patterns)
- Input validation
- Pattern retrieval by result_type
- Proper error handling for missing data
- Ordering by match_score DESC
"""

import pytest
import sqlite3
import uuid
from pathlib import Path
from httpx import AsyncClient, ConnectError


# Path to the actual components.db used by the running server
COMPONENTS_DB = Path("/home/coding/aide-de-camp/data/components.db")


def is_server_running() -> bool:
    """Check if the ADC server is running."""
    import httpx

    try:
        response = httpx.get("http://localhost:8000/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


# Skip all tests if server is not running
pytestmark = pytest.mark.skipif(
    not is_server_running(),
    reason="ADC server is not running on localhost:8000"
)


def cleanup_test_pattern(result_type: str, component_id: str, layout_bucket: str):
    """Remove a test pattern from the database."""
    if not COMPONENTS_DB.exists():
        return

    conn = sqlite3.connect(str(COMPONENTS_DB))
    conn.execute(
        "DELETE FROM component_usage_patterns "
        "WHERE result_type = ? AND component_id = ? AND layout_bucket = ?",
        (result_type, component_id, layout_bucket)
    )
    conn.commit()
    conn.close()


@pytest.fixture
def test_component():
    """Get or create a test component for pattern recording tests."""
    conn = sqlite3.connect(str(COMPONENTS_DB))

    # Try to find an existing test component
    row = conn.execute(
        "SELECT id, name FROM components WHERE name LIKE 'test-pattern-component-%' LIMIT 1"
    ).fetchone()

    if row:
        component_id = row[0]
        conn.close()
        return component_id

    # Create a new test component
    import time
    component_id = f"comp-{uuid.uuid4().hex[:12]}"
    created_at = int(time.time())

    conn.execute(
        """
        INSERT INTO components (id, name, description, html_template, version, created_at, usage_count)
        VALUES (?, ?, ?, ?, 1, ?, 0)
        """,
        (component_id, f"test-pattern-component-{component_id[:8]}", "Test component for pattern recording", "<div>Test</div>", created_at)
    )

    # Create version history
    conn.execute(
        """
        INSERT INTO component_versions (component_id, version, html_template, created_at, change_note)
        VALUES (?, 1, ?, ?, ?)
        """,
        (component_id, "<div>Test</div>", created_at, "Initial version")
    )

    conn.commit()
    conn.close()

    return component_id


@pytest.mark.asyncio
async def test_patterns_api_accepts_valid_data(async_client: AsyncClient, test_component: str):
    """Test that the endpoint accepts valid pattern data."""
    result_type = "test-pod-status-valid"
    layout_bucket = "normal"

    try:
        response = await async_client.post(
            "/api/v1/patterns",
            json={
                "result_type": result_type,
                "component_id": test_component,
                "layout_bucket": layout_bucket,
                "match_score": 0.85
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["pattern"]["result_type"] == result_type
        assert data["pattern"]["component_id"] == test_component
        assert data["pattern"]["layout_bucket"] == layout_bucket
        assert data["pattern"]["match_score"] == 0.85
    finally:
        cleanup_test_pattern(result_type, test_component, layout_bucket)


@pytest.mark.asyncio
async def test_patterns_api_upsert_new_pattern(async_client: AsyncClient, test_component: str):
    """Test upsert behavior for a new pattern (insert)."""
    result_type = "test-deployment-status-new"
    layout_bucket = "compact"

    try:
        # Ensure pattern doesn't exist
        cleanup_test_pattern(result_type, test_component, layout_bucket)

        # Record a new pattern
        response = await async_client.post(
            "/api/v1/patterns",
            json={
                "result_type": result_type,
                "component_id": test_component,
                "layout_bucket": layout_bucket,
                "match_score": 0.75
            }
        )

        assert response.status_code == 200

        # Verify it was inserted into the database
        conn = sqlite3.connect(str(COMPONENTS_DB))
        row = conn.execute(
            "SELECT result_type, component_id, layout_bucket, match_score, sample_count "
            "FROM component_usage_patterns "
            "WHERE result_type = ? AND component_id = ? AND layout_bucket = ?",
            (result_type, test_component, layout_bucket)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == result_type
        assert row[1] == test_component
        assert row[2] == layout_bucket
        assert row[3] == 0.75
        assert row[4] == 1  # sample_count starts at 1
    finally:
        cleanup_test_pattern(result_type, test_component, layout_bucket)


@pytest.mark.asyncio
async def test_patterns_api_upsert_existing_pattern(async_client: AsyncClient, test_component: str):
    """Test upsert behavior for an existing pattern (update)."""
    import time
    result_type = "test-service-status-upsert"
    layout_bucket = "normal"

    try:
        conn = sqlite3.connect(str(COMPONENTS_DB))
        initial_time = int(time.time()) - 1000

        # Insert initial pattern directly into database
        conn.execute(
            "INSERT OR REPLACE INTO component_usage_patterns "
            "(result_type, component_id, layout_bucket, match_score, sample_count, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (result_type, test_component, layout_bucket, 0.70, 3, initial_time)
        )
        conn.commit()
        conn.close()

        # Update the pattern via API
        response = await async_client.post(
            "/api/v1/patterns",
            json={
                "result_type": result_type,
                "component_id": test_component,
                "layout_bucket": layout_bucket,
                "match_score": 0.92
            }
        )

        assert response.status_code == 200

        # Verify the pattern was updated
        conn = sqlite3.connect(str(COMPONENTS_DB))
        row = conn.execute(
            "SELECT result_type, component_id, layout_bucket, match_score, sample_count, updated_at "
            "FROM component_usage_patterns "
            "WHERE result_type = ? AND component_id = ? AND layout_bucket = ?",
            (result_type, test_component, layout_bucket)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == result_type
        assert row[1] == test_component
        assert row[2] == layout_bucket
        # Match score should be updated (averaged with previous value)
        assert 0.70 < row[3] <= 0.92
        # Sample count should be incremented
        assert row[4] == 4
        # Updated at should be more recent
        assert row[5] > initial_time
    finally:
        cleanup_test_pattern(result_type, test_component, layout_bucket)


@pytest.mark.asyncio
async def test_patterns_api_validation_missing_required_fields(async_client: AsyncClient):
    """Test input validation rejects missing required fields."""
    import json

    # Missing result_type - FastAPI returns 422 for Pydantic validation errors
    response = await async_client.post(
        "/api/v1/patterns",
        json={
            "component_id": "comp-123abc",
            "layout_bucket": "normal",
            "match_score": 0.85
        }
    )
    assert response.status_code == 422
    # Pydantic error detail includes "field required"
    error_detail = response.json()["detail"]
    assert any("result_type" in str(err).lower() and "required" in str(err).lower() for err in error_detail)

    # Missing component_id - FastAPI returns 422 for Pydantic validation errors
    response = await async_client.post(
        "/api/v1/patterns",
        json={
            "result_type": "pod-status",
            "layout_bucket": "normal",
            "match_score": 0.85
        }
    )
    assert response.status_code == 422
    error_detail = response.json()["detail"]
    assert any("component_id" in str(err).lower() and "required" in str(err).lower() for err in error_detail)


@pytest.mark.asyncio
async def test_patterns_api_validation_invalid_match_score(async_client: AsyncClient, test_component: str):
    """Test input validation rejects invalid match_score values."""

    # Match score > 1.0
    response = await async_client.post(
        "/api/v1/patterns",
        json={
            "result_type": "pod-status",
            "component_id": test_component,
            "layout_bucket": "normal",
            "match_score": 1.5
        }
    )
    assert response.status_code == 400
    assert "match_score must be between 0.0 and 1.0" in response.json()["error"]

    # Match score < 0.0
    response = await async_client.post(
        "/api/v1/patterns",
        json={
            "result_type": "pod-status",
            "component_id": test_component,
            "layout_bucket": "normal",
            "match_score": -0.1
        }
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_patterns_api_validation_invalid_layout_bucket(async_client: AsyncClient, test_component: str):
    """Test input validation rejects invalid layout_bucket values."""

    # Invalid layout bucket
    response = await async_client.post(
        "/api/v1/patterns",
        json={
            "result_type": "pod-status",
            "component_id": test_component,
            "layout_bucket": "invalid",
            "match_score": 0.85
        }
    )
    assert response.status_code == 400
    assert "layout_bucket must be one of" in response.json()["error"]


@pytest.mark.asyncio
async def test_patterns_api_valid_layout_buckets(async_client: AsyncClient, test_component: str):
    """Test that all valid layout buckets are accepted."""
    valid_buckets = ["compact", "normal", "expanded"]

    for bucket in valid_buckets:
        result_type = f"test-layout-{bucket}"
        try:
            response = await async_client.post(
                "/api/v1/patterns",
                json={
                    "result_type": result_type,
                    "component_id": test_component,
                    "layout_bucket": bucket,
                    "match_score": 0.80
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["pattern"]["layout_bucket"] == bucket
        finally:
            cleanup_test_pattern(result_type, test_component, bucket)


@pytest.mark.asyncio
async def test_patterns_api_edge_cases(async_client: AsyncClient, test_component: str):
    """Test edge cases for pattern recording."""
    result_type = "test-edge-case-boundary"
    layout_bucket = "normal"

    try:
        # Test match_score = 0.0 (boundary)
        response = await async_client.post(
            "/api/v1/patterns",
            json={
                "result_type": result_type + "-zero",
                "component_id": test_component,
                "layout_bucket": layout_bucket,
                "match_score": 0.0
            }
        )
        assert response.status_code == 200

        # Test match_score = 1.0 (boundary)
        response = await async_client.post(
            "/api/v1/patterns",
            json={
                "result_type": result_type + "-one",
                "component_id": test_component,
                "layout_bucket": layout_bucket,
                "match_score": 1.0
            }
        )
        assert response.status_code == 200
    finally:
        cleanup_test_pattern(result_type + "-zero", test_component, layout_bucket)
        cleanup_test_pattern(result_type + "-one", test_component, layout_bucket)


# =============================================================================
# GET /api/v1/patterns endpoint tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_patterns_by_result_type(async_client: AsyncClient, test_component: str):
    """Test GET /api/v1/patterns with a valid result_type returns patterns ordered by match_score DESC."""
    result_type_base = "test-get-patterns-retrieval"
    layout_bucket = "normal"

    try:
        # Create multiple patterns with different match scores
        patterns_to_create = [
            (result_type_base, test_component, layout_bucket, 0.65),
            (result_type_base, test_component, layout_bucket, 0.92),
            (result_type_base, test_component, layout_bucket, 0.78),
        ]

        for rt, comp_id, bucket, score in patterns_to_create:
            # Each pattern will have different layout_bucket to avoid primary key conflict
            # But for this test, we want same result_type, so we need to use different layout buckets
            # or we can just verify the last one persists (upsert behavior)
            response = await async_client.post(
                "/api/v1/patterns",
                json={
                    "result_type": rt,
                    "component_id": comp_id,
                    "layout_bucket": bucket,
                    "match_score": score
                }
            )
            assert response.status_code == 200

        # Create patterns with different result_types to test ordering
        result_type = result_type_base

        # Insert patterns with different match scores directly into DB
        # (to avoid upsert behavior and get multiple rows for same result_type)
        import time
        import uuid
        conn = sqlite3.connect(str(COMPONENTS_DB))

        # Create additional test components to get multiple patterns
        comp2_id = f"comp-{uuid.uuid4().hex[:12]}"
        created_at = int(time.time())
        conn.execute(
            """
            INSERT INTO components (id, name, description, html_template, version, created_at, usage_count)
            VALUES (?, ?, ?, ?, 1, ?, 0)
            """,
            (comp2_id, f"test-get-{comp2_id[:8]}", "Test component", "<div>Test</div>", created_at)
        )
        conn.execute(
            """
            INSERT INTO component_versions (component_id, version, html_template, created_at, change_note)
            VALUES (?, 1, ?, ?, ?)
            """,
            (comp2_id, "<div>Test</div>", created_at, "Initial version")
        )

        # Insert patterns with known match scores
        test_patterns = [
            (result_type, test_component, "normal", 0.75, 1, created_at),
            (result_type, comp2_id, "normal", 0.92, 1, created_at),
            (result_type, test_component, "compact", 0.65, 1, created_at),
        ]

        for pattern in test_patterns:
            conn.execute(
                """
                INSERT OR REPLACE INTO component_usage_patterns
                (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                pattern
            )
        conn.commit()
        conn.close()

        # Get patterns via API
        response = await async_client.get(
            f"/api/v1/patterns?result_type={result_type}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "patterns" in data
        assert "count" in data
        assert data["count"] == len(data["patterns"])
        assert data["count"] > 0

        # Verify patterns are ordered by match_score DESC
        patterns = data["patterns"]
        match_scores = [p["match_score"] for p in patterns]
        assert match_scores == sorted(match_scores, reverse=True), \
            f"Patterns should be ordered by match_score DESC, got: {match_scores}"

    finally:
        cleanup_test_pattern(result_type_base, test_component, "normal")
        cleanup_test_pattern(result_type_base, test_component, "compact")
        # Clean up comp2 if created
        if 'comp2_id' in locals():
            cleanup_test_pattern(result_type_base, comp2_id, "normal")


@pytest.mark.asyncio
async def test_get_patterns_missing_result_type(async_client: AsyncClient):
    """Test GET /api/v1/patterns without result_type returns 422 validation error."""
    response = await async_client.get("/api/v1/patterns")

    # FastAPI returns 422 for missing required query parameters
    assert response.status_code == 422
    error_detail = response.json()["detail"]
    assert any("result_type" in str(err).lower() and ("required" in str(err).lower() or "field" in str(err).lower()) for err in error_detail)


@pytest.mark.asyncio
async def test_get_patterns_no_patterns_found(async_client: AsyncClient):
    """Test GET /api/v1/patterns with non-existent result_type returns 404."""
    result_type = "test-nonexistent-result-type-xyz123"

    response = await async_client.get(f"/api/v1/patterns?result_type={result_type}")

    assert response.status_code == 404
    assert "error" in response.json()
    assert "No patterns found" in response.json()["error"]


@pytest.mark.asyncio
async def test_get_patterns_ordering_verification(async_client: AsyncClient, test_component: str):
    """Test that patterns are correctly ordered by match_score DESC."""
    result_type = "test-ordering-verification"
    import time
    import uuid

    try:
        conn = sqlite3.connect(str(COMPONENTS_DB))
        created_at = int(time.time())

        # Create additional test components
        comp_ids = []
        for i in range(5):
            comp_id = f"comp-{uuid.uuid4().hex[:12]}"
            comp_ids.append(comp_id)
            conn.execute(
                """
                INSERT INTO components (id, name, description, html_template, version, created_at, usage_count)
                VALUES (?, ?, ?, ?, 1, ?, 0)
                """,
                (comp_id, f"test-order-{comp_id[:8]}", "Test component", "<div>Test</div>", created_at)
            )
            conn.execute(
                """
                INSERT INTO component_versions (component_id, version, html_template, created_at, change_note)
                VALUES (?, 1, ?, ?, ?)
                """,
                (comp_id, "<div>Test</div>", created_at, "Initial version")
            )

        # Insert patterns with specific match scores (out of order)
        match_scores = [0.45, 0.92, 0.67, 0.88, 0.23]
        for comp_id, score in zip(comp_ids, match_scores):
            conn.execute(
                """
                INSERT INTO component_usage_patterns
                (result_type, component_id, layout_bucket, match_score, sample_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (result_type, comp_id, "normal", score, 1, created_at)
            )

        conn.commit()
        conn.close()

        # Get patterns via API
        response = await async_client.get(f"/api/v1/patterns?result_type={result_type}")

        assert response.status_code == 200
        data = response.json()
        patterns = data["patterns"]

        # Verify we got all patterns
        assert len(patterns) == 5

        # Verify ordering by match_score DESC
        returned_scores = [p["match_score"] for p in patterns]
        expected_scores = sorted(match_scores, reverse=True)
        assert returned_scores == expected_scores, \
            f"Expected scores {expected_scores}, got {returned_scores}"

    finally:
        conn = sqlite3.connect(str(COMPONENTS_DB))
        for comp_id in comp_ids:
            conn.execute(
                "DELETE FROM component_usage_patterns WHERE component_id = ?",
                (comp_id,)
            )
            conn.execute(
                "DELETE FROM components WHERE id = ?",
                (comp_id,)
            )
            conn.execute(
                "DELETE FROM component_versions WHERE component_id = ?",
                (comp_id,)
            )
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_get_patterns_empty_string_result_type(async_client: AsyncClient):
    """Test GET /api/v1/patterns with empty string result_type returns 404."""
    response = await async_client.get("/api/v1/patterns?result_type=")

    # Empty string is a valid query param value, but should find no patterns
    assert response.status_code == 404
    assert "error" in response.json()
