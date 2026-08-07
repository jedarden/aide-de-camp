"""
Unit tests for transient network error detection and classification.

Tests the is_transient() and get_error_category() functions from
src.errors.transient_errors, covering:
- Timeouts (socket, HTTP read, connect)
- Connection resets and refused connections
- DNS resolution failures
- HTTP 5xx server errors (transient)
- HTTP 4xx client errors (permanent, except 429)
- Socket and OS errors with errno codes
"""

import errno
import socket
from unittest.mock import Mock

import pytest
import httpx
import aiohttp

from src.errors.transient_errors import is_transient, get_error_category


class TestTimeoutErrors:
    """Test timeout error detection - all should be transient."""

    def test_httpx_timeout_exception(self):
        """httpx.TimeoutException should be transient."""
        error = httpx.TimeoutException("Request timed out")
        assert is_transient(error) is True

    def test_httpx_connect_timeout(self):
        """httpx.ConnectTimeout should be transient."""
        error = httpx.ConnectTimeout("Connection timed out")
        assert is_transient(error) is True

    def test_httpx_read_timeout(self):
        """httpx.ReadTimeout should be transient."""
        error = httpx.ReadTimeout("Read operation timed out")
        assert is_transient(error) is True

    def test_httpx_write_timeout(self):
        """httpx.WriteTimeout should be transient."""
        error = httpx.WriteTimeout("Write operation timed out")
        assert is_transient(error) is True

    def test_aiohttp_client_timeout(self):
        """aiohttp.ClientTimeout should be transient."""
        error = aiohttp.ClientTimeout(total=30.0)
        assert is_transient(error) is True

    def test_aiohttp_server_timeout_error(self):
        """aiohttp.ServerTimeoutError should be transient."""
        error = aiohttp.ServerTimeoutError("Server timeout")
        assert is_transient(error) is True

    def test_socket_timeout(self):
        """socket.timeout should be transient."""
        error = socket.timeout("Socket timeout")
        assert is_transient(error) is True


class TestConnectionErrors:
    """Test connection error detection."""

    def test_httpx_connect_error(self):
        """httpx.ConnectError should be transient."""
        error = httpx.ConnectError("Connection refused")
        assert is_transient(error) is True

    def test_httpx_remote_protocol_error(self):
        """httpx.RemoteProtocolError should be transient."""
        error = httpx.RemoteProtocolError("Remote closed connection")
        assert is_transient(error) is True

    def test_aiohttp_client_connection_error(self):
        """aiohttp.ClientConnectionError should be transient."""
        error = aiohttp.ClientConnectionError("Connection failed")
        assert is_transient(error) is True

    def test_socket_connection_refused(self):
        """Socket ECONNREFUSED error should be transient."""
        error = socket.error(errno.ECONNREFUSED, "Connection refused")
        assert is_transient(error) is True

    def test_socket_connection_reset(self):
        """Socket ECONNRESET error should be transient."""
        error = socket.error(errno.ECONNRESET, "Connection reset by peer")
        assert is_transient(error) is True

    def test_socket_connection_aborted(self):
        """Socket ECONNABORTED error should be transient."""
        error = socket.error(errno.ECONNABORTED, "Software caused connection abort")
        assert is_transient(error) is True

    def test_socket_broken_pipe(self):
        """Socket EPIPE error should be transient."""
        error = socket.error(errno.EPIPE, "Broken pipe")
        assert is_transient(error) is True


class TestDNSErrors:
    """Test DNS resolution failure detection."""

    def test_httpx_connect_error_dns_message(self):
        """httpx.ConnectError with DNS message should be transient."""
        error = httpx.ConnectError("Failed to resolve hostname")
        assert is_transient(error) is True
        category = get_error_category(error)
        assert category in ('connection', 'dns')

    def test_aiohtp_dns_error(self):
        """aiohttp.ClientConnectionError with DNS message should be transient."""
        error = aiohttp.ClientConnectionError("Cannot resolve hostname")
        assert is_transient(error) is True

    def test_socket_host_unreachable(self):
        """Socket EHOSTUNREACH should be transient."""
        error = socket.error(errno.EHOSTUNREACH, "No route to host")
        assert is_transient(error) is True

    def test_socket_host_down(self):
        """Socket EHOSTDOWN should be transient."""
        error = socket.error(errno.EHOSTDOWN, "Host is down")
        assert is_transient(error) is True

    def test_socket_network_unreachable(self):
        """Socket ENETUNREACH should be transient."""
        error = socket.error(errno.ENETUNREACH, "Network unreachable")
        assert is_transient(error) is True


class TestHTTPServerErrors:
    """Test HTTP 5xx server error detection - all should be transient."""

    def test_httpx_500_internal_server_error(self):
        """HTTP 500 should be transient."""
        response = Mock(status_code=500)
        error = httpx.HTTPStatusError("Internal Server Error", request=Mock(), response=response)
        assert is_transient(error) is True

    def test_httpx_502_bad_gateway(self):
        """HTTP 502 should be transient."""
        response = Mock(status_code=502)
        error = httpx.HTTPStatusError("Bad Gateway", request=Mock(), response=response)
        assert is_transient(error) is True

    def test_httpx_503_service_unavailable(self):
        """HTTP 503 should be transient."""
        response = Mock(status_code=503)
        error = httpx.HTTPStatusError("Service Unavailable", request=Mock(), response=response)
        assert is_transient(error) is True

    def test_httpx_504_gateway_timeout(self):
        """HTTP 504 should be transient."""
        response = Mock(status_code=504)
        error = httpx.HTTPStatusError("Gateway Timeout", request=Mock(), response=response)
        assert is_transient(error) is True

    def test_httpx_507_insufficient_storage(self):
        """HTTP 507 should be transient."""
        response = Mock(status_code=507)
        error = httpx.HTTPStatusError("Insufficient Storage", request=Mock(), response=response)
        assert is_transient(error) is True

    def test_aiohttp_500_error(self):
        """aiohttp with 500 status should be transient."""
        error = aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=500,
            message="Internal Server Error"
        )
        assert is_transient(error) is True

    def test_aiohttp_503_error(self):
        """aiohttp with 503 status should be transient."""
        error = aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=503,
            message="Service Unavailable"
        )
        assert is_transient(error) is True


class TestHTTPClientErrors:
    """Test HTTP 4xx client error detection - should be permanent (except 429)."""

    def test_httpx_400_bad_request(self):
        """HTTP 400 should be permanent."""
        response = Mock(status_code=400)
        error = httpx.HTTPStatusError("Bad Request", request=Mock(), response=response)
        assert is_transient(error) is False

    def test_httpx_401_unauthorized(self):
        """HTTP 401 should be permanent."""
        response = Mock(status_code=401)
        error = httpx.HTTPStatusError("Unauthorized", request=Mock(), response=response)
        assert is_transient(error) is False

    def test_httpx_403_forbidden(self):
        """HTTP 403 should be permanent."""
        response = Mock(status_code=403)
        error = httpx.HTTPStatusError("Forbidden", request=Mock(), response=response)
        assert is_transient(error) is False

    def test_httpx_404_not_found(self):
        """HTTP 404 should be permanent."""
        response = Mock(status_code=404)
        error = httpx.HTTPStatusError("Not Found", request=Mock(), response=response)
        assert is_transient(error) is False

    def test_httpx_422_unprocessable_entity(self):
        """HTTP 422 should be permanent."""
        response = Mock(status_code=422)
        error = httpx.HTTPStatusError("Unprocessable Entity", request=Mock(), response=response)
        assert is_transient(error) is False

    def test_httpx_429_rate_limit_transient(self):
        """HTTP 429 should be transient (rate limiting)."""
        response = Mock(status_code=429)
        error = httpx.HTTPStatusError("Too Many Requests", request=Mock(), response=response)
        assert is_transient(error) is True

    def test_aiohttp_404_error(self):
        """aiohttp with 404 status should be permanent."""
        error = aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=404,
            message="Not Found"
        )
        assert is_transient(error) is False

    def test_aiohttp_403_error(self):
        """aiohttp with 403 status should be permanent."""
        error = aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=403,
            message="Forbidden"
        )
        assert is_transient(error) is False


class TestPermanentSocketErrors:
    """Test socket errors that should be permanent."""

    def test_socket_permission_denied(self):
        """Socket EACCES should be permanent."""
        error = socket.error(errno.EACCES, "Permission denied")
        assert is_transient(error) is False

    def test_socket_address_in_use(self):
        """Socket EADDRINUSE should be permanent."""
        error = socket.error(errno.EADDRINUSE, "Address already in use")
        assert is_transient(error) is False

    def test_socket_address_not_available(self):
        """Socket EADDRNOTAVAIL should be permanent."""
        error = socket.error(errno.EADDRNOTAVAIL, "Address not available")
        assert is_transient(error) is False

    def test_socket_invalid_argument(self):
        """Socket EINVAL should be permanent."""
        error = socket.error(errno.EINVAL, "Invalid argument")
        assert is_transient(error) is False

    def test_socket_no_buffer_space(self):
        """Socket ENOBUFS should be permanent."""
        error = socket.error(errno.ENOBUFS, "No buffer space available")
        assert is_transient(error) is False


class TestNetworkErrors:
    """Test general network error detection."""

    def test_httpx_read_error(self):
        """httpx.ReadError should be transient."""
        error = httpx.ReadError("Read failed")
        assert is_transient(error) is True

    def test_httpx_write_error(self):
        """httpx.WriteError should be transient."""
        error = httpx.WriteError("Write failed")
        assert is_transient(error) is True

    def test_httpx_local_protocol_error(self):
        """httpx.LocalProtocolError should be transient."""
        error = httpx.LocalProtocolError("Local protocol error")
        assert is_transient(error) is True

    def test_httpx_unsupported_protocol_permanent(self):
        """httpx.UnsupportedProtocol should be permanent."""
        error = httpx.UnsupportedProtocol("Unsupported protocol")
        assert is_transient(error) is False

    def test_httpx_http_error_base(self):
        """httpx.HTTPError base class should be transient."""
        error = httpx.HTTPError("Generic HTTP error")
        assert is_transient(error) is True

    def test_aiohttp_client_error_base(self):
        """aiohttp.ClientError base class should be transient."""
        error = aiohttp.ClientError("Generic client error")
        assert is_transient(error) is True


class TestOSErrors:
    """Test OSError classification."""

    def test_os_error_timeout(self):
        """OSError with ETIMEDOUT should be transient."""
        error = OSError(errno.ETIMEDOUT, "Operation timed out")
        assert is_transient(error) is True

    def test_os_error_connection_refused(self):
        """OSError with ECONNREFUSED should be transient."""
        error = OSError(errno.ECONNREFUSED, "Connection refused")
        assert is_transient(error) is True

    def test_os_error_host_unreachable(self):
        """OSError with EHOSTUNREACH should be transient."""
        error = OSError(errno.EHOSTUNREACH, "No route to host")
        assert is_transient(error) is True

    def test_os_error_generic(self):
        """OSError without recognized errno should be permanent."""
        error = OSError(errno.EBADF, "Bad file descriptor")
        assert is_transient(error) is False


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_none_error(self):
        """None error should return False."""
        assert is_transient(None) is False

    def test_unknown_exception_type(self):
        """Unknown exception types should be permanent (conservative)."""
        error = ValueError("Some random error")
        assert is_transient(error) is False

    def test_runtime_error(self):
        """RuntimeError should be permanent."""
        error = RuntimeError("Something went wrong")
        assert is_transient(error) is False

    def test_generic_exception(self):
        """Generic Exception should be permanent."""
        error = Exception("Generic error")
        assert is_transient(error) is False

    def test_socket_error_without_errno(self):
        """socket.error without errno should be transient (conservative)."""
        error = socket.error("Socket error without errno")
        assert is_transient(error) is True


class TestErrorCategories:
    """Test get_error_category() function."""

    def test_category_timeout(self):
        """Timeout errors should return 'timeout' category."""
        assert get_error_category(httpx.TimeoutException("timeout")) == 'timeout'
        assert get_error_category(socket.timeout("timeout")) == 'timeout'

    def test_category_connection(self):
        """Connection errors should return 'connection' category."""
        assert get_error_category(httpx.ConnectError("connection refused")) == 'connection'
        assert get_error_category(aiohttp.ClientConnectionError("connection failed")) == 'connection'

    def test_category_dns(self):
        """DNS-related errors should return 'dns' category."""
        error = httpx.ConnectError("Cannot resolve hostname")
        assert get_error_category(error) in ('connection', 'dns')

    def test_category_server_error(self):
        """HTTP 5xx errors should return 'server_error' category."""
        response = Mock(status_code=500)
        error = httpx.HTTPStatusError("Internal Server Error", request=Mock(), response=response)
        assert get_error_category(error) == 'server_error'

    def test_category_rate_limit(self):
        """HTTP 429 should return 'rate_limit' category."""
        response = Mock(status_code=429)
        error = httpx.HTTPStatusError("Too Many Requests", request=Mock(), response=response)
        assert get_error_category(error) == 'rate_limit'

    def test_category_client_error(self):
        """HTTP 4xx errors should return 'client_error' category."""
        response = Mock(status_code=404)
        error = httpx.HTTPStatusError("Not Found", request=Mock(), response=response)
        assert get_error_category(error) == 'client_error'

    def test_category_network(self):
        """General network errors should return 'network' category."""
        assert get_error_category(httpx.ReadError("Read failed")) == 'network'
        assert get_error_category(httpx.WriteError("Write failed")) == 'network'

    def test_category_unknown(self):
        """Unknown errors should return 'unknown' category."""
        assert get_error_category(None) == 'unknown'
        assert get_error_category(ValueError("random error")) == 'unknown'

    def test_category_aiohttp_500(self):
        """aiohttp with 500 should return 'server_error' category."""
        error = aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=500,
            message="Internal Server Error"
        )
        assert get_error_category(error) == 'server_error'

    def test_category_aiohttp_404(self):
        """aiohttp with 404 should return 'client_error' category."""
        error = aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=404,
            message="Not Found"
        )
        assert get_error_category(error) == 'client_error'
