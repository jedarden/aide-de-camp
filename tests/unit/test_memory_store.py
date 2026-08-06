"""
MemoryStore load initialization and in-memory add_fact tests (bead adc-6cfeq).

Tests basic MemoryStore initialization and in-memory operations:
- load() initializes with empty facts list
- load() initializes with provided session_id
- add_fact() appends fact to in-memory facts list
- add_fact() increments facts counter
- Multiple add_fact() calls accumulate correctly
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.memory.store import FactCategory, MemoryStore


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def temp_memory_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for memory files."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


@pytest.fixture
def session_id() -> str:
    """Test session ID."""
    return "test-session-123"


@pytest.fixture
def store(temp_memory_dir: Path, session_id: str) -> MemoryStore:
    """Create a MemoryStore instance for testing."""
    logger = MagicMock()
    return MemoryStore(
        session_id=session_id,
        memory_dir=str(temp_memory_dir),
        logger=logger
    )


# --- load() initialization tests -----------------------------------------------


def test_load_initializes_with_empty_facts_list(store: MemoryStore) -> None:
    """Test load() initializes with empty facts list when file doesn't exist."""
    store.load()

    assert store._facts == []
    assert len(store._facts) == 0
    assert isinstance(store._facts, list)


def test_load_initializes_with_provided_session_id(store: MemoryStore) -> None:
    """Test load() initializes with the provided session_id."""
    test_session_id = "my-custom-session-456"
    custom_store = MemoryStore(
        session_id=test_session_id,
        memory_dir=str(store.memory_dir),
        logger=MagicMock()
    )
    custom_store.load()

    assert custom_store._data["session_id"] == test_session_id
    assert custom_store.session_id == test_session_id


def test_load_initializes_empty_facts_dict(store: MemoryStore) -> None:
    """Test load() starts with empty facts dict in _data."""
    store.load()

    assert "facts" in store._data
    assert store._data["facts"] == []
    assert store._data["session_id"] == store.session_id


# --- add_fact() in-memory tests ----------------------------------------------


def test_add_fact_appends_to_in_memory_facts_list(store: MemoryStore) -> None:
    """Test add_fact() appends fact to in-memory facts list."""
    store.load()

    initial_length = len(store._facts)
    result = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)

    assert result is True
    assert len(store._facts) == initial_length + 1
    assert store._facts[-1].text == "User prefers dark mode"
    assert store._facts[-1].category == FactCategory.PREFERENCE


def test_add_fact_increments_facts_counter(store: MemoryStore) -> None:
    """Test add_fact() increments facts counter (list length)."""
    store.load()

    # Start with empty facts
    assert len(store._facts) == 0

    # Add first fact
    store.add_fact("First fact", FactCategory.CONTEXT, 0.8)
    assert len(store._facts) == 1

    # Add second fact
    store.add_fact("Second fact", FactCategory.PERSONAL, 0.9)
    assert len(store._facts) == 2

    # Add third fact
    store.add_fact("Third fact", FactCategory.PREFERENCE, 0.85)
    assert len(store._facts) == 3


def test_multiple_add_fact_calls_accumulate_correctly(store: MemoryStore) -> None:
    """Test multiple add_fact() calls accumulate correctly in memory."""
    store.load()

    # Add multiple facts
    facts_to_add = [
        ("User prefers dark mode", FactCategory.PREFERENCE, 0.9),
        ("User lives in Berlin", FactCategory.PERSONAL, 0.95),
        ("User works on Python projects", FactCategory.CONTEXT, 0.85),
        ("User likes Kubernetes", FactCategory.PREFERENCE, 0.88),
    ]

    for text, category, confidence in facts_to_add:
        result = store.add_fact(text, category, confidence)
        assert result is True, f"Failed to add fact: {text}"

    # Verify all facts accumulated
    assert len(store._facts) == len(facts_to_add)

    # Verify each fact is stored correctly
    stored_texts = [f.text for f in store._facts]
    stored_categories = [f.category for f in store._facts]
    stored_confidences = [f.confidence for f in store._facts]

    expected_texts = [text for text, _, _ in facts_to_add]
    expected_categories = [category for _, category, _ in facts_to_add]
    expected_confidences = [confidence for _, _, confidence in facts_to_add]

    assert stored_texts == expected_texts
    assert stored_categories == expected_categories
    assert stored_confidences == expected_confidences


def test_add_fact_returns_false_for_duplicate_without_changing_counter(store: MemoryStore) -> None:
    """Test that duplicate add_fact() returns False and doesn't increment counter."""
    store.load()

    # Add first fact
    result1 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result1 is True
    assert len(store._facts) == 1

    # Try to add duplicate
    result2 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result2 is False
    assert len(store._facts) == 1, "Counter should not increment for duplicate"


def test_add_fact_on_empty_store(store: MemoryStore) -> None:
    """Test add_fact() works correctly on newly loaded empty store."""
    store.load()

    # Verify store is empty
    assert len(store._facts) == 0

    # Add first fact
    result = store.add_fact("First fact after load", FactCategory.CONTEXT, 0.75)

    assert result is True
    assert len(store._facts) == 1
    assert store._facts[0].text == "First fact after load"


def test_facts_list_order_preserved_on_multiple_adds(store: MemoryStore) -> None:
    """Test that facts maintain insertion order with multiple add_fact() calls."""
    store.load()

    # Add facts in specific order
    store.add_fact("First", FactCategory.CONTEXT, 0.8)
    store.add_fact("Second", FactCategory.PERSONAL, 0.9)
    store.add_fact("Third", FactCategory.PREFERENCE, 0.85)

    # Verify order is preserved
    assert len(store._facts) == 3
    assert store._facts[0].text == "First"
    assert store._facts[1].text == "Second"
    assert store._facts[2].text == "Third"
