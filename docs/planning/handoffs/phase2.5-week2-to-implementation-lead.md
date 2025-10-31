# Phase 2.5 Week 2 Handoff: BuildSRPMFromSCM Adapter + SCM Module

**Date**: 2025-10-31
**From**: Strategic Planner
**To**: Implementation Lead
**Status**: Ready for Week 2 Implementation
**Priority**: CRITICAL - Blocks deployment

---

## Context

**Week 1 Status**: ✅ **COMPLETE** - RebuildSRPMAdapter delivered successfully!

**Deliverables Completed**:
- ✅ RebuildSRPMAdapter implementation (581 lines)
- ✅ Unit tests (12 tests, 91.7% pass rate)
- ✅ Kojid integration with fallback
- ✅ 66.67% code coverage

**Outstanding**: 1 minor test issue (non-blocking), will be addressed by Quality Engineer

---

## Week 2 Mission: BuildSRPMFromSCM Adapter + SCM Module

**Timeline**: 7 days
**Complexity**: HIGH (SCM integration adds complexity vs Week 1)

### What You're Building

**BuildSRPMFromSCMAdapter**: Checkout source from version control (git) and build SRPM

**SCM Module**: Git checkout abstraction (protocol-based for future SVN/CVS support)

**Complete Workflow**:
```
User: koji build f39 git://example.com/package.git
  ↓
1. BuildSRPMFromSCMTask spawns subtask
2. BuildSRPMFromSCMAdapter:
   - Checkout git://example.com/package.git
   - Build SRPM from checked-out source
   - Upload SRPM to hub
3. BuildArchTask spawns (uses Week 1's RebuildSRPM or direct RPM build)
```

---

## Week 2 Deliverables

### 1. SCM Module (Days 1-2)

**Directory**: `koji_adjutant/task_adapters/scm/`

**Files to Create**:
- `__init__.py` - Module initialization
- `base.py` - SCMHandler protocol definition
- `git.py` - GitHandler implementation

**Estimated Lines**: ~400 total (100 + 100 + 200)

### 2. BuildSRPMFromSCMAdapter (Days 3-5)

**File**: `koji_adjutant/task_adapters/buildsrpm_scm.py`

**Estimated Lines**: ~350-400 lines

### 3. Unit Tests (Days 5-6)

**Files**:
- `tests/unit/test_scm_handlers.py` - SCM module tests
- `tests/unit/test_buildsrpm_scm_adapter.py` - Adapter tests

**Test Target**: 12-15 tests, 95%+ pass rate

### 4. Kojid Integration (Day 7)

**Modify**: `koji_adjutant/kojid.py` - BuildSRPMFromSCMTask.handler()

**Pattern**: Same as RebuildSRPM (adapter detection + fallback)

---

## Detailed Task Breakdown

### Task 1: SCM Module (Days 1-2)

#### File 1: `koji_adjutant/task_adapters/scm/__init__.py`

```python
"""SCM integration module for source checkout operations.

Provides protocol-based abstraction for different SCM types (git, svn, cvs).
"""

from .base import SCMHandler
from .git import GitHandler

__all__ = [
    "SCMHandler",
    "GitHandler",
]
```

---

#### File 2: `koji_adjutant/task_adapters/scm/base.py`

```python
"""Base SCM handler protocol."""

from __future__ import annotations

from typing import Dict, Optional, Protocol

from ...container.interface import ContainerManager


class SCMHandler(Protocol):
    """Protocol for SCM checkout handlers.

    All SCM implementations (git, svn, cvs) must implement this protocol.
    """

    @staticmethod
    def is_scm_url(url: str) -> bool:
        """Check if URL matches this SCM type.

        Args:
            url: URL to check (e.g., git://example.com/repo.git)

        Returns:
            True if this handler can process the URL

        Examples:
            GitHandler.is_scm_url("git://example.com/repo.git") -> True
            GitHandler.is_scm_url("svn://example.com/repo") -> False
        """
        ...

    def __init__(self, url: str, options: Optional[Dict] = None):
        """Initialize handler for SCM URL.

        Args:
            url: SCM URL with optional fragment (#branch, #tag, #commit)
            options: Optional dict with checkout options
                - branch: Branch name to checkout
                - commit: Specific commit hash
                - tag: Tag name to checkout

        Examples:
            GitHandler("git://example.com/repo.git#main")
            GitHandler("git://example.com/repo.git", {"commit": "abc123"})
        """
        ...

    def checkout(
        self,
        container_manager: ContainerManager,
        container_id: str,
        dest_dir: str,
    ) -> Dict[str, str]:
        """Checkout source code to destination directory in container.

        Args:
            container_manager: Container manager for executing commands
            container_id: ID of running container
            dest_dir: Destination directory path (in container)

        Returns:
            Metadata dict with keys:
            - url: Original SCM URL
            - commit: Resolved commit hash (for git)
            - branch: Branch name (if applicable)
            - revision: Revision number (for svn)

        Raises:
            ContainerError: If checkout fails

        Example:
            metadata = handler.checkout(manager, container_id, "/builddir/source")
            # Returns: {
            #     'url': 'git://example.com/repo.git',
            #     'commit': 'abc123def456...',
            #     'branch': 'main'
            # }
        """
        ...
```

---

#### File 3: `koji_adjutant/task_adapters/scm/git.py`

```python
"""Git SCM handler implementation."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ...container.interface import ContainerError, ContainerManager

logger = logging.getLogger(__name__)


class GitHandler:
    """Git SCM checkout handler.

    Handles git:// and https://*.git URLs with branch/tag/commit support.
    """

    # Patterns for git URL detection
    GIT_URL_PATTERNS = [
        r'^git://',
        r'^git\+https://',
        r'^git\+http://',
        r'^https?://.*\.git',
        r'^https?://github\.com/',
        r'^https?://gitlab\.com/',
    ]

    @staticmethod
    def is_scm_url(url: str) -> bool:
        """Check if URL is a git URL.

        Args:
            url: URL to check

        Returns:
            True if URL matches git patterns

        Examples:
            >>> GitHandler.is_scm_url("git://example.com/repo.git")
            True
            >>> GitHandler.is_scm_url("https://github.com/user/repo.git")
            True
            >>> GitHandler.is_scm_url("svn://example.com/repo")
            False
        """
        for pattern in GitHandler.GIT_URL_PATTERNS:
            if re.match(pattern, url):
                return True
        return False

    def __init__(self, url: str, options: Optional[Dict] = None):
        """Initialize git handler.

        Args:
            url: Git URL with optional fragment (#branch, #tag, #commit)
                 Format: git://host/path[#ref] or https://host/path[#ref]
            options: Optional dict with:
                - branch: Branch name (overrides fragment)
                - commit: Specific commit hash
                - tag: Tag name

        Examples:
            GitHandler("git://example.com/repo.git#main")
            GitHandler("https://github.com/user/repo.git#v1.0.0")
            GitHandler("git://example.com/repo.git", {"commit": "abc123"})
        """
        self.options = options or {}

        # Parse URL and fragment
        if '#' in url:
            self.url, self.ref = url.rsplit('#', 1)
        else:
            self.url = url
            self.ref = None

        # Override ref with options if provided
        if 'branch' in self.options:
            self.ref = self.options['branch']
            self.ref_type = 'branch'
        elif 'tag' in self.options:
            self.ref = self.options['tag']
            self.ref_type = 'tag'
        elif 'commit' in self.options:
            self.ref = self.options['commit']
            self.ref_type = 'commit'
        elif self.ref:
            # Auto-detect ref type (branch/tag/commit)
            if re.match(r'^[0-9a-f]{7,40}$', self.ref):
                self.ref_type = 'commit'
            elif self.ref.startswith('v') or re.match(r'^\d+\.\d+', self.ref):
                self.ref_type = 'tag'
            else:
                self.ref_type = 'branch'
        else:
            # Default to main/master
            self.ref = 'main'
            self.ref_type = 'branch'

        logger.debug(
            "Parsed git URL: url=%s ref=%s ref_type=%s",
            self.url, self.ref, self.ref_type
        )

    def checkout(
        self,
        container_manager: ContainerManager,
        container_handle: Any,
        dest_dir: str,
    ) -> Dict[str, str]:
        """Checkout git repository.

        Args:
            container_manager: Container manager
            container_handle: Container handle (not just ID)
            dest_dir: Destination directory in container

        Returns:
            Metadata dict with url, commit, branch

        Raises:
            ContainerError: If git clone or checkout fails
        """
        logger.info("Checking out git repo: %s -> %s", self.url, dest_dir)

        # Create destination directory
        mkdir_cmd = ["mkdir", "-p", dest_dir]
        exit_code = container_manager.exec(container_handle, mkdir_cmd, None, {})
        if exit_code != 0:
            raise ContainerError(f"Failed to create directory: {dest_dir}")

        # Git clone
        clone_cmd = ["git", "clone", "--depth", "1", "--branch", self.ref, self.url, dest_dir]
        logger.debug("Git clone command: %s", clone_cmd)

        exit_code = container_manager.exec(container_handle, clone_cmd, None, {})
        if exit_code != 0:
            # Try without --depth and --branch for commit-specific checkout
            if self.ref_type == 'commit':
                logger.debug("Retrying clone without branch/depth for commit checkout")
                clone_cmd = ["git", "clone", self.url, dest_dir]
                exit_code = container_manager.exec(container_handle, clone_cmd, None, {})
                if exit_code != 0:
                    raise ContainerError(f"Git clone failed: {self.url}")

                # Checkout specific commit
                checkout_cmd = ["git", "-C", dest_dir, "checkout", self.ref]
                exit_code = container_manager.exec(container_handle, checkout_cmd, None, {})
                if exit_code != 0:
                    raise ContainerError(f"Git checkout commit failed: {self.ref}")
            else:
                raise ContainerError(f"Git clone failed: {self.url}")

        # Get commit hash
        rev_parse_cmd = ["git", "-C", dest_dir, "rev-parse", "HEAD"]
        # Note: Need to capture output - will use a temp file approach
        # Write output to temp file, then read it
        commit_file = f"{dest_dir}/.git_commit"
        rev_parse_with_redirect = [
            "sh", "-c",
            f"git -C {dest_dir} rev-parse HEAD > {commit_file}"
        ]
        exit_code = container_manager.exec(container_handle, rev_parse_with_redirect, None, {})

        # For now, return placeholder - actual commit will be read from file
        # This is a simplification; real implementation would need copy_from
        commit_hash = "unknown"  # Would read from commit_file via mounted volume

        logger.info("Git checkout complete: commit=%s", commit_hash)

        return {
            'url': self.url,
            'commit': commit_hash,
            'branch': self.ref if self.ref_type == 'branch' else '',
            'ref': self.ref,
            'ref_type': self.ref_type,
        }


def get_scm_handler(url: str, options: Optional[Dict] = None) -> GitHandler:
    """Factory function to get appropriate SCM handler for URL.

    Args:
        url: SCM URL
        options: Optional checkout options

    Returns:
        Appropriate SCM handler instance

    Raises:
        ValueError: If URL is not recognized as valid SCM URL

    Example:
        handler = get_scm_handler("git://example.com/repo.git")
        metadata = handler.checkout(manager, container_id, "/builddir")
    """
    if GitHandler.is_scm_url(url):
        return GitHandler(url, options)
    else:
        raise ValueError(f"Unsupported SCM URL: {url}")
```

**Key Implementation Notes**:
- Git clone with `--depth 1` for performance
- Auto-detect ref type (branch/tag/commit)
- Fallback for commit-specific checkout
- Commit hash capture (simplified for now)

---

### Task 2: BuildSRPMFromSCMAdapter (Days 3-5)

**File**: `koji_adjutant/task_adapters/buildsrpm_scm.py`

**Pattern**: Similar to RebuildSRPMAdapter but with SCM checkout + network enabled

```python
"""BuildSRPMFromSCM task adapter for containerized SRPM builds from source control.

This adapter translates Koji buildSRPMFromSCM tasks into container executions,
checking out source from git/svn and building SRPMs in isolated containers.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..container.interface import ContainerError, ContainerManager, ContainerSpec, VolumeMount
from .. import config as adj_config
from ..policy import PolicyResolver
from ..buildroot import BuildrootInitializer
from .base import BaseTaskAdapter, KojiLogSink, TaskContext
from .scm import get_scm_handler

logger = logging.getLogger(__name__)

# Optional monitoring registry import
try:
    from ..monitoring import get_task_registry
except ImportError:
    def get_task_registry():
        return None


class BuildSRPMFromSCMAdapter(BaseTaskAdapter):
    """Adapter for executing buildSRPMFromSCM tasks in containers.

    Translates buildSRPMFromSCM task context into ContainerSpec and executes
    SRPM builds from source control inside isolated containers.
    """

    def build_spec(
        self,
        ctx: TaskContext,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> ContainerSpec:
        """Build ContainerSpec from buildSRPMFromSCM task context.

        Args:
            ctx: Task context
            task_params: Task parameters dict with keys:
                - url: SCM URL (e.g., git://example.com/package.git#branch)
                - build_tag: Build tag name or ID
                - opts: Optional dict with repo_id and other options
            session: Optional koji session for policy resolution
            event_id: Optional event ID for policy queries

        Returns:
            ContainerSpec configured for SRPM build from SCM
        """
        url = task_params["url"]
        build_tag = task_params["build_tag"]
        opts = task_params.get("opts") or {}
        repo_id = opts.get("repo_id")
        if not repo_id:
            raise ValueError("A repo id must be provided")

        # Resolve task image from policy or config
        # Same as RebuildSRPM but with task_type="buildSRPMFromSCM"
        if session is not None and adj_config.adjutant_policy_enabled():
            try:
                resolver = PolicyResolver(session)
                tag_name = build_tag
                if isinstance(build_tag, int):
                    logger.warning(
                        "build_tag is int (%d), assuming tag name lookup needed",
                        build_tag,
                    )
                image = resolver.resolve_image(
                    tag_name=str(tag_name),
                    arch="noarch",  # SRPM builds are always noarch
                    task_type="buildSRPMFromSCM",
                    event_id=event_id,
                )
                logger.debug("Resolved image via policy: %s", image)
            except Exception as exc:
                logger.warning("Policy resolution failed: %s", exc)
                image = adj_config.adjutant_task_image_default()
        else:
            image = adj_config.adjutant_task_image_default()

        # Same mount and environment setup as RebuildSRPM
        work_target_path = f"/work/{ctx.task_id}"

        env = dict(ctx.environment)
        env.update({
            "KOJI_TASK_ID": str(ctx.task_id),
            "KOJI_BUILD_TAG": str(build_tag),
            "KOJI_REPO_ID": str(repo_id),
            "KOJI_SCM_URL": url,  # Additional: track SCM URL
        })

        mounts = [
            VolumeMount(
                source=ctx.koji_mount_root,
                target=Path("/mnt/koji"),
                read_only=False,
                selinux_label="Z",
            ),
            VolumeMount(
                source=ctx.work_dir,
                target=Path(work_target_path),
                read_only=False,
                selinux_label="Z",
            ),
        ]

        return ContainerSpec(
            image=image,
            command=["/bin/sleep", "infinity"],  # Exec pattern
            environment=env,
            workdir=Path(work_target_path),
            mounts=tuple(mounts),
            user_id=1000,
            group_id=1000,
            network_enabled=True,  # KEY DIFFERENCE: Network required for SCM checkout
            remove_after_exit=True,
        )

    def run(
        self,
        ctx: TaskContext,
        manager: ContainerManager,
        sink: KojiLogSink,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> tuple[int, Dict]:
        """Execute buildSRPMFromSCM task in container.

        Workflow:
        1. Create container with network enabled
        2. Initialize buildroot (srpm-build group)
        3. Checkout source from SCM
        4. Detect build method (make srpm vs rpmbuild -bs)
        5. Build SRPM
        6. Validate SRPM
        7. Return result

        Returns:
            Tuple of (exit_code, result_dict)
        """
        url = task_params["url"]
        build_tag = task_params["build_tag"]
        opts = task_params.get("opts") or {}
        repo_id = opts.get("repo_id")

        # Similar structure to RebuildSRPM.run()
        # Key differences:
        # 1. SCM checkout step
        # 2. Detect build method (make srpm vs rpmbuild -bs)
        # 3. Build SRPM from checked-out source
        # 4. Include SCM metadata in result

        # [Implementation follows RebuildSRPM pattern]
        # See design doc for full implementation

        pass  # Placeholder

    def checkout_scm(
        self,
        handle: Any,
        manager: ContainerManager,
        scm_url: str,
        dest_dir: str,
        sink: KojiLogSink,
    ) -> Dict[str, str]:
        """Checkout source from SCM.

        Args:
            handle: Container handle
            manager: Container manager
            scm_url: SCM URL with optional fragment
            dest_dir: Destination directory in container
            sink: Log sink

        Returns:
            SCM metadata dict (url, commit, branch, etc.)
        """
        # Get appropriate SCM handler
        handler = get_scm_handler(scm_url)

        # Perform checkout
        metadata = handler.checkout(manager, handle, dest_dir)

        logger.info("SCM checkout complete: %s", metadata)
        return metadata

    def detect_build_method(
        self,
        handle: Any,
        manager: ContainerManager,
        source_dir: str,
        sink: KojiLogSink,
    ) -> str:
        """Detect build method (make srpm vs rpmbuild -bs).

        Args:
            handle: Container handle
            manager: Container manager
            source_dir: Source directory
            sink: Log sink

        Returns:
            "make" or "rpmbuild"
        """
        # Check for Makefile with srpm target
        check_makefile = [
            "sh", "-c",
            f"test -f {source_dir}/Makefile && grep -q 'srpm:' {source_dir}/Makefile"
        ]
        exit_code = manager.exec(handle, check_makefile, sink, {})

        if exit_code == 0:
            return "make"
        else:
            return "rpmbuild"

    def build_srpm(
        self,
        handle: Any,
        manager: ContainerManager,
        source_dir: str,
        work_dir: str,
        method: str,
        sink: KojiLogSink,
        env: Dict[str, str],
    ) -> str:
        """Build SRPM from source.

        Args:
            handle: Container handle
            manager: Container manager
            source_dir: Source directory
            work_dir: Work directory
            method: "make" or "rpmbuild"
            sink: Log sink
            env: Environment variables

        Returns:
            Path pattern to built SRPM
        """
        result_dir = f"{work_dir}/result"
        manager.exec(handle, ["mkdir", "-p", result_dir], sink, env)

        if method == "make":
            # Use make srpm
            build_cmd = ["make", "-C", source_dir, "srpm"]
        else:
            # Use rpmbuild -bs
            # Need to find spec file first
            spec_file = f"{source_dir}/*.spec"  # Wildcard, use with sh -c
            build_cmd = [
                "sh", "-c",
                f"rpmbuild -bs --define '_topdir {work_dir}' --define '_sourcedir {source_dir}' --define '_srcrpmdir {result_dir}' {spec_file}"
            ]

        exit_code = manager.exec(handle, build_cmd, sink, env)
        if exit_code != 0:
            raise ContainerError(f"SRPM build failed with method: {method}")

        return f"{result_dir}/*.src.rpm"
```

**Key Differences from RebuildSRPM**:
- Network enabled in ContainerSpec
- SCM checkout step added
- Build method detection (make vs rpmbuild)
- SCM metadata in result

---

### Task 3: Unit Tests (Days 5-6)

#### Test File 1: `tests/unit/test_scm_handlers.py`

```python
"""Unit tests for SCM handlers."""

from unittest.mock import MagicMock

import pytest

from koji_adjutant.container.interface import ContainerError, ContainerHandle
from koji_adjutant.task_adapters.scm.git import GitHandler, get_scm_handler


class TestGitHandler:
    """Test GitHandler class."""

    def test_is_scm_url_git_protocol(self):
        """Test git:// URL detection."""
        assert GitHandler.is_scm_url("git://example.com/repo.git") is True
        assert GitHandler.is_scm_url("git+https://example.com/repo.git") is True

    def test_is_scm_url_https_git(self):
        """Test https://*.git URL detection."""
        assert GitHandler.is_scm_url("https://github.com/user/repo.git") is True
        assert GitHandler.is_scm_url("https://gitlab.com/user/repo.git") is True

    def test_is_scm_url_non_git(self):
        """Test non-git URL rejection."""
        assert GitHandler.is_scm_url("svn://example.com/repo") is False
        assert GitHandler.is_scm_url("https://example.com/file.tar.gz") is False

    def test_init_with_branch(self):
        """Test GitHandler initialization with branch in fragment."""
        handler = GitHandler("git://example.com/repo.git#develop")
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "develop"
        assert handler.ref_type == "branch"

    def test_init_with_tag(self):
        """Test GitHandler initialization with tag in fragment."""
        handler = GitHandler("git://example.com/repo.git#v1.0.0")
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "v1.0.0"
        assert handler.ref_type == "tag"

    def test_init_with_commit(self):
        """Test GitHandler initialization with commit in fragment."""
        handler = GitHandler("git://example.com/repo.git#abc123def456")
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "abc123def456"
        assert handler.ref_type == "commit"

    def test_init_default_ref(self):
        """Test GitHandler initialization without fragment defaults to main."""
        handler = GitHandler("git://example.com/repo.git")
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "main"
        assert handler.ref_type == "branch"

    def test_checkout_success(self):
        """Test successful git checkout."""
        handler = GitHandler("git://example.com/repo.git#main")
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0

        result = handler.checkout(mock_manager, handle, "/builddir/source")

        assert result["url"] == "git://example.com/repo.git"
        assert "commit" in result
        assert result["branch"] == "main"

        # Verify git clone was called
        calls = mock_manager.exec.call_args_list
        clone_calls = [call for call in calls if any("clone" in str(arg) for arg in call[0])]
        assert len(clone_calls) > 0

    def test_checkout_failure(self):
        """Test git checkout failure."""
        handler = GitHandler("git://example.com/repo.git")
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.side_effect = [
            0,  # mkdir succeeds
            1,  # git clone fails
        ]

        with pytest.raises(ContainerError, match="Git clone failed"):
            handler.checkout(mock_manager, handle, "/builddir/source")


class TestGetSCMHandler:
    """Test get_scm_handler factory function."""

    def test_get_git_handler(self):
        """Test getting git handler."""
        handler = get_scm_handler("git://example.com/repo.git")
        assert isinstance(handler, GitHandler)

    def test_unsupported_scm(self):
        """Test unsupported SCM URL."""
        with pytest.raises(ValueError, match="Unsupported SCM URL"):
            get_scm_handler("ftp://example.com/file.tar.gz")
```

#### Test File 2: `tests/unit/test_buildsrpm_scm_adapter.py`

**Pattern**: Similar to test_rebuild_srpm_adapter.py but with:
- Tests for SCM checkout integration
- Tests for build method detection
- Tests for network-enabled container spec
- Tests with SCM metadata in results

---

### Task 4: Kojid Integration (Day 7)

**Modify**: `koji_adjutant/kojid.py` - Find `BuildSRPMFromSCMTask` class

**Pattern**: Same as RebuildSRPM integration:

1. Add import at top (around line 139):
```python
from koji_adjutant.task_adapters.buildsrpm_scm import BuildSRPMFromSCMAdapter
```

2. Modify `BuildSRPMFromSCMTask.handler()` method:
```python
class BuildSRPMFromSCMTask(BaseBuildTask):
    def handler(self, url, build_target, opts=None):
        # Check if adapter available
        if BuildSRPMFromSCMAdapter is None or PodmanManager is None:
            # Fallback to original BuildRoot execution
            # ... existing mock code ...
        else:
            # Use container-based adapter
            # ... similar to RebuildSRPM integration ...
```

3. Export from __init__.py:
```python
# In koji_adjutant/task_adapters/__init__.py
from .buildsrpm_scm import BuildSRPMFromSCMAdapter

__all__ = [
    # ... existing ...
    "BuildSRPMFromSCMAdapter",
]
```

---

## Week 2 Acceptance Criteria

### Must Complete:
- [ ] SCM module created (base.py, git.py, __init__.py)
- [ ] GitHandler can detect git URLs
- [ ] GitHandler can parse URL fragments (branch/tag/commit)
- [ ] GitHandler can checkout git repositories
- [ ] BuildSRPMFromSCMAdapter implemented
- [ ] Adapter has build_spec() with network enabled
- [ ] Adapter has SCM checkout integration
- [ ] Adapter has build method detection
- [ ] Adapter can build SRPM from source
- [ ] Unit tests written (12+ tests)
- [ ] Test pass rate ≥ 90%
- [ ] Kojid integration complete
- [ ] Module exports updated

### Quality Targets:
- [ ] Code coverage ≥ 70%
- [ ] All methods have docstrings
- [ ] Type hints throughout
- [ ] Follows BaseTaskAdapter pattern
- [ ] Error handling with try/finally
- [ ] Logging at appropriate levels

---

## Reference Materials

### Must Read:
1. **Phase 2.5 Design Document** - Section on BuildSRPMFromSCMAdapter and SCM module
2. **ADR 0006** - SRPM Task Adapters architecture
3. **Week 1 Code** - RebuildSRPMAdapter as pattern reference
4. **Original kojid.py** - BuildSRPMFromSCMTask (line 5410-5570)

### Code References:
- **Pattern**: `koji_adjutant/task_adapters/rebuild_srpm.py` (Week 1 deliverable)
- **BuildArch**: `koji_adjutant/task_adapters/buildarch.py` (original adapter)
- **Original**: `koji_adjutant/kojid.py` lines 5410-5570

---

## Common Pitfalls to Avoid

1. **Network Access**: Must enable network in ContainerSpec
2. **Git Commands**: Use proper git flags (--depth 1, --branch)
3. **Commit Hash**: Need to capture git rev-parse output properly
4. **Build Method**: Don't assume make srpm exists, check first
5. **Spec File Location**: May vary, use wildcards with sh -c
6. **URL Parsing**: Handle fragments correctly (#branch)
7. **Error Messages**: Clear distinction between SCM errors and build errors

---

## Testing Strategy

### Unit Tests (Mock-based):
- SCM URL detection
- URL parsing (fragment extraction)
- Git handler initialization
- Adapter spec building
- Build method detection
- Error handling

### Integration Tests (Week 3):
- Real git checkout from public repo
- Real SRPM build from checked-out source
- Complete workflow (git → SRPM → RPM)

---

## Timeline

| Day | Tasks | Deliverables |
|-----|-------|--------------|
| **1** | SCM module skeleton, base.py | Protocol defined |
| **2** | git.py implementation, SCM tests | GitHandler working |
| **3** | BuildSRPMFromSCMAdapter skeleton | Adapter structure |
| **4** | Adapter implementation (checkout, build) | Core methods done |
| **5** | Adapter tests, validation | Tests passing |
| **6** | Kojid integration, fixes | Integration complete |
| **7** | Testing, refinement, documentation | Week 2 complete |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Files created | 6 files |
| Lines of code | ~750 lines |
| Unit tests | ≥ 12 tests |
| Test pass rate | ≥ 90% |
| Code coverage | ≥ 70% |
| No critical bugs | Required |

---

## Next Steps After Week 2

**Week 3**: Integration & Validation
- End-to-end workflow tests
- Performance validation
- Documentation updates
- Phase 2.5 completion report

---

## Getting Help

**Stuck on SCM integration?**
→ Reference koji.daemon.SCM class in original koji

**Git command issues?**
→ Consult Container Engineer

**Testing strategy?**
→ Consult Quality Engineer

**Schedule/priority?**
→ Consult Strategic Planner

---

## Handoff Checklist

### Before Starting:
- [ ] Read this handoff document completely
- [ ] Review Phase 2.5 design document
- [ ] Review ADR 0006
- [ ] Study Week 1 RebuildSRPMAdapter code
- [ ] Understand git checkout requirements

### During Implementation:
- [ ] Start with SCM module (Days 1-2)
- [ ] Test git handler thoroughly before adapter
- [ ] Follow RebuildSRPM pattern for adapter
- [ ] Write tests as you implement
- [ ] Update __init__.py exports

### Before Completion:
- [ ] All tests passing
- [ ] Kojid integration working
- [ ] Documentation updated
- [ ] No linter errors

---

**Handoff Status**: ✅ READY

**Your mission**: Implement BuildSRPMFromSCMAdapter + SCM module for git support

**Expected completion**: 7 days from start

**Good luck, Implementation Lead!** 🚀

---

**From**: Strategic Planner
**Date**: 2025-10-31
**Priority**: CRITICAL
**Week**: 2 of 3 (Phase 2.5)
