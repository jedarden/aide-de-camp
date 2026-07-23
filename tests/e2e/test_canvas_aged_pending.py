"""
Headless test for the aged-pending treatment (bead adc-3wgko).

Tests that a pending card older than 30 seconds is flagged with the 'aged'
treatment, showing elapsed time and a "taking longer than expected" message.
The test uses a mock clock so it doesn't need to wait 30 real seconds.

Acceptance criteria:
- A pending card older than 30s is flagged 'taking longer than expected' with elapsed time
- Fires with the server STOPPED (zero SSE dependency) — the survival test
- Works for both the placeholder and the per-thread cards
- All values are text nodes via escapeHtml (escaping-contract)
- Headless test (tests/e2e/, real-browser Chromium pass): with the server stopped,
  the submit-time placeholder ages to the 30s flag via a mock clock
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.canvas_render import NODE, node_available

# Minimal DOM shim for Node.js tests (matches canvas_dom_runner.js)
_DOM_SHIM = """
// Escape functions (matching browser behavior)
function escapeText(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function escapeAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

// Text node class
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

// Element node class
class ShimNode {
    constructor(tag) {
        this._tag = tag;
        this._classes = [];
        this._dataset = {};
        this._textContent = "";
        this._innerHTML = "";
        this._children = [];
        this.style = {};
    }

    set className(v) {
        this._classes = String(v).split(/\\s+/).filter(Boolean);
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
        this._children = [];
        this._innerHTML = escapeText(this._textContent);
    }

    get textContent() {
        // Concatenate text from all children (including text nodes)
        if (this._children.length) {
            return this._children.map((c) => {
                return c.textContent != null ? c.textContent : "";
            }).join("");
        }
        return this._textContent;
    }

    set innerHTML(v) {
        this._innerHTML = v == null ? "" : String(v);
        this._children = [];
    }

    get innerHTML() {
        if (this._children.length) {
            return this._children.map((c) => c.outerHTML).join("");
        }
        return this._innerHTML;
    }

    _datasetAttrs() {
        const out = [];
        for (const key of Object.keys(this._dataset)) {
            const name = "data-" + key.replace(/([A-Z])/g, "-$1").toLowerCase();
            out.push(`${name}="${escapeAttr(this._dataset[key])}"`);
        }
        return out;
    }

    querySelector(selector) {
        // Simple implementation for .class selectors
        if (selector.startsWith('.')) {
            const className = selector.substring(1);
            for (const child of this._walk()) {
                if (child._classes && child._classes.includes(className)) {
                    return child;
                }
            }
        }
        return null;
    }

    _walk() {
        const result = [];
        for (const child of this._children) {
            result.push(child);
            if (child._walk) {
                result.push(...child._walk());
            }
        }
        return result;
    }

    get outerHTML() {
        const cls = this._classes.length ? ` class="${this._classes.join(" ")}"` : "";
        const attrs = this._datasetAttrs();
        const attrStr = attrs.length ? " " + attrs.join(" ") : "";
        return `<${this._tag}${cls}${attrStr}>${this.innerHTML}</${this._tag}>`;
    }
}

// Set up global document
global.document = {
    createElement(tag) {
        return new ShimNode(tag);
    },
    createTextNode(text) {
        return new ShimText(text);
    },
};
"""

# Minimal Node script that creates a pending card and ages it with a mock clock
_AGED_TEST_SCRIPT = _DOM_SHIM + """
const path = require('path');
const canvasPath = process.env.CANVAS_JS_PATH || path.resolve(__dirname, '..', '..', 'src', 'canvas', 'canvas.js');
const canvas = require(canvasPath);

// Mock current time (can be advanced by test)
let mockNow = 1000000000000;  // Some base time

function MockDate() {
    return mockNow;
}

// Create a pending placeholder card
const utterance = "Test aged treatment";
const createdAt = mockNow - 35000;  // 35 seconds ago (past threshold)
const pendingId = "test-aged-pending-1";

const card = canvas.createPendingPlaceholderCard(utterance, createdAt, pendingId);

// Apply aged treatment with current time
const isAged = canvas.applyAgedTreatment(card, mockNow);

// Serialize the card state
const result = {
    isAged: isAged,
    className: card.className,
    dataset: {...card.dataset},
    outerHTML: card.outerHTML,
    hasAgedClass: card.classList.contains('aged'),
    elapsedText: null
};

// Extract elapsed text
const elapsedEl = card.querySelector('.pending-elapsed');
if (elapsedEl) {
    result.elapsedText = elapsedEl.textContent;
}

// Extract aged note visibility
const agedNote = card.querySelector('.pending-aged-note');
if (agedNote) {
    result.agedNoteDisplay = agedNote.style.display;
    result.agedNoteText = agedNote.textContent;
}

console.log(JSON.stringify(result));
"""

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas test"
)


def test_pending_card_aged_after_30_seconds():
    """A pending card older than 30 seconds receives the 'aged' treatment."""
    canvas_js = Path(__file__).parents[2] / "src" / "canvas" / "canvas.js"

    # When using -e, we need to pass the canvas path via environment variable
    env = {"CANVAS_JS_PATH": str(canvas_js)}
    import os
    env.update(os.environ)

    proc = subprocess.run(
        [NODE, "-e", _AGED_TEST_SCRIPT],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"aged-pending test exited {proc.returncode}: {proc.stderr.strip()}"
        )

    result = json.loads(proc.stdout.strip())

    # Card should be flagged as aged
    assert result["isAged"] is True
    assert result["hasAgedClass"] is True
    assert "aged" in result["className"]

    # Elapsed time should be displayed (35s = "35s")
    assert result["elapsedText"] is not None
    assert "35s" in result["elapsedText"] or "35s" in result["elapsedText"]
    assert "elapsed" in result["elapsedText"].lower()

    # Aged note should be visible
    assert result["agedNoteDisplay"] == "" or result["agedNoteDisplay"] != "none"
    assert result["agedNoteText"] is not None
    assert "taking longer than expected" in result["agedNoteText"].lower()


def test_pending_card_not_aged_before_30_seconds():
    """A pending card younger than 30 seconds does NOT receive the 'aged' treatment."""
    canvas_js = Path(__file__).parents[2] / "src" / "canvas" / "canvas.js"

    import os
    env = {"CANVAS_JS_PATH": str(canvas_js)}
    env.update(os.environ)

    script = _DOM_SHIM + """
const path = require('path');
const canvasPath = process.env.CANVAS_JS_PATH || path.resolve(__dirname, '..', '..', 'src', 'canvas', 'canvas.js');
const canvas = require(canvasPath);

const utterance = "Test young card";
const createdAt = 1000000000000 - 15000;  // 15 seconds ago (under threshold)
const pendingId = "test-young-pending";

const card = canvas.createPendingPlaceholderCard(utterance, createdAt, pendingId);
const now = 1000000000000;

const isAged = canvas.applyAgedTreatment(card, now);

const elapsedEl = card.querySelector('.pending-elapsed');

console.log(JSON.stringify({
    isAged: isAged,
    hasAgedClass: card.classList.contains('aged'),
    elapsedText: elapsedEl ? elapsedEl.textContent : null
}));
"""

    proc = subprocess.run(
        [NODE, "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"young-pending test exited {proc.returncode}: {proc.stderr.strip()}"
        )

    result = json.loads(proc.stdout.strip())

    # Card should NOT be flagged as aged
    assert result["isAged"] is False
    assert result["hasAgedClass"] is False

    # Elapsed time should still be shown (15s)
    assert result["elapsedText"] is not None
    assert "15s" in result["elapsedText"] or "15s" in result["elapsedText"]


def test_thread_card_inherits_placeholder_timestamp_for_aging():
    """When a placeholder splits into thread cards, each thread inherits the
    original creation time, so the aged timer is continuous."""
    canvas_js = Path(__file__).parents[2] / "src" / "canvas" / "canvas.js"

    import os
    env = {"CANVAS_JS_PATH": str(canvas_js)}
    env.update(os.environ)

    script = _DOM_SHIM + """
const path = require('path');
const canvasPath = process.env.CANVAS_JS_PATH || path.resolve(__dirname, '..', '..', 'src', 'canvas', 'canvas.js');
const canvas = require(canvasPath);

// Create placeholder at t=0
const utterance = "Test timestamp inheritance";
const createdAt = 1000000000000 - 35000;  // 35s ago
const placeholderId = "utt-inherit";

const placeholder = canvas.createPendingPlaceholderCard(utterance, createdAt, placeholderId);

// Split into thread cards (simulating dispatch_ack)
const intentIds = ["intent-1", "intent-2"];
const threadCards = canvas.splitPlaceholderToThreads(utterance, createdAt, intentIds);

// Apply aged treatment at t=now
const now = 1000000000000;
const agedStates = threadCards.map(card => ({
    isAged: canvas.applyAgedTreatment(card, now),
    hasAgedClass: card.classList.contains('aged'),
    createdAt: parseInt(card.dataset.createdAt, 10)
}));

console.log(JSON.stringify(agedStates));
"""

    proc = subprocess.run(
        [NODE, "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"thread-inheritance test exited {proc.returncode}: {proc.stderr.strip()}"
        )

    results = json.loads(proc.stdout.strip())

    # Both thread cards should inherit the original timestamp
    assert all(r["createdAt"] == (1000000000000 - 35000) for r in results)

    # Both should be flagged as aged (35s > 30s threshold)
    assert all(r["isAged"] for r in results)
    assert all(r["hasAgedClass"] for r in results)


def test_aged_note_contains_retry_button():
    """The aged note includes a retry button for user action."""
    canvas_js = Path(__file__).parents[2] / "src" / "canvas" / "canvas.js"

    import os
    env = {"CANVAS_JS_PATH": str(canvas_js)}
    env.update(os.environ)

    script = _DOM_SHIM + """
const path = require('path');
const canvasPath = process.env.CANVAS_JS_PATH || path.resolve(__dirname, '..', '..', 'src', 'canvas', 'canvas.js');
const canvas = require(canvasPath);

const utterance = "Test retry button";
const createdAt = 1000000000000 - 40000;  // 40s ago
const pendingId = "test-retry";

const card = canvas.createPendingPlaceholderCard(utterance, createdAt, pendingId);
canvas.applyAgedTreatment(card, 1000000000000);

const retryBtn = card.querySelector('.pending-retry');
console.log(JSON.stringify({
    hasRetryButton: retryBtn !== null,
    retryText: retryBtn ? retryBtn.textContent : null
}));
"""

    proc = subprocess.run(
        [NODE, "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"retry-button test exited {proc.returncode}: {proc.stderr.strip()}"
        )

    result = json.loads(proc.stdout.strip())

    assert result["hasRetryButton"] is True
    assert result["retryText"] is not None
    assert "retry" in result["retryText"].lower()


def test_aged_treatment_survives_hung_server():
    """The aged treatment is applied purely client-side, with no SSE dependency.
    This test verifies that even without any server events, a pending card
    will age past 30s based solely on its creation timestamp."""
    canvas_js = Path(__file__).parents[2] / "src" / "canvas" / "canvas.js"

    import os
    env = {"CANVAS_JS_PATH": str(canvas_js)}
    env.update(os.environ)

    script = _DOM_SHIM + """
const path = require('path');
const canvasPath = process.env.CANVAS_JS_PATH || path.resolve(__dirname, '..', '..', 'src', 'canvas', 'canvas.js');
const canvas = require(canvasPath);

// Simulate a submit that created a placeholder, then the server hung
// No SSE events arrive, no fetch responses — just the local card aging
const utterance = "Server is hung";
const createdAt = 1000000000000 - 45000;  // 45s ago (server never responded)
const pendingId = "hung-server-test";

const card = canvas.createPendingPlaceholderCard(utterance, createdAt, pendingId);

// Simulate multiple timer ticks (no SSE, just local time advancing)
const times = [createdAt + 30000, createdAt + 35000, createdAt + 45000];
const agedStates = times.map(t => canvas.applyAgedTreatment(card, t));

console.log(JSON.stringify({
    // At 30s: should become aged
    becameAgedAt30s: agedStates[0] === true,
    // Still aged at 45s
    stillAgedAt45s: agedStates[2] === true,
    finalClass: card.classList.contains('aged') ? 'aged' : 'not-aged'
}));
"""

    proc = subprocess.run(
        [NODE, "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"hung-server test exited {proc.returncode}: {proc.stderr.strip()}"
        )

    result = json.loads(proc.stdout.strip())

    # Should become aged exactly at the 30s threshold
    assert result["becameAgedAt30s"] is True
    # Should remain aged
    assert result["stillAgedAt45s"] is True
    assert result["finalClass"] == "aged"


def test_elapsed_time_updates_correctly_format():
    """Test that elapsed time formats correctly: seconds, minutes+seconds."""
    canvas_js = Path(__file__).parents[2] / "src" / "canvas" / "canvas.js"

    import os
    env = {"CANVAS_JS_PATH": str(canvas_js)}
    env.update(os.environ)

    script = _DOM_SHIM + """
const path = require('path');
const canvasPath = process.env.CANVAS_JS_PATH || path.resolve(__dirname, '..', '..', 'src', 'canvas', 'canvas.js');
const canvas = require(canvasPath);

const testCases = [
    {elapsed: 5000, expected: '5s'},
    {elapsed: 65000, expected: '1m 05s'},
    {elapsed: 125000, expected: '2m 05s'},
    {elapsed: 3665000, expected: '61m 05s'},
];

const results = testCases.map(tc => {
    const utterance = "Test format";
    const createdAt = 1000000000000 - tc.elapsed;
    const card = canvas.createPendingPlaceholderCard(utterance, createdAt, "test");
    canvas.tickPendingElapsed(card, 1000000000000);
    const elapsedEl = card.querySelector('.pending-elapsed');
    const text = elapsedEl ? elapsedEl.textContent : '';
    return {
        elapsed: tc.elapsed,
        expected: tc.expected,
        actual: text,
        match: text.includes(tc.expected)
    };
});

console.log(JSON.stringify(results));
"""

    proc = subprocess.run(
        [NODE, "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"format test exited {proc.returncode}: {proc.stderr.strip()}"
        )

    results = json.loads(proc.stdout.strip())

    # All time formats should match
    for r in results:
        assert r["match"], f"Expected '{r['expected']}' in elapsed text, got '{r['actual']}'"
