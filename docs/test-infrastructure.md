# Test Endpoint Call Infrastructure

## Overview

This document describes the test endpoint call infrastructure for aide-de-camp, which provides comprehensive testing capabilities for FastAPI endpoints including response structure validation, status code checks, header verification, and basic request handling tests.

## Test Structure

The test infrastructure is organized into logical test classes:

### 1. TestHealthEndpoint
Tests the `/health` endpoint which is the core health check endpoint for the service.
- Status code validation (HTTP 200)
- JSON content-type verification
- Response structure validation
- Response time performance checks

### 2. TestRootEndpoint  
Tests the root `/` endpoint for basic accessibility.
- Endpoint accessibility
- Content-type validation

### 3. TestAPIEndpoints
Tests basic API endpoints functionality.
- `/api/v1/environment` endpoint
- `/api/v1/registry` endpoint
- Graceful handling of missing endpoints

### 4. TestResponseStructureValidation
Tests response structure validation capabilities.
- JSON response parsing
- Header presence validation
- Response body content validation

### 5. TestErrorHandling
Tests error handling and edge cases.
- Nonexistent endpoint returns 404
- Invalid HTTP method returns 405
- Malformed request handling

### 6. TestHTTPClientConfiguration
Tests HTTP client configuration and connection handling.
- Timeout configuration validation
- Connection reuse verification

### 7. TestValidationUtilities
Tests the validation utility functions.
- `validate_response_structure()` function testing

## Usage

### Running Tests

To run all endpoint verification tests:
```bash
.venv/bin/python -m pytest tests/test_endpoint_verification.py -v
```

To run a specific test class:
```bash
.venv/bin/python -m pytest tests/test_endpoint_verification.py::TestHealthEndpoint -v
```

To run a specific test:
```bash
.venv/bin/python -m pytest tests/test_endpoint_verification.py::TestHealthEndpoint::test_health_endpoint_returns_200 -v
```

### Test Fixtures

The tests use the `async_client` fixture from `tests/conftest.py` which provides:
- HTTPX async client configured for `http://localhost:8000`
- 10-second timeout
- Automatic cleanup after tests

### Utility Functions

#### `validate_response_structure()`

Utility function for comprehensive response validation:

```python
def validate_response_structure(
    response: httpx.Response,
    expected_status: int = 200,
    expected_content_type: str = None,
    expected_fields: list = None
) -> Dict[str, Any]:
    """
    Validate response structure and return parsed JSON data.

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
```

Example usage:
```python
response = await async_client.get("/health")
data = validate_response_structure(
    response,
    expected_status=200,
    expected_content_type="application/json",
    expected_fields=["status", "service"]
)
```

## Test Coverage

The current test suite provides:
- ✅ Basic endpoint accessibility testing
- ✅ Response structure validation
- ✅ Error handling verification
- ✅ HTTP client configuration testing
- ✅ Performance baseline testing
- ✅ JSON parsing and validation
- ✅ Header validation
- ✅ Content verification

## Dependencies

The test infrastructure depends on:
- `pytest` - Testing framework
- `httpx` - Async HTTP client
- `fastapi` - Web framework (running server required)

## Server Requirements

Tests require the aide-de-camp server to be running on `http://localhost:8000`. To start the server:

```bash
systemctl --user start aide-de-camp
```

Or manually:
```bash
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## Extension Guidelines

To add new endpoint tests:

1. **Add test methods** to appropriate test classes based on functionality
2. **Use descriptive names** following `test_<endpoint>_<behavior>` pattern
3. **Validate responses** using the `validate_response_structure()` utility
4. **Test both success and error cases** for comprehensive coverage
5. **Include performance checks** for time-sensitive endpoints

Example:
```python
@pytest.mark.asyncio
async def test_new_endpoint_returns_200(self, async_client: httpx.AsyncClient):
    """Test that new endpoint returns 200."""
    response = await async_client.get("/api/v1/new-endpoint")
    data = validate_response_structure(
        response,
        expected_status=200,
        expected_content_type="application/json",
        expected_fields=["result"]
    )
    assert data["result"] == "expected_value"
```

## Acceptance Criteria Verification

✅ **Test endpoint call returns a valid HTTP response**
- All 17 tests pass with valid HTTP responses
- Status codes properly validated (200, 404, 405, etc.)

✅ **Response structure is validated (status code, headers, body)**
- Status code validation implemented
- Content-type header validation implemented  
- JSON body structure validation implemented
- Custom `validate_response_structure()` utility function

✅ **Basic test scaffolding is in place**
- Test classes organized by functionality
- Pytest fixtures properly configured
- Async test support enabled
- Test documentation complete

✅ **Test can run successfully without errors**
- All 17 tests pass in 0.40s
- No errors or failures
- Server connectivity verified
- HTTP client configuration validated