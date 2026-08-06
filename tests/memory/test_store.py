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

        memory_dir = tmp_path
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

        memory_dir = tmp_path
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

        memory_dir = tmp_path
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


class TestMemoryStorePersistence:
    """Test MemoryStore persistence: add_fact() and save() behavior."""

    def test_add_fact_adds_to_in_memory_facts_list(self, tmp_path):
        """add_fact() adds fact to in-memory facts list."""
        store = MemoryStore("test-session", memory_dir=str(tmp_path))
        store.load()

        # Add a fact
        result = store.add_fact("User prefers dark mode", FactCategory.PREFERENCE, 0.9)

        # Verify it was added
        assert result is True
        assert len(store._facts) == 1
        assert store._facts[0].text == "User prefers dark mode"
        assert store._facts[0].category == FactCategory.PREFERENCE
        assert store._facts[0].confidence == 0.9

    def test_add_fact_creates_json_file(self, tmp_path):
        """add_fact() creates JSON file in data/memory directory."""
        session_id = "persist-session"
        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        # Add a fact
        store.add_fact("Lives in Berlin", FactCategory.PERSONAL, 0.95)

        # Verify file exists
        assert store.file_path.exists()
        assert store.file_path.parent.exists()

    def test_save_writes_json_file_to_correct_path(self, tmp_path):
        """save() writes JSON file to correct path with proper format."""
        session_id = "save-path-session"
        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        # Add facts
        store.add_fact("Prefers dark mode", FactCategory.PREFERENCE, 0.9)
        store.add_fact("Lives in Berlin", FactCategory.PERSONAL, 0.95)

        # File should exist at correct path
        assert store.file_path.exists()

        # Verify JSON content is valid and properly formatted
        with open(store.file_path, "r") as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert "facts" in data
        assert "session_id" in data
        assert "updated_at" in data
        assert data["session_id"] == session_id
        assert len(data["facts"]) == 2

    def test_json_file_format_is_correct(self, tmp_path):
        """JSON file format includes all required fields and is readable."""
        session_id = "format-session"
        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        # Add a fact
        store.add_fact("Working on Kubernetes cluster", FactCategory.CONTEXT, 0.8)

        # Read file directly
        with open(store.file_path, "r") as f:
            content = f.read()
            data = json.loads(content)

        # Verify top-level structure
        assert isinstance(data, dict)
        assert set(data.keys()) >= {"facts", "session_id", "updated_at"}

        # Verify fact structure
        facts = data["facts"]
        assert len(facts) == 1
        fact = facts[0]

        required_keys = {"text", "category", "confidence", "created_at", "last_referenced"}
        assert set(fact.keys()) == required_keys
        assert fact["text"] == "Working on Kubernetes cluster"
        assert fact["category"] == "context"
        assert 0.0 <= fact["confidence"] <= 1.0
        assert isinstance(fact["created_at"], str)
        assert isinstance(fact["last_referenced"], str)

    def test_round_trip_save_load_preserves_facts(self, tmp_path):
        """Round-trip test: save → load → facts are preserved."""
        session_id = "roundtrip-session"

        # Create first store and add facts
        store1 = MemoryStore(session_id, memory_dir=str(tmp_path))
        store1.load()
        store1.add_fact("Prefers dark mode", FactCategory.PREFERENCE, 0.9)
        store1.add_fact("Lives in Berlin", FactCategory.PERSONAL, 0.95)
        store1.add_fact("Working on Kubernetes", FactCategory.CONTEXT, 0.8)

        # Create new store instance and load from same file
        store2 = MemoryStore(session_id, memory_dir=str(tmp_path))
        store2.load()

        # Verify all facts preserved
        assert len(store2._facts) == 3
        facts_by_text = {f.text: f for f in store2._facts}

        assert "Prefers dark mode" in facts_by_text
        assert facts_by_text["Prefers dark mode"].category == FactCategory.PREFERENCE
        assert facts_by_text["Prefers dark mode"].confidence == 0.9

        assert "Lives in Berlin" in facts_by_text
        assert facts_by_text["Lives in Berlin"].category == FactCategory.PERSONAL
        assert facts_by_text["Lives in Berlin"].confidence == 0.95

        assert "Working on Kubernetes" in facts_by_text
        assert facts_by_text["Working on Kubernetes"].category == FactCategory.CONTEXT
        assert facts_by_text["Working on Kubernetes"].confidence == 0.8

    def test_save_creates_directory_if_not_exists(self, tmp_path):
        """save() creates memory directory if it doesn't exist."""
        import shutil

        # Create a subdirectory that doesn't exist yet
        session_id = "mkdir-session"
        memory_dir = tmp_path / "subdir" / "memory"

        # Directory should not exist initially
        assert not memory_dir.exists()

        # Add fact - should create directory
        store = MemoryStore(session_id, memory_dir=str(memory_dir))
        store.load()
        store.add_fact("Test fact", FactCategory.CONTEXT, 0.7)

        # Directory and file should exist
        assert memory_dir.exists()
        assert store.file_path.exists()

    def test_save_updates_updated_at_timestamp(self, tmp_path):
        """save() updates the updated_at timestamp field."""
        session_id = "timestamp-session"
        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        # Add a fact
        store.add_fact("Test fact", FactCategory.CONTEXT, 0.7)

        # Load and check updated_at
        with open(store.file_path, "r") as f:
            data = json.load(f)

        assert "updated_at" in data
        assert data["updated_at"] is not None

    def test_save_preserves_session_id(self, tmp_path):
        """save() preserves session_id in JSON file."""
        session_id = "preserve-session-id"
        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        store.add_fact("Test fact", FactCategory.CONTEXT, 0.7)

        with open(store.file_path, "r") as f:
            data = json.load(f)

        assert data["session_id"] == session_id

    def test_multiple_add_facts_persist_correctly(self, tmp_path):
        """Multiple add_fact() calls persist all facts correctly."""
        session_id = "multi-facts-session"
        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        # Add multiple facts
        categories = [
            (FactCategory.PREFERENCE, "Prefers dark mode", 0.9),
            (FactCategory.PERSONAL, "Lives in Berlin", 0.95),
            (FactCategory.CONTEXT, "Working on Kubernetes", 0.8),
            (FactCategory.CORRECTION, "Corrected previous assumption", 0.85),
        ]

        for category, text, conf in categories:
            store.add_fact(text, category, conf)

        # Load fresh instance
        store2 = MemoryStore(session_id, memory_dir=str(tmp_path))
        store2.load()

        # All facts should be present
        assert len(store2._facts) == 4

        for category, text, conf in categories:
            found = any(
                f.text == text and f.category == category and f.confidence == conf
                for f in store2._facts
            )
            assert found, f"Fact '{text}' not found in loaded data"

    def test_json_file_is_human_readable(self, tmp_path):
        """JSON file is human-readable with proper indentation."""
        session_id = "readable-session"
        store = MemoryStore(session_id, memory_dir=str(tmp_path))
        store.load()

        store.add_fact("Test fact", FactCategory.PREFERENCE, 0.9)

        # Read as raw text
        with open(store.file_path, "r") as f:
            content = f.read()

        # Should be readable (has indentation)
        assert "\n" in content  # Multi-line
        assert "  " in content  # Has indentation

        # Should be valid JSON
        data = json.loads(content)
        assert isinstance(data, dict)

    def test_save_error_handling_does_not_crash(self, tmp_path):
        """save() handles errors gracefully (log only, no crash)."""
        import os
        from unittest.mock import patch

        session_id = "error-session"
        logger = MagicMock()
        store = MemoryStore(session_id, memory_dir=str(tmp_path), logger=logger)
        store.load()

        # Mock to raise OSError
        with patch.object(store, "file_path") as mock_path:
            mock_path.exists.return_value = False
            # Make parent.mkdir raise an error
            mock_path.parent.mkdir.side_effect = OSError("Permission denied")

            # Should not crash
            try:
                store.add_fact("Test fact", FactCategory.CONTEXT, 0.7)
            except Exception as e:
                pytest.fail(f"add_fact should not crash: {e}")
