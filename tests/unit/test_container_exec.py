"""Unit tests for container exec() and copy_to() methods."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from koji_adjutant.container.interface import ContainerError, ContainerHandle, InMemoryLogSink
from koji_adjutant.container.podman_manager import PodmanManager


class TestPodmanManagerExec:
    """Test exec() method of PodmanManager."""

    def test_exec_success(self):
        """Test successful command execution."""
        manager = PodmanManager()
        handle = ContainerHandle(container_id="test-container-id")
        sink = InMemoryLogSink()

        # Mock container
        mock_container = MagicMock()
        mock_chunk1 = (b"stdout output", None)
        mock_chunk2 = (None, b"stderr output")
        mock_chunk3 = (b"more stdout", None)

        # Set up exec_run to return generator for stream=True, tuple for stream=False
        def exec_run_side_effect(cmd, environment=None, stream=False, demux=False):
            if stream:
                return iter([mock_chunk1, mock_chunk2, mock_chunk3])
            else:
                return (0, b"output")

        mock_container.exec_run.side_effect = exec_run_side_effect

        with patch.object(manager, "_ensure_client"):
            manager._client = MagicMock()
            manager._client.containers.get.return_value = mock_container

            exit_code = manager.exec(handle, ["/bin/echo", "test"], sink)

            assert exit_code == 0
            assert b"stdout output" in sink.stdout
            assert b"more stdout" in sink.stdout
            assert b"stderr output" in sink.stderr

    def test_exec_failure(self):
        """Test command execution with non-zero exit code."""
        manager = PodmanManager()
        handle = ContainerHandle(container_id="test-container-id")
        sink = InMemoryLogSink()

        mock_container = MagicMock()

        def exec_run_side_effect(cmd, environment=None, stream=False, demux=False):
            if stream:
                return iter([(b"error output", None)])
            else:
                return (1, b"error output")

        mock_container.exec_run.side_effect = exec_run_side_effect

        with patch.object(manager, "_ensure_client"):
            manager._client = MagicMock()
            manager._client.containers.get.return_value = mock_container

            exit_code = manager.exec(handle, ["/bin/false"], sink)

            assert exit_code == 1

    def test_exec_container_not_found(self):
        """Test exec() raises ContainerError when container not found."""
        manager = PodmanManager()
        handle = ContainerHandle(container_id="nonexistent")
        sink = InMemoryLogSink()

        from podman.errors import NotFound

        with patch.object(manager, "_ensure_client"):
            manager._client = MagicMock()
            manager._client.containers.get.side_effect = NotFound("container not found")

            with pytest.raises(ContainerError) as exc_info:
                manager.exec(handle, ["/bin/echo", "test"], sink)

            assert "container not found" in str(exc_info.value).lower()

    def test_exec_with_environment(self):
        """Test exec() with custom environment variables."""
        manager = PodmanManager()
        handle = ContainerHandle(container_id="test-container-id")
        sink = InMemoryLogSink()
        env = {"TEST_VAR": "test_value"}

        mock_container = MagicMock()

        def exec_run_side_effect(cmd, environment=None, stream=False, demux=False):
            if stream:
                return iter([(b"output", None)])
            else:
                # Verify environment was passed
                assert environment == env
                return (0, b"output")

        mock_container.exec_run.side_effect = exec_run_side_effect

        with patch.object(manager, "_ensure_client"):
            manager._client = MagicMock()
            manager._client.containers.get.return_value = mock_container

            exit_code = manager.exec(handle, ["/bin/env"], sink, environment=env)

            assert exit_code == 0


class TestPodmanManagerCopyTo:
    """Test copy_to() method of PodmanManager."""

    def test_copy_to_success(self, tmp_path):
        """Test successful file copy to container."""
        manager = PodmanManager()
        handle = ContainerHandle(container_id="test-container-id")

        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_container = MagicMock()
        mock_container.put_archive.return_value = None

        with patch.object(manager, "_ensure_client"):
            manager._client = MagicMock()
            manager._client.containers.get.return_value = mock_container

            manager.copy_to(handle, test_file, "/etc/test.txt")

            # Verify put_archive was called
            assert mock_container.put_archive.called
            call_args = mock_container.put_archive.call_args
            assert call_args[1]["path"] == "/etc"
            assert isinstance(call_args[1]["data"], bytes)

    def test_copy_to_file_not_found(self):
        """Test copy_to() raises ContainerError when source file doesn't exist."""
        manager = PodmanManager()
        handle = ContainerHandle(container_id="test-container-id")
        nonexistent_file = Path("/nonexistent/file.txt")

        with patch.object(manager, "_ensure_client"):
            manager._client = MagicMock()

            with pytest.raises(ContainerError) as exc_info:
                manager.copy_to(handle, nonexistent_file, "/etc/file.txt")

            assert "does not exist" in str(exc_info.value).lower()

    def test_copy_to_directory_not_file(self, tmp_path):
        """Test copy_to() raises ContainerError when source is a directory."""
        manager = PodmanManager()
        handle = ContainerHandle(container_id="test-container-id")
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        with patch.object(manager, "_ensure_client"):
            manager._client = MagicMock()

            with pytest.raises(ContainerError) as exc_info:
                manager.copy_to(handle, test_dir, "/etc/testdir")

            assert "not a file" in str(exc_info.value).lower()

    def test_copy_to_container_not_found(self, tmp_path):
        """Test copy_to() raises ContainerError when container not found."""
        manager = PodmanManager()
        handle = ContainerHandle(container_id="nonexistent")
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        from podman.errors import NotFound

        with patch.object(manager, "_ensure_client"):
            manager._client = MagicMock()
            manager._client.containers.get.side_effect = NotFound("container not found")

            with pytest.raises(ContainerError) as exc_info:
                manager.copy_to(handle, test_file, "/etc/test.txt")

            assert "container not found" in str(exc_info.value).lower()

    def test_copy_to_api_error(self, tmp_path):
        """Test copy_to() handles API errors."""
        manager = PodmanManager()
        handle = ContainerHandle(container_id="test-container-id")
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        from podman.errors import APIError

        mock_container = MagicMock()
        mock_container.put_archive.side_effect = APIError("API error")

        with patch.object(manager, "_ensure_client"):
            manager._client = MagicMock()
            manager._client.containers.get.return_value = mock_container

            with pytest.raises(ContainerError) as exc_info:
                manager.copy_to(handle, test_file, "/etc/test.txt")

            assert "failed to copy file" in str(exc_info.value).lower()
