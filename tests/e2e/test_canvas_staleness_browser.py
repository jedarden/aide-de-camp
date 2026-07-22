"""
Real-browser staleness verification for canvas topic cards (bead adc-jr35).

The headless suite ``tests/test_canvas_staleness.py`` (bead adc-2vto) verifies the
staleness affordance through the Node DOM shim — it drives the REAL
``src/canvas/canvas.js`` but with **no browser**. THIS suite is the real-browser
counterpart the bead's acceptance criteria call for: it injects topics at known
ages via the adc-5unt test-data injector (``/api/v1/test/create-topic`` back-dates
``last_active`` by ``staleness_seconds``), points a headless chromium at the live
canvas, and asserts the *rendered* staleness UI in the real DOM:

- **per-level class** — fresh / stale / very-stale cards each carry the right
  level class on the card root (``.topic-card.stale`` etc.), with no bleed.
- **STALE badge** — appears ONLY once a card is no longer fresh; the visible
  badge text is ``STALE``.
- **staleness footer** — every card shows ``Updated <time-ago>`` matching
  ``formatStaleness()`` for that age, with a colored ``.staleness-dot``.
- **visual color** — the rendered card's on-screen border/colour is driven by the
  level class the stylesheet keys off of; asserting the class is present (and the
  stylesheet rule exists — see the headless suite) is the scriptable proxy for a
  screenshot diff a human would otherwise eyeball.

This runs ONLY where a real browser can launch. On NixOS the
``nixos_browser_bootstrap`` module preloads libstdc++ and resolves the missing
FHS libs so Playwright's chromium actually starts (the headless suite is the
always-green floor where it can't).
"""
from __future__ import annotations

import pytest

CANVAS_URL = "http://localhost:8000"

# (staleness_seconds, expected_level, expected_time_ago_text). Margins are wide so
# real-clock drift during the test never crosses a threshold or a formatted bucket.
#   5     → fresh     (< 600s)        "just now"  (< 60s)
#   1200  → stale     (< 3600s)       "20m ago"   (floor(1200/60)=20)
#   7200  → very-stale(>= 3600s)      "2h ago"    (floor(7200/3600)=2)
LEVELS = [
    (5, "fresh", "Updated just now"),
    (1200, "stale", "Updated 20m ago"),
    (7200, "very-stale", "Updated 2h ago"),
]


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
    """Lazily import Playwright; skip the module's tests if it is unusable.

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
    """Launch a headless browser + page; skip if chromium can't actually launch."""
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


async def _seed_and_open(
    page, injector, *, label, topic_type, summary, urgency, staleness_seconds
):
    """Inject one topic at a known age, open the canvas scoped to its session.

    Returns the created topic_id so the caller can build precise
    ``[data-topic-id="..."]`` locators. ``staleness_seconds`` is honoured
    server-side: ``/test/create-topic`` back-dates ``last_active`` to
    ``now - staleness_seconds``, so the card renders at the requested level.
    """
    session_id = injector.predictable_session_id(
        f"stalebrowser-{staleness_seconds}-{label}"
    )
    await injector.create_session(session_id)
    created = await injector.inject_topic(
        session_id,
        label=label,
        topic_type=topic_type,
        summary=summary,
        urgency=urgency,
        staleness_seconds=staleness_seconds,
    )
    topic_id = created["topic_id"]
    await page.goto(
        f"{CANVAS_URL}/?session_id={session_id}", wait_until="domcontentloaded"
    )
    return topic_id


async def _card_classes(page, topic_id: str) -> list[str]:
    """The class list of the rendered card root for ``topic_id``."""
    card = page.locator(f'.topic-card[data-topic-id="{topic_id}"]')
    cls = await card.get_attribute("class")
    return (cls or "").split()


# === per-level class on the card root ========================================


class TestStalenessLevelOnCardRoot:
    """The card root carries the staleness level as a class — the hook the CSS
    colour rules hang off of (``.topic-card.stale`` etc.)."""

    @pytest.mark.parametrize("seconds,level,_text", LEVELS)
    @pytest.mark.asyncio
    async def test_card_carries_its_level_class(
        self, seconds, level, _text, browser_page, injector, pw
    ):
        _, expect = pw
        tid = await _seed_and_open(
            browser_page, injector,
            label=f"{level} Card", topic_type="project",
            summary="aged", urgency="normal", staleness_seconds=seconds,
        )
        card = browser_page.locator(f'.topic-card[data-topic-id="{tid}"]')
        await expect(card).to_be_visible()
        classes = await _card_classes(browser_page, tid)
        assert level in classes
        # The two other levels never bleed in.
        others = {lvl for _, lvl, _ in LEVELS if lvl != level}
        assert not (others & set(classes))

    @pytest.mark.asyncio
    async def test_boundaries_match_getstalenesslevel(self, browser_page, injector, pw):
        """The rendered level tracks the same thresholds canvas.js uses:
        <600s fresh, <3600s stale, else very-stale."""
        _, expect = pw
        # 300s → fresh (5 min under the 600s / 10-min ceiling). The ceiling can't
        # be probed with a 1s margin: inject → navigate → SSE-open → render
        # orchestration takes >1s, so a 599s card ages past 600s during setup and
        # *correctly* renders "stale". (This test passed pre-fix ONLY because the
        # datetime.utcnow() server bug — see src/test/router.py — made every
        # backdated card render "fresh", masking the race.) 300s leaves minutes of
        # headroom so the fresh bucket is asserted deterministically.
        tid = await _seed_and_open(
            browser_page, injector, label="Under10m", topic_type="project",
            summary="x", urgency="normal", staleness_seconds=300,
        )
        await expect(browser_page.locator(f'.topic-card[data-topic-id="{tid}"]')).to_be_visible()
        assert "fresh" in await _card_classes(browser_page, tid)


# === STALE badge (only when not fresh) =======================================


class TestStaleBadge:
    """The uppercase "STALE" badge is the at-a-glance visual flag. It appears
    ONLY once a card is no longer fresh."""

    @pytest.mark.asyncio
    async def test_fresh_card_has_no_stale_badge(self, browser_page, injector, pw):
        _, expect = pw
        tid = await _seed_and_open(
            browser_page, injector, label="Fresh", topic_type="project",
            summary="new", urgency="normal", staleness_seconds=5,
        )
        card = browser_page.locator(f'.topic-card[data-topic-id="{tid}"]')
        await expect(card).to_be_visible()
        await expect(card.locator(".stale-badge")).to_have_count(0)

    @pytest.mark.parametrize("seconds,level,_text", LEVELS[1:])  # stale + very-stale
    @pytest.mark.asyncio
    async def test_nonfresh_card_has_stale_badge_with_level(
        self, seconds, level, _text, browser_page, injector, pw
    ):
        _, expect = pw
        tid = await _seed_and_open(
            browser_page, injector, label=f"{level} Badge", topic_type="project",
            summary="old", urgency="normal", staleness_seconds=seconds,
        )
        card = browser_page.locator(f'.topic-card[data-topic-id="{tid}"]')
        await expect(card.locator(f".stale-badge.{level}")).to_have_count(1)
        await expect(card.locator(".stale-badge")).to_have_text("STALE")

    @pytest.mark.asyncio
    async def test_stale_badge_lives_in_the_header(self, browser_page, injector, pw):
        _, expect = pw
        tid = await _seed_and_open(
            browser_page, injector, label="HeaderBadge", topic_type="project",
            summary="s", urgency="normal", staleness_seconds=1200,
        )
        card = browser_page.locator(f'.topic-card[data-topic-id="{tid}"]')
        # The badge is rendered inside .topic-header, not loose in the card body.
        await expect(card.locator(".topic-header .stale-badge")).to_have_count(1)


# === staleness footer (always present) =======================================


class TestStalenessFooter:
    """Every card shows a ``.staleness-indicator`` footer with a coloured
    ``.staleness-dot`` and a human ``Updated <time-ago>`` label matching
    ``formatStaleness()``."""

    @pytest.mark.parametrize("seconds,level,expected_text", LEVELS)
    @pytest.mark.asyncio
    async def test_footer_present_with_dot_and_time_ago(
        self, seconds, level, expected_text, browser_page, injector, pw
    ):
        _, expect = pw
        tid = await _seed_and_open(
            browser_page, injector, label=f"{level} Footer", topic_type="project",
            summary="z", urgency="normal", staleness_seconds=seconds,
        )
        card = browser_page.locator(f'.topic-card[data-topic-id="{tid}"]')
        await expect(card).to_be_visible()
        ind = card.locator(f".staleness-indicator.{level}")
        await expect(ind).to_have_count(1)
        await expect(ind.locator(f".staleness-dot.{level}")).to_have_count(1)
        # The visible "Updated <time-ago>" text matches formatStaleness() for the age.
        await expect(ind).to_contain_text(expected_text)


# === mixed ages render independently (no bleed) ==============================


class TestMixedStalenessRenders:
    """A canvas with cards of three ages renders each at its own level —
    staleness never leaks across cards."""

    @pytest.mark.asyncio
    async def test_each_card_keeps_own_level(self, browser_page, injector, pw):
        _, expect = pw
        session_id = injector.predictable_session_id("stalebrowser-mixed")
        await injector.create_session(session_id)

        ids = {}
        for seconds, level, _text in LEVELS:
            created = await injector.inject_topic(
                session_id,
                label=f"{level.title()} Mixed",
                topic_type="project",
                summary=level,
                urgency="normal",
                staleness_seconds=seconds,
            )
            ids[level] = created["topic_id"]

        await browser_page.goto(
            f"{CANVAS_URL}/?session_id={session_id}", wait_until="domcontentloaded"
        )
        # All three cards render.
        await expect(browser_page.locator(".topic-card")).to_have_count(len(LEVELS))

        # Each card carries exactly its own level and badge presence.
        for _seconds, level, _text in LEVELS:
            classes = await _card_classes(browser_page, ids[level])
            assert level in classes
            others = {lvl for _, lvl, _ in LEVELS if lvl != level}
            assert not (others & set(classes))

            card = browser_page.locator(f'.topic-card[data-topic-id="{ids[level]}"]')
            if level == "fresh":
                await expect(card.locator(".stale-badge")).to_have_count(0)
            else:
                await expect(card.locator(f".stale-badge.{level}")).to_have_count(1)
