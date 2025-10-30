"""KojiLogSink implementation for streaming container logs to Koji and persisting to filesystem.

This module provides a concrete implementation of the KojiLogSink protocol that:
- Streams stdout/stderr to Koji task logger
- Persists logs to `/mnt/koji/logs/<task_id>/container.log`
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO, Optional

from .base import KojiLogSink

logger = logging.getLogger(__name__)


class FileKojiLogSink:
    """KojiLogSink implementation that writes to both Koji logger and filesystem.

    Streams container stdout/stderr to a Koji logger instance and simultaneously
    persists all output to a log file for archival purposes.
    """

    def __init__(
        self,
        koji_logger: logging.Logger,
        log_file_path: Path,
    ) -> None:
        """Initialize KojiLogSink with logger and file destination.

        Args:
            koji_logger: Koji task logger instance (from self.logger in task handlers)
            log_file_path: Path to log file (e.g., `/mnt/koji/logs/<task_id>/container.log`)
        """
        self.koji_logger = koji_logger
        self.log_file_path = log_file_path
        self._file_handle: Optional[BinaryIO] = None

        # Ensure log directory exists
        try:
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
            # Open file in append mode (in case of multiple writes)
            self._file_handle = open(self.log_file_path, "ab")
        except Exception as exc:
            # Log error but don't fail - logging to Koji is more important
            logger.warning(
                "Failed to open log file %s: %s. Continuing with Koji-only logging.",
                self.log_file_path,
                exc,
            )
            self._file_handle = None

    def write_stdout(self, data: bytes) -> None:
        """Write stdout data to both Koji logger and file.

        Args:
            data: Bytes from container stdout
        """
        if not data:
            return

        # Decode for Koji logger (strip trailing newlines handled by logging)
        try:
            text = data.decode("utf-8", errors="replace")
            # Log each line separately to preserve formatting
            for line in text.splitlines():
                if line.strip():  # Skip empty lines
                    self.koji_logger.info(line)
        except Exception as exc:
            logger.warning("Error writing stdout to Koji logger: %s", exc)

        # Persist to file
        if self._file_handle:
            try:
                self._file_handle.write(data)
                self._file_handle.flush()
            except Exception as exc:
                logger.warning(
                    "Error writing stdout to log file %s: %s", self.log_file_path, exc
                )

    def write_stderr(self, data: bytes) -> None:
        """Write stderr data to both Koji logger and file.

        Args:
            data: Bytes from container stderr
        """
        if not data:
            return

        # Decode for Koji logger
        try:
            text = data.decode("utf-8", errors="replace")
            # Log each line separately to preserve formatting
            for line in text.splitlines():
                if line.strip():  # Skip empty lines
                    self.koji_logger.error(line)
        except Exception as exc:
            logger.warning("Error writing stderr to Koji logger: %s", exc)

        # Persist to file
        if self._file_handle:
            try:
                self._file_handle.write(data)
                self._file_handle.flush()
            except Exception as exc:
                logger.warning(
                    "Error writing stderr to log file %s: %s", self.log_file_path, exc
                )

    def close(self) -> None:
        """Close log file handle. Should be called when logging is complete."""
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass  # Ignore errors on close
            finally:
                self._file_handle = None

    def __enter__(self) -> "FileKojiLogSink":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures file is closed."""
        self.close()
