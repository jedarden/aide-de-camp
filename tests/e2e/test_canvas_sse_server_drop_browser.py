"""
Real-browser SSE reconnection via a SERVER-initiated drop (bead adc-jr35).

The sibling suite ``test_canvas_sse_reconnect_browser.py`` simulates a drop by
installing an ``EventSource`` wrapper and firing the canvas's ``onerror``
synthetically (``__adcES.dispatchEvent(new Event('error'))`` + ``close()``).
That exercises the canvas's reconnect *handlers* — but not the path a real
network/server break takes: the server actually ending the stream, the
browser's NATIVE ``EventSource`` noticing the dead connection, and
auto-reconnecting on its own.

This suite proves that other path. It calls the adc-jr35 test endpoint
``POST /api/v1/test/drop-sse`` (backed by ``SSEBroadcaster.drop_session`` — see
``src/sse/broadcaster.py``), which pushes a sentinel that makes the SSE
event-generator ``return`` WITHOUT emitting a ``disconnect`` event. The
browser's native ``EventSource`` then sees the response body end, fires its own
``onerror`` (→ ``#statusText`` flips to ``Disconnected``), and — left
un-``close()``d — performs its built-in auto-reconnect, whose ``onopen``
re-runs ``loadTopics()`` and so recovers any card injected during the outage.

This is the most faithful "simulate a connection drop" the bead's acceptance
criteria call for, and it is the only test that exercises the broadcaster's
``drop_session`` + keepalive code path end-to-end (the keepalive comments keep
an idle stream observable so a *silent* break is detected; the explicit
``drop_session`` makes the break immediate and deterministic).

It deliberately does NOT install the EventSource wrapper the sibling suite
uses: we want the native EventSource, untouched, so its real ``onerror`` +
auto-reconnect run. (The wrapper exists only so the sibling suite can reach
the otherwise-private ``eventSource`` binding to drive it by hand.)

Runs ONLY where a real browser can launch (the NixOS bootstrap in conftest
makes Playwright importable + chromium launchable) and the server answers
/health. Both gate as clean ``pytest.skip``s otherwise.
"""
from __future__ import annotations

import pytest

CANVAS_URL = "http://localhost:8000"

# Native EventSource auto-reconnect uses a backoff (Chromium's initial retry
# delay is ~3s, growing on repeated failures). Give the reconnected-stream
# assertions generous headroom so slow CI never flakes.
_NATIVE_RECONNECT_TIMEOUT_MS = 25_000
_DROP_DETECTED_TIMEOUT_MS = 10_000


def _server_running() -> bool:
    """True iff the ADC server answers /health on localhost:8000."""
    import httpx

    try:
        return httpx.get(f"{CANVAS_URL}/health", timeout=2).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _server_running(), reason="ADC server not running on localhost:8000"
)


@pytest.fixture(scope="module")
def pw():
    """Lazily import Playwright; skip the module's tests if it is unusable."""
    try:
        from playwright.async_api import async_playwright, expect
    except Exception as exc:  # absent OR a broken native dep — either way, skip
        pytest.skip(f"playwright unusable on this host: {exc}")
    return async_playwright, expect


@pytest.fixture
async def browser_page(pw):
    """Launch a headless browser + page; skip if chromium can't launch.

    No EventSource wrapper (unlike the sibling suite): we exercise the NATIVE
    onerror + auto-reconnect path, which a wrapper would not change but also
    would not need.
    """
    async_playwright, _ = pw
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"playwright chromium could not launch: {exc}")
        try:
            context = await browser.new_context(viewport={"width": 1400, "height": 1080})
            page = await context.new_page()
            yield page
        finally:
            await context.close()
            await browser.close()


@pytest.fixture
async def injector():
    """Live-server TestDataInjector (adc-5unt) that cleans up its sessions."""
    from tests.e2e.inject import TestDataInjector

    async with TestDataInjector(base_url=CANVAS_URL) as inj:
        yield inj


async def _open_connected(page, injector, *, key: str) -> str:
    """Open the canvas for a fresh session and block until SSE shows Connected.

    Returns the session id. Blocks on the SSE stream actually opening (onopen →
    "Connected"), not merely the page load — that is the precondition for a
    server-initiated drop to have a live stream to sever.
    """
    session_id = injector.predictable_session_id(f"sse-server-drop-{key}")
    await injector.create_session(session_id)
    await page.goto(
        f"{CANVAS_URL}/?session_id={session_id}", wait_until="domcontentloaded"
    )
    await page.wait_for_function(
        "() => document.getElementById('statusText').textContent === 'Connected'",
        timeout=10_000,
    )
    return session_id


class TestServerInitiatedDrop:
    """The server ends the stream; the browser's native EventSource notices and
    auto-reconnects — the path no synthetic ``dispatchEvent`` test exercises."""

    @pytest.mark.asyncio
    async def test_native_detection_of_server_drop(self, browser_page, injector, pw):
        """Server severs the stream → native onerror fires → status flips to
        Disconnected, with no client-side simulation of the drop."""
        _, expect = pw
        page = browser_page
        session_id = await _open_connected(page, injector, key="detect2")

        await expect(page.locator("#statusText")).to_have_text("Connected")

        res = await injector.drop_sse(session_id)
        assert res["dropped_streams"] >= 1, (
            f"drop-sse reported {res['dropped_streams']} streams — no live "
            "connection existed to sever (precondition not met)"
        )

        # The browser's NATIVE EventSource detects the abruptly-ended stream and
        # fires onerror → "Disconnected". This is the proof that a real
        # server-initiated drop propagates to the client without any synthetic
        # dispatchEvent — the behaviour drop_session + keepalive exist to enable.
        await expect(page.locator("#statusText")).to_have_text(
            "Disconnected", timeout=_DROP_DETECTED_TIMEOUT_MS
        )

    @pytest.mark.asyncio
    async def test_native_reconnect_recovers_missed_topic(
        self, browser_page, injector, pw
    ):
        """After the server drop, the native auto-reconnect's onopen re-runs
        loadTopics() and recovers a card injected during the outage."""
        _, expect = pw
        page = browser_page
        session_id = await _open_connected(page, injector, key="resync")

        # A topic exists and renders before the drop.
        before = await injector.inject_topic(
            session_id, label="Before Server Drop", topic_type="project",
            summary="present pre-outage", urgency="normal", staleness_seconds=5,
        )
        await expect(
            page.locator(f'.topic-card[data-topic-id="{before["topic_id"]}"]')
        ).to_be_visible(timeout=10_000)

        # Sever server-side, then inject a SECOND topic while the native
        # EventSource is mid-reconnect-backoff (its result_created SSE event is
        # lost until the new stream's onopen → loadTopics() full-syncs).
        await injector.drop_sse(session_id)
        await expect(page.locator("#statusText")).to_have_text(
            "Disconnected", timeout=_DROP_DETECTED_TIMEOUT_MS
        )
        missed = await injector.inject_topic(
            session_id, label="During Server Outage", topic_type="research",
            summary="injected while offline", urgency="normal", staleness_seconds=5,
        )

        # Native auto-reconnect (no manual connectSSE()) opens a fresh stream,
        # whose onopen re-runs loadTopics() and recovers the missed card.
        await expect(page.locator("#statusText")).to_have_text(
            "Connected", timeout=_NATIVE_RECONNECT_TIMEOUT_MS
        )
        await expect(
            page.locator(f'.topic-card[data-topic-id="{missed["topic_id"]}"]')
        ).to_be_visible(timeout=_NATIVE_RECONNECT_TIMEOUT_MS)
        # The pre-drop card survived the cycle.
        await expect(
            page.locator(f'.topic-card[data-topic-id="{before["topic_id"]}"]')
        ).to_have_count(1)
