"""
MemoryStore unit tests (bead adc-90mjr).

Tests core persistence operations for MemoryStore:
- load() - initialize store
- add_fact() - add test facts
- save() - persist to disk
- Fact persistence across load() cycles
- _is_duplicate() deduplication logic

These tests are hermetic and use temporary directories to avoid touching
production data/data/memory/.
"""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.memory.store import Fact, FactCategory, MemoryStore

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


# --- basic load/save tests ---------------------------------------------------


def test_load_initializes_empty_store(store: MemoryStore) -> None:
    """Test load() initializes empty store when file doesn't exist."""
    store.load()

    assert store._data == {"facts": [], "session_id": store.session_id}
    assert store._facts == []


def test_load_creates_file_path_correctly(store: MemoryStore) -> None:
    """Test that file path is created with correct hash format."""
    expected_hash = hashlib.sha256(store.session_id.encode()).hexdigest()[:16]
    expected_filename = f"session_{expected_hash}.json"

    assert store.file_path.name == expected_filename
    assert str(store.file_path).endswith(expected_filename)


def test_save_creates_json_file(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test save() creates a JSON file at the expected path."""
    store.load()

    # Add a fact
    store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)

    # Verify file was created
    assert store.file_path.exists(), "JSON file should be created"
    assert store.file_path.is_file(), "Should be a file, not directory"

    # Verify it's valid JSON
    with open(store.file_path, "r") as f:
        data = json.load(f)

    assert "facts" in data
    assert data["session_id"] == store.session_id


def test_save_persists_fact_to_disk(store: MemoryStore) -> None:
    """Test save() persists fact data correctly to disk."""
    store.load()
    store.add_fact("User lives in Berlin", FactCategory.PERSONAL, 0.95)

    # Read the file directly
    with open(store.file_path, "r") as f:
        data = json.load(f)

    assert len(data["facts"]) == 1
    fact = data["facts"][0]
    assert fact["text"] == "User lives in Berlin"
    assert fact["category"] == "personal"
    assert fact["confidence"] == 0.95
    assert "created_at" in fact
    assert "last_referenced" in fact


# --- persistence across load cycles -------------------------------------------


def test_fact_survives_load_cycle(store: MemoryStore) -> None:
    """Test that facts persist across a fresh MemoryStore.load()."""
    # Create a fact and save
    store.load()
    store.add_fact("User works on Python projects", FactCategory.PERSONAL, 0.85)

    # Create a new store instance and load
    logger = MagicMock()
    new_store = MemoryStore(
        session_id=store.session_id,
        memory_dir=str(store.memory_dir),
        logger=logger
    )
    new_store.load()

    # Verify the fact survived
    assert len(new_store._facts) == 1
    fact = new_store._facts[0]
    assert fact.text == "User works on Python projects"
    assert fact.category == FactCategory.PERSONAL
    assert fact.confidence == 0.85


def test_multiple_facts_survive_load_cycle(store: MemoryStore) -> None:
    """Test that multiple facts persist across load cycles."""
    store.load()

    # Add multiple facts
    store.add_fact("Prefers dark mode", FactCategory.PREFERENCE, 0.9)
    store.add_fact("Lives in Berlin", FactCategory.PERSONAL, 0.95)
    store.add_fact("Working on Kubernetes cluster", FactCategory.CONTEXT, 0.8)

    # Load in a new store instance
    logger = MagicMock()
    new_store = MemoryStore(
        session_id=store.session_id,
        memory_dir=str(store.memory_dir),
        logger=logger
    )
    new_store.load()

    # Verify all facts survived
    assert len(new_store._facts) == 3
    texts = [f.text for f in new_store._facts]
    assert "Prefers dark mode" in texts
    assert "Lives in Berlin" in texts
    assert "Working on Kubernetes cluster" in texts


def test_load_with_corrupted_json_falls_back_safely(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() handles corrupted JSON gracefully."""
    # Create a file with invalid JSON
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        f.write("{ invalid json content")

    # Should not crash, should fall back to empty state
    store.load()

    assert store._data == {"facts": [], "session_id": store.session_id}
    assert store._facts == []


# --- duplicate detection tests -----------------------------------------------


def test_duplicate_exact_match(store: MemoryStore) -> None:
    """Test _is_duplicate() detects exact matches."""
    store.load()

    # Add first fact
    result1 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result1 is True, "First fact should be added"

    # Try to add identical fact
    result2 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result2 is False, "Duplicate should not be added"

    # Verify only one fact exists
    assert len(store._facts) == 1


def test_duplicate_case_insensitive(store: MemoryStore) -> None:
    """Test _is_duplicate() is case-insensitive."""
    store.load()

    result1 = store.add_fact("User Prefers Dark Mode", FactCategory.PREFERENCE, 0.9)
    assert result1 is True

    # Same text, different case
    result2 = store.add_fact("user prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result2 is False, "Case-insensitive duplicate should not be added"

    assert len(store._facts) == 1


def test_duplicate_whitespace_normalized(store: MemoryStore) -> None:
    """Test _is_duplicate() normalizes whitespace."""
    store.load()

    result1 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result1 is True

    # Same text with different whitespace
    result2 = store.add_fact("  User   prefers   dark  mode  ", FactCategory.PREFERENCE, 0.9)
    assert result2 is False, "Whitespace-normalized duplicate should not be added"

    assert len(store._facts) == 1


def test_duplicate_long_text_prefix_match(store: MemoryStore) -> None:
    """Test _is_duplicate() detects prefix matches for long texts."""
    store.load()

    # Add long fact
    long_fact = "User has been working on distributed systems for over 10 years and prefers microservices architecture over monolithic applications"
    result1 = store.add_fact(long_fact, FactCategory.CONTEXT, 0.8)
    assert result1 is True

    # Try to add a fact that is a prefix
    prefix_fact = "User has been working on distributed systems for over 10 years"
    result2 = store.add_fact(prefix_fact, FactCategory.CONTEXT, 0.8)
    assert result2 is False, "Prefix duplicate should not be added"

    assert len(store._facts) == 1


def test_duplicate_different_category_allowed(store: MemoryStore) -> None:
    """Test that same text with different category is allowed."""
    store.load()

    result1 = store.add_fact("User loves Kubernetes", FactCategory.PREFERENCE, 0.9)
    assert result1 is True

    # Same text, different category - should be allowed
    result2 = store.add_fact("User loves Kubernetes", FactCategory.CONTEXT, 0.9)
    assert result2 is True, "Different category should be allowed"

    assert len(store._facts) == 2


def test_duplicate_short_text_no_prefix_match(store: MemoryStore) -> None:
    """Test that short texts don't trigger prefix matching."""
    store.load()

    # Add short fact (< 20 chars)
    result1 = store.add_fact("Likes cats", FactCategory.PREFERENCE, 0.9)
    assert result1 is True

    # Similar but not identical - should be allowed
    result2 = store.add_fact("Likes dogs", FactCategory.PREFERENCE, 0.9)
    assert result2 is True, "Short different text should be allowed"

    assert len(store._facts) == 2


def test_no_duplicate_for_different_text(store: MemoryStore) -> None:
    """Test that genuinely different facts are not considered duplicates."""
    store.load()

    result1 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    result2 = store.add_fact("User lives in Berlin", FactCategory.PERSONAL, 0.95)
    result3 = store.add_fact("User works on Python projects", FactCategory.CONTEXT, 0.85)

    assert result1 is True
    assert result2 is True
    assert result3 is True

    assert len(store._facts) == 3


# --- fact limit and trimming tests ------------------------------------------


def test_add_fact_trims_oldest_when_at_limit(store: MemoryStore) -> None:
    """Test that oldest fact is trimmed when MAX_FACTS is reached."""
    store.load()

    # Add MAX_FACTS + 1 facts
    for i in range(101):  # MAX_FACTS is 100
        store.add_fact(f"Fact number {i}", FactCategory.CONTEXT, 0.7)

    # Should have exactly 100 facts
    assert len(store._facts) == 100

    # Oldest fact should be removed
    texts = [f.text for f in store._facts]
    assert "Fact number 0" not in texts, "Oldest fact should be trimmed"
    assert "Fact number 1" in texts, "Second fact should still exist"
    assert "Fact number 100" in texts, "Newest fact should exist"


# --- get_facts tests ---------------------------------------------------------


def test_get_facts_returns_copy(store: MemoryStore) -> None:
    """Test get_facts() returns a copy, not the internal list."""
    store.load()
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    facts1 = store.get_facts()
    facts2 = store.get_facts()

    # Should be equal but not the same object
    assert facts1 == facts2
    assert facts1 is not facts2


def test_get_facts_updates_timestamps(store: MemoryStore) -> None:
    """Test get_facts() updates last_referenced timestamps."""
    store.load()
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    old_timestamp = store._facts[0].last_referenced

    # Call get_facts
    import time
    time.sleep(0.01)  # Small delay to ensure timestamp difference
    facts = store.get_facts()

    # Timestamp should be updated
    new_timestamp = store._facts[0].last_referenced
    assert new_timestamp != old_timestamp


# --- category serialization tests --------------------------------------------


def test_fact_category_serialization_roundtrip(store: MemoryStore) -> None:
    """Test FactCategory serialization and deserialization."""
    store.load()

    # Add one of each category
    store.add_fact("Prefers dark mode", FactCategory.PREFERENCE, 0.9)
    store.add_fact("Lives in Berlin", FactCategory.PERSONAL, 0.95)
    store.add_fact("Assistant was wrong about X", FactCategory.CORRECTION, 0.85)
    store.add_fact("Working on Kubernetes", FactCategory.CONTEXT, 0.8)

    # Load in new store
    logger = MagicMock()
    new_store = MemoryStore(
        session_id=store.session_id,
        memory_dir=str(store.memory_dir),
        logger=logger
    )
    new_store.load()

    # Verify all categories survived
    categories = {f.category for f in new_store._facts}
    assert categories == {
        FactCategory.PREFERENCE,
        FactCategory.PERSONAL,
        FactCategory.CORRECTION,
        FactCategory.CONTEXT
    }


def test_fact_to_dict_and_from_dict() -> None:
    """Test Fact to_dict() and from_dict() methods."""
    fact = Fact(
        text="Test fact",
        category=FactCategory.PREFERENCE,
        confidence=0.85,
        created_at="2024-01-01T00:00:00Z",
        last_referenced="2024-01-01T01:00:00Z"
    )

    # Convert to dict
    fact_dict = fact.to_dict()
    assert fact_dict["text"] == "Test fact"
    assert fact_dict["category"] == "preference"
    assert fact_dict["confidence"] == 0.85

    # Convert back from dict
    restored_fact = Fact.from_dict(fact_dict)
    assert restored_fact.text == fact.text
    assert restored_fact.category == fact.category
    assert restored_fact.confidence == fact.confidence
    assert restored_fact.created_at == fact.created_at
    assert restored_fact.last_referenced == fact.last_referenced


# --- empty/edge case tests ---------------------------------------------------


def test_add_empty_text_returns_false(store: MemoryStore) -> None:
    """Test add_fact() returns False for empty text."""
    store.load()

    result = store.add_fact("", FactCategory.CONTEXT, 0.8)
    assert result is False
    assert len(store._facts) == 0


def test_add_whitespace_only_text_returns_false(store: MemoryStore) -> None:
    """Test add_fact() returns False for whitespace-only text."""
    store.load()

    result = store.add_fact("   ", FactCategory.CONTEXT, 0.8)
    assert result is False
    assert len(store._facts) == 0


def test_confidence_clamping(store: MemoryStore) -> None:
    """Test that confidence values are clamped to [0.0, 1.0]."""
    store.load()

    # Add fact with confidence > 1.0
    store.add_fact("High confidence", FactCategory.CONTEXT, 1.5)
    assert store._facts[0].confidence == 1.0

    # Add fact with confidence < 0.0
    store.add_fact("Negative confidence", FactCategory.CONTEXT, -0.5)
    assert store._facts[1].confidence == 0.0


# --- session isolation tests -------------------------------------------------


def test_different_sessions_have_different_files(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test that different sessions create different memory files."""
    session1 = "session-one"
    session2 = "session-two"

    logger = MagicMock()
    store1 = MemoryStore(session1, str(temp_memory_dir), logger)
    store2 = MemoryStore(session2, str(temp_memory_dir), logger)

    store1.load()
    store1.add_fact("Session 1 fact", FactCategory.CONTEXT, 0.8)

    store2.load()
    store2.add_fact("Session 2 fact", FactCategory.CONTEXT, 0.8)

    # Verify different file paths
    assert store1.file_path != store2.file_path

    # Verify both files exist
    assert store1.file_path.exists()
    assert store2.file_path.exists()

    # Verify stores don't see each other's facts
    assert len(store1._facts) == 1
    assert len(store2._facts) == 1
    assert store1._facts[0].text == "Session 1 fact"
    assert store2._facts[0].text == "Session 2 fact"


# --- file structure tests -----------------------------------------------------


def test_json_file_structure_is_valid(store: MemoryStore) -> None:
    """Test that the JSON file has the expected structure."""
    store.load()
    store.add_fact("Test fact", FactCategory.PREFERENCE, 0.9)

    with open(store.file_path, "r") as f:
        data = json.load(f)

    # Verify top-level structure
    assert "session_id" in data
    assert "facts" in data
    assert isinstance(data["facts"], list)
    assert "updated_at" in data

    # Verify fact structure
    fact = data["facts"][0]
    required_keys = {"text", "category", "confidence", "created_at", "last_referenced"}
    assert set(fact.keys()) == required_keys


def test_file_path_uses_correct_hash_length(store: MemoryStore) -> None:
    """Test that the hash in filename is exactly 16 characters."""
    filename = store.file_path.name

    # Extract hash from filename
    hash_part = filename.replace("session_", "").replace(".json", "")

    assert len(hash_part) == 16, "Hash should be exactly 16 characters"
    assert hash_part.isalnum(), "Hash should be alphanumeric"
