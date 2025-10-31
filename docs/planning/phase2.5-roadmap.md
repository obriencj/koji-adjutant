# Phase 2.5 Roadmap: SRPM Task Adapters

**Version**: 1.0
**Date**: 2025-10-31
**Status**: Planning - Ready to Execute
**Owner**: Implementation Lead (to be assigned)
**Priority**: CRITICAL - Blocks Phase 3 and all deployment

---

## Executive Summary

**Goal**: Implement missing SRPM task adapters to enable complete build workflows (SCM → SRPM → RPM)

**Scope**: Two new adapters + SCM integration module
**Timeline**: 2-3 weeks (15-20 working days)
**Deliverables**: Production-ready SRPM build capability
**Success**: Complete koji build workflow functional end-to-end

---

## Problem Statement

**Current State**: Koji-adjutant can only build RPMs from pre-existing SRPM files
**Gap**: Cannot build SRPMs from source control (git/svn) or rebuild existing SRPMs
**Impact**: Blocks production deployment, koji-boxed integration, real-world usage
**Discovery**: 2025-10-31 during user review

---

## Objectives

### Primary Objectives

1. **Implement RebuildSRPMAdapter**
   - Rebuild existing SRPMs with correct dist tags
   - Full test coverage
   - Integration with kojid

2. **Implement BuildSRPMFromSCMAdapter**
   - Checkout source from git repositories
   - Build SRPMs from checked-out source
   - Full test coverage
   - Integration with kojid

3. **Enable Complete Build Workflow**
   - User runs: `koji build f39 git://example.com/package.git`
   - System creates SRPM → builds RPMs → uploads artifacts
   - Equivalent to mock-based kojid functionality

### Secondary Objectives

4. **SCM Integration Module**
   - Git support (primary)
   - SVN support (optional, Phase 3 candidate)
   - Extensible for other SCM types

5. **Testing and Validation**
   - Unit tests (95%+ pass rate)
   - Integration tests (100% pass rate)
   - End-to-end workflow validation

6. **Documentation**
   - Design document (complete)
   - Implementation guide
   - Updated PROJECT_STATUS.md

---

## Deliverables

| # | Deliverable | Type | Owner | Status |
|---|-------------|------|-------|--------|
| 1 | Design document | Documentation | Strategic Planner | ✅ Complete |
| 2 | RebuildSRPMAdapter | Code | Implementation Lead | Pending |
| 3 | RebuildSRPM unit tests | Tests | Implementation Lead | Pending |
| 4 | RebuildSRPM integration tests | Tests | Quality Engineer | Pending |
| 5 | SCM module (git support) | Code | Implementation Lead | Pending |
| 6 | BuildSRPMFromSCMAdapter | Code | Implementation Lead | Pending |
| 7 | BuildSRPMFromSCM unit tests | Tests | Implementation Lead | Pending |
| 8 | BuildSRPMFromSCM integration tests | Tests | Quality Engineer | Pending |
| 9 | End-to-end workflow tests | Tests | Quality Engineer | Pending |
| 10 | Kojid integration | Code | Implementation Lead | Pending |
| 11 | Documentation updates | Documentation | Strategic Planner | Pending |
| 12 | Phase 2.5 completion report | Documentation | Strategic Planner | Pending |

---

## Implementation Schedule

### Week 1: RebuildSRPM + Foundation

**Goal**: Complete RebuildSRPM adapter with full testing

| Day | Tasks | Owner | Deliverables |
|-----|-------|-------|--------------|
| **1-2** | • Review design document<br>• Set up development environment<br>• Create adapter skeleton | Implementation Lead | • Dev env ready<br>• Code scaffolding |
| **3-4** | • Implement RebuildSRPMAdapter<br>• Implement unpack/rebuild logic<br>• Implement validation | Implementation Lead | • Functional adapter<br>• Helper methods |
| **5** | • Write unit tests<br>• Initial integration test | Implementation Lead | • Test suite<br>• 80%+ coverage |
| **6-7** | • Kojid integration<br>• Testing and refinement<br>• Bug fixes | Implementation Lead | • kojid.py modified<br>• Tests passing |

**Milestone 1 (End of Week 1)**: ✅ RebuildSRPM adapter functional and tested

**Exit Criteria**:
- [ ] RebuildSRPMAdapter compiles without errors
- [ ] Unit tests: 95%+ pass rate
- [ ] Can rebuild a simple SRPM successfully
- [ ] Integrates with kojid RebuildSRPM handler
- [ ] No critical bugs

---

### Week 2: BuildSRPMFromSCM

**Goal**: Complete BuildSRPMFromSCM adapter with SCM integration

| Day | Tasks | Owner | Deliverables |
|-----|-------|-------|--------------|
| **8** | • Design SCM module structure<br>• Implement SCMHandler protocol | Implementation Lead | • SCM module skeleton<br>• Protocol definition |
| **9** | • Implement GitHandler<br>• Test git checkout logic | Implementation Lead | • Git support functional<br>• Unit tests |
| **10-11** | • Implement BuildSRPMFromSCMAdapter<br>• Integrate SCM checkout<br>• Implement SRPM build | Implementation Lead | • Functional adapter<br>• SCM integration |
| **12** | • Write unit tests<br>• Write SCM tests | Implementation Lead | • Test suite<br>• 80%+ coverage |
| **13-14** | • Kojid integration<br>• Integration testing<br>• Bug fixes | Implementation Lead | • kojid.py modified<br>• Tests passing |

**Milestone 2 (End of Week 2)**: ✅ BuildSRPMFromSCM adapter functional and tested

**Exit Criteria**:
- [ ] BuildSRPMFromSCMAdapter compiles without errors
- [ ] SCM module supports git checkouts
- [ ] Unit tests: 95%+ pass rate
- [ ] Can checkout from public git repo
- [ ] Can build SRPM from checked-out source
- [ ] Integrates with kojid BuildSRPMFromSCMTask handler
- [ ] No critical bugs

---

### Week 3: Integration, Testing, Validation

**Goal**: Complete end-to-end validation and documentation

| Day | Tasks | Owner | Deliverables |
|-----|-------|-------|--------------|
| **15** | • End-to-end workflow testing<br>• Test SCM → SRPM → RPM flow | Quality Engineer | • Workflow validated<br>• Test report |
| **16** | • Test with multiple packages<br>• Error scenario testing<br>• Edge case validation | Quality Engineer | • Comprehensive tests<br>• Issue list |
| **17** | • Performance testing<br>• Measure overhead vs kojid<br>• Optimization if needed | Quality Engineer | • Performance baseline<br>• Optimization report |
| **18** | • Documentation updates<br>• Update WORKFLOW.md<br>• Update PROJECT_STATUS.md | Strategic Planner | • Updated docs<br>• User guides |
| **19-20** | • Code review<br>• Address feedback<br>• Final validation<br>• Buffer for issues | All | • Code reviewed<br>• Issues resolved<br>• Phase 2.5 complete |

**Milestone 3 (End of Week 3)**: ✅ Phase 2.5 complete, ready for staging

**Exit Criteria**:
- [ ] Complete workflow (SCM → SRPM → RPM) works
- [ ] All tests passing (unit + integration)
- [ ] Performance overhead < 10%
- [ ] Documentation updated and reviewed
- [ ] Code reviewed and approved
- [ ] No critical or high-severity bugs
- [ ] Ready for koji-boxed integration testing

---

## Resource Requirements

### Personnel

| Role | Effort | Responsibilities |
|------|--------|------------------|
| **Implementation Lead** | 15-18 days | Adapter implementation, kojid integration, unit tests |
| **Quality Engineer** | 3-5 days | Integration tests, performance testing, validation |
| **Strategic Planner** | 2-3 days | Design review, documentation, coordination |
| **Container Engineer** | 1-2 days | SCM network configuration review, container setup |

**Total Effort**: 21-28 person-days across 3 weeks

### Infrastructure

- **Development environment**: Linux workstation with podman
- **Test environment**: Access to public git repositories for testing
- **Container images**: AlmaLinux 10 buildroot images (from ADR 0004)
- **Network access**: Required for git clone operations
- **Storage**: Sufficient for test SRPMs and RPMs (~10 GB)

### Dependencies

**Hard Dependencies** (must have):
- ✅ Phase 2 infrastructure (ContainerManager, BuildrootInitializer, etc.)
- ✅ Podman 4.0+
- ✅ Git client (in container images)
- ✅ RPM tools (in container images)

**Soft Dependencies** (nice to have):
- SVN client (for future svn:// support)
- Test package repository (for comprehensive testing)

---

## Risk Management

### High-Priority Risks

| Risk | Mitigation | Owner | Status |
|------|------------|-------|--------|
| **SCM checkout complexity** | Start with git only, defer svn/cvs | Implementation Lead | Planned |
| **Network configuration issues** | Test early, document requirements | Container Engineer | Planned |
| **Schedule slippage** | 2-3 week buffer, incremental milestones | Strategic Planner | Monitoring |
| **Integration issues with kojid** | Study existing code, test incrementally | Implementation Lead | Planned |

### Medium-Priority Risks

| Risk | Mitigation | Owner | Status |
|------|------------|-------|--------|
| **SRPM validation edge cases** | Extensive testing with various formats | Quality Engineer | Planned |
| **Performance overhead** | Measure early, optimize if needed | Quality Engineer | Planned |
| **Test coverage gaps** | Mandate 95%+ unit test coverage | Quality Engineer | Planned |

### Low-Priority Risks

| Risk | Mitigation | Owner | Status |
|------|------------|-------|--------|
| **Authentication for private repos** | Defer to Phase 3 | Implementation Lead | Deferred |
| **SVN support** | Not required for Phase 2.5 | Implementation Lead | Deferred |

---

## Success Metrics

### Quantitative Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **Unit test pass rate** | ≥ 95% | pytest output |
| **Integration test pass rate** | 100% | pytest output |
| **Code coverage (adapters)** | ≥ 80% | pytest-cov |
| **Performance overhead** | < 10% | Benchmark comparison |
| **Build success rate** | ≥ 95% | Test package builds |
| **Container cleanup rate** | 100% | No orphaned containers |

### Qualitative Metrics

| Metric | Target | Assessment Method |
|--------|--------|-------------------|
| **Code quality** | High | Code review approval |
| **Documentation quality** | Complete | Review by all personas |
| **API compatibility** | Perfect | Hub result validation |
| **Error handling** | Robust | Error scenario testing |

---

## Acceptance Criteria

Phase 2.5 is **ACCEPTED** when all criteria are met:

### Functional Acceptance

- [ ] **AC1**: RebuildSRPMAdapter rebuilds SRPMs with correct dist tags
- [ ] **AC2**: BuildSRPMFromSCMAdapter checks out source from git
- [ ] **AC3**: BuildSRPMFromSCMAdapter builds valid SRPMs
- [ ] **AC4**: Complete workflow (SCM → SRPM → RPM) executes successfully
- [ ] **AC5**: Adapters integrate with kojid task handlers
- [ ] **AC6**: Result format matches kojid expectations exactly

### Quality Acceptance

- [ ] **AC7**: Unit tests pass at ≥ 95%
- [ ] **AC8**: Integration tests pass at 100%
- [ ] **AC9**: Code coverage ≥ 80% for new adapters
- [ ] **AC10**: No critical or high-severity bugs
- [ ] **AC11**: Code reviewed and approved
- [ ] **AC12**: Documentation complete and reviewed

### Performance Acceptance

- [ ] **AC13**: SRPM rebuild overhead < 5%
- [ ] **AC14**: SCM checkout + SRPM build overhead < 10%
- [ ] **AC15**: Container startup time < 5 seconds
- [ ] **AC16**: No memory leaks or resource exhaustion

### Integration Acceptance

- [ ] **AC17**: Logs stream to Koji log system correctly
- [ ] **AC18**: Monitoring API tracks SRPM tasks
- [ ] **AC19**: Container cleanup on success and failure
- [ ] **AC20**: Policy resolver selects correct images

---

## Phase 2.5 to Phase 3 Transition

### Exit Criteria from Phase 2.5

**Phase 2.5 is complete when**:
1. All acceptance criteria met (see above)
2. PROJECT_STATUS.md updated to "Production-Ready"
3. Phase 2.5 completion report written
4. Handoff to koji-boxed integration testing

### Entry Criteria to Phase 3

**Cannot proceed to Phase 3 until**:
1. Phase 2.5 complete (all deliverables)
2. Koji-boxed integration testing successful
3. Staging deployment validation complete
4. No blocking issues identified

**Phase 3 Prerequisites**:
- ✅ Phase 2.5 complete
- ✅ Koji-boxed integration successful
- ✅ Initial production pilot completed
- ✅ Operator feedback collected

---

## Communication Plan

### Status Updates

**Weekly Status Reports**:
- **Audience**: All personas (planner, architect, implementation, container, quality)
- **Format**: Email/doc with progress, blockers, next steps
- **Schedule**: End of Week 1, Week 2, Week 3

**Daily Standups** (during implementation):
- **Audience**: Implementation Lead, Quality Engineer
- **Format**: Quick sync on progress and blockers
- **Duration**: 15 minutes

### Milestone Reviews

**Milestone 1 Review** (End of Week 1):
- **Date**: Day 7
- **Attendees**: All personas
- **Agenda**: Review RebuildSRPM completion, demo, go/no-go decision
- **Deliverable**: Milestone 1 report

**Milestone 2 Review** (End of Week 2):
- **Date**: Day 14
- **Attendees**: All personas
- **Agenda**: Review BuildSRPMFromSCM completion, demo, go/no-go decision
- **Deliverable**: Milestone 2 report

**Final Review** (End of Week 3):
- **Date**: Day 20
- **Attendees**: All personas
- **Agenda**: Review complete workflow, acceptance criteria, go/no-go for Phase 3
- **Deliverable**: Phase 2.5 completion report

### Stakeholder Communication

**Project Update** (Start of Phase 2.5):
- Inform stakeholders of timeline and objectives
- Set expectations for completion

**Completion Announcement** (End of Phase 2.5):
- Announce Phase 2.5 completion
- Highlight readiness for staging deployment
- Outline next steps (koji-boxed integration)

---

## Dependencies and Assumptions

### Dependencies

**Technical Dependencies**:
- Phase 2 infrastructure complete ✅
- Podman 4.0+ available ✅
- Container images available ✅
- Network access for git clone ✅
- Koji hub API accessible ✅

**Resource Dependencies**:
- Implementation Lead available (15-18 days)
- Quality Engineer available (3-5 days)
- Development environment set up
- Test infrastructure available

### Assumptions

1. **Technical Assumptions**:
   - Git-only support sufficient for Phase 2.5
   - Public repos sufficient for testing (no auth needed initially)
   - Existing buildroot images contain necessary tools
   - Network configuration allows git clone

2. **Schedule Assumptions**:
   - No major holidays or team member unavailability
   - No critical bugs in Phase 2 infrastructure discovered
   - Design document complete and approved
   - Dependencies available when needed

3. **Scope Assumptions**:
   - SVN support deferred to Phase 3
   - Private repo authentication deferred to Phase 3
   - Only essential features in Phase 2.5
   - Advanced SCM features not required

---

## Post-Phase 2.5 Activities

### Immediate Next Steps (After Completion)

1. **Week 4: Koji-Boxed Integration**
   - Deploy to koji-boxed staging environment
   - Test with real koji hub
   - Validate complete build workflows
   - Identify any integration issues

2. **Week 5: Staging Validation**
   - Run production-like workloads
   - Performance validation
   - Operator testing and feedback
   - Documentation refinement

3. **Week 6: Production Pilot**
   - Limited production deployment
   - Monitor closely
   - Gather operational experience
   - Prepare for full rollout

### Future Enhancements (Phase 3 Candidates)

**High Priority**:
- Private repository authentication (SSH keys, tokens)
- SVN support for legacy packages
- Enhanced error recovery

**Medium Priority**:
- CVS support (if needed)
- Advanced SCM features (submodules, LFS)
- Container caching for performance

**Low Priority**:
- Alternative build methods (tito, etc.)
- Custom SRPM build scripts
- Advanced network policies

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-31 | Strategic Planner | Initial roadmap |

### Approvals

| Role | Name | Date | Signature |
|------|------|------|-----------|
| **Strategic Planner** | [Assigned] | [Pending] | [Pending] |
| **Systems Architect** | [Assigned] | [Pending] | [Pending] |
| **Implementation Lead** | [To be assigned] | [Pending] | [Pending] |
| **Container Engineer** | [Assigned] | [Pending] | [Pending] |
| **Quality Engineer** | [Assigned] | [Pending] | [Pending] |

### Related Documents

- **Design Document**: `phase2.5-srpm-adapters-design.md` (this phase)
- **Status Update**: `status-update-2025-10-31-srpm-gap.md`
- **Project Status**: `../PROJECT_STATUS.md`
- **Phase 2 Roadmap**: `phase2-roadmap.md`
- **ADRs**: `../architecture/decisions/000*.md`

---

## Quick Reference

### Key Files to Create

```
koji_adjutant/
└── task_adapters/
    ├── rebuild_srpm.py              # NEW: ~250 lines
    ├── buildsrpm_scm.py             # NEW: ~350 lines
    └── scm/
        ├── __init__.py              # NEW: ~20 lines
        ├── base.py                  # NEW: ~100 lines
        └── git.py                   # NEW: ~200 lines

tests/
├── unit/
│   ├── test_rebuild_srpm_adapter.py     # NEW: ~200 lines
│   ├── test_buildsrpm_scm_adapter.py    # NEW: ~250 lines
│   └── test_scm_handlers.py             # NEW: ~150 lines
└── integration/
    └── test_srpm_workflow.py            # NEW: ~300 lines
```

**Total New Code**: ~1,800 lines (estimated)

### Command Reference

```bash
# Run unit tests
pytest tests/unit/test_rebuild_srpm_adapter.py -v
pytest tests/unit/test_buildsrpm_scm_adapter.py -v

# Run integration tests
pytest tests/integration/test_srpm_workflow.py -v

# Run all SRPM-related tests
pytest -k "srpm" -v

# Check coverage
pytest --cov=koji_adjutant.task_adapters.rebuild_srpm --cov-report=html
pytest --cov=koji_adjutant.task_adapters.buildsrpm_scm --cov-report=html

# Performance testing
time python -m koji_adjutant.task_adapters.rebuild_srpm <test_srpm>
```

---

**Phase 2.5 Roadmap Status**: ✅ READY TO EXECUTE

**Next Action**: Assign Implementation Lead and schedule kickoff meeting

---
