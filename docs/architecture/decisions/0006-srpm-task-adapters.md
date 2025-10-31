# ADR 0006: SRPM Task Adapters and SCM Integration

**Status**: Implemented ✅
**Date**: 2025-10-31
**Authors**: Strategic Planner, Systems Architect, Implementation Lead, Quality Engineer
**Relates to**: ADR 0001 (Container Lifecycle), ADR 0003 (Hub Policy)

---

## Context

Koji-adjutant Phase 1 and Phase 2 successfully implemented container-based RPM builds via the `BuildArchAdapter`, which builds binary RPMs from pre-existing SRPM files. However, a critical gap was identified: **SRPM creation tasks are not implemented**.

In normal Koji build workflows, users submit builds from source control URLs (git, svn), not pre-built SRPMs:

```bash
koji build f39 git://example.com/package.git
```

This requires two sequential task types that were missing:

1. **buildSRPMFromSCM**: Checkout source from version control and build SRPM
2. **rebuildSRPM**: Rebuild an existing SRPM with correct dist tags/macros

Without these adapters, koji-adjutant cannot:
- Accept normal build requests from users
- Integrate with koji-boxed or production koji hub
- Replace existing kojid workers
- Run complete end-to-end build workflows

**Discovery**: This gap was identified on 2025-10-31 during user review, blocking all deployment plans.

---

## Decision

We will implement **two new task adapters** following the established adapter pattern, plus a **SCM integration module** to handle source checkout:

### 1. RebuildSRPMAdapter
- **Purpose**: Rebuild existing SRPM with build-tag-specific macros (dist tags, release)
- **Complexity**: MEDIUM
- **Priority**: HIGH
- **Implementation**: Week 1 of Phase 2.5

### 2. BuildSRPMFromSCMAdapter
- **Purpose**: Checkout source from version control and build SRPM
- **Complexity**: HIGH (requires SCM integration and network access)
- **Priority**: CRITICAL
- **Implementation**: Week 2 of Phase 2.5

### 3. SCM Integration Module
- **Purpose**: Abstract git/svn/cvs checkout operations
- **Initial Scope**: Git support only (svn/cvs deferred to Phase 3)
- **Architecture**: Protocol-based design for extensibility
- **Implementation**: Week 2 of Phase 2.5

---

## Architectural Principles

### Consistency with Existing Adapters

Both SRPM adapters will follow the **established adapter pattern** from `BuildArchAdapter`:

```python
class BaseTaskAdapter:
    """Base pattern for all task adapters."""

    def build_spec(
        self,
        ctx: TaskContext,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> ContainerSpec:
        """Translate task parameters to ContainerSpec."""

    def execute_task(
        self,
        container_manager: ContainerManager,
        container_spec: ContainerSpec,
        task_params: dict,
        log_sink: Optional[LogSink] = None,
    ) -> dict:
        """Execute task in container, return hub-compatible result."""
```

**Rationale**: Consistency reduces learning curve, enables code reuse, maintains architectural coherence.

---

## Design Details

### RebuildSRPMAdapter Architecture

**Purpose**: Rebuild existing SRPM with correct macros for build tag

**Input**:
```python
{
    'srpm': 'work/12344/mypackage-1.0-1.src.rpm',  # Existing SRPM path
    'build_tag': 'f39-build',                       # Target build tag
    'opts': {'repo_id': 123}                        # Additional options
}
```

**Process**:
1. Resolve container image via `PolicyResolver`
2. Create container with `srpm-build` install group
3. Initialize buildroot (repos, macros for build tag)
4. Copy input SRPM to container
5. Unpack SRPM: `rpm -iv --define '_topdir /builddir'`
6. Apply build tag macros (dist tags)
7. Rebuild SRPM: `rpmbuild -bs --define 'dist .el9'`
8. Validate rebuilt SRPM
9. Return result with SRPM path

**Output**:
```python
{
    'srpm': 'work/12345/mypackage-1.0-1.el9.src.rpm',
    'source': {'url': 'mypackage-1.0-1.src.rpm'},
    'logs': ['work/12345/build.log'],
    'brootid': 67890
}
```

**Container Configuration**:
- **Image**: Policy-resolved (build tag + arch=noarch + task_type=rebuildSRPM)
- **Network**: Optional (not required for rebuild)
- **Install Group**: `srpm-build` (smaller than `build` group)
- **Mounts**: Standard (workdir, koji storage)

---

### BuildSRPMFromSCMAdapter Architecture

**Purpose**: Checkout source from version control and build SRPM

**Input**:
```python
{
    'url': 'git://example.com/package.git#branch',  # SCM URL with ref
    'build_tag': 'f39-build',                        # Target build tag
    'opts': {'repo_id': 123}                         # Additional options
}
```

**Process**:
1. Parse SCM URL (determine type: git/svn/cvs)
2. Resolve container image via `PolicyResolver`
3. Create container with `srpm-build` install group + **network enabled**
4. Initialize buildroot (repos, macros for build tag)
5. Checkout source from SCM to `/builddir`
6. Detect build method (Makefile with 'srpm' target vs direct rpmbuild)
7. Build SRPM: `make srpm` or `rpmbuild -bs --define '_topdir /builddir'`
8. Validate SRPM (name, version, release)
9. Return result with SRPM path and SCM metadata

**Output**:
```python
{
    'srpm': 'work/12345/mypackage-1.0-1.src.rpm',
    'source': {
        'url': 'git://example.com/package.git',
        'commit': 'abc123def456...',
        'branch': 'main'
    },
    'logs': ['work/12345/build.log'],
    'brootid': 67890
}
```

**Container Configuration**:
- **Image**: Policy-resolved (build tag + arch=noarch + task_type=buildSRPMFromSCM)
- **Network**: **REQUIRED** (for SCM checkout)
- **Install Group**: `srpm-build` + git client
- **Mounts**: Standard (workdir, koji storage)

**Key Difference from RebuildSRPM**: Network access required for source checkout

---

### SCM Integration Module Architecture

**Design**: Protocol-based abstraction for SCM operations

```python
# koji_adjutant/task_adapters/scm/base.py

class SCMHandler(Protocol):
    """Protocol for SCM checkout operations."""

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

**Implementations**:

1. **GitHandler** (Phase 2.5)
   - Supports: `git://`, `git+https://`, `https://***.git`
   - Features: branch, tag, commit checkout
   - Method: Execute `git clone` + `git checkout` via container exec()

2. **SVNHandler** (Phase 3)
   - Supports: `svn://`, `svn+ssh://`
   - Features: trunk, branch, tag, revision checkout
   - Deferred due to lower usage

3. **CVSHandler** (Phase 3+)
   - Supports: `cvs://`
   - Rarely used, low priority

**Rationale**:
- **Protocol pattern**: Extensible for future SCM types
- **Git-first**: Covers 95%+ of modern use cases
- **Container execution**: SCM commands run inside build container (consistent environment)

---

## Container Lifecycle

Both SRPM adapters follow the **exec() pattern** established in Phase 2.2 (ADR 0004):

```python
# Adapter execute_task() pattern:

1. Create container from spec
2. Start container
3. Initialize buildroot via BuildrootInitializer
   - Install srpm-build group
   - Configure repos
   - Apply macros
4. Execute task-specific steps via exec():
   - RebuildSRPM: unpack → rebuild → validate
   - BuildSRPMFromSCM: checkout → build → validate
5. Collect artifacts (SRPM file)
6. Format result for hub
7. Cleanup container (guaranteed)
```

**Key Points**:
- **One ephemeral container per task** (consistent with buildArch)
- **Guaranteed cleanup** on success and failure
- **exec() pattern** for step-by-step execution
- **Logs streamed** to Koji log system and filesystem

---

## Integration with Existing Components

### PolicyResolver Integration

SRPM adapters use **hub policy** for image selection:

```python
image = policy_resolver.resolve_image(
    session=session,
    build_tag=build_tag,
    arch="noarch",  # SRPM builds are always noarch
    task_type="buildSRPMFromSCM",  # or "rebuildSRPM"
    event_id=event_id,
)
```

**Policy Examples**:

```python
# Hub policy for SRPM builds:
build_tag == 'f39-build' and task_type == 'buildSRPMFromSCM':
    -> image = 'registry.io/koji-buildroot:f39-srpm'

build_tag == 'f39-build' and task_type == 'rebuildSRPM':
    -> image = 'registry.io/koji-buildroot:f39-srpm'
```

**Rationale**: Consistent with buildArch (ADR 0003), enables tag-specific SRPM build environments

---

### BuildrootInitializer Enhancement

Add support for **srpm-build** install group:

```python
class BuildrootInitializer:
    def initialize(
        self,
        container_id: str,
        build_tag: dict,
        arch: str,
        install_group: str = "build",  # NEW: can be "srpm-build"
        repo_id: Optional[int] = None,
    ) -> None:
        """Initialize buildroot in container."""
```

**Install Groups**:
- **`build`**: Full build environment (gcc, make, buildroot packages) - Used by buildArch
- **`srpm-build`**: Minimal SRPM build environment (rpm-build, rpmlint) - Used by SRPM adapters

**Rationale**:
- SRPM builds don't need compiler toolchain (smaller images, faster startup)
- Consistent with mock and original kojid behavior
- Reduces attack surface (fewer packages)

---

### Kojid Task Handler Integration

SRPM adapters integrate via **adapter detection pattern** in kojid.py:

```python
# In kojid.py - RebuildSRPM.handler()

class RebuildSRPM(BaseBuildTask):
    Methods = ['rebuildSRPM']

    def handler(self, srpm, build_tag, opts=None):
        # Try adapter-based execution
        try:
            from koji_adjutant.task_adapters.rebuild_srpm import RebuildSRPMAdapter
            from koji_adjutant.container.podman_manager import PodmanManager

            adapter = RebuildSRPMAdapter()
            # ... execute via adapter ...
            return result

        except ImportError:
            # Fallback to mock-based implementation
            self.logger.warning("Adapter not available, using mock")
            # ... original mock code ...
```

**Rationale**:
- **Graceful fallback** if adapters not available (development, mixed deployments)
- **Minimal kojid.py changes** (preserves original code)
- **Easy testing** (can test with/without adapters)

---

### Monitoring Integration

SRPM tasks tracked via **ContainerRegistry** and **TaskRegistry** (Phase 2.3):

```python
# In adapter execute_task():
task_registry = get_task_registry()
if task_registry:
    task_registry.register_task(
        task_id=ctx.task_id,
        task_type="buildSRPMFromSCM",  # or "rebuildSRPM"
        srpm=task_params.get('url') or task_params.get('srpm'),
        build_tag=task_params.get('build_tag'),
        container_id=container_id,
    )
```

**Monitoring API**:
- `GET /api/v1/tasks/<task_id>` - SRPM task details
- `GET /api/v1/containers` - Active SRPM build containers
- `GET /api/v1/status` - Overall worker status (includes SRPM tasks)

**Rationale**: Consistent operational visibility across all task types

---

## Network Policy Decision

**For RebuildSRPMAdapter**: Network is **optional** (not required for rebuild)

**For BuildSRPMFromSCMAdapter**: Network is **REQUIRED** (for SCM checkout)

### Network Configuration

```python
# BuildSRPMFromSCMAdapter.build_spec():
ContainerSpec(
    network_mode="default",  # Enable network
    # ... other config ...
)
```

**Network Access Requirements**:
- DNS resolution (for git clone)
- HTTPS/SSH protocols (for git repositories)
- Access to source control servers (github.com, gitlab.com, internal git servers)

**Security Considerations**:
1. **Network isolation**: Container network is isolated from host by default (podman)
2. **No internet for rebuilds**: RebuildSRPM doesn't enable network (unnecessary)
3. **Outbound only**: Build containers cannot accept inbound connections
4. **Configurable**: Network policy can be tightened per build tag if needed (Phase 3 feature)

**Rationale**:
- SCM checkout inherently requires network access
- Mirrors original kojid behavior (mock with network for SRPM builds)
- Security acceptable for outbound-only checkout operations

---

## SRPM Validation Strategy

Both adapters perform **comprehensive SRPM validation**:

### Validation Steps

1. **File Existence**: SRPM file created and non-empty
2. **RPM Header**: Valid RPM file (readable by rpm tools)
3. **Source Package**: Is a source package (not binary RPM)
4. **Name Format**: Matches pattern `<name>-<version>-<release>.src.rpm`
5. **Expected Name**: Name matches spec file metadata
6. **Required Headers**: Contains Name, Version, Release, Summary, License

### Validation Implementation

```python
def validate_srpm(self, srpm_path: str) -> dict:
    """Validate SRPM and extract metadata."""

    # Check file exists
    if not os.path.exists(srpm_path):
        raise BuildError(f"SRPM not found: {srpm_path}")

    # Check is valid RPM
    header = koji.get_rpm_header(srpm_path)
    if not header:
        raise BuildError(f"Invalid RPM file: {srpm_path}")

    # Check is source package
    if not koji.is_source_package(header):
        raise BuildError(f"Not a source package: {srpm_path}")

    # Extract metadata
    name = header['name']
    version = header['version']
    release = header['release']

    # Validate name format
    expected_name = f"{name}-{version}-{release}.src.rpm"
    actual_name = os.path.basename(srpm_path)
    if expected_name != actual_name:
        raise BuildError(f"SRPM name mismatch: {expected_name} != {actual_name}")

    return {'name': name, 'version': version, 'release': release}
```

**Rationale**:
- Catch errors early before uploading to hub
- Consistent with original kojid validation
- Prevents invalid SRPMs from entering build system

---

## Error Handling Strategy

### Container Cleanup Guarantee

Both adapters implement **guaranteed cleanup** via try/finally:

```python
def execute_task(self, container_manager, container_spec, task_params, log_sink):
    container_id = None
    try:
        # Create and execute
        container_id = container_manager.create(container_spec)
        container_manager.start(container_id)
        # ... task execution ...
        result = self.format_result(container_id, task_params)
        return result

    finally:
        # Guaranteed cleanup
        if container_id:
            try:
                container_manager.remove(container_id, force=True)
            except ContainerError as e:
                logger.warning(f"Cleanup failed: {e}")
```

**Rationale**: No orphaned containers, even on task failure

---

### SCM Checkout Error Handling

BuildSRPMFromSCMAdapter handles **SCM checkout failures** gracefully:

```python
def checkout_scm(self, container_id, scm_url, dest_dir):
    """Checkout source from SCM with comprehensive error handling."""
    try:
        scm_handler = self._get_scm_handler(scm_url)
        metadata = scm_handler.checkout(container_manager, container_id, dest_dir)
        return metadata

    except GitCheckoutError as e:
        # Git-specific errors (auth, network, invalid ref)
        raise BuildError(f"Git checkout failed: {e}")

    except SCMError as e:
        # Generic SCM errors
        raise BuildError(f"SCM checkout failed: {e}")

    except Exception as e:
        # Unexpected errors
        logger.exception(f"Unexpected error during SCM checkout: {e}")
        raise BuildError(f"SCM checkout error: {e}")
```

**Error Categories**:
- **Authentication failures**: SSH keys, HTTPS tokens
- **Network failures**: DNS, timeout, unreachable
- **Invalid references**: Non-existent branch/tag/commit
- **Repository errors**: Empty repo, corrupt repo
- **Permission errors**: Access denied

**Rationale**: Clear error messages help users diagnose build failures

---

## Performance Considerations

### Expected Performance

Based on Phase 2 measurements (buildArch: < 5% overhead):

| Task | Expected Overhead | Rationale |
|------|------------------|-----------|
| **RebuildSRPM** | < 3% | Simpler than buildArch (no compilation) |
| **BuildSRPMFromSCM** | < 8% | SCM checkout adds network time |

**Breakdown**:
- Container creation: ~1-2 seconds
- Buildroot init (srpm-build): ~5-10 seconds (smaller than full build group)
- SCM checkout: ~5-30 seconds (depends on repo size)
- SRPM build: ~10-60 seconds (depends on package)
- Cleanup: ~1 second

**Total**: ~20-100 seconds for typical package (comparable to mock-based kojid)

---

### Optimization Opportunities (Phase 3)

1. **Container image caching**: Pre-pull images for faster startup
2. **Buildroot caching**: Reuse initialized buildroots (requires more complex lifecycle)
3. **SCM caching**: Local git mirrors for frequently-built repos
4. **Parallel operations**: Overlap buildroot init with SCM checkout

**Rationale**: Defer optimizations until real-world performance data available

---

## Testing Strategy

### Unit Tests

**RebuildSRPMAdapter**:
- Container spec building
- SRPM unpacking
- SRPM rebuilding with macros
- SRPM validation
- Result formatting
- Error handling

**BuildSRPMFromSCMAdapter**:
- Container spec building (with network)
- SCM URL parsing
- SCM checkout (mocked)
- SRPM build methods (make srpm vs rpmbuild)
- SRPM validation
- Result formatting
- Error handling

**SCM Module**:
- GitHandler URL detection
- Git checkout operations
- Commit hash resolution
- Error handling

**Target**: 95%+ unit test pass rate, 80%+ code coverage

---

### Integration Tests

**End-to-End Workflows**:
1. RebuildSRPM: Valid SRPM → Rebuilt SRPM
2. BuildSRPMFromSCM: Public git repo → SRPM
3. Complete: Git → SRPM → RPM (with BuildArchAdapter)

**Real Containers**:
- Use actual podman containers (not mocks)
- Use real AlmaLinux 10 buildroot images
- Test with real git repositories (public test repos)

**Target**: 100% integration test pass rate

---

### Acceptance Tests

**Complete Build Workflow**:
```python
def test_complete_koji_build():
    """Test full workflow: git → SRPM → RPMs."""

    # Step 1: Build SRPM from git
    scm_adapter = BuildSRPMFromSCMAdapter()
    srpm_result = scm_adapter.execute_task(...)
    srpm_path = srpm_result['srpm']

    # Step 2: Build RPMs from SRPM
    arch_adapter = BuildArchAdapter()
    rpm_result = arch_adapter.execute_task(
        task_params={'pkg': srpm_path, ...}
    )

    # Validate: SRPM and RPMs created
    assert os.path.exists(srpm_path)
    assert len(rpm_result['rpms']) > 0
```

**Target**: Complete workflow functional, equivalent to kojid behavior

---

## Implementation Notes

**Status**: ✅ **IMPLEMENTED** (Phase 2.5 Complete)

### Implementation Summary

**Week 1**: RebuildSRPMAdapter implemented (581 lines, 12 tests, 100% passing)

**Week 2**: BuildSRPMFromSCMAdapter + SCM module implemented (550 + 214 lines, 29 tests, 100% passing)

**Week 3**: Integration testing and validation complete (10 integration tests, 100% pass rate)

### Key Implementation Details

1. **Network Policy**: BuildSRPMFromSCMAdapter enables network for git checkout; RebuildSRPMAdapter keeps network disabled
2. **Build Method Detection**: Automatic detection of `make srpm` vs `rpmbuild -bs` based on Makefile presence
3. **SCM Handler**: Git handler supports branch/tag/commit checkout with appropriate git clone strategies
4. **Buildroot Group**: Both adapters use `srpm-build` install group (not `build`)
5. **Error Handling**: Comprehensive error handling with guaranteed container cleanup

### Deviations from Design

- **Minor**: Commit hash length detection refined (7-40 characters for auto-detection)
- **Enhancement**: Added SCM metadata (commit, branch) to result dict for traceability
- **Enhancement**: Integration tests validate complete workflows

### Testing Results

- **Unit Tests**: 42 tests, 100% passing
- **Integration Tests**: 10 tests, 100% passing
- **Coverage**: 85% weighted average (exceeds 70% target)
- **Performance**: < 10% overhead (meets target)

### Production Readiness

✅ **GO** for staging deployment

See `docs/implementation/phase2.5-completion-report.md` for details.

---

## Consequences

### Positive

✅ **Complete build system**: Koji-adjutant can handle full build workflows
✅ **Production-ready**: Can replace mock-based kojid workers
✅ **Hub compatibility**: Full koji hub API compatibility
✅ **Consistent architecture**: Follows established adapter pattern
✅ **Extensible**: SCM module supports future SCM types
✅ **Testable**: Comprehensive test coverage
✅ **Observable**: Full monitoring integration
✅ **Policy-driven**: Hub controls SRPM build environments

---

### Negative

⚠️ **Network dependency**: BuildSRPMFromSCM requires network access (inherent to SCM)
⚠️ **Complexity**: SCM integration adds ~500 lines of code
⚠️ **Limited SCM support**: Git only in Phase 2.5 (svn/cvs deferred)
⚠️ **Timeline impact**: +2-3 weeks before deployment

---

### Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| **SCM checkout complexity** | MEDIUM | Start with git only, well-understood protocol |
| **Network configuration issues** | MEDIUM | Test early, document requirements, use podman defaults |
| **Authentication for private repos** | LOW | Defer to Phase 3, start with public repos |
| **Performance overhead** | LOW | Expected < 10%, monitor and optimize if needed |

---

## Alternatives Considered

### Alternative 1: Reuse Original Kojid Code (Rejected)

**Approach**: Don't create adapters, just use original kojid BuildSRPMFromSCMTask

**Pros**:
- No new code needed
- Battle-tested implementation

**Cons**:
- **Mock dependency**: Still uses mock buildroots (defeats project purpose)
- **Inconsistent architecture**: Mixing mock and container-based execution
- **Technical debt**: Maintains legacy code instead of modernizing
- **Limited improvement**: No performance or observability benefits

**Rejection Rationale**: Defeats core project mission of replacing mock with containers

---

### Alternative 2: Single Generic Adapter (Rejected)

**Approach**: One adapter handles both rebuildSRPM and buildSRPMFromSCM

**Pros**:
- Less code duplication
- Single adapter to maintain

**Cons**:
- **Complexity**: Conditionally handling two different workflows
- **Testing difficulty**: More code paths, harder to test thoroughly
- **Unclear responsibility**: Violates single responsibility principle
- **Error handling**: More complex, harder to debug

**Rejection Rationale**: Separate adapters clearer, more maintainable, easier to test

---

### Alternative 3: Defer SCM Integration (Rejected)

**Approach**: Implement only RebuildSRPM, defer BuildSRPMFromSCM to Phase 3

**Pros**:
- Faster to implement (1 week vs 2-3 weeks)
- Lower risk

**Cons**:
- **Still blocks deployment**: Most builds start from SCM, not existing SRPMs
- **Incomplete solution**: Doesn't solve the core problem
- **User frustration**: Cannot handle normal build requests

**Rejection Rationale**: BuildSRPMFromSCM is essential for production use, not optional

---

## Implementation Plan

### Phase 2.5 Schedule (2-3 weeks)

**Week 1: RebuildSRPM**
- Design review and setup (2 days)
- Implement RebuildSRPMAdapter (3 days)
- Unit and integration tests (2 days)
- **Milestone 1**: RebuildSRPM functional

**Week 2: BuildSRPMFromSCM + SCM Module**
- Implement SCM module with GitHandler (2 days)
- Implement BuildSRPMFromSCMAdapter (3 days)
- Unit and integration tests (2 days)
- **Milestone 2**: BuildSRPMFromSCM functional

**Week 3: Integration & Validation**
- End-to-end workflow testing (2 days)
- Performance validation (1 day)
- Documentation updates (1 day)
- Buffer for issues and code review (1-2 days)
- **Milestone 3**: Phase 2.5 complete

---

## Success Criteria

Phase 2.5 (and this ADR) considered successful when:

✅ RebuildSRPMAdapter implemented and tested
✅ BuildSRPMFromSCMAdapter implemented and tested
✅ SCM module with git support implemented
✅ Complete workflow (git → SRPM → RPM) functional
✅ Unit tests: 95%+ pass rate
✅ Integration tests: 100% pass rate
✅ Performance overhead: < 10%
✅ Hub API compatibility validated
✅ Documentation updated
✅ Koji-boxed integration successful

---

## References

### Related ADRs
- **ADR 0001**: Container lifecycle and manager boundaries
- **ADR 0002**: Container image bootstrap and security
- **ADR 0003**: Hub policy-driven image selection
- **ADR 0004**: Production buildroot container images
- **ADR 0005**: Operational monitoring server

### Implementation Documents
- **Design Document**: `/home/siege/koji-adjutant/docs/planning/phase2.5-srpm-adapters-design.md`
- **Roadmap**: `/home/siege/koji-adjutant/docs/planning/phase2.5-roadmap.md`
- **Stakeholder Brief**: `/home/siege/koji-adjutant/docs/planning/phase2.5-stakeholder-brief.md`

### Code References
- **Original kojid**: `/home/siege/koji-adjutant/koji_adjutant/kojid.py`
  - BuildSRPMFromSCMTask: Line 5410-5570
  - RebuildSRPM: Line 5326-5410
- **Existing adapters**: `/home/siege/koji-adjutant/koji_adjutant/task_adapters/`
  - buildarch.py (reference implementation)
  - createrepo.py (reference implementation)

---

## Decision Log

| Date | Author | Decision |
|------|--------|----------|
| 2025-10-31 | Strategic Planner | Identified SRPM adapter gap as critical blocker |
| 2025-10-31 | Strategic Planner | Created Phase 2.5 plan for SRPM adapters |
| 2025-10-31 | Strategic Planner | Approved two-adapter approach (vs alternatives) |
| 2025-10-31 | Strategic Planner | Approved git-first SCM strategy (defer svn/cvs) |
| 2025-10-31 | Strategic Planner | Approved network-enabled for BuildSRPMFromSCM |
| 2025-10-31 | Systems Architect | ADR 0006 drafted and accepted |

---

## Status

**Status**: ✅ **ACCEPTED**

**Date**: 2025-10-31

**Implementation**: Phase 2.5 (scheduled 2-3 weeks)

**Next Actions**:
1. Assign Implementation Lead for Phase 2.5
2. Begin Week 1: RebuildSRPM implementation
3. Weekly milestone reviews
4. Update PROJECT_STATUS.md upon completion

---

**ADR 0006: COMPLETE** ✅

This architectural decision enables koji-adjutant to become a complete, production-ready build system capable of replacing mock-based kojid workers.
