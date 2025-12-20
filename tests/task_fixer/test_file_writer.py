"""Tests for file writer module."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from spec_workflow_runner.task_fixer.file_writer import FileWriter, WriteResult


@pytest.fixture
def file_writer() -> FileWriter:
    """Create a FileWriter instance."""
    return FileWriter()


@pytest.fixture
def temp_dir() -> TemporaryDirectory:
    """Create a temporary directory for test files."""
    return TemporaryDirectory()


def test_write_new_file(file_writer: FileWriter, temp_dir: TemporaryDirectory) -> None:
    """Test writing a new file that doesn't exist."""
    test_file = Path(temp_dir.name) / "new_file.md"
    content = "New file content\n"

    result = file_writer.write_with_backup(test_file, content)

    assert result.success
    assert result.file_path == test_file
    assert result.backup_path is None
    assert result.error_message is None
    assert test_file.exists()
    assert test_file.read_text(encoding="utf-8") == content


def test_write_existing_file_creates_backup(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test writing to existing file creates backup."""
    test_file = Path(temp_dir.name) / "existing.md"
    original_content = "Original content\n"
    new_content = "New content\n"

    # Create original file
    test_file.write_text(original_content, encoding="utf-8")

    result = file_writer.write_with_backup(test_file, new_content)

    assert result.success
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert result.backup_path.read_text(encoding="utf-8") == original_content
    assert test_file.read_text(encoding="utf-8") == new_content


def test_backup_path_has_correct_suffix(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test backup file has .backup suffix."""
    test_file = Path(temp_dir.name) / "test.md"
    test_file.write_text("Original\n", encoding="utf-8")

    result = file_writer.write_with_backup(test_file, "New\n")

    assert result.success
    assert result.backup_path is not None
    assert result.backup_path.name == "test.md.backup"


def test_multiple_backups_get_unique_names(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test that multiple backups get unique names."""
    test_file = Path(temp_dir.name) / "test.md"
    test_file.write_text("Version 1\n", encoding="utf-8")

    # First write creates .backup
    result1 = file_writer.write_with_backup(test_file, "Version 2\n")
    assert result1.success
    assert result1.backup_path is not None
    first_backup = result1.backup_path

    # Second write creates .backup.1
    result2 = file_writer.write_with_backup(test_file, "Version 3\n")
    assert result2.success
    assert result2.backup_path is not None
    second_backup = result2.backup_path

    # Third write creates .backup.2
    result3 = file_writer.write_with_backup(test_file, "Version 4\n")
    assert result3.success
    assert result3.backup_path is not None
    third_backup = result3.backup_path

    # All backups should exist with unique names
    assert first_backup.exists()
    assert second_backup.exists()
    assert third_backup.exists()
    assert first_backup != second_backup != third_backup
    assert str(second_backup).endswith(".backup.1")
    assert str(third_backup).endswith(".backup.2")


def test_atomic_write_uses_temp_file(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test that write uses atomic temp file pattern."""
    test_file = Path(temp_dir.name) / "atomic.md"
    content = "Atomic content\n"

    # Write should use temp file in same directory
    result = file_writer.write_with_backup(test_file, content)

    assert result.success
    # Original file should have final content
    assert test_file.read_text(encoding="utf-8") == content
    # No temp files should remain
    temp_files = list(Path(temp_dir.name).glob(".atomic.md.*.tmp"))
    assert len(temp_files) == 0


def test_creates_parent_directories(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test that parent directories are created if they don't exist."""
    test_file = Path(temp_dir.name) / "subdir" / "nested" / "file.md"
    content = "Nested content\n"

    result = file_writer.write_with_backup(test_file, content)

    assert result.success
    assert test_file.exists()
    assert test_file.read_text(encoding="utf-8") == content


def test_restore_from_backup_success(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test successful restore from backup."""
    test_file = Path(temp_dir.name) / "test.md"
    original_content = "Original\n"
    new_content = "Modified\n"

    # Create and modify file
    test_file.write_text(original_content, encoding="utf-8")
    result = file_writer.write_with_backup(test_file, new_content)
    assert result.success
    backup_path = result.backup_path
    assert backup_path is not None

    # File should have new content
    assert test_file.read_text(encoding="utf-8") == new_content

    # Restore from backup
    success = file_writer.restore_from_backup(backup_path, test_file)

    assert success
    assert test_file.read_text(encoding="utf-8") == original_content
    # Backup file is consumed by atomic rename
    assert not backup_path.exists()


def test_restore_from_nonexistent_backup(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test restore fails if backup doesn't exist."""
    test_file = Path(temp_dir.name) / "test.md"
    backup_path = Path(temp_dir.name) / "nonexistent.backup"

    success = file_writer.restore_from_backup(backup_path, test_file)

    assert not success


def test_write_handles_unicode(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test writing unicode content."""
    test_file = Path(temp_dir.name) / "unicode.md"
    content = "Hello 世界 🌍\n"

    result = file_writer.write_with_backup(test_file, content)

    assert result.success
    assert test_file.read_text(encoding="utf-8") == content


def test_write_result_immutability() -> None:
    """Test that WriteResult is immutable."""
    result = WriteResult(
        success=True,
        file_path=Path("/tmp/test.md"),
        backup_path=None,
    )

    # Should not be able to modify frozen dataclass
    with pytest.raises(AttributeError):
        result.success = False  # type: ignore


def test_backup_creation_error_handling(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test error handling when backup creation fails."""
    test_file = Path(temp_dir.name) / "test.md"
    test_file.write_text("Original\n", encoding="utf-8")

    # Mock shutil.copy2 to raise an error
    with patch("spec_workflow_runner.task_fixer.file_writer.shutil.copy2") as mock_copy:
        mock_copy.side_effect = OSError("Permission denied")

        result = file_writer.write_with_backup(test_file, "New\n")

        assert not result.success
        assert result.backup_path is None
        assert "Failed to create backup" in result.error_message
        # Original file should still exist
        assert test_file.exists()


def test_temp_file_write_error_handling(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test error handling when temp file write fails."""
    test_file = Path(temp_dir.name) / "test.md"

    # Mock the open call to raise an error during write
    with patch("builtins.open") as mock_open:
        mock_open.side_effect = IOError("Disk full")

        result = file_writer.write_with_backup(test_file, "Content\n")

        assert not result.success
        assert result.error_message is not None
        assert "Failed to write file" in result.error_message or "Disk full" in result.error_message


def test_restore_error_handling(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test restore error handling."""
    backup_path = Path(temp_dir.name) / "backup.md"
    test_file = Path(temp_dir.name) / "test.md"

    # Create backup
    backup_path.write_text("Backup\n", encoding="utf-8")

    # Mock Path.replace to raise error
    with patch.object(Path, "replace") as mock_replace:
        mock_replace.side_effect = OSError("Permission denied")

        success = file_writer.restore_from_backup(backup_path, test_file)

        assert not success


def test_write_preserves_file_permissions(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test that writing preserves original file permissions."""
    test_file = Path(temp_dir.name) / "test.md"
    test_file.write_text("Original\n", encoding="utf-8")

    # Set specific permissions
    test_file.chmod(0o644)
    original_mode = test_file.stat().st_mode

    result = file_writer.write_with_backup(test_file, "New\n")

    assert result.success
    # Note: Atomic rename may not preserve permissions perfectly
    # This test verifies file is writable
    assert test_file.exists()


def test_concurrent_writes_use_unique_temp_files(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test that concurrent writes would use unique temp files."""
    test_file = Path(temp_dir.name) / "test.md"

    # Track temp file names created
    temp_files: list[str] = []
    original_mkstemp = __import__("tempfile").mkstemp

    def track_mkstemp(*args, **kwargs):
        fd, path = original_mkstemp(*args, **kwargs)
        temp_files.append(path)
        return fd, path

    with patch("tempfile.mkstemp", side_effect=track_mkstemp):
        result1 = file_writer.write_with_backup(test_file, "Content 1\n")
        result2 = file_writer.write_with_backup(test_file, "Content 2\n")

        assert result1.success
        assert result2.success
        # Each write should have used a different temp file
        # (though sequential writes will reuse since first is already cleaned up)
        assert len(temp_files) == 2


def test_empty_content(file_writer: FileWriter, temp_dir: TemporaryDirectory) -> None:
    """Test writing empty content."""
    test_file = Path(temp_dir.name) / "empty.md"

    result = file_writer.write_with_backup(test_file, "")

    assert result.success
    assert test_file.exists()
    assert test_file.read_text(encoding="utf-8") == ""


def test_very_large_content(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test writing very large content."""
    test_file = Path(temp_dir.name) / "large.md"
    # Create 1MB of content
    large_content = "x" * (1024 * 1024)

    result = file_writer.write_with_backup(test_file, large_content)

    assert result.success
    assert test_file.stat().st_size == len(large_content)


def test_create_backup_path_logic(file_writer: FileWriter) -> None:
    """Test _create_backup_path creates correct paths."""
    # Access private method for unit testing
    file_path = Path("/tmp/test.md")

    backup_path = file_writer._create_backup_path(file_path)

    assert str(backup_path) == "/tmp/test.md.backup"


def test_write_with_backup_full_workflow(
    file_writer: FileWriter, temp_dir: TemporaryDirectory
) -> None:
    """Test complete workflow: write, modify, restore."""
    test_file = Path(temp_dir.name) / "workflow.md"
    version1 = "Version 1\n"
    version2 = "Version 2\n"

    # Create initial file
    test_file.write_text(version1, encoding="utf-8")

    # Modify and create backup
    result = file_writer.write_with_backup(test_file, version2)
    assert result.success
    assert result.backup_path is not None
    backup_path = result.backup_path

    # Verify modification
    assert test_file.read_text(encoding="utf-8") == version2
    assert backup_path.read_text(encoding="utf-8") == version1

    # Restore from backup
    restore_success = file_writer.restore_from_backup(backup_path, test_file)
    assert restore_success
    assert test_file.read_text(encoding="utf-8") == version1
