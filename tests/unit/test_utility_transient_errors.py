"""
Unit tests for transient error detection utility.

Tests the is_transient_error() and get_error_type() functions from
src.utilities.transient_errors, covering:
- Timeout errors (TimeoutError, asyncio.TimeoutError)
- Connection errors (ConnectionError, httpx.ConnectError)
- HTTP 5xx server errors (transient)
- HTTP 4xx client errors (permanent, except 429)
- Network error classification
"""

import asyncio
from unittest.mock import Mock

import pytest
import httpx

from src.utilities.transient_errors import is_transient_error, get_error_type


class TestTimeoutErrors:
    """Test timeout error detection - all should be transient."""

    def test_asyncio_timeout_error(self):
        """asyncio.TimeoutError should be transient."""
        error = asyncio.TimeoutError("Async operation timed out")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'timeout'

    def test_timeout_error(self):
        """Standard library TimeoutError should be transient."""
        error = TimeoutError("Operation timed out")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'timeout'

    def test_httpx_timeout_exception(self):
        """httpx.TimeoutException should be transient."""
        error = httpx.TimeoutException("Request timed out")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'timeout'

    def test_httpx_connect_timeout(self):
        """httpx.ConnectTimeout should be transient."""
        error = httpx.ConnectTimeout("Connection timed out")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'timeout'

    def test_httpx_read_timeout(self):
        """httpx.ReadTimeout should be transient."""
        error = httpx.ReadTimeout("Read operation timed out")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'timeout'

    def test_httpx_write_timeout(self):
        """httpx.WriteTimeout should be transient."""
        error = httpx.WriteTimeout("Write operation timed out")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'timeout'


class TestConnectionErrors:
    """Test connection error detection - should be transient."""

    def test_connection_error_base(self):
        """Standard library ConnectionError should be transient."""
        error = ConnectionError("Connection failed")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'connection'

    def test_httpx_connect_error(self):
        """httpx.ConnectError should be transient."""
        error = httpx.ConnectError("Connection refused")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'connection'


class TestHTTPServerErrors:
    """Test HTTP 5xx server error detection - all should be transient."""

    def test_httpx_500_internal_server_error(self):
        """HTTP 500 should be transient."""
        response = Mock(status_code=500)
        error = httpx.HTTPStatusError("Internal Server Error", request=Mock(), response=response)
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'server_error'

    def test_httpx_502_bad_gateway(self):
        """HTTP 502 should be transient."""
        response = Mock(status_code=502)
        error = httpx.HTTPStatusError("Bad Gateway", request=Mock(), response=response)
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'server_error'

    def test_httpx_503_service_unavailable(self):
        """HTTP 503 should be transient."""
        response = Mock(status_code=503)
        error = httpx.HTTPStatusError("Service Unavailable", request=Mock(), response=response)
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'server_error'

    def test_httpx_504_gateway_timeout(self):
        """HTTP 504 should be transient."""
        response = Mock(status_code=504)
        error = httpx.HTTPStatusError("Gateway Timeout", request=Mock(), response=response)
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'server_error'

    def test_httpx_507_insufficient_storage(self):
        """HTTP 507 should be transient."""
        response = Mock(status_code=507)
        error = httpx.HTTPStatusError("Insufficient Storage", request=Mock(), response=response)
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'server_error'


class TestHTTPClientErrors:
    """Test HTTP 4xx client error detection - should be permanent."""

    def test_httpx_400_bad_request_permanent(self):
        """HTTP 400 should be permanent."""
        response = Mock(status_code=400)
        error = httpx.HTTPStatusError("Bad Request", request=Mock(), response=response)
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'client_error'

    def test_httpx_401_unauthorized_permanent(self):
        """HTTP 401 Unauthorized should be permanent."""
        response = Mock(status_code=401)
        error = httpx.HTTPStatusError("Unauthorized", request=Mock(), response=response)
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'client_error'

    def test_httpx_403_forbidden_permanent(self):
        """HTTP 403 Forbidden should be permanent."""
        response = Mock(status_code=403)
        error = httpx.HTTPStatusError("Forbidden", request=Mock(), response=response)
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'client_error'

    def test_httpx_404_not_found_permanent(self):
        """HTTP 404 Not Found should be permanent."""
        response = Mock(status_code=404)
        error = httpx.HTTPStatusError("Not Found", request=Mock(), response=response)
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'client_error'

    def test_httpx_409_conflict_permanent(self):
        """HTTP 409 Conflict should be permanent."""
        response = Mock(status_code=409)
        error = httpx.HTTPStatusError("Conflict", request=Mock(), response=response)
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'client_error'

    def test_httpx_422_unprocessable_entity_permanent(self):
        """HTTP 422 Unprocessable Entity should be permanent."""
        response = Mock(status_code=422)
        error = httpx.HTTPStatusError("Unprocessable Entity", request=Mock(), response=response)
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'client_error'

    def test_httpx_429_rate_limit_transient(self):
        """HTTP 429 should be transient (rate limiting)."""
        response = Mock(status_code=429)
        error = httpx.HTTPStatusError("Too Many Requests", request=Mock(), response=response)
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'rate_limit'


class TestNetworkErrors:
    """Test general network error detection."""

    def test_httpx_read_error(self):
        """httpx.ReadError should be transient."""
        error = httpx.ReadError("Read failed")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'network'

    def test_httpx_write_error(self):
        """httpx.WriteError should be transient."""
        error = httpx.WriteError("Write failed")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'network'

    def test_httpx_remote_protocol_error(self):
        """httpx.RemoteProtocolError should be transient."""
        error = httpx.RemoteProtocolError("Remote closed connection")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'network'

    def test_httpx_local_protocol_error(self):
        """httpx.LocalProtocolError should be transient."""
        error = httpx.LocalProtocolError("Local protocol error")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'network'

    def test_httpx_http_error_base(self):
        """httpx.HTTPError base class should be transient."""
        error = httpx.HTTPError("Generic HTTP error")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'network'


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_none_error(self):
        """None error should return False."""
        assert is_transient_error(None) is False
        assert get_error_type(None) == 'unknown'

    def test_unknown_exception_type(self):
        """Unknown exception types should be permanent (conservative)."""
        error = ValueError("Some random error")
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'unknown'

    def test_runtime_error(self):
        """RuntimeError should be permanent."""
        error = RuntimeError("Something went wrong")
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'unknown'

    def test_generic_exception(self):
        """Generic Exception should be permanent."""
        error = Exception("Generic error")
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'unknown'

    def test_io_error(self):
        """IOError should be permanent (not a network error)."""
        error = IOError("File I/O error")
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'unknown'


class TestErrorTypeClassification:
    """Test get_error_type() function classification."""

    def test_type_timeout_asyncio(self):
        """asyncio.TimeoutError should return 'timeout' type."""
        error = asyncio.TimeoutError("timeout")
        assert get_error_type(error) == 'timeout'

    def test_type_timeout_standard(self):
        """TimeoutError should return 'timeout' type."""
        error = TimeoutError("timeout")
        assert get_error_type(error) == 'timeout'

    def test_type_timeout_httpx(self):
        """httpx.TimeoutException should return 'timeout' type."""
        error = httpx.TimeoutException("timeout")
        assert get_error_type(error) == 'timeout'

    def test_type_connection_base(self):
        """ConnectionError should return 'connection' type."""
        error = ConnectionError("connection refused")
        assert get_error_type(error) == 'connection'

    def test_type_connection_httpx(self):
        """httpx.ConnectError should return 'connection' type."""
        error = httpx.ConnectError("connection failed")
        assert get_error_type(error) == 'connection'

    def test_type_server_error(self):
        """HTTP 5xx errors should return 'server_error' type."""
        response = Mock(status_code=500)
        error = httpx.HTTPStatusError("Internal Server Error", request=Mock(), response=response)
        assert get_error_type(error) == 'server_error'

    def test_type_rate_limit(self):
        """HTTP 429 should return 'rate_limit' type."""
        response = Mock(status_code=429)
        error = httpx.HTTPStatusError("Too Many Requests", request=Mock(), response=response)
        assert get_error_type(error) == 'rate_limit'

    def test_type_client_error(self):
        """HTTP 4xx errors should return 'client_error' type."""
        response = Mock(status_code=404)
        error = httpx.HTTPStatusError("Not Found", request=Mock(), response=response)
        assert get_error_type(error) == 'client_error'

    def test_type_network(self):
        """General network errors should return 'network' type."""
        assert get_error_type(httpx.ReadError("Read failed")) == 'network'
        assert get_error_type(httpx.WriteError("Write failed")) == 'network'

    def test_type_unknown(self):
        """Unknown errors should return 'unknown' type."""
        assert get_error_type(None) == 'unknown'
        assert get_error_type(ValueError("random error")) == 'unknown'


class TestIntegrationScenarios:
    """Test integration scenarios for Git operations."""

    def test_git_clone_timeout(self):
        """Simulate Git clone timeout scenario."""
        # When a Git clone times out due to network latency
        error = asyncio.TimeoutError("Git clone operation timed out")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'timeout'

    def test_git_push_connection_refused(self):
        """Simulate Git push connection refused scenario."""
        # When a Git push fails because the server is temporarily down
        error = httpx.ConnectError("Connection refused: Git server unreachable")
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'connection'

    def test_git_fetch_server_error(self):
        """Simulate Git fetch server error scenario."""
        # When a Git fetch fails due to server-side issues
        response = Mock(status_code=503)
        error = httpx.HTTPStatusError(
            "Service Unavailable: Git server overloaded",
            request=Mock(),
            response=response
        )
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'server_error'

    def test_git_auth_failure(self):
        """Simulate Git authentication failure scenario."""
        # When Git fails due to invalid credentials
        response = Mock(status_code=401)
        error = httpx.HTTPStatusError(
            "Unauthorized: Invalid Git credentials",
            request=Mock(),
            response=response
        )
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'client_error'

    def test_git_conflict_error(self):
        """Simulate Git conflict scenario."""
        # When Git push fails due to conflicting changes
        response = Mock(status_code=409)
        error = httpx.HTTPStatusError(
            "Conflict: Concurrent Git modification",
            request=Mock(),
            response=response
        )
        assert is_transient_error(error) is False
        assert get_error_type(error) == 'client_error'

    def test_git_rate_limiting(self):
        """Simulate Git rate limiting scenario."""
        # When Git operations are rate-limited by the server
        response = Mock(status_code=429)
        error = httpx.HTTPStatusError(
            "Too Many Requests: Git API rate limit exceeded",
            request=Mock(),
            response=response
        )
        assert is_transient_error(error) is True
        assert get_error_type(error) == 'rate_limit'
