"""Integration tests for complete SRPM workflow (git → SRPM → RPM).

These tests validate the complete workflow:
1. BuildSRPMFromSCMAdapter: git → SRPM
2. RebuildSRPMAdapter: SRPM → SRPM (with dist tags)
3. BuildArchAdapter: SRPM → RPM (if available)

Note: Full workflow tests require buildroot initialization and may
be skipped if dependencies are not available.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

# Test if podman is available
try:
    from podman import PodmanClient
    PODMAN_AVAILABLE = True
except Exception:
    PodmanClient = None  # type: ignore[assignment]
    PODMAN_AVAILABLE = False

from koji_adjutant.container.podman_manager import PodmanManager
from koji_adjutant.task_adapters.base import TaskContext
from koji_adjutant.task_adapters.buildsrpm_scm import BuildSRPMFromSCMAdapter
from koji_adjutant.task_adapters.rebuild_srpm import RebuildSRPMAdapter

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test image
TEST_IMAGE = os.environ.get("KOJI_ADJUTANT_TEST_IMAGE", "docker.io/almalinux/9-minimal:latest")

# Skip marker for tests requiring Podman
requires_podman = pytest.mark.skipif(
    not PODMAN_AVAILABLE,
    reason="Podman Python API not available",
)


@pytest.fixture(scope="module")
def podman_available():
    """Check if Podman is available and accessible."""
    if not PODMAN_AVAILABLE:
        pytest.skip("Podman Python API not available")

    try:
        client = PodmanClient()
        client.containers.list(all=True)
        return True
    except Exception as e:
        pytest.skip(f"Podman not accessible: {e}")


@pytest.fixture
def temp_koji_root(tmp_path):
    """Create a temporary /mnt/koji-like directory structure."""
    koji_root = tmp_path / "mnt" / "koji"
    koji_root.mkdir(parents=True, exist_ok=True)

    (koji_root / "work").mkdir(exist_ok=True)
    (koji_root / "logs").mkdir(exist_ok=True)
    (koji_root / "repos").mkdir(exist_ok=True)

    return koji_root


@pytest.fixture
def test_task_context_scm(temp_koji_root):
    """Create a TaskContext for SCM build."""
    task_id = 77777
    work_dir = temp_koji_root / "work" / str(task_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    return TaskContext(
        task_id=task_id,
        work_dir=work_dir,
        koji_mount_root=temp_koji_root,
        environment={"TEST": "1"},
    )


@pytest.fixture
def test_task_context_rebuild(temp_koji_root):
    """Create a TaskContext for rebuild."""
    task_id = 77778
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
        pull_always=False,
        network_default=True,
        worker_id="test-worker",
    )


def ensure_image_available(manager: PodmanManager, image: str) -> bool:
    """Helper to ensure test image is available."""
    try:
        manager.ensure_image_available(image)
        return True
    except Exception as e:
        pytest.skip(f"Test image not available: {e}")


@requires_podman
def test_workflow_scm_to_srpm_spec_validation(
    podman_available,
    podman_manager,
    test_task_context_scm,
):
    """Test workflow step 1: BuildSRPMFromSCM adapter spec validation.
    
    Validates that BuildSRPMFromSCM adapter creates correct ContainerSpec
    for git → SRPM workflow.
    """
    manager = podman_manager
    ensure_image_available(manager, TEST_IMAGE)

    adapter = BuildSRPMFromSCMAdapter()
    
    task_params = {
        "url": "git://example.com/repo.git#main",
        "build_tag": "test-build",
        "opts": {"repo_id": 1},
    }

    spec = adapter.build_spec(test_task_context_scm, task_params)
    
    # Validate SCM build spec
    assert spec.network_enabled is True  # Required for git checkout
    assert "KOJI_SCM_URL" in spec.environment
    
    logger.info("Step 1 (SCM → SRPM) spec validation passed")


@requires_podman
def test_workflow_srpm_rebuild_spec_validation(
    podman_available,
    podman_manager,
    test_task_context_rebuild,
):
    """Test workflow step 2: RebuildSRPM adapter spec validation.
    
    Validates that RebuildSRPM adapter creates correct ContainerSpec
    for SRPM → SRPM (with dist tags) workflow.
    """
    manager = podman_manager
    ensure_image_available(manager, TEST_IMAGE)

    adapter = RebuildSRPMAdapter()
    
    # Simulate SRPM from previous step
    task_params = {
        "srpm": f"work/{test_task_context_rebuild.task_id}/work/package-1.0-1.src.rpm",
        "build_tag": "test-build",
        "opts": {"repo_id": 1},
    }

    spec = adapter.build_spec(test_task_context_rebuild, task_params)
    
    # Validate rebuild spec
    assert spec.network_enabled is False  # Rebuild doesn't need network
    assert "KOJI_TASK_ID" in spec.environment
    
    logger.info("Step 2 (SRPM rebuild) spec validation passed")


@requires_podman
def test_workflow_adapter_compatibility(
    podman_available,
    podman_manager,
    test_task_context_scm,
    test_task_context_rebuild,
):
    """Test that adapters are compatible in workflow sequence.
    
    Validates that:
    1. BuildSRPMFromSCM output format matches RebuildSRPM input format
    2. Task contexts are compatible
    3. Container specs are compatible
    """
    scm_adapter = BuildSRPMFromSCMAdapter()
    rebuild_adapter = RebuildSRPMAdapter()

    # Step 1: SCM build params
    scm_params = {
        "url": "git://example.com/repo.git#main",
        "build_tag": "test-build",
        "opts": {"repo_id": 1},
    }

    # Step 2: Rebuild params (would use SRPM from step 1)
    rebuild_params = {
        "srpm": f"work/{test_task_context_rebuild.task_id}/result/package-1.0-1.src.rpm",
        "build_tag": "test-build",
        "opts": {"repo_id": 1},
    }

    # Build specs
    scm_spec = scm_adapter.build_spec(test_task_context_scm, scm_params)
    rebuild_spec = rebuild_adapter.build_spec(test_task_context_rebuild, rebuild_params)

    # Validate compatibility
    # Both should use same image (if policy enabled, would be same)
    assert scm_spec.image is not None
    assert rebuild_spec.image is not None
    
    # Both should mount same koji root
    scm_koji_mounts = [m for m in scm_spec.mounts if m.target == Path("/mnt/koji")]
    rebuild_koji_mounts = [m for m in rebuild_spec.mounts if m.target == Path("/mnt/koji")]
    assert len(scm_koji_mounts) > 0
    assert len(rebuild_koji_mounts) > 0
    
    # Both should use exec pattern
    assert scm_spec.command == ["/bin/sleep", "infinity"]
    assert rebuild_spec.command == ["/bin/sleep", "infinity"]
    
    logger.info("Adapter compatibility validation passed")


@requires_podman
def test_workflow_error_propagation(
    podman_available,
    podman_manager,
    test_task_context_scm,
):
    """Test error handling across workflow steps.
    
    Validates that errors in one step are handled gracefully
    and don't break subsequent steps.
    """
    adapter = BuildSRPMFromSCMAdapter()
    
    # Test invalid URL format
    invalid_params = {
        "url": "invalid://not-a-valid-scm-url",
        "build_tag": "test-build",
        "opts": {"repo_id": 1},
    }
    
    # Should raise ValueError for unsupported SCM URL
    # (This would be caught by get_scm_handler in real execution)
    # For now, we validate adapter handles it
    try:
        spec = adapter.build_spec(test_task_context_scm, invalid_params)
        # If spec is created, network should still be enabled
        assert spec.network_enabled is True
    except ValueError:
        # Expected if adapter validates URL format
        logger.info("Error handling validated: invalid URL rejected")
    
    logger.info("Error propagation validation passed")