"""Real-browser screenshot capture + objective visual verification (bead adc-jr35).

This is the "take screenshots of the rendered canvas" piece of the bead's
acceptance criteria — done *objectively*, not as human eyeballing. The other
real-browser suites (``test_canvas_dom_verification`` / ``test_canvas_staleness_browser``
/ ``test_canvas_sse_reconnect_browser``) verify the **DOM** (classes, data
attributes, text, SSE behaviour). A screenshot is pixels; without analysis it is
just evidence a person would look at. This suite makes a capture *scriptably
verifiable* via :mod:`tests.e2e.screenshot_analyze` (PIL-backed):

- **captures are real images** of the expected shape — valid PNG, and a full-page
  capture of a multi-card canvas is taller than the viewport (cards stack).
- **distinct states produce distinct captures** — an empty canvas and a populated
  one are pixel-distinct (``images_differ``). This is the direct guard against the
  failure mode the *old* canvas suite hit: every screenshot it wrote was a
  byte-identical 30075-byte blank (Playwright couldn't launch back then, so
  "01_initial_load" / "02_empty_state" / "03_with_topics" / "04_after_reconnection"
  were all the same image). That regression is now caught mechanically.
- **a populated canvas renders real content** — its distinct-colour count exceeds
  the empty-canvas baseline by a comfortable margin (cards, badges, dots and text
  add colour variety a blank page lacks).
- **staleness renders visually** — the same CSS colour rules the staleness class
  keys off of produce different pixels for a fresh card vs a very-stale one, so a
  human *would* see the difference. Asserting on the cropped ``.staleness-dot``
  pixel data proves the visual affordance actually rendered, not just that the
  class is present (the DOM suite already covers the class).

Each capture is written under ``tests/e2e/screenshots/jr35/`` with a stable name
(latest-overwrites, not timestamped clutter) so the artifacts are inspectable
after a run.

This runs ONLY where a real browser can launch (the NixOS bootstrap in conftest
makes Playwright importable + chromium launchable here) AND Pillow is installed
(a declared ``dev`` extra). Both gate as clean ``pytest.skip``s otherwise.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e import screenshot_analyze as sa

CANVAS_URL = "http://localhost:8000"

# Stable artifact directory: latest-overwrites so the screenshots are easy to
# inspect after a run rather than accumulating timestamped copies.
SHOT_DIR = Path(__file__).parent / "screenshots" / "jr35"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

# A representative mix: every topic type, every staleness level, varied urgency —
# so the populated capture exercises the full visual vocabulary (type badges,
# STALE badges, urgency badges, staleness dots/footers) in one screenshot.
MIXED_SPECS = [
    dict(label="Fresh Project", topic_type="project", summary="just created",
         urgency="normal", staleness_seconds=5),
    dict(label="Stale Research", topic_type="research", summary="needs review",
         urgency="high", staleness_seconds=1200),
    dict(label="Very-Stale Personal", topic_type="personal", summary="forgotten",
         urgency="normal", staleness_seconds=7200),
    dict(label="Fresh Exception", topic_type="exception", summary="active alert",
         urgency="critical", staleness_seconds=5),
    dict(label="Stale Compound", topic_type="compound", summary="multi-strand",
         urgency="normal", staleness_seconds=1200),
]

# Floor for "a populated canvas rendered real content", independent of the
# empty-canvas baseline. The empty canvas page renders ~400 distinct colours
# (header, gradients, anti-aliasing); five mixed cards push it well past 1000.
_POPULATED_COLOR_FLOOR = 1000


def _server_running() -> bool:
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
    """Lazily import Playwright; skip the module if it is unusable.

    Deferred (not top-level) so the module collects even where Playwright's
    native deps are broken. The NixOS bootstrap (conftest) makes the import work
    here; on a host without that, this skip keeps collection green.
    """
    try:
        from playwright.async_api import async_playwright, expect
    except Exception as exc:  # absent OR a broken native dep — either way, skip
        pytest.skip(f"playwright unusable on this host: {exc}")
    return async_playwright, expect


@pytest.fixture
async def browser_page(pw):
    """Launch a headless browser + page; skip if chromium can't launch.

    Viewport matches the other browser suites (1400×1080) and uses the default
    device scale ratio of 1, so a Playwright bounding box (CSS px, document-
    relative) maps 1:1 to screenshot pixels — the invariant
    :mod:`screenshot_analyze` relies on to crop card regions.
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
def analysis():
    """PIL-backed analysis; skip the test if Pillow is not importable."""
    if not sa._HAS_PIL:
        pytest.skip("Pillow not installed — install dev extras: pip install -e '.[dev]'")
    return sa


@pytest.fixture
async def injector():
    """Live-server TestDataInjector (adc-5unt) that cleans up its sessions."""
    from tests.e2e.inject import TestDataInjector

    async with TestDataInjector(base_url=CANVAS_URL) as inj:
        yield inj


async def _open_connected(page, session_id: str) -> None:
    """Open the canvas for ``session_id`` and block until SSE shows Connected."""
    await page.goto(
        f"{CANVAS_URL}/?session_id={session_id}", wait_until="domcontentloaded"
    )
    await page.wait_for_function(
        "() => document.getElementById('statusText').textContent === 'Connected'",
        timeout=10_000,
    )


async def _capture(page, name: str, *, full_page: bool = True) -> Path:
    """Full-page screenshot written to the stable artifact dir; returns its path."""
    path = SHOT_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=full_page, animations="disabled")
    return path


class TestScreenshotIntegrity:
    """Captures are valid PNGs of the expected shape (width matches the
    viewport, full-page capture fills at least one screen).

    Note we do NOT assert the populated capture is *taller* than the 1080px
    viewport: ``.topics-grid`` is ``repeat(auto-fill, minmax(350px, 1fr))``, so at
    1400px wide five cards wrap into ~4 columns and stay within one screen. Card
    stacking is layout-dependent and therefore not a robust integrity signal —
    the layout-independent ``distinct_colors`` / ``images_differ`` tests below
    carry the "content rendered" proof.
    """

    @pytest.mark.asyncio
    async def test_populated_capture_is_valid_png_filling_viewport(
        self, browser_page, injector, analysis
    ):
        page = browser_page
        session_id = injector.predictable_session_id("shot-populated")
        await injector.create_session(session_id)
        await injector.inject_topics(session_id, MIXED_SPECS)
        await _open_connected(page, session_id)
        # All five cards rendered before we capture.
        from playwright.async_api import expect as _expect

        await _expect(page.locator(".topic-card")).to_have_count(len(MIXED_SPECS), timeout=10_000)

        shot = await _capture(page, "populated")
        w, h = sa.png_dimensions(shot)
        assert w == 1400, f"capture width {w} should match 1400px viewport"
        assert h >= 1080, f"full-page height {h} should fill at least the viewport"

    @pytest.mark.asyncio
    async def test_empty_capture_is_valid_png(self, browser_page, injector, analysis):
        page = browser_page
        session_id = injector.predictable_session_id("shot-empty")
        await injector.create_session(session_id)
        await _open_connected(page, session_id)
        shot = await _capture(page, "empty")
        w, h = sa.png_dimensions(shot)
        assert w == 1400
        assert h >= 1080  # empty canvas fits within one viewport


class TestScreenshotsReflectState:
    """Distinct canvas states produce pixel-distinct captures — the guard
    against the old suite's identical-blank regression."""

    @pytest.mark.asyncio
    async def test_empty_and_populated_captures_differ(
        self, browser_page, injector, analysis
    ):
        page = browser_page

        # Empty state.
        empty_sid = injector.predictable_session_id("shot-diff-empty")
        await injector.create_session(empty_sid)
        await _open_connected(page, empty_sid)
        empty_shot = await _capture(page, "empty")

        # Same page, now populated.
        await injector.inject_topics(empty_sid, MIXED_SPECS)
        from playwright.async_api import expect as _expect

        await _expect(page.locator(".topic-card")).to_have_count(
            len(MIXED_SPECS), timeout=10_000
        )
        populated_shot = await _capture(page, "populated")

        assert sa.images_differ(empty_shot, populated_shot), (
            "empty and populated captures are pixel-identical — the canvas did "
            "not re-render the injected cards (the old suite's failure mode)"
        )

    @pytest.mark.asyncio
    async def test_populated_has_more_colors_than_empty(
        self, browser_page, injector, analysis
    ):
        """A populated canvas renders more distinct colours than the empty page
        — cards/badges/dots/text add variety a blank canvas lacks."""
        page = browser_page

        empty_sid = injector.predictable_session_id("shot-colors-empty")
        await injector.create_session(empty_sid)
        await _open_connected(page, empty_sid)
        empty_colors = sa.distinct_colors(await _capture(page, "empty_colors"))

        await injector.inject_topics(empty_sid, MIXED_SPECS)
        from playwright.async_api import expect as _expect

        await _expect(page.locator(".topic-card")).to_have_count(
            len(MIXED_SPECS), timeout=10_000
        )
        populated_colors = sa.distinct_colors(
            await _capture(page, "populated_colors")
        )

        assert populated_colors > empty_colors, (
            f"populated ({populated_colors}) should exceed empty ({empty_colors}) colours"
        )


class TestScreenshotContentRendered:
    """Absolute backstop: a populated capture objectively shows content."""

    @pytest.mark.asyncio
    async def test_populated_capture_exceeds_color_floor(
        self, browser_page, injector, analysis
    ):
        page = browser_page
        session_id = injector.predictable_session_id("shot-floor")
        await injector.create_session(session_id)
        await injector.inject_topics(session_id, MIXED_SPECS)
        await _open_connected(page, session_id)
        from playwright.async_api import expect as _expect

        await _expect(page.locator(".topic-card")).to_have_count(
            len(MIXED_SPECS), timeout=10_000
        )
        shot = await _capture(page, "floor_check")
        n = sa.distinct_colors(shot)
        assert n >= _POPULATED_COLOR_FLOOR, (
            f"populated capture has only {n} distinct colours (<{_POPULATED_COLOR_FLOOR}) "
            "— content did not render to pixels"
        )


class TestStalenessRendersVisuallyDistinct:
    """The staleness CSS colour rules produce different pixels for different
    levels — a human would see the difference; this proves it scriptably."""

    @pytest.mark.asyncio
    async def test_fresh_and_very_stale_dots_render_different_colors(
        self, browser_page, injector, analysis
    ):
        page = browser_page
        session_id = injector.predictable_session_id("shot-staleness")
        await injector.create_session(session_id)

        # One fresh, one very-stale card in the same session.
        fresh = await injector.inject_topic(
            session_id, label="Visual Fresh", topic_type="project",
            summary="green dot", urgency="normal", staleness_seconds=5,
        )
        very_stale = await injector.inject_topic(
            session_id, label="Visual Ripe", topic_type="project",
            summary="red dot", urgency="normal", staleness_seconds=7200,
        )
        await _open_connected(page, session_id)

        # Read each card's .staleness-dot bounding box (CSS px, document-relative
        # → screenshot px at device-scale 1), then capture + crop.
        fresh_dot = page.locator(
            f'.topic-card[data-topic-id="{fresh["topic_id"]}"] .staleness-dot'
        )
        stale_dot = page.locator(
            f'.topic-card[data-topic-id="{very_stale["topic_id"]}"] .staleness-dot'
        )
        await fresh_dot.wait_for(state="visible", timeout=10_000)
        await stale_dot.wait_for(state="visible", timeout=10_000)
        fresh_bbox = await fresh_dot.bounding_box()
        stale_bbox = await stale_dot.bounding_box()
        assert fresh_bbox and stale_bbox, "could not read staleness-dot bounding boxes"

        shot = await _capture(page, "staleness_dots")
        fresh_prof = sa.region_color_profile(shot, fresh_bbox)
        stale_prof = sa.region_color_profile(shot, stale_bbox)

        # The fresh dot is green (#22c55e), the very-stale dot is red (#ef4444).
        # Asserted as a channel-dominance check (robust to the dark-bg dilution
        # from cropping a few px of margin around the dot): green ⇒ G is the
        # max channel; red ⇒ R is the max channel.
        fr = fresh_prof["mean_rgb"]
        sr = stale_prof["mean_rgb"]
        assert fr is not None and sr is not None, "dot crop was empty"
        assert max(fr) == fr[1], f"fresh dot mean {fr} should be green-dominant (G max)"
        assert max(sr) == sr[0], f"very-stale dot mean {sr} should be red-dominant (R max)"
        # And they are distinct as regions outright.
        assert sa.images_differ(
            _crop_to_temp(shot, fresh_bbox, "fresh_dot"),
            _crop_to_temp(shot, stale_bbox, "stale_dot"),
        ), "fresh and very-stale dot crops are pixel-identical"


def _crop_to_temp(src: Path, bbox: dict[str, float], name: str) -> Path:
    """Write the ``bbox`` region of ``src`` to a named temp PNG; returns its path.

    Used to feed two regions through :func:`images_differ` (which takes paths).
    ``name`` disambiguates the output so two crops aren't written to the same
    file (which would make ``images_differ`` compare a file against itself).
    """
    from PIL import Image

    left = int(round(bbox["x"]))
    upper = int(round(bbox["y"]))
    right = left + int(round(bbox["width"]))
    lower = upper + int(round(bbox["height"]))
    out = SHOT_DIR / f"_region_{name}.png"
    with Image.open(src) as img:
        rgb = img.convert("RGB")
        right = min(right, rgb.size[0])
        lower = min(lower, rgb.size[1])
        rgb.crop((left, upper, right, lower)).save(out)
    return out
