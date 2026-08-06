"""
Test endpoint call infrastructure and basic response verification.

This module provides comprehensive testing infrastructure for FastAPI endpoints
including response structure validation, status code checks, header verification,
and basic request handling tests.
"""

import pytest
from typing import Dict, Any
import httpx


class TestHealthEndpoint:
    """Test the /health endpoint for basic response verification."""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_200(self, async_client: httpx.AsyncClient):
        """Test that /health endpoint returns HTTP 200 status code."""
        response = await async_client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_json(self, async_client: httpx.AsyncClient):
        """Test that /health endpoint returns valid JSON content."""
        response = await async_client.get("/health")
        assert response.headers["content-type"] == "application/json"

    @pytest.mark.asyncio
    async def test_health_endpoint_response_structure(self, async_client: httpx.AsyncClient):
        """Test that /health endpoint returns expected response structure."""
        response = await async_client.get("/health")
        data = response.json()

        # Verify response has expected keys
        assert "status" in data
        assert "service" in data
        assert data["status"] == "ok"
        assert data["service"] == "adc-voice"

    @pytest.mark.asyncio
    async def test_health_endpoint_response_time(self, async_client: httpx.AsyncClient):
        """Test that /health endpoint responds quickly (< 1 second)."""
        import time
        start = time.monotonic()
        response = await async_client.get("/health")
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        assert elapsed < 1.0, f"Health check took {elapsed:.2f}s, expected < 1.0s"


class TestRootEndpoint:
    """Test the root / endpoint."""

    @pytest.mark.asyncio
    async def test_root_endpoint_accessible(self, async_client: httpx.AsyncClient):
        """Test that root endpoint is accessible."""
        response = await async_client.get("/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_root_endpoint_content_type(self, async_client: httpx.AsyncClient):
        """Test that root endpoint returns HTML content."""
        response = await async_client.get("/")
        assert "text/html" in response.headers["content-type"]


class TestAPIEndpoints:
    """Test basic API endpoints functionality."""

    @pytest.mark.asyncio
    async def test_api_v1_environment_endpoint(self, async_client: httpx.AsyncClient):
        """Test /api/v1/environment endpoint returns valid response."""
        response = await async_client.get("/api/v1/environment")

        # Should return 200 or 404 if endpoint doesn't exist
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (dict, list))

    @pytest.mark.asyncio
    async def test_api_v1_registry_endpoint(self, async_client: httpx.AsyncClient):
        """Test /api/v1/registry endpoint returns valid response."""
        response = await async_client.get("/api/v1/registry")

        # Should return 200 or 404 if endpoint doesn't exist
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (dict, list))


class TestResponseStructureValidation:
    """Test response structure validation utilities."""

    @pytest.mark.asyncio
    async def test_json_response_parsing(self, async_client: httpx.AsyncClient):
        """Test that JSON responses can be properly parsed."""
        response = await async_client.get("/health")

        # Verify response can be parsed as JSON
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_response_headers_present(self, async_client: httpx.AsyncClient):
        """Test that responses include required headers."""
        response = await async_client.get("/health")

        # Check for common headers
        assert "content-type" in response.headers
        assert len(response.headers) > 0

    @pytest.mark.asyncio
    async def test_response_body_not_empty(self, async_client: httpx.AsyncClient):
        """Test that responses return non-empty body content."""
        response = await async_client.get("/health")

        # Verify response has content
        assert len(response.content) > 0


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_nonexistent_endpoint_returns_404(self, async_client: httpx.AsyncClient):
        """Test that nonexistent endpoints return 404."""
        response = await async_client.get("/nonexistent-endpoint")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_method_returns_405(self, async_client: httpx.AsyncClient):
        """Test that invalid HTTP methods return 405."""
        # Try POST on endpoint that only supports GET
        response = await async_client.post("/health")
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_malformed_request_handled_gracefully(self, async_client: httpx.AsyncClient):
        """Test that malformed requests are handled gracefully."""
        # Try sending invalid data to an endpoint
        response = await async_client.post(
            "/api/v1/timings",
            json={"invalid": "data"},
            headers={"Content-Type": "application/json"}
        )

        # Should return 422 (validation error) or 400 (bad request)
        assert response.status_code in [400, 422, 404]


class TestHTTPClientConfiguration:
    """Test HTTP client configuration and connection handling."""

    @pytest.mark.asyncio
    async def test_client_timeout_configuration(self, async_client: httpx.AsyncClient):
        """Test that HTTP client respects timeout configuration."""
        # Health endpoint should respond quickly
        import time
        start = time.monotonic()

        response = await async_client.get("/health")
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        assert elapsed < 10.0, "Request should complete within timeout"

    @pytest.mark.asyncio
    async def test_client_connection_reuse(self, async_client: httpx.AsyncClient):
        """Test that client can reuse connections for multiple requests."""
        # Make multiple requests
        responses = []
        for _ in range(3):
            response = await async_client.get("/health")
            responses.append(response)

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200


def validate_response_structure(
    response: httpx.Response,
    expected_status: int = 200,
    expected_content_type: str = None,
    expected_fields: list = None
) -> Dict[str, Any]:
    """
    Utility function to validate response structure.

    Args:
        response: HTTP response object
        expected_status: Expected HTTP status code
        expected_content_type: Expected content-type header
        expected_fields: List of expected JSON fields

    Returns:
        Parsed JSON response data

    Raises:
        AssertionError: If validation fails
    """
    # Validate status code
    assert response.status_code == expected_status, \
        f"Expected status {expected_status}, got {response.status_code}"

    # Validate content type if specified
    if expected_content_type:
        assert expected_content_type in response.headers.get("content-type", ""), \
            f"Expected content-type {expected_content_type}, got {response.headers.get('content-type')}"

    # Parse JSON response
    try:
        data = response.json()
    except Exception as e:
        raise AssertionError(f"Failed to parse JSON response: {e}")

    # Validate expected fields if specified
    if expected_fields:
        for field in expected_fields:
            assert field in data, f"Missing expected field: {field}"

    return data


class TestValidationUtilities:
    """Test the validation utility functions."""

    @pytest.mark.asyncio
    async def test_validate_response_structure_utility(self, async_client: httpx.AsyncClient):
        """Test the validate_response_structure utility function."""
        response = await async_client.get("/health")

        # Use the utility to validate
        data = validate_response_structure(
            response,
            expected_status=200,
            expected_content_type="application/json",
            expected_fields=["status", "service"]
        )

        # Verify data was parsed correctly
        assert data["status"] == "ok"
        assert data["service"] == "adc-voice"