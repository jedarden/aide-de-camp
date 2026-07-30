# HTTP/2 Support Implementation for ZAI Proxy Client

## Summary

Implemented comprehensive HTTP/2 support for the ZAI proxy client in `src/escalate/llm.py`. The implementation reduces per-request overhead through multiplexing and connection reuse.

## Changes Made

### 1. Dependency Update (`pyproject.toml`)
- Updated `httpx>=0.27.0` → `httpx[http2]>=0.27.0`
- Explicitly includes HTTP/2 support via the `http2` extra

### 2. Enhanced Client Implementation (`src/escalate/llm.py`)
- **Already implemented**: HTTP/2 was already configured in the `_get_client()` method (line 254: `http2=True`)
- **Enhanced logging**:
  - Warmup method now logs protocol version and HTTP version used
  - Call method now logs HTTP/2 usage for each request
  - Existing fallback to HTTP/1.1 if HTTP/2 fails

### 3. Test Suite (`test/test_http2_support.py`)
Created comprehensive test suite covering:
- Client initialization with HTTP/2 enabled
- Fallback to HTTP/1.1 on initialization error
- HTTP/2 optimization headers presence
- Connection pooling configuration for HTTP/2
- Global client HTTP/2 support
- Actual proxy connection verification (integration test)

## Acceptance Criteria Met

✅ **Upgrade httpx client to support HTTP/2**
- Updated dependency to `httpx[http2]>=0.27.0`

✅ **Configure http2=True in the ZAI proxy client**
- Already configured at line 254 in `src/escalate/llm.py`

✅ **Test that HTTP/2 negotiation works with the proxy**
- Created 6 comprehensive tests, all passing

✅ **Verify no breaking changes to existing functionality**
- Existing tests pass (unrelated pre-existing test failures are router/flag check issues)
- HTTP/2 implementation includes fallback to HTTP/1.1

✅ **Add logging to confirm HTTP/2 is being used**
- Enhanced warmup logging: logs protocol and HTTP version
- Enhanced call logging: logs HTTP/2 usage per request

## HTTP/2 Benefits

- **Multiplexing**: Multiple concurrent requests over single connection
- **Connection reuse**: Reduced TLS handshake overhead
- **Header compression**: Lower bandwidth usage
- **Better latency**: Reduced per-request overhead

## Configuration

The client uses optimized connection pooling for HTTP/2:
- `max_keepalive_connections: 50` - Large pool for HTTP/2 multiplexing
- `max_connections: 150` - Support for high parallelism
- `keepalive_expiry: 180.0` - Extended keepalive (3 minutes)

## Testing

All HTTP/2 tests pass:
```bash
.venv/bin/python -m pytest test/test_http2_support.py -v
# 6 passed in 0.72s
```

## Rollback

The implementation includes automatic fallback to HTTP/1.1 if HTTP/2 initialization fails, ensuring backward compatibility.
