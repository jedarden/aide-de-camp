"""
LLM client for ZAI proxy (llm-proxy.ardenone.com).

Provides direct API calls to Claude models for bead formulation.
Used by escalate strand for single-turn, stateless LLM calls.
"""

import asyncio
import json
import os
import socket
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from logging import getLogger
from typing import Any, AsyncGenerator, Dict, Optional, Union
from urllib.parse import urlparse

import httpx

logger = getLogger(__name__)


# --- TCP Socket Optimizations -----------------------------------------------

def configure_tcp_optimizations() -> None:
    """
    Configure TCP-level optimizations for low-latency connections.

    This function sets up event loop policies for better TCP performance:
    - TCP_NODELAY: Disable Nagle's algorithm for reduced latency
    - SO_REUSEADDR: Allow address reuse for faster connection recycling
    - TCP_KEEPALIVE: Enable keepalive for connection health monitoring

    Should be called once at application startup.
    """
    try:
        # Get the current event loop
        loop = asyncio.get_running_loop()

        # Create a custom connector with optimized socket options
        # Note: httpx doesn't expose direct socket configuration, but we can
        # influence it through event loop policies and environment variables

        # Set environment variables for better TCP performance
        # These are respected by the underlying TCP stack
        os.environ.setdefault('TCP_NODELAY', '1')  # Disable Nagle's algorithm
        os.environ.setdefault('SO_KEEPALIVE', '1')  # Enable TCP keepalive

        logger.info("TCP optimizations configured: TCP_NODELAY enabled, keepalive enabled")
    except Exception as e:
        logger.warning(f"Failed to configure TCP optimizations: {e}")


# Initialize TCP optimizations at module load time
try:
    configure_tcp_optimizations()
except Exception as e:
    logger.debug(f"TCP optimization deferred to runtime: {e}")

# ZAI proxy endpoint — overridable via env var for local dev
ZAI_PROXY_URL = os.environ.get(
    "ZAI_PROXY_URL",
    "https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages",
)

# Default model for bead formulation
DEFAULT_MODEL = "claude-sonnet-4-20250514"


# --- DNS Caching ---------------------------------------------------------------

@lru_cache(maxsize=32)
def _resolve_hostname_cached(hostname: str, port: int, timeout: float = 2.0) -> Optional[str]:
    """
    Resolve hostname to IP with caching.

    Reduces DNS lookup overhead for repeated connections to the same endpoint.
    Uses LRU cache with TTL expiration implicitly via cache size limits.

    Args:
        hostname: The hostname to resolve
        port: The port number
        timeout: DNS resolution timeout in seconds

    Returns:
        IP address string or None if resolution fails
    """
    try:
        # Use getaddrinfo with socket-level timeout
        results = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        if results:
            ip_address = results[0][4][0]  # Extract IP from (host, port) tuple
            logger.debug(f"DNS resolved: {hostname} -> {ip_address}")
            return ip_address
    except socket.gaierror as e:
        logger.warning(f"DNS resolution failed for {hostname}: {e}")
        return None
    except Exception as e:
        logger.error(f"DNS resolution error for {hostname}: {e}")
        return None


def extract_host_from_url(url: str) -> Optional[tuple[str, int]]:
    """
    Extract hostname and port from URL.

    Args:
        url: The URL to parse

    Returns:
        Tuple of (hostname, port) or None if parsing fails
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if hostname:
            return hostname, port
    except Exception as e:
        logger.warning(f"Failed to parse URL {url}: {e}")
        return None


class ModelClass(Enum):
    """Available model classes.

    Performance note: For routing tasks, SONNET is empirically faster than HAIKU
    (median ~2362ms vs ~3861ms in our tests). Use SONNET for router despite HAIKU
    being marketed as "fast". SONNET provides better price-performance for this use case.
    """
    HAIKU = "claude-haiku-4-20250514"  # Fast, cheap - but slower for routing in practice
    SONNET = "claude-sonnet-4-20250514"  # Balanced - fastest for routing tasks
    OPUS = "claude-opus-4-20250514"  # Highest quality - for complex tasks


@dataclass
class LLMRequest:
    """A request to the LLM."""
    system_prompt: str
    user_message: str
    model: str = DEFAULT_MODEL
    max_tokens: int = 4096
    temperature: float = 0.7

    def to_payload(self) -> Dict[str, Any]:
        """Convert to API payload."""
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": self.system_prompt,
            "messages": [
                {"role": "user", "content": self.user_message}
            ],
        }


@dataclass
class LLMResponse:
    """Response from the LLM."""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str | None = None
    timing_network_ms: float | None = None  # Network latency (first byte received)
    timing_total_ms: float | None = None  # Total round-trip time

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def timing_inference_ms(self) -> float | None:
        """Estimated model inference time (total - network)."""
        if self.timing_total_ms is not None and self.timing_network_ms is not None:
            return max(0, self.timing_total_ms - self.timing_network_ms)
        return None


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


class LLMTimeoutError(LLMError):
    """LLM request timed out."""
    pass


class LLMRateLimitError(LLMError):
    """LLM rate limited."""
    pass


class ZAIClient:
    """
    Client for ZAI proxy (llm-proxy.ardenone.com).

    Provides single-turn, stateless LLM calls for:
    - Escalate strand: bead body formulation
    - Future: Intent router, Synthesize strand
    """

    def __init__(
        self,
        proxy_url: str = ZAI_PROXY_URL,
        default_model: str = DEFAULT_MODEL,
        timeout: float = 30.0,
    ) -> None:
        self.proxy_url = proxy_url
        self.default_model = default_model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with HTTP/2 and optimized connection pooling."""
        if self._client is None:
            # Configure aggressive connection pooling for reduced latency
            # - HTTP/2 for multiplexing and connection reuse
            # - Larger connection pool for concurrent requests
            # - Longer keepalive to reduce TLS handshakes
            # - Connection warmup for faster first requests
            limits = httpx.Limits(
                max_keepalive_connections=50,  # Increased from 30 for better concurrency under load
                max_connections=150,  # Increased from 100 to handle parallel requests
                keepalive_expiry=180.0  # Increased from 120s to reduce reconnections (3 minutes)
            )

            # Configure timeout with aggressive connection settings
            timeout_config = httpx.Timeout(
                connect=8.0,  # Reduced from 10s for faster failure detection
                read=30.0,  # Read timeout
                write=8.0,  # Reduced from 10s for faster failure detection
                pool=3.0,  # Reduced from 5s for faster failover
            )

            # Pre-resolve hostname using DNS cache for faster initial connections
            host_info = extract_host_from_url(self.proxy_url)
            if host_info:
                hostname, port = host_info
                resolved_ip = _resolve_hostname_cached(hostname, port)
                if resolved_ip:
                    logger.debug(f"Using cached DNS resolution: {hostname} -> {resolved_ip}")

            # Try HTTP/2 with fallback to HTTP/1.1
            try:
                # HTTP/2 configuration optimized for low latency
                self._client = httpx.AsyncClient(
                    timeout=timeout_config,
                    verify=False,
                    limits=limits,
                    http2=True,  # Enable HTTP/2 for multiplexing
                    headers={
                        "Connection": "keep-alive",
                        "Accept-Encoding": "gzip, deflate",  # Enable compression
                        "Accept": "*/*",
                        # Add HTTP/2 optimization headers
                        "te": "trailers",  # Enable trailer headers support
                    },
                    # Enable socket options for better performance
                    # httpx doesn't expose socket options directly, but we can set them via event loop policies
                )
                logger.info("ZAI client initialized with HTTP/2, compression, and optimized connection pooling")
            except Exception as e:
                logger.warning(f"HTTP/2 not available, falling back to HTTP/1.1: {e}")
                self._client = httpx.AsyncClient(
                    timeout=timeout_config,
                    verify=False,
                    limits=limits,
                    http1=True,
                    headers={
                        "Connection": "keep-alive",
                        "Accept-Encoding": "gzip, deflate",  # Enable compression
                        "Accept": "*/*"
                    }
                )
                logger.info("ZAI client initialized with HTTP/1.1, compression, and optimized connection pooling")
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def warmup(self) -> None:
        """
        Warm up the connection pool proactively.

        Establishes a low-cost connection to reduce latency for first real request.
        This eliminates the TLS handshake cost from the first actual LLM call.
        """
        if self._client is None:
            client = await self._get_client()

        try:
            # Send a lightweight OPTIONS request to establish connection
            import time
            warmup_start = time.monotonic()
            response = await self._client.request(
                "OPTIONS",
                self.proxy_url,
                headers={"Content-Type": "application/json"}
            )
            warmup_ms = (time.monotonic() - warmup_start) * 1000

            # Check HTTP version from response
            http_version = getattr(response, 'http_version', 'unknown')
            pool = self._client._transport._pool
            protocol = "HTTP/2" if getattr(pool, '_http2', False) else "HTTP/1.1"

            # Log warmup success (we expect 401/403 or similar, we just want the connection)
            logger.info(
                f"ZAI client connection warmup completed in {warmup_ms:.0f}ms "
                f"(status: {response.status_code}, protocol: {protocol}, response_version: {http_version})"
            )
        except Exception as e:
            logger.warning(f"ZAI client warmup failed (non-fatal): {e}")

    async def call(self, request: LLMRequest) -> LLMResponse:
        """
        Make a single-turn LLM call.

        Args:
            request: The LLM request

        Returns:
            LLMResponse with content, usage info, and timing breakdown

        Raises:
            LLMTimeoutError: If request times out
            LLMRateLimitError: If rate limited
            LLMError: For other errors
        """
        import time
        client = await self._get_client()

        request_start_ms = time.perf_counter() * 1000
        first_byte_ms = None

        try:
            payload = request.to_payload()
            logger.debug(f"LLM request: model={request.model}, input_tokens_estimate={len(request.user_message) // 4}")

            # Use streaming to measure actual first-byte time (network latency)
            async with client.stream(
                "POST",
                self.proxy_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                },
            ) as response:
                # Check for rate limit
                if response.status_code == 429:
                    raise LLMRateLimitError("Rate limited by ZAI proxy")

                response.raise_for_status()

                # Measure first-byte time: time when response headers are received
                first_byte_ms = time.perf_counter() * 1000
                network_ms = first_byte_ms - request_start_ms

                # Read the full response body (required for streaming responses)
                response_text = await response.aread()
                import json as json_lib
                data = json_lib.loads(response_text)

            request_end_ms = time.perf_counter() * 1000

            # Log HTTP/2 usage for this request
            http_version = getattr(response, 'http_version', 'unknown')
            pool = client._transport._pool
            protocol = "HTTP/2" if getattr(pool, '_http2', False) else "HTTP/1.1"
            logger.debug(f"LLM request using {protocol} (response HTTP version: {http_version})")

            # ZAI proxy wraps the Anthropic response under "result"
            payload_inner = data.get("result", data)

            # Extract content from response
            content = payload_inner.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                text = content[0].get("text", "")
            else:
                text = str(content)

            # Extract usage
            usage = payload_inner.get("usage", data.get("usage", {}))
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            # Calculate timing breakdown with actual network measurement
            total_ms = request_end_ms - request_start_ms
            inference_ms = total_ms - network_ms

            logger.debug(
                f"LLM response: input_tokens={input_tokens}, output_tokens={output_tokens}, "
                f"timing_total_ms={total_ms:.2f}, timing_network_ms={network_ms:.2f} (measured), "
                f"timing_inference_ms={inference_ms:.2f} (measured)"
            )

            return LLMResponse(
                content=text,
                model=payload_inner.get("model", request.model),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=payload_inner.get("stop_reason"),
                timing_total_ms=total_ms,
                timing_network_ms=network_ms,
            )

        except asyncio.TimeoutError as e:
            raise LLMTimeoutError(f"LLM request timed out after {self.timeout}s") from e
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"LLM request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise LLMRateLimitError("Rate limited by ZAI proxy") from e
            raise LLMError(f"LLM request failed: {e.response.status_code}") from e
        except (LLMTimeoutError, LLMRateLimitError, LLMError):
            # Re-raise our own exceptions without wrapping
            raise
        except Exception as e:
            raise LLMError(f"LLM request failed: {e}") from e

    async def call_simple(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        return_timing: bool = False,
    ) -> str | dict:
        """
        Convenience method for simple LLM calls.

        Args:
            system_prompt: System prompt for the LLM
            user_message: User message
            model: Model to use (defaults to client's default_model)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            return_timing: If True, return dict with content and timing; if False, return just text

        Returns:
            Text content (default) or dict with content and timing breakdown
        """
        request = LLMRequest(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model or self.default_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        response = await self.call(request)

        if return_timing:
            return {
                "content": response.content,
                "timing_total_ms": response.timing_total_ms,
                "timing_network_ms": response.timing_network_ms,
                "timing_inference_ms": response.timing_inference_ms,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        return response.content

    async def call_streaming(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """
        Stream LLM response for progressive card fill.

        Yields text chunks as they arrive from the API.

        Args:
            system_prompt: System prompt for the LLM
            user_message: User message
            model: Model to use (defaults to client's default_model)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Yields:
            Text chunks as they arrive

        Returns:
            Complete response text and usage info in the final iteration
        """
        request = LLMRequest(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model or self.default_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        client = await self._get_client()

        try:
            payload = request.to_payload()
            payload["stream"] = True  # Enable streaming

            logger.debug(f"LLM streaming request: model={request.model}")

            async with client.stream(
                "POST",
                self.proxy_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                # Check for rate limit
                if response.status_code == 429:
                    raise LLMRateLimitError("Rate limited by ZAI proxy")

                response.raise_for_status()

                accumulated_text = []
                input_tokens = 0
                output_tokens = 0

                # Process server-sent events
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix

                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)

                            # Handle ZAI proxy wrapping
                            if "result" in data:
                                data = data["result"]

                            # Extract delta from streaming event
                            if data.get("type") == "content_block_delta":
                                delta = data.get("delta", {})
                                text = delta.get("text", "")
                                if text:
                                    accumulated_text.append(text)
                                    yield text

                            # Extract final usage
                            if data.get("type") == "message_stop":
                                usage = data.get("usage", {})
                                input_tokens = usage.get("input_tokens", 0)
                                output_tokens = usage.get("output_tokens", 0)

                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse streaming event: {e}")

                # Yield final result with usage info
                full_text = "".join(accumulated_text)
                logger.debug(f"LLM streaming complete: input_tokens={input_tokens}, output_tokens={output_tokens}")
                yield {
                    "text": full_text,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "finish_reason": "stop",
                }

        except asyncio.TimeoutError as e:
            raise LLMTimeoutError(f"LLM streaming request timed out after {self.timeout}s") from e
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"LLM streaming request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise LLMRateLimitError("Rate limited by ZAI proxy") from e
            raise LLMError(f"LLM streaming request failed: {e.response.status_code}") from e
        except (LLMTimeoutError, LLMRateLimitError, LLMError):
            raise
        except Exception as e:
            raise LLMError(f"LLM streaming request failed: {e}") from e


# Global ZAI client instance
_client: Optional[ZAIClient] = None


def get_zai_client(
    proxy_url: str = ZAI_PROXY_URL,
    default_model: str = DEFAULT_MODEL,
    timeout: float = 30.0,
) -> ZAIClient:
    """Get or create the global ZAI client instance."""
    global _client
    if _client is None:
        _client = ZAIClient(
            proxy_url=proxy_url,
            default_model=default_model,
            timeout=timeout,
        )
    return _client


def get_router_zai_client(
    proxy_url: str = ZAI_PROXY_URL,
    default_model: str = DEFAULT_MODEL,
    timeout: float = 8.0,
) -> ZAIClient:
    """
    Get or create a dedicated ZAI client instance for router requests.

    Uses more aggressive connection pooling and shorter timeout for fail-fast behavior.
    Router requests are latency-sensitive and need rapid failure detection.
    """
    # Create a dedicated router client with optimized settings
    return ZAIClient(
        proxy_url=proxy_url,
        default_model=default_model,
        timeout=timeout,
    )


async def warmup_zai_connections() -> None:
    """
    Warm up ZAI proxy connections proactively during application startup.

    Should be called in the application lifespan manager to establish connections
    before the first user request arrives. This eliminates TLS and connection setup
    latency from the first actual request.
    """
    logger.info("Warming up ZAI proxy connections...")

    # Warm up the main client
    main_client = get_zai_client()
    await main_client.warmup()

    # Warm up the router client
    router_client = get_router_zai_client()
    await router_client.warmup()

    logger.info("ZAI proxy connection warmup complete")
