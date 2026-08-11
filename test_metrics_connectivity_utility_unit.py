#!/usr/bin/env python3
"""
Unit tests for the metrics endpoint connectivity utility.

Tests the functionality of check_endpoint_connectivity and related functions
with mock HTTP servers and various error conditions.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import httpx

from src.test.utilities import (
    check_endpoint_connectivity,
    check_metrics_endpoints,
    check_endpoint_connectivity_sync,
    EndpointConnectivityResult,
)


class TestEndpointConnectivityResult:
    """Test the EndpointConnectivityResult class."""

    def test_success_result_creation(self):
        """Test creating a successful result."""
        result = EndpointConnectivityResult(
            success=True,
            status_code=200,
            response_body="OK",
            response_time_ms=123.45,
        )

        assert result.success is True
        assert result.status_code == 200
        assert result.response_body == "OK"
        assert result.response_time_ms == 123.45
        assert result.error_message is None

    def test_failure_result_creation(self):
        """Test creating a failed result."""
        result = EndpointConnectivityResult(
            success=False,
            error_message="Connection timeout",
        )

        assert result.success is False
        assert result.error_message == "Connection timeout"
        assert result.status_code is None
        assert result.response_body is None

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = EndpointConnectivityResult(
            success=True,
            status_code=200,
            response_body="test",
            error_message=None,
            response_time_ms=100.0,
        )

        result_dict = result.to_dict()

        assert result_dict == {
            "success": True,
            "status_code": 200,
            "response_body": "test",
            "error_message": None,
            "response_time_ms": 100.0,
        }

    def test_repr_success(self):
        """Test string representation of successful result."""
        result = EndpointConnectivityResult(
            success=True,
            status_code=200,
            response_time_ms=150.75,
        )

        repr_str = repr(result)
        assert "success=True" in repr_str
        assert "status_code=200" in repr_str
        assert "150.75" in repr_str

    def test_repr_failure(self):
        """Test string representation of failed result."""
        result = EndpointConnectivityResult(
            success=False,
            error_message="Timeout error",
        )

        repr_str = repr(result)
        assert "success=False" in repr_str
        assert "Timeout error" in repr_str


@pytest.mark.asyncio
class TestCheckEndpointConnectivity:
    """Test the check_endpoint_connectivity function."""

    async def test_successful_get_request(self):
        """Test a successful GET request."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "success"}'

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await check_endpoint_connectivity(
                endpoint_url="http://example.com/api/test",
                timeout_seconds=10.0,
            )

        assert result.success is True
        assert result.status_code == 200
        assert result.response_body == '{"status": "success"}'
        assert result.response_time_ms > 0

    async def test_unexpected_status_code(self):
        """Test handling of unexpected status codes."""
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await check_endpoint_connectivity(
                endpoint_url="http://example.com/notfound",
                timeout_seconds=10.0,
            )

        assert result.success is False
        assert result.status_code == 404
        assert "Unexpected status code" in result.error_message

    async def test_timeout_exception(self):
        """Test handling of timeout exceptions."""
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(
            side_effect=httpx.TimeoutException("Request timed out")
        )
        mock_client.aclose = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await check_endpoint_connectivity(
                endpoint_url="http://example.com/slow",
                timeout_seconds=1.0,
            )

        assert result.success is False
        assert "Timeout" in result.error_message
        assert result.response_time_ms is not None

    async def test_connection_error(self):
        """Test handling of connection errors."""
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_client.aclose = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await check_endpoint_connectivity(
                endpoint_url="http://invalid-host/api",
                timeout_seconds=10.0,
            )

        assert result.success is False
        assert "Connection error" in result.error_message

    async def test_custom_expected_status_codes(self):
        """Test custom expected status codes."""
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_response.text = ""

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await check_endpoint_connectivity(
                endpoint_url="http://example.com/delete",
                timeout_seconds=10.0,
                expected_status_codes=[204, 200],
            )

        assert result.success is True
        assert result.status_code == 204

    async def test_custom_headers(self):
        """Test request with custom headers."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await check_endpoint_connectivity(
                endpoint_url="http://example.com/api",
                timeout_seconds=10.0,
                headers={"Authorization": "Bearer token123"},
            )

        assert result.success is True
        # Verify the client was called with the custom headers
        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer token123"

    async def test_ssl_verify_disabled(self):
        """Test with SSL verification disabled."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await check_endpoint_connectivity(
                endpoint_url="http://example.com/api",
                timeout_seconds=10.0,
                verify_ssl=False,
            )

        assert result.success is True

    async def test_response_time_calculation(self):
        """Test that response time is calculated correctly."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock()
        # Add a small delay to test timing
        async def slow_request(*args, **kwargs):
            await asyncio.sleep(0.1)  # 100ms delay
            return mock_response

        mock_client.request = slow_request
        mock_client.aclose = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await check_endpoint_connectivity(
                endpoint_url="http://example.com/api",
                timeout_seconds=10.0,
            )

        assert result.success is True
        assert result.response_time_ms >= 100  # At least 100ms


@pytest.mark.asyncio
class TestCheckMetricsEndpoints:
    """Test the check_metrics_endpoints function."""

    async def test_multiple_endpoints_success(self):
        """Test checking multiple endpoints successfully."""
        endpoints = [
            {
                "name": "endpoint1",
                "url": "http://example.com/api1",
            },
            {
                "name": "endpoint2",
                "url": "http://example.com/api2",
            },
        ]

        # Mock successful responses
        async def mock_check(*args, **kwargs):
            # Simulate different URLs
            url = kwargs.get("endpoint_url", "")
            return EndpointConnectivityResult(
                success=True,
                status_code=200,
                response_body=f"Response from {url}",
                response_time_ms=50.0,
            )

        with patch('src.test.utilities.check_endpoint_connectivity', side_effect=mock_check):
            results = await check_metrics_endpoints(endpoints, timeout_seconds=30.0)

        assert len(results) == 2
        assert "endpoint1" in results
        assert "endpoint2" in results
        assert results["endpoint1"].success is True
        assert results["endpoint2"].success is True

    async def test_multiple_endpoints_mixed_results(self):
        """Test checking endpoints with mixed success/failure."""
        endpoints = [
            {
                "name": "success",
                "url": "http://example.com/success",
            },
            {
                "name": "failure",
                "url": "http://example.com/failure",
            },
        ]

        async def mock_check(*args, **kwargs):
            url = kwargs.get("endpoint_url", "")
            if "success" in url:
                return EndpointConnectivityResult(
                    success=True,
                    status_code=200,
                    response_body="OK",
                    response_time_ms=50.0,
                )
            else:
                return EndpointConnectivityResult(
                    success=False,
                    error_message="Connection failed",
                )

        with patch('src.test.utilities.check_endpoint_connectivity', side_effect=mock_check):
            results = await check_metrics_endpoints(endpoints, timeout_seconds=30.0)

        assert len(results) == 2
        assert results["success"].success is True
        assert results["failure"].success is False

    async def test_endpoint_missing_url(self):
        """Test endpoint configuration missing URL."""
        endpoints = [
            {
                "name": "invalid",
                # Missing "url" key
            },
        ]

        results = await check_metrics_endpoints(endpoints, timeout_seconds=30.0)

        assert "invalid" in results
        assert results["invalid"].success is False
        assert "Missing URL" in results["invalid"].error_message

    async def test_endpoint_with_custom_config(self):
        """Test endpoints with custom configuration."""
        endpoints = [
            {
                "name": "custom",
                "url": "http://example.com/api",
                "method": "POST",
                "headers": {"X-Custom": "header"},
                "expected_status_codes": [201],
                "verify_ssl": False,
            },
        ]

        async def mock_check(*args, **kwargs):
            # Verify custom parameters were passed
            assert kwargs.get("method") == "POST"
            assert kwargs.get("headers") == {"X-Custom": "header"}
            assert kwargs.get("expected_status_codes") == [201]
            assert kwargs.get("verify_ssl") is False

            return EndpointConnectivityResult(
                success=True,
                status_code=201,
                response_body="Created",
                response_time_ms=100.0,
            )

        with patch('src.test.utilities.check_endpoint_connectivity', side_effect=mock_check):
            results = await check_metrics_endpoints(endpoints, timeout_seconds=30.0)

        assert results["custom"].success is True
        assert results["custom"].status_code == 201


class TestCheckEndpointConnectivitySync:
    """Test the synchronous wrapper function."""

    def test_sync_wrapper_success(self):
        """Test synchronous wrapper with successful request."""
        mock_result = EndpointConnectivityResult(
            success=True,
            status_code=200,
            response_body="OK",
            response_time_ms=50.0,
        )

        async def mock_async_check(*args, **kwargs):
            return mock_result

        with patch('src.test.utilities.check_endpoint_connectivity', side_effect=mock_async_check):
            result = check_endpoint_connectivity_sync(
                endpoint_url="http://example.com/api",
                timeout_seconds=10.0,
            )

        assert result.success is True
        assert result.status_code == 200

    def test_sync_wrapper_failure(self):
        """Test synchronous wrapper with failed request."""
        mock_result = EndpointConnectivityResult(
            success=False,
            error_message="Connection timeout",
        )

        async def mock_async_check(*args, **kwargs):
            return mock_result

        with patch('src.test.utilities.check_endpoint_connectivity', side_effect=mock_async_check):
            result = check_endpoint_connectivity_sync(
                endpoint_url="http://example.com/api",
                timeout_seconds=10.0,
            )

        assert result.success is False
        assert "Connection timeout" in result.error_message


@pytest.mark.integration
class TestIntegrationExamples:
    """Integration examples demonstrating real usage patterns."""

    @pytest.mark.skip("Requires actual HTTP endpoint")
    async def test_real_prometheus_query(self):
        """Example of querying a real Prometheus instance."""
        result = await check_endpoint_connectivity(
            endpoint_url="http://localhost:9090/api/v1/query?query=up",
            timeout_seconds=10.0,
        )

        assert result.success is True
        assert result.status_code == 200

    @pytest.mark.skip("Requires actual HTTP endpoint")
    def test_real_prometheus_query_sync(self):
        """Example of synchronous query to real Prometheus."""
        result = check_endpoint_connectivity_sync(
            endpoint_url="http://localhost:9090/api/v1/query?query=up",
            timeout_seconds=10.0,
        )

        assert result.success is True
        assert result.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
