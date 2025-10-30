"""Integration tests for exec() pattern (Phase 2.2)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from koji_adjutant.container.interface import ContainerHandle, InMemoryLogSink
from koji_adjutant.container.podman_manager import PodmanManager

logger = logging.getLogger(__name__)

# Test if podman is available
try:
    from podman import PodmanClient
    PODMAN_AVAILABLE = True
except Exception:
    PodmanClient = None  # type: ignore[assignment]
    PODMAN_AVAILABLE = False

# Test image (should be available in test environment)
TEST_IMAGE = "docker.io/almalinux/9-minimal:latest"

# Marker for tests requiring podman
requires_podman = pytest.mark.skipif(
    not PODMAN_AVAILABLE,
    reason="Podman Python API not available",
)


@pytest.fixture
def podman_manager():
    """Create PodmanManager instance for testing."""
    return PodmanManager()


@pytest.fixture
def podman_available():
    """Check if Podman is available and accessible."""
    if not PODMAN_AVAILABLE:
        pytest.skip("Podman Python API not available")

    # Try to create a client and verify it works
    try:
        client = PodmanClient()
        # Simple check: list containers (should not fail)
        client.containers.list(all=True)
        return True
    except Exception as e:
        pytest.skip(f"Podman not accessible: {e}")


@pytest.fixture
def ensure_image_available(podman_manager, podman_available):
    """Ensure test image is available."""
    try:
        podman_manager.ensure_image_available(TEST_IMAGE)
        yield
    except Exception as exc:
        pytest.skip(f"Could not ensure image availability: {exc}")


@requires_podman
def test_exec_basic_command(podman_manager, ensure_image_available, tmp_path):
    """Test basic exec() command execution in running container."""
    manager = podman_manager
    sink = InMemoryLogSink()

    from koji_adjutant.container.interface import ContainerSpec

    # Create container with sleep
    spec = ContainerSpec(
        image=TEST_IMAGE,
        command=["/bin/sleep", "infinity"],
        environment={},
        remove_after_exit=True,
    )

    handle = manager.create(spec)
    manager.start(handle)
    manager.stream_logs(handle, sink, follow=False)

    try:
        # Execute a simple command
        exit_code = manager.exec(handle, ["/bin/echo", "hello", "world"], sink)

        assert exit_code == 0
        output = sink.stdout.decode("utf-8", errors="replace")
        assert "hello world" in output or "hello" in output

    finally:
        manager.remove(handle, force=True)


@requires_podman
def test_copy_to_basic(podman_manager, ensure_image_available, tmp_path):
    """Test copy_to() basic file copy."""
    manager = podman_manager
    sink = InMemoryLogSink()

    from koji_adjutant.container.interface import ContainerSpec

    # Create test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content\n")

    # Create container with sleep
    spec = ContainerSpec(
        image=TEST_IMAGE,
        command=["/bin/sleep", "infinity"],
        environment={},
        remove_after_exit=True,
    )

    handle = manager.create(spec)
    manager.start(handle)
    manager.stream_logs(handle, sink, follow=False)

    try:
        # Copy file to container
        manager.copy_to(handle, test_file, "/tmp/test.txt")

        # Verify file exists by executing cat
        exit_code = manager.exec(handle, ["/bin/cat", "/tmp/test.txt"], sink)

        assert exit_code == 0
        output = sink.stdout.decode("utf-8", errors="replace")
        assert "test content" in output

    finally:
        manager.remove(handle, force=True)


@requires_podman
def test_exec_pattern_full_flow(podman_manager, ensure_image_available, tmp_path):
    """Test full exec pattern flow: copy configs, exec init commands, exec build."""
    manager = podman_manager
    sink = InMemoryLogSink()

    from koji_adjutant.container.interface import ContainerSpec

    # Create config files
    repo_file = tmp_path / "koji.repo"
    repo_file.write_text("[koji-repo]\nbaseurl=file:///mnt/koji/repos\nenabled=1\n")

    macros_file = tmp_path / "macros.koji"
    macros_file.write_text("%dist .almalinux10\n%_topdir /work/12345\n")

    # Create container with sleep
    spec = ContainerSpec(
        image=TEST_IMAGE,
        command=["/bin/sleep", "infinity"],
        environment={"TEST_VAR": "test_value"},
        remove_after_exit=True,
    )

    handle = manager.create(spec)
    manager.start(handle)
    manager.stream_logs(handle, sink, follow=False)

    try:
        # Step 1: Copy config files
        manager.copy_to(handle, repo_file, "/etc/yum.repos.d/koji.repo")
        manager.copy_to(handle, macros_file, "/etc/rpm/macros.koji")

        # Step 2: Verify files exist
        exit_code = manager.exec(handle, ["/bin/test", "-f", "/etc/yum.repos.d/koji.repo"], sink)
        assert exit_code == 0

        exit_code = manager.exec(handle, ["/bin/test", "-f", "/etc/rpm/macros.koji"], sink)
        assert exit_code == 0

        # Step 3: Execute init command (mkdir)
        exit_code = manager.exec(
            handle,
            ["mkdir", "-p", "/work/12345/work", "/work/12345/build", "/work/12345/result"],
            sink,
        )
        assert exit_code == 0

        # Step 4: Verify directories created
        exit_code = manager.exec(handle, ["/bin/test", "-d", "/work/12345/work"], sink)
        assert exit_code == 0

        # Step 5: Execute command with environment
        exit_code = manager.exec(
            handle,
            ["/bin/sh", "-c", "echo $TEST_VAR"],
            sink,
            environment={"TEST_VAR": "modified_value"},
        )
        assert exit_code == 0
        output = sink.stdout.decode("utf-8", errors="replace")
        assert "modified_value" in output

    finally:
        manager.remove(handle, force=True)


@requires_podman
def test_exec_error_handling(podman_manager, ensure_image_available, tmp_path):
    """Test error handling in exec pattern."""
    manager = podman_manager
    sink = InMemoryLogSink()

    from koji_adjutant.container.interface import ContainerSpec

    spec = ContainerSpec(
        image=TEST_IMAGE,
        command=["/bin/sleep", "infinity"],
        environment={},
        remove_after_exit=True,
    )

    handle = manager.create(spec)
    manager.start(handle)
    manager.stream_logs(handle, sink, follow=False)

    try:
        # Execute failing command
        exit_code = manager.exec(handle, ["/bin/false"], sink)
        assert exit_code != 0

        # Execute command that doesn't exist
        exit_code = manager.exec(handle, ["/nonexistent/command"], sink)
        assert exit_code != 0

    finally:
        manager.remove(handle, force=True)


@requires_podman
def test_copy_to_error_handling(podman_manager, ensure_image_available, tmp_path):
    """Test error handling in copy_to."""
    manager = podman_manager
    sink = InMemoryLogSink()

    from koji_adjutant.container.interface import ContainerError, ContainerSpec

    spec = ContainerSpec(
        image=TEST_IMAGE,
        command=["/bin/sleep", "infinity"],
        environment={},
        remove_after_exit=True,
    )

    handle = manager.create(spec)
    manager.start(handle)
    manager.stream_logs(handle, sink, follow=False)

    try:
        # Try to copy nonexistent file
        nonexistent = tmp_path / "nonexistent.txt"
        with pytest.raises(ContainerError):
            manager.copy_to(handle, nonexistent, "/tmp/test.txt")

        # Try to copy directory (should fail)
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        with pytest.raises(ContainerError):
            manager.copy_to(handle, test_dir, "/tmp/testdir")

    finally:
        manager.remove(handle, force=True)
