"""
LLM client for ZAI proxy (llm-proxy.ardenone.com).

Provides direct API calls to Claude models for bead formulation.
Used by escalate strand for single-turn, stateless LLM calls.
"""

import asyncio
import json
import os
from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from typing import Any, AsyncGenerator, Dict, Optional, Union

import httpx

logger = getLogger(__name__)

# ZAI proxy endpoint — overridable via env var for local dev
ZAI_PROXY_URL = os.environ.get(
    "ZAI_PROXY_URL",
    "https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages",
)

# Default model for bead formulation
DEFAULT_MODEL = "claude-sonnet-4-20250514"


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

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


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
        """Get or create HTTP client with connection pooling."""
        if self._client is None:
            # Configure connection pooling for reduced latency
            # - HTTP/1.1 keepalive for connection reuse
            # - Connection limits for ZAI proxy
            # - Softer timeouts for connection establishment
            limits = httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0
            )
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=False,
                limits=limits,
                http1=True,  # Force HTTP/1.1 for better compatibility
                headers={"Connection": "keep-alive"}
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def call(self, request: LLMRequest) -> LLMResponse:
        """
        Make a single-turn LLM call.

        Args:
            request: The LLM request

        Returns:
            LLMResponse with content and usage info

        Raises:
            LLMTimeoutError: If request times out
            LLMRateLimitError: If rate limited
            LLMError: For other errors
        """
        client = await self._get_client()

        try:
            payload = request.to_payload()
            logger.debug(f"LLM request: model={request.model}, input_tokens_estimate={len(request.user_message) // 4}")

            response = await client.post(
                self.proxy_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                },
            )

            # Check for rate limit
            if response.status_code == 429:
                raise LLMRateLimitError("Rate limited by ZAI proxy")

            response.raise_for_status()
            data = response.json()

            # ZAI proxy wraps the Anthropic response under "result"
            payload = data.get("result", data)

            # Extract content from response
            content = payload.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                text = content[0].get("text", "")
            else:
                text = str(content)

            # Extract usage
            usage = payload.get("usage", data.get("usage", {}))
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            logger.debug(f"LLM response: input_tokens={input_tokens}, output_tokens={output_tokens}")

            return LLMResponse(
                content=text,
                model=payload.get("model", request.model),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=payload.get("stop_reason"),
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
    ) -> str:
        """
        Convenience method for simple LLM calls.

        Returns just the text content.
        """
        request = LLMRequest(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model or self.default_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        response = await self.call(request)
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
