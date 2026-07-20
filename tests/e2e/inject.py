"""
Test data injection client for canvas testing.

``TestDataInjector`` is an async httpx client that injects test sessions and
topics into a running ADC server (or an in-process FastAPI app) and cleans them
up afterwards. It is transport-agnostic:

- **Live server** (used by Playwright/browser e2e suites against :8000):
    ``TestDataInjector(base_url="http://localhost:8000")``
- **In-process** (no network server, isolated temp DB — used by unit tests):
    ``TestDataInjector(app=src.main.app)``

Endpoints exercised:

- ``POST   /api/v1/sessions``                 — create a session w/ predictable ID
- ``DELETE /api/v1/sessions/{session_id}``     — cascade-clean a session (teardown)
- ``GET    /api/v1/sessions/{session_id}/topics`` — read back injected topic cards
- ``POST   /api/v1/test/create-topic``         — inject a topic + result directly (no LLM)
- ``POST   /api/v1/test/dispatch``             — inject via the real dispatch pipeline (LLM)

The direct ``create-topic`` path is deterministic and network-free; ``dispatch``
exercises the full router → fetch+synthesize pipeline but depends on the ZAI LLM
proxy. Default injection uses ``direct`` so tests stay fast and hermetic.
"""
from __future__ import annotations

import uuid
from logging import getLogger
from typing import Any, Optional

import httpx

logger = getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:8000"
# All auto-generated session IDs share this prefix so they are easy to spot and
# bulk-clean, and never collide with real production session IDs.
TEST_SESSION_PREFIX = "test-inject-"
_TESTSERVER = "http://testserver"  # synthetic host used with the ASGI transport


class InjectionError(RuntimeError):
    """Raised when an injection/cleanup HTTP call fails or returns an unexpected shape."""


class TestDataInjector:
    # pytest sees any ``Test*`` class as a test class; this is a helper, not a
    # test. Suppress collection so the suite stays warning-free.
    __test__ = False

    """Async httpx client for injecting and tearing down canvas test data.

    Tracks every session it creates and deletes them all on ``cleanup()`` /
    ``aclose()``, so tests can use it as a context manager for guaranteed
    teardown:

        async with TestDataInjector(app=app) as inj:
            await inj.create_session("test-inject-foo")
            await inj.inject_topic("test-inject-foo", label="Pods")
            ...  # cleanup runs on exit, even if the body raises
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        app: Any = None,
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 30.0,
    ) -> None:
        if app is not None and base_url != DEFAULT_BASE_URL:
            # Avoid ambiguous combos — pick one transport explicitly.
            raise ValueError("Pass either app= (in-process) or base_url= (live), not both")

        self._owns_client = client is None
        self._created_session_ids: list[str] = []

        if client is not None:
            self._client = client
        elif app is not None:
            # ASGI transport drives the app directly — no socket, no server.
            self._client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=_TESTSERVER,
                timeout=timeout,
            )
        else:
            self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    # -- lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> "TestDataInjector":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Clean up every tracked session, then close the owned httpx client."""
        try:
            await self.cleanup()
        finally:
            if self._owns_client:
                await self._client.aclose()

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def predictable_session_id(label: str) -> str:
        """Build a stable, prefixed session ID from a human label."""
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label).strip("-")
        return f"{TEST_SESSION_PREFIX}{safe or 'session'}"

    @classmethod
    def _resolve_session_id(cls, session_id: Optional[str]) -> str:
        """Normalize any session-id input into a prefixed, trackable test ID.

        Guarantees every session this injector touches carries the test prefix
        (so it is easy to spot and bulk-clean, and never collides with a real
        production session id):

        - ``None``          → auto-generate ``test-inject-<hex>``
        - already-prefixed  → returned verbatim (idempotent)
        - anything else     → namespaced via :meth:`predictable_session_id`
        """
        if session_id is None:
            return f"{TEST_SESSION_PREFIX}{uuid.uuid4().hex[:12]}"
        if session_id.startswith(TEST_SESSION_PREFIX):
            return session_id
        return cls.predictable_session_id(session_id)

    def _track(self, session_id: str) -> None:
        if session_id not in self._created_session_ids:
            self._created_session_ids.append(session_id)

    def _untrack(self, session_id: str) -> None:
        if session_id in self._created_session_ids:
            self._created_session_ids.remove(session_id)

    @property
    def tracked_sessions(self) -> list[str]:
        """Session IDs this injector will clean up on teardown."""
        return list(self._created_session_ids)

    @staticmethod
    def _check(resp: httpx.Response, *, expected: int = 200) -> httpx.Response:
        if resp.status_code != expected:
            raise InjectionError(
                f"HTTP {resp.status_code} (expected {expected}): {resp.text[:300]}"
            )
        return resp

    # -- session -------------------------------------------------------------

    async def create_session(self, session_id: Optional[str] = None) -> dict:
        """Create a test session. Auto-generates a prefixed ID if none given.

        Explicit labels are namespaced under the test prefix (see
        :meth:`_resolve_session_id`) so they stay easy to spot and bulk-clean.
        Idempotent: calling twice with the same input returns ``created: false``
        the second time. The resolved session is tracked for teardown.
        """
        session_id = self._resolve_session_id(session_id)
        resp = await self._client.post("/api/v1/sessions", json={"session_id": session_id})
        self._check(resp)
        data = resp.json()
        sid = data.get("session_id", session_id)
        self._track(sid)
        return data

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Return the raw session row (via the store) or None if absent."""
        # There is no public GET /sessions/{id}; reuse the topics endpoint as a
        # presence probe by checking the store directly through create-session
        # idempotency: a session that already exists reports created=false.
        session_id = self._resolve_session_id(session_id)
        resp = await self._client.post("/api/v1/sessions", json={"session_id": session_id})
        self._check(resp)
        data = resp.json()
        return {"session_id": data["session_id"], "exists": not data["created"]}

    async def delete_session(self, session_id: str) -> dict:
        """Delete a session and all its data. Untracks it regardless of outcome."""
        session_id = self._resolve_session_id(session_id)
        resp = await self._client.delete(f"/api/v1/sessions/{session_id}")
        self._check(resp)
        self._untrack(session_id)
        return resp.json()

    # -- topics --------------------------------------------------------------

    async def inject_topic(
        self,
        session_id: str,
        *,
        label: Optional[str] = None,
        topic_type: str = "project",
        summary: str = "injected test result",
        urgency: str = "normal",
        staleness_seconds: int = 0,
        via: str = "direct",
        utterance: Optional[str] = None,
        surface_id: Optional[str] = None,
        wait_for_results: bool = True,
        timeout_seconds: int = 30,
    ) -> dict:
        """Inject one topic into ``session_id``.

        ``via="direct"`` (default): writes a topic + result straight to the store
        via ``POST /api/v1/test/create-topic`` — deterministic, no LLM. Best for
        hermetic tests.

        ``via="dispatch"``: runs the full router → fetch+synthesize pipeline via
        ``POST /api/v1/test/dispatch`` (requires the ZAI LLM proxy). ``utterance``
        is required for this path; ``label`` is ignored (the router derives it),
        so it may be omitted.
        """
        session_id = self._resolve_session_id(session_id)
        if via == "direct":
            if not label:
                raise ValueError("via='direct' requires a 'label'")
            payload = {
                "session_id": session_id,
                "label": label,
                "type": topic_type,
                "summary": summary,
                "urgency": urgency,
                "staleness_seconds": staleness_seconds,
            }
            resp = await self._client.post("/api/v1/test/create-topic", json=payload)
            self._check(resp)
            return resp.json()
        elif via == "dispatch":
            if not utterance:
                raise ValueError("via='dispatch' requires an 'utterance'")
            payload = {
                "utterance": utterance,
                "session_id": session_id,
                "surface_id": surface_id,
                "wait_for_results": wait_for_results,
                "timeout_seconds": timeout_seconds,
            }
            resp = await self._client.post("/api/v1/test/dispatch", json=payload)
            self._check(resp)
            return resp.json()
        raise ValueError(f"unknown via={via!r} (expected 'direct' or 'dispatch')")

    async def inject_topics(
        self,
        session_id: str,
        specs: list[dict],
    ) -> list[dict]:
        """Inject many topics sequentially. Each spec is a kwarg dict for inject_topic."""
        results = []
        for spec in specs:
            results.append(await self.inject_topic(session_id, **spec))
        return results

    async def inject_session_with_topics(
        self,
        session_id: str,
        topic_specs: list[dict],
    ) -> dict:
        """Convenience: create a session, then inject N topics into it."""
        sid = self._resolve_session_id(session_id)
        await self.create_session(sid)
        topics = await self.inject_topics(sid, topic_specs)
        return {"session_id": sid, "topic_count": len(topics), "topics": topics}

    async def get_topics(self, session_id: str) -> list[dict]:
        """Return the canvas topic cards for a session (GET .../topics)."""
        session_id = self._resolve_session_id(session_id)
        resp = await self._client.get(f"/api/v1/sessions/{session_id}/topics")
        self._check(resp)
        data = resp.json()
        return data.get("cards", [])

    # -- teardown ------------------------------------------------------------

    async def cleanup(self) -> list[str]:
        """Delete every tracked session. Best-effort: never raises.

        Returns the list of session IDs actually removed.
        """
        removed: list[str] = []
        for sid in list(self._created_session_ids):
            try:
                await self.delete_session(sid)
                removed.append(sid)
            except Exception as exc:  # noqa: BLE001 — teardown must be best-effort
                logger.warning(f"cleanup: failed to delete session {sid}: {exc}")
                self._untrack(sid)
        return removed
