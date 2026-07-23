#!/usr/bin/env node
/*
 * Headless DOM runner for the REAL production canvas render module
 * (src/canvas/canvas.js). Bead adc-1l8w; ``--container`` mode (bead adc-4nd25).
 *
 * canvas.js is written so its render helpers (createTopicCard et al.) can be
 * exercised without a browser — its module docstring promises exactly this
 * file:
 *
 *     "tests/e2e/canvas_dom_runner.js loads this exact file under a minimal
 *      DOM shim and asserts the rendered HTML, with no browser or network
 *      required."
 *
 * This is that file. It provides a minimal DOM shim that implements precisely
 * the surface the render helpers touch — document.createElement,
 * document.createTextNode, appendChild, className, classList.add, dataset,
 * textContent (→ escaped innerHTML), and innerHTML get/set — then loads the
 * actual src/canvas/canvas.js and renders the card dicts the canvas really
 * receives from GET /api/v1/sessions/{id}/topics.
 *
 * Two modes:
 *
 *   1. DEFAULT (bead adc-1l8w) — render an array of card dicts through
 *      createTopicCard(), the function loadTopics() calls per card. Drives the
 *      escaping contract for the topic-card family.
 *
 *   2. ``--container`` (bead adc-4nd25) — render the shared container-decision
 *      core buildContainerChildren(cards, projects, description), which is what
 *      loadTopics() actually calls: on a fresh session with ZERO cards it
 *      returns the first-run welcome card (built from the registry project
 *      list — no DB/result dependence); the moment any real card exists it
 *      returns topic cards only (dropping the welcome card, never alongside
 *      real cards). This is the headlessly-testable contract the bead's
 *      acceptance criteria name: "welcome card renders from a zero-card
 *      session and is dropped on first result."
 *
 * The Python contract tests (tests/test_canvas_render.py and
 * tests/e2e/test_canvas_welcome_card.py) feed it JSON and assert the rendered
 * outerHTML, so a regression in the render contract is caught headlessly, in
 * CI, with no browser.
 *
 * Usage:
 *   node canvas_dom_runner.js '<json array of card dicts>'
 *   echo '<json array>' | node canvas_dom_runner.js        # stdin fallback
 *   node canvas_dom_runner.js --container '{"cards":[...],"projects":[...],"description":"..."}'
 *   echo '{...}' | node canvas_dom_runner.js --container   # stdin fallback
 *
 * Stdout: a JSON array of { outerHTML, className, dataset } per rendered node.
 */

"use strict";

const fs = require("fs");
const path = require("path");

// --- minimal DOM shim -------------------------------------------------------

function escapeText(s) {
    // Matches the browser: textContent→innerHTML escapes &, <, > (not quotes).
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

// A text node (document.createTextNode). Its serialized form is the escaped
// text — the escaping contract's literal form, since el()/createTextNode never
// splice raw markup.
class ShimText {
    constructor(text) {
        this._text = text == null ? "" : String(text);
        this.nodeType = 3;
    }

    set textContent(v) {
        this._text = v == null ? "" : String(v);
    }

    get textContent() {
        return this._text;
    }

    get outerHTML() {
        return escapeText(this._text);
    }

    get innerHTML() {
        return escapeText(this._text);
    }
}

class ShimNode {
    constructor(tag) {
        this._tag = tag;
        this._classes = [];
        this._dataset = {};
        this._textContent = "";
        this._innerHTML = "";
        this._children = []; // built via appendChild (el()/createWelcomeCard path)
        this.style = {}; // present so style.* assignments are no-ops, not crashes
    }

    set className(v) {
        this._classes = String(v).split(/\s+/).filter(Boolean);
    }

    get className() {
        return this._classes.join(" ");
    }

    get classList() {
        const self = this;
        return {
            add(c) {
                if (!self._classes.includes(c)) self._classes.push(c);
            },
            contains(c) {
                return self._classes.includes(c);
            },
            toggle(c, force) {
                const on = force === undefined ? !self._classes.includes(c) : !!force;
                if (on && !self._classes.includes(c)) self._classes.push(c);
                if (!on) self._classes = self._classes.filter((x) => x !== c);
                return on;
            },
        };
    }

    get dataset() {
        return this._dataset;
    }

    appendChild(node) {
        this._children.push(node);
        return node;
    }

    set textContent(v) {
        this._textContent = v == null ? "" : String(v);
        // Setting textContent replaces all children with a single text node —
        // mirrors the browser, and keeps escapeHtml()'s "set textContent then
        // read innerHTML" pattern producing escaped text.
        this._children = [];
        this._innerHTML = escapeText(this._textContent);
    }

    get textContent() {
        return this._textContent;
    }

    set innerHTML(v) {
        this._innerHTML = v == null ? "" : String(v);
        this._children = []; // innerHTML= replaces children, browser-faithful
    }

    get innerHTML() {
        // Children built via appendChild serialize recursively; a directly-set
        // innerHTML string (the createTopicCard path) is used otherwise.
        if (this._children.length) {
            return this._children.map((c) => c.outerHTML).join("");
        }
        return this._innerHTML;
    }

    _datasetAttrs() {
        // dataset.topicId → data-topic-id (camelCase → kebab-case w/ data- prefix).
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

// canvas.js references `document` as a free variable inside its functions, so
// it must resolve via the global scope at call time.
global.document = {
    createElement(tag) {
        return new ShimNode(tag);
    },
    createTextNode(text) {
        return new ShimText(text);
    },
};

// --- load the REAL canvas.js ------------------------------------------------

const canvasPath = path.resolve(__dirname, "..", "..", "src", "canvas", "canvas.js");
const canvas = require(canvasPath); // { createTopicCard, escapeHtml, formatStaleness, getStalenessLevel }

// --- render driver ----------------------------------------------------------

// Read the JSON payload for the active mode. argvPos is the index of the
// positional JSON arg (after any --mode flag); stdin is the pipe-friendly
// fallback. Returns the parsed value.
function readPayload(argvPos) {
    if (process.argv[argvPos] !== undefined && process.argv[argvPos] !== "") {
        return JSON.parse(process.argv[argvPos]);
    }
    const raw = fs.readFileSync(0, "utf8");
    return JSON.parse(raw);
}

function serialize(node) {
    return {
        outerHTML: node.outerHTML,
        className: node.className,
        dataset: { ...node.dataset },
    };
}

// DEFAULT mode: render an array of card dicts through createTopicCard() — the
// function loadTopics() calls per card after a reload.
function runCardsMode() {
    const cards = readPayload(2);
    if (!Array.isArray(cards)) {
        throw new Error("expected a JSON array of card dicts");
    }
    const rendered = cards.map((card) => serialize(canvas.createTopicCard(card)));
    process.stdout.write(JSON.stringify(rendered));
}

// --container mode (bead adc-4nd25): render buildContainerChildren() — the
// shared render-path core loadTopics() calls. Empty cards → the welcome card;
// any card → topic cards only (welcome dropped). The input object mirrors what
// loadTopics() builds: cards from GET /topics, projects from GET /registry,
// and an optional one-line description.
function runContainerMode() {
    const payload = readPayload(3);
    const cards = (payload && payload.cards) || [];
    const projects = (payload && payload.projects) || [];
    const description = payload && payload.description;
    const nodes = canvas.buildContainerChildren(cards, projects, description);
    const rendered = nodes.map((node) => serialize(node));
    process.stdout.write(JSON.stringify(rendered));
}

function main() {
    if (process.argv[2] === "--container") {
        runContainerMode();
    } else {
        runCardsMode();
    }
}

try {
    main();
} catch (err) {
    process.stderr.write(`canvas_dom_runner error: ${err && err.stack ? err.stack : err}\n`);
    process.exit(1);
}
