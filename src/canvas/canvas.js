/*
 * ADC Canvas — rendering helpers.
 *
 * Pure functions that turn a /api/v1/sessions/{id}/topics card dict into a DOM
 * topic-card element, and that build the four BUILT-IN card families the plan
 * ships as fixed templates in this served frontend (Component Library →
 * "Built-in cards"): (1) generic fallback, (2) first-run welcome card, (3)
 * pending/ack cards (submit-time placeholder, per-thread pending with
 * per-source progress, aged-pending treatment), and (4) the error/clarification
 * family from Degraded-State UX. They are kept in this separate, loadable
 * module (rather than inline in index.html) so the render contract can be
 * verified headlessly — tests/e2e/canvas_dom_runner.js and
 * tests/e2e/canvas_builtin_runner.js load this exact file under a minimal DOM
 * shim and assert the rendered HTML, with no browser or network required.
 *
 * ESCAPING CONTRACT (the render-path escaping contract, see plan UI-Regen Agent
 * "Escaping contract"): every dynamic value — registry descriptions, utterance
 * text, per-source names, error detail, elapsed strings, LLM/worker-authored
 * free text — is interpolated through escapeHtml(), which sets it via a text
 * node (textContent → the browser's own escaper). No dynamic value is ever
 * spliced raw into innerHTML. The built-in builders below all go through the
 * same escapeHtml() the topic card uses, so they are bound by the identical
 * escaping contract.
 *
 * In the browser, index.html loads this via <script src="/canvas.js"> before
 * the inline app script, so these declarations are globals just like they were
 * when they lived inline. In Node, the trailing export shim exposes them via
 * module.exports for the DOM tests.
 */

// Node.js compatibility: ensure document is available in Node for headless tests
// When loaded in Node (module.exports exists), make the global document accessible
// to the el() helper function which uses document.createElement() and .createTextNode()
if (typeof module !== 'undefined' && module.exports && typeof document === 'undefined') {
    var document = global.document;
}

// ---------------------------------------------------------------------------
// Tunables (exported so tests can assert against the same constants)
// ---------------------------------------------------------------------------

// Hot-path intents flag at 30s pending (their budget is 3s) — see plan, The
// Async Path → Visible aging + Degraded-State UX aged-pending row. This flag is
// applied PURELY client-side from the local placeholder's creation time so it
// survives a hung/wedged server (no SSE dependency).
var PENDING_AGE_THRESHOLD_MS = 30000;

// ---------------------------------------------------------------------------
// Existing topic-card render helpers
// ---------------------------------------------------------------------------

function formatStaleness(seconds) {
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

function getStalenessLevel(seconds) {
    if (seconds < 600) return 'fresh';      // 10 minutes
    if (seconds < 3600) return 'stale';     // 1 hour
    return 'very-stale';
}

function createTopicCard(cardData) {
    const topic = cardData.topic;
    const staleness = cardData.staleness;
    const latestResult = cardData.latest_result;

    const card = document.createElement('div');
    card.className = 'topic-card';
    card.dataset.topicId = topic.id;

    const stalenessLevel = getStalenessLevel(staleness.seconds);
    card.classList.add(stalenessLevel);

    const typeClass = topic.type || 'adhoc';

    // Expose the topic type as a data attribute alongside data-topic-id so cards
    // are queryable by type with a robust, stable selector (e.g.
    // [data-topic-type="research"]) rather than relying on class names. The DOM
    // verification suites assert both dataset attributes are present per card.
    card.dataset.topicType = typeClass;

    let html = `
        <div class="topic-header">
            <div class="topic-label">${escapeHtml(topic.label)}</div>
            <div>
                <span class="topic-type ${typeClass}">${escapeHtml(topic.type || 'adhoc')}</span>
                ${stalenessLevel !== 'fresh' ? `<span class="stale-badge ${stalenessLevel}">STALE</span>` : ''}
            </div>
        </div>
    `;

    // Add latest result if available
    if (latestResult) {
        const urgencyClass = latestResult.urgency || 'normal';
        html += `
            <div class="result-content">
                <div class="result-summary">
                    ${escapeHtml(latestResult.summary)}
                    <span class="urgency-badge ${urgencyClass}">${escapeHtml(urgencyClass)}</span>
                </div>
        `;

        if (latestResult.data) {
            html += `<div class="result-data">${escapeHtml(JSON.stringify(latestResult.data, null, 2))}</div>`;
        }

        html += `</div>`;
    }

    // Add staleness indicator
    const timeAgo = formatStaleness(staleness.seconds);
    html += `
        <div class="staleness-indicator ${stalenessLevel}">
            <span class="staleness-dot ${stalenessLevel}"></span>
            <span>Updated ${timeAgo}</span>
        </div>
    `;

    card.innerHTML = html;
    return card;
}

// ---------------------------------------------------------------------------
// Shared escaping + small DOM helpers (text-node based — escaping contract)
// ---------------------------------------------------------------------------

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

/**
 * Build a DOM element with tag + className + a list of children/strings.
 *
 * Strings are appended as TEXT NODES (never spliced into innerHTML), which is
 * the escaping contract's literal form — a markup-looking log line renders as
 * literal text instead of breaking layout. Use this for any value that must be
 * inserted verbatim as text.
 */
function el(tag, className, children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    (children || []).forEach(function (c) {
        if (c == null) return;
        if (typeof c === 'string' || typeof c === 'number') {
            node.appendChild(document.createTextNode(String(c)));
        } else {
            node.appendChild(c);
        }
    });
    return node;
}

// Seconds → "0s" / "12s" / "1m 05s" elapsed label for pending cards.
function formatElapsed(ms) {
    const s = Math.max(0, Math.floor((ms || 0) / 1000));
    if (s < 60) return s + 's';
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return m + 'm ' + (rem < 10 ? '0' : '') + rem + 's';
}

// ---------------------------------------------------------------------------
// (2) First-run welcome card — built-in, zero DB dependence
// ---------------------------------------------------------------------------

// Default example utterances used when the registry yields no project with a
// supported intent to derive one from. These never touch the component DB.
var DEFAULT_EXAMPLE_UTTERANCES = [
    'Has the options pipeline caught up?',
    'What is the state of the ibkr mcp?',
    'Queue up a research task on recent pipeline errors — no rush.'
];

// Map a supported intent type to an example utterance fragment, so the welcome
// card's examples are drawn from the projects the router actually knows about
// (plan: Cold start & demo seed — "2-3 example utterances drawn from those
// projects' supported intents").
var INTENT_EXAMPLES = {
    status: 'What is the status of {proj}?',
    action: 'Restart the {proj} deployment.',
    brainstorm: 'Brainstorm trade-offs for {proj}.',
    lookup: 'Pull up recent logs for {proj}.',
    'task-profile': 'Queue up a research task on {proj} — no rush.',
    'self-modification': 'Add an alias to the {proj} registry entry.',
    'monitoring-config': 'Watch {proj} for pod restarts.',
    reminder: 'Remind me to check {proj} in an hour.'
};

function _deriveExamples(projects) {
    const out = [];
    const seen = {};
    // Prefer projects that carry a description (registry.yaml entries) so the
    // welcome examples reference real, described projects — not bare discovered
    // repos with auto-README blurbs.
    const ordered = (projects || []).slice().sort(function (a, b) {
        const ad = a && a.description ? 0 : 1;
        const bd = b && b.description ? 0 : 1;
        return ad - bd;
    });
    ordered.forEach(function (p) {
        if (out.length >= 3) return;
        (p.intent_support || []).forEach(function (intent) {
            if (out.length >= 3 || seen[intent]) return;
            const tmpl = INTENT_EXAMPLES[intent];
            if (!tmpl) return;
            seen[intent] = true;
            out.push(tmpl.replace('{proj}', p.slug || p.name || 'the project'));
        });
    });
    return out.length ? out : DEFAULT_EXAMPLE_UTTERANCES.slice(0, 3);
}

// Cap the welcome-card project list so a 38-repo registry doesn't overwhelm the
// first frame. The first N are shown; an "+N more" note counts the rest.
var WELCOME_PROJECT_CAP = 12;

/**
 * Build the first-run welcome card.
 *
 * @param {Array} projects  registry entries [{slug,name,description,intent_support,aliases}]
 * @param {string} [description]  one-line description of aide-de-camp
 * @returns {HTMLElement} a .welcome-card element (data-builtin="welcome")
 *
 * Renders even against an empty component library / DB — the project list comes
 * from config/registry.yaml (served at /api/v1/registry), not the DB. The first
 * real result replaces it (the canvas drops it once any topic card exists).
 */
function createWelcomeCard(projects, description) {
    const card = el('div', 'builtin-card welcome-card');
    card.dataset.builtin = 'welcome';

    card.appendChild(el('div', 'builtin-header', [
        el('span', 'builtin-icon', ['👋']),
        el('span', 'builtin-title', ['Welcome to ADC'])
    ]));

    card.appendChild(el('p', 'builtin-desc', [
        description || 'A single input surface that routes what you say to the right project, fetches in parallel, and renders results as live cards.'
    ]));

    card.appendChild(el('div', 'builtin-section-title', ['Registered projects']));
    const list = el('ul', 'builtin-project-list');
    (projects || []).forEach(function (p) {
        const slug = p.slug || p.name || 'project';
        const desc = p.description || '';
        const intents = (p.intent_support || []).join(' · ');
        const li = el('li', 'builtin-project');
        li.appendChild(el('strong', 'builtin-project-slug', [slug]));
        if (desc) li.appendChild(document.createTextNode(' — ' + desc));
        if (intents) li.appendChild(el('span', 'builtin-intents', [' ' + intents]));
        list.appendChild(li);
    });
    if (!(projects && projects.length)) {
        list.appendChild(el('li', 'builtin-project', ['No projects registered yet.']));
    }
    card.appendChild(list);

    card.appendChild(el('div', 'builtin-section-title', ['Try asking']));
    const examples = el('ul', 'builtin-examples');
    _deriveExamples(projects).forEach(function (ex) {
        examples.appendChild(el('li', 'builtin-example', [ex]));
    });
    card.appendChild(examples);

    return card;
}

// ---------------------------------------------------------------------------
// Container decision — the headlessly-testable core of loadTopics()
// ---------------------------------------------------------------------------

/**
 * Decide what the canvas topic-container shows for a given card set.
 *
 * This is the shared render path index.html's ``loadTopics()`` calls after
 * ``GET /api/v1/sessions/{id}/topics``: on a fresh session with zero cards it
 * shows the first-run welcome card (built from the registry project list — no
 * DB/result dependence); the moment any real card exists it shows only topic
 * cards, which drops any welcome card (never alongside real cards). The caller
 * clears the container and appends the returned nodes.
 *
 * Kept here (not inline in index.html) so the zero→welcome / first-result→drop
 * contract is verifiable headlessly: ``tests/e2e/canvas_dom_runner.js`` drives
 * this exact function (``--container`` mode) and asserts the welcome card
 * renders from an empty card set and is absent once a real card is present.
 *
 * @param {Array} [cards]      card dicts from /topics (empty → welcome card)
 * @param {Array} [projects]   registry entries for the welcome card
 * @param {string} [description] one-line description for the welcome card
 * @returns {HTMLElement[]}    child nodes for the container
 */
function buildContainerChildren(cards, projects, description) {
    if (!cards || cards.length === 0) {
        return [createWelcomeCard(projects, description)];
    }
    return cards.map(function (c) { return createTopicCard(c); });
}

// ---------------------------------------------------------------------------
// (3) Pending/ack cards — submit-time placeholder + per-thread pending
// ---------------------------------------------------------------------------

/**
 * Build a submit-time pending placeholder.
 *
 * Created LOCALLY at dispatch() submit time, BEFORE any server response, so a
 * hung/wedged server still leaves a card on canvas to age (plan, Escalate
 * Strand → Pending/ack card render path). It splits into per-thread pending
 * cards when the dispatch ack (the /dispatch HTTP response) carries intent_ids.
 *
 * @param {string} utterance   the raw text being dispatched
 * @param {number} createdAt   Date.now() at placeholder creation (ms epoch)
 * @param {string} [pendingId] stable id for this placeholder (utterance id)
 * @returns {HTMLElement} a .pending-card.placeholder (data-builtin="pending")
 */
function createPendingPlaceholderCard(utterance, createdAt, pendingId) {
    const card = _createPendingCard(utterance, createdAt, pendingId, 'Sending…');
    card.classList.add('placeholder');
    card.dataset.pendingKind = 'placeholder';
    return card;
}

/**
 * Build a per-thread pending card (one per dispatch-ack intent_id). Carries the
 * per-source progress state ('3/5 sources in') and the elapsed-time footer.
 *
 * @param {string} intentId    the intent this thread tracks (result_created key)
 * @param {string} utterance   the originating utterance fragment/text
 * @param {number} createdAt   ms epoch inherited from the placeholder
 * @param {object} [progress]  {completed, total} initial per-source progress
 * @returns {HTMLElement} a .pending-card.thread (data-builtin="pending")
 */
function createPendingThreadCard(intentId, utterance, createdAt, progress) {
    const card = _createPendingCard(utterance, createdAt, intentId, 'Working on it…');
    card.classList.add('thread');
    card.dataset.pendingKind = 'thread';
    if (progress) _setProgress(card, progress);
    return card;
}

/**
 * Split a submit-time placeholder into per-thread pending cards on the dispatch
 * ack. The /dispatch ack response carries ``intent_ids`` — one per routed
 * thread — so this produces one per-thread pending card per intent_id, each
 * inheriting the placeholder's ``createdAt`` (so the 30s aged timer is
 * continuous across the split — the timer started at submit, not at ack) and
 * the originating utterance. (plan, Escalate Strand → Pending/ack card render
 * path: "splits into per-thread pending cards when the dispatch ack arrives".)
 *
 * This is the headlessly-testable core of the split: index.html's dispatch()
 * calls it with the ack's intent_ids and replaces the placeholder DOM node with
 * the returned cards; the Node DOM shim exercises it directly (no browser) to
 * prove the split is one-card-per-thread.
 *
 * @param {string} utterance   the originating utterance text
 * @param {number} createdAt   ms epoch inherited from the placeholder
 * @param {string[]} intentIds the ack's intent_ids (one per routed thread)
 * @returns {HTMLElement[]} one .pending-card.thread per intent_id
 */
function splitPlaceholderToThreads(utterance, createdAt, intentIds) {
    return (intentIds || []).map(function (id) {
        return createPendingThreadCard(id, utterance, createdAt);
    });
}

// Shared skeleton for both placeholder + per-thread pending cards.
function _createPendingCard(utterance, createdAt, pendingId, titleText) {
    const card = el('div', 'builtin-card pending-card');
    card.dataset.builtin = 'pending';
    card.dataset.createdAt = String(createdAt || 0);
    if (pendingId) card.dataset.pendingId = String(pendingId);

    card.appendChild(el('div', 'builtin-header', [
        el('span', 'pending-spinner'),
        el('span', 'builtin-title pending-title', [titleText || 'Pending…'])
    ]));

    if (utterance) {
        card.appendChild(el('p', 'pending-utterance', [utterance]));
    }

    const progress = el('div', 'pending-progress');
    progress.style.display = 'none';
    card.appendChild(progress);

    const elapsed = el('div', 'pending-elapsed', [
        formatElapsed(0) + ' elapsed'
    ]);
    card.appendChild(elapsed);

    // Aged note (hidden until the 30s threshold) — see applyAgedTreatment().
    const agedNote = el('div', 'pending-aged-note');
    agedNote.style.display = 'none';
    agedNote.appendChild(document.createTextNode('Taking longer than expected — the server may be hung. '));
    const retry = el('button', 'pending-retry', ['Retry']);
    agedNote.appendChild(retry);
    card.appendChild(agedNote);

    return card;
}

function _setProgress(card, progress) {
    const node = card.querySelector('.pending-progress');
    if (!node || !progress) return;
    const completed = Math.max(0, parseInt(progress.completed, 10) || 0);
    const total = Math.max(0, parseInt(progress.total, 10) || 0);
    node.textContent = completed + '/' + total + ' sources in';
    node.dataset.completed = String(completed);
    node.dataset.total = String(total);
    node.style.display = total > 0 ? '' : 'none';
}

/**
 * Recompute the elapsed-time footer for a pending card against `now` (ms).
 * Returns the elapsed ms. Pure: no timers, no globals beyond the card's own
 * data-createdAt — so the headless harness can drive it via a mock clock.
 */
function tickPendingElapsed(card, now) {
    const createdAt = parseInt(card.dataset.createdAt, 10) || 0;
    const elapsedMs = Math.max(0, (now || 0) - createdAt);
    const node = card.querySelector('.pending-elapsed');
    if (node) node.textContent = formatElapsed(elapsedMs) + ' elapsed';
    return elapsedMs;
}

/**
 * Apply (or remove) the aged-pending treatment based on elapsed ms vs the 30s
 * threshold. Pure client-side — survives a hung server (no SSE dependency).
 * Returns true if the card is currently flagged aged.
 */
function applyAgedTreatment(card, now) {
    const elapsedMs = tickPendingElapsed(card, now);
    const aged = elapsedMs >= PENDING_AGE_THRESHOLD_MS;
    card.classList.toggle('aged', aged);
    const note = card.querySelector('.pending-aged-note');
    if (note) note.style.display = aged ? '' : 'none';
    return aged;
}

// ---------------------------------------------------------------------------
// (4) Error / clarification family — Degraded-State UX, filled client-side
//     from SSE error events
// ---------------------------------------------------------------------------

// Display metadata per error variant. title + icon + a one-line description
// template. Variants accept both snake_case and kebab-case keys (normalized in
// _errorVariant()). Maps directly to the Degraded-State UX matrix rows.
var ERROR_VARIANTS = {
    router_unavailable: {
        title: 'Router unavailable',
        icon: '🔌',
        detail: 'The LLM proxy (ZAI) was unreachable at the router stage, so this utterance could not be routed.'
    },
    all_sources_failed: {
        title: 'No data available',
        icon: '📭',
        detail: 'Every fetch source failed or timed out, so there is nothing to synthesize.'
    },
    synthesis_failed: {
        title: 'Summary unavailable',
        icon: '⚠️',
        detail: 'The raw data was fetched, but the summary could not be produced.'
    },
    malformed_router_output: {
        title: "Couldn't parse that into intents",
        icon: '🧩',
        detail: 'The router returned output the system could not interpret.'
    },
    no_match: {
        title: 'No matching project',
        icon: '❓',
        detail: 'No registered project matched this request.'
    }
};

function _normalizeVariant(errorType) {
    if (!errorType) return 'no_match';
    const key = String(errorType).trim().replace(/-/g, '_').toLowerCase();
    return ERROR_VARIANTS[key] ? key : 'no_match';
}

/**
 * Build an error/clarification card from an SSE error event payload.
 *
 * @param {object} data  {error_type, utterance, detail, sources, data, intent_id, pending_id}
 * @returns {HTMLElement} a .error-card element (data-builtin="error")
 *
 * Per-source failure lists, the echoed utterance, raw degraded data, and any
 * detail text are all inserted as text nodes (escaping contract).
 */
function createErrorCard(data) {
    data = data || {};
    const variant = _normalizeVariant(data.error_type);
    const meta = ERROR_VARIANTS[variant];

    const card = el('div', 'builtin-card error-card error-' + variant);
    card.dataset.builtin = 'error';
    card.dataset.errorType = variant;
    if (data.intent_id) card.dataset.intentId = String(data.intent_id);
    if (data.pending_id) card.dataset.pendingId = String(data.pending_id);

    card.appendChild(el('div', 'builtin-header', [
        el('span', 'builtin-icon', [meta.icon]),
        el('span', 'builtin-title', [meta.title])
    ]));

    const detail = data.detail || meta.detail;
    card.appendChild(el('p', 'error-detail', [detail]));

    // Echo the utterance so nothing is ever lost (router_unavailable /
    // malformed_router_output rows). Rendered as text, never raw HTML.
    if (data.utterance) {
        card.appendChild(el('div', 'error-utterance-wrap', [
            el('span', 'error-utterance-label', ['You said: ']),
            el('span', 'error-utterance', ['“' + data.utterance + '”'])
        ]));
    }

    // Per-source failure list (all_sources_failed row).
    const sources = data.sources;
    if (Array.isArray(sources) && sources.length) {
        const ul = el('ul', 'error-source-list');
        sources.forEach(function (s) {
            const name = (s && (s.name || s.source)) || 'source';
            const reason = (s && (s.reason || s.error)) || 'failed';
            ul.appendChild(el('li', 'error-source', [
                el('span', 'error-source-name', [name + ': ']),
                el('span', 'error-source-reason', [reason])
            ]));
        });
        card.appendChild(ul);
    }

    // Degraded raw data (synthesis_failed row): fetched data is never discarded.
    if (data.data != null) {
        const raw = typeof data.data === 'string' ? data.data : JSON.stringify(data.data, null, 2);
        card.appendChild(el('div', 'error-raw-label', ['Fetched data']));
        card.appendChild(el('pre', 'error-raw', [raw]));
    }

    // No-match clarification: list the registered projects so the user can pick.
    if (variant === 'no_match' && Array.isArray(data.registered_projects) && data.registered_projects.length) {
        const ul = el('ul', 'error-project-list');
        data.registered_projects.forEach(function (p) {
            const slug = typeof p === 'string' ? p : (p.slug || p.name || 'project');
            ul.appendChild(el('li', 'error-project', [slug]));
        });
        card.appendChild(el('div', 'error-projects-wrap', [
            el('span', 'error-projects-label', ['Registered projects: ']),
            ul
        ]));
    }

    // Recovery action button. Variant-aware label.
    const retryLabel = (variant === 'malformed_router_output' || variant === 'no_match')
        ? 'Edit & resend'
        : 'Retry';
    card.appendChild(el('button', 'error-retry', [retryLabel]));

    return card;
}

// ---------------------------------------------------------------------------
// (5) Stuck/Failed cards — circuit breaker and terminal failure cards
// ---------------------------------------------------------------------------

/**
 * Build a stuck card for a fenced bead.
 *
 * Plan §10 The Async Path: displayed when a bead is fenced due to repeated
 * refusals or timeout. Shows the bead reference, refusal count, and latest reason.
 *
 * @param {object} data  {bead_id, stuck_reason, refusal_count, message, action_hint}
 * @returns {HTMLElement} a .stuck-card element (data-builtin="stuck")
 */
function createStuckCard(data) {
    data = data || {};
    const card = el('div', 'builtin-card stuck-card');
    card.dataset.builtin = 'stuck';
    if (data.bead_id) card.dataset.beadId = String(data.bead_id);

    card.appendChild(el('div', 'builtin-header', [
        el('span', 'builtin-icon', ['🚧']),
        el('span', 'builtin-title', ['Task stuck — needs your input'])
    ]));

    if (data.message) {
        card.appendChild(el('p', 'stuck-message', [data.message]));
    }

    if (data.stuck_reason) {
        card.appendChild(el('div', 'stuck-reason-wrap', [
            el('span', 'stuck-reason-label', ['Reason: ']),
            el('span', 'stuck-reason', [data.stuck_reason])
        ]));
    }

    const meta = el('div', 'stuck-meta');
    if (data.refusal_count != null) {
        meta.appendChild(el('span', 'stuck-refusal-count', [
            'Refusals: ' + String(data.refusal_count)
        ]));
    }
    if (data.bead_id) {
        if (meta.children.length > 0) {
            meta.appendChild(document.createTextNode(' • '));
        }
        meta.appendChild(el('span', 'stuck-bead-id', ['Bead: ' + data.bead_id]));
    }
    if (meta.children.length > 0) {
        card.appendChild(meta);
    }

    if (data.action_hint) {
        card.appendChild(el('p', 'stuck-action-hint', [data.action_hint]));
    }

    // View bead button
    const viewBtn = el('button', 'stuck-view-bead', ['View bead']);
    card.appendChild(viewBtn);

    return card;
}

/**
 * Build a failed card for a terminal failure.
 *
 * Plan §10 The Async Path: displayed when an intent fails non-recoverably
 * (worker crash, invalid input, etc.). Shows failure reason and context.
 *
 * @param {object} data  {bead_id, failure_reason, error_type, message}
 * @returns {HTMLElement} a .failed-card element (data-builtin="failed")
 */
function createFailedCard(data) {
    data = data || {};
    const card = el('div', 'builtin-card failed-card');
    card.dataset.builtin = 'failed';
    if (data.bead_id) card.dataset.beadId = String(data.bead_id);

    card.appendChild(el('div', 'builtin-header', [
        el('span', 'builtin-icon', ['❌']),
        el('span', 'builtin-title', ['Task failed'])
    ]));

    if (data.message) {
        card.appendChild(el('p', 'failed-message', [data.message]));
    }

    if (data.failure_reason) {
        card.appendChild(el('div', 'failed-reason-wrap', [
            el('span', 'failed-reason-label', ['Reason: ']),
            el('span', 'failed-reason', [data.failure_reason])
        ]));
    }

    if (data.error_type) {
        card.appendChild(el('div', 'failed-error-type', [
            'Error type: ' + data.error_type
        ]));
    }

    if (data.bead_id) {
        card.appendChild(el('div', 'failed-bead-id', ['Bead: ' + data.bead_id]));
    }

    // Retry button
    const retryBtn = el('button', 'failed-retry', ['Retry']);
    card.appendChild(retryBtn);

    return card;
}

// ---------------------------------------------------------------------------
// (1) Generic fallback card — key/value grid over result.data + summary
// ---------------------------------------------------------------------------

/**
 * Build the generic fallback card for a result that matched no component
 * (plan, Component Library → "Built-in generic fallback card"). Key/value grid
 * over result.data plus the summary line — every value escaped per the
 * rendering escaping contract.
 *
 * @param {object} result  {summary, data, urgency}
 * @returns {HTMLElement} a .fallback-card element (data-builtin="fallback")
 */
function createFallbackCard(result) {
    result = result || {};
    const card = el('div', 'builtin-card fallback-card');
    card.dataset.builtin = 'fallback';

    card.appendChild(el('div', 'builtin-header', [
        el('span', 'builtin-icon', ['🗒️']),
        el('span', 'builtin-title', ['Result'])
    ]));

    if (result.summary) {
        card.appendChild(el('p', 'fallback-summary', [result.summary]));
    }

    const data = result.data;
    const rows = _fallbackRows(data);
    if (rows.length) {
        const grid = el('div', 'fallback-grid');
        rows.forEach(function (r) {
            grid.appendChild(el('div', 'fallback-key', [r[0]]));
            grid.appendChild(el('div', 'fallback-val', [r[1]]));
        });
        card.appendChild(grid);
    }

    if (result.urgency) {
        card.appendChild(el('span', 'urgency-badge ' + result.urgency, [result.urgency]));
    }

    return card;
}

// Flatten result.data into [key, value] string pairs for the fallback grid.
function _fallbackRows(data) {
    if (data == null) return [];
    let obj = data;
    if (typeof data === 'string') {
        try { obj = JSON.parse(data); } catch (e) { return [['value', data]]; }
    }
    if (Array.isArray(obj)) {
        return obj.slice(0, 50).map(function (v, i) { return [String(i), _stringify(v)]; });
    }
    if (typeof obj === 'object') {
        return Object.keys(obj).slice(0, 50).map(function (k) { return [k, _stringify(obj[k])]; });
    }
    return [['value', String(obj)]];
}

function _stringify(v) {
    if (v == null) return '';
    if (typeof v === 'string') return v;
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    try { return JSON.stringify(v); } catch (e) { return String(v); }
}

// Export shim: browser globals are already in place (these are top-level
// function declarations). In Node, expose them for the headless DOM tests.
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        createTopicCard: createTopicCard,
        escapeHtml: escapeHtml,
        formatStaleness: formatStaleness,
        getStalenessLevel: getStalenessLevel,
        // Built-in card families + helpers
        el: el,
        formatElapsed: formatElapsed,
        createWelcomeCard: createWelcomeCard,
        buildContainerChildren: buildContainerChildren,
        createPendingPlaceholderCard: createPendingPlaceholderCard,
        createPendingThreadCard: createPendingThreadCard,
        splitPlaceholderToThreads: splitPlaceholderToThreads,
        tickPendingElapsed: tickPendingElapsed,
        applyAgedTreatment: applyAgedTreatment,
        setPendingProgress: _setProgress,
        createErrorCard: createErrorCard,
        createFallbackCard: createFallbackCard,
        createStuckCard: createStuckCard,
        createFailedCard: createFailedCard,
        normalizeErrorVariant: _normalizeVariant,
        deriveExamples: _deriveExamples,
        PENDING_AGE_THRESHOLD_MS: PENDING_AGE_THRESHOLD_MS,
        _setProgress: _setProgress,  // Also export internal helper
        _normalizeVariant: _normalizeVariant,  // Also export for testing
    };
}

// Also expose to inline script in browser (buildContainerChildren is used by loadTopics)
if (typeof window !== 'undefined') {
    window.buildContainerChildren = buildContainerChildren;
    window._setProgress = _setProgress;
    window.el = el;  // DOM helper for pending cards
    window.createErrorCard = createErrorCard;  // Error card renderer for SSE error events
    window.createStuckCard = createStuckCard;  // Stuck card renderer for task_stuck events
    window.createFailedCard = createFailedCard;  // Failed card renderer for task_failed events
}
