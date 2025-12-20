"""File writer with atomic operations and backup support."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WriteResult:
    """Result of writing a file with backup."""

    success: bool
    file_path: Path
    backup_path: Path | None
    error_message: str | None = None


class FileWriter:
    """Writes files atomically with backup creation."""

    def write_with_backup(self, file_path: Path, content: str) -> WriteResult:
        """Write content to file atomically with backup creation.

        Uses atomic write pattern: write to temp file, create backup, then rename.
        This ensures no partial writes and allows rollback.

        Args:
            file_path: Path to file to write
            content: Content to write

        Returns:
            WriteResult with success status and backup path
        """
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create backup if file exists
            backup_path: Path | None = None
            if file_path.exists():
                backup_path = self._create_backup_path(file_path)
                try:
                    shutil.copy2(file_path, backup_path)
                except OSError as err:
                    return WriteResult(
                        success=False,
                        file_path=file_path,
                        backup_path=None,
                        error_message=f"Failed to create backup: {err}",
                    )

            # Write to temporary file first (atomic operation)
            temp_fd, temp_path_str = tempfile.mkstemp(
                dir=file_path.parent,
                prefix=f".{file_path.name}.",
                suffix=".tmp",
                text=True,
            )

            try:
                # Write content to temp file
                with open(temp_fd, "w", encoding="utf-8") as f:
                    f.write(content)

                # Atomic rename (replaces original file)
                temp_path = Path(temp_path_str)
                temp_path.replace(file_path)

                return WriteResult(
                    success=True,
                    file_path=file_path,
                    backup_path=backup_path,
                )

            except Exception as err:
                # Clean up temp file on error
                try:
                    Path(temp_path_str).unlink(missing_ok=True)
                except Exception:
                    pass

                return WriteResult(
                    success=False,
                    file_path=file_path,
                    backup_path=backup_path,
                    error_message=f"Failed to write file: {err}",
                )

        except Exception as err:
            return WriteResult(
                success=False,
                file_path=file_path,
                backup_path=None,
                error_message=f"Unexpected error: {err}",
            )

    def restore_from_backup(self, backup_path: Path, original_path: Path) -> bool:
        """Restore original file from backup.

        Args:
            backup_path: Path to backup file
            original_path: Path to restore to

        Returns:
            True if restore successful, False otherwise
        """
        try:
            if not backup_path.exists():
                return False

            # Use atomic rename for restore
            backup_path.replace(original_path)
            return True

        except Exception:
            return False

    def _create_backup_path(self, file_path: Path) -> Path:
        """Create a unique backup path for the given file.

        Args:
            file_path: Path to create backup for

        Returns:
            Path for backup file with .backup suffix (unique if exists)
        """
        backup_path = file_path.with_suffix(file_path.suffix + ".backup")

        # If backup already exists, add a number to make it unique
        counter = 1
        while backup_path.exists():
            backup_path = file_path.with_suffix(f"{file_path.suffix}.backup.{counter}")
            counter += 1

        return backup_path
