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


# --- comprehensive deduplication tests (bead adc-312mo) ----------------------


def test_deduplicate_same_text_different_category_allowed(store: MemoryStore) -> None:
    """Test that identical text with different categories are both stored."""
    store.load()

    result1 = store.add_fact("User loves Kubernetes", FactCategory.PREFERENCE, 0.9)
    result2 = store.add_fact("User loves Kubernetes", FactCategory.CONTEXT, 0.8)

    assert result1 is True, "First fact should be added"
    assert result2 is True, "Same text with different category should be allowed"

    assert len(store._facts) == 2
    categories = {f.category for f in store._facts}
    assert categories == {FactCategory.PREFERENCE, FactCategory.CONTEXT}


def test_deduplicate_different_text_same_category_allowed(store: MemoryStore) -> None:
    """Test that different text with same category are both stored."""
    store.load()

    result1 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    result2 = store.add_fact("User prefers light mode", FactCategory.PREFERENCE, 0.8)

    assert result1 is True, "First fact should be added"
    assert result2 is True, "Different text with same category should be allowed"

    assert len(store._facts) == 2
    texts = {f.text for f in store._facts}
    assert texts == {"User prefers dark mode", "User prefers light mode"}


def test_deduplicate_exact_match_with_metadata(store: MemoryStore) -> None:
    """Test deduplication considers text+category as the composite key."""
    store.load()

    # Add first fact with specific confidence
    result1 = store.add_fact("User prefers async/await", FactCategory.PREFERENCE, 0.95)
    assert result1 is True

    # Try to add identical fact with different confidence (metadata)
    result2 = store.add_fact("User prefers async/await", FactCategory.PREFERENCE, 0.7)
    assert result2 is False, "Duplicate should be rejected regardless of confidence"

    # Only one fact should exist
    assert len(store._facts) == 1
    # Original confidence should be preserved
    assert store._facts[0].confidence == 0.95


def test_deduplicate_similar_but_different_meaning(store: MemoryStore) -> None:
    """Test that similar facts with different meanings are both stored."""
    store.load()

    # These are similar but express different preferences
    result1 = store.add_fact("User prefers dark mode for IDEs", FactCategory.PREFERENCE, 0.9)
    result2 = store.add_fact("User prefers light mode for terminals", FactCategory.PREFERENCE, 0.9)

    assert result1 is True
    assert result2 is True, "Different meanings should not be deduplicated"

    assert len(store._facts) == 2


def test_deduplicate_substring_not_duplicate(store: MemoryStore) -> None:
    """Test that one fact being a substring of another doesn't trigger deduplication for short texts."""
    store.load()

    # Short facts (< 20 chars) should not trigger prefix matching
    result1 = store.add_fact("Likes Python", FactCategory.PREFERENCE, 0.9)
    result2 = store.add_fact("Likes Python programming", FactCategory.PREFERENCE, 0.9)

    assert result1 is True
    assert result2 is True, "Substring relationship in short texts should not deduplicate"

    assert len(store._facts) == 2


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


# --- additional load() edge case tests (bead adc-hxc18) ----------------------


def test_load_with_missing_facts_field(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() handles JSON missing 'facts' field gracefully."""
    # Create a file with valid JSON but missing 'facts' field
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({"session_id": store.session_id}, f)

    store.load()

    # Should fall back to empty facts list
    assert store._facts == []
    assert store._data.get("session_id") == store.session_id


def test_load_with_missing_session_id_field(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() handles JSON missing 'session_id' field gracefully."""
    # Create a file with valid JSON but missing 'session_id' field
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({"facts": []}, f)

    store.load()

    # Should initialize with current session_id
    assert store._data.get("session_id") == store.session_id
    assert store._facts == []


def test_load_with_empty_facts_array(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() correctly handles JSON with empty facts array."""
    # Create a file with empty facts array
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": store.session_id,
            "facts": []
        }, f)

    store.load()

    # Should load with empty facts
    assert store._facts == []
    assert len(store._facts) == 0


def test_load_with_invalid_fact_structure(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() handles facts with invalid/missing fields gracefully."""
    # Create a file with malformed fact data
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": store.session_id,
            "facts": [
                {"text": "Valid fact", "category": "preference", "confidence": 0.8,
                 "created_at": "2024-01-01T00:00:00Z", "last_referenced": "2024-01-01T00:00:00Z"},
                {"text": "Missing fields"},  # Invalid fact
                None,  # Not a dict
                "string_instead_of_dict",  # Wrong type
                {"text": "Partial fact", "category": "context"}  # Missing required fields
            ]
        }, f)

    store.load()

    # Should load only the valid fact and skip invalid ones
    assert len(store._facts) == 1
    assert store._facts[0].text == "Valid fact"
    assert store._facts[0].category == FactCategory.PREFERENCE


def test_load_with_extra_unknown_fields(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() handles JSON with extra/unknown fields gracefully."""
    # Create a file with extra fields
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": store.session_id,
            "facts": [],
            "unknown_field": "some_value",
            "another_unknown": 123,
            "nested": {"key": "value"}
        }, f)

    store.load()

    # Should load successfully, ignoring extra fields
    assert store._facts == []
    assert store._data.get("session_id") == store.session_id


def test_load_with_null_session_id(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() handles JSON with null session_id."""
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": None,
            "facts": []
        }, f)

    store.load()

    # Should use the store's session_id
    assert store._data.get("session_id") == store.session_id


def test_load_with_facts_as_non_list(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() handles JSON where 'facts' is not a list."""
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": store.session_id,
            "facts": "not_a_list"
        }, f)

    store.load()

    # Should fall back to empty list
    assert store._facts == []


def test_session_id_persists_across_load(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test that session_id is correctly stored and retrieved."""
    store.load()
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    # Read the file directly to verify session_id is stored
    with open(store.file_path, "r") as f:
        data = json.load(f)

    assert data["session_id"] == store.session_id
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


def test_load_from_empty_json_object(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() handles completely empty JSON object."""
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({}, f)

    store.load()

    # Should initialize with defaults
    assert store._facts == []
    assert store._data.get("session_id") == store.session_id


# --- load() initialization edge cases (bead adc-4uqev) --------------------------


def test_load_with_nonexistent_memory_directory(tmp_path: Path, session_id: str) -> None:
    """Test load() when memory directory doesn't exist at all."""
    # Create a MemoryStore with a non-existent directory
    nonexistent_dir = tmp_path / "nonexistent" / "memory" / "path"
    logger = MagicMock()
    store = MemoryStore(
        session_id=session_id,
        memory_dir=str(nonexistent_dir),
        logger=logger
    )

    # load() should not crash - it should initialize empty state
    store.load()

    assert store._facts == []
    assert store._data == {"facts": [], "session_id": store.session_id}
    assert store.file_path.parent == nonexistent_dir


def test_load_with_empty_memory_directory(tmp_path: Path, session_id: str) -> None:
    """Test load() when memory directory exists but is empty."""
    # Create an empty directory
    empty_dir = tmp_path / "empty_memory"
    empty_dir.mkdir(parents=True, exist_ok=True)

    logger = MagicMock()
    store = MemoryStore(
        session_id=session_id,
        memory_dir=str(empty_dir),
        logger=logger
    )

    # load() should not crash - should initialize empty state
    store.load()

    assert store._facts == []
    assert store._data == {"facts": [], "session_id": store.session_id}


def test_load_creates_empty_state_when_file_missing(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test load() creates empty state when specific memory file doesn't exist."""
    # Ensure directory exists but file doesn't
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    assert not store.file_path.exists()

    store.load()

    # Should initialize with empty state
    assert store._facts == []
    assert store._data == {"facts": [], "session_id": store.session_id}


def test_load_is_idempotent(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test that calling load() multiple times is safe (idempotent)."""
    store.load()

    # Add a fact
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)
    initial_count = len(store._facts)

    # Call load() again - should not change the facts already in memory
    store.load()

    assert len(store._facts) == initial_count
    assert store._facts[0].text == "Test fact"


def test_load_with_nested_nonexistent_path(tmp_path: Path, session_id: str) -> None:
    """Test load() with deeply nested non-existent directory path."""
    # Create a path with multiple non-existent levels
    nested_dir = tmp_path / "level1" / "level2" / "level3" / "memory"
    logger = MagicMock()
    store = MemoryStore(
        session_id=session_id,
        memory_dir=str(nested_dir),
        logger=logger
    )

    # Should not crash
    store.load()

    assert store._facts == []
    assert store._data == {"facts": [], "session_id": store.session_id}


def test_load_then_save_creates_directory(tmp_path: Path, session_id: str) -> None:
    """Test that save() creates directory structure after load() from nonexistent dir."""
    # Create store with non-existent directory
    nonexistent_dir = tmp_path / "does" / "not" / "exist"
    logger = MagicMock()
    store = MemoryStore(
        session_id=session_id,
        memory_dir=str(nonexistent_dir),
        logger=logger
    )

    # Load from non-existent directory
    store.load()
    assert not store.file_path.parent.exists()

    # Save should create the directory
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    # Directory and file should now exist
    assert store.file_path.parent.exists()
    assert store.file_path.exists()


def test_load_initializes_session_id_field(store: MemoryStore, temp_memory_dir: Path) -> None:
    """Test that load() initializes session_id field correctly."""
    store.load()

    # Check internal data structure
    assert "session_id" in store._data
    assert store._data["session_id"] == store.session_id
    assert isinstance(store._data["session_id"], str)


def test_load_initializes_facts_field_as_empty_list(store: MemoryStore) -> None:
    """Test that load() initializes facts field as empty list when file missing."""
    store.load()

    # Should have facts field initialized
    assert "facts" in store._data
    assert isinstance(store._data["facts"], list)
    assert len(store._data["facts"]) == 0
    assert store._facts == []


def test_load_with_partial_directory_exists(tmp_path: Path, session_id: str) -> None:
    """Test load() when partial directory structure exists."""
    # Create partial structure: /tmp/level1/level2 exists but level3 doesn't
    partial_dir = tmp_path / "level1" / "level2"
    full_dir = partial_dir / "level3" / "memory"
    partial_dir.mkdir(parents=True, exist_ok=True)

    logger = MagicMock()
    store = MemoryStore(
        session_id=session_id,
        memory_dir=str(full_dir),
        logger=logger
    )

    # Should handle gracefully
    store.load()

    assert store._facts == []
    assert store._data == {"facts": [], "session_id": store.session_id}


# --- save() persistence tests (bead adc-434vw) -----------------------------------


def test_save_creates_file_at_exact_hashed_path(tmp_path: Path, session_id: str) -> None:
    """Test save() creates JSON file at correct path: session_<sha256(session_id)[:16]>.json"""
    memory_dir = tmp_path / "data" / "memory"
    logger = MagicMock()
    store = MemoryStore(
        session_id=session_id,
        memory_dir=str(memory_dir),
        logger=logger
    )

    # Calculate expected hash
    expected_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
    expected_filename = f"session_{expected_hash}.json"

    # Save without calling load() first
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    # Verify file exists at expected path
    assert store.file_path.exists()
    assert store.file_path.name == expected_filename
    assert str(store.file_path.parent) == str(memory_dir)


def test_save_creates_data_memory_directory_if_missing(tmp_path: Path, session_id: str) -> None:
    """Test save() creates data/memory/ directory if it doesn't exist."""
    # Use a path that definitely doesn't exist
    memory_dir = tmp_path / "data" / "memory"
    assert not memory_dir.exists(), "Directory should not exist initially"

    logger = MagicMock()
    store = MemoryStore(
        session_id=session_id,
        memory_dir=str(memory_dir),
        logger=logger
    )

    # Save should create the directory
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    # Verify directory was created
    assert memory_dir.exists(), "Directory should be created by save()"
    assert memory_dir.is_dir(), "Should be a directory"


def test_save_creates_nested_directory_structure(tmp_path: Path, session_id: str) -> None:
    """Test save() creates nested directory structure like data/deep/nested/memory."""
    # Use a deeply nested path that doesn't exist
    nested_dir = tmp_path / "data" / "deep" / "nested" / "memory"
    assert not nested_dir.exists(), "Nested directory should not exist initially"

    logger = MagicMock()
    store = MemoryStore(
        session_id=session_id,
        memory_dir=str(nested_dir),
        logger=logger
    )

    # Save should create all parent directories
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    # Verify entire path was created
    assert nested_dir.exists(), "Nested directory should be created"
    assert nested_dir.is_dir(), "Should be a directory"
    assert store.file_path.exists(), "File should exist in nested directory"


def test_save_overwrites_existing_file(store: MemoryStore) -> None:
    """Test file overwrites on subsequent save() calls."""
    store.load()

    # First save
    store.add_fact("First fact", FactCategory.PREFERENCE, 0.9)
    first_modified = store.file_path.stat().st_mtime

    # Small delay to ensure timestamp difference
    import time
    time.sleep(0.01)

    # Second save - should overwrite
    store.add_fact("Second fact", FactCategory.PERSONAL, 0.85)
    second_modified = store.file_path.stat().st_mtime

    # Verify file was overwritten (modified time should be later)
    assert second_modified > first_modified, "File should be overwritten on subsequent save"

    # Verify both facts are in the file
    with open(store.file_path, "r") as f:
        data = json.load(f)

    assert len(data["facts"]) == 2
    texts = [f["text"] for f in data["facts"]]
    assert "First fact" in texts
    assert "Second fact" in texts


def test_save_persists_all_fact_fields(store: MemoryStore) -> None:
    """Test that persisted JSON structure contains all fact fields."""
    store.load()
    store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.95)

    # Read the file and verify structure
    with open(store.file_path, "r") as f:
        data = json.load(f)

    # Verify top-level fields
    assert "session_id" in data
    assert "facts" in data
    assert "updated_at" in data

    # Verify fact has all required fields
    fact = data["facts"][0]
    required_fields = {"text", "category", "confidence", "created_at", "last_referenced"}
    assert set(fact.keys()) == required_fields

    # Verify field types
    assert isinstance(fact["text"], str)
    assert isinstance(fact["category"], str)
    assert isinstance(fact["confidence"], float)
    assert isinstance(fact["created_at"], str)
    assert isinstance(fact["last_referenced"], str)


def test_save_persists_multiple_facts(store: MemoryStore) -> None:
    """Test that all facts are persisted correctly."""
    store.load()

    # Add multiple facts
    facts_to_add = [
        ("Prefers dark mode", FactCategory.PREFERENCE, 0.9),
        ("Lives in Berlin", FactCategory.PERSONAL, 0.95),
        ("Working on Kubernetes", FactCategory.CONTEXT, 0.8),
        ("Corrected about X", FactCategory.CORRECTION, 0.85),
    ]

    for text, category, confidence in facts_to_add:
        store.add_fact(text, category, confidence)

    # Read the file and verify all facts are present
    with open(store.file_path, "r") as f:
        data = json.load(f)

    assert len(data["facts"]) == len(facts_to_add)

    # Verify each fact
    for i, (text, category, confidence) in enumerate(facts_to_add):
        fact = data["facts"][i]
        assert fact["text"] == text
        assert fact["category"] == category.value
        assert fact["confidence"] == confidence


def test_save_without_prior_load(store: MemoryStore) -> None:
    """Test save() works correctly without calling load() first."""
    # Don't call load() - just add facts directly
    store.add_fact("Direct save test", FactCategory.CONTEXT, 0.8)

    # Verify file was created
    assert store.file_path.exists()

    # Verify content
    with open(store.file_path, "r") as f:
        data = json.load(f)

    assert len(data["facts"]) == 1
    assert data["facts"][0]["text"] == "Direct save test"
