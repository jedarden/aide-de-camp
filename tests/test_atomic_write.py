"""
Unit tests for atomic_write utility.
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.utils.atomic_write import atomic_write


class TestAtomicWrite:
    """Test suite for atomic_write function."""

    def test_writes_new_file(self, tmp_path):
        """Test that atomic_write creates a new file with correct content."""
        filepath = tmp_path / "new_file.txt"
        content = "Hello, World!"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_overwrites_existing_file(self, tmp_path):
        """Test that atomic_write correctly overwrites an existing file."""
        filepath = tmp_path / "existing_file.txt"
        original_content = "Original content"
        new_content = "New content"

        # Create file with original content
        filepath.write_text(original_content)

        # Overwrite with new content
        atomic_write(filepath, new_content)

        assert filepath.read_text() == new_content

    def test_creates_parent_directories(self, tmp_path):
        """Test that atomic_write creates parent directories if needed."""
        filepath = tmp_path / "deep" / "nested" / "file.txt"
        content = "Content in nested path"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_binary_mode(self, tmp_path):
        """Test that atomic_write works in binary mode."""
        filepath = tmp_path / "binary_file.bin"
        content = b"\x00\x01\x02\x03\xff\xfe"

        atomic_write(filepath, content, mode='wb')

        assert filepath.exists()
        assert filepath.read_bytes() == content

    def test_empty_content(self, tmp_path):
        """Test that atomic_write handles empty content correctly."""
        filepath = tmp_path / "empty.txt"
        atomic_write(filepath, "")
        assert filepath.exists()
        assert filepath.read_text() == ""

    def test_unicode_content(self, tmp_path):
        """Test that atomic_write handles Unicode characters correctly."""
        filepath = tmp_path / "unicode.txt"
        content = "Hello 世界 🌍"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_type_error_text_mode_with_bytes(self, tmp_path):
        """Test that passing bytes to text mode raises TypeError."""
        filepath = tmp_path / "test.txt"
        content = b"bytes content"

        with pytest.raises(TypeError, match="Text mode requires str content"):
            atomic_write(filepath, content, mode='w')

    def test_type_error_binary_mode_with_str(self, tmp_path):
        """Test that passing str to binary mode raises TypeError."""
        filepath = tmp_path / "test.bin"
        content = "string content"

        with pytest.raises(TypeError, match="Binary mode requires bytes content"):
            atomic_write(filepath, content, mode='wb')

    def test_permission_error_on_readonly_directory(self, tmp_path):
        """Test that permission error is raised when directory is not writable."""
        # Create a read-only directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only

        filepath = readonly_dir / "file.txt"

        with pytest.raises(PermissionError):
            atomic_write(filepath, "content")

    def test_atomicity_on_same_filesystem(self, tmp_path):
        """Test that writes appear atomic (all-or-nothing)."""
        filepath = tmp_path / "atomic_test.txt"
        original_content = "Original"
        new_content = "New" * 1000  # Larger content to test actual rename

        # Write original content
        filepath.write_text(original_content)

        # Perform atomic overwrite
        atomic_write(filepath, new_content)

        # Verify file has complete new content (not partial)
        result = filepath.read_text()
        assert result == new_content
        assert len(result) == len(new_content)

    def test_pathlib_path_support(self, tmp_path):
        """Test that atomic_write accepts pathlib.Path objects."""
        filepath = tmp_path / "pathlib_test.txt"
        content = "Pathlib support test"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_string_path_support(self, tmp_path):
        """Test that atomic_write accepts string paths."""
        filepath = str(tmp_path / "string_path.txt")
        content = "String path support test"

        atomic_write(filepath, content)

        assert Path(filepath).exists()
        assert Path(filepath).read_text() == content
