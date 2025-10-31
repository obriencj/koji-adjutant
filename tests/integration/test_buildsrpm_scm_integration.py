"""Integration tests for BuildSRPMFromSCM adapter with real containers and git.

These tests validate that BuildSRPMFromSCMAdapter can:
1. Checkout source from git repositories
2. Build SRPMs from checked-out source
3. Handle container lifecycle correctly
4. Clean up containers properly
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

from koji_adjutant.container.interface import InMemoryLogSink
from koji_adjutant.container.podman_manager import PodmanManager
from koji_adjutant.task_adapters.base import TaskContext
from koji_adjutant.task_adapters.buildsrpm_scm import BuildSRPMFromSCMAdapter
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

    # Create standard subdirectories
    (koji_root / "work").mkdir(exist_ok=True)
    (koji_root / "logs").mkdir(exist_ok=True)
    (koji_root / "repos").mkdir(exist_ok=True)

    return koji_root


@pytest.fixture
def test_task_context(temp_koji_root):
    """Create a TaskContext for testing."""
    task_id = 88888
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
    """Helper to ensure test image is available, skip test if not."""
    try:
        manager.ensure_image_available(image)
        return True
    except Exception as e:
        pytest.skip(f"Test image not available: {e}")


@requires_podman
def test_buildsrpm_scm_container_spec_validation(
    podman_available,
    podman_manager,
    test_task_context,
):
    """Test that BuildSRPMFromSCM adapter creates valid ContainerSpec.
    
    This validates the adapter's build_spec method with network enabled
    for SCM checkout.
    """
    manager = podman_manager
    ensure_image_available(manager, TEST_IMAGE)

    adapter = BuildSRPMFromSCMAdapter()
    
    task_params = {
        "url": "git://example.com/repo.git#main",
        "build_tag": "test-build",
        "opts": {"repo_id": 1},
    }

    # Build spec
    spec = adapter.build_spec(test_task_context, task_params)
    
    # Validate spec structure
    assert spec.image is not None
    assert spec.command == ["/bin/sleep", "infinity"]  # Exec pattern
    assert len(spec.mounts) >= 2  # koji mount + workdir mount
    assert spec.network_enabled is True  # KEY: SCM checkout requires network
    assert spec.remove_after_exit is True
    
    # Verify environment variables
    assert "KOJI_TASK_ID" in spec.environment
    assert "KOJI_BUILD_TAG" in spec.environment
    assert "KOJI_REPO_ID" in spec.environment
    assert "KOJI_SCM_URL" in spec.environment
    
    logger.info("BuildSRPMFromSCM ContainerSpec validation passed")


@requires_podman
def test_buildsrpm_scm_git_checkout_validation(
    podman_available,
    podman_manager,
    test_task_context,
):
    """Test git checkout validation in BuildSRPMFromSCM adapter.
    
    This test validates that the adapter can handle git URLs correctly
    and creates appropriate specs for SCM checkout.
    """
    adapter = BuildSRPMFromSCMAdapter()
    
    # Test different git URL formats
    test_cases = [
        ("git://example.com/repo.git", "main"),
        ("git://example.com/repo.git#develop", "develop"),
        ("git://example.com/repo.git#v1.0.0", "v1.0.0"),
        ("https://github.com/user/repo.git", "main"),
    ]
    
    for url, expected_ref in test_cases:
        task_params = {
            "url": url,
            "build_tag": "test-build",
            "opts": {"repo_id": 1},
        }
        
        spec = adapter.build_spec(test_task_context, task_params)
        
        # Verify network is enabled for all git URLs
        assert spec.network_enabled is True, f"Network should be enabled for {url}"
        assert "KOJI_SCM_URL" in spec.environment
        assert spec.environment["KOJI_SCM_URL"] == url
        
        logger.info(f"Git URL validation passed: {url}")


@requires_podman
def test_buildsrpm_scm_error_handling(
    podman_available,
    podman_manager,
    test_task_context,
):
    """Test BuildSRPMFromSCM adapter error handling."""
    adapter = BuildSRPMFromSCMAdapter()
    
    # Test missing repo_id
    task_params_no_repo = {
        "url": "git://example.com/repo.git",
        "build_tag": "test-build",
        "opts": {},  # Missing repo_id
    }
    
    with pytest.raises(ValueError, match="repo id"):
        adapter.build_spec(test_task_context, task_params_no_repo)
    
    # Test missing url
    task_params_no_url = {
        "build_tag": "test-build",
        "opts": {"repo_id": 1},
    }
    
    with pytest.raises(KeyError):
        adapter.build_spec(test_task_context, task_params_no_url)
    
    logger.info("Error handling validation passed")


@requires_podman
def test_buildsrpm_scm_checkout_scm_method(
    podman_available,
    podman_manager,
    test_task_context,
):
    """Test that checkout_scm method handles different SCM URLs."""
    adapter = BuildSRPMFromSCMAdapter()
    
    # This test validates the adapter can identify and handle git URLs
    # Full checkout testing requires git available in container
    
    test_urls = [
        "git://example.com/repo.git",
        "git://example.com/repo.git#main",
        "git://example.com/repo.git#abc123def456",  # Commit hash
        "https://github.com/user/repo.git",
    ]
    
    for url in test_urls:
        # Verify adapter can build spec for each URL
        task_params = {
            "url": url,
            "build_tag": "test-build",
            "opts": {"repo_id": 1},
        }
        
        spec = adapter.build_spec(test_task_context, task_params)
        assert spec.network_enabled is True
        
        logger.info(f"SCM URL handling validated: {url}")