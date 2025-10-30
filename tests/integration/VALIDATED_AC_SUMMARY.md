# Phase 1 Smoke Tests - Validated Acceptance Criteria Summary

This document summarizes which acceptance criteria from the Phase 1 test plan have been validated by the implemented smoke tests.

## Validated Criteria

### AC1: Container Lifecycle (ADR 0001)

#### ✅ AC1.1 - Image Availability
**Test**: `test_st1_1_image_availability` (ST1.1)

**Validated**:
- Task image is pulled or verified via `ensure_image_available()`
- Image pull respects `adjutant_image_pull_policy` configuration  
- Pull failures raise `ContainerError` with clear error message
- Image validation occurs before container creation

**Coverage**: Full validation

---

#### ✅ AC1.4 - Log Streaming
**Test**: `test_st1_3_log_streaming` (ST1.3)

**Validated**:
- Container stdout/stderr are streamed to `LogSink` immediately after start
- Logs are streamed non-blockingly until container exit
- Both stdout and stderr are captured and forwarded
- Log streaming does not block container execution or exit code retrieval

**Coverage**: Full validation

---

#### ✅ AC1.6 - Container Cleanup
**Test**: `test_st1_5_container_cleanup` (ST1.5)

**Validated**:
- Container is removed via `remove()` after task completion (success or failure)
- Cleanup occurs in finally block or exception handler (guaranteed execution)
- Force removal (`force=True`) succeeds when container is stuck (via `run()` implementation)
- Container removal errors are logged but do not mask task errors

**Coverage**: Full validation

---

### AC2: Mount Configuration (ADR 0001)

#### ✅ AC2.2 - Mount Permissions
**Test**: `test_st2_2_mount_permissions` (ST2.2)

**Validated**:
- Mounted directories are accessible by container user (UID 1000 for rootless, root otherwise)
- Container can write to mounted paths for artifact uploads
- Container can read files from mounted directories

**Coverage**: Core permission validation

**Note**: Full SELinux validation (AC2.3) deferred to Phase 2

---

### AC3: Task Execution (buildArch)

#### ✅ AC3.1 - Task Context
**Test**: `test_st3_1_buildarch_task_execution` (ST3.1)

**Validated**:
- Task adapter builds `ContainerSpec` from `TaskContext` correctly
- Container command structure is correct
- Environment variables are set correctly (build tag, architecture, paths)
- Working directory is set appropriately (`/work/<task_id>`)
- Mounts are configured correctly

**Coverage**: Spec generation validation

**Note**: Full build execution (AC3.2-AC3.5) deferred to Phase 2 (requires build dependencies in image)

---

### AC4: Task Execution (createrepo)

#### ✅ AC4.1 - Task Context
**Test**: `test_st4_1_createrepo_task_execution` (ST4.1

**Validated**:
- Task adapter builds `ContainerSpec` from `TaskContext` correctly
- Container command structure for `createrepo_c` is correct
- Repository directory path is correctly resolved and mounted
- Working directory and environment are configured appropriately

**Coverage**: Spec generation validation

**Note**: Full repository creation (AC4.2-AC4.5) deferred to Phase 2 (requires createrepo_c in image)

---

### AC5: Logging (ADR 0001)

#### ✅ AC5.2 - Log Persistence
**Test**: `test_log_persistence_to_filesystem`

**Validated**:
- Container logs are persisted to `/mnt/koji/logs/<task_id>/container.log`
- Log file contains complete stdout/stderr from container execution
- Log file is created even if task fails
- Log file permissions allow reading by koji user and hub processes

**Coverage**: Full validation

**Note**: Real-time streaming to Koji (AC5.1) validated via ST1.3

---

### AC6: Cleanup and Error Handling (ADR 0001)

#### ✅ AC6.1 - Success Cleanup
**Test**: `test_st1_5_container_cleanup` (ST1.5, Test 1)

**Validated**:
- Container is removed after successful task completion
- Container removal succeeds without errors
- No containers remain after task completion (verified via `podman ps -a`)

**Coverage**: Full validation

---

#### ✅ AC6.2 - Failure Cleanup
**Test**: `test_st1_5_container_cleanup` (ST1.5, Test 2)

**Validated**:
- Container is removed after task failure (build error, timeout, etc.)
- Cleanup occurs even when exceptions are raised
- Force removal succeeds for stuck containers

**Coverage**: Full validation

---

## Partially Validated (Covered by Other Tests)

These criteria are validated indirectly through the smoke tests:

- **AC1.2 - Container Creation**: Validated via all container execution tests
- **AC1.3 - Container Start**: Validated via ST1.3, ST1.5, ST2.2
- **AC1.5 - Container Wait**: Validated via all tests that check exit codes
- **AC1.7 - High-Level Run Helper**: Validated via all `run()` calls in tests
- **AC5.1 - Log Streaming**: Validated via ST1.3 (InMemoryLogSink captures streams)

## Deferred to Phase 2

The following criteria require additional infrastructure or full task execution:

### AC1: Container Lifecycle
- **AC1.2**: Container labels verification (needs Podman inspection)
- **AC1.3**: Start timeout enforcement (needs timeout test)

### AC2: Mount Configuration
- **AC2.1**: Standard mounts structure validation (full mount list)
- **AC2.3**: SELinux labeling enforcement (needs SELinux-enabled system)
- **AC2.4**: Mount isolation verification (needs security context tests)

### AC3: Task Execution (buildArch)
- **AC3.2**: Build execution with real SRPM (requires build dependencies)
- **AC3.3**: Artifact generation validation (requires successful build)
- **AC3.4**: Result structure matching kojid format (requires artifacts)
- **AC3.5**: Error handling with invalid inputs (requires full build environment)

### AC4: Task Execution (createrepo)
- **AC4.2**: Repository metadata generation (requires createrepo_c in image)
- **AC4.3**: Repository state validation (requires koji integration)
- **AC4.4**: Result and cleanup after createrepo (requires successful execution)
- **AC4.5**: Error handling for createrepo (requires full environment)

### AC5: Logging
- **AC5.3**: Log completeness verification (requires extensive output)
- **AC5.4**: Log integration with Koji viewer (requires hub integration)

### AC6: Cleanup and Error Handling
- **AC6.3**: Resource cleanup (network, storage volumes)
- **AC6.4**: Worker shutdown cleanup (requires signal handling tests)

### AC7: Hub Compatibility
- **AC7.1**: Task result format validation (requires full task execution)
- **AC7.2**: Artifact upload verification (requires hub integration)
- **AC7.3**: Error reporting format (requires hub integration)
- **AC7.4**: API compatibility (requires full kojid integration)

## Test Coverage Summary

### By Test Suite

| Test Suite | Tests | ACs Validated | Coverage |
|------------|-------|---------------|----------|
| ST1 (Lifecycle) | 3 | AC1.1, AC1.4, AC1.6, AC6.1, AC6.2 | 5 criteria | Core lifecycle |
| ST2 (Mounts) | 1 | AC2.2 | 1 criterion | Permissions only |
| ST3 (buildArch) | 1 | AC3.1 | 1 criterion | Spec generation |
| ST4 (createrepo) | 1 | AC4.1 | 1 criterion | Spec generation |
| Log Persistence | 1 | AC5.2 | 1 criterion | File logging |
| **Total** | **7** | **9 criteria** | **Core functionality** |

### By Acceptance Criteria Group

| AC Group | Total Criteria | Validated | Partial | Deferred |
|----------|---------------|-----------|---------|----------|
| AC1 (Lifecycle) | 7 | 3 | 4 | 0 |
| AC2 (Mounts) | 4 | 1 | 0 | 3 |
| AC3 (buildArch) | 5 | 1 | 0 | 4 |
| AC4 (createrepo) | 5 | 1 | 0 | 4 |
| AC5 (Logging) | 4 | 2 | 0 | 2 |
| AC6 (Cleanup) | 4 | 2 | 0 | 2 |
| AC7 (Hub) | 4 | 0 | 0 | 4 |
| **Total** | **33** | **10** | **4** | **19** |

## Conclusion

**Phase 1 Smoke Tests validate the critical path for container-based task execution:**

✅ **Core Container Operations**: Image management, lifecycle, cleanup  
✅ **Logging Infrastructure**: Streaming and persistence  
✅ **Mount Configuration**: Basic permissions  
✅ **Task Adapter Spec Generation**: Both buildArch and createrepo  

**Gap Analysis for Phase 2:**

1. **Full Task Execution**: Tests validate spec generation but not full task runs (requires build dependencies)
2. **Hub Integration**: Tests validate local execution but not hub compatibility (requires koji hub)
3. **Error Scenarios**: Tests validate success paths primarily (needs comprehensive error tests)
4. **SELinux**: Tests validate basic mounts but not SELinux labeling (requires SELinux system)

**Phase 1 Status**: **CORE FUNCTIONALITY VALIDATED** ✅

The implemented smoke tests successfully validate that:
- PodmanManager correctly implements ContainerManager interface
- Container lifecycle is properly managed (create, start, log, wait, cleanup)
- Mounts are accessible with correct permissions
- Task adapters generate correct ContainerSpec structures
- Logs are streamed and persisted correctly

These tests provide confidence that Phase 1 implementation is sound and ready for Phase 2 expansion.
