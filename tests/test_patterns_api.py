"""
Tests for POST /api/v1/patterns endpoint.

Tests component usage pattern recording API including:
- Valid pattern data acceptance
- Upsert behavior (new and existing patterns)
- Input validation
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
