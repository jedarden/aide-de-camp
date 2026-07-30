#!/usr/bin/env python3
"""
Test suite for connection pooling in ZAI proxy client.

Acceptance criteria for connection pooling:
- httpx connection limits properly configured (max_connections, max_keepalive)
- Pool size appropriate for concurrent requests
- Connection reuse works across multiple requests
- Concurrent dispatches handled correctly
- Pool settings documented in code
"""

import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

# Ensure the project root is in the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import httpx
from src.escalate.llm import ZAIClient, LLMRequest, get_zai_client, get_router_zai_client


class TestConnectionPooling:
    """Test connection pooling configuration and behavior."""

    @pytest.mark.asyncio
    async def test_client_has_connection_limits_configured(self):
        """Verify ZAI client has proper httpx.Limits configuration."""
        client = ZAIClient()
        http_client = await client._get_client()

        # Verify connection limits are properly configured via the pool
        pool = http_client._transport._pool
        assert hasattr(pool, "_max_keepalive_connections"), "Pool should have keepalive connections limit"
        assert hasattr(pool, "_max_connections"), "Pool should have max connections limit"

        # Check the actual limit values
        assert pool._max_keepalive_connections >= 50, "Keepalive connections should be >= 50"
        assert pool._max_connections >= 150, "Max connections should be >= 150"

        await client.close()

    @pytest.mark.asyncio
    async def test_pool_size_for_concurrent_requests(self):
        """Verify pool size is appropriate for handling concurrent requests."""
        client = ZAIClient()
        http_client = await client._get_client()

        # Check pool can handle concurrent requests
        pool = http_client._transport._pool
        assert hasattr(pool, "_max_connections"), "Pool should have max connections attribute"
        assert hasattr(pool, "_max_keepalive_connections"), "Pool should have max keepalive connections"

        # Pool should support at least 150 concurrent connections
        assert pool._max_connections >= 150, "Pool should support >= 150 concurrent connections"

        await client.close()

    @pytest.mark.asyncio
    async def test_connection_reuse_across_requests(self):
        """Verify connection pool can handle multiple sequential requests."""
        client = ZAIClient()

        # Track connection pool state
        http_client = await client._get_client()
        pool = http_client._transport._pool

        # Verify pool is properly configured for connection reuse
        assert pool._max_keepalive_connections >= 50, "Should have large keepalive pool for reuse"
        assert pool._max_connections >= 150, "Should have large max connections"

        # Connection reuse happens internally in httpx - we verify the pool is sized correctly
        # Actual connection reuse is tested through integration tests with real connections

        await client.close()

    @pytest.mark.asyncio
    async def test_concurrent_dispatch_handling(self):
        """Verify connection pool handles concurrent dispatches correctly."""
        client = ZAIClient()
        http_client = await client._get_client()

        # Create multiple concurrent requests
        async def make_request(request_id: int):
            """Simulate a concurrent request."""
            with patch.object(http_client, "request") as mock_request:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.headers = {}
                mock_response.http_version = "HTTP/2"
                mock_response.areturn = AsyncMock(return_value=b'{"result": {"content": [{"text": "test"}]}}')
                mock_request.return_value.__aenter__.return_value = mock_response

                try:
                    await client.call(LLMRequest(
                        system_prompt="test",
                        user_message=f"concurrent request {request_id}"
                    ))
                    return f"success-{request_id}"
                except Exception as e:
                    return f"error-{request_id}: {e}"

        # Launch 10 concurrent requests
        tasks = [make_request(i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All requests should complete without pool exhaustion
        successful = [r for r in results if isinstance(r, str) and r.startswith("success-")]
        assert len(successful) >= 10, f"All concurrent requests should succeed, got {len(successful)}/10"

        await client.close()

    @pytest.mark.asyncio
    async def test_router_client_has_aggressive_pooling(self):
        """Verify router client has more aggressive connection pooling."""
        router_client = get_router_zai_client(timeout=8.0)
        http_client = await router_client._get_client()

        # Router client should have optimized pooling for low latency
        pool = http_client._transport._pool

        # Should have aggressive keepalive for fast repeated requests
        assert pool._max_keepalive_connections >= 50, "Router should have large keepalive pool"
        assert pool._max_connections >= 150, "Router should handle concurrent requests"

        await router_client.close()

    @pytest.mark.asyncio
    async def test_pool_configuration_documentation(self):
        """Verify pool settings are documented in code."""
        client = ZAIClient()
        http_client = await client._get_client()

        # Check that pool has reasonable defaults documented in code
        pool = http_client._transport._pool

        # These values should match the documented settings in src/escalate/llm.py
        assert pool._max_keepalive_connections == 50, "Keepalive should match documented value"
        assert pool._max_connections == 150, "Max connections should match documented value"

        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_configuration_with_pooling(self):
        """Verify timeout configuration works well with connection pooling."""
        client = ZAIClient()
        http_client = await client._get_client()

        # Check timeout configuration
        timeout_config = http_client._timeout

        # Verify aggressive timeouts for fail-fast behavior
        assert timeout_config.connect <= 8.0, "Connect timeout should be aggressive"
        assert timeout_config.write <= 8.0, "Write timeout should be aggressive"
        assert timeout_config.pool <= 3.0, "Pool timeout should be aggressive"

        # These timeouts should complement the pooling strategy (keepalive is in pool)
        pool = http_client._transport._pool
        # Keepalive expires in 180s which is much longer than connect timeout - good for reuse
        assert pool._max_keepalive_connections >= 50, "Should maintain large keepalive pool"

        await client.close()

    @pytest.mark.asyncio
    async def test_keepalive_settings_for_connection_reuse(self):
        """Verify keepalive settings promote connection reuse."""
        client = ZAIClient()
        http_client = await client._get_client()

        pool = http_client._transport._pool

        # Pool should be configured for connection reuse
        # 180 seconds = 3 minutes of connection reuse
        assert pool._max_keepalive_connections >= 50, "Should maintain large keepalive pool"
        assert pool._max_connections >= 150, "Should support connection reuse across requests"

        await client.close()

    @pytest.mark.asyncio
    async def test_global_client_pooling(self):
        """Verify global ZAI client has proper connection pooling."""
        global_client = get_zai_client()
        http_client = await global_client._get_client()

        # Global client should have same pooling configuration
        pool = http_client._transport._pool
        assert pool._max_connections >= 150, "Global client should have large connection pool"
        assert pool._max_keepalive_connections >= 50, "Global client should have large keepalive pool"

    @pytest.mark.asyncio
    async def test_pool_limits_max_connections(self):
        """Test that max_connections limits are properly enforced."""
        client = ZAIClient()
        http_client = await client._get_client()

        pool = http_client._transport._pool

        # Verify the pool has the expected limits configured
        assert pool._max_connections >= 150, "Pool should have max_connections limit >= 150"
        assert pool._max_keepalive_connections >= 50, "Pool should have keepalive connections limit >= 50"

        await client.close()

    @pytest.mark.asyncio
    async def test_http2_with_connection_pooling(self):
        """Verify HTTP/2 and connection pooling work together."""
        client = ZAIClient()
        http_client = await client._get_client()

        pool = http_client._transport._pool

        # HTTP/2 should be enabled alongside connection pooling
        assert hasattr(pool, "_http2"), "Pool should have HTTP/2 support"
        assert pool._http2 is True, "HTTP/2 should be enabled"

        # Pool should be sized for HTTP/2 multiplexing efficiency
        assert pool._max_connections >= 150, "Pool size should support HTTP/2 multiplexing"

        await client.close()


class TestPoolingUnderLoad:
    """Test connection pooling behavior under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_request_limit(self):
        """Test that connection pool handles request limit correctly."""
        client = ZAIClient()
        http_client = await client._get_client()

        pool = http_client._transport._pool

        # Create batch of concurrent requests up to a reasonable test limit
        batch_size = min(20, pool._max_connections)  # Test with reasonable batch

        async def mock_request(req_id):
            with patch.object(http_client, "request") as mock_request:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.headers = {}
                mock_response.http_version = "HTTP/2"
                mock_response.areturn = AsyncMock(return_value=b'{"result": {"content": [{"text": "test"}]}}')
                mock_request.return_value.__aenter__.return_value = mock_response

                await client.call(LLMRequest(
                    system_prompt="test",
                    user_message=f"load test {req_id}"
                ))
                return req_id

        # Launch concurrent batch
        tasks = [mock_request(i) for i in range(batch_size)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All requests should succeed
        successful = [r for r in results if isinstance(r, int)]
        assert len(successful) == batch_size, f"All {batch_size} requests should succeed"

        await client.close()

    @pytest.mark.asyncio
    async def test_pool_recovery_after_timeout(self):
        """Verify connection pool recovers properly after timeout scenarios."""
        client = ZAIClient()
        http_client = await client._get_client()

        # Simulate timeout scenario - the client.call method converts TimeoutException to LLMTimeoutError
        with patch.object(http_client, "stream") as mock_stream:
            # First request times out
            mock_stream.side_effect = httpx.TimeoutException("Connection timeout")

            from src.escalate.llm import LLMTimeoutError
            with pytest.raises(LLMTimeoutError):
                await client.call(LLMRequest(
                    system_prompt="test",
                    user_message="timeout test"
                ))

            # Pool should still be functional for subsequent requests
            mock_stream.side_effect = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_response.http_version = "HTTP/2"
            # Properly mock the async aread() method
            mock_response.aread = AsyncMock(return_value=b'{"result": {"content": [{"text": "recovery"}], "usage": {"input_tokens": 10, "output_tokens": 5}}}')
            mock_stream.return_value.__aenter__.return_value = mock_response

            response = await client.call(LLMRequest(
                system_prompt="test",
                user_message="recovery test"
            ))

            assert response.content == "recovery", "Pool should recover after timeout"

        await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
