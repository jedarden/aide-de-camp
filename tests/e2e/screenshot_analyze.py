"""Objective visual analysis of canvas screenshots (bead adc-jr35).

The canvas browser suites (staleness / DOM / SSE-reconnect) verify the *DOM*
— classes, data attributes, text. A screenshot, on its own, is just evidence a
human would eyeball. This module makes a screenshot *scriptably verifiable*:
given a PNG written by Playwright's ``page.screenshot()``, it answers objective
questions about what was actually rendered to pixels:

- :func:`png_dimensions` — the captured image's width/height (valid PNG, and the
  full-page height grows past the viewport when cards stack).
- :func:`distinct_colors` — how many distinct ``(R, G, B)`` tuples appear. A
  blank or single-colour page collapses to a handful; a canvas with rendered
  cards, badges, dots and text yields thousands. This is the objective signal
  that *content rendered* — the failure mode the old suite hit, where every
  capture was an identical 30075-byte blank because Playwright couldn't launch.
- :func:`is_uniform` — boolean ``distinct_colors <= threshold`` (blank / error page).
- :func:`region_color_profile` — mean colour + colour count within a bounding box,
  so two cards can be proven to render *visually* differently (e.g. a fresh card
  vs a very-stale one, whose CSS colour rules the staleness class keys off of).
- :func:`images_differ` — two captures are pixel-distinct (catches "every
  screenshot is the same static image" regressions).

PIL (Pillow) backs all of it; if PIL is not importable, every function raises
:class:`AnalysisUnavailableError` and the caller is expected to ``pytest.skip`` (the
screenshot test fixture does). Pillow is declared in ``pyproject.toml``'s ``dev``
extras, so a fresh ``pip install -e ".[dev]"`` after a NixOS rebuild brings it.

Device-pixel alignment
----------------------
The browser fixtures launch chromium at the default device scale ratio of 1
(``new_context(viewport=...)`` with no ``device_scale_ratio``), so 1 CSS pixel
maps to exactly 1 screenshot pixel. That is what lets a Playwright
``bounding_box()`` (returned in CSS pixels, document-relative) be cropped
directly from a ``full_page=True`` screenshot with PIL. Keep that invariant in
mind before changing the viewport or scale ratio.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:  # Pillow is a declared dev extra; absent only on a bare env.
    Image = None  # type: ignore[assignment]
    _HAS_PIL = False


class AnalysisUnavailableError(RuntimeError):
    """Raised when Pillow is not importable. Callers should ``pytest.skip``."""


def _require_pil() -> None:
    if not _HAS_PIL:
        raise AnalysisUnavailableError(
            "Pillow is not installed — install dev extras: pip install -e '.[dev]'"
        )


def _as_path(path: str | Path) -> str:
    return str(path)


def png_dimensions(path: str | Path) -> tuple[int, int]:
    """Return ``(width, height)`` in pixels of the PNG at ``path``.

    Verifies the capture is a real image of the expected shape (e.g. a full-page
    screenshot of a multi-card canvas is taller than the 1080px viewport).
    """
    _require_pil()
    with Image.open(_as_path(path)) as img:
        return img.size  # (width, height)


def _downsample(img: "Image.Image", *, target_pixels: int) -> "Image.Image":
    """Shrink ``img`` so it has roughly ``target_pixels`` pixels, for fast colour counting.

    Colour counting scales with pixel count; a 1400×3000 full-page capture is
    ~4M pixels. Downsampling to ~40k loses no meaningful colour information
    (cards are large contiguous colour regions) but cuts the count from seconds
    to milliseconds.
    """
    w, h = img.size
    if w * h <= target_pixels:
        return img
    scale = (target_pixels / (w * h)) ** 0.5
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new_size)


def distinct_colors(path: str | Path, *, sample_target_pixels: int = 40_000) -> int:
    """Count distinct ``(R, G, B)`` tuples in the image (alpha ignored).

    The objective "did content render" metric: a blank/error page yields a
    single-digit count; a populated canvas yields thousands. The image is
    downsampled first (see :func:`_downsample`) — colour *variety*, not pixel
    count, is what matters, and downsampling preserves it.
    """
    _require_pil()
    with Image.open(_as_path(path)) as img:
        rgb = img.convert("RGB")
        small = _downsample(rgb, target_pixels=sample_target_pixels)
        colors = small.getcolors(maxcolors=small.size[0] * small.size[1] + 1)
        if colors is None:
            # More distinct colours than maxcolors allowed — i.e. a LOT. Count
            # exactly via a set (only reachable on a tiny/undownsampled image).
            return len({px for _, px in small.getdata()})
        return len(colors)


def is_uniform(
    path: str | Path, *, max_colors: int = 8, sample_target_pixels: int = 40_000
) -> bool:
    """True iff the image is effectively blank (``distinct_colors <= max_colors``).

    ``max_colors=8`` tolerates anti-aliasing edges / a status dot while still
    flagging a genuinely empty or error page.
    """
    return distinct_colors(path, sample_target_pixels=sample_target_pixels) <= max_colors


def region_color_profile(
    path: str | Path, bbox: dict[str, float], *, sample_target_pixels: int = 8_000
) -> dict[str, Any]:
    """Colour stats for the sub-rectangle ``bbox`` within the screenshot.

    ``bbox`` is a Playwright bounding box: ``{"x","y","width","height"}`` in CSS
    pixels, document-relative. With device-scale-ratio 1 those map 1:1 to
    screenshot pixels (see module docstring).

    Returns ``{"distinct_colors": int, "mean_rgb": (r,g,b)}``. The mean colour
    is the at-a-glance "what colour is this card" value a human sees; comparing
    two regions' means (and colour counts) proves they render differently.
    """
    _require_pil()
    left = int(round(bbox["x"]))
    upper = int(round(bbox["y"]))
    right = left + int(round(bbox["width"]))
    lower = upper + int(round(bbox["height"]))
    with Image.open(_as_path(path)) as img:
        rgb = img.convert("RGB")
        # Clamp to image bounds — a card near the bottom of a long page may sit
        # at the edge of the full-page capture.
        right = min(right, rgb.size[0])
        lower = min(lower, rgb.size[1])
        crop = rgb.crop((left, upper, right, lower))
        if crop.size == (0, 0):
            return {"distinct_colors": 0, "mean_rgb": None}
        small = _downsample(crop, target_pixels=sample_target_pixels)
        npx = small.size[0] * small.size[1]
        # getcolors returns [(count, (r,g,b)), ...] — one entry per distinct
        # colour — capped at ``maxcolors`` (None if exceeded). Computing the mean
        # from it (count-weighted) avoids the deprecated ``getdata`` and is
        # faster than materializing every pixel. For a small card region the
        # distinct-colour count stays well under the cap.
        colors = small.getcolors(maxcolors=npx + 1)
        if colors is None:
            # Too many distinct colours for getcolors (unexpected for a card
            # region after downsampling) — fall back to an exact pixel pass.
            data = list(small.getdata())  # still works through Pillow 13
            n = len(data)
            mean = (sum(p[0] for p in data) // n,
                    sum(p[1] for p in data) // n,
                    sum(p[2] for p in data) // n)
            return {"distinct_colors": len(set(data)), "mean_rgb": mean}
        total = sum(c for c, _ in colors)
        if total == 0:
            return {"distinct_colors": 0, "mean_rgb": None}
        rs = sum(c * px[0] for c, px in colors)
        gs = sum(c * px[1] for c, px in colors)
        bs = sum(c * px[2] for c, px in colors)
        mean = (rs // total, gs // total, bs // total)
        return {"distinct_colors": len(colors), "mean_rgb": mean}


def images_differ(path_a: str | Path, path_b: str | Path) -> bool:
    """True iff the two PNGs are pixel-distinct.

    Catches the "every screenshot is byte-identical" regression the old suite
    produced. Compares content (not file metadata): two captures that render the
    same pixels count as equal even if PNG encoding differs.
    """
    _require_pil()
    with Image.open(_as_path(path_a)) as a, Image.open(_as_path(path_b)) as b:
        if a.size != b.size:
            return True
        # Convert both to RGB and compare raw bytes. Image.tobytes is exact.
        return a.convert("RGB").tobytes() != b.convert("RGB").tobytes()


__all__ = [
    "AnalysisUnavailableError",
    "png_dimensions",
    "distinct_colors",
    "is_uniform",
    "region_color_profile",
    "images_differ",
]
