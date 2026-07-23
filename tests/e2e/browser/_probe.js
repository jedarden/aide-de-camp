// Throwaway probe: does chromium launch, reach the canvas, report Connected,
// and can we drop/reconnect the SSE stream in a real browser? Drives the LIVE
// server at :8000 against an ephemeral session.
const { chromium } = require('playwright');

const BASE = 'http://localhost:8000';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function statusText(page) {
  return page.evaluate(() => {
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    return { cls: dot ? dot.className : null, text: txt ? txt.textContent : null };
  });
}

async function waitFor(page, pred, { timeout = 12000, every = 200 } = {}) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const v = await pred();
    if (v) return v;
    await sleep(every);
  }
  return null;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 1080 } });
  const page = await ctx.newPage();

  const sid = 'probe-' + Date.now();
  await page.goto(`${BASE}/?session_id=${sid}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#statusDot', { timeout: 5000 });

  // Wait for Connected (statusDot className == 'status-dot ').
  const connected = await waitFor(page, async () => {
    const s = await statusText(page);
    return (s.cls === 'status-dot ' || s.cls === 'status-dot') ? s : null;
  });
  console.log('INITIAL:', JSON.stringify(connected));

  // Probe 1: can we reach the global lexical `eventSource` (top-level `let`)?
  const esType = await page.evaluate(() => typeof eventSource);
  console.log('eventSource reachable as global lexical?', esType);

  // Probe 2: setOffline(true) — does it drop the live SSE stream (→ Disconnected)?
  await ctx.setOffline(true);
  const dropped = await waitFor(page, async () => {
    const s = await statusText(page);
    return s && /disconnected/.test(s.cls) ? s : null;
  }, { timeout: 8000 });
  console.log('AFTER setOffline(true):', JSON.stringify(dropped));

  // Probe 3: setOffline(false) — does the browser auto-reconnect (→ Connected)?
  await ctx.setOffline(false);
  const reconnected = await waitFor(page, async () => {
    const s = await statusText(page);
    return s && /^status-dot ?$/.test(s.cls) ? s : null;
  }, { timeout: 12000 });
  console.log('AFTER setOffline(false):', JSON.stringify(reconnected));

  await browser.close();
  console.log('DONE');
})().catch(e => { console.error('PROBE ERROR:', e); process.exit(1); });
