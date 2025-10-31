# Phase 2.5 Week 3 Handoff: Integration Testing & Validation

**Date**: 2025-10-31
**From**: Strategic Planner
**To**: Quality Engineer
**Status**: Ready for Week 3 - Final Validation
**Priority**: CRITICAL - Final Phase 2.5 Milestone

---

## Context

**Week 1 Status**: ✅ **COMPLETE** - RebuildSRPMAdapter (12/12 tests passing, 100%)

**Week 2 Status**: ✅ **95% COMPLETE** - BuildSRPMFromSCMAdapter + SCM module
- 29/31 tests passing (93.5%)
- 2 minor test failures (edge cases)
- All core functionality working

**Week 3 Mission**: Validate complete SRPM workflow, fix remaining issues, declare Phase 2.5 COMPLETE

---

## Week 3 Objectives

### Primary Goals

1. **Fix Remaining Test Failures** (2 tests)
2. **Integration Testing** - Validate complete workflows
3. **Performance Validation** - Measure overhead
4. **Documentation Updates** - Phase 2.5 completion
5. **Production Readiness Assessment** - Final go/no-go

### Success Criteria

- ✅ All tests passing (100% pass rate)
- ✅ End-to-end workflow functional (git → SRPM → RPM)
- ✅ Performance overhead < 10%
- ✅ No critical or high-severity bugs
- ✅ Documentation complete and accurate
- ✅ Phase 2.5 completion report written

---

## Task Breakdown

### Task 1: Fix Failing Tests (Priority 1)

**Timeline**: Day 1 (1-2 hours)

#### Failing Test 1: `test_checkout_failure_checkout_commit`
**File**: `tests/unit/test_scm_handlers.py`
**Line**: ~159
**Issue**: Test expects `ContainerError` with message "Git checkout commit failed" but error not raised properly

**Analysis Needed**:
```python
def test_checkout_failure_checkout_commit(self):
    """Test git checkout failure for specific commit."""
    handler = GitHandler("git://example.com/repo.git", {"commit": "abc123"})
    handle = ContainerHandle(container_id="test-container")
    mock_manager = MagicMock()
    mock_manager.exec.side_effect = [
        0,  # mkdir succeeds
        0,  # git clone succeeds
        1,  # git checkout commit fails
    ]

    with pytest.raises(ContainerError, match="Git checkout commit failed"):
        handler.checkout(mock_manager, handle, "/builddir/source")
```

**Likely Fix**: Check `koji_adjutant/task_adapters/scm/git.py` - ensure commit checkout failure raises proper ContainerError with correct message.

#### Failing Test 2: `test_run_success_with_srpm`
**File**: `tests/unit/test_buildsrpm_scm_adapter.py`
**Line**: ~392
**Issue**: AssertionError + policy resolver error "Policy must be a dict"

**Error Message**:
```
ERROR koji_adjutant.policy.resolver:resolver.py:199
Policy must be a dict, got <class 'unittest.mock.MagicMock'>
```

**Analysis Needed**:
- Test is calling PolicyResolver with improper mock
- Need to mock `session.getTag()` to return proper dict structure
- Or mock PolicyResolver entirely

**Likely Fix**: Update test mocking to provide proper tag dict structure when policy resolution is attempted.

**Deliverables**:
- [ ] Both tests passing
- [ ] No new test failures introduced
- [ ] Run full test suite to confirm

---

### Task 2: Integration Testing (Priority 1)

**Timeline**: Days 2-3 (2 days)

#### Test Scenario 1: RebuildSRPM End-to-End

**Objective**: Verify RebuildSRPM adapter works with real container

**Steps**:
1. Create a real test SRPM (simple package)
2. Use PodmanManager to execute RebuildSRPM adapter
3. Verify rebuilt SRPM created with correct dist tags
4. Validate container cleanup

**Expected Result**: SRPM rebuilt successfully, container cleaned up

**Test File**: Create `tests/integration/test_rebuild_srpm_integration.py`

```python
"""Integration tests for RebuildSRPM adapter with real containers."""

import pytest
from pathlib import Path
from koji_adjutant.container.podman_manager import PodmanManager
from koji_adjutant.task_adapters.rebuild_srpm import RebuildSRPMAdapter
from koji_adjutant.task_adapters.base import TaskContext
from koji_adjutant.task_adapters.logging import FileKojiLogSink

@pytest.mark.integration
def test_rebuild_srpm_real_container(tmp_path):
    """Test RebuildSRPM with real podman container."""
    # Setup
    adapter = RebuildSRPMAdapter()
    manager = PodmanManager()

    ctx = TaskContext(
        task_id=99999,
        work_dir=tmp_path,
        koji_mount_root=tmp_path / "koji",
        environment={},
    )

    # Create mock SRPM or use existing test SRPM
    # ... test implementation ...

    # Verify result
    assert exit_code == 0
    assert result['srpm'] != ''
```

#### Test Scenario 2: BuildSRPMFromSCM End-to-End

**Objective**: Verify BuildSRPMFromSCM adapter can checkout from git and build SRPM

**Steps**:
1. Use a public test git repository (simple package)
2. Execute BuildSRPMFromSCMAdapter with real container
3. Verify source checkout successful
4. Verify SRPM built from checked-out source
5. Validate container cleanup

**Expected Result**: SRPM built from git source, container cleaned up

**Test Git Repo Options**:
- Create minimal test repo with spec file
- Or use public koji test repo if available

**Test File**: Create `tests/integration/test_buildsrpm_scm_integration.py`

#### Test Scenario 3: Complete Workflow (git → SRPM → RPM)

**Objective**: Verify complete build workflow using both adapters

**Steps**:
1. BuildSRPMFromSCMAdapter: git → SRPM
2. Pass SRPM path to BuildArchAdapter: SRPM → RPM
3. Verify complete artifact chain
4. Validate all containers cleaned up

**Expected Result**: Complete workflow functional, RPMs built from git source

**Test File**: `tests/integration/test_complete_workflow.py`

**Acceptance Criteria for Integration Tests**:
- [ ] At least 3 integration tests written
- [ ] All integration tests pass
- [ ] Tests use real containers (podman)
- [ ] Tests clean up after themselves
- [ ] Tests document any environmental requirements

---

### Task 3: Performance Validation (Priority 2)

**Timeline**: Day 3 (0.5 days)

#### Performance Baseline

**Measure**:
1. Container startup time
2. RebuildSRPM execution time (vs mock-based)
3. BuildSRPMFromSCM execution time (vs mock-based)
4. Memory usage
5. Disk I/O

**Target**: < 10% overhead vs mock-based kojid

**Methodology**:
```python
import time

# Measure RebuildSRPM
start = time.time()
exit_code, result = adapter.run(ctx, manager, sink, params, session)
elapsed = time.time() - start
print(f"RebuildSRPM execution time: {elapsed:.2f}s")

# Compare to mock baseline (from Phase 1/2 measurements)
# Baseline: ~30-60 seconds for typical SRPM
# Target: < 66 seconds (10% overhead)
```

**Deliverables**:
- [ ] Performance measurements documented
- [ ] Comparison to mock-based baseline
- [ ] Overhead percentage calculated
- [ ] Performance report created

**Document**: `docs/implementation/phase2.5-performance-baseline.md`

---

### Task 4: Test Coverage Analysis (Priority 2)

**Timeline**: Day 3 (0.5 days)

**Current Coverage**:
- RebuildSRPMAdapter: 66.67%
- BuildSRPMFromSCMAdapter: Unknown (measure)
- SCM module: Unknown (measure)

**Target**: ≥ 70% for all new code

**Measure Coverage**:
```bash
tox -e py3 -- tests/unit/test_rebuild_srpm_adapter.py \
                tests/unit/test_buildsrpm_scm_adapter.py \
                tests/unit/test_scm_handlers.py \
                --cov=koji_adjutant.task_adapters.rebuild_srpm \
                --cov=koji_adjutant.task_adapters.buildsrpm_scm \
                --cov=koji_adjutant.task_adapters.scm \
                --cov-report=html \
                --cov-report=term
```

**Analysis**:
- Identify uncovered lines
- Assess criticality (error paths vs edge cases)
- Document coverage gaps
- Recommend additional tests if needed (optional)

**Deliverables**:
- [ ] Coverage report generated
- [ ] Coverage percentages documented
- [ ] Gap analysis completed
- [ ] Recommendations provided (if needed)

**Document**: `docs/implementation/phase2.5-test-coverage.md`

---

### Task 5: Documentation Updates (Priority 2)

**Timeline**: Day 4 (1 day)

#### Documents to Update

**1. PROJECT_STATUS.md**
- Update to Phase 2.5 COMPLETE
- Add Week 3 completion section
- Update capabilities: Full SRPM workflow
- Remove "Critical Gap" from limitations
- Update "Next Steps" to point to staging deployment

**2. WORKFLOW.md**
- Add SRPM task workflows
- Document RebuildSRPM process
- Document BuildSRPMFromSCM process
- Update end-to-end workflow diagram

**3. Phase 2.5 Completion Report** (NEW)
**File**: `docs/implementation/phase2.5-completion-report.md`

**Contents**:
- Executive summary (Phase 2.5 delivered)
- Week-by-week breakdown
- Final test results (total tests, pass rate)
- Performance results
- Code metrics (lines, files, coverage)
- Known limitations (if any)
- Lessons learned
- Recommendations for Phase 3

**4. ADR 0006 Status Update**
- Update status from "In Progress" to "Implemented"
- Add implementation notes section
- Document any deviations from design

**Deliverables**:
- [ ] PROJECT_STATUS.md updated (Phase 2.5 COMPLETE)
- [ ] WORKFLOW.md updated (SRPM workflows)
- [ ] Phase 2.5 completion report written
- [ ] ADR 0006 updated (status: Implemented)

---

### Task 6: Production Readiness Assessment (Priority 1)

**Timeline**: Day 5 (1 day)

#### Assessment Checklist

**Functionality** ✅/❌:
- [ ] RebuildSRPM adapter functional
- [ ] BuildSRPMFromSCM adapter functional
- [ ] Complete workflow (git → SRPM → RPM) works
- [ ] All task types working (buildArch, createrepo, rebuildSRPM, buildSRPMFromSCM)
- [ ] Hub API compatibility validated
- [ ] Policy integration working
- [ ] Monitoring integration working

**Quality** ✅/❌:
- [ ] All tests passing (100%)
- [ ] Code coverage ≥ 70%
- [ ] No critical bugs
- [ ] No high-severity bugs
- [ ] Code reviewed
- [ ] Documentation complete

**Performance** ✅/❌:
- [ ] Overhead < 10%
- [ ] Container startup < 5 seconds
- [ ] No memory leaks
- [ ] Resource cleanup working

**Integration** ✅/❌:
- [ ] Kojid integration complete
- [ ] Graceful fallback working
- [ ] Module exports correct
- [ ] No import errors

**Deployment Readiness** ✅/❌:
- [ ] Configuration documented
- [ ] Container images available
- [ ] Network requirements documented
- [ ] Troubleshooting guide exists

**Final Decision**: GO / NO-GO for staging deployment

**Document**: Update `docs/production-readiness-checklist.md`

---

## Timeline

| Day | Tasks | Deliverables | Owner |
|-----|-------|--------------|-------|
| **1** | Fix 2 failing tests, run full test suite | All tests passing | Quality Engineer |
| **2** | Integration test scenarios 1-2 | RebuildSRPM + BuildSRPMFromSCM integration tests | Quality Engineer |
| **3a** | Integration test scenario 3, performance | Complete workflow test, performance baseline | Quality Engineer |
| **3b** | Test coverage analysis | Coverage report | Quality Engineer |
| **4** | Documentation updates | 4 documents updated | Quality Engineer |
| **5** | Production readiness assessment | GO/NO-GO decision | Quality Engineer + Strategic Planner |

**Total**: 5 days

---

## Acceptance Criteria

### Must Complete (Blockers):
- [ ] All 33 tests passing (100%) - RebuildSRPM (12) + BuildSRPMFromSCM (13) + SCM (17) + Integration (3+)
- [ ] At least 3 integration tests written and passing
- [ ] Performance overhead < 10%
- [ ] No critical or high-severity bugs
- [ ] PROJECT_STATUS.md reflects Phase 2.5 COMPLETE
- [ ] Phase 2.5 completion report written
- [ ] Production readiness: GO decision

### Nice to Have (Optional):
- [ ] Test coverage ≥ 80%
- [ ] Additional integration tests (4+)
- [ ] Performance optimizations documented
- [ ] Operator guide started

---

## Reference Materials

### Week 1 & 2 Deliverables

**Week 1**:
- `koji_adjutant/task_adapters/rebuild_srpm.py` (581 lines)
- `tests/unit/test_rebuild_srpm_adapter.py` (12 tests, 100% passing)

**Week 2**:
- `koji_adjutant/task_adapters/scm/` (3 files, ~400 lines)
- `koji_adjutant/task_adapters/buildsrpm_scm.py` (550 lines)
- `tests/unit/test_scm_handlers.py` (17 tests)
- `tests/unit/test_buildsrpm_scm_adapter.py` (13 tests)

### Design Documents

- **Phase 2.5 Design**: `docs/planning/phase2.5-srpm-adapters-design.md`
- **ADR 0006**: `docs/architecture/decisions/0006-srpm-task-adapters.md`
- **Phase 2.5 Roadmap**: `docs/planning/phase2.5-roadmap.md`

### Test Patterns

- **Unit test pattern**: Follow `test_rebuild_srpm_adapter.py`
- **Integration test pattern**: Follow Phase 1/2 integration tests
- **Mock patterns**: Use MagicMock for container operations in unit tests

---

## Testing Environment

### Requirements

**Software**:
- Python 3.11+
- Podman 4.0+
- pytest, tox
- Git (for SCM tests)

**Network**:
- Internet access (for git clone tests)
- Or local test git repository

**Resources**:
- ~10 GB disk space (for test containers and artifacts)
- 4+ GB RAM
- Podman socket accessible

### Setup

```bash
# Ensure podman is running
systemctl --user status podman.socket

# Run tests
tox -e py3 -- tests/unit/test_scm_handlers.py::TestGitHandler::test_checkout_failure_checkout_commit -v

# Run integration tests (if created)
pytest tests/integration/ -v -m integration

# Generate coverage
tox -e py3 -- tests/unit/ --cov=koji_adjutant.task_adapters --cov-report=html
```

---

## Common Issues & Solutions

### Issue 1: Podman not available
**Solution**: Tests should be skippable if podman not available (use pytest.mark.skipif)

### Issue 2: Network access for git clone
**Solution**: Use local test repo or mock git operations in unit tests

### Issue 3: Container cleanup failures
**Solution**: Ensure try/finally blocks, add explicit cleanup in tests

### Issue 4: Test isolation issues
**Solution**: Use tmp_path fixture, unique container names per test

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Test pass rate** | 100% | pytest output |
| **Test count** | ≥ 45 tests | pytest --collect-only |
| **Code coverage** | ≥ 70% | pytest-cov |
| **Performance overhead** | < 10% | Time measurements |
| **Integration tests** | ≥ 3 tests | pytest tests/integration/ |
| **Critical bugs** | 0 | Manual review |
| **Documentation** | 100% complete | Checklist |

---

## Phase 2.5 Completion Criteria

Phase 2.5 is **COMPLETE** when:

✅ All unit tests passing (100%)
✅ Integration tests passing (≥ 3 tests)
✅ Performance validated (< 10% overhead)
✅ Complete workflow functional (git → SRPM → RPM)
✅ No critical bugs
✅ Documentation updated
✅ Production readiness: GO
✅ Phase 2.5 completion report written

**Then**: Ready for staging deployment and koji-boxed integration

---

## Handoff Checklist

### Before Starting:
- [ ] Read this handoff document
- [ ] Review Week 1 & 2 code
- [ ] Understand test environment requirements
- [ ] Have podman access

### During Week 3:
- [ ] Fix failing tests first (Day 1)
- [ ] Write integration tests (Days 2-3)
- [ ] Measure performance (Day 3)
- [ ] Update documentation (Day 4)
- [ ] Production readiness assessment (Day 5)

### Before Completion:
- [ ] All acceptance criteria met
- [ ] All tests passing
- [ ] Documents updated
- [ ] GO/NO-GO decision made

---

## Communication

**Daily Standup**: Report progress on:
- Tests fixed/written/passing
- Integration test status
- Blockers or issues
- ETA for completion

**End of Week 3**: Present to Strategic Planner:
- Phase 2.5 completion report
- Production readiness assessment
- GO/NO-GO recommendation for staging

---

**Handoff Status**: ✅ READY

**Your mission**: Validate Phase 2.5 SRPM adapters and declare production readiness

**Expected completion**: 5 days from start

**Good luck, Quality Engineer!** 🧪🔬

---

**From**: Strategic Planner
**Date**: 2025-10-31
**Priority**: CRITICAL
**Week**: 3 of 3 (Phase 2.5 - FINAL)
