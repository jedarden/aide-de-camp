/*
 * ADC Canvas — rendering helpers.
 *
 * Pure functions that turn a /api/v1/sessions/{id}/topics card dict into a DOM
 * topic-card element. They are kept in this separate, loadable module (rather
 * than inline in index.html) so the render contract can be verified headlessly
 * — tests/e2e/canvas_dom_runner.js loads this exact file under a minimal DOM
 * shim and asserts the rendered HTML, with no browser or network required.
 *
 * In the browser, index.html loads this via <script src="/canvas.js"> before
 * the inline app script, so these declarations are globals just like they were
 * when they lived inline. In Node, the trailing export shim exposes them via
 * module.exports for the DOM test.
 */

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
                <span class="topic-type ${typeClass}">${topic.type || 'adhoc'}</span>
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
                    <span class="urgency-badge ${urgencyClass}">${urgencyClass}</span>
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

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Export shim: browser globals are already in place (these are top-level
// function declarations). In Node, expose them for the headless DOM test.
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        createTopicCard: createTopicCard,
        escapeHtml: escapeHtml,
        formatStaleness: formatStaleness,
        getStalenessLevel: getStalenessLevel,
    };
}
