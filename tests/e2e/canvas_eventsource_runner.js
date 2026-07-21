#!/usr/bin/env node
/*
 * Headless mock-EventSource harness for the REAL inline canvas script
 * (src/canvas/index.html, the <script> block WITHOUT a src). Bead adc-2vto.
 *
 * The companion server-side suite (tests/e2e/test_canvas_sse_reconnect.py)
 * models an SSE drop/reconnect by cancelling the server-side drain task that
 * wraps broadcaster.event_generator(). That proves the *server* still delivers
 * to a reconnected stream — but it never drives the browser's own EventSource
 * state machine (onopen → loadTopics, onerror, addEventListener('result_created')
 * → loadTopics, the 'disconnect' → eventSource.close()). This file is the
 * client-side half: it runs the EXACT inline app script the browser runs,
 * under a mock EventSource + mock fetch + minimal DOM shim, and lets a test
 * plan drive open / error / named-event / close / reconnect and observe what
 * the script does in response.
 *
 * What "reconnect" means here: a browser EventSource auto-reconnects on
 * transient onerror — the SAME object fires onopen again. That second onopen
 * is the canvas's reconnect path, and it calls loadTopics() (the re-render
 * the AC names). We model reconnect by firing onopen again on the live
 * EventSource — faithful to real browser behavior.
 *
 * The Python driver (tests/test_canvas_eventsource_reconnect.py) feeds a JSON
 * test plan and asserts on the telemetry this prints.
 *
 * Usage:
 *   node canvas_eventsource_runner.js '<json plan>'
 *   echo '<json plan>' | node canvas_eventsource_runner.js        # stdin fallback
 *
 * Plan:
 *   {
 *     "session_id": "...",          // pre-seeded URL ?session_id=
 *     "register_surface_id": "...", // what /surfaces/register returns
 *     "openapi_version": "1.2.3",   // what /openapi.json reports
 *     "cards": [ ... ],             // initial GET /topics response
 *     "steps": [
 *       {"action":"wait"},
 *       {"action":"open"},
 *       {"action":"event","name":"result_created","data":{...}},
 *       {"action":"event","name":"disconnect"},
 *       {"action":"error"},
 *       {"action":"close"},
 *       {"action":"reconnect"},
 *       {"action":"setCards","cards":[...]}
 *     ]
 *   }
 *
 * Telemetry (stdout, one JSON object):
 *   {
 *     "initCompleted": bool,         // connectSSE() ran → an EventSource exists
 *     "eventSourcesCreated": int,
 *     "currentEventSourceUrl": str,
 *     "loadTopicsCalls": int,        // GET /sessions/{id}/topics fetch count
 *     "statuses": [{"status","text"}...],   // every updateConnectionStatus()
 *     "closeCalls": int,
 *     "containerHTML": str,
 *     "containerCardCount": int,
 *     "containerCardLabels": [str...]
 *   }
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

// --- minimal DOM shim --------------------------------------------------------

function escapeText(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function escapeAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

class El {
    constructor(tag) {
        this._tag = tag;
        this._classes = [];
        this._classHistory = [];
        this._dataset = {};
        this._textContent = "";
        this._innerHTML = "";
        this._children = [];
        this._style = {};
        this._disabled = false;
        this._value = "";
        this._title = "";
        this._textHistory = [];
    }
    set className(v) {
        this._classes = String(v).split(/\s+/).filter(Boolean);
        this._classHistory.push(this._classes.join(" "));
    }
    get className() { return this._classes.join(" "); }
    get classList() {
        const self = this;
        return {
            add(c) { if (!self._classes.includes(c)) self._classes.push(c); },
            remove(c) { self._classes = self._classes.filter((x) => x !== c); },
            contains(c) { return self._classes.includes(c); },
        };
    }
    get dataset() { return this._dataset; }
    get style() { return this._style; }
    get disabled() { return this._disabled; }
    set disabled(v) { this._disabled = !!v; }
    get value() { return this._value; }
    set value(v) { this._value = v == null ? "" : String(v); }
    get title() { return this._title; }
    set title(v) { this._title = v == null ? "" : String(v); }
    get scrollHeight() { return 40; }
    set textContent(v) {
        this._textContent = v == null ? "" : String(v);
        this._innerHTML = escapeText(this._textContent);
        this._textHistory.push(this._textContent);
    }
    get textContent() { return this._textContent; }
    set innerHTML(v) {
        this._innerHTML = v == null ? "" : String(v);
        if (this._innerHTML === "") this._children = [];   // container.innerHTML = ''
    }
    get innerHTML() {
        if (this._children.length) return this._children.map((c) => c.outerHTML).join("");
        return this._innerHTML;
    }
    appendChild(c) { this._children.push(c); return c; }
    addEventListener() {}   // handlers are not driven by this harness
    _datasetAttrs() {
        const out = [];
        for (const key of Object.keys(this._dataset)) {
            const name = "data-" + key.replace(/([A-Z])/g, "-$1").toLowerCase();
            out.push(`${name}="${escapeAttr(this._dataset[key])}"`);
        }
        return out;
    }
    get outerHTML() {
        const cls = this._classes.length ? ` class="${this._classes.join(" ")}"` : "";
        const attrs = this._datasetAttrs();
        const attrStr = attrs.length ? " " + attrs.join(" ") : "";
        return `<${this._tag}${cls}${attrStr}>${this.innerHTML}</${this._tag}>`;
    }
}

const elementsById = {};
global.document = {
    getElementById(id) {
        if (!elementsById[id]) elementsById[id] = new El("div");
        return elementsById[id];
    },
    createElement(tag) { return new El(tag); },
};

// --- mock fetch + EventSource ------------------------------------------------

let topicsCards = [];
let mockSurfaceId = "surf-mock";
const fetchLog = [];

global.fetch = async (url) => {
    fetchLog.push(url);
    if (url === "/openapi.json") {
        return { ok: true, json: async () => ({ info: { version: "0.0.0" } }), text: async () => "" };
    }
    if (url === "/api/v1/surfaces/register") {
        return { ok: true, json: async () => ({ surface_id: mockSurfaceId }) };
    }
    if (url.startsWith("/api/v1/sessions/") && url.endsWith("/topics")) {
        return { ok: true, json: async () => ({ cards: topicsCards }) };
    }
    if (url === "/dispatch") {
        return { ok: true, json: async () => ({}), text: async () => "" };
    }
    return { ok: false, json: async () => ({}), text: async () => "" };
};

const eventSources = [];
let closeCount = 0;

class MockEventSource {
    constructor(url) {
        this.url = url;
        this.readyState = 0;       // 0=connecting 1=open 2=closed
        this.onopen = null;
        this.onerror = null;
        this._listeners = {};
        this._closed = false;
        eventSources.push(this);
    }
    addEventListener(name, cb) {
        (this._listeners[name] = this._listeners[name] || []).push(cb);
    }
    removeEventListener() {}
    close() { this._closed = true; this.readyState = 2; closeCount++; }
    // --- driver helpers (used by the harness, not by the app script) ---
    fireOpen() { this.readyState = 1; if (this.onopen) this.onopen({}); }
    fireError(e) { if (this.onerror) this.onerror(e || {}); }
    dispatch(name, dataObj) {
        const ev = { data: typeof dataObj === "string" ? dataObj : JSON.stringify(dataObj || {}) };
        (this._listeners[name] || []).forEach((cb) => cb(ev));
    }
}
global.EventSource = MockEventSource;

// --- globals the inline script touches ---------------------------------------

global.window = {
    location: { search: "", pathname: "/canvas" },
    history: { replaceState() {} },
    // Deliberately NO SpeechRecognition / webkitSpeechRecognition and NO
    // navigator.mediaDevices — the inline script's mic block only touches those
    // inside click handlers, which this harness never fires.
};
// Node 21+ exposes a read-only `navigator` getter on the global object, so a
// plain `global.navigator = {}` throws "which has only a getter". defineProperty
// replaces it regardless (Node's getter is configurable). The inline mic block
// only reads navigator.mediaDevices inside a click handler this harness never
// fires, but keep a shim so any future top-level navigator read can't crash it.
Object.defineProperty(global, "navigator", { value: {}, configurable: true, writable: true });

// Keep stdout reserved for the single telemetry JSON blob this harness prints at
// the end. The REAL inline app script uses console.log for debug noise ("New
// result:", "Server disconnect:", "SSE error:", …); if that reached stdout it
// would prefix the telemetry and break the Python driver's JSON.parse. Route all
// console methods to stderr — the same channel the harness's own error path uses.
global.console = Object.assign({}, console, {
    log: (...a) => process.stderr.write(a.map(String).join(" ") + "\n"),
    error: (...a) => process.stderr.write(a.map(String).join(" ") + "\n"),
    warn: (...a) => process.stderr.write(a.map(String).join(" ") + "\n"),
    info: (...a) => process.stderr.write(a.map(String).join(" ") + "\n"),
    debug: (...a) => process.stderr.write(a.map(String).join(" ") + "\n"),
});
global.setInterval = () => 0;   // suppress the 30s heartbeat timer
global.setTimeout = () => 0;

// --- load the REAL render module as globals (as <script src="/canvas.js">) ---

const canvasPath = path.resolve(__dirname, "..", "..", "src", "canvas", "canvas.js");
const canvas = require(canvasPath);
global.createTopicCard = canvas.createTopicCard;
global.escapeHtml = canvas.escapeHtml;
global.formatStaleness = canvas.formatStaleness;
global.getStalenessLevel = canvas.getStalenessLevel;

// --- extract + run the REAL inline app script --------------------------------

function readPlan() {
    if (process.argv[2] !== undefined && process.argv[2] !== "") return JSON.parse(process.argv[2]);
    return JSON.parse(fs.readFileSync(0, "utf8"));
}

function extractInlineScript(html) {
    // The main inline app script is the FIRST attribute-less <script> block —
    // the one immediately after <script src="/canvas.js"> that defines
    // connectSSE()/loadTopics()/init() and wires the EventSource handlers.
    // index.html has a LATER attribute-less <script> (the agentation feedback
    // toolbar, an IIFE that touches document.addEventListener etc.), so taking
    // the last match would run the wrong script. First match wins.
    const re = /<script>([\s\S]*?)<\/script>/g;
    const m = re.exec(html);
    if (!m) throw new Error("no attribute-less <script> block found in index.html");
    return m[1];
}

const microtaskDrain = async (n = 5) => {
    for (let i = 0; i < n; i++) await new Promise((r) => setImmediate(r));
};

async function run() {
    const plan = readPlan();
    topicsCards = Array.isArray(plan.cards) ? plan.cards : [];
    mockSurfaceId = plan.register_surface_id || "surf-mock";
    if (plan.session_id) global.window.location.search = `?session_id=${plan.session_id}`;
    if (plan.openapi_version) {
        const v = plan.openapi_version;
        global.fetch = async (url) => {
            fetchLog.push(url);
            if (url === "/openapi.json") return { ok: true, json: async () => ({ info: { version: v } }), text: async () => "" };
            if (url === "/api/v1/surfaces/register") return { ok: true, json: async () => ({ surface_id: mockSurfaceId }) };
            if (url.startsWith("/api/v1/sessions/") && url.endsWith("/topics")) return { ok: true, json: async () => ({ cards: topicsCards }) };
            if (url === "/dispatch") return { ok: true, json: async () => ({}), text: async () => "" };
            return { ok: false, json: async () => ({}), text: async () => "" };
        };
    }

    const htmlPath = path.resolve(__dirname, "..", "..", "src", "canvas", "index.html");
    const inline = extractInlineScript(fs.readFileSync(htmlPath, "utf8"));
    // runInThisContext so the inline script's free `document`/`window`/`fetch`/
    // `EventSource` resolve to the globals installed above — exactly the globals
    // a browser would provide. The script's top-level init() call schedules the
    // async registerSurface() → connectSSE() chain.
    vm.runInThisContext(inline, { filename: "canvas-inline-script.js" });

    // Let init() settle: openapi fetch → registerSurface fetch → connectSSE()
    // creates the (mock) EventSource and wires its handlers.
    await microtaskDrain(10);

    for (const step of plan.steps || []) {
        const es = eventSources[eventSources.length - 1];
        switch (step.action) {
            case "wait":
                break;
            case "open":
                if (es) es.fireOpen();
                break;
            case "error":
                if (es) es.fireError();
                break;
            case "event":
                if (es) es.dispatch(step.name, step.data);
                break;
            case "close":
                if (es) es.close();
                break;
            case "reconnect":
                // Native EventSource auto-reconnect: same object fires onopen again.
                if (es) es.fireOpen();
                break;
            case "setCards":
                topicsCards = Array.isArray(step.cards) ? step.cards : [];
                break;
            default:
                throw new Error(`unknown step action: ${step.action}`);
        }
        await microtaskDrain(5);
    }

    // --- telemetry ---
    const statusText = elementsById["statusText"];
    const statusDot = elementsById["statusDot"];
    const textHist = statusText ? statusText._textHistory : [];
    const dotHist = statusDot ? statusDot._classHistory : [];
    const statuses = textHist.map((text, i) => {
        const dot = dotHist[i] || "";
        return { status: dot.replace(/^status-dot\s*/, "").trim(), text };
    });

    const container = elementsById["topicsContainer"];
    const containerHTML = container ? container.innerHTML : "";
    // card labels live in the rendered <topic-header> text; pull them out of the
    // HTML the real createTopicCard() produced.
    const containerCardLabels = (containerHTML.match(/<div class="topic-header">([\s\S]*?)<\/div>/g) || [])
        .map((h) => {
            // topic-label is a <div> in canvas.js, not a <span>; match the class
            // and grab visible text up to the next tag so this is tag-agnostic.
            const m = h.match(/class="topic-label">\s*([^<]+)/);
            return m ? m[1].trim() : "";
        });

    // Fallback: if the label class name shifts, best-effort labels from dataset.
    const containerCardCount = (containerHTML.match(/class="topic-card/g) || []).length;

    process.stdout.write(JSON.stringify({
        initCompleted: eventSources.length > 0,
        eventSourcesCreated: eventSources.length,
        currentEventSourceUrl: eventSources.length ? eventSources[eventSources.length - 1].url : null,
        loadTopicsCalls: fetchLog.filter((u) => u.startsWith("/api/v1/sessions/") && u.endsWith("/topics")).length,
        statuses,
        closeCalls: closeCount,
        containerHTML,
        containerCardCount,
        containerCardLabels,
    }));
}

run().catch((err) => {
    process.stderr.write(`canvas_eventsource_runner error: ${err && err.stack ? err.stack : err}\n`);
    process.exit(1);
});
