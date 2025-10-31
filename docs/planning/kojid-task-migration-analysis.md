# Kojid Task Migration Analysis

**Date**: 2025-10-31
**Author**: Implementation Lead
**Purpose**: Document all kojid tasks, identify containerization status, and provide migration recommendations
**Status**: Planning Document

---

## Executive Summary

This document provides a comprehensive analysis of all task handlers in the original kojid daemon, categorizing them by:
1. **Migration Status**: Already containerized, not yet migrated, or N/A
2. **Containerization Recommendation**: Should or should not be containerized
3. **Rationale**: Why a task should or shouldn't run in a container
4. **Priority**: Based on production requirements and common workflows

**Key Findings**:
- **2 tasks** already migrated to containers (buildArch, createrepo)
- **2 critical tasks** identified for immediate migration (rebuildSRPM, buildSRPMFromSCM) - Phase 2.5
- **5 additional build tasks** could benefit from containerization (Phase 3+)
- **9 image building tasks** could be containerized but lower priority
- **6 orchestration/notification tasks** should NOT be containerized (hub API operations only)

---

## Task Categories

### Category 1: Already Migrated to Containers ✅

These tasks are successfully running in podman containers in the current koji-adjutant implementation.

#### 1.1. buildArch
- **Handler Class**: `BuildArchTask` → `BuildArchAdapter`
- **Method**: `buildArch`
- **Status**: ✅ **Migrated** (Phase 1 complete, Phase 2 enhanced)
- **Container**: Yes
- **Rationale**: Core RPM build task requiring isolated buildroot environment. Perfect fit for containers.
- **Implementation**: `koji_adjutant/task_adapters/buildarch.py`
- **Notes**:
  - Phase 1: Basic rpmbuild execution
  - Phase 2: Full buildroot initialization with dependencies
  - Uses BuildrootInitializer for dependency resolution
  - Supports hub policy-driven image selection

#### 1.2. createrepo
- **Handler Class**: `CreaterepoTask` → `CreaterepoAdapter`
- **Method**: `createrepo`
- **Status**: ✅ **Migrated** (Phase 1 complete)
- **Container**: Yes
- **Rationale**: Repository metadata generation benefits from isolation and reproducibility
- **Implementation**: `koji_adjutant/task_adapters/createrepo.py`
- **Notes**:
  - Handles package list generation
  - Supports old repo metadata copying (done on host before container starts)
  - Runs createrepo/createrepo_c in container
  - Results uploaded via /mnt/koji mount

---

### Category 2: Critical Missing Tasks (Phase 2.5) 🚨

These tasks are **critical blockers** for production deployment. Without them, koji-adjutant cannot handle standard build workflows.

#### 2.1. rebuildSRPM
- **Handler Class**: `RebuildSRPM`
- **Method**: `rebuildSRPM`
- **Status**: ❌ **Not Migrated** - **CRITICAL GAP**
- **Should Containerize**: ✅ **YES** - **HIGH PRIORITY**
- **Rationale**:
  - Rebuilds SRPMs with correct dist tags for the target build tag
  - Uses mock buildroot (should use container instead)
  - Required for normal build workflows when `rebuild_srpm` config is true
  - Isolation needs match buildArch (same buildroot requirements)
- **Current Behavior**:
  - Creates mock buildroot with `install_group: srpm-build`
  - Unpacks SRPM using `rpm -iv`
  - Rebuilds with `rpmbuild -bs` from spec + sources
  - Uploads rebuilt SRPM
- **Containerization Approach**:
  - Create `RebuildSRPMAdapter` similar to `BuildArchAdapter`
  - Use buildroot initialization for `srpm-build` group
  - Execute rebuild steps in container
  - Follow same pattern: create work dir, copy SRPM in, rebuild, collect results
- **Priority**: **P0 - Critical** (blocks production deployment)
- **Estimated Effort**: 5-7 days (similar complexity to buildArch Phase 1)

#### 2.2. buildSRPMFromSCM
- **Handler Class**: `BuildSRPMFromSCMTask`
- **Method**: `buildSRPMFromSCM`
- **Status**: ❌ **Not Migrated** - **CRITICAL GAP**
- **Should Containerize**: ✅ **YES** - **HIGH PRIORITY**
- **Rationale**:
  - Most common entry point for builds: `koji build f39 git://example.com/package.git`
  - Checks out source from SCM (git, svn, etc.)
  - Builds SRPM from spec file and sources
  - Uses mock buildroot (should use container instead)
  - Without this, users cannot build from source control
- **Current Behavior**:
  - Parses and validates SCM URL
  - Creates mock buildroot with `install_group: srpm-build`
  - Checks out source from git/svn into buildroot
  - Finds and validates spec file
  - Runs `rpmbuild -bs` to create SRPM
  - Uploads SRPM and logs
- **Containerization Approach**:
  - Create `BuildSRPMFromSCMAdapter` similar to `BuildArchAdapter`
  - Add SCM checkout module (git clone, svn checkout)
  - Use buildroot initialization for `srpm-build` group
  - Execute checkout and build steps in container
  - Handle spec file validation and source collection
- **Additional Requirements**:
  - SCM integration module (git, svn support)
  - Spec file sanity checks (packager, distribution, vendor tags)
  - Source patching hooks (callbacks)
  - Git/svn tools in container image
- **Priority**: **P0 - Critical** (blocks production deployment)
- **Estimated Effort**: 7-10 days (more complex due to SCM integration)

---

### Category 3: Orchestration Tasks (Should NOT Containerize) 🎯

These tasks coordinate other tasks and interact primarily with the hub API. They should run directly on the worker host, not in containers.

#### 3.1. build
- **Handler Class**: `BuildTask`
- **Method**: `build`
- **Status**: N/A (orchestration task)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Master build orchestration task
  - Coordinates subtasks: getSRPM → buildArch (per arch) → tag
  - Makes hub API calls to spawn subtasks
  - No buildroot or isolation needed
  - Lightweight coordination only (weight: 0.2)
- **Current Behavior**:
  - Validates build target and options
  - Determines source type (SCM URL vs SRPM file)
  - Spawns `buildSRPMFromSCM` or `rebuildSRPM` subtask if needed
  - Spawns `buildArch` subtasks for each architecture
  - Waits for all subtasks to complete
  - Tags build in destination tag
  - Reports results to hub
- **Recommendation**: Keep as host-side task handler (no migration needed)

#### 3.2. chainbuild
- **Handler Class**: `ChainBuildTask`
- **Method**: `chainbuild`
- **Status**: N/A (orchestration task)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Orchestrates chain of dependent builds
  - Pure hub API coordination
  - Spawns `build` subtasks in dependency order
  - No buildroot or isolation needed
- **Recommendation**: Keep as host-side task handler (no migration needed)

#### 3.3. tagBuild
- **Handler Class**: `TagBuildTask`
- **Method**: `tagBuild`
- **Status**: N/A (hub API task)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Tags builds in koji hub database
  - Runs hub API "post tests" for tag operations
  - Pure hub API calls, no build work
  - Spawns `tagNotification` subtask
- **Recommendation**: Keep as host-side task handler (no migration needed)

#### 3.4. tagNotification
- **Handler Class**: `TagNotificationTask`
- **Method**: `tagNotification`
- **Status**: N/A (notification task)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Sends email notifications for tag operations
  - SMTP operations only
  - No buildroot or isolation needed
  - Lightweight (weight: 0.1)
- **Recommendation**: Keep as host-side task handler (no migration needed)

#### 3.5. buildNotification
- **Handler Class**: `BuildNotificationTask`
- **Method**: `buildNotification`
- **Status**: N/A (notification task)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Sends email notifications for build completion
  - SMTP operations only
  - No buildroot or isolation needed
- **Recommendation**: Keep as host-side task handler (no migration needed)

#### 3.6. newRepo
- **Handler Class**: `NewRepoTask`
- **Method**: `newRepo`
- **Status**: N/A (orchestration task)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Coordinates repository generation
  - Spawns `createrepo` subtasks per architecture
  - Handles repo cloning optimization (copies old repodata if possible)
  - Makes hub API calls (repoInit, repoDone)
  - Coordination logic, not build work
  - Lightweight (weight: 0.1)
- **Current Behavior**:
  - Calls `session.host.repoInit()` to initialize repo in hub
  - Checks if old repo can be cloned (same packages)
  - For each architecture:
    - If cloneable, copies repodata directly (host operation)
    - Otherwise, spawns `createrepo` subtask (containerized)
  - Waits for all createrepo subtasks
  - Calls `session.host.repoDone()` to finalize
- **Recommendation**: Keep as host-side task handler. The `createrepo` subtasks are already containerized.

---

### Category 4: Additional Build Tasks (Future Phases) 📦

These tasks involve buildroot operations and could benefit from containerization, but are lower priority than SRPM tasks.

#### 4.1. buildMaven
- **Handler Class**: `BuildMavenTask`
- **Method**: `buildMaven`
- **Status**: ❌ **Not Migrated**
- **Should Containerize**: ⚠️ **MAYBE** (Phase 3+)
- **Rationale**:
  - Maven builds require buildroot with Java toolchain
  - Uses mock/buildroot for dependency resolution
  - Less common than RPM builds in most deployments
  - Would benefit from containerization for isolation
- **Complexity**: High (Maven-specific tooling, artifact handling)
- **Priority**: P2 (defer to Phase 3+, unless Maven builds are critical for your deployment)
- **Dependencies**: Would need Maven-capable container images

#### 4.2. wrapperRPM
- **Handler Class**: `WrapperRPMTask`
- **Method**: `wrapperRPM`
- **Status**: ❌ **Not Migrated**
- **Should Containerize**: ⚠️ **MAYBE** (Phase 3+)
- **Rationale**:
  - Builds wrapper RPMs around Maven or Windows build artifacts
  - Uses buildroot for RPM creation
  - Similar to buildArch but for non-native artifacts
- **Complexity**: Medium (wrapper logic, artifact handling)
- **Priority**: P2 (defer to Phase 3+)

#### 4.3. maven (orchestration)
- **Handler Class**: `MavenTask`
- **Method**: `maven`
- **Status**: N/A (orchestration task)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Orchestrates multi-platform Maven builds
  - Spawns `buildMaven` subtasks
  - Pure coordination, no build work
- **Recommendation**: Keep as host-side task handler

#### 4.4. chainmaven
- **Handler Class**: `ChainMavenTask`
- **Method**: `chainmaven`
- **Status**: N/A (orchestration task)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Orchestrates chain of dependent Maven builds
  - Pure hub API coordination
- **Recommendation**: Keep as host-side task handler

---

### Category 5: Image Building Tasks (Future Phases) 🖼️

Image building tasks use specialized tools (Oz, ImageFactory, livemedia-creator) and could be containerized, but require significant adaptation.

#### 5.1. createImage (Oz-based)
- **Handler Class**: `BaseImageTask`
- **Method**: `createImage`
- **Status**: ❌ **Not Migrated**
- **Should Containerize**: ⚠️ **MAYBE** (Phase 4+)
- **Rationale**:
  - Uses Oz for image creation
  - Requires virtualization (KVM/QEMU)
  - Complex dependencies (Oz, imagefactory, pykickstart)
  - Would need nested virtualization or privileged containers
- **Complexity**: Very High (virtualization, Oz/ImageFactory integration)
- **Priority**: P3 (defer to Phase 4+, or consider alternative approach)
- **Notes**: May not be suitable for containerization due to virtualization requirements

#### 5.2. image, appliance, livecd, livemedia (orchestration)
- **Handler Classes**: `BuildBaseImageTask`, `BuildApplianceTask`, `BuildLiveCDTask`, `BuildLiveMediaTask`
- **Methods**: `image`, `appliance`, `livecd`, `livemedia`
- **Status**: N/A (orchestration tasks)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Orchestrate image build workflows
  - Spawn subtasks (createImage, createAppliance, etc.)
  - Pure coordination logic
- **Recommendation**: Keep as host-side task handlers

#### 5.3. createAppliance, createLiveCD, createLiveMedia
- **Handler Classes**: `ApplianceTask`, `LiveCDTask`, `LiveMediaTask`
- **Methods**: `createAppliance`, `createLiveCD`, `createLiveMedia`
- **Status**: ❌ **Not Migrated**
- **Should Containerize**: ⚠️ **MAYBE** (Phase 4+)
- **Rationale**:
  - Use specialized tools (livemedia-creator, appliance-creator)
  - Require buildroot-like environments
  - Complex kickstart processing
  - Would benefit from isolation
- **Complexity**: Very High (specialized tools, kickstart, repo setup)
- **Priority**: P3 (defer to Phase 4+)
- **Notes**: Less common than RPM builds; assess demand before investing

#### 5.4. indirectionimage
- **Handler Class**: `BuildIndirectionImageTask`
- **Method**: `indirectionimage`
- **Status**: ❌ **Not Migrated**
- **Should Containerize**: ⚠️ **MAYBE** (Phase 4+)
- **Rationale**:
  - Uses ImageFactory for indirection image builds
  - Requires virtualization and complex toolchain
- **Complexity**: Very High
- **Priority**: P3 (defer to Phase 4+)

---

### Category 6: Distribution Repository Tasks (Mixed) 📚

Distribution repo tasks involve coordination and some build-like operations.

#### 6.1. distRepo (orchestration)
- **Handler Class**: `NewDistRepoTask`
- **Method**: `distRepo`
- **Status**: N/A (orchestration task)
- **Should Containerize**: ❌ **NO**
- **Rationale**:
  - Coordinates distribution repository generation
  - Spawns `createdistrepo` subtasks per architecture
  - Pure coordination logic
  - Lightweight (weight: 0.1)
- **Recommendation**: Keep as host-side task handler

#### 6.2. createdistrepo
- **Handler Class**: `createDistRepoTask`
- **Method**: `createdistrepo`
- **Status**: ❌ **Not Migrated**
- **Should Containerize**: ⚠️ **MAYBE** (Phase 3+)
- **Rationale**:
  - Creates distribution repositories (ISO-like structures)
  - Involves pungi, lorax, or similar tools
  - Build-like operations with complex dependencies
  - Would benefit from containerization
- **Complexity**: High (distribution-specific tooling)
- **Priority**: P2 (defer to Phase 3+, assess demand)
- **Notes**: May require custom container images with pungi/lorax

---

## Summary Tables

### Tasks by Migration Status

| Status | Count | Tasks |
|--------|-------|-------|
| ✅ Migrated | 2 | buildArch, createrepo |
| ❌ Critical Gap | 2 | rebuildSRPM, buildSRPMFromSCM |
| ❌ Not Migrated (Lower Priority) | 12 | buildMaven, wrapperRPM, createImage, createAppliance, createLiveCD, createLiveMedia, indirectionimage, createdistrepo, and others |
| N/A (Should Not Migrate) | 10 | build, chainbuild, tagBuild, tagNotification, buildNotification, newRepo, maven, chainmaven, distRepo, image/appliance/livecd/livemedia orchestrators |

### Tasks by Containerization Recommendation

| Recommendation | Count | Rationale |
|----------------|-------|-----------|
| ✅ Already Containerized | 2 | buildArch, createrepo |
| ✅ Should Containerize (Critical) | 2 | rebuildSRPM, buildSRPMFromSCM - **blocks production** |
| ⚠️ Could Containerize (Future) | 8 | buildMaven, wrapperRPM, createImage, createAppliance, createLiveCD, createLiveMedia, indirectionimage, createdistrepo |
| ❌ Should NOT Containerize | 10 | Orchestration and notification tasks (hub API operations only) |

### Priority Breakdown

| Priority | Tasks | Timeline |
|----------|-------|----------|
| **P0 - Critical** | rebuildSRPM, buildSRPMFromSCM | **Phase 2.5** (2-3 weeks) |
| **P1 - High Value** | (none currently) | N/A |
| **P2 - Nice to Have** | buildMaven, wrapperRPM, createdistrepo | Phase 3+ (TBD) |
| **P3 - Low Priority** | Image building tasks | Phase 4+ (TBD) |

---

## Recommendations

### Immediate Action (Phase 2.5) 🚨

**Implement the 2 critical SRPM adapters** to unblock production deployment:

1. **RebuildSRPMAdapter** (Week 1 of Phase 2.5)
   - Similar complexity to buildArch Phase 1
   - Reuse buildroot initialization patterns
   - Estimated: 5-7 days

2. **BuildSRPMFromSCMAdapter** (Week 2 of Phase 2.5)
   - Requires SCM integration module (git/svn)
   - More complex than rebuildSRPM
   - Estimated: 7-10 days

**Rationale**: Without these tasks, koji-adjutant cannot handle standard build workflows (`koji build f39 git://...`). This blocks all production deployment.

### Short-Term (Phase 3)

**Assess demand for additional build tasks**:
- Survey users: Are Maven builds critical for your deployment?
- Survey users: Do you need distribution repo (createdistrepo) support?
- Prioritize based on actual usage patterns

If Maven builds are required:
- Implement `BuildMavenAdapter` (similar to buildArch)
- Create Maven-capable container images
- Estimated: 2-3 weeks

### Medium-Term (Phase 4+)

**Evaluate image building tasks**:
- Image building (Oz, ImageFactory, livemedia-creator) is complex
- May not be suitable for containerization (virtualization requirements)
- Consider alternative approaches (e.g., nested virtualization, privileged containers)
- Only invest if there is significant demand

**Distribution repository tasks**:
- `createdistrepo` could be containerized if needed
- Requires custom images with pungi/lorax
- Assess demand before investing

### Long-Term

**No action needed for orchestration tasks**:
- Orchestration tasks (build, chainbuild, newRepo, etc.) should remain host-side
- They coordinate subtasks and make hub API calls
- No isolation or buildroot requirements
- Current implementation is appropriate

---

## Technical Considerations

### Container Image Requirements

Different tasks require different base images:

| Task Type | Required Tooling | Image Base |
|-----------|------------------|------------|
| buildArch (current) | rpmbuild, dnf/yum, rpm | AlmaLinux 10 |
| SRPM tasks | rpmbuild, git, svn, dnf/yum | AlmaLinux 10 + SCM tools |
| createrepo (current) | createrepo_c, rpm | AlmaLinux 10 |
| Maven builds | maven, java, rpmbuild | AlmaLinux 10 + JDK + Maven |
| Image builds | oz, imagefactory, KVM | Specialized image (if feasible) |
| Dist repo | pungi, lorax, rpm | Specialized image |

**Recommendation**:
- Phase 2.5: Extend current AlmaLinux 10 image with git/svn for SRPM tasks
- Phase 3+: Create specialized images as needed (Maven, dist repo)

### Buildroot Initialization

Tasks that require buildroot initialization:
- buildArch ✅ (implemented in Phase 2)
- rebuildSRPM ❌ (needs implementation in Phase 2.5)
- buildSRPMFromSCM ❌ (needs implementation in Phase 2.5)
- buildMaven ⏸️ (future, if needed)
- wrapperRPM ⏸️ (future, if needed)

**Current Status**: `BuildrootInitializer` exists and is used by buildArch adapter. SRPM adapters will reuse it with `install_group: srpm-build`.

### SCM Integration

BuildSRPMFromSCM requires SCM checkout support:
- Git (most common)
- SVN (less common, still used)
- CVS (deprecated, likely not needed)

**Recommendation**: Create `koji_adjutant/scm.py` module:
- Git checkout via `git clone`
- SVN checkout via `svn checkout`
- URL validation and security checks
- Reuse existing koji SCM class patterns

### Network Requirements

Tasks that require network access:
- buildArch ✅ (for dependency downloads)
- rebuildSRPM ✅ (for dependency downloads)
- buildSRPMFromSCM ✅ (for git clone)
- buildMaven ✅ (for Maven central, dependencies)

**Current Status**: Containers have network enabled by default. This is correct for all build tasks.

---

## Migration Effort Estimates

### Phase 2.5 (SRPM Adapters) - 2-3 weeks
- RebuildSRPMAdapter: 5-7 days
- BuildSRPMFromSCMAdapter: 7-10 days
- SCM integration module: included in above
- Testing and validation: 3-5 days
- **Total: 15-22 days**

### Phase 3 (Optional: Maven Support) - 2-3 weeks
- BuildMavenAdapter: 7-10 days
- Maven container image creation: 2-3 days
- Testing with real Maven projects: 3-5 days
- **Total: 12-18 days**

### Phase 4+ (Image Building) - 6-8 weeks
- Feasibility analysis: 1 week
- Oz/ImageFactory containerization: 2-3 weeks (high risk)
- LiveMedia/Appliance adapters: 2-3 weeks
- Testing and validation: 1-2 weeks
- **Total: 6-9 weeks** (high uncertainty, may not be feasible)

---

## Success Criteria

### Phase 2.5 Complete When:
- [ ] `RebuildSRPMAdapter` implemented and tested
- [ ] `BuildSRPMFromSCMAdapter` implemented and tested
- [ ] SCM integration module supports git and svn
- [ ] End-to-end workflow: `koji build f39 git://...` succeeds
- [ ] Unit tests: 95%+ pass rate for new adapters
- [ ] Integration tests: 100% pass rate with koji-boxed
- [ ] Documentation updated

### Production Ready When (includes Phase 2.5):
- [ ] All P0 tasks implemented (buildArch, createrepo, rebuildSRPM, buildSRPMFromSCM)
- [ ] Koji-boxed integration successful
- [ ] Staging validation complete
- [ ] Performance meets targets (< 10% overhead vs mock)
- [ ] No critical bugs
- [ ] Operator documentation complete

---

## Conclusion

**Current State**: Koji-adjutant has successfully containerized the core buildArch and createrepo tasks, but lacks critical SRPM adapters needed for production deployment.

**Immediate Need**: Phase 2.5 implementation (rebuildSRPM, buildSRPMFromSCM) is required to unblock production. These tasks are well-scoped and follow proven patterns from Phase 1/2.

**Future Decisions**: Additional task migrations (Maven, image builds) should be based on actual deployment requirements and user demand. Not all tasks need containerization - orchestration tasks appropriately remain host-side.

**Recommendation**: **Approve and begin Phase 2.5 immediately** to deliver a complete, production-ready build system.

---

**Document Prepared**: 2025-10-31
**Prepared By**: Implementation Lead
**Next Review**: After Phase 2.5 completion
