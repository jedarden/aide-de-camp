#!/usr/bin/env node
/**
 * Direct Node.js test for createFailedCard rendering function.
 * Uses the DOM shim from canvas_dom_runner.js to test headlessly.
 */

"use strict";

// Load the DOM shim from canvas_dom_runner.js
const fs = require("fs");
const path = require("path");

// Read and eval the DOM shim setup
const shimCode = fs.readFileSync(
    path.join(__dirname, "e2e/canvas_dom_runner.js"),
    "utf8"
);

// Extract the DOM classes (simplified - we'll recreate just what we need)
function escapeText(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

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
        this._children = [];
        this.nodeType = 1;
    }

    get className() {
        return this._classes.join(" ");
    }

    set className(v) {
        this._classes = v ? v.split(/\s+/).filter(c => c) : [];
    }

    get classList() {
        const self = this;
        return {
            add: function(cls) {
                if (!self._classes.includes(cls)) self._classes.push(cls);
            },
            remove: function(cls) {
                self._classes = self._classes.filter(c => c !== cls);
            },
            contains: function(cls) {
                return self._classes.includes(cls);
            },
            toggle: function(cls, force) {
                const has = self._classes.includes(cls);
                if (force === undefined || force !== has) {
                    if (has) {
                        self._classes = self._classes.filter(c => c !== cls);
                    } else {
                        self._classes.push(cls);
                    }
                }
                return self._classes.includes(cls);
            }
        };
    }

    get dataset() {
        return this._dataset;
    }

    get textContent() {
        return this._children.map(c => c.textContent).join("");
    }

    set textContent(v) {
        this._textContent = v == null ? "" : String(v);
    }

    appendChild(child) {
        this._children.push(child);
        return child;
    }

    querySelector(sel) {
        if (sel.startsWith(".")) {
            const cls = sel.slice(1);
            for (const c of this._children) {
                if (c._classes && c._classes.includes(cls)) return c;
            }
        }
        return null;
    }

    querySelectorAll(sel) {
        if (sel.startsWith(".")) {
            const cls = sel.slice(1);
            return this._children.filter(c => c._classes && c._classes.includes(cls));
        }
        return [];
    }

    get outerHTML() {
        const attrs = [];
        if (this.className) attrs.push(` class="${escapeAttr(this.className)}"`);
        for (const [k, v] of Object.entries(this._dataset)) {
            attrs.push(` data-${k}="${escapeAttr(v)}"`);
        }

        const childrenHTML = this._children.map(c =>
            typeof c === "string" ? escapeText(c) : c.outerHTML
        ).join("");

        return `<${this._tag}${attrs.join("")}>${childrenHTML}</${this._tag}>`;
    }

    get innerHTML() {
        return this._children.map(c =>
            typeof c === "string" ? escapeText(c) : c.outerHTML
        ).join("");
    }

    set innerHTML(v) {
        this._innerHTML = v;
    }
}

function escapeAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

// Setup global document
global.document = {
    createElement: (tag) => new ShimNode(tag),
    createTextNode: (text) => new ShimText(text)
};

// Setup module.exports for the export shim to work
global.module = { exports: {} };

// Now load canvas.js
const canvasPath = path.join(__dirname, "../src/canvas/canvas.js");
const canvasCode = fs.readFileSync(canvasPath, "utf8");

// Remove the Node.js check at the top of canvas.js (we're providing document)
const processedCanvasCode = canvasCode.replace(
    /if \(typeof module !== 'undefined' && module\.exports && typeof document === 'undefined'\) \{[^}]+\}/,
    ""
);

eval(processedCanvasCode);

// Extract functions from module.exports
const {
    createFailedCard,
    createTopicCard,
    createWelcomeCard,
    createErrorCard,
    createStuckCard
} = module.exports;

// Run tests
let failed = 0;

function assert(desc, condition) {
    if (!condition) {
        console.log(`❌ FAIL: ${desc}`);
        failed++;
    } else {
        console.log(`✅ PASS: ${desc}`);
    }
}

console.log("\n=== Testing createFailedCard function ===\n");

// Test 1: Failed card with all fields
console.log("Test 1: Full failed card with all fields");
try {
    const card1 = createFailedCard({
        bead_id: "adc-test123",
        failure_reason: "Worker process crashed",
        error_type: "worker_crash",
        message: "The task failed to complete"
    });

    const html1 = card1.outerHTML;

    assert("Has failed-card class", card1.classList.contains("failed-card"));
    assert("Has builtin=failed dataset", card1.dataset.builtin === "failed");
    assert("Has bead_id dataset", card1.dataset.beadId === "adc-test123");
    assert("Contains 'Task failed' title", html1.includes("Task failed"));
    assert("Contains failure_reason", html1.includes("Worker process crashed"));
    assert("Contains bead_id in body", html1.includes("adc-test123"));
    assert("Contains error_type", html1.includes("worker_crash"));
    assert("Contains message", html1.includes("The task failed to complete"));
} catch (e) {
    console.log(`❌ EXCEPTION in Test 1: ${e.message}`);
    failed++;
}

// Test 2: Failed card with minimal fields (graceful handling)
console.log("\nTest 2: Minimal failed card (graceful handling)");
try {
    const card2 = createFailedCard({
        bead_id: "adc-minimal",
        failure_reason: "Test failure"
    });

    const html2 = card2.outerHTML;

    assert("Renders without error", card2 !== null);
    assert("Has failed-card class", card2.classList.contains("failed-card"));
    assert("Contains 'Task failed' title", html2.includes("Task failed"));
    assert("Contains failure_reason", html2.includes("Test failure"));
    assert("Contains bead_id", html2.includes("adc-minimal"));
} catch (e) {
    console.log(`❌ EXCEPTION in Test 2: ${e.message}`);
    failed++;
}

// Test 3: Failed card with empty/missing fields (graceful handling)
console.log("\nTest 3: Empty failed card (graceful handling)");
try {
    const card3 = createFailedCard({});

    const html3 = card3.outerHTML;

    assert("Renders without error", card3 !== null);
    assert("Has failed-card class", card3.classList.contains("failed-card"));
    assert("Contains 'Task failed' title", html3.includes("Task failed"));
    assert("Has retry button", html3.includes("Retry"));
} catch (e) {
    console.log(`❌ EXCEPTION in Test 3: ${e.message}`);
    failed++;
}

// Test 4: Verify HTML escaping for malicious input
console.log("\nTest 4: HTML escaping for malicious input");
try {
    const card4 = createFailedCard({
        bead_id: "<script>alert('xss')</script>",
        failure_reason: "<img src=x onerror=alert(1)>",
        message: "'; DROP TABLE cards; --"
    });

    const html4 = card4.outerHTML;

    // Should NOT contain raw script tags (should be escaped)
    assert("Escapes <script> tag", !html4.includes("<script>alert") || html4.includes("&lt;script&gt;"));
    assert("Escapes <img> tag", !html4.includes("<img src=") || html4.includes("&lt;img"));
} catch (e) {
    console.log(`❌ EXCEPTION in Test 4: ${e.message}`);
    failed++;
}

// Test 5: Verify CSS selector targets
console.log("\nTest 5: CSS selector targets");
try {
    const card5 = createFailedCard({
        bead_id: "adc-selectors",
        failure_reason: "Test"
    });

    assert("Selectable by .failed-card", card5.classList.contains("failed-card"));
    assert("Selectable by .builtin-card", card5.classList.contains("builtin-card"));
    assert("Selectable by [data-builtin=\"failed\"]", card5.dataset.builtin === "failed");
} catch (e) {
    console.log(`❌ EXCEPTION in Test 5: ${e.message}`);
    failed++;
}

// Summary
console.log("\n=== Test Summary ===");
if (failed === 0) {
    console.log("✅ All tests passed!");
    process.exit(0);
} else {
    console.log(`❌ ${failed} test(s) failed`);
    process.exit(1);
}
