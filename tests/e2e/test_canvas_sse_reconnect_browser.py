"""
Real-browser SSE reconnection verification for the canvas (bead adc-jr35).

The hermetic suite ``tests/test_canvas_eventsource_reconnect.py`` (bead adc-2vto)
verifies the client ``EventSource`` state machine (onopen/onerror → loadTopics)
through a *mock* EventSource harness that runs the real inline canvas script —
no browser, no network. The server-side half ``tests/e2e/test_canvas_sse_reconnect.py``
proves the broadcaster unregister/register wire path in-process. THIS suite is the
real-browser counterpart the bead's acceptance criteria call for: it drives a
headless chromium against the live server, **simulates a network connection drop**
deterministically, and asserts on the *rendered* reconnect behaviour in the real
DOM:

- **drop is detected** — the ``#statusText`` indicator flips from ``Connected`` to
  ``Disconnected`` (the ``onerror`` handler) when the SSE stream is cut.
- **the client reconnects** — re-running the canvas's own ``connectSSE()`` mints a
  fresh ``EventSource`` to the same surface, firing ``onopen`` and flipping the
  indicator back to ``Connected``.
- **state is re-synced on reconnect** — events missed while offline are recovered:
  a topic injected *during* the outage appears once ``onopen`` → ``loadTopics()``
  re-fetches the full session state (the canvas does not rely on Last-Event-ID
  replay; it full-syncs on every reconnect).
- **live delivery works over the new stream** — a topic injected *after* reconnect
  is pushed live (``result_created`` → ``loadTopics()``) and renders.

Drop simulation note (why not ``context.set_offline``)
------------------------------------------------------
An earlier revision used Playwright's ``context.set_offline(True)`` to cut the
stream. That does not work for an *established idle* SSE connection:
``set_offline`` blocks **new** requests but does not sever an already-open socket
(an idle stream has no I/O to fail), so the native ``EventSource`` never fires
``onerror`` and ``#statusText`` stays ``Connected`` indefinitely — confirmed by
``tests/e2e/_probe_offline.py``. (The server *does* emit ``": ping"`` comments
every few seconds so a *real* network break is detected, but ``set_offline``
doesn't actually break localhost sockets.)

Instead we install a transparent ``EventSource`` subclass via
``context.add_init_script`` that stashes the live instance on ``window.__adcES``
(the canvas declares ``eventSource`` with ``let``, so it is lexical — not on
``window`` — and otherwise unreachable). The test then drives the canvas's REAL
``onerror`` handler with ``__adcES.dispatchEvent(new Event('error'))`` and closes
the stream with ``__adcES.close()`` (a genuine close → live delivery stops →
missed events are really missed), and reconnects by re-running the canvas's own
``connectSSE()`` (the same path native ``EventSource`` retry takes internally).
This exercises the real canvas handlers against the real server with no
non-deterministic waits on native reconnect backoff.

This runs ONLY where a real browser can launch. On NixOS the
``nixos_browser_bootstrap`` module (imported by conftest) preloads libstdc++ and
resolves the missing FHS libs so Playwright's chromium actually starts.
"""
from __future__ import annotations

import pytest

CANVAS_URL = "http://localhost:8000"

# The drop itself is driven synchronously (dispatchEvent fires onerror inline),
# but reconnect runs the canvas's async connectSSE() → onopen, so we still give
# the rendered status + card assertions generous headroom for slow CI.
_RECONNECT_TIMEOUT_MS = 20_000
_DROP_DETECTED_TIMEOUT_MS = 10_000


# Transparent EventSource wrapper installed before the page loads. It subclasses
# the native EventSource (every behaviour delegated unchanged) and stashes the
# live instance on window.__adcES so the test can drive the canvas's real
# onerror handler and close the stream — see the module docstring for why
# set_offline cannot do this.
_ES_WRAPPER_INIT = """
window.__adcES = null;
(() => {
    const RealEventSource = window.EventSource;
    window.EventSource = class extends RealEventSource {
        constructor(url, opts) { super(url, opts); window.__adcES = this; }
    };
})();
"""


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
    """Launch a headless browser + page; skip if chromium can't actually launch.

    Installs the EventSource wrapper so tests can drive the live connection.
    """
    async_playwright, _ = pw
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"playwright chromium could not launch: {exc}")
        try:
            context = await browser.new_context(viewport={"width": 1400, "height": 1080})
            await context.add_init_script(_ES_WRAPPER_INIT)
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

    Returns the session id. Using the injector's tracked session guarantees
    teardown regardless of how the test ends.
    """
    session_id = injector.predictable_session_id(f"sse-reconnect-{key}")
    await injector.create_session(session_id)
    await page.goto(
        f"{CANVAS_URL}/?session_id={session_id}", wait_until="domcontentloaded"
    )
    # Block until the SSE stream has actually opened (onopen → "Connected"), not
    # merely the page load. This is the precondition for every drop test below.
    await page.wait_for_function(
        "() => document.getElementById('statusText').textContent === 'Connected'",
        timeout=10_000,
    )
    # The wrapper must have captured the live EventSource by now (connectSSE ran
    # during init). Guard so a future change that delays connect() surfaces here
    # instead of as a cryptic null-deref in _simulate_drop.
    has_es = await page.evaluate("() => !!window.__adcES")
    assert has_es, "EventSource wrapper did not capture the live connection"
    return session_id


async def _simulate_drop(page):
    """Deterministically fire the canvas's real ``onerror`` handler and sever the
    live stream.

    Driving ``__adcES.dispatchEvent(new Event('error'))`` invokes the canvas's
    actual ``onerror`` (→ ``updateConnectionStatus('disconnected', 'Disconnected')``)
    exactly as a real network break would. ``close()`` then genuinely tears the
    connection down, so a topic injected afterwards is *not* delivered live and
    must be recovered by the reconnect re-sync.
    """
    await page.evaluate(
        """() => {
            const es = window.__adcES;
            if (!es) throw new Error("no live EventSource to drop");
            es.dispatchEvent(new Event("error"));
            es.close();
        }"""
    )


async def _simulate_reconnect(page):
    """Reconnect as the browser would on native EventSource retry.

    Re-runs the canvas's own ``connectSSE()``, which builds a fresh
    ``new EventSource(url)`` to the same ``surfaceId`` and fires ``onopen``
    → ``updateConnectionStatus('', 'Connected')`` + ``loadTopics()`` (the full
    re-sync). The wrapper captures the new instance on ``window.__adcES``.
    """
    await page.evaluate("() => window.connectSSE()")


class TestSSEDropDetected:
    """When the network drops, the canvas surface shows it lost the stream."""

    @pytest.mark.asyncio
    async def test_status_flips_to_disconnected_on_drop(self, browser_page, injector, pw):
        _, expect = pw
        page = browser_page
        await _open_connected(page, injector, key="drop-detected")

        # Sanity: connected before the drop.
        await expect(page.locator("#statusText")).to_have_text("Connected")

        # Fire the canvas's real onerror handler. The indicator flips to
        # "Disconnected" synchronously (dispatchEvent runs onerror inline).
        try:
            await _simulate_drop(page)
            await expect(page.locator("#statusText")).to_have_text(
                "Disconnected", timeout=_DROP_DETECTED_TIMEOUT_MS
            )
        finally:
            # Leave the context connected so teardown is clean.
            await _simulate_reconnect(page)


class TestReconnectStateSync:
    """After a drop, reconnect re-fetches full state — events missed while
    offline are recovered via onopen → loadTopics(), not SSE replay."""

    @pytest.mark.asyncio
    async def test_missed_topic_appears_after_reconnect(
        self, browser_page, injector, pw
    ):
        _, expect = pw
        page = browser_page
        session_id = await _open_connected(page, injector, key="resync")

        # A topic exists before the drop and is rendered.
        before = await injector.inject_topic(
            session_id, label="Before Drop", topic_type="project",
            summary="present pre-outage", urgency="normal", staleness_seconds=5,
        )
        await expect(
            page.locator(f'.topic-card[data-topic-id="{before["topic_id"]}"]')
        ).to_be_visible(timeout=10_000)

        # Sever the stream and inject a SECOND topic while the canvas is blind.
        # Its result_created SSE event is lost (the stream is closed; no replay).
        await _simulate_drop(page)
        await expect(page.locator("#statusText")).to_have_text(
            "Disconnected", timeout=_DROP_DETECTED_TIMEOUT_MS
        )
        missed = await injector.inject_topic(
            session_id, label="During Outage", topic_type="research",
            summary="injected while offline", urgency="normal", staleness_seconds=5,
        )

        # Reconnect. connectSSE() → onopen → loadTopics() full-syncs the session,
        # recovering the missed card.
        await _simulate_reconnect(page)
        await expect(page.locator("#statusText")).to_have_text(
            "Connected", timeout=_RECONNECT_TIMEOUT_MS
        )
        await expect(
            page.locator(f'.topic-card[data-topic-id="{missed["topic_id"]}"]')
        ).to_be_visible(timeout=_RECONNECT_TIMEOUT_MS)
        # The pre-drop card is still there too — reconnect replaced, not cleared.
        await expect(
            page.locator(f'.topic-card[data-topic-id="{before["topic_id"]}"]')
        ).to_have_count(1)


class TestLiveDeliveryAfterReconnect:
    """Once reconnected, the new stream pushes live events normally."""

    @pytest.mark.asyncio
    async def test_new_topic_pushes_live_over_reconnected_stream(
        self, browser_page, injector, pw
    ):
        _, expect = pw
        page = browser_page
        session_id = await _open_connected(page, injector, key="live-after")

        # A short outage + recovery cycle — what we actually want to exercise.
        await _simulate_drop(page)
        await expect(page.locator("#statusText")).to_have_text(
            "Disconnected", timeout=_DROP_DETECTED_TIMEOUT_MS
        )
        await _simulate_reconnect(page)
        await expect(page.locator("#statusText")).to_have_text(
            "Connected", timeout=_RECONNECT_TIMEOUT_MS
        )

        # Now inject over the healthy, reconnected stream. The result_created
        # event must arrive live and render — proving the new connection
        # delivers, not just the one-shot loadTopics() on open.
        live = await injector.inject_topic(
            session_id, label="After Reconnect", topic_type="project",
            summary="pushed over new stream", urgency="normal", staleness_seconds=5,
        )
        await expect(
            page.locator(f'.topic-card[data-topic-id="{live["topic_id"]}"]')
        ).to_be_visible(timeout=_RECONNECT_TIMEOUT_MS)
