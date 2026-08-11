"""
Transient network error detection and classification.

Provides is_transient() function to determine if an error is temporary
(transient) or permanent. Transient errors are candidates for retry logic;
permanent errors should fail immediately without retry.

This module handles exceptions from:
- httpx (used in most fetch operations)
- aiohttp (used in ambient monitoring)
- Standard library socket/timeout errors
"""

import errno
import socket
from typing import Any, Union

import httpx
import aiohttp


def is_transient(error: Any) -> bool:
    """
    Determine if an error is transient (temporary) or permanent.

    Transient errors are temporary failures that may resolve with retry:
    - Timeouts (socket, HTTP read, connect)
    - Connection resets and refused connections
    - DNS resolution failures
    - HTTP 5xx server errors
    - Network unreachable errors

    Permanent errors should not be retried:
    - HTTP 4xx client errors (except 429 Too Many Requests)
    - HTTP 401, 403 (authentication/authorization)
    - HTTP 404 (not found)
    - HTTP 422 (unprocessable entity)
    - SSL certificate verification errors

    Args:
        error: Exception or error object to classify

    Returns:
        True if error is transient (retry-eligible), False if permanent
    """
    if error is None:
        return False

    # Handle httpx exceptions
    if isinstance(error, httpx.HTTPStatusError):
        return _is_http_status_transient(error.response.status_code)

    if isinstance(error, httpx.TimeoutException):
        # All timeouts are transient
        return True

    # Check for permanent errors before generic HTTPError
    if isinstance(error, httpx.UnsupportedProtocol):
        # Unsupported protocol is a permanent error
        return False

    if isinstance(error, httpx.NetworkError):
        # Most network errors are transient
        return _is_httpx_network_error_transient(error)

    if isinstance(error, httpx.HTTPError):
        # Base HTTPError - be conservative and mark as transient
        # This includes stream errors, protocol errors, etc.
        return True

    # Handle aiohttp exceptions
    if isinstance(error, aiohttp.ClientResponseError):
        status = error.status if hasattr(error, 'status') else None
        if status:
            return _is_http_status_transient(status)
        # No status available - treat as transient
        return True

    if isinstance(error, (aiohttp.ClientTimeout, aiohttp.ServerTimeoutError)):
        # All timeouts are transient
        return True

    if isinstance(error, aiohttp.ClientConnectionError):
        # Connection errors are transient (includes resets, refused, etc.)
        return True

    if isinstance(error, aiohttp.ClientError):
        # Base aiohttp client error - conservative: treat as transient
        return True

    # Handle TimeoutError (includes socket.timeout in Python 3)
    if isinstance(error, TimeoutError):
        # All timeouts are transient
        return True

    # Handle OSError and subclasses (including socket.error)
    # Note: socket.error is an alias for OSError in Python 3
    if isinstance(error, OSError):
        return _is_os_error_transient(error)

    # Handle Git-specific errors (from src.action.steps.git_validation)
    # Check class name to avoid circular import
    error_class_name = error.__class__.__name__
    error_module = error.__class__.__module__

    # GitNetworkError - transient (network issues)
    if error_class_name == "GitNetworkError":
        return True

    # GitAuthenticationError, GitConflictError - permanent (do not retry)
    if error_class_name in ("GitAuthenticationError", "GitConflictError"):
        return False

    # Unknown error type - be conservative and treat as permanent
    return False


def _is_http_status_transient(status: int) -> bool:
    """
    Classify HTTP status codes as transient or permanent.

    Transient (retry-eligible):
    - 429 Too Many Requests (rate limiting - retry with backoff)
    - 500 Internal Server Error
    - 502 Bad Gateway
    - 503 Service Unavailable
    - 504 Gateway Timeout
    - 507 Insufficient Storage (rare, but server-side)
    - 599 Network Connect Timeout Error (some proxies)

    Permanent (do not retry):
    - 400 Bad Request
    - 401 Unauthorized
    - 403 Forbidden
    - 404 Not Found
    - 405 Method Not Allowed
    - 406 Not Acceptable
    - 409 Conflict (usually permanent unless retrying with different data)
    - 410 Gone
    - 412 Precondition Failed
    - 413 Payload Too Large
    - 414 URI Too Long
    - 415 Unsupported Media Type
    - 422 Unprocessable Entity
    - 423 Locked
    - 424 Failed Dependency
    - 426 Upgrade Required
    - 428 Precondition Required
    - 431 Request Header Fields Too Large
    - 451 Unavailable For Legal Reasons

    Args:
        status: HTTP status code

    Returns:
        True if status indicates transient error, False if permanent
    """
    # Rate limiting - transient (retry with backoff)
    if status == 429:
        return True

    # Server errors (5xx) - all transient except 501 (Not Implemented)
    if 500 <= status <= 599:
        return status not in (501, 505, 510)

    # All other status codes (4xx and others) - permanent
    return False


def _is_httpx_network_error_transient(error: httpx.NetworkError) -> bool:
    """
    Classify httpx.NetworkError subclasses as transient or permanent.

    Transient network errors:
    - httpx.RemoteProtocolError (server closed connection, etc.)
    - httpx.LocalProtocolError (usually transient unless it's about framing)
    - httpx.ConnectError (connection refused, timeout, etc.)
    - httpx.ReadError (network read failures)
    - httpx.WriteError (network write failures)

    Args:
        error: httpx.NetworkError instance

    Returns:
        True if transient, False if permanent
    """
    # Most httpx network errors are transient
    # Specific cases that might be permanent:
    if isinstance(error, httpx.UnsupportedProtocol):
        # Protocol not supported - permanent
        return False

    if isinstance(error, httpx.ProtocolError):
        # Protocol errors are usually transient (connection resets, etc.)
        return True

    # ConnectError, ReadError, WriteError, etc. - all transient
    return True


def _is_socket_error_transient(error: socket.error) -> bool:
    """
    Classify socket.error as transient or permanent.

    Transient socket errors (errno-based):
    - errno.ECONNREFUSED (111): Connection refused (server temporarily down)
    - errno.ECONNRESET (104): Connection reset by peer
    - errno.ETIMEDOUT (110): Connection timed out
    - errno.EHOSTUNREACH (113): No route to host
    - errno.EHOSTDOWN (112): Host is down
    - errno.ENETUNREACH (101): Network unreachable
    - errno.ECONNABORTED (103): Software caused connection abort
    - errno.EPIPE (32): Broken pipe

    Permanent socket errors:
    - errno.EACCES (13): Permission denied
    - errno.EADDRINUSE (98): Address already in use
    - errno.EADDRNOTAVAIL (99): Address not available
    - errno.EINVAL (22): Invalid argument
    - errno.ENOBUFS (105): No buffer space available

    Args:
        error: socket.error instance

    Returns:
        True if transient, False if permanent
    """
    if hasattr(error, 'errno'):
        error_code = error.errno

        # Transient network errors
        transient_codes = {
            errno.ECONNREFUSED,    # Connection refused
            errno.ECONNRESET,     # Connection reset
            errno.ETIMEDOUT,      # Timeout
            errno.EHOSTUNREACH,   # Host unreachable
            errno.EHOSTDOWN,      # Host down
            errno.ENETUNREACH,    # Network unreachable
            errno.ECONNABORTED,   # Connection aborted
            errno.EPIPE,          # Broken pipe
        }

        if error_code in transient_codes:
            return True

        # Permanent errors
        permanent_codes = {
            errno.EACCES,         # Permission denied
            errno.EADDRINUSE,     # Address in use
            errno.EADDRNOTAVAIL,  # Address not available
            errno.EINVAL,         # Invalid argument
            errno.ENOBUFS,        # No buffer space
        }

        if error_code in permanent_codes:
            return False

    # No errno or unknown code - be conservative and treat as transient
    return True


def _is_os_error_transient(error: OSError) -> bool:
    """
    Classify OSError as transient or permanent.

    Uses errno-based classification. Since socket.error is an alias for
    OSError in Python 3, we handle both here using errno codes.

    Args:
        error: OSError instance

    Returns:
        True if transient, False if permanent
    """
    if hasattr(error, 'errno') and error.errno is not None:
        error_code = error.errno

        # Transient: network-related timeouts and connection issues
        transient_codes = {
            errno.ETIMEDOUT,      # Timeout
            errno.ECONNREFUSED,   # Connection refused
            errno.ECONNRESET,     # Connection reset
            errno.EHOSTUNREACH,   # Host unreachable
            errno.EHOSTDOWN,      # Host is down
            errno.ENETUNREACH,    # Network unreachable
            errno.ECONNABORTED,   # Connection aborted
            errno.EPIPE,          # Broken pipe
        }

        if error_code in transient_codes:
            return True

        # Permanent errors
        permanent_codes = {
            errno.EACCES,         # Permission denied
            errno.EADDRINUSE,     # Address in use
            errno.EADDRNOTAVAIL,  # Address not available
            errno.EINVAL,         # Invalid argument
            errno.ENOBUFS,        # No buffer space
            errno.EBADF,          # Bad file descriptor
        }

        if error_code in permanent_codes:
            return False

        # Unknown errno but still an OSError - treat as permanent
        return False

    # OSError without errno or with errno=None - conservative: treat as transient (likely network issue)
    return True


def get_error_category(error: Any) -> str:
    """
    Get a human-readable category for an error.

    Useful for logging and debugging. Returns one of:
    - 'timeout': Timeout errors (socket, HTTP, connect, read)
    - 'connection': Connection errors (reset, refused, unreachable)
    - 'dns': DNS resolution failures
    - 'server_error': HTTP 5xx server errors
    - 'rate_limit': HTTP 429 rate limiting
    - 'client_error': HTTP 4xx client errors (permanent)
    - 'network': General network errors
    - 'unknown': Unknown error type

    Args:
        error: Exception or error object

    Returns:
        String category name
    """
    if error is None:
        return 'unknown'

    # Timeouts
    if isinstance(error, (httpx.TimeoutException, aiohttp.ClientTimeout,
                         aiohttp.ServerTimeoutError, socket.timeout)):
        return 'timeout'

    # HTTP status errors
    if isinstance(error, (httpx.HTTPStatusError, aiohttp.ClientResponseError)):
        status = None
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
        elif isinstance(error, aiohttp.ClientResponseError) and hasattr(error, 'status'):
            status = error.status

        if status:
            if status == 429:
                return 'rate_limit'
            elif 500 <= status <= 599:
                return 'server_error'
            elif 400 <= status <= 499:
                return 'client_error'

    # Connection errors
    if isinstance(error, (httpx.ConnectError, aiohttp.ClientConnectionError)):
        # Check for DNS-specific errors
        if 'dns' in str(error).lower() or 'resolve' in str(error).lower():
            return 'dns'
        return 'connection'

    # Network errors
    if isinstance(error, (httpx.NetworkError, httpx.HTTPError,
                         aiohttp.ClientError, socket.error)):
        return 'network'

    return 'unknown'
