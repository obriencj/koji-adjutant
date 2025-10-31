# Phase 2.5: SRPM Adapters - Stakeholder Brief

**Date**: 2025-10-31
**Type**: Project Update
**Audience**: Project stakeholders, deployment teams, management
**Status**: CRITICAL GAP IDENTIFIED - Implementation Required

---

## Executive Summary

A critical gap has been identified in koji-adjutant that blocks production deployment: **SRPM task adapters are not implemented**. While the project successfully completed Phase 2 with excellent architecture and performance, it currently can only build RPMs from pre-existing SRPM files, not create SRPMs from source control.

**Timeline Impact**: +2-3 weeks before deployment
**Priority**: CRITICAL - Blocks all deployment activities
**Solution**: Implement Phase 2.5 (SRPM adapters)
**Current Status**: Planning complete, ready to implement

---

## The Situation

### What We Discovered

On **2025-10-31**, during a user review, we discovered that koji-adjutant is missing two essential task adapters:

1. **buildSRPMFromSCM** - Builds SRPMs from source control (git, svn)
2. **rebuildSRPM** - Rebuilds existing SRPMs with correct dist tags

### Why This Matters

**Normal koji build workflow**:
```
User: koji build f39 git://example.com/package.git

Step 1: Build SRPM from git     ← MISSING (can't do this)
Step 2: Build RPMs from SRPM    ← WORKING (we can do this)
```

**Current capability**: We can do Step 2 if someone manually provides the SRPM
**Production requirement**: We need to do both steps automatically

**Impact**: Cannot deploy to production or staging until this is fixed

---

## What This Means

### Can Do Today ✅
- Build RPMs from manually-provided SRPMs (buildArch)
- Generate repository metadata (createrepo)
- Development and unit testing
- Architecture and design work

### Cannot Do Yet ❌
- **Production deployment** (any environment)
- **Staging deployment**
- **Integration testing** with koji-boxed
- **Real package builds** from source control
- **Replace existing kojid workers**

### Blocking Activities 🚨
- All deployment plans
- Koji-boxed integration testing
- Production pilot programs
- Operator evaluation
- Performance validation with real workloads

---

## The Plan

### Phase 2.5: SRPM Task Adapters

**Objective**: Implement missing SRPM adapters to enable complete build workflows

**Timeline**: **2-3 weeks** (15-20 working days)

**Deliverables**:
1. RebuildSRPMAdapter - Rebuild SRPMs with dist tags
2. BuildSRPMFromSCMAdapter - Build SRPMs from git
3. SCM integration module - Git checkout support
4. Comprehensive testing (unit + integration)
5. Full end-to-end workflow validation
6. Documentation updates

**Resources Required**:
- Implementation Lead: 15-18 days
- Quality Engineer: 3-5 days
- Strategic Planner: 2-3 days
- Container Engineer: 1-2 days (advisory)

---

## Schedule

### Week 1: RebuildSRPM
- Design review and setup (2 days)
- Implement RebuildSRPMAdapter (3 days)
- Testing and refinement (2 days)
- **Milestone 1**: RebuildSRPM functional ✓

### Week 2: BuildSRPMFromSCM
- SCM module implementation (2 days)
- Implement BuildSRPMFromSCMAdapter (3 days)
- Testing and refinement (2 days)
- **Milestone 2**: BuildSRPMFromSCM functional ✓

### Week 3: Integration & Validation
- End-to-end workflow testing (2 days)
- Performance validation (1 day)
- Documentation updates (1 day)
- Buffer for issues and code review (1-2 days)
- **Milestone 3**: Phase 2.5 complete ✓

### After Phase 2.5
- **Week 4**: Koji-boxed integration testing
- **Week 5**: Staging validation
- **Week 6**: Production pilot (low-risk builds)

**Total Timeline to Production**: ~6 weeks from start of Phase 2.5

---

## Revised Project Timeline

### Original Timeline (Before Discovery)
```
Phase 2: COMPLETE ✅
  ↓
Staging Deployment: Week 1-2
  ↓
Production Pilot: Week 3-4
```

### Revised Timeline (After Discovery)
```
Phase 2: COMPLETE ✅ (with gap identified)
  ↓
Phase 2.5: SRPM Adapters: Week 1-3  ← NEW
  ↓
Staging Deployment: Week 4-5
  ↓
Production Pilot: Week 6-7
```

**Impact**: +3 weeks to production deployment

---

## Risk Assessment

### Low Risk ✅
- **Technical approach**: Follows proven patterns from buildArch adapter
- **Architecture**: Phase 2 infrastructure solid (< 5% overhead, 85% test pass)
- **Design**: Comprehensive design document complete
- **Team**: Experienced with similar adapter implementation

### Medium Risk ⚠️
- **Schedule**: 2-3 week estimate based on similar work (buildArch took ~1 week)
- **SCM integration**: Git checkout adds complexity, but well-understood
- **Testing**: Need public git repos for testing (readily available)

### Mitigation Strategies
- Incremental implementation (RebuildSRPM first, then SCM)
- Weekly milestone reviews with go/no-go decisions
- Buffer time built into Week 3
- Existing adapter code provides reference implementation

---

## Business Impact

### Cost
- **Development effort**: ~21-28 person-days
- **Timeline delay**: +3 weeks to production
- **Opportunity cost**: Delayed production benefits

### Benefit
- **Complete build system**: Full koji functionality
- **Production-ready**: Can replace existing kojid workers
- **Market readiness**: Can support real customers/users
- **Risk reduction**: Gaps found early, not in production

### ROI
- **One-time cost**: 3 weeks implementation
- **Permanent value**: Complete, deployable build system
- **Alternative**: Without this work, project cannot be deployed (infinite delay)

---

## What We Need

### Decisions Required
1. **Approval to proceed** with Phase 2.5 implementation
2. **Resource allocation** (Implementation Lead for 3 weeks)
3. **Timeline acceptance** (acknowledge +3 week delay)

### Support Required
1. **Development environment** access
2. **Test infrastructure** (public git repos, container images)
3. **Milestone review** participation (end of each week)

### Communication Required
1. **Internal stakeholders**: Update on timeline change
2. **Deployment teams**: Hold deployment planning until Week 4
3. **Users/customers**: Adjust expectations if needed

---

## Success Criteria

Phase 2.5 will be considered successful when:

✅ **Complete build workflow functional**
- User can run: `koji build f39 git://example.com/package.git`
- System builds SRPM from git → builds RPMs → uploads artifacts
- Equivalent to mock-based kojid

✅ **Quality standards met**
- Unit tests: 95%+ pass rate
- Integration tests: 100% pass rate
- Performance overhead: < 10%
- Code reviewed and approved

✅ **Ready for deployment**
- Koji-boxed integration successful
- Staging validation complete
- Documentation updated
- No critical bugs

---

## Questions & Answers

### Q: Why wasn't this caught earlier?
**A**: Phase 1 and 2 focused on proving container-based execution viable with buildArch. SRPM adapters were assumed but not explicitly scoped. User review caught the gap before deployment, which is the right time to find it.

### Q: Can we deploy without SRPM adapters?
**A**: No. Normal koji builds start from source control URLs, not pre-built SRPMs. Without SRPM adapters, we cannot handle standard build requests.

### Q: Can we reduce the 2-3 week timeline?
**A**: Possibly to 2 weeks minimum, but risk of quality issues. The estimate is based on:
- RebuildSRPM: 5-7 days (similar to buildArch: ~5 days)
- BuildSRPMFromSCM: 7-10 days (more complex, needs SCM)
- Integration/testing: 3-5 days

### Q: What if we only implement one adapter?
**A**: Both are needed for complete workflows:
- **buildSRPMFromSCM**: New builds from git (most common)
- **rebuildSRPM**: Rebuild requests (less common but required)

### Q: Is the rest of Phase 2 still solid?
**A**: Yes! Phase 2 work is excellent:
- BuildArch adapter: Working, tested, < 5% overhead
- Architecture: Clean, maintainable, well-documented
- Performance: Exceeds targets
- This is an additive gap, not a fundamental flaw

### Q: What happens after Phase 2.5?
**A**: Standard deployment process resumes:
1. Koji-boxed integration testing (Week 4)
2. Staging validation (Week 5)
3. Production pilot (Week 6+)
4. Full production rollout

---

## Recommendation

**Proceed with Phase 2.5 implementation immediately**

**Rationale**:
1. **Critical gap**: Blocks all deployment without it
2. **Well-scoped**: Clear requirements, proven approach
3. **Low risk**: Follows existing patterns, comprehensive design
4. **Finite timeline**: 2-3 weeks to completion
5. **High value**: Enables complete, deployable build system

**Alternative (not recommended)**: Delay project indefinitely - gap must be addressed for any production use

---

## Next Steps

### Immediate Actions (This Week)
1. **Review and approve** this brief and Phase 2.5 plan
2. **Assign Implementation Lead** for 3-week engagement
3. **Schedule kickoff meeting** with all personas
4. **Communicate timeline update** to stakeholders

### Phase 2.5 Execution (Weeks 1-3)
1. **Week 1**: Implement RebuildSRPM adapter
2. **Week 2**: Implement BuildSRPMFromSCM adapter
3. **Week 3**: Integration testing and validation

### Post-Phase 2.5 (Weeks 4+)
1. **Week 4**: Koji-boxed integration testing
2. **Week 5**: Staging validation
3. **Week 6+**: Production pilot and rollout

---

## Contact

**Questions or concerns?**

- **Strategic planning**: Strategic Planner
- **Technical details**: Implementation Lead (TBD) / Systems Architect
- **Quality/testing**: Quality Engineer
- **Timeline/resources**: Strategic Planner

**Documentation**:
- **Design document**: `docs/planning/phase2.5-srpm-adapters-design.md`
- **Detailed roadmap**: `docs/planning/phase2.5-roadmap.md`
- **Project status**: `docs/PROJECT_STATUS.md`

---

## Summary

| Aspect | Status |
|--------|--------|
| **Issue** | SRPM task adapters missing (critical gap) |
| **Impact** | Blocks production deployment |
| **Timeline** | +2-3 weeks (Phase 2.5 implementation) |
| **Risk** | Low (well-understood, proven approach) |
| **Cost** | ~21-28 person-days |
| **Plan** | Comprehensive design and roadmap ready |
| **Next** | Approve and begin implementation |

**Bottom Line**: Critical but manageable gap. 2-3 weeks of implementation work will deliver a complete, production-ready build system.

---

**Document Status**: ✅ READY FOR REVIEW AND APPROVAL

**Date Prepared**: 2025-10-31
**Prepared By**: Strategic Planner
**Review Required**: Yes (all personas + stakeholders)

---
