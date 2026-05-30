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
from typing import Any, Optional

import httpx


logger = getLogger(__name__)

# ZAI proxy endpoint
ZAI_PROXY_URL = "http://llm-proxy.ardenone.com/v1/messages"

# Default model for bead formulation
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class ModelClass(Enum):
    """Available model classes."""
    HAIKU = "claude-haiku-4-20250514"  # Fast, cheap - for routing
    SONNET = "claude-sonnet-4-20250514"  # Balanced - for synthesis
    OPUS = "claude-opus-4-20250514"  # Highest quality - for complex tasks


@dataclass
class LLMRequest:
    """A request to the LLM."""
    system_prompt: str
    user_message: str
    model: str = DEFAULT_MODEL
    max_tokens: int = 4096
    temperature: float = 0.7

    def to_payload(self) -> dict:
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
    ):
        self.proxy_url = proxy_url
        self.default_model = default_model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
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

            # Extract content from response
            content = data.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                text = content[0].get("text", "")
            else:
                text = str(content)

            # Extract usage
            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            logger.debug(f"LLM response: input_tokens={input_tokens}, output_tokens={output_tokens}")

            return LLMResponse(
                content=text,
                model=data.get("model", request.model),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=data.get("stop_reason"),
            )

        except asyncio.TimeoutError as e:
            raise LLMTimeoutError(f"LLM request timed out after {self.timeout}s") from e
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"LLM request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise LLMRateLimitError("Rate limited by ZAI proxy") from e
            raise LLMError(f"LLM request failed: {e.response.status_code}") from e
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
