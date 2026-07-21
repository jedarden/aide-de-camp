#!/usr/bin/env node
/*
 * Headless DOM runner for the REAL production canvas render module
 * (src/canvas/canvas.js). Bead adc-1l8w.
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
 * the surface createTopicCard()/escapeHtml() touch — document.createElement,
 * className, classList.add, dataset, textContent (→ escaped innerHTML), and
 * innerHTML get/set — then loads the actual src/canvas/canvas.js and renders
 * the card dicts the canvas really receives from
 * GET /api/v1/sessions/{id}/topics.
 *
 * The Python contract test (tests/test_canvas_render.py) feeds it card JSON
 * and asserts the rendered outerHTML, so a regression in the render contract
 * is caught headlessly, in CI, with no browser.
 *
 * Usage:
 *   node canvas_dom_runner.js '<json array of card dicts>'
 *   echo '<json array>' | node canvas_dom_runner.js        # stdin fallback
 *
 * Stdout: a JSON array of { outerHTML, className, dataset } per card.
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

class ShimNode {
    constructor(tag) {
        this._tag = tag;
        this._classes = [];
        this._dataset = {};
        this._textContent = "";
        this._innerHTML = "";
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
        };
    }

    get dataset() {
        return this._dataset;
    }

    set textContent(v) {
        this._textContent = v == null ? "" : String(v);
        this._innerHTML = escapeText(this._textContent);
    }

    get textContent() {
        return this._textContent;
    }

    set innerHTML(v) {
        this._innerHTML = v == null ? "" : String(v);
    }

    get innerHTML() {
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
        return `<${this._tag}${cls}${attrStr}>${this._innerHTML}</${this._tag}>`;
    }
}

// canvas.js references `document` as a free variable inside its functions, so
// it must resolve via the global scope at call time.
global.document = {
    createElement(tag) {
        return new ShimNode(tag);
    },
};

// --- load the REAL canvas.js ------------------------------------------------

const canvasPath = path.resolve(__dirname, "..", "..", "src", "canvas", "canvas.js");
const canvas = require(canvasPath); // { createTopicCard, escapeHtml, formatStaleness, getStalenessLevel }

// --- render driver ----------------------------------------------------------

function readCards() {
    // argv[2] wins; fall back to stdin so the runner is pipe-friendly.
    if (process.argv[2] !== undefined && process.argv[2] !== "") {
        return JSON.parse(process.argv[2]);
    }
    const raw = fs.readFileSync(0, "utf8");
    return JSON.parse(raw);
}

function main() {
    const cards = readCards();
    if (!Array.isArray(cards)) {
        throw new Error("expected a JSON array of card dicts");
    }

    const rendered = cards.map((card) => {
        const el = canvas.createTopicCard(card);
        return {
            outerHTML: el.outerHTML,
            className: el.className,
            dataset: { ...el.dataset },
        };
    });

    process.stdout.write(JSON.stringify(rendered));
}

try {
    main();
} catch (err) {
    process.stderr.write(`canvas_dom_runner error: ${err && err.stack ? err.stack : err}\n`);
    process.exit(1);
}
