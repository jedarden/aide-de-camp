"""
Transient error detection utility for Git network operations.

Provides is_transient_error() function to identify retryable network errors
when working with Git operations over HTTP/HTTPS.

This module focuses on:
- Timeout errors from asyncio and httpx
- Connection errors from network failures
- HTTP 5xx server errors
- Distinguishing permanent errors (401, 403, 409) that should not be retried
"""

import asyncio
from typing import Any, Union

import httpx


def is_transient_error(error: Any) -> bool:
    """
    Determine if an error is transient (temporary) or permanent.

    Transient errors are temporary failures that may resolve with retry:
    - Timeouts (asyncio.TimeoutError, httpx.TimeoutException)
    - Connection errors (httpx.ConnectError, ConnectionError)
    - HTTP 5xx server errors (500, 502, 503, 504)
    - Network errors (httpx.NetworkError)

    Permanent errors should not be retried:
    - HTTP 401 Unauthorized (authentication issues)
    - HTTP 403 Forbidden (authorization issues)
    - HTTP 409 Conflict (concurrent modification conflicts)
    - HTTP 422 Unprocessable Entity (validation errors)
    - HTTP 429 Rate limiting (requires exponential backoff, may be considered transient)
    - SSL/protocol errors (permanent configuration issues)

    Args:
        error: Exception or error object to classify

    Returns:
        True if error is transient (retry-eligible), False if permanent
    """
    if error is None:
        return False

    # Handle asyncio.TimeoutError
    if isinstance(error, asyncio.TimeoutError):
        return True

    # Handle standard library TimeoutError
    if isinstance(error, TimeoutError):
        return True

    # Handle ConnectionError
    if isinstance(error, ConnectionError):
        return True

    # Handle httpx exceptions
    if isinstance(error, httpx.TimeoutException):
        # All httpx timeouts are transient
        return True

    if isinstance(error, httpx.ConnectError):
        # Connection failures are transient
        return True

    if isinstance(error, httpx.NetworkError):
        # Most network errors are transient
        return True

    if isinstance(error, httpx.HTTPStatusError):
        # Check HTTP status code
        status_code = error.response.status_code
        return _is_http_status_transient(status_code)

    if isinstance(error, httpx.HTTPError):
        # Base HTTPError - be conservative and treat as transient
        # This includes stream errors, protocol errors, etc.
        return True

    # Unknown error type - be conservative and treat as permanent
    return False


def _is_http_status_transient(status: int) -> bool:
    """
    Classify HTTP status codes as transient or permanent.

    Transient (retry-eligible):
    - 500 Internal Server Error
    - 502 Bad Gateway
    - 503 Service Unavailable
    - 504 Gateway Timeout
    - 429 Too Many Requests (rate limiting - retry with backoff)

    Permanent (do not retry):
    - 400 Bad Request
    - 401 Unauthorized (authentication required)
    - 403 Forbidden (authorization failed)
    - 404 Not Found
    - 409 Conflict (concurrent modification)
    - 422 Unprocessable Entity (validation errors)
    - All other 4xx client errors

    Args:
        status: HTTP status code

    Returns:
        True if status indicates transient error, False if permanent
    """
    # Rate limiting - transient (retry with backoff)
    if status == 429:
        return True

    # Server errors (5xx) - transient
    if 500 <= status <= 599:
        return True

    # All other status codes (4xx) - permanent
    return False


def get_error_type(error: Any) -> str:
    """
    Get a human-readable error type for logging/debugging.

    Returns one of:
    - 'timeout': Timeout errors
    - 'connection': Connection errors
    - 'server_error': HTTP 5xx errors
    - 'rate_limit': HTTP 429 rate limiting
    - 'client_error': HTTP 4xx errors (permanent)
    - 'network': General network errors
    - 'unknown': Unknown error type

    Args:
        error: Exception or error object

    Returns:
        String error type
    """
    if error is None:
        return 'unknown'

    # Timeouts
    if isinstance(error, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return 'timeout'

    # Connection errors
    if isinstance(error, (ConnectionError, httpx.ConnectError)):
        return 'connection'

    # HTTP status errors
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 429:
            return 'rate_limit'
        elif 500 <= status <= 599:
            return 'server_error'
        elif 400 <= status <= 499:
            return 'client_error'

    # Protocol errors
    if isinstance(error, (httpx.RemoteProtocolError, httpx.LocalProtocolError)):
        return 'network'

    # Network errors
    if isinstance(error, httpx.NetworkError):
        return 'network'

    # Base HTTPError
    if isinstance(error, httpx.HTTPError):
        return 'network'

    return 'unknown'
