"""Tests for MemoryStore load() behavior and edge cases."""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.memory.store import Fact, FactCategory, MemoryStore, DEFAULT_MEMORY_DIR


class TestMemoryStoreLoad:
    """Test MemoryStore.load() initialization and file loading behavior."""

    def test_load_creates_empty_store_when_file_not_found(self, tmp_path):
        """Loading from non-existent file creates empty store (facts=[])."""
        store = MemoryStore("test-session", memory_dir=str(tmp_path))
        store.load()

        assert store._facts == []
        assert store.session_id == "test-session"
        assert store._data.get("facts") == []
        assert store._data.get("session_id") == "test-session"

    def test_load_from_existing_json_file_restores_facts(self, tmp_path):
        """Loading from existing JSON file restores facts correctly."""
        session_id = "test-session-123"

        # Create a pre-existing memory file with facts
        memory_dir = tmp_path
        memory_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        file_path = memory_dir / f"session_{user_hash}.json"

        test_data = {
            "session_id": session_id,
            "facts": [
                {
                    "text": "User prefers dark mode",
                    "category": "preference",
                    "confidence": 0.9,
                    "created_at": "2026-08-06T12:00:00+00:00",
                    "last_referenced": "2026-08-06T12:00:00+00:00",
                },
                {
                    "text": "Lives in Berlin",
                    "category": "personal",
                    "confidence": 0.95,
                    "created_at": "2026-08-06T12:01:00+00:00",
                    "last_referenced": "2026-08-06T12:01:00+00:00",
                },
            ],
        }

        with open(file_path, "w") as f:
            json.dump(test_data, f)

        # Load and verify
        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        assert len(store._facts) == 2
        assert store._facts[0].text == "User prefers dark mode"
        assert store._facts[0].category == FactCategory.PREFERENCE
        assert store._facts[0].confidence == 0.9
        assert store._facts[1].text == "Lives in Berlin"
        assert store._facts[1].category == FactCategory.PERSONAL

    def test_file_path_format(self, tmp_path):
        """File path format is correct: data/memory/session_<sha256(session_id)[:16]>.json."""
        session_id = "test-session-path"

        store = MemoryStore(session_id, memory_dir=str(tmp_path))

        # Verify hash is computed correctly
        import hashlib
        expected_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]

        assert store.user_hash == expected_hash
        assert store.file_path == tmp_path / f"session_{expected_hash}.json"

    def test_session_id_stored_correctly_in_data(self, tmp_path):
        """Session ID is stored correctly in _data."""
        session_id = "my-test-session-456"

        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        assert store._data["session_id"] == session_id
        assert store.session_id == session_id

    def test_load_handles_malformed_json_gracefully(self, tmp_path):
        """Malformed JSON file results in empty store, no crash."""
        session_id = "malformed-test"

        # Create file with invalid JSON
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        file_path = memory_dir / f"session_{user_hash}.json"

        with open(file_path, "w") as f:
            f.write("{invalid json content")

        # Load should handle error gracefully
        logger = MagicMock()
        store = MemoryStore(session_id, memory_dir=str(tmp_path), logger=logger)
        store.load()

        # Should fall back to empty state
        assert store._facts == []
        assert store._data["session_id"] == session_id
        assert store._data["facts"] == []
        logger.debug.assert_called()

    def test_load_handles_missing_session_id_field(self, tmp_path):
        """Missing session_id field gets filled with current session_id."""
        session_id = "session-missing-field"

        # Create file with no session_id
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        file_path = memory_dir / f"session_{user_hash}.json"

        with open(file_path, "w") as f:
            json.dump({"facts": []}, f)

        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        # Should fill in session_id
        assert store._data["session_id"] == session_id

    def test_load_handles_null_session_id_field(self, tmp_path):
        """Null session_id field gets replaced with current session_id."""
        session_id = "session-null-field"

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        file_path = memory_dir / f"session_{user_hash}.json"

        with open(file_path, "w") as f:
            json.dump({"session_id": None, "facts": []}, f)

        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        assert store._data["session_id"] == session_id

    def test_load_handles_missing_facts_field(self, tmp_path):
        """Missing facts field defaults to empty list."""
        session_id = "session-no-facts"

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        file_path = memory_dir / f"session_{user_hash}.json"

        with open(file_path, "w") as f:
            json.dump({"session_id": session_id}, f)

        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        assert store._facts == []
        assert store._data["facts"] == []

    def test_load_handles_non_list_facts_field(self, tmp_path):
        """Facts field with non-list value gets reset to empty list."""
        session_id = "session-bad-facts-type"

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        file_path = memory_dir / f"session_{user_hash}.json"

        with open(file_path, "w") as f:
            json.dump({"session_id": session_id, "facts": "not-a-list"}, f)

        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        assert store._facts == []
        assert store._data["facts"] == []

    def test_load_handles_malformed_fact_entries(self, tmp_path):
        """Malformed fact entries are skipped, valid ones loaded."""
        session_id = "session-mixed-facts"

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        file_path = memory_dir / f"session_{user_hash}.json"

        test_data = {
            "session_id": session_id,
            "facts": [
                # Valid fact
                {
                    "text": "Valid fact",
                    "category": "preference",
                    "confidence": 0.8,
                    "created_at": "2026-08-06T12:00:00+00:00",
                    "last_referenced": "2026-08-06T12:00:00+00:00",
                },
                # Missing required field
                {
                    "text": "Missing category",
                    "confidence": 0.7,
                    "created_at": "2026-08-06T12:00:00+00:00",
                    "last_referenced": "2026-08-06T12:00:00+00:00",
                },
                # Not a dict
                "not a dict",
                # Another valid fact
                {
                    "text": "Another valid one",
                    "category": "personal",
                    "confidence": 0.9,
                    "created_at": "2026-08-06T12:01:00+00:00",
                    "last_referenced": "2026-08-06T12:01:00+00:00",
                },
            ],
        }

        with open(file_path, "w") as f:
            json.dump(test_data, f)

        logger = MagicMock()
        store = MemoryStore(session_id, memory_dir=str(tmp_path), logger=logger)
        store.load()

        # Should load only valid facts
        assert len(store._facts) == 2
        assert store._facts[0].text == "Valid fact"
        assert store._facts[1].text == "Another valid one"
        logger.debug.assert_called()

    def test_load_handles_empty_facts_list(self, tmp_path):
        """Empty facts list loads correctly."""
        session_id = "empty-facts-session"

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        file_path = memory_dir / f"session_{user_hash}.json"

        with open(file_path, "w") as f:
            json.dump({"session_id": session_id, "facts": []}, f)

        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        assert store._facts == []
        assert store._data["facts"] == []

    def test_load_updates_fact_timestamps(self, tmp_path):
        """load() doesn't modify fact timestamps - save() does."""
        session_id = "timestamp-session"

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        file_path = memory_dir / f"session_{user_hash}.json"

        original_time = "2026-08-01T10:00:00+00:00"
        test_data = {
            "session_id": session_id,
            "facts": [
                {
                    "text": "Old fact",
                    "category": "context",
                    "confidence": 0.7,
                    "created_at": original_time,
                    "last_referenced": original_time,
                },
            ],
        }

        with open(file_path, "w") as f:
            json.dump(test_data, f)

        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        # Timestamps should be preserved from file
        assert store._facts[0].created_at == original_time
        assert store._facts[0].last_referenced == original_time

    def test_load_idempotent(self, tmp_path):
        """Loading multiple times produces consistent results."""
        session_id = "idempotent-session"

        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        first_facts = store._facts.copy()
        first_data = store._data.copy()

        # Load again
        store.load()

        # Should be identical
        assert store._facts == first_facts
        assert store._data == first_data
