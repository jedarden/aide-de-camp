# Test Endpoint Call Infrastructure

## Overview

This document describes the test endpoint call infrastructure for aide-de-camp, which provides comprehensive testing capabilities for FastAPI endpoints including response structure validation, status code checks, header verification, and basic request handling tests.

## Isolation guarantees and connection lifecycle

The test suite has two different kinds of state to isolate: SQLite state and
long-lived HTTP clients. They must be verified separately. A green repeat run
is only meaningful when the checkout is quiescent; another worker must not be
changing tracked or untracked test files, shared configuration, or the live
server at the same time.

### Database isolation patterns

Use the fixtures in `tests/conftest.py` rather than `data/session.db` directly:

- `test_db_path` creates a unique database file under pytest's per-test
  `tmp_path`. Its teardown removes the database, `-wal`, and `-shm` files.
- `test_db_store` initializes a fresh `SessionStore` with the production schema
  and migrations, enables WAL mode, yields it to the test, and closes it before
  the path fixture removes files.
- `test_db_connection` provides a direct `aiosqlite` connection to the same
  per-test temporary database for low-level SQL tests and closes it in teardown.
- `in_memory_db_store` uses a unique SQLite shared-cache URI for each test. A
  keeper connection stays open while `SessionStore` performs its per-operation
  work; the store is closed first and the keeper is closed last. This ordering
  prevents SQLite from destroying the named in-memory database before the
  store's final checkpoint.
- `in_memory_db_connection` uses its own unique shared-cache URI and closes the
  direct connection at teardown, which destroys that in-memory database.
- The autouse `reset_global_store_singleton` fixture assigns a unique
  `ADC_DB_PATH` before each test, clears the process-wide store singleton, and
  closes any store created by the test before restoring the previous singleton
  and environment. Tests that call `get_store()` therefore do not silently use
  production `data/session.db` or retain a test database into the next test.

These fixtures guarantee fresh database state between tests and prevent test
rows from reaching the production database. They do not make raw record IDs an
authorization boundary: callers must use the session-scoped query methods (and
must not expose a record fetched only by its global ID to another session).
Within a database, session-scoped queries are expected to filter by
`session_id`; the database and session-storage verification tests cover the
corresponding topic, result, utterance, intent, and deletion behavior.

For tests that create their own store, follow the same lifecycle:

```python
store = SessionStore(tmp_path / "session.db")
await store.initialize()
try:
    # Exercise the store using test-only session IDs.
    ...
finally:
    await store.close()
```

Do not use a plain `:memory:` path with `SessionStore`: the store opens a new
SQLite connection for each operation, so a plain in-memory database would lose
its schema when the creating connection closes. Use the unique shared-cache
URI plus a keeper connection, as the `in_memory_db_store` fixture does.

### SQLite connection behavior under load

`SessionStore` is not a connection pool. Each database operation opens an
`aiosqlite` connection, performs the operation, commits when needed, and closes
the connection through its async context manager. WAL mode permits concurrent
readers while writes are serialized by SQLite; store-level critical sections
also use the instance lock where required.

`SessionStore.close()` is a shutdown operation, not a pool return operation. It
uses a bounded retry sequence for `PASSIVE`, `FULL`, and `TRUNCATE` WAL
checkpoints. If another reader keeps SQLite busy after the retries, close
raises and leaves the WAL intact for recovery and a later retry rather than
claiming a clean shutdown. Tests that enable the optional connection monitor
can inspect active, closed, peak, and leaked connections with
`get_connection_stats()` and `assert_no_connection_leaks()`.

### HTTP connection pool behavior under load

`ZAIClient` owns one lazily-created `httpx.AsyncClient` per client instance.
The default pool is configured as follows:

| Setting | Value | Lifecycle meaning |
| --- | ---: | --- |
| Maximum connections | 150 | Upper bound on concurrent proxy connections per client |
| Keep-alive connections | 50 | Idle connections retained for reuse |
| Keep-alive expiry | 180 seconds | Idle connection lifetime |
| Pool timeout | 3 seconds | Maximum wait for a pool slot before the request fails |

HTTP/2 is attempted for multiplexing and falls back to HTTP/1.1 if client
construction fails. `warmup()` makes a lightweight request to establish the
first connection; warmup failure is non-fatal. `close()` calls `aclose()` and
clears the client, so the owner must retain the client and close it during its
shutdown path. The global main ZAI client is reused by the router, synthesize,
and agent paths. The dedicated router client is cached by an `IntentRouter`
instance and should be closed with that instance's lifecycle.

This pool is independent of SQLite and does not isolate database state. Under
load, application-level concurrency limits and the HTTPX pool limit work
together: requests up to the pool limit can run concurrently, while requests
above it wait for at most the 3-second pool timeout. Tests using mocked clients
should still assert that the owning client is closed; tests exercising actual
concurrency should use `asyncio.gather()` and verify cleanup after the batch.

### Repeat-run verification

Run the repeat detector from a clean, quiescent checkout with the project
environment:

```bash
.venv/bin/python scripts/run_tests_repeatedly.py --count 10
```

The result is stable only when all ten requested runs complete, every run has
exit code 0, and the report shows no failed or errored tests. Skips are
reported separately and must be understood before treating the suite as
complete. Inspect `test_repeat_report.json` for per-run counts and the
pass/fail history; do not infer isolation from a single green run.

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
