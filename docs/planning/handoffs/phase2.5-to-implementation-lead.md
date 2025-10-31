# Phase 2.5 Handoff: Strategic Planner to Implementation Lead

**Date**: 2025-10-31
**From**: Strategic Planner
**To**: Implementation Lead
**Status**: Ready for Implementation
**Priority**: CRITICAL - Blocks deployment

---

## Context

Critical gap identified on 2025-10-31: **SRPM task adapters are not implemented**, blocking all production deployment. Planning phase (Option 2) is now complete. Ready for implementation phase (Phase 2.5).

**Current State**:
- Phase 2 complete: BuildArchAdapter + CreaterepoAdapter working
- Gap: buildSRPMFromSCM and rebuildSRPM adapters missing
- Impact: Cannot run complete build workflows (SCM → SRPM → RPM)
- Deployment: BLOCKED until Phase 2.5 complete

---

## Planning Deliverables Complete ✅

1. **PROJECT_STATUS.md** - Updated to reflect gap
2. **Design Document** - 42 pages, comprehensive technical design
3. **Phase 2.5 Roadmap** - 28 pages, detailed 3-week schedule
4. **Stakeholder Brief** - 14 pages, executive summary
5. **ADR 0006** - Architectural decision for SRPM adapters
6. **Planning Index** - Navigation guide for all docs

**All documents**: `/home/siege/koji-adjutant/docs/planning/phase2.5-*`

---

## Your Mission: Phase 2.5 Implementation

**Timeline**: 2-3 weeks (15-20 working days)
**Scope**: Two adapters + SCM module + tests + integration

### Week 1: RebuildSRPM Adapter
- Implement adapter (~250 lines)
- Unit tests (95%+ pass rate)
- Kojid integration
- **Milestone 1**: RebuildSRPM functional

### Week 2: BuildSRPMFromSCM Adapter
- Implement SCM module (~300 lines)
- Implement adapter (~350 lines)
- Unit tests (95%+ pass rate)
- Kojid integration
- **Milestone 2**: BuildSRPMFromSCM functional

### Week 3: Integration & Validation
- End-to-end workflow tests
- Performance validation (< 10% overhead target)
- Documentation updates
- **Milestone 3**: Phase 2.5 complete

---

## Reference Materials

### Must Read (Priority Order)

1. **Design Document** (your technical blueprint)
   - Path: `/home/siege/koji-adjutant/docs/planning/phase2.5-srpm-adapters-design.md`
   - Sections: Architecture Design, Implementation Approach
   - Contains: Class designs, method signatures, code examples

2. **ADR 0006** (architectural decisions)
   - Path: `/home/siege/koji-adjutant/docs/architecture/decisions/0006-srpm-task-adapters.md`
   - Focus: Design rationale, alternatives considered, integration points

3. **Phase 2.5 Roadmap** (execution plan)
   - Path: `/home/siege/koji-adjutant/docs/planning/phase2.5-roadmap.md`
   - Focus: Daily schedule, deliverables, acceptance criteria

### Reference Implementations

**BuildArchAdapter** (follow this pattern):
- Path: `/home/siege/koji-adjutant/koji_adjutant/task_adapters/buildarch.py`
- Use as template for adapter structure

**Original kojid** (behavioral reference):
- Path: `/home/siege/koji-adjutant/koji_adjutant/kojid.py`
- RebuildSRPM: Line 5326-5410
- BuildSRPMFromSCMTask: Line 5410-5570

### Existing Components to Leverage

- **BaseTaskAdapter**: `koji_adjutant/task_adapters/base.py`
- **PodmanManager**: `koji_adjutant/container/podman_manager.py`
- **BuildrootInitializer**: `koji_adjutant/buildroot/initializer.py`
- **PolicyResolver**: `koji_adjutant/policy/resolver.py`

---

## Detailed Task Breakdown

### Task 1: RebuildSRPMAdapter (Week 1)

**File**: `koji_adjutant/task_adapters/rebuild_srpm.py`

**Requirements**:
```python
class RebuildSRPMAdapter(BaseTaskAdapter):
    """Rebuild existing SRPM with correct dist tags."""

    def build_spec(self, ctx, task_params, session, event_id) -> ContainerSpec:
        # Resolve image via PolicyResolver
        # Configure mounts (workdir, koji storage)
        # Set environment
        # Network: optional (not required)
        # Install group: srpm-build

    def execute_task(self, container_manager, container_spec, task_params, log_sink) -> dict:
        # Create and start container
        # Initialize buildroot (BuildrootInitializer)
        # Copy input SRPM to container
        # Unpack SRPM: rpm -iv --define '_topdir /builddir'
        # Apply build tag macros (dist tags)
        # Rebuild: rpmbuild -bs --define 'dist .el9'
        # Validate SRPM
        # Format result
        # Cleanup (guaranteed via try/finally)

    def unpack_srpm(self, container_id, srpm_path, dest_dir) -> dict:
        # Execute rpm -iv via container exec()

    def rebuild_srpm(self, container_id, spec_file, source_dir) -> str:
        # Execute rpmbuild -bs via container exec()

    def validate_srpm(self, srpm_path) -> dict:
        # Check file exists
        # Check is valid RPM
        # Check is source package
        # Validate name format
        # Return metadata
```

**Input Example**:
```python
{
    'srpm': 'work/12344/mypackage-1.0-1.src.rpm',
    'build_tag': 'f39-build',
    'opts': {'repo_id': 123}
}
```

**Output Example**:
```python
{
    'srpm': 'work/12345/mypackage-1.0-1.el9.src.rpm',
    'source': {'url': 'mypackage-1.0-1.src.rpm'},
    'logs': ['work/12345/build.log'],
    'brootid': 67890
}
```

**Container Spec**:
- Image: Policy-resolved (build_tag + arch=noarch + task_type=rebuildSRPM)
- Network: Optional (disabled or default)
- Install group: `srpm-build`
- Mounts: workdir + koji storage (standard)
- Labels: task_id, task_type, etc.

**Testing**:
- File: `tests/unit/test_rebuild_srpm_adapter.py`
- Coverage target: 80%+
- Test cases: spec building, unpacking, rebuilding, validation, errors

**Integration**:
- Modify `kojid.py` RebuildSRPM.handler() to detect and use adapter
- Add try/except with fallback to mock-based code
- Test with kojid task execution

---

### Task 2: SCM Module (Week 2, Part 1)

**Directory**: `koji_adjutant/task_adapters/scm/`

**Files**:
1. `__init__.py` - Module initialization
2. `base.py` - SCMHandler protocol
3. `git.py` - GitHandler implementation

**SCMHandler Protocol**:
```python
class SCMHandler(Protocol):
    @staticmethod
    def is_scm_url(url: str) -> bool:
        """Check if URL matches this SCM type."""

    def __init__(self, url: str, options: Optional[Dict] = None):
        """Parse URL and options."""

    def checkout(
        self,
        container_manager: ContainerManager,
        container_id: str,
        dest_dir: str,
    ) -> Dict[str, str]:
        """Checkout source, return metadata."""
```

**GitHandler Implementation**:
```python
class GitHandler:
    """Git SCM checkout handler."""

    @staticmethod
    def is_scm_url(url: str) -> bool:
        # Match: git://, git+https://, *.git

    def __init__(self, url: str, options: Optional[Dict] = None):
        # Parse URL: extract repo, branch/tag/commit

    def checkout(self, container_manager, container_id, dest_dir) -> Dict:
        # Execute: git clone <url> <dest>
        # Execute: cd <dest> && git checkout <ref>
        # Execute: git rev-parse HEAD  # Get commit hash
        # Return: {'url': ..., 'commit': ..., 'branch': ...}
```

**URL Examples**:
- `git://example.com/package.git`
- `git://example.com/package.git?#branch-name`
- `git+https://github.com/user/package.git`
- `https://github.com/user/package.git#v1.0.0`

**Testing**:
- File: `tests/unit/test_scm_handlers.py`
- Test cases: URL detection, parsing, checkout, commit resolution, errors

---

### Task 3: BuildSRPMFromSCMAdapter (Week 2, Part 2)

**File**: `koji_adjutant/task_adapters/buildsrpm_scm.py`

**Requirements**:
```python
class BuildSRPMFromSCMAdapter(BaseTaskAdapter):
    """Build SRPM from source control."""

    def build_spec(self, ctx, task_params, session, event_id) -> ContainerSpec:
        # Similar to RebuildSRPM but:
        # - Network: REQUIRED (enable network for SCM checkout)
        # - Install group: srpm-build + git

    def execute_task(self, container_manager, container_spec, task_params, log_sink) -> dict:
        # Create and start container
        # Initialize buildroot
        # Checkout source from SCM (via SCMHandler)
        # Detect build method (make srpm vs rpmbuild -bs)
        # Build SRPM
        # Validate SRPM
        # Format result (include SCM metadata)
        # Cleanup

    def checkout_scm(self, container_id, scm_url, dest_dir) -> dict:
        # Get appropriate SCMHandler
        # Execute checkout
        # Return metadata

    def build_srpm(self, container_id, spec_file, source_dir) -> str:
        # Check for Makefile with srpm target
        # If yes: make srpm
        # Else: rpmbuild -bs

    def validate_srpm(self, srpm_path) -> dict:
        # Same as RebuildSRPMAdapter
```

**Input Example**:
```python
{
    'url': 'git://example.com/package.git#main',
    'build_tag': 'f39-build',
    'opts': {'repo_id': 123}
}
```

**Output Example**:
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

**Container Spec**:
- Image: Policy-resolved
- Network: **REQUIRED** (network_mode="default")
- Install group: `srpm-build`
- Mounts: standard
- Labels: include scm_url

**Testing**:
- File: `tests/unit/test_buildsrpm_scm_adapter.py`
- Coverage target: 80%+
- Test cases: spec with network, SCM checkout, build methods, validation, errors

**Integration**:
- Modify `kojid.py` BuildSRPMFromSCMTask.handler() to use adapter
- Add try/except with fallback

---

### Task 4: End-to-End Testing (Week 3)

**File**: `tests/integration/test_srpm_workflow.py`

**Test Scenarios**:

1. **test_rebuild_srpm_end_to_end()**
   - Start with valid SRPM
   - Rebuild via RebuildSRPMAdapter
   - Validate output SRPM
   - Check logs and cleanup

2. **test_buildsrpm_from_git()**
   - Use public git repo (e.g., simple test package)
   - Build SRPM via BuildSRPMFromSCMAdapter
   - Validate output SRPM
   - Check logs and cleanup

3. **test_complete_build_workflow()**
   - BuildSRPMFromSCMAdapter: git → SRPM
   - Pass SRPM to BuildArchAdapter
   - BuildArchAdapter: SRPM → RPM
   - Validate complete workflow

4. **test_policy_integration()**
   - Test policy-driven image selection for SRPM tasks

5. **test_monitoring_integration()**
   - Test SRPM task tracking in monitoring API

**Performance Testing**:
- Measure overhead vs mock-based kojid
- Target: < 10%
- Document results

---

## Implementation Guidelines

### Code Style

**Follow Existing Patterns**:
- Study `buildarch.py` - use as template
- Use type hints consistently
- Follow PEP 8
- Use pathlib.Path for file operations
- Proper logging (logging.getLogger)

**Container Interaction**:
- Use `exec()` pattern (established in Phase 2.2)
- No shell scripts - structured Python commands
- Use `copy_to()` for file copying
- Stream logs via LogSink

**Error Handling**:
- Try/finally for guaranteed cleanup
- Specific exceptions (BuildError, ContainerError)
- Clear error messages
- Log exceptions with context

### Testing Standards

**Unit Tests**:
- Pytest framework
- Mock external dependencies (container operations)
- Test one thing per test
- Descriptive test names
- Target: 95%+ pass rate, 80%+ coverage

**Integration Tests**:
- Use real containers (podman)
- Use real git repos (public test repos)
- Test complete workflows
- Clean up containers after tests
- Target: 100% pass rate

### Documentation

**Docstrings**:
- All public methods
- Google-style format
- Include Args, Returns, Raises

**Inline Comments**:
- Explain "why", not "what"
- Complex logic only

---

## Kojid Integration Pattern

**Modify existing task handlers**:

```python
# In kojid.py

class RebuildSRPM(BaseBuildTask):
    Methods = ['rebuildSRPM']

    def handler(self, srpm, build_tag, opts=None):
        # Try adapter-based execution
        try:
            from koji_adjutant.task_adapters.rebuild_srpm import RebuildSRPMAdapter
            from koji_adjutant.container.podman_manager import PodmanManager
            from koji_adjutant.task_adapters.base import TaskContext
            from koji_adjutant.task_adapters.logging import FileKojiLogSink

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

            container_spec = adapter.build_spec(
                ctx, task_params, self.session, self.event_id
            )

            result = adapter.execute_task(
                container_manager=container_manager,
                container_spec=container_spec,
                task_params=task_params,
                log_sink=FileKojiLogSink(self.logger, ctx.task_id),
            )

            return result

        except ImportError:
            # Fallback to mock-based implementation
            self.logger.warning("Adapter not available, using mock-based buildroot")
            # ... existing mock code ...
```

**Key Points**:
- Add imports inside try block (graceful fallback)
- Create TaskContext from task handler attributes
- Pass session and event_id for policy resolution
- Use FileKojiLogSink for log streaming
- Keep existing mock code as fallback

---

## Acceptance Criteria

### Week 1 Complete When:
- [ ] RebuildSRPMAdapter file created
- [ ] All methods implemented
- [ ] Unit tests written (95%+ pass)
- [ ] Kojid integration working
- [ ] Can rebuild a simple SRPM successfully
- [ ] No critical bugs

### Week 2 Complete When:
- [ ] SCM module created (base + git)
- [ ] GitHandler functional
- [ ] BuildSRPMFromSCMAdapter file created
- [ ] All methods implemented
- [ ] Unit tests written (95%+ pass)
- [ ] Kojid integration working
- [ ] Can build SRPM from git successfully
- [ ] No critical bugs

### Week 3 Complete When:
- [ ] End-to-end workflow tests passing (100%)
- [ ] Complete workflow (git → SRPM → RPM) functional
- [ ] Performance validated (< 10% overhead)
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Code reviewed
- [ ] No critical or high-severity bugs

### Phase 2.5 Complete When:
- [ ] All acceptance criteria met
- [ ] PROJECT_STATUS.md updated
- [ ] Phase 2.5 completion report written
- [ ] Ready for koji-boxed integration testing

---

## Common Pitfalls to Avoid

1. **Container Cleanup**: Always use try/finally for cleanup
2. **Network Configuration**: BuildSRPMFromSCM needs network enabled
3. **Install Group**: Use `srpm-build`, not `build`
4. **SRPM Validation**: Comprehensive validation before upload
5. **Error Messages**: Clear, actionable error messages
6. **Test Coverage**: Don't skip error cases
7. **Policy Integration**: Use PolicyResolver for image selection
8. **Logging**: Stream to both Koji and filesystem

---

## Getting Help

**Stuck on architecture decisions?**
→ Consult Systems Architect (via cursor-agent)

**Container/podman issues?**
→ Consult Container Engineer (via cursor-agent)

**Testing strategy questions?**
→ Consult Quality Engineer (via cursor-agent)

**Schedule/priority questions?**
→ Consult Strategic Planner (me!)

---

## Deliverables Checklist

### Code Files
- [ ] `koji_adjutant/task_adapters/rebuild_srpm.py`
- [ ] `koji_adjutant/task_adapters/buildsrpm_scm.py`
- [ ] `koji_adjutant/task_adapters/scm/__init__.py`
- [ ] `koji_adjutant/task_adapters/scm/base.py`
- [ ] `koji_adjutant/task_adapters/scm/git.py`
- [ ] Kojid integration (modify `kojid.py`)

### Test Files
- [ ] `tests/unit/test_rebuild_srpm_adapter.py`
- [ ] `tests/unit/test_buildsrpm_scm_adapter.py`
- [ ] `tests/unit/test_scm_handlers.py`
- [ ] `tests/integration/test_srpm_workflow.py`

### Documentation
- [ ] Update `docs/WORKFLOW.md` (add SRPM tasks)
- [ ] Update `docs/PROJECT_STATUS.md` (Phase 2.5 complete)
- [ ] Create `docs/implementation/phase2.5-completion-report.md`

---

## Timeline

**Start**: Upon handoff acceptance
**Week 1 Due**: Day 7 (Milestone 1 review)
**Week 2 Due**: Day 14 (Milestone 2 review)
**Week 3 Due**: Day 20 (Milestone 3 review)
**Phase 2.5 Complete**: Day 20

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Unit test pass rate | ≥ 95% |
| Integration test pass rate | 100% |
| Code coverage (adapters) | ≥ 80% |
| Performance overhead | < 10% |
| Build success rate | ≥ 95% |
| Container cleanup rate | 100% |

---

## Next Steps

1. **Review all Phase 2.5 documents** (design, roadmap, ADR)
2. **Set up development environment**
3. **Begin Week 1: RebuildSRPM implementation**
4. **Daily progress updates** (standup format)
5. **Weekly milestone reviews**

---

## Questions Before Starting?

If you have questions about:
- **Technical approach**: Review design doc, ADR 0006
- **Schedule**: Review Phase 2.5 roadmap
- **Architecture**: Consult Systems Architect
- **Anything else**: Ask Strategic Planner (me!)

---

**Handoff Status**: ✅ READY

**Your mission**: Implement Phase 2.5 SRPM adapters to unblock deployment

**Good luck, Implementation Lead!** 🚀

---

**From**: Strategic Planner
**Date**: 2025-10-31
**Priority**: CRITICAL
