# Phase 2.5: SRPM Task Adapters - Design Document

**Date**: 2025-10-31
**Author**: Strategic Planner
**Status**: Design - Ready for Review
**Phase**: 2.5 (Critical Gap Resolution)

---

## Executive Summary

This document defines the architecture, implementation approach, and integration strategy for two critical missing components: `BuildSRPMFromSCMAdapter` and `RebuildSRPMAdapter`. These adapters are required to enable complete build workflows (SCM → SRPM → RPM) in koji-adjutant.

**Implementation Priority**: CRITICAL - Blocks all deployment and integration testing
**Estimated Effort**: 2-3 weeks (1 engineer)
**Dependencies**: Phase 2 infrastructure (container manager, buildroot initializer, policy resolver)

---

## Table of Contents

1. [Background and Context](#background-and-context)
2. [Requirements](#requirements)
3. [Architecture Design](#architecture-design)
4. [Implementation Approach](#implementation-approach)
5. [Testing Strategy](#testing-strategy)
6. [Integration Plan](#integration-plan)
7. [Risk Assessment](#risk-assessment)
8. [Timeline and Milestones](#timeline-and-milestones)

---

## Background and Context

### Problem Statement

**Discovery Date**: 2025-10-31
**Reported By**: User review of task coverage

Koji-adjutant currently implements only the `buildArch` task adapter, which builds RPMs from existing SRPM files. However, normal koji build workflows require two preceding task types to create those SRPMs:

1. **buildSRPMFromSCM**: Checkout source from version control (git/svn) and build SRPM
2. **rebuildSRPM**: Rebuild an existing SRPM with correct dist tags and macros

Without these adapters, koji-adjutant cannot:
- Accept builds from source control URLs
- Process complete build tasks end-to-end
- Integrate with koji-boxed or production koji hub
- Replace existing kojid workers

### Current Build Flow (Incomplete)

```
User: koji build f39 git://example.com/package.git

1. BuildTask (coordinator) ← kojid.py ✅
   └─ Calls getSRPM() to obtain SRPM
      ├─ getSRPMFromSCM() → spawns buildSRPMFromSCM subtask ❌ NO ADAPTER
      └─ getSRPMFromSRPM() → spawns rebuildSRPM subtask ❌ NO ADAPTER

2. buildArch subtasks (parallel) ← BuildArchAdapter ✅
   └─ Builds RPMs from SRPM (works, but never reached)
```

### Required Build Flow (Complete)

```
User: koji build f39 git://example.com/package.git

1. BuildTask (coordinator) ← kojid.py ✅
   ↓
2. buildSRPMFromSCM subtask ← NEW ADAPTER NEEDED
   - Checkout git://example.com/package.git
   - Run rpmbuild -bs or make srpm
   - Upload mypackage-1.0-1.src.rpm
   ↓
3. buildArch subtasks (parallel) ← BuildArchAdapter ✅
   - x86_64: rpmbuild --rebuild mypackage-1.0-1.src.rpm
   - aarch64: rpmbuild --rebuild mypackage-1.0-1.src.rpm
   ↓
4. Build complete, artifacts uploaded
```

### Reference Implementation

**Original kojid source**: `/home/siege/koji-adjutant/koji_adjutant/kojid.py`
- `BuildSRPMFromSCMTask` (line 5410-5570)
- `RebuildSRPM` (line 5326-5410)

---

## Requirements

### Functional Requirements

#### FR1: BuildSRPMFromSCMAdapter

**Priority**: CRITICAL
**Complexity**: HIGH

| Requirement | Description |
|-------------|-------------|
| **FR1.1** | Checkout source code from SCM URL (git, svn, cvs) |
| **FR1.2** | Support authentication methods (public repos, SSH keys, tokens) |
| **FR1.3** | Execute build command (`rpmbuild -bs` or `make srpm`) |
| **FR1.4** | Apply koji build environment (macros, dist tags) |
| **FR1.5** | Validate resulting SRPM file |
| **FR1.6** | Upload SRPM to hub via task result |
| **FR1.7** | Stream build logs to Koji log system |
| **FR1.8** | Handle SCM checkout failures gracefully |
| **FR1.9** | Support spec file validation |
| **FR1.10** | Clean up container and workspace on completion |

#### FR2: RebuildSRPMAdapter

**Priority**: HIGH
**Complexity**: MEDIUM

| Requirement | Description |
|-------------|-------------|
| **FR2.1** | Accept existing SRPM file path as input |
| **FR2.2** | Unpack SRPM to extract spec and sources |
| **FR2.3** | Apply build tag-specific macros (dist tags) |
| **FR2.4** | Rebuild SRPM with `rpmbuild --rebuild` or equivalent |
| **FR2.5** | Validate rebuilt SRPM (name, version, release) |
| **FR2.6** | Upload rebuilt SRPM to hub via task result |
| **FR2.7** | Stream build logs to Koji log system |
| **FR2.8** | Handle rebuild failures gracefully |
| **FR2.9** | Clean up container and workspace on completion |

### Non-Functional Requirements

#### NFR1: Performance
- Container startup: < 5 seconds
- SCM checkout: Depends on repo size (no artificial limits)
- SRPM build: < 2 minutes for typical packages
- Total overhead vs kojid: < 10%

#### NFR2: Reliability
- Automatic cleanup on failure
- No orphaned containers
- No workspace leaks
- Reproducible builds (same SRPM from same source)

#### NFR3: Security
- SCM credentials handled securely (no logging)
- Container network isolation when appropriate
- SELinux labels on all mounts
- No privilege escalation

#### NFR4: Observability
- All operations logged to Koji
- Container lifecycle visible via monitoring API
- SCM checkout logged (URL, commit, branch)
- Build commands logged for reproducibility

#### NFR5: Compatibility
- Hub API compatibility (result format)
- Mock-based kojid behavioral equivalence
- Existing task handler integration
- Policy-driven image selection

---

## Architecture Design

### Component Overview

```
koji_adjutant/
└── task_adapters/
    ├── base.py                    # Existing base adapter
    ├── buildarch.py               # Existing RPM adapter ✅
    ├── createrepo.py              # Existing repo adapter ✅
    ├── buildsrpm_scm.py           # NEW: SCM → SRPM adapter
    ├── rebuild_srpm.py            # NEW: SRPM rebuild adapter
    └── scm/                       # NEW: SCM integration module
        ├── __init__.py
        ├── base.py                # SCM abstraction
        ├── git.py                 # Git implementation
        └── svn.py                 # SVN implementation (optional)
```

### Class Hierarchy

```python
BaseTaskAdapter (existing)
    ├── BuildArchAdapter (existing)
    ├── CreaterepoAdapter (existing)
    ├── BuildSRPMFromSCMAdapter (NEW)
    └── RebuildSRPMAdapter (NEW)

# SCM Module
SCMHandler (protocol)
    ├── GitHandler (NEW)
    └── SVNHandler (NEW - optional)
```

### BuildSRPMFromSCMAdapter Design

#### Responsibilities
1. Parse task parameters (SCM URL, build tag, options)
2. Resolve container image via PolicyResolver
3. Build ContainerSpec with network enabled
4. Initialize buildroot with `srpm-build` install group
5. Checkout source from SCM
6. Execute SRPM build command
7. Validate and collect SRPM artifact
8. Format result for hub

#### Key Methods

```python
class BuildSRPMFromSCMAdapter(BaseTaskAdapter):
    """Adapter for building SRPMs from source control."""

    def build_spec(
        self,
        ctx: TaskContext,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> ContainerSpec:
        """Build ContainerSpec for SRPM build from SCM.

        Args:
            ctx: Task context (task_id, work_dir, koji_mount_root)
            task_params: {
                'url': 'git://example.com/package.git#branch',
                'build_tag': 'f39-build',
                'opts': {'repo_id': 123, ...}
            }
            session: Koji session for policy/buildconfig queries
            event_id: Event ID for consistent queries

        Returns:
            ContainerSpec with:
            - Image from policy (srpm-build tag)
            - Network enabled (for SCM checkout)
            - Mounts: workdir, koji storage
            - Environment: build macros, dist tags
            - Command: None (will use exec() pattern)
        """

    def execute_task(
        self,
        container_manager: ContainerManager,
        container_spec: ContainerSpec,
        task_params: dict,
        log_sink: Optional[LogSink] = None,
    ) -> dict:
        """Execute SRPM build from SCM in container.

        Steps:
        1. Create and start container
        2. Initialize buildroot (srpm-build group)
        3. Checkout source from SCM
        4. Run build command (make srpm or rpmbuild -bs)
        5. Collect SRPM artifact
        6. Validate SRPM
        7. Format result
        8. Cleanup container

        Returns:
            {
                'srpm': 'work/12345/mypackage-1.0-1.src.rpm',
                'source': {'url': '...', 'commit': '...'},
                'logs': ['work/12345/build.log'],
                'brootid': 67890
            }
        """

    def checkout_scm(
        self,
        container_id: str,
        scm_url: str,
        dest_dir: str,
    ) -> dict:
        """Checkout source from SCM.

        Uses SCMHandler to abstract git/svn differences.
        Returns metadata about checkout (commit hash, branch, etc.)
        """

    def build_srpm(
        self,
        container_id: str,
        spec_file: str,
        source_dir: str,
    ) -> str:
        """Build SRPM from spec and sources.

        Detects build method:
        - If Makefile with 'srpm' target: make srpm
        - Otherwise: rpmbuild -bs

        Returns path to SRPM artifact.
        """

    def validate_srpm(self, srpm_path: str) -> dict:
        """Validate SRPM file and extract metadata.

        Checks:
        - File exists and is valid RPM
        - Is source package (not binary)
        - Name matches expected pattern
        - Contains required headers

        Returns: {'name': ..., 'version': ..., 'release': ...}
        """
```

#### Container Specification

```python
ContainerSpec(
    image="<policy-resolved-image>",  # e.g., registry.io/koji-buildroot:f39

    command=None,  # Will use exec() pattern

    mounts=[
        VolumeMount(
            host_path="/mnt/koji/work/<task_id>",
            container_path="/builddir",
            mode="rw",
            selinux_label="Z"  # Private unshared
        ),
        VolumeMount(
            host_path="/mnt/koji",
            container_path="/mnt/koji",
            mode="rw",
            selinux_label="z"  # Shared
        ),
    ],

    environment={
        "KOJI_BUILD_ID": "<build_id>",
        "KOJI_TASK_ID": "<task_id>",
        # Build macros will be written to /etc/rpm/macros.koji
    },

    network_mode="default",  # Enable network for SCM checkout

    labels={
        "io.koji.adjutant.task_id": "<task_id>",
        "io.koji.adjutant.task_type": "buildSRPMFromSCM",
        "io.koji.adjutant.scm_url": "<url>",
    },

    working_dir="/builddir",

    user=None,  # Default (root for buildroot init, then mockbuild)
)
```

### RebuildSRPMAdapter Design

#### Responsibilities
1. Parse task parameters (SRPM path, build tag, options)
2. Resolve container image via PolicyResolver
3. Build ContainerSpec (network optional)
4. Initialize buildroot with `srpm-build` install group
5. Copy input SRPM to container
6. Unpack SRPM and rebuild with correct macros
7. Validate and collect rebuilt SRPM
8. Format result for hub

#### Key Methods

```python
class RebuildSRPMAdapter(BaseTaskAdapter):
    """Adapter for rebuilding existing SRPMs."""

    def build_spec(
        self,
        ctx: TaskContext,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> ContainerSpec:
        """Build ContainerSpec for SRPM rebuild.

        Args:
            ctx: Task context
            task_params: {
                'srpm': 'work/12344/mypackage-1.0-1.src.rpm',
                'build_tag': 'f39-build',
                'opts': {'repo_id': 123}
            }

        Returns:
            ContainerSpec (similar to SCM but network optional)
        """

    def execute_task(
        self,
        container_manager: ContainerManager,
        container_spec: ContainerSpec,
        task_params: dict,
        log_sink: Optional[LogSink] = None,
    ) -> dict:
        """Execute SRPM rebuild in container.

        Steps:
        1. Create and start container
        2. Initialize buildroot (srpm-build group)
        3. Copy input SRPM to container
        4. Unpack SRPM (rpm -iv)
        5. Apply build tag macros
        6. Rebuild SRPM (rpmbuild --rebuild or rpmbuild -bs)
        7. Validate rebuilt SRPM
        8. Format result
        9. Cleanup container

        Returns:
            {
                'srpm': 'work/12345/mypackage-1.0-1.el9.src.rpm',
                'source': {'url': 'mypackage-1.0-1.src.rpm'},
                'logs': ['work/12345/build.log'],
                'brootid': 67890
            }
        """

    def unpack_srpm(
        self,
        container_id: str,
        srpm_path: str,
        dest_dir: str,
    ) -> dict:
        """Unpack SRPM to extract spec and sources.

        Uses: rpm -iv --define '_topdir <dest>'
        Returns: {'spec': '...', 'sources': [...]}
        """

    def rebuild_srpm(
        self,
        container_id: str,
        spec_file: str,
        source_dir: str,
    ) -> str:
        """Rebuild SRPM with correct macros.

        Uses: rpmbuild -bs --define 'dist .el9' <spec>
        Returns: Path to rebuilt SRPM
        """
```

### SCM Integration Module Design

#### SCM Abstraction

```python
# koji_adjutant/task_adapters/scm/base.py

from typing import Protocol, Dict, Optional

class SCMHandler(Protocol):
    """Protocol for SCM checkout handlers."""

    @staticmethod
    def is_scm_url(url: str) -> bool:
        """Check if URL matches this SCM type."""

    def __init__(self, url: str, options: Optional[Dict] = None):
        """Initialize handler for SCM URL."""

    def checkout(
        self,
        container_manager: ContainerManager,
        container_id: str,
        dest_dir: str,
    ) -> Dict[str, str]:
        """Checkout source to destination directory.

        Returns metadata: {
            'url': 'git://...',
            'commit': 'abc123...',
            'branch': 'main',
            'revision': '...',
        }
        """
```

#### Git Implementation

```python
# koji_adjutant/task_adapters/scm/git.py

class GitHandler:
    """Git SCM checkout handler."""

    @staticmethod
    def is_scm_url(url: str) -> bool:
        """Check if URL is a git URL."""
        # git://, git+http://, git+https://, https://...git

    def __init__(self, url: str, options: Optional[Dict] = None):
        """Parse git URL and extract branch/tag/commit."""
        self.url = url
        self.branch = options.get('branch', 'main')
        self.commit = options.get('commit')

    def checkout(
        self,
        container_manager: ContainerManager,
        container_id: str,
        dest_dir: str,
    ) -> Dict[str, str]:
        """Checkout git repository.

        Uses exec() to run:
        1. git clone <url> <dest>
        2. cd <dest> && git checkout <commit/branch>
        3. git rev-parse HEAD  # Get commit hash
        """
```

### Integration with Existing Components

#### BuildrootInitializer Enhancement

Add support for `srpm-build` install group:

```python
# koji_adjutant/buildroot/initializer.py

class BuildrootInitializer:
    def initialize(
        self,
        container_id: str,
        build_tag: dict,
        arch: str,
        install_group: str = "build",  # NEW: default "build", can be "srpm-build"
        repo_id: Optional[int] = None,
    ) -> None:
        """Initialize buildroot in container.

        For SRPM builds:
        - install_group="srpm-build" (smaller package set)
        - Still need repos, macros, but different packages
        """
```

#### PolicyResolver Integration

SRPM adapters use same policy resolution as buildArch:

```python
# Adapter code:
image = policy_resolver.resolve_image(
    session=session,
    build_tag=build_tag,
    arch="noarch",  # SRPM builds are noarch
    task_type="buildSRPMFromSCM",  # or "rebuildSRPM"
    event_id=event_id,
)
```

#### Monitoring Integration

SRPM tasks tracked same as buildArch:

```python
# In adapter execute_task():
task_registry = get_task_registry()
if task_registry:
    task_registry.register_task(
        task_id=ctx.task_id,
        task_type="buildSRPMFromSCM",
        srpm=task_params.get('url'),
        build_tag=task_params.get('build_tag'),
        container_id=container_id,
    )
```

---

## Implementation Approach

### Development Strategy

**Approach**: Iterative implementation with incremental testing

1. **Phase 1**: RebuildSRPM (simpler, no SCM)
   - Implement adapter skeleton
   - Add SRPM unpack logic
   - Add rebuild logic
   - Test with mock SRPM files

2. **Phase 2**: BuildSRPMFromSCM (complex, needs SCM)
   - Implement adapter skeleton
   - Add SCM module (git support only initially)
   - Add SRPM build logic
   - Test with public git repos

3. **Phase 3**: Integration and validation
   - Wire adapters into kojid task handlers
   - Test complete workflow (SCM → SRPM → RPM)
   - Validate with BuildArchAdapter
   - End-to-end testing

### Task Handler Integration

Adapters must be called from existing kojid task handlers:

```python
# In kojid.py - RebuildSRPM.handler()

class RebuildSRPM(BaseBuildTask):
    Methods = ['rebuildSRPM']

    def handler(self, srpm, build_tag, opts=None):
        # Existing mock-based code...

        # NEW: Try adapter-based execution
        try:
            from koji_adjutant.task_adapters.rebuild_srpm import RebuildSRPMAdapter
            from koji_adjutant.container.podman_manager import PodmanManager

            adapter = RebuildSRPMAdapter()
            container_manager = PodmanManager()

            ctx = TaskContext(
                task_id=self.id,
                work_dir=self.workdir,
                koji_mount_root='/mnt/koji',
            )

            task_params = {
                'srpm': srpm,
                'build_tag': build_tag,
                'opts': opts or {},
            }

            result = adapter.execute_task(
                container_manager=container_manager,
                container_spec=adapter.build_spec(ctx, task_params, self.session, self.event_id),
                task_params=task_params,
                log_sink=FileKojiLogSink(self.logger, ctx.task_id),
            )

            return result

        except ImportError:
            # Fallback to mock-based implementation
            self.logger.warning("Adapter not available, using mock-based buildroot")
            # ... existing code ...
```

### Code Reuse Strategy

**Leverage existing components**:
- `BaseTaskAdapter`: Container spec building patterns
- `BuildArchAdapter`: Mount configuration, logging, result formatting
- `BuildrootInitializer`: Repo setup, macro application
- `PolicyResolver`: Image selection
- `PodmanManager`: Container lifecycle

**New components**:
- `RebuildSRPMAdapter`: ~200-300 lines (similar to BuildArchAdapter)
- `BuildSRPMFromSCMAdapter`: ~300-400 lines (more complex)
- `SCMHandler` + `GitHandler`: ~200-300 lines
- Tests: ~500-800 lines

**Total new code**: ~1,200-1,800 lines

---

## Testing Strategy

### Unit Tests

#### RebuildSRPMAdapter Tests
```python
# tests/unit/test_rebuild_srpm_adapter.py

def test_build_spec_basic():
    """Test ContainerSpec creation for basic rebuild."""

def test_build_spec_with_policy():
    """Test image selection via PolicyResolver."""

def test_unpack_srpm():
    """Test SRPM unpacking logic."""

def test_rebuild_srpm_with_macros():
    """Test SRPM rebuild with dist tag macros."""

def test_validate_srpm_success():
    """Test SRPM validation with valid file."""

def test_validate_srpm_failure():
    """Test SRPM validation with invalid file."""

def test_format_result():
    """Test result dict formatting for hub."""

def test_error_handling():
    """Test error handling and cleanup."""
```

#### BuildSRPMFromSCMAdapter Tests
```python
# tests/unit/test_buildsrpm_scm_adapter.py

def test_build_spec_with_network():
    """Test ContainerSpec includes network enabled."""

def test_scm_url_parsing():
    """Test SCM URL parsing (git+https, branch, commit)."""

def test_checkout_git():
    """Test git checkout via SCMHandler."""

def test_build_srpm_make():
    """Test SRPM build via 'make srpm'."""

def test_build_srpm_rpmbuild():
    """Test SRPM build via 'rpmbuild -bs'."""

def test_spec_file_validation():
    """Test spec file sanity checks."""

def test_scm_checkout_failure():
    """Test handling of SCM checkout failures."""
```

#### SCM Module Tests
```python
# tests/unit/test_scm_handlers.py

def test_git_is_scm_url():
    """Test git URL detection."""

def test_git_checkout():
    """Test git clone and checkout."""

def test_git_commit_resolution():
    """Test getting commit hash after checkout."""

def test_git_auth_handling():
    """Test SSH key and token auth (if implemented)."""
```

### Integration Tests

```python
# tests/integration/test_srpm_workflow.py

def test_rebuild_srpm_end_to_end():
    """Test complete SRPM rebuild workflow.

    1. Start with valid SRPM
    2. Rebuild with RebuildSRPMAdapter
    3. Validate output SRPM
    4. Check logs and cleanup
    """

def test_buildsrpm_from_git():
    """Test complete SCM → SRPM workflow.

    1. Use public git repo (e.g., simple test package)
    2. Build SRPM with BuildSRPMFromSCMAdapter
    3. Validate output SRPM
    4. Check logs and cleanup
    """

def test_complete_build_workflow():
    """Test SCM → SRPM → RPM workflow.

    1. BuildSRPMFromSCMAdapter creates SRPM
    2. Pass SRPM to BuildArchAdapter
    3. Build RPM
    4. Validate complete workflow
    """

def test_policy_integration():
    """Test policy-driven image selection for SRPM builds."""

def test_monitoring_integration():
    """Test SRPM task tracking in monitoring API."""
```

### Acceptance Criteria

| ID | Criterion | Test Method |
|----|-----------|-------------|
| AC1 | RebuildSRPM adapter builds valid SRPM | Integration test |
| AC2 | BuildSRPMFromSCM adapter checks out git | Integration test |
| AC3 | BuildSRPMFromSCM adapter builds valid SRPM | Integration test |
| AC4 | Complete workflow (SCM → SRPM → RPM) works | Integration test |
| AC5 | Adapters integrate with BuildTask coordinator | Manual test with kojid |
| AC6 | Logs stream to Koji log system | Integration test |
| AC7 | Container cleanup on success | Unit + integration test |
| AC8 | Container cleanup on failure | Unit + integration test |
| AC9 | Policy resolver selects correct image | Unit test |
| AC10 | Monitoring API tracks SRPM tasks | Integration test |
| AC11 | Result format matches kojid expectations | Unit test |
| AC12 | Performance overhead < 10% | Performance test |

---

## Integration Plan

### Phase 1: RebuildSRPM Integration

**Week 1-2**

1. **Implement adapter** (3 days)
   - Create `koji_adjutant/task_adapters/rebuild_srpm.py`
   - Implement `build_spec()` method
   - Implement `execute_task()` method
   - Implement helper methods (unpack, rebuild, validate)

2. **Write tests** (2 days)
   - Unit tests for all methods
   - Integration test with mock SRPM
   - Error handling tests

3. **Integrate with kojid** (1 day)
   - Modify `RebuildSRPM.handler()` in kojid.py
   - Add adapter detection and fallback
   - Test with kojid task execution

4. **Validate** (1 day)
   - Run unit tests (target: 100% pass)
   - Run integration tests
   - Manual testing with kojid

### Phase 2: BuildSRPMFromSCM Integration

**Week 2-3**

1. **Implement SCM module** (2 days)
   - Create `koji_adjutant/task_adapters/scm/` module
   - Implement `SCMHandler` protocol
   - Implement `GitHandler` (git support only)

2. **Implement adapter** (3 days)
   - Create `koji_adjutant/task_adapters/buildsrpm_scm.py`
   - Implement `build_spec()` method with network enabled
   - Implement `execute_task()` method
   - Implement SCM checkout integration
   - Implement SRPM build logic

3. **Write tests** (2 days)
   - Unit tests for adapter methods
   - Unit tests for SCM handlers
   - Integration test with public git repo
   - Error handling tests

4. **Integrate with kojid** (1 day)
   - Modify `BuildSRPMFromSCMTask.handler()` in kojid.py
   - Add adapter detection and fallback
   - Test with kojid task execution

### Phase 3: End-to-End Validation

**Week 3**

1. **Complete workflow testing** (2 days)
   - Test SCM → SRPM → RPM flow
   - Test with multiple packages
   - Test error scenarios
   - Validate hub result format

2. **Performance testing** (1 day)
   - Measure SRPM build overhead
   - Compare to mock-based kojid
   - Optimize if needed

3. **Documentation** (1 day)
   - Update WORKFLOW.md
   - Document adapter usage
   - Update PROJECT_STATUS.md

4. **Code review and refinement** (1 day)
   - Address review feedback
   - Fix any issues found in testing
   - Final validation

---

## Risk Assessment

### Technical Risks

| Risk | Severity | Probability | Mitigation |
|------|----------|-------------|------------|
| **SCM checkout complexity** | HIGH | MEDIUM | Start with git only, add svn later if needed |
| **Network configuration issues** | MEDIUM | MEDIUM | Test thoroughly, document network requirements |
| **Authentication handling** | HIGH | LOW | Start with public repos, add auth support later |
| **SRPM validation edge cases** | MEDIUM | MEDIUM | Extensive testing with various SRPM formats |
| **BuildTask integration issues** | MEDIUM | LOW | Study existing kojid code carefully |
| **Container network isolation** | MEDIUM | LOW | Use podman default network, document requirements |
| **Performance overhead** | LOW | LOW | Existing buildArch has < 5% overhead |

### Schedule Risks

| Risk | Severity | Probability | Mitigation |
|------|----------|-------------|------------|
| **Underestimated complexity** | MEDIUM | MEDIUM | 2-3 week range allows buffer |
| **SCM integration takes longer** | MEDIUM | MEDIUM | Implement git first, defer svn/cvs |
| **Testing uncovers major issues** | HIGH | LOW | Incremental testing reduces risk |
| **Dependency on existing components** | LOW | LOW | Phase 2 components are stable |

### Deployment Risks

| Risk | Severity | Probability | Mitigation |
|------|----------|-------------|------------|
| **Hub compatibility issues** | HIGH | LOW | Match kojid result format exactly |
| **Production SCM access** | MEDIUM | MEDIUM | Test with representative repos |
| **Network policy conflicts** | MEDIUM | MEDIUM | Document network requirements clearly |

---

## Timeline and Milestones

### Detailed Schedule

**Total Duration**: 2-3 weeks (15-20 working days)

#### Week 1: RebuildSRPM + Design
- **Day 1-2**: Detailed design review, setup development environment
- **Day 3-5**: Implement RebuildSRPMAdapter
- **Day 6-7**: Write tests for RebuildSRPM
- **Milestone 1**: RebuildSRPM adapter functional ✓

#### Week 2: BuildSRPMFromSCM
- **Day 8-9**: Implement SCM module (git support)
- **Day 10-12**: Implement BuildSRPMFromSCMAdapter
- **Day 13-14**: Write tests for BuildSRPMFromSCM
- **Milestone 2**: BuildSRPMFromSCM adapter functional ✓

#### Week 3: Integration & Validation
- **Day 15-16**: Kojid integration and end-to-end testing
- **Day 17**: Performance testing and optimization
- **Day 18**: Documentation updates
- **Day 19-20**: Buffer for issues, code review, refinement
- **Milestone 3**: Phase 2.5 complete, ready for staging ✓

### Critical Path

```
Design (2 days)
  ↓
RebuildSRPM Implementation (5 days)
  ↓
BuildSRPMFromSCM Implementation (7 days)
  ↓
Integration & Testing (5 days)
  ↓
Documentation & Validation (1 day)
```

**Total Critical Path**: 20 days (~3 weeks)

### Go/No-Go Decision Points

**Milestone 1 Review** (End of Week 1):
- ✅ RebuildSRPM adapter compiles and passes tests
- ✅ Can rebuild a simple SRPM successfully
- ✅ Integrates with kojid handler
- **Decision**: Proceed to BuildSRPMFromSCM or address issues

**Milestone 2 Review** (End of Week 2):
- ✅ BuildSRPMFromSCM adapter compiles and passes tests
- ✅ Can checkout from public git repo
- ✅ Can build SRPM from checked-out source
- **Decision**: Proceed to integration testing or address issues

**Final Review** (End of Week 3):
- ✅ Complete workflow (SCM → SRPM → RPM) works
- ✅ All tests passing
- ✅ Performance acceptable (< 10% overhead)
- ✅ Documentation updated
- **Decision**: Declare Phase 2.5 complete and ready for staging

---

## Success Criteria

Phase 2.5 is considered successful when:

1. ✅ **RebuildSRPMAdapter implemented and tested**
   - Rebuilds SRPMs with correct dist tags
   - Integrates with kojid RebuildSRPM handler
   - Passes all unit and integration tests

2. ✅ **BuildSRPMFromSCMAdapter implemented and tested**
   - Checks out source from git repositories
   - Builds SRPMs from checked-out source
   - Integrates with kojid BuildSRPMFromSCMTask handler
   - Passes all unit and integration tests

3. ✅ **Complete build workflow functional**
   - User can run: `koji build f39 git://example.com/package.git`
   - BuildTask spawns buildSRPMFromSCM subtask (uses adapter)
   - SRPM is built and uploaded
   - BuildTask spawns buildArch subtasks (existing adapter)
   - RPMs are built and uploaded
   - Build completes successfully

4. ✅ **Testing complete**
   - Unit tests: 95%+ pass rate
   - Integration tests: 100% pass rate
   - End-to-end workflow: Validated with 3+ test packages
   - Performance: < 10% overhead vs mock-based kojid

5. ✅ **Documentation updated**
   - PROJECT_STATUS.md reflects Phase 2.5 completion
   - WORKFLOW.md includes SRPM adapter details
   - Adapter usage documented
   - Architecture diagrams updated

6. ✅ **Ready for staging deployment**
   - Code reviewed and approved
   - No critical bugs
   - Monitoring integration working
   - Logs streaming correctly

---

## Dependencies

### Required Components (Already Implemented)
- ✅ ContainerManager (PodmanManager)
- ✅ BaseTaskAdapter
- ✅ BuildrootInitializer
- ✅ PolicyResolver
- ✅ Monitoring (ContainerRegistry, TaskRegistry)
- ✅ Configuration (kojid.conf parsing)
- ✅ Logging (FileKojiLogSink)

### External Dependencies
- Podman 4.0+ (container runtime)
- Git (for SCM checkout)
- RPM tools (rpm, rpmbuild) - available in container images
- Network access (for git clone)
- Koji hub API (for policy resolution, buildconfig)

### Optional Dependencies (Nice to Have)
- SVN client (for svn:// URLs) - can be Phase 3
- CVS client (for cvs:// URLs) - rarely used, Phase 3
- SSH keys for private repos - can be Phase 3

---

## Appendix A: Adapter Interface

### Standard Adapter Pattern

All adapters follow this pattern:

```python
from koji_adjutant.task_adapters.base import BaseTaskAdapter, TaskContext

class MyAdapter(BaseTaskAdapter):
    """Adapter for X task type."""

    def build_spec(
        self,
        ctx: TaskContext,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> ContainerSpec:
        """Build container specification from task parameters."""
        # 1. Resolve image via PolicyResolver
        # 2. Configure mounts (workdir, koji storage)
        # 3. Set environment variables
        # 4. Configure network (if needed)
        # 5. Set labels for monitoring
        # 6. Return ContainerSpec

    def execute_task(
        self,
        container_manager: ContainerManager,
        container_spec: ContainerSpec,
        task_params: dict,
        log_sink: Optional[LogSink] = None,
    ) -> dict:
        """Execute task in container and return result."""
        # 1. Create and start container
        # 2. Initialize buildroot (if needed)
        # 3. Execute task-specific logic via exec()
        # 4. Collect artifacts
        # 5. Format result for hub
        # 6. Cleanup container
        # 7. Return result dict

    def format_result(self, container_id: str, task_params: dict) -> dict:
        """Format task result for koji hub."""
        # Return hub-compatible result dict
```

---

## Appendix B: Reference Links

### Code References
- **Original kojid**: `/home/siege/koji-adjutant/koji_adjutant/kojid.py`
  - `BuildSRPMFromSCMTask`: Line 5410-5570
  - `RebuildSRPM`: Line 5326-5410
- **Existing adapters**:
  - BuildArchAdapter: `/home/siege/koji-adjutant/koji_adjutant/task_adapters/buildarch.py`
  - CreaterepoAdapter: `/home/siege/koji-adjutant/koji_adjutant/task_adapters/createrepo.py`
- **Base adapter**: `/home/siege/koji-adjutant/koji_adjutant/task_adapters/base.py`

### Documentation References
- ADR 0001: Container lifecycle and manager boundaries
- ADR 0002: Container image bootstrap and security
- ADR 0003: Hub policy-driven image selection
- ADR 0004: Production buildroot container images
- Phase 2 Roadmap: `/home/siege/koji-adjutant/docs/planning/phase2-roadmap.md`
- WORKFLOW.md: `/home/siege/koji-adjutant/docs/WORKFLOW.md`

---

## Appendix C: SCM URL Examples

### Git URLs
```
git://example.com/package.git
git://example.com/package.git?#<branch>
git://example.com/package.git?#<commit-hash>
git+https://github.com/user/package.git
git+https://github.com/user/package.git?#main
https://github.com/user/package.git
```

### Git URL Parsing
```python
# Format: git://host/path[?query][#fragment]
# Fragment: branch name, tag, or commit hash
# Query: optional parameters

url = "git://example.com/package.git?#v1.0.0"
# → repo: git://example.com/package.git
# → ref: v1.0.0 (tag)

url = "git+https://github.com/user/pkg.git?#abc123"
# → repo: https://github.com/user/pkg.git
# → ref: abc123 (commit)
```

---

**Design Document Status**: ✅ COMPLETE - Ready for Implementation

**Next Step**: Create Phase 2.5 Implementation Roadmap and Schedule

---
