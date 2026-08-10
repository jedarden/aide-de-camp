"""Async client for injecting topics through the production dispatch endpoint."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class TopicCreationError(RuntimeError):
    """Base exception raised when a topic cannot be created."""


class IntentRoutingError(TopicCreationError):
    """Raised when the dispatch service cannot route an utterance."""


class SynthesisError(TopicCreationError):
    """Raised when dispatch succeeds but synthesis fails."""


class TestTopicClient:
    """Create test topics by posting utterances to ``POST /dispatch``.

    The client owns one reusable :class:`httpx.AsyncClient`, so several topics
    can be created in order without opening a new connection for every topic.
    Use it as an async context manager, or assign an already-open client to the
    ``client`` attribute when using a mocked transport in a unit test.
    """

    __test__ = False

    DEFAULT_BASE_URL = "http://localhost:8000"
    DEFAULT_TIMEOUT = 60.0

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        *,
        dispatch_url: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        """Initialize the topic client.

        Args:
            base_url: ADC server URL. The default targets the local server.
            timeout: Per-request timeout in seconds.
            dispatch_url: Optional complete URL overriding ``base_url``.
            client: Optional preconfigured async client, useful for tests.
        """
        if not base_url or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        normalized_base_url = base_url.rstrip("/")
        self.dispatch_url = dispatch_url or (
            normalized_base_url
            if normalized_base_url.endswith("/dispatch")
            else f"{normalized_base_url}/dispatch"
        )
        self.timeout = timeout
        self.client = client

    async def __aenter__(self) -> "TestTopicClient":
        """Open the underlying HTTP client."""
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close the underlying HTTP client."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client, if it is open."""
        if self.client is not None and not self.client.is_closed:
            await self.client.aclose()

    def _require_client(self) -> httpx.AsyncClient:
        if self.client is None or self.client.is_closed:
            raise TopicCreationError(
                "TestTopicClient is not open; use it as an async context manager"
            )
        return self.client

    async def create_topic(
        self,
        utterance: str,
        session_id: str,
        surface_id: str,
    ) -> dict[str, Any]:
        """Create one topic through the dispatch endpoint.

        The returned dictionary contains the server's response and is
        guaranteed to include a non-empty ``topic_id`` and a ``result`` key.
        ``synthesis_result`` is accepted as an upstream spelling and normalized
        to ``result``.
        """
        utterance = self._required_value(utterance, "utterance")
        session_id = self._required_value(session_id, "session_id")
        surface_id = self._required_value(surface_id, "surface_id")
        payload = {
            "utterance": utterance,
            "session_id": session_id,
            "surface_id": surface_id,
        }

        client = self._require_client()
        try:
            response = await client.post(self.dispatch_url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._error_for_message(
                self._response_error_message(exc.response), exc.response.status_code
            ) from exc
        except httpx.RequestError as exc:
            raise TopicCreationError(
                f"Failed to create topic: dispatch request failed: {exc}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise TopicCreationError(
                "Failed to create topic: dispatch response was not valid JSON"
            ) from exc

        if not isinstance(data, dict):
            raise TopicCreationError(
                "Failed to create topic: dispatch response must be a JSON object"
            )

        error_message = self._embedded_error_message(data)
        if error_message:
            raise self._error_for_message(error_message, response.status_code)

        # A few dispatch adapters wrap their result under ``data``. Accept that
        # shape while preserving the original response returned to callers.
        response_data = data.get("data") if isinstance(data.get("data"), dict) else data
        topic_id = response_data.get("topic_id")
        if not isinstance(topic_id, str) or not topic_id.strip():
            raise TopicCreationError(
                "Failed to create topic: response is missing a valid topic_id"
            )
        if "topic_id" not in data:
            data["topic_id"] = topic_id

        if "result" not in data and "synthesis_result" in response_data:
            data["result"] = response_data["synthesis_result"]
        if "result" not in data:
            if "result" in response_data:
                data["result"] = response_data["result"]
            else:
                raise TopicCreationError(
                    "Failed to create topic: response is missing a synthesis result"
                )

        logger.info("[TEST] Created topic %s for session %s", topic_id, session_id)
        return data

    async def create_topics(
        self,
        topics: Iterable[str | Mapping[str, Any]],
        session_id: Optional[str] = None,
        surface_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Create multiple topics sequentially and return them in input order.

        String entries use the shared ``session_id`` and ``surface_id``
        arguments. Mapping entries may provide those fields individually, which
        is useful when a sequence spans more than one session or surface; any
        omitted field falls back to the shared argument.

        The next request is not started until the previous request has
        completed. If one request fails, its typed exception is raised and
        later topics are not attempted.
        """
        results: list[dict[str, Any]] = []
        for topic in topics:
            if isinstance(topic, str):
                request_session_id = session_id
                request_surface_id = surface_id
                utterance = topic
            elif isinstance(topic, Mapping):
                utterance = topic.get("utterance")
                request_session_id = topic.get("session_id", session_id)
                request_surface_id = topic.get("surface_id", surface_id)
            else:
                raise ValueError(
                    "each topic must be an utterance string or a mapping containing utterance"
                )

            if request_session_id is None or request_surface_id is None:
                raise ValueError(
                    "session_id and surface_id are required for every topic"
                )

            results.append(
                await self.create_topic(
                    utterance=utterance,
                    session_id=request_session_id,
                    surface_id=request_surface_id,
                )
            )
        return results

    async def inject_topic(
        self,
        utterance: str,
        session_id: str,
        surface_id: str,
    ) -> dict[str, Any]:
        """Alias for :meth:`create_topic` using injection terminology."""
        return await self.create_topic(utterance, session_id, surface_id)

    async def inject_topics(
        self,
        topics: Iterable[str | Mapping[str, Any]],
        session_id: Optional[str] = None,
        surface_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Alias for :meth:`create_topics` using injection terminology."""
        return await self.create_topics(topics, session_id, surface_id)

    @staticmethod
    def _required_value(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _response_error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = response.text

        if isinstance(body, dict):
            message = body.get("error") or body.get("detail") or body.get("message")
            if isinstance(message, dict):
                message = message.get("message") or message.get("detail")
            if message:
                return str(message)
        return str(body) if body else f"HTTP {response.status_code}"

    @staticmethod
    def _embedded_error_message(data: dict[str, Any]) -> Optional[str]:
        status = str(data.get("status", "")).lower()
        error = data.get("error") or data.get("detail")
        if error is None and data.get("success") is False:
            error = data.get("message") or "dispatch failed"
        if error:
            if isinstance(error, dict):
                error = error.get("message") or error.get("detail") or error
            return str(error)
        if status in {"error", "failed", "failure"}:
            return str(data.get("message") or "dispatch failed")
        return None

    @staticmethod
    def _error_for_message(message: str, status_code: Optional[int] = None) -> TopicCreationError:
        lowered = message.lower()
        prefix = f"HTTP {status_code}: " if status_code is not None else ""
        if any(term in lowered for term in ("intent", "route", "routing", "classif")):
            return IntentRoutingError(f"Failed to create topic: {prefix}{message}")
        if any(term in lowered for term in ("synth", "result", "generation")):
            return SynthesisError(f"Failed to create topic: {prefix}{message}")
        return TopicCreationError(f"Failed to create topic: {prefix}{message}")


# Short aliases make the utility convenient for tests that describe this
# operation as injection rather than creation.
TopicInjector = TestTopicClient


__all__ = [
    "IntentRoutingError",
    "SynthesisError",
    "TestTopicClient",
    "TopicCreationError",
    "TopicInjector",
]
