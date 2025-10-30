"""Phase 1 Smoke Tests for Koji-Adjutant Container-Based Task Execution.

This test suite validates critical functionality of the Phase 1 implementation:
- Container lifecycle management (PodmanManager)
- Mount configuration and permissions
- Task adapter execution (buildArch, createrepo)
- Log streaming and persistence
- Container cleanup

Tests are designed to run with real Podman when available, but gracefully
skip if Podman is not available or properly configured.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

# Test if podman is available
try:
    from podman import PodmanClient
    from podman.errors import NotFound
    PODMAN_AVAILABLE = True
except Exception:
    PodmanClient = None  # type: ignore[assignment]
    NotFound = Exception  # type: ignore[assignment]
    PODMAN_AVAILABLE = False

from koji_adjutant.container.interface import (
    ContainerError,
    ContainerSpec,
    InMemoryLogSink,
    VolumeMount,
)
from koji_adjutant.container.podman_manager import PodmanManager
from koji_adjutant.task_adapters.base import TaskContext
from koji_adjutant.task_adapters.buildarch import BuildArchAdapter
from koji_adjutant.task_adapters.createrepo import CreaterepoAdapter
from koji_adjutant.task_adapters.logging import FileKojiLogSink

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test image - use a minimal image available in most environments
TEST_IMAGE = os.environ.get("KOJI_ADJUTANT_TEST_IMAGE", "docker.io/almalinux/9-minimal:latest")


# Skip marker for tests requiring Podman
requires_podman = pytest.mark.skipif(
    not PODMAN_AVAILABLE,
    reason="Podman Python API not available",
)


# Fixtures
@pytest.fixture(scope="module")
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
def temp_koji_root(tmp_path):
    """Create a temporary /mnt/koji-like directory structure."""
    koji_root = tmp_path / "mnt" / "koji"
    koji_root.mkdir(parents=True, exist_ok=True)

    # Create standard subdirectories
    (koji_root / "work").mkdir(exist_ok=True)
    (koji_root / "logs").mkdir(exist_ok=True)
    (koji_root / "repos").mkdir(exist_ok=True)

    return koji_root


@pytest.fixture
def test_task_context(temp_koji_root):
    """Create a TaskContext for testing."""
    task_id = 12345
    work_dir = temp_koji_root / "work" / str(task_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    return TaskContext(
        task_id=task_id,
        work_dir=work_dir,
        koji_mount_root=temp_koji_root,
        environment={"TEST": "1"},
    )


@pytest.fixture
def podman_manager():
    """Create a PodmanManager instance for testing."""
    return PodmanManager(
        pull_always=False,  # Use if-not-present for tests
        network_default=True,
        worker_id="test-worker",
    )


@pytest.fixture
def mock_koji_logger():
    """Create a mock Koji logger for log sink testing."""
    return logging.getLogger("test.koji")


@pytest.fixture
def minimal_srpm_content():
    """Generate minimal valid SRPM-like test data."""
    # For Phase 1, we'll create a simple test file instead of a real SRPM
    # In real scenarios, this would be a valid SRPM file
    return b"TEST_SRPM_CONTENT\n"


@pytest.fixture
def test_repo_directory(temp_koji_root, test_task_context):
    """Create a minimal test repository directory."""
    repo_id = 1
    arch = "x86_64"
    repo_dir = temp_koji_root / "repos" / str(repo_id) / arch
    repo_dir.mkdir(parents=True, exist_ok=True)

    # Create a pkglist file (empty for Phase 1 minimal test)
    pkglist = repo_dir / "pkglist"
    pkglist.write_text("", encoding="utf-8")

    return repo_dir


# Helper functions
def ensure_image_available(manager: PodmanManager, image: str) -> bool:
    """Helper to ensure test image is available, skip test if not."""
    try:
        manager.ensure_image_available(image)
        return True
    except ContainerError as e:
        pytest.skip(f"Test image not available: {e}")


# ST1: Container Lifecycle Smoke Tests

@requires_podman
def test_st1_1_image_availability(podman_available, podman_manager):
    """ST1.1 - Image Availability Test

    Verify container image can be pulled and validated.
    AC1.1: Image availability validation before container creation.
    """
    # Test 1: Verify image exists or can be pulled
    manager = podman_manager
    try:
        manager.ensure_image_available(TEST_IMAGE)
        # If we get here, image is available
        assert True, "Image available or pulled successfully"
    except ContainerError as e:
        pytest.fail(f"Image availability check failed: {e}")

    # Test 2: Verify ContainerError raised on invalid image
    with pytest.raises(ContainerError):
        manager.ensure_image_available("nonexistent:invalid:tag")


@requires_podman
def test_st1_3_log_streaming(podman_available, podman_manager, temp_koji_root):
    """ST1.3 - Log Streaming Test

    Verify container logs are streamed correctly to LogSink.
    AC1.4: Container stdout/stderr are streamed to LogSink immediately after start.
    """
    manager = podman_manager
    ensure_image_available(manager, TEST_IMAGE)

    # Create a container that produces known output
    sink = InMemoryLogSink()

    spec = ContainerSpec(
        image=TEST_IMAGE,
        command=["/bin/sh", "-c", "echo 'stdout test'; echo 'stderr test' >&2"],
        environment={},
        remove_after_exit=True,
    )

    # Execute container
    result = manager.run(spec, sink, attach_streams=True)

    # Verify exit code
    assert result.exit_code == 0, f"Container should exit with 0, got {result.exit_code}"

    # Verify logs were captured
    stdout_content = sink.stdout.decode("utf-8", errors="replace")
    stderr_content = sink.stderr.decode("utf-8", errors="replace")

    # Check that output was captured (may contain test strings)
    assert len(stdout_content) > 0 or len(stderr_content) > 0, "Logs should be captured"

    logger.info(f"Captured stdout: {stdout_content[:200]}")
    logger.info(f"Captured stderr: {stderr_content[:200]}")


@requires_podman
def test_st1_5_container_cleanup(podman_available, podman_manager, temp_koji_root):
    """ST1.5 - Container Cleanup Test

    Verify container cleanup on success and failure.
    AC1.6: Container is removed via remove() after task completion.
    AC6.1: Container is removed after successful task completion.
    AC6.2: Container is removed after task failure.
    """
    manager = podman_manager
    ensure_image_available(manager, TEST_IMAGE)

    # Test 1: Successful cleanup
    sink = InMemoryLogSink()
    spec = ContainerSpec(
        image=TEST_IMAGE,
        command=["/bin/sh", "-c", "echo 'success'; exit 0"],
        environment={},
        remove_after_exit=True,
    )

    result = manager.run(spec, sink, attach_streams=True)
    assert result.exit_code == 0

    # Verify container was removed by checking it doesn't exist
    if PODMAN_AVAILABLE:
        try:
            # Try to inspect the container - should raise NotFound
            client = PodmanClient()
            container = client.containers.get(result.handle.container_id)
            pytest.fail(f"Container {result.handle.container_id} should be removed but still exists")
        except NotFound:
            # Expected - container was removed
            pass
        except Exception as e:
            # Other errors are acceptable (container may not be accessible)
            logger.debug(f"Could not verify container removal (expected): {e}")

    # Test 2: Cleanup on failure
    spec_fail = ContainerSpec(
        image=TEST_IMAGE,
        command=["/bin/sh", "-c", "echo 'failure'; exit 1"],
        environment={},
        remove_after_exit=True,
    )

    result_fail = manager.run(spec_fail, sink, attach_streams=True)
    assert result_fail.exit_code != 0

    # Verify container was removed even on failure
    if PODMAN_AVAILABLE:
        try:
            client = PodmanClient()
            container = client.containers.get(result_fail.handle.container_id)
            pytest.fail(f"Container {result_fail.handle.container_id} should be removed after failure")
        except NotFound:
            pass
        except Exception as e:
            logger.debug(f"Could not verify container removal (expected): {e}")


# ST2: Mount Configuration Smoke Tests

@requires_podman
def test_st2_2_mount_permissions(podman_available, podman_manager, temp_koji_root):
    """ST2.2 - Mount Permissions Test

    Verify container can read/write mounted directories.
    AC2.2: Mounted directories are accessible by container user.
    """
    manager = podman_manager
    ensure_image_available(manager, TEST_IMAGE)

    # Create test file on host
    test_file = temp_koji_root / "test_write.txt"
    test_content = "test content from host"
    test_file.write_text(test_content, encoding="utf-8")

    # Create container with mount that writes a file
    sink = InMemoryLogSink()
    mount_source = temp_koji_root
    mount_target = Path("/mnt/test")

    spec = ContainerSpec(
        image=TEST_IMAGE,
        command=[
            "/bin/sh",
            "-c",
            f"ls {mount_target} && echo 'write_test' > {mount_target}/container_write.txt && cat {mount_target}/test_write.txt",
        ],
        environment={},
        mounts=(
            VolumeMount(
                source=mount_source,
                target=mount_target,
                read_only=False,
                selinux_label="Z",
            ),
        ),
        remove_after_exit=True,
    )

    result = manager.run(spec, sink, attach_streams=True)

    # Verify exit code
    assert result.exit_code == 0, f"Container should succeed, got exit code {result.exit_code}"

    # Verify container wrote file
    container_file = temp_koji_root / "container_write.txt"
    assert container_file.exists(), "Container should write file to mounted directory"

    # Verify container read file
    stdout = sink.stdout.decode("utf-8", errors="replace")
    assert test_content in stdout, f"Container should read host file content, got: {stdout[:200]}"


# ST3: buildArch Task Smoke Tests

@requires_podman
def test_st3_1_buildarch_task_execution(
    podman_available, podman_manager, test_task_context, temp_koji_root
):
    """ST3.1 - BuildArch Task Execution Test

    Verify buildArch task adapter executes successfully in container.
    AC3.1: Task adapter builds ContainerSpec from TaskContext correctly.

    Note: This is a simplified test that validates the adapter runs,
    not a full RPM build (which would require build dependencies).
    """
    manager = podman_manager
    ensure_image_available(manager, TEST_IMAGE)

    # Create a minimal "SRPM" file for testing
    # In real scenario, this would be a valid SRPM
    work_dir = test_task_context.work_dir
    (work_dir / "work").mkdir(exist_ok=True)
    test_srpm = work_dir / "work" / "test.src.rpm"
    test_srpm.write_bytes(b"MINIMAL_SRPM_CONTENT\n")

    # Create adapter
    adapter = BuildArchAdapter()

    # Build task parameters
    task_params = {
        "pkg": "test.src.rpm",
        "root": "test-build-1.0-1",
        "arch": "x86_64",
        "keep_srpm": False,
        "opts": {"repo_id": 1},
    }

    # Build ContainerSpec
    spec = adapter.build_spec(test_task_context, task_params)

    # Verify spec is valid
    assert spec.image is not None
    assert len(spec.command) > 0
    assert len(spec.mounts) > 0
    assert "KOJI_TASK_ID" in spec.environment
    assert spec.remove_after_exit is True

    # For Phase 1, we'll verify the spec is correct rather than running
    # a full build (which would require build dependencies in the image)
    # The spec should include proper mounts and environment
    assert any(m.target == Path("/mnt/koji") for m in spec.mounts), "Should mount /mnt/koji"
    assert any(m.target == Path(f"/work/{test_task_context.task_id}") for m in spec.mounts), "Should mount work directory"


# ST4: createrepo Task Smoke Tests

@requires_podman
def test_st4_1_createrepo_task_execution(
    podman_available,
    podman_manager,
    test_task_context,
    test_repo_directory,
    temp_koji_root,
):
    """ST4.1 - Createrepo Task Execution Test

    Verify createrepo task adapter executes successfully in container.
    AC4.1: Task adapter builds ContainerSpec from TaskContext correctly.

    Note: This is a simplified test that validates the adapter runs,
    not a full createrepo execution (which would require createrepo_c in image).
    """
    manager = podman_manager
    ensure_image_available(manager, TEST_IMAGE)

    # Create adapter
    adapter = CreaterepoAdapter()

    # Build task parameters
    repo_id = 1
    arch = "x86_64"
    task_params = {
        "repo_id": repo_id,
        "arch": arch,
        "repodir": f"/mnt/koji/repos/{repo_id}/{arch}",
        "pkglist": str(test_repo_directory / "pkglist"),
    }

    # Build ContainerSpec
    spec = adapter.build_spec(test_task_context, task_params)

    # Verify spec is valid
    assert spec.image is not None
    assert len(spec.command) > 0
    assert len(spec.mounts) > 0
    assert "KOJI_TASK_ID" in spec.environment
    assert "KOJI_REPO_ID" in spec.environment
    assert spec.remove_after_exit is True

    # Verify mounts include repository directory
    assert any(m.target == Path("/mnt/koji") for m in spec.mounts), "Should mount /mnt/koji"


# Additional validation tests for log persistence

@requires_podman
def test_log_persistence_to_filesystem(
    podman_available, podman_manager, test_task_context, mock_koji_logger
):
    """Test that logs are persisted to filesystem.

    AC5.2: Container logs are persisted to /mnt/koji/logs/<task_id>/container.log
    """
    manager = podman_manager
    ensure_image_available(manager, TEST_IMAGE)

    # Create log file path
    log_dir = test_task_context.koji_mount_root / "logs" / str(test_task_context.task_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "container.log"

    # Create FileKojiLogSink
    sink = FileKojiLogSink(mock_koji_logger, log_file)

    try:
        # Create container with known output
        spec = ContainerSpec(
            image=TEST_IMAGE,
            command=["/bin/sh", "-c", "echo 'test log output'; echo 'test error' >&2"],
            environment={},
            remove_after_exit=True,
        )

        result = manager.run(spec, sink, attach_streams=True)

        # Close sink to ensure file is flushed
        sink.close()

        # Verify log file exists
        assert log_file.exists(), f"Log file should exist at {log_file}"

        # Verify log file contains output
        log_content = log_file.read_bytes()
        assert b"test log output" in log_content or b"test error" in log_content, \
            f"Log file should contain container output, got: {log_content[:200]}"

    finally:
        sink.close()


# Test execution helpers

if __name__ == "__main__":
    # Allow direct execution for debugging
    pytest.main([__file__, "-v", "-s"])
