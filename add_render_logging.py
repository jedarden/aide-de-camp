#!/usr/bin/env python3
"""
Add comprehensive logging to trace component rendering paths.

This script adds logging statements to key files to trace:
1. When hot_path.render() is invoked
2. Whether components match or fallback is used
3. What result_types are being generated
4. Whether card_cache is being written
"""

import re
from pathlib import Path

# File paths
HOT_PATH_PY = Path("/home/coding/aide-de-camp/src/render/hot_path.py")
INTENT_ROUTER_PY = Path("/home/coding/aide-de-camp/src/intent/router.py")


def add_hot_path_logging():
    """Add detailed logging to hot_path.py render() method."""
    content = HOT_PATH_PY.read_text()

    # Add logging at the start of render() method
    render_start_log = """        logger.info(
            "hot-path render() called: result_id=%s, result_type=%r, threshold=%.2f",
            result_id,
            result_type,
            self.match_threshold,
        )

"""

    # Find the render() method and add logging after the bucket assignment
    pattern = r'(        bucket = layout_bucket or self\.layout_bucket\n)'
    replacement = r'\1' + render_start_log
    content = re.sub(pattern, replacement, content, count=1)

    # Add logging when component is None (fallback case)
    fallback_log = """            logger.warning(
                "hot-path fallback: NO COMPONENT MATCHED for result_type=%r (threshold %.2f), result_id=%s",
                result_type,
                self.match_threshold,
                result_id,
            )

"""

    pattern = r'(        if component is None:\n            logger.debug\()'
    replacement = r'\1' + fallback_log
    # This replacement is more complex, let's use a different approach

    # Add logging when component IS found
    component_found_log = """        logger.info(
            "hot-path COMPONENT MATCH: result_id=%s, result_type=%r -> component_id=%s v%s",
            result_id,
            result_type,
            component.id,
            component.version,
        )

        rendered_html = fill_template(component.html_template, result_data)

"""
    pattern = r'(        rendered_html = fill_template\(component\.html_template, result_data\)\n)'
    replacement = component_found_log
    content = re.sub(pattern, replacement, content, count=1)

    # Add logging for cache_card call
    cache_log = """        logger.info(
            "hot-path caching card: result_id=%s, component_id=%s, version=%s, bucket=%s",
            result_id,
            component.id,
            component.version,
            bucket,
        )
        self.library.cache_card(
"""

    pattern = r'(        self\.library\.cache_card\()'
    replacement = cache_log
    content = re.sub(pattern, replacement, content, count=1)

    HOT_PATH_PY.write_text(content)
    print("✓ Added logging to hot_path.py")


def add_intent_router_logging():
    """Add logging to intent router to trace render calls."""
    content = INTENT_ROUTER_PY.read_text()

    # Add logging before hot-path render call
    render_call_log = """            logger.info(
                "intent-router calling hot-path renderer: result_type=%r, intent_id=%s",
                result_type,
                result_id,
            )
            renderer = get_renderer()
            render_outcome = renderer.render(

"""

    pattern = r'(            # Render card via hot-path selector \(deterministic, no LLM\)\n            renderer = get_renderer\(\)\n            render_outcome = renderer\.render\()'
    replacement = render_call_log + r'\2'
    content = re.sub(pattern, replacement, content, count=1)

    # Add logging after render outcome
    outcome_log = """            logger.info(
                "intent-router render outcome: result_id=%s, card_fallback=%s, component_id=%s, has_html=%s",
                result_id,
                render_outcome.card_fallback,
                render_outcome.component_id,
                render_outcome.rendered_html is not None,
            )

            # Update result's card_fallback flag
"""
    pattern = r'(            # Update result\'s card_fallback flag so client knows which path to take\n)'
    replacement = outcome_log + r'\1'
    content = re.sub(pattern, replacement, content, count=1)

    INTENT_ROUTER_PY.write_text(content)
    print("✓ Added logging to intent/router.py")


def add_canvas_logging():
    """Add logging to canvas.js createTopicCard() to see which path is taken."""
    canvas_js = Path("/home/coding/aide-de-camp/src/canvas/canvas.js")
    content = canvas_js.read_text()

    # Add console.log at the start of createTopicCard
    start_log = '''function createTopicCard(cardData) {
    const topic = cardData.topic;
    const staleness = cardData.staleness;
    const latestResult = cardData.latest_result;
    const cardId = cardData.card_id;  // Unique (topic, result_type) identifier

    // Log which render path is being taken
    if (latestResult) {
        console.log('[canvas-render] result_id=' + (cardData.result_id || 'unknown') +
                    ', result_type=' + (latestResult.result_type || 'unknown') +
                    ', card_fallback=' + latestResult.card_fallback +
                    ', has_rendered_html=' + !!latestResult.rendered_html);
    }

'''

    pattern = r'(function createTopicCard\(cardData\) \{\n    const topic = cardData\.topic;\n    const staleness = cardData\.staleness;\n    const latestResult = cardData\.latest_result;\n    const cardId = cardData\.card_id;  // Unique \(topic, result_type\) identifier\n\n)'
    replacement = start_log
    content = re.sub(pattern, replacement, content, count=1)

    # Add console.log for fallback path
    fallback_console = '''    if (latestResult && latestResult.card_fallback) {
        console.log('[canvas-render] USING FALLBACK CARD: result_type=' + (latestResult.result_type || 'unknown'));
        const fallbackCard = createFallbackCard(latestResult);
'''

    pattern = r'(    if \(latestResult && latestResult\.card_fallback\) \{\n        const fallbackCard = createFallbackCard\(latestResult\);'
    replacement = fallback_console
    content = re.sub(pattern, replacement, content, count=1)

    # Add console.log for component path
    component_console = '''    if (latestResult && latestResult.rendered_html) {
        console.log('[canvas-render] USING COMPONENT CARD: component_id=' + (latestResult.component_id || 'unknown') +
                    ', result_type=' + (latestResult.result_type || 'unknown'));
        const card = document.createElement('div');
'''

    pattern = r'(    if \(latestResult && latestResult\.rendered_html\) \{\n        const card = document\.createElement\(\'div\'\);'
    replacement = component_console
    content = re.sub(pattern, replacement, content, count=1)

    # Add console.log for generic path
    generic_console = '''    console.log('[canvas-render] USING GENERIC TOPIC CARD (no component, no fallback): result_type=' +
                (latestResult?.result_type || 'unknown'));

    const card = document.createElement('div');
'''
    # Insert this before the generic card creation (after the component check)
    pattern = r'(    const card = document\.createElement\(\'div\'\);\n    card\.className = \'topic-card\';\n    card\.dataset\.topicId = topic\.id;)'
    replacement = generic_console + r'\1'
    content = re.sub(pattern, replacement, content, count=1)

    canvas_js.write_text(content)
    print("✓ Added logging to canvas.js")


if __name__ == "__main__":
    print("Adding comprehensive rendering path logging...")
    print()
    add_hot_path_logging()
    add_intent_router_logging()
    add_canvas_logging()
    print()
    print("Logging added! Restart the aide-de-camp service to enable logging:")
    print("  systemctl --user restart aide-de-camp")
    print()
    print("Then monitor logs:")
    print("  journalctl --user -u aide-de-camp -f")
    print()
    print("In the browser, check console logs for canvas-render messages.")
