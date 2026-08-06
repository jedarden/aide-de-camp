"""
MemoryStore unit tests.

Tests MemoryStore initialization, in-memory operations, and JSON persistence:

Load initialization tests (bead adc-6cfeq, adc-4uqev):
- load() initializes with empty facts list
- load() initializes with provided session_id
- load() handles missing data/memory/ directory gracefully (adc-4uqev)
- load() handles empty facts dict in _data
- add_fact() appends fact to in-memory facts list
- add_fact() increments facts counter
- Multiple add_fact() calls accumulate correctly

Save persistence tests (bead adc-3g29w):
- save() creates JSON file at data/memory/session_<sha256(session_id)[:16]>.json
- save() writes facts in correct JSON structure
- save() creates data/memory/ directory if missing
- File content matches MemoryStore state
- save() includes updated_at and session_id fields
- save() handles empty facts and multiple facts correctly
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


def test_load_with_missing_directory(tmp_path: Path) -> None:
    """Test load() handles missing data/memory/ directory gracefully."""
    import shutil

    # Create a non-existent directory path
    missing_dir = tmp_path / "nonexistent" / "memory" / "path"

    # Ensure the directory truly doesn't exist
    if missing_dir.exists():
        shutil.rmtree(missing_dir.parent)

    # Create a store with the missing directory path
    test_store = MemoryStore(
        session_id="test-session-missing-dir",
        memory_dir=str(missing_dir),
        logger=MagicMock()
    )

    # load() should handle missing directory gracefully without errors
    test_store.load()

    # Verify it initializes with empty state despite missing directory
    assert len(test_store._facts) == 0
    assert isinstance(test_store._facts, list)
    assert test_store._data["session_id"] == test_store.session_id
    assert test_store._data["facts"] == []


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


# --- save() persistence tests (bead adc-3g29w) --------------------------------------


def test_save_creates_directory_if_missing(store: MemoryStore, tmp_path: Path) -> None:
    """Test that save() creates data/memory/ directory if missing."""
    import shutil
    import hashlib

    # Remove the memory directory if it exists
    memory_dir = tmp_path / "memory"
    if memory_dir.exists():
        shutil.rmtree(memory_dir)

    # Create a new store with the removed directory path
    new_store = MemoryStore(
        session_id="test-session-new",
        memory_dir=str(memory_dir),
        logger=MagicMock()
    )
    new_store.load()

    # Verify directory doesn't exist
    assert not memory_dir.exists()

    # Add a fact and save (should create directory)
    new_store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)

    # Verify directory was created
    assert memory_dir.exists()
    assert memory_dir.is_dir()


def test_save_creates_json_file_at_correct_path(store: MemoryStore) -> None:
    """Test that save() creates JSON file at data/memory/session_<sha256(session_id)[:16]>.json."""
    import hashlib

    store.load()
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    # Calculate expected filename
    session_id = store.session_id
    expected_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
    expected_filename = f"session_{expected_hash}.json"
    expected_path = store.memory_dir / expected_filename

    # Verify file exists at expected path
    assert expected_path.exists()
    assert expected_path.is_file()
    assert expected_path.name == expected_filename


def test_save_writes_facts_in_correct_json_structure(store: MemoryStore) -> None:
    """Test that save() writes facts in correct JSON structure."""
    import json

    store.load()

    # Add multiple facts
    store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    store.add_fact("User lives in Berlin", FactCategory.PERSONAL, 0.95)
    store.add_fact("User works on Kubernetes", FactCategory.CONTEXT, 0.85)

    # Read the saved file
    with open(store.file_path, "r") as f:
        saved_data = json.load(f)

    # Verify JSON structure
    assert isinstance(saved_data, dict)
    assert "facts" in saved_data
    assert "session_id" in saved_data
    assert "updated_at" in saved_data
    assert isinstance(saved_data["facts"], list)
    assert len(saved_data["facts"]) == 3


def test_save_file_content_matches_memory_store_state(store: MemoryStore) -> None:
    """Test that file content matches what was saved in MemoryStore state."""
    import json

    store.load()

    # Add facts
    facts_to_add = [
        ("User prefers dark mode", FactCategory.PREFERENCE, 0.9),
        ("User lives in Berlin", FactCategory.PERSONAL, 0.95),
    ]

    for text, category, confidence in facts_to_add:
        store.add_fact(text, category, confidence)

    # Read the saved file
    with open(store.file_path, "r") as f:
        saved_data = json.load(f)

    # Verify facts match
    saved_facts = saved_data["facts"]
    assert len(saved_facts) == 2

    for i, (text, category, confidence) in enumerate(facts_to_add):
        assert saved_facts[i]["text"] == text
        assert saved_facts[i]["category"] == category.value
        assert saved_facts[i]["confidence"] == confidence
        assert "created_at" in saved_facts[i]
        assert "last_referenced" in saved_facts[i]


def test_save_includes_updated_at_field(store: MemoryStore) -> None:
    """Test that save() includes updated_at timestamp field."""
    import json
    from datetime import datetime, timezone

    store.load()
    store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    # Read the saved file
    with open(store.file_path, "r") as f:
        saved_data = json.load(f)

    # Verify updated_at field exists and is valid ISO format
    assert "updated_at" in saved_data
    assert isinstance(saved_data["updated_at"], str)

    # Verify it's a valid ISO timestamp
    updated_at = saved_data["updated_at"]
    try:
        datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        pytest.fail("updated_at is not a valid ISO timestamp")


def test_save_includes_session_id(store: MemoryStore) -> None:
    """Test that saved file includes session_id."""
    import json

    test_session_id = "my-test-session-789"
    custom_store = MemoryStore(
        session_id=test_session_id,
        memory_dir=str(store.memory_dir),
        logger=MagicMock()
    )
    custom_store.load()
    custom_store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    # Read the saved file
    with open(custom_store.file_path, "r") as f:
        saved_data = json.load(f)

    # Verify session_id is saved correctly
    assert saved_data["session_id"] == test_session_id


def test_save_with_empty_facts(store: MemoryStore) -> None:
    """Test save() with no facts (empty facts list)."""
    import json

    store.load()

    # Save without adding any facts
    store.save()

    # Verify file was created with empty facts array
    assert store.file_path.exists()
    with open(store.file_path, "r") as f:
        saved_data = json.load(f)

    assert saved_data["facts"] == []
    assert "session_id" in saved_data
    assert "updated_at" in saved_data


def test_save_with_multiple_facts(store: MemoryStore) -> None:
    """Test save() with multiple facts accumulates correctly."""
    import json

    store.load()

    # Add multiple facts in sequence
    num_facts = 5
    for i in range(num_facts):
        store.add_fact(f"Fact {i}", FactCategory.CONTEXT, 0.8 + i * 0.02)

    # Read the saved file
    with open(store.file_path, "r") as f:
        saved_data = json.load(f)

    # Verify all facts were saved
    assert len(saved_data["facts"]) == num_facts

    # Verify each fact's content
    for i in range(num_facts):
        assert saved_data["facts"][i]["text"] == f"Fact {i}"
        assert saved_data["facts"][i]["category"] == FactCategory.CONTEXT.value


def test_save_fact_category_is_enum_value(store: MemoryStore) -> None:
    """Test that saved fact.category is the enum value string, not the enum."""
    import json

    store.load()
    store.add_fact("Test fact", FactCategory.PREFERENCE, 0.9)

    # Read the saved file
    with open(store.file_path, "r") as f:
        saved_data = json.load(f)

    # Verify category is the string value
    assert isinstance(saved_data["facts"][0]["category"], str)
    assert saved_data["facts"][0]["category"] == "preference"
    assert saved_data["facts"][0]["category"] == FactCategory.PREFERENCE.value


def test_save_overwrites_existing_file(store: MemoryStore) -> None:
    """Test that save() overwrites existing file with new data."""
    import json

    store.load()

    # Save first fact
    store.add_fact("First fact", FactCategory.CONTEXT, 0.8)

    # Add another fact and save again
    store.add_fact("Second fact", FactCategory.PERSONAL, 0.9)

    # Read the saved file
    with open(store.file_path, "r") as f:
        saved_data = json.load(f)

    # Verify both facts are present (not duplicated)
    assert len(saved_data["facts"]) == 2
    assert saved_data["facts"][0]["text"] == "First fact"
    assert saved_data["facts"][1]["text"] == "Second fact"


# --- load() from existing JSON tests (bead adc-ow8jx) --------------------------------


def test_load_reads_existing_json_file(store: MemoryStore) -> None:
    """Test that fresh load() reads existing JSON file correctly."""
    import json

    # Create a pre-existing JSON file with facts
    preexisting_facts = [
        {
            "text": "User prefers dark mode",
            "category": "preference",
            "confidence": 0.9,
            "created_at": "2024-01-01T12:00:00+00:00",
            "last_referenced": "2024-01-01T12:00:00+00:00"
        },
        {
            "text": "User lives in Berlin",
            "category": "personal",
            "confidence": 0.95,
            "created_at": "2024-01-02T14:30:00+00:00",
            "last_referenced": "2024-01-02T14:30:00+00:00"
        }
    ]

    # Write the pre-existing file
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": store.session_id,
            "facts": preexisting_facts,
            "updated_at": "2024-01-02T14:30:00+00:00"
        }, f)

    # Create a NEW store instance and load from the file
    new_store = MemoryStore(
        session_id=store.session_id,
        memory_dir=str(store.memory_dir),
        logger=MagicMock()
    )
    new_store.load()

    # Verify facts were loaded correctly
    assert len(new_store._facts) == 2
    assert new_store._facts[0].text == "User prefers dark mode"
    assert new_store._facts[0].category == FactCategory.PREFERENCE
    assert new_store._facts[0].confidence == 0.9
    assert new_store._facts[1].text == "User lives in Berlin"
    assert new_store._facts[1].category == FactCategory.PERSONAL
    assert new_store._facts[1].confidence == 0.95


def test_load_with_empty_json_file(store: MemoryStore) -> None:
    """Test load() with existing but empty JSON file."""
    import json

    # Create an empty JSON file
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": store.session_id,
            "facts": []
        }, f)

    # Load from the empty file
    store.load()

    # Verify we have empty facts list
    assert len(store._facts) == 0
    assert isinstance(store._facts, list)


def test_load_with_malformed_fact_entry(store: MemoryStore) -> None:
    """Test that load() skips malformed fact entries gracefully."""
    import json

    # Create a file with one valid and one malformed fact
    mixed_facts = [
        {
            "text": "Valid fact",
            "category": "preference",
            "confidence": 0.8,
            "created_at": "2024-01-01T12:00:00+00:00",
            "last_referenced": "2024-01-01T12:00:00+00:00"
        },
        {
            "text": "Malformed fact",
            "category": "preference",
            # Missing confidence field
            "created_at": "2024-01-01T12:00:00+00:00",
            "last_referenced": "2024-01-01T12:00:00+00:00"
        }
    ]

    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": store.session_id,
            "facts": mixed_facts
        }, f)

    # Load - should skip the malformed fact
    store.load()

    # Verify only the valid fact was loaded
    assert len(store._facts) == 1
    assert store._facts[0].text == "Valid fact"


def test_load_with_missing_facts_field(store: MemoryStore) -> None:
    """Test that load() handles missing 'facts' field gracefully."""
    import json

    # Create a file without 'facts' field
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": store.session_id
        }, f)

    # Load - should initialize with empty facts
    store.load()

    # Verify we have empty facts list
    assert len(store._facts) == 0
    assert store._data["facts"] == []


def test_load_with_missing_session_id(store: MemoryStore) -> None:
    """Test that load() adds missing session_id."""
    import json

    # Create a file without session_id
    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({"facts": []}, f)

    # Load - should add session_id
    store.load()

    # Verify session_id was added
    assert store._data["session_id"] == store.session_id


# --- _is_duplicate() tests (bead adc-ow8jx) -----------------------------------


def test_is_duplicate_detects_exact_match(store: MemoryStore) -> None:
    """Test that _is_duplicate() detects exact duplicate facts."""
    store.load()

    # Add a fact
    store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)

    # Check if the same text is detected as duplicate
    is_dup = store._is_duplicate("User prefers dark mode", FactCategory.PREFERENCE)
    assert is_dup is True


def test_is_duplicate_detects_normalized_match(store: MemoryStore) -> None:
    """Test that _is_duplicate() detects duplicates with different whitespace/case."""
    store.load()

    # Add a fact
    store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)

    # Check if variations are detected as duplicates
    assert store._is_duplicate("User prefers dark mode", FactCategory.PREFERENCE) is True
    assert store._is_duplicate("User  prefers  dark  mode", FactCategory.PREFERENCE) is True
    assert store._is_duplicate("user prefers dark mode", FactCategory.PREFERENCE) is True
    assert store._is_duplicate("USER PREFERS DARK MODE", FactCategory.PREFERENCE) is True


def test_is_duplicate_different_category_not_duplicate(store: MemoryStore) -> None:
    """Test that _is_duplicate() only checks within same category."""
    store.load()

    # Add a fact as PREFERENCE
    store.add_fact("User likes coding", FactCategory.PREFERENCE, 0.9)

    # Same text in different category should not be duplicate
    is_dup = store._is_duplicate("User likes coding", FactCategory.CONTEXT)
    assert is_dup is False


def test_is_duplicate_detects_long_text_overlap(store: MemoryStore) -> None:
    """Test that _is_duplicate() detects duplicates with long text overlap."""
    store.load()

    # Add a long fact
    long_fact = "User works extensively with Kubernetes clusters and has extensive experience with ArgoCD"
    store.add_fact(long_fact, FactCategory.CONTEXT, 0.9)

    # Check if a slightly different but overlapping text is detected
    overlapping_fact = "User works extensively with Kubernetes clusters and has extensive experience with ArgoCD deployments"
    is_dup = store._is_duplicate(overlapping_fact, FactCategory.CONTEXT)

    # Should detect as duplicate due to prefix overlap (>20 chars)
    assert is_dup is True


def test_is_duplicate_short_text_no_overlap(store: MemoryStore) -> None:
    """Test that _is_duplicate() doesn't detect overlap for short text."""
    store.load()

    # Add a short fact
    store.add_fact("Likes cats", FactCategory.PREFERENCE, 0.9)

    # Similar but different short text should not be duplicate
    is_dup = store._is_duplicate("Likes dogs", FactCategory.PREFERENCE)
    assert is_dup is False


def test_is_duplicate_no_facts(store: MemoryStore) -> None:
    """Test that _is_duplicate() returns False when no facts exist."""
    store.load()

    # With no facts, nothing should be duplicate
    is_dup = store._is_duplicate("Any text", FactCategory.PREFERENCE)
    assert is_dup is False


# --- deduplication on add_fact() tests (bead adc-ow8jx) -------------------------


def test_add_fact_skips_duplicate_exact_match(store: MemoryStore) -> None:
    """Test that add_fact() skips duplicate facts (exact match)."""
    store.load()

    # Add a fact
    result1 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result1 is True
    assert len(store._facts) == 1

    # Try to add the same fact again
    result2 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result2 is False
    assert len(store._facts) == 1, "Duplicate should not be added"


def test_add_fact_skips_duplicate_normalized_match(store: MemoryStore) -> None:
    """Test that add_fact() skips duplicates with different whitespace/case."""
    store.load()

    # Add a fact
    result1 = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result1 is True
    assert len(store._facts) == 1

    # Try to add variations - all should be rejected
    result2 = store.add_fact("User  prefers  dark  mode", FactCategory.PREFERENCE, 0.9)
    assert result2 is False
    assert len(store._facts) == 1

    result3 = store.add_fact("user prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result3 is False
    assert len(store._facts) == 1


def test_add_fact_allows_same_text_different_category(store: MemoryStore) -> None:
    """Test that add_fact() allows same text in different categories."""
    store.load()

    # Add a fact as PREFERENCE
    result1 = store.add_fact("User likes coding", FactCategory.PREFERENCE, 0.9)
    assert result1 is True
    assert len(store._facts) == 1

    # Same text as CONTEXT should be allowed
    result2 = store.add_fact("User likes coding", FactCategory.CONTEXT, 0.9)
    assert result2 is True
    assert len(store._facts) == 2


def test_add_fact_after_load_from_persisted_file(store: MemoryStore) -> None:
    """Test that add_fact() skips duplicates when loading from persisted file."""
    import json

    # Create a pre-existing file with facts
    preexisting_facts = [
        {
            "text": "User prefers dark mode",
            "category": "preference",
            "confidence": 0.9,
            "created_at": "2024-01-01T12:00:00+00:00",
            "last_referenced": "2024-01-01T12:00:00+00:00"
        }
    ]

    store.file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.file_path, "w") as f:
        json.dump({
            "session_id": store.session_id,
            "facts": preexisting_facts
        }, f)

    # Load from file
    store.load()
    assert len(store._facts) == 1

    # Try to add the same fact - should be skipped
    result = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)
    assert result is False
    assert len(store._facts) == 1, "Duplicate should not be added after load"

    # Add a different fact - should work
    result2 = store.add_fact("User lives in Berlin", FactCategory.PERSONAL, 0.95)
    assert result2 is True
    assert len(store._facts) == 2


# --- round-trip persistence tests (bead adc-ow8jx) --------------------------------


def test_round_trip_save_load_preserves_facts(store: MemoryStore) -> None:
    """Test round-trip: save → load → facts match original."""
    import json

    store.load()

    # Add multiple facts
    original_facts = [
        ("User prefers dark mode", FactCategory.PREFERENCE, 0.9),
        ("User lives in Berlin", FactCategory.PERSONAL, 0.95),
        ("User works on Kubernetes", FactCategory.CONTEXT, 0.85),
    ]

    for text, category, confidence in original_facts:
        store.add_fact(text, category, confidence)

    # Save to disk
    store.save()

    # Create a NEW store instance and load from disk
    new_store = MemoryStore(
        session_id=store.session_id,
        memory_dir=str(store.memory_dir),
        logger=MagicMock()
    )
    new_store.load()

    # Verify facts match
    assert len(new_store._facts) == len(original_facts)

    for i, (text, category, confidence) in enumerate(original_facts):
        assert new_store._facts[i].text == text
        assert new_store._facts[i].category == category
        assert new_store._facts[i].confidence == confidence


def test_round_trip_preserves_metadata(store: MemoryStore) -> None:
    """Test that round-trip preserves timestamps and metadata."""
    store.load()

    # Add a fact
    store.add_fact("Test fact", FactCategory.PREFERENCE, 0.9)

    # Get the original timestamp
    original_created_at = store._facts[0].created_at
    original_last_referenced = store._facts[0].last_referenced

    # Save
    store.save()

    # Load into new store
    new_store = MemoryStore(
        session_id=store.session_id,
        memory_dir=str(store.memory_dir),
        logger=MagicMock()
    )
    new_store.load()

    # Verify metadata is preserved
    assert new_store._facts[0].created_at == original_created_at
    assert new_store._facts[0].last_referenced == original_last_referenced
    assert new_store._facts[0].text == "Test fact"
    assert new_store._facts[0].category == FactCategory.PREFERENCE
    assert new_store._facts[0].confidence == 0.9


def test_round_trip_with_empty_facts(store: MemoryStore) -> None:
    """Test round-trip with empty facts list."""
    store.load()
    store.save()

    # Load into new store
    new_store = MemoryStore(
        session_id=store.session_id,
        memory_dir=str(store.memory_dir),
        logger=MagicMock()
    )
    new_store.load()

    # Verify empty facts list
    assert len(new_store._facts) == 0
    assert isinstance(new_store._facts, list)


def test_round_trip_preserves_session_id(store: MemoryStore) -> None:
    """Test that round-trip preserves session_id."""
    test_session_id = "round-trip-test-session"
    custom_store = MemoryStore(
        session_id=test_session_id,
        memory_dir=str(store.memory_dir),
        logger=MagicMock()
    )

    custom_store.load()
    custom_store.add_fact("Test fact", FactCategory.CONTEXT, 0.8)

    # Load into new store
    new_store = MemoryStore(
        session_id=test_session_id,
        memory_dir=str(store.memory_dir),
        logger=MagicMock()
    )
    new_store.load()

    # Verify session_id is preserved
    assert new_store._data["session_id"] == test_session_id
    assert new_store.session_id == test_session_id


def test_round_trip_multiple_cycles(store: MemoryStore) -> None:
    """Test multiple save/load cycles preserve facts correctly."""
    store.load()

    # First cycle: add facts and save
    store.add_fact("Fact 1", FactCategory.PREFERENCE, 0.9)
    store.add_fact("Fact 2", FactCategory.PERSONAL, 0.85)
    store.save()

    # Second cycle: load, add more, save
    store.load()
    store.add_fact("Fact 3", FactCategory.CONTEXT, 0.8)
    store.save()

    # Third cycle: load and verify
    store.load()
    assert len(store._facts) == 3
    assert store._facts[0].text == "Fact 1"
    assert store._facts[1].text == "Fact 2"
    assert store._facts[2].text == "Fact 3"


def test_round_trip_preserves_fact_order(store: MemoryStore) -> None:
    """Test that round-trip preserves fact insertion order."""
    store.load()

    # Add facts in specific order
    facts_order = ["First", "Second", "Third", "Fourth"]
    for fact_text in facts_order:
        store.add_fact(fact_text, FactCategory.CONTEXT, 0.8)

    store.save()

    # Load into new store
    new_store = MemoryStore(
        session_id=store.session_id,
        memory_dir=str(store.memory_dir),
        logger=MagicMock()
    )
    new_store.load()

    # Verify order is preserved
    loaded_texts = [f.text for f in new_store._facts]
    assert loaded_texts == facts_order
