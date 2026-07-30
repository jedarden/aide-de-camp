# Card Dismissal Test Infrastructure

This document describes the test infrastructure and helpers available for card dismissal testing in aide-de-camp.

## Overview

The card dismissal test infrastructure provides a comprehensive set of helpers and fixtures for testing card dismissal functionality. This includes:

- Creating test sessions with isolated stores
- Creating stuck and failed cards
- Verifying card presence in the canvas
- Triggering dismissal button clicks
- Managing SSE broadcasts

## Quick Start

```python
from tests.card_dismissal_helpers import (
    create_test_session_with_topic,
    create_stuck_card,
    verify_card_present,
    get_dismissal_selector,
)

# Create a test session with topic
store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

# Create a stuck card
card_data = await create_stuck_card(
    store=store,
    session_id=session_id,
    topic_id=topic_id,
    bead_id="adc-test-stuck"
)

# Verify card is present
cards = await store.get_active_topics(session_id)
assert verify_card_present(cards, "stuck", "adc-test-stuck")

# Get dismissal selector
selector = get_dismissal_selector(bead_id="adc-test-stuck", card_type="stuck")
```

## Available Helpers

### Session Creation

#### `create_test_session(store=None, tmp_path=None)`

Create a test session with an isolated store.

**Parameters:**
- `store` (Optional[SessionStore]): Existing SessionStore. If None, creates a new one.
- `tmp_path` (Optional[Path]): Temp path for store. Required if store is None.

**Returns:**
- `tuple[SessionStore, str]`: Store and session_id

**Example:**
```python
store, session_id = await create_test_session(tmp_path=tmp_path)
```

#### `create_test_session_with_topic(store=None, tmp_path=None, label="Test Topic", topic_type="project")`

Create a test session with a topic.

**Parameters:**
- `store` (Optional[SessionStore]): Existing SessionStore
- `tmp_path` (Optional[Path]): Temp path for store
- `label` (str): Topic label
- `topic_type` (str): Topic type (project, research, personal, etc.)

**Returns:**
- `tuple[SessionStore, str, str]`: Store, session_id, and topic_id

**Example:**
```python
store, session_id, topic_id = await create_test_session_with_topic(
    tmp_path=tmp_path,
    label="My Test Topic",
    topic_type="research"
)
```

### Card Creation

#### `create_stuck_card(store, session_id, topic_id=None, bead_id="adc-stuck-test", stuck_reason="Test stuck reason", refusal_count=3, message="Task stuck — needs input")`

Create a stuck card in the session store.

**Parameters:**
- `store` (SessionStore): SessionStore instance
- `session_id` (str): Session ID
- `topic_id` (Optional[str]): Topic ID. If None, creates one.
- `bead_id` (str): Bead reference ID
- `stuck_reason` (str): Reason for being stuck
- `refusal_count` (int): Number of refusals
- `message` (str): Card message

**Returns:**
- `dict[str, Any]`: Card data including bead_id, stuck_reason, etc.

**Example:**
```python
card_data = await create_stuck_card(
    store=store,
    session_id=session_id,
    topic_id=topic_id,
    bead_id="adc-stuck-1",
    stuck_reason="Needs clarification",
    refusal_count=3,
    message="Task is stuck"
)
```

#### `create_failed_card(store, session_id, topic_id=None, bead_id="adc-failed-test", failure_reason="Test failure reason", error_type="test_error", message="Task failed")`

Create a failed card in the session store.

**Parameters:**
- `store` (SessionStore): SessionStore instance
- `session_id` (str): Session ID
- `topic_id` (Optional[str]): Topic ID. If None, creates one.
- `bead_id` (str): Bead reference ID
- `failure_reason` (str): Reason for failure
- `error_type` (str): Type of error
- `message` (str): Card message

**Returns:**
- `dict[str, Any]`: Card data including bead_id, failure_reason, etc.

**Example:**
```python
card_data = await create_failed_card(
    store=store,
    session_id=session_id,
    topic_id=topic_id,
    bead_id="adc-failed-1",
    failure_reason="Worker crashed",
    error_type="worker_crash",
    message="Task failed"
)
```

### Card Verification

#### `verify_card_present(cards, card_type, bead_id=None)`

Verify that a card is present in the cards list.

**Parameters:**
- `cards` (list[dict[str, Any]]): List of card dicts from GET /api/v1/sessions/{id}/topics
- `card_type` (str): Type of card ('stuck' or 'failed')
- `bead_id` (Optional[str]): Optional bead_id to match

**Returns:**
- `bool`: True if card is present, False otherwise

**Example:**
```python
cards = await store.get_active_topics(session_id)
assert verify_card_present(cards, 'stuck', 'adc-stuck-1')
```

#### `count_cards_by_type(cards, card_type)`

Count cards of a specific type.

**Parameters:**
- `cards` (list[dict[str, Any]]): List of card dicts
- `card_type` (str): Type to count ('stuck' or 'failed')

**Returns:**
- `int`: Number of cards of the specified type

**Example:**
```python
stuck_count = count_cards_by_type(cards, 'stuck')
failed_count = count_cards_by_type(cards, 'failed')
```

#### `find_card_by_bead_id(cards, bead_id)`

Find a card by its bead_id.

**Parameters:**
- `cards` (list[dict[str, Any]]): List of card dicts
- `bead_id` (str): Bead ID to search for

**Returns:**
- `dict[str, Any] | None`: Card dict if found, None otherwise

**Example:**
```python
card = find_card_by_bead_id(cards, 'adc-stuck-1')
if card:
    print(f"Found card: {card['builtin_data']['type']}")
```

### Dismissal Trigger

#### `get_dismissal_selector(bead_id=None, card_type="stuck")`

Get CSS selector for dismissal button.

**Parameters:**
- `bead_id` (Optional[str]): Optional bead_id for specific card
- `card_type` (str): Type of card ('stuck' or 'failed')

**Returns:**
- `str`: CSS selector string

**Examples:**
```python
# Select all stuck card dismissal buttons
selector = get_dismissal_selector(card_type='stuck')

# Select specific card's dismissal button
selector = get_dismissal_selector(bead_id='adc-stuck-1', card_type='stuck')
```

#### `trigger_dismissal(page, bead_id=None, card_type="stuck", button_selector=None)`

Trigger a dismissal button click in the browser.

**Parameters:**
- `page`: Playwright Page instance
- `bead_id` (Optional[str]): Optional bead_id for specific card
- `card_type` (str): Type of card ('stuck' or 'failed')
- `button_selector` (Optional[str]): Optional custom button selector

**Example:**
```python
await trigger_dismissal(page, bead_id='adc-stuck-1', card_type='stuck')
```

#### `dismiss_and_verify(page, store, session_id, bead_id, card_type="stuck")`

Dismiss a card and verify it's removed from the store.

**Parameters:**
- `page`: Playwright Page instance
- `store` (SessionStore): SessionStore instance
- `session_id` (str): Session ID
- `bead_id` (str): Bead ID to dismiss
- `card_type` (str): Type of card ('stuck' or 'failed')

**Example:**
```python
await dismiss_and_verify(page, store, session_id, 'adc-stuck-1', 'stuck')
```

### SSE Broadcast

#### `broadcast_stuck_card(broadcaster, card_data, session_id)`

Broadcast a stuck card via SSE.

**Parameters:**
- `broadcaster` (SSEBroadcaster): SSEBroadcaster instance
- `card_data` (dict[str, Any]): Card data from create_stuck_card()
- `session_id` (str): Session ID

**Example:**
```python
card_data = await create_stuck_card(store, session_id)
await broadcast_stuck_card(broadcaster, card_data, session_id)
```

#### `broadcast_failed_card(broadcaster, card_data, session_id)`

Broadcast a failed card via SSE.

**Parameters:**
- `broadcaster` (SSEBroadcaster): SSEBroadcaster instance
- `card_data` (dict[str, Any]): Card data from create_failed_card()
- `session_id` (str): Session ID

**Example:**
```python
card_data = await create_failed_card(store, session_id)
await broadcast_failed_card(broadcaster, card_data, session_id)
```

## Fixtures

The following pytest fixtures are available:

### `test_store(tmp_path)`

Create an isolated SessionStore for testing.

**Yields:**
- `SessionStore`: Isolated store instance

### `test_broadcaster()`

Create a fresh SSE broadcaster for testing.

**Yields:**
- `SSEBroadcaster`: Fresh broadcaster instance

### `test_session_with_store(test_store)`

Create a test session with store.

**Yields:**
- `tuple[SessionStore, str]`: Store and session_id

### `test_session_with_topic(test_store)`

Create a test session with a topic.

**Yields:**
- `tuple[SessionStore, str, str]`: Store, session_id, and topic_id

## Mock Helpers

### `create_mock_router()`

Create a mock surface router for testing.

**Returns:**
- `AsyncMock`: Configured mock router

**Example:**
```python
router = create_mock_router()
decision = await router.route_result()
```

## Complete Example

Here's a complete example of using the helpers in a test:

```python
import pytest
from tests.card_dismissal_helpers import (
    create_test_session_with_topic,
    create_stuck_card,
    create_failed_card,
    verify_card_present,
    count_cards_by_type,
    get_dismissal_selector,
)

class TestCardDismissal:
    @pytest.mark.asyncio
    async def test_stuck_card_dismissal(self, tmp_path):
        # Create session with topic
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path,
            label="Dismissal Test Topic"
        )

        # Create stuck card
        card_data = await create_stuck_card(
            store=store,
            session_id=session_id,
            topic_id=topic_id,
            bead_id="adc-dismissal-test"
        )

        # Get cards and verify
        cards = await store.get_active_topics(session_id)
        assert verify_card_present(cards, "stuck", "adc-dismissal-test")

        # Get selector for dismissal
        selector = get_dismissal_selector(
            bead_id="adc-dismissal-test",
            card_type="stuck"
        )
        assert 'adc-dismissal-test' in selector

        await store.close()
```

## Testing Best Practices

1. **Use isolated stores**: Always use the `tmp_path` fixture to create isolated stores for each test
2. **Clean up resources**: Use store cleanup in fixtures or explicit close calls
3. **Test both card types**: Test both stuck and failed cards for comprehensive coverage
4. **Verify state changes**: Always verify card presence/absence before and after operations
5. **Use meaningful bead_ids**: Use descriptive bead_id values for easier debugging

## Related Files

- `tests/card_dismissal_helpers.py` - Helper functions and fixtures
- `tests/test_card_dismissal_helpers.py` - Unit tests for the helpers
- `tests/test_card_dismissal_persistence_selectors.py` - Persistence and selector tests
- `tests/test_canvas_card_dismissal.py` - Integration tests for card dismissal

## Bead References

This infrastructure was created for bead `adc-3xgfs` to support card dismissal testing across multiple related beads.
