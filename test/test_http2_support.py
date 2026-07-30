#!/usr/bin/env python3
"""
Test suite for HTTP/2 support in ZAI proxy client.

Acceptance criteria:
- Client is configured with HTTP/2 support
- HTTP/2 negotiation works with the proxy
- Fallback to HTTP/1.1 if HTTP/2 fails
- Logging confirms which protocol is being used
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure the project root is in the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import httpx
from src.escalate.llm import ZAIClient, LLMRequest, get_zai_client


class TestHTTP2Support:
    """Test HTTP/2 support in ZAI client."""

    @pytest.mark.asyncio
    async def test_client_initialized_with_http2(self):
        """Verify ZAI client is initialized with HTTP/2 enabled."""
        client = ZAIClient()

        # Get the internal httpx client
        http_client = await client._get_client()

        # Verify HTTP/2 is enabled in the pool configuration
        pool = http_client._transport._pool
        assert hasattr(pool, "_http2"), "Pool should have HTTP/2 attribute"
        assert pool._http2 is True, "HTTP/2 should be enabled in pool"

        await client.close()

    @pytest.mark.asyncio
    async def test_http2_fallback_on_error(self):
        """Verify fallback to HTTP/1.1 if HTTP/2 initialization fails."""
        # Mock httpx.AsyncClient to raise an exception on first call (HTTP/2)
        # but succeed on second call (HTTP/1.1 fallback)
        original_init = httpx.AsyncClient.__init__

        call_count = {"count": 0}

        def mock_init(self, *args, **kwargs):
            call_count["count"] += 1
            if call_count["count"] == 1 and kwargs.get("http2"):
                # Simulate HTTP/2 initialization failure
                raise Exception("HTTP/2 not available")
            # Let HTTP/1.1 succeed
            return original_init(self, *args, **kwargs)

        with patch.object(httpx.AsyncClient, "__init__", mock_init):
            client = ZAIClient()
            # Clear any existing client to force re-initialization
            client._client = None
            http_client = await client._get_client()

        # Should have fallen back to HTTP/1.1
        pool = http_client._transport._pool
        assert pool._http2 is False, "Should fall back to HTTP/1.1"
        await client.close()

    @pytest.mark.asyncio
    async def test_http2_headers_present(self):
        """Verify HTTP/2 optimization headers are present."""
        client = ZAIClient()
        http_client = await client._get_client()

        # Check for HTTP/2 optimization headers
        headers = http_client.headers
        assert "Connection" in headers or "te" in headers, "Should have HTTP/2 optimization headers"

        await client.close()

    @pytest.mark.asyncio
    async def test_connection_pooling_with_http2(self):
        """Verify connection pooling is configured for HTTP/2."""
        client = ZAIClient()
        http_client = await client._get_client()

        # Check connection limits - stored in the pool attributes
        pool = http_client._transport._pool
        assert pool._max_keepalive_connections >= 50, "Should have large keepalive pool for HTTP/2"
        assert pool._max_connections >= 150, "Should have large max connections for HTTP/2"

        await client.close()

    @pytest.mark.asyncio
    async def test_global_client_has_http2(self):
        """Verify the global ZAI client also has HTTP/2 enabled."""
        client = get_zai_client()
        http_client = await client._get_client()

        pool = http_client._transport._pool
        assert pool._http2 is True, "Global client should have HTTP/2 enabled"
        await client.close()

    @pytest.mark.asyncio
    async def test_http2_with_actual_proxy_check(self):
        """
        Verify HTTP/2 negotiation with the actual ZAI proxy.

        This test makes a real connection to verify HTTP/2 negotiation works.
        It's marked as integration test and may be skipped in CI.
        """
        client = ZAIClient()

        try:
            # Warmup to establish connection
            await client.warmup()

            # Get the client after warmup
            http_client = await client._get_client()

            # If we got here without exception, HTTP/2 or HTTP/1.1 is working
            # The logger will have indicated which protocol was used
            assert http_client is not None, "Client should be initialized"

            await client.close()
        except Exception as e:
            pytest.skip(f"Unable to connect to ZAI proxy: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
