"""Definitive probe: does set_offline break an established EventSource?

Opens the canvas, waits for Connected, sets offline, and polls #statusText
for 25s. Prints a timestamped trace so we can see whether 'Disconnected'
ever surfaces (and how fast), or whether the idle stream stays 'Connected'.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.nixos_browser_bootstrap import bootstrap  # noqa: E402

bootstrap()

from playwright.async_api import async_playwright  # noqa: E402

CANVAS_URL = "http://localhost:8000"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 1080})
        page = await ctx.new_page()
        # Surface any console / onerror signals.
        page.on("console", lambda m: print(f"[console.{m.type}] {m.text}"))
        page.on("pageerror", lambda e: print(f"[pageerror] {e}"))

        await page.goto(f"{CANVAS_URL}/?session_id=probe-offline", wait_until="domcontentloaded")
        await page.wait_for_function(
            "() => document.getElementById('statusText').textContent === 'Connected'",
            timeout=10_000,
        )
        print("t=0  Connected established. Going offline NOW.")
        await ctx.set_offline(True)

        prev = None
        for i in range(1, 26):
            await asyncio.sleep(1)
            txt = await page.locator("#statusText").text_content()
            mark = "  <-- CHANGE" if txt != prev else ""
            print(f"t={i:>2}s  statusText={txt!r}{mark}")
            prev = txt

        await ctx.set_offline(False)
        await asyncio.sleep(3)
        txt = await page.locator("#statusText").text_content()
        print(f"after restore (3s): statusText={txt!r}")
        await browser.close()


asyncio.run(main())
