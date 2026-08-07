"""
Comprehensive tests for endpoint connectivity utility functions.

This module tests the endpoint connectivity checking utilities that are used
for testing metrics endpoints and other HTTP services, including pbx-web and
whisper-stt connectivity validation.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from src.test.utilities import (
    EndpointConnectivityResult,
    check_endpoint_connectivity,
    check_metrics_endpoints,
    check_endpoint_connectivity_sync,
)


class TestEndpointConnectivityResult:
    """Test the EndpointConnectivityResult data structure."""

    def test_successful_result_creation(self):
        """Test creating a successful connectivity result."""
        result = EndpointConnectivityResult(
            success=True,
            status_code=200,
            response_body='{"status": "ok"}',
            response_time_ms=123.45,
        )

        assert result.success is True
        assert result.status_code == 200
        assert result.response_body == '{"status": "ok"}'
        assert result.response_time_ms == 123.45
        assert result.error_message is None

    def test_failed_result_creation(self):
        """Test creating a failed connectivity result."""
        result = EndpointConnectivityResult(
            success=False,
            error_message="Connection refused",
            response_time_ms=50.0,
        )

        assert result.success is False
        assert result.error_message == "Connection refused"
        assert result.status_code is None
        assert result.response_body is None

    def test_to_dict_conversion(self):
        """Test converting result to dictionary."""
        result = EndpointConnectivityResult(
            success=True,
            status_code=200,
            response_body="test body",
            error_message=None,
            response_time_ms=100.0,
        )

        data = result.to_dict()

        assert data == {
            "success": True,
            "status_code": 200,
            "response_body": "test body",
            "error_message": None,
            "response_time_ms": 100.0,
        }

    def test_successful_repr(self):
        """Test string representation for successful result."""
        result = EndpointConnectivityResult(
            success=True,
            status_code=200,
            response_time_ms=150.75,
        )

        repr_str = repr(result)
        assert "success=True" in repr_str
        assert "status_code=200" in repr_str
        assert "response_time_ms=150.75" in repr_str

    def test_failed_repr(self):
        """Test string representation for failed result."""
        result = EndpointConnectivityResult(
            success=False,
            error_message="Timeout after 30s",
        )

        repr_str = repr(result)
        assert "success=False" in repr_str
        assert "Timeout after 30s" in repr_str


class TestCheckEndpointConnectivity:
    """Test the check_endpoint_connectivity function."""

    @pytest.mark.asyncio
    async def test_successful_get_request(self):
        """Test successful GET request to endpoint."""
        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock the response
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = '{"status": "healthy"}'
            mock_response.json = AsyncMock(return_value={"status": "healthy"})

            # Mock the client
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await check_endpoint_connectivity(
                endpoint_url="http://localhost:9090/api/v1/query",
                timeout_seconds=10.0,
            )

            assert result.success is True
            assert result.status_code == 200
            assert result.response_body == '{"status": "healthy"}'
            assert result.response_time_ms > 0
            assert result.error_message is None

            # Verify the client was called correctly
            mock_client.request.assert_called_once()
            call_kwargs = mock_client.request.call_args[1]
            assert call_kwargs["method"] == "GET"
            assert "query" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test timeout handling for unresponsive endpoints."""
        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock timeout exception
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(
                side_effect=Exception("Timeout")
            )
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await check_endpoint_connectivity(
                endpoint_url="http://localhost:9090/api/v1/query",
                timeout_seconds=1.0,
            )

            assert result.success is False
            assert "Timeout" in result.error_message or "timeout" in result.error_message.lower()
            assert result.response_time_ms >= 0

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test handling of connection errors."""
        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock connection error
            import httpx
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await check_endpoint_connectivity(
                endpoint_url="http://localhost:9090/api/v1/query",
            )

            assert result.success is False
            assert "Connection error" in result.error_message
            assert "Connection refused" in result.error_message

    @pytest.mark.asyncio
    async def test_unexpected_status_code(self):
        """Test handling of unexpected HTTP status codes."""
        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock 404 response
            mock_response = AsyncMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await check_endpoint_connectivity(
                endpoint_url="http://localhost:9090/api/v1/query",
                expected_status_codes=[200],
            )

            assert result.success is False
            assert result.status_code == 404
            assert "Unexpected status code" in result.error_message
            assert result.response_body == "Not Found"

    @pytest.mark.asyncio
    async def test_custom_status_codes(self):
        """Test accepting multiple status codes."""
        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock 202 response
            mock_response = AsyncMock()
            mock_response.status_code = 202
            mock_response.text = '{"status": "accepted"}'

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await check_endpoint_connectivity(
                endpoint_url="http://localhost:9090/api/v1/query",
                expected_status_codes=[200, 202, 204],
            )

            assert result.success is True
            assert result.status_code == 202
            assert result.response_body == '{"status": "accepted"}'

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        """Test sending custom headers with request."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = "OK"

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            custom_headers = {"Authorization": "Bearer test-token", "Accept": "application/json"}

            result = await check_endpoint_connectivity(
                endpoint_url="http://localhost:9090/api/v1/query",
                headers=custom_headers,
            )

            assert result.success is True

            # Verify headers were passed
            call_kwargs = mock_client.request.call_args[1]
            assert "headers" in call_kwargs
            assert call_kwargs["headers"] == custom_headers

    @pytest.mark.asyncio
    async def test_ssl_verification_disabled(self):
        """Test disabling SSL verification."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = "OK"

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await check_endpoint_connectivity(
                endpoint_url="https://localhost:9090/api/v1/query",
                verify_ssl=False,
            )

            # Verify client was created with verify=False
            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args[1]
            assert call_kwargs["verify"] is False

    @pytest.mark.asyncio
    async def test_http_response_time_measurement(self):
        """Test that response time is measured accurately."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = "OK"

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await check_endpoint_connectivity(
                endpoint_url="http://localhost:9090/api/v1/query",
            )

            assert result.response_time_ms >= 0
            # Should be very fast for a mock, but greater than 0
            assert result.response_time_ms > 0


class TestCheckMetricsEndpoints:
    """Test the check_metrics_endpoints function for concurrent checking."""

    @pytest.mark.asyncio
    async def test_multiple_endpoints_concurrently(self):
        """Test checking multiple endpoints concurrently."""
        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock successful responses
            mock_response_1 = AsyncMock()
            mock_response_1.status_code = 200
            mock_response_1.text = '{"status": "ok"}'

            mock_response_2 = AsyncMock()
            mock_response_2.status_code = 200
            mock_response_2.text = "metrics data"

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(
                side_effect=[mock_response_1, mock_response_2]
            )
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            endpoints = [
                {
                    "name": "prometheus",
                    "url": "http://localhost:9090/api/v1/query",
                },
                {
                    "name": "pbx-web",
                    "url": "http://localhost:9090/metrics",
                },
            ]

            results = await check_metrics_endpoints(endpoints, timeout_seconds=10.0)

            assert len(results) == 2
            assert "prometheus" in results
            assert "pbx-web" in results
            assert results["prometheus"].success is True
            assert results["pbx-web"].success is True

    @pytest.mark.asyncio
    async def test_mixed_success_failure(self):
        """Test handling mixed successful and failed endpoints."""
        with patch("httpx.AsyncClient") as mock_client_class:
            import httpx

            # Mock one success, one failure
            mock_response_success = AsyncMock()
            mock_response_success.status_code = 200
            mock_response_success.text = "OK"

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(
                side_effect=[
                    mock_response_success,
                    httpx.ConnectError("Connection refused"),
                ]
            )
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            endpoints = [
                {
                    "name": "working-endpoint",
                    "url": "http://localhost:9090/api/v1/query",
                },
                {
                    "name": "broken-endpoint",
                    "url": "http://localhost:9091/api/v1/query",
                },
            ]

            results = await check_metrics_endpoints(endpoints)

            assert results["working-endpoint"].success is True
            assert results["broken-endpoint"].success is False
            assert "Connection error" in results["broken-endpoint"].error_message

    @pytest.mark.asyncio
    async def test_endpoint_with_custom_config(self):
        """Test endpoint configuration with custom settings."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 202
            mock_response.text = "Accepted"

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            endpoints = [
                {
                    "name": "custom-endpoint",
                    "url": "http://localhost:9090/api/v1/query",
                    "method": "POST",
                    "expected_status_codes": [200, 202, 204],
                    "headers": {"X-Custom-Header": "value"},
                },
            ]

            results = await check_metrics_endpoints(endpoints)

            assert results["custom-endpoint"].success is True
            assert results["custom-endpoint"].status_code == 202


class TestCheckEndpointConnectivitySync:
    """Test the synchronous wrapper for endpoint connectivity checking."""

    def test_sync_wrapper_basic(self):
        """Test basic synchronous endpoint check."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = "OK"

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = check_endpoint_connectivity_sync(
                endpoint_url="http://localhost:9090/api/v1/query",
            )

            assert result.success is True
            assert result.status_code == 200

    def test_sync_wrapper_with_parameters(self):
        """Test synchronous wrapper with custom parameters."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = "OK"

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = check_endpoint_connectivity_sync(
                endpoint_url="http://localhost:9090/api/v1/query",
                timeout_seconds=15.0,
                method="POST",
                headers={"X-Test": "value"},
                expected_status_codes=[200, 201],
                verify_ssl=False,
            )

            assert result.success is True
            # Verify the client was created with verify=False
            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args[1]
            assert call_kwargs["verify"] is False


class TestRealWorldScenarios:
    """Test real-world usage scenarios for pbx-web and whisper-stt."""

    @pytest.mark.asyncio
    async def test_prometheus_query_endpoint(self):
        """Test typical Prometheus query endpoint structure."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = '{"data": {"result": []}}'

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            # Typical Prometheus query for checking if a target is up
            result = await check_endpoint_connectivity(
                endpoint_url="http://localhost:9090/api/v1/query?query=up",
                timeout_seconds=10.0,
            )

            assert result.success is True
            assert result.status_code == 200
            assert '"result"' in result.response_body

    @pytest.mark.asyncio
    async def test_pbx_web_metrics_scenario(self):
        """Test pbx-web metrics endpoint scenario."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = '# HELP pbx_web_requests_total Total requests\n'

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await check_endpoint_connectivity(
                endpoint_url="http://pbx-web:9090/metrics",
                timeout_seconds=30.0,
                headers={"Accept": "text/plain"},
            )

            assert result.success is True
            assert "pbx_web" in result.response_body

    @pytest.mark.asyncio
    async def test_whisper_stt_metrics_scenario(self):
        """Test whisper-stt metrics endpoint scenario."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = '# HELP whisper_stt_requests_total Total STT requests\n'

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await check_endpoint_connectivity(
                endpoint_url="http://whisper-stt:9090/metrics",
                timeout_seconds=30.0,
            )

            assert result.success is True
            assert "whisper_stt" in result.response_body

    @pytest.mark.asyncio
    async def test_concurrent_pbx_and_whisper_check(self):
        """Test concurrent checking of both pbx-web and whisper-stt endpoints."""
        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock responses for both endpoints
            pbx_response = AsyncMock()
            pbx_response.status_code = 200
            pbx_response.text = '# pbx-web metrics'

            whisper_response = AsyncMock()
            whisper_response.status_code = 200
            whisper_response.text = '# whisper-stt metrics'

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(
                side_effect=[pbx_response, whisper_response]
            )
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            endpoints = [
                {
                    "name": "pbx-web",
                    "url": "http://pbx-web:9090/metrics",
                    "timeout": 30.0,
                },
                {
                    "name": "whisper-stt",
                    "url": "http://whisper-stt:9090/metrics",
                    "timeout": 30.0,
                },
            ]

            results = await check_metrics_endpoints(endpoints)

            assert len(results) == 2
            assert results["pbx-web"].success is True
            assert results["whisper-stt"].success is True
            assert "pbx-web" in results["pbx-web"].response_body.lower()
            assert "whisper-stt" in results["whisper-stt"].response_body.lower()
