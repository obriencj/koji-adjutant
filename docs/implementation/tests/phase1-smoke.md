# Phase 1 Acceptance Criteria and Smoke Test Plan

**Status**: Draft for Implementation
**Target**: Phase 1 Foundation - buildArch and createrepo Tasks
**Based On**: ADR 0001 (Container Lifecycle) and ADR 0002 (Container Image and Security)
**Date**: 2025-01-27

## Overview

This document defines acceptance criteria and executable smoke tests for Phase 1 of Koji-Adjutant. Phase 1 validates that core task types (`buildArch` and `createrepo`) execute successfully in Podman containers with proper lifecycle management, mount configuration, logging, and cleanup.

## Phase 1 Scope

### Task Types Under Test

1. **buildArch**: Builds an RPM package for a specific architecture in a containerized buildroot
   - Input: SRPM file, build tag, architecture
   - Output: RPM artifacts, SRPM (optional), build logs, build root ID
   - Validates: Container execution, artifact generation, hub-compatible result structure

2. **createrepo**: Generates repository metadata for a Koji tag/architecture
   - Input: Repository ID, architecture, optional old repo reference
   - Output: repodata directory with repository metadata
   - Validates: Repository creation, file system operations, metadata correctness

### Integration Points

- **Container Manager**: Podman-based container lifecycle (create, start, stream, wait, remove)
- **Task Adapters**: Translation from Koji task context to `ContainerSpec`
- **Mount Strategy**: `/mnt/koji` and `/work/<task_id>` mounts with SELinux labels
- **Logging**: Streaming to Koji log system and persistence to filesystem
- **Hub Compatibility**: Result structures match kojid expectations

## Acceptance Criteria

### AC1: Container Lifecycle (ADR 0001)

**AC1.1 - Image Availability**
- [ ] Task image is pulled or verified via `ensure_image_available()`
- [ ] Image pull respects `adjutant_image_pull_policy` configuration
- [ ] Pull failures raise `ContainerError` with clear error message
- [ ] Image validation occurs before container creation

**AC1.2 - Container Creation**
- [ ] Container is created from `ContainerSpec` via `create()`
- [ ] Container includes correct labels (`io.koji.adjutant.task_id`, `io.koji.adjutant.worker_id`)
- [ ] Container creation fails gracefully with `ContainerError` on invalid spec
- [ ] Container ID is returned as `ContainerHandle`

**AC1.3 - Container Start**
- [ ] Container starts successfully via `start()` after creation
- [ ] Start timeout is enforced per configuration (default 60s)
- [ ] Start failures trigger cleanup attempt and raise `ContainerError`

**AC1.4 - Log Streaming**
- [ ] Container stdout/stderr are streamed to `LogSink` immediately after start
- [ ] Logs are streamed non-blockingly until container exit
- [ ] Both stdout and stderr are captured and forwarded to Koji log system
- [ ] Log streaming does not block container execution or exit code retrieval

**AC1.5 - Container Wait**
- [ ] `wait()` blocks until container process exits
- [ ] Exit code is returned correctly (0 for success, non-zero for failure)
- [ ] Wait operation does not timeout during normal execution

**AC1.6 - Container Cleanup**
- [ ] Container is removed via `remove()` after task completion (success or failure)
- [ ] Cleanup occurs in finally block or exception handler (guaranteed execution)
- [ ] Force removal (`force=True`) succeeds when container is stuck
- [ ] Container removal errors are logged but do not mask task errors

**AC1.7 - High-Level Run Helper**
- [ ] `run(spec, sink)` executes full lifecycle (create → start → stream → wait → optional remove)
- [ ] `run()` guarantees cleanup via finally block when `remove_after_exit=True`
- [ ] `run()` returns `ContainerRunResult` with exit code and timestamps
- [ ] Exception handling preserves original errors while ensuring cleanup

### AC2: Mount Configuration (ADR 0001)

**AC2.1 - Standard Mounts**
- [ ] `/mnt/koji` is mounted read-write at container path `/mnt/koji` with SELinux label `:Z`
- [ ] Task workspace `/mnt/koji/work/<task_id>` is mounted read-write at `/work/<task_id>` with SELinux label `:Z`
- [ ] Mounts are configured in `ContainerSpec.mounts` as `VolumeMount` entries

**AC2.2 - Mount Permissions**
- [ ] Mounted directories are accessible by container user (UID 1000 for rootless, root otherwise)
- [ ] Container can write to `/mnt/koji` for artifact uploads
- [ ] Container can write to `/work/<task_id>` for temporary files

**AC2.3 - SELinux Labeling**
- [ ] SELinux labels (`:Z` default) are applied to mounts when SELinux is enforcing
- [ ] Container operations succeed without SELinux denials
- [ ] Label configuration respects `adjutant_container_mounts` config value

**AC2.4 - Mount Isolation**
- [ ] Containers only see explicitly mounted paths (no host filesystem access beyond mounts)
- [ ] Mount source paths exist and are accessible from host
- [ ] Mount target paths are created if missing (or Podman creates automatically)

### AC3: Task Execution (buildArch)

**AC3.1 - Task Context**
- [ ] Task adapter builds `ContainerSpec` from `TaskContext` correctly
- [ ] Container command executes build process (mock-like buildroot initialization and RPM build)
- [ ] Environment variables are set correctly (build tag, architecture, paths)
- [ ] Working directory is set appropriately (typically `/work/<task_id>`)

**AC3.2 - Build Execution**
- [ ] Build command executes successfully (exit code 0) for valid SRPM
- [ ] Build artifacts (RPMs, SRPMs) are generated in expected locations
- [ ] Build logs are generated and collected
- [ ] Build root ID (`brootid`) is captured and returned

**AC3.3 - Artifact Generation**
- [ ] RPM files are generated in result directory
- [ ] SRPM is generated when `keep_srpm=True` option is set
- [ ] Build log files are generated (build.log, root.log, state.log, etc.)
- [ ] Artifacts are accessible from host at expected paths under `/mnt/koji`

**AC3.4 - Result Structure (Hub Compatibility)**
- [ ] Task result is a dict with keys: `rpms`, `srpms`, `logs`, `brootid`
- [ ] `rpms`: List of RPM file paths (relative to upload path or absolute)
- [ ] `srpms`: List of SRPM file paths (empty list if `keep_srpm=False`)
- [ ] `logs`: List of log file paths
- [ ] `brootid`: Integer build root ID
- [ ] Result structure matches kojid format exactly

**AC3.5 - Error Handling**
- [ ] Build failures (non-zero exit code) are reported to hub correctly
- [ ] Build errors are logged with context (task ID, command, exit code)
- [ ] Container cleanup occurs even on build failure
- [ ] Error messages are informative and aid debugging

### AC4: Task Execution (createrepo)

**AC4.1 - Task Context**
- [ ] Task adapter builds `ContainerSpec` from `TaskContext` correctly
- [ ] Container command executes `createrepo_c` with correct arguments
- [ ] Repository directory path is correctly resolved and mounted
- [ ] Working directory and environment are configured appropriately

**AC4.2 - Repository Creation**
- [ ] `createrepo_c` command executes successfully (exit code 0)
- [ ] Repository metadata (`repodata/`) is generated in expected location
- [ ] Metadata files are correct (primary.xml, filelists.xml, other.xml, repomd.xml)
- [ ] Repository is usable by package managers (dnf/yum)

**AC4.3 - Repository State**
- [ ] Task validates repository is in INIT state before execution
- [ ] Empty repositories are handled correctly (EMPTY_REPO marker created if needed)
- [ ] External repository merging works when configured
- [ ] Group data (comps.xml) is processed if present

**AC4.4 - Result and Cleanup**
- [ ] Repository metadata is accessible from host at expected paths
- [ ] Container cleanup occurs after successful execution
- [ ] Task completes and reports success to hub

**AC4.5 - Error Handling**
- [ ] Invalid repository state triggers appropriate error
- [ ] Missing repository directory triggers error with clear message
- [ ] Container cleanup occurs on task failure
- [ ] Errors are reported to hub correctly

### AC5: Logging (ADR 0001)

**AC5.1 - Log Streaming**
- [ ] Container stdout/stderr are streamed to Koji log system during execution
- [ ] Logs appear in Koji task logs in real-time (or near real-time)
- [ ] Both stdout and stderr are captured and streamed
- [ ] Log streaming does not interfere with task execution

**AC5.2 - Log Persistence**
- [ ] Container logs are persisted to `/mnt/koji/logs/<task_id>/container.log`
- [ ] Log file contains complete stdout/stderr from container execution
- [ ] Log file is created even if task fails
- [ ] Log file permissions allow reading by koji user and hub processes

**AC5.3 - Log Completeness**
- [ ] All container output (from start to exit) is captured
- [ ] Logs include build output, error messages, and diagnostic information
- [ ] Logs are bounded to prevent disk exhaustion (drop-oldest policy on overflow)

**AC5.4 - Log Integration**
- [ ] Koji log viewer can display container logs
- [ ] Log format matches expected koji log format (or is clearly marked as container log)
- [ ] Log entries are associated with correct task ID

### AC6: Cleanup and Error Handling (ADR 0001)

**AC6.1 - Success Cleanup**
- [ ] Container is removed after successful task completion
- [ ] Container removal succeeds without errors
- [ ] No containers remain after task completion (verified via `podman ps -a`)

**AC6.2 - Failure Cleanup**
- [ ] Container is removed after task failure (build error, timeout, etc.)
- [ ] Cleanup occurs even when exceptions are raised
- [ ] Force removal succeeds for stuck containers
- [ ] Cleanup errors are logged but do not mask original task errors

**AC6.3 - Resource Cleanup**
- [ ] Container network namespaces are cleaned up
- [ ] Container storage volumes are released
- [ ] No resource leaks (containers, mounts, network interfaces)
- [ ] Host filesystem is not polluted with orphaned containers

**AC6.4 - Worker Shutdown**
- [ ] Running containers are stopped gracefully on worker shutdown (SIGTERM)
- [ ] Grace period (default 20s) is respected before force stop
- [ ] All containers are removed before worker exit
- [ ] Shutdown cleanup is logged

### AC7: Hub Compatibility

**AC7.1 - Task Result Format**
- [ ] buildArch result structure matches kojid format:
  - `rpms`: List of strings (file paths)
  - `srpms`: List of strings (file paths or empty list)
  - `logs`: List of strings (file paths)
  - `brootid`: Integer
- [ ] createrepo completes successfully and reports to hub
- [ ] Task status reporting matches kojid behavior (SUCCESS, FAILURE)

**AC7.2 - Artifact Upload**
- [ ] Artifacts are uploaded to hub via standard upload mechanism
- [ ] Upload paths match kojid conventions
- [ ] Artifact metadata (size, checksums) is preserved

**AC7.3 - Error Reporting**
- [ ] Task failures are reported to hub with appropriate error codes
- [ ] Error messages are formatted correctly for hub consumption
- [ ] Hub can distinguish between build failures and system failures

**AC7.4 - API Compatibility**
- [ ] Task handler methods match kojid signatures
- [ ] Task parameters are parsed and validated correctly
- [ ] Task options are handled according to kojid behavior

## Smoke Test Plan

### Test Infrastructure Requirements

#### Prerequisites

1. **Podman Availability**
   - Podman 4.0+ installed and running
   - Podman Python API (`podman` package) available
   - Rootless podman configured (optional but preferred)
   - Podman socket accessible

2. **Container Image**
   - Task image available: `koji-adjutant-task:almalinux10` (or configured default)
   - Image contains required packages: `rpm-build`, `gcc`, `make`, `createrepo_c`, etc.
   - Image can be pulled from configured registry
   - Image is validated before test execution

3. **Filesystem Setup**
   - `/mnt/koji` directory exists and is writable
   - Test workspace directories can be created under `/mnt/koji/work`
   - SELinux context allows container access (if SELinux is enforcing)
   - Permissions allow UID 1000 (or test user) to write

4. **Mock Koji Hub**
   - Mock hub implementation for task submission and result collection
   - XMLRPC server or stub that accepts task results
   - Ability to validate result structure and format
   - Log capture for validation

5. **Test Data**
   - Sample SRPM file for buildArch tests
   - Sample repository directory structure for createrepo tests
   - Reference artifacts for comparison
   - Known-good outputs for validation

#### Test Environment Setup

```bash
# Example test setup script
#!/bin/bash
set -euo pipefail

# Verify Podman
podman --version
podman ps

# Pull test image (if not present)
podman pull koji-adjutant-task:almalinux10

# Create test directories
mkdir -p /mnt/koji/work
mkdir -p /mnt/koji/logs
chmod 755 /mnt/koji/work /mnt/koji/logs

# Verify SELinux (if applicable)
getenforce

# Run tests
pytest tests/integration/test_phase1_smoke.py -v
```

### Smoke Test Structure

#### ST1: Container Lifecycle Smoke Tests

**ST1.1 - Image Availability Test**
```python
def test_image_availability():
    """Verify container image can be pulled and validated."""
    # Test steps:
    # 1. Call ensure_image_available() with test image
    # 2. Verify image exists locally or is pulled
    # 3. Verify ContainerError raised on invalid image
    # 4. Verify pull policy is respected
```

**ST1.2 - Container Creation and Start Test**
```python
def test_container_create_start():
    """Verify container creation and start lifecycle."""
    # Test steps:
    # 1. Create ContainerSpec with minimal valid config
    # 2. Call create() and verify ContainerHandle returned
    # 3. Call start() and verify container starts
    # 4. Verify container is running (podman ps)
    # 5. Verify labels are set correctly
```

**ST1.3 - Log Streaming Test**
```python
def test_log_streaming():
    """Verify container logs are streamed correctly."""
    # Test steps:
    # 1. Create and start container with known output command
    # 2. Stream logs to InMemoryLogSink
    # 3. Verify stdout/stderr captured
    # 4. Verify logs match container output
    # 5. Verify streaming completes when container exits
```

**ST1.4 - Container Wait and Exit Code Test**
```python
def test_container_wait_exit_code():
    """Verify wait() returns correct exit codes."""
    # Test steps:
    # 1. Run container with exit 0 command, verify exit_code=0
    # 2. Run container with exit 1 command, verify exit_code=1
    # 3. Verify wait() blocks until completion
    # 4. Verify ContainerRunResult timestamps are set
```

**ST1.5 - Container Cleanup Test**
```python
def test_container_cleanup():
    """Verify container cleanup on success and failure."""
    # Test steps:
    # 1. Run container successfully, verify removal
    # 2. Run container with failure, verify removal
    # 3. Verify no containers remain (podman ps -a)
    # 4. Test force removal for stuck container
```

**ST1.6 - High-Level Run Helper Test**
```python
def test_container_run_helper():
    """Verify run() helper executes full lifecycle."""
    # Test steps:
    # 1. Call run() with valid spec and sink
    # 2. Verify create → start → stream → wait → remove sequence
    # 3. Verify cleanup occurs on exception
    # 4. Verify ContainerRunResult is returned
```

#### ST2: Mount Configuration Smoke Tests

**ST2.1 - Standard Mounts Test**
```python
def test_standard_mounts():
    """Verify standard mounts are configured correctly."""
    # Test steps:
    # 1. Create container with default mounts (/mnt/koji, /work/<task_id>)
    # 2. Verify mounts are present in ContainerSpec
    # 3. Verify mount source paths exist
    # 4. Verify SELinux labels are applied (:Z default)
```

**ST2.2 - Mount Permissions Test**
```python
def test_mount_permissions():
    """Verify container can read/write mounted directories."""
    # Test steps:
    # 1. Create container with /mnt/koji mount
    # 2. Execute command to write file to /mnt/koji/test
    # 3. Verify file exists on host
    # 4. Execute command to read file from mount
    # 5. Verify permissions allow container user access
```

**ST2.3 - SELinux Labeling Test**
```python
def test_selinux_labeling():
    """Verify SELinux labels are applied correctly."""
    # Test steps:
    # 1. Create container with mount having :Z label
    # 2. Verify container can access mount (no SELinux denials)
    # 3. Check SELinux context on mounted files (if enforcing)
    # 4. Verify label configuration is respected
```

**ST2.4 - Mount Isolation Test**
```python
def test_mount_isolation():
    """Verify containers only see mounted paths."""
    # Test steps:
    # 1. Create container with minimal mounts
    # 2. Execute command to list / (should not see host filesystem)
    # 3. Verify only mounted paths are accessible
    # 4. Verify host paths outside mounts are not visible
```

#### ST3: buildArch Task Smoke Tests

**ST3.1 - BuildArch Task Execution Test**
```python
def test_buildarch_task_execution():
    """Verify buildArch task executes successfully in container."""
    # Test steps:
    # 1. Create TaskContext with test task_id, work_dir, koji_mount_root
    # 2. Build ContainerSpec from context using BuildArchTask adapter
    # 3. Execute container via ContainerManager.run()
    # 4. Verify exit code is 0
    # 5. Verify container is removed after completion
```

**ST3.2 - BuildArch Artifact Generation Test**
```python
def test_buildarch_artifacts():
    """Verify buildArch generates expected artifacts."""
    # Test steps:
    # 1. Execute buildArch task with test SRPM
    # 2. Verify RPM files exist in result directory
    # 3. Verify SRPM exists (if keep_srpm=True)
    # 4. Verify build logs exist (build.log, root.log, etc.)
    # 5. Verify artifacts are accessible from host at /mnt/koji paths
```

**ST3.3 - BuildArch Result Structure Test**
```python
def test_buildarch_result_structure():
    """Verify buildArch result matches kojid format."""
    # Test steps:
    # 1. Execute buildArch task and capture result
    # 2. Verify result is dict with keys: rpms, srpms, logs, brootid
    # 3. Verify rpms is list of file paths (strings)
    # 4. Verify srpms is list (empty or single SRPM path)
    # 5. Verify logs is list of log file paths
    # 6. Verify brootid is integer
    # 7. Compare structure with kojid reference output
```

**ST3.4 - BuildArch Error Handling Test**
```python
def test_buildarch_error_handling():
    """Verify buildArch handles errors correctly."""
    # Test steps:
    # 1. Execute buildArch with invalid SRPM (should fail)
    # 2. Verify exit code is non-zero
    # 3. Verify error is logged appropriately
    # 4. Verify container is cleaned up
    # 5. Verify error is reported to hub (or mock)
```

**ST3.5 - BuildArch Hub Compatibility Test**
```python
def test_buildarch_hub_compatibility():
    """Verify buildArch results are hub-compatible."""
    # Test steps:
    # 1. Execute buildArch task
    # 2. Submit result to mock hub
    # 3. Verify hub accepts result format
    # 4. Verify artifact paths are valid
    # 5. Verify result can be processed by hub (matches kojid expectations)
```

#### ST4: createrepo Task Smoke Tests

**ST4.1 - Createrepo Task Execution Test**
```python
def test_createrepo_task_execution():
    """Verify createrepo task executes successfully in container."""
    # Test steps:
    # 1. Create test repository directory with package files
    # 2. Create TaskContext for createrepo task
    # 3. Build ContainerSpec using CreaterepoTask adapter
    # 4. Execute container via ContainerManager.run()
    # 5. Verify exit code is 0
    # 6. Verify container is removed after completion
```

**ST4.2 - Createrepo Metadata Generation Test**
```python
def test_createrepo_metadata():
    """Verify createrepo generates correct repository metadata."""
    # Test steps:
    # 1. Execute createrepo task with test repository
    # 2. Verify repodata/ directory is created
    # 3. Verify metadata files exist: primary.xml, filelists.xml, other.xml, repomd.xml
    # 4. Verify metadata is valid (can be read by dnf/yum)
    # 5. Verify metadata is accessible from host
```

**ST4.3 - Createrepo Empty Repository Test**
```python
def test_createrepo_empty_repo():
    """Verify createrepo handles empty repositories correctly."""
    # Test steps:
    # 1. Execute createrepo with empty repository (no packages)
    # 2. Verify EMPTY_REPO marker is created (if pkglist is empty)
    # 3. Verify task completes successfully
    # 4. Verify appropriate metadata is generated
```

**ST4.4 - Createrepo Error Handling Test**
```python
def test_createrepo_error_handling():
    """Verify createrepo handles errors correctly."""
    # Test steps:
    # 1. Execute createrepo with invalid repository state
    # 2. Verify error is raised appropriately
    # 3. Verify container is cleaned up
    # 4. Verify error is reported to hub
```

#### ST5: Logging Smoke Tests

**ST5.1 - Log Streaming Test**
```python
def test_log_streaming_to_koji():
    """Verify logs are streamed to Koji log system."""
    # Test steps:
    # 1. Execute task with known output
    # 2. Capture logs via mock KojiLogSink
    # 3. Verify stdout/stderr are captured
    # 4. Verify logs appear in correct order
    # 5. Verify all output is captured (no truncation)
```

**ST5.2 - Log Persistence Test**
```python
def test_log_persistence():
    """Verify logs are persisted to filesystem."""
    # Test steps:
    # 1. Execute task
    # 2. Verify /mnt/koji/logs/<task_id>/container.log exists
    # 3. Verify log file contains complete container output
    # 4. Verify log file permissions allow reading
    # 5. Verify log file is created even on task failure
```

**ST5.3 - Log Completeness Test**
```python
def test_log_completeness():
    """Verify all container output is logged."""
    # Test steps:
    # 1. Execute task with extensive output
    # 2. Compare container.log with direct container output
    # 3. Verify no lines are missing
    # 4. Verify both stdout and stderr are included
    # 5. Verify log boundaries are correct (start to exit)
```

#### ST6: Cleanup and Error Handling Smoke Tests

**ST6.1 - Success Cleanup Test**
```python
def test_success_cleanup():
    """Verify cleanup occurs after successful task completion."""
    # Test steps:
    # 1. Execute successful task
    # 2. Verify container is removed (podman ps -a shows no container)
    # 3. Verify container labels enable identification
    # 4. Verify no resource leaks
```

**ST6.2 - Failure Cleanup Test**
```python
def test_failure_cleanup():
    """Verify cleanup occurs after task failure."""
    # Test steps:
    # 1. Execute task that fails (non-zero exit code)
    # 2. Verify container is removed
    # 3. Verify cleanup occurs even when exception is raised
    # 4. Verify original error is preserved
```

**ST6.3 - Force Cleanup Test**
```python
def test_force_cleanup():
    """Verify force removal works for stuck containers."""
    # Test steps:
    # 1. Create container that doesn't exit (or simulate stuck)
    # 2. Attempt removal with force=True
    # 3. Verify container is forcefully removed
    # 4. Verify graceful stop timeout is respected before force
```

**ST6.4 - Worker Shutdown Cleanup Test**
```python
def test_worker_shutdown_cleanup():
    """Verify containers are cleaned up on worker shutdown."""
    # Test steps:
    # 1. Start multiple tasks (containers)
    # 2. Send SIGTERM to worker
    # 3. Verify graceful stop is attempted (SIGTERM to containers)
    # 4. Verify force stop after grace period
    # 5. Verify all containers are removed before worker exit
```

## Test Execution

### Local Execution

**Prerequisites:**
1. Podman installed and running
2. Test image available or pullable
3. Test directories created (`/mnt/koji/work`, `/mnt/koji/logs`)
4. Python test dependencies installed (`pytest`, `podman`)

**Run All Smoke Tests:**
```bash
cd /home/siege/koji-adjutant
pytest tests/integration/test_phase1_smoke.py -v --tb=short
```

**Run Specific Test Suite:**
```bash
# Container lifecycle tests
pytest tests/integration/test_phase1_smoke.py::ST1 -v

# buildArch tests
pytest tests/integration/test_phase1_smoke.py::ST3 -v

# createrepo tests
pytest tests/integration/test_phase1_smoke.py::ST4 -v
```

**Run with Coverage:**
```bash
pytest tests/integration/test_phase1_smoke.py --cov=koji_adjutant --cov-report=html
```

### CI Execution

**CI Pipeline Steps:**
1. **Setup**: Install Podman, pull test image, create test directories
2. **Unit Tests**: Run unit tests (fast, no containers)
3. **Smoke Tests**: Run Phase 1 smoke tests (containers required)
4. **Cleanup**: Remove test containers and artifacts
5. **Reporting**: Generate test reports and coverage

**CI Configuration Example:**
```yaml
# .github/workflows/phase1-smoke.yml
name: Phase 1 Smoke Tests

on: [push, pull_request]

jobs:
  smoke-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Podman
        run: |
          sudo apt-get update
          sudo apt-get install -y podman
          podman --version
      - name: Pull Test Image
        run: podman pull koji-adjutant-task:almalinux10
      - name: Create Test Directories
        run: |
          sudo mkdir -p /mnt/koji/work /mnt/koji/logs
          sudo chmod 755 /mnt/koji/work /mnt/koji/logs
      - name: Run Smoke Tests
        run: pytest tests/integration/test_phase1_smoke.py -v
      - name: Cleanup
        run: podman ps -aq | xargs -r podman rm -f
```

### Test Data Management

**Test SRPM:**
- Minimal valid SRPM file for buildArch tests
- Should build successfully with standard toolchain
- Should generate predictable artifacts

**Test Repository:**
- Directory structure: `/mnt/koji/repos/<tag>/<arch>/`
- Contains sample RPM packages
- Includes `pkglist` file
- May include `groups/comps.xml` for group data

**Reference Outputs:**
- Known-good buildArch result structure (from kojid reference)
- Expected log formats
- Expected artifact layouts

## Success Metrics

### Exit Codes
- **All Tests Pass**: Exit code 0
- **Any Test Failure**: Exit code 1
- **Container Exit Codes**: 0 for success, non-zero for failure (must match task outcome)

### Artifact Presence
- **buildArch**: RPM files, SRPM (if `keep_srpm=True`), build logs exist at expected paths
- **createrepo**: `repodata/` directory with metadata files exists
- **All Artifacts**: Accessible from host filesystem, readable by hub processes

### Log Completeness
- **Streamed Logs**: All stdout/stderr captured and forwarded to Koji
- **Persisted Logs**: Complete container output in `/mnt/koji/logs/<task_id>/container.log`
- **Log Format**: Readable, includes timestamps and output type markers

### Cleanup Verification
- **Container Removal**: No containers remain after task completion (`podman ps -a` empty)
- **Resource Cleanup**: No orphaned network namespaces, mounts, or storage
- **Cleanup on Failure**: Containers removed even when tasks fail

### Hub Compatibility
- **Result Structure**: Matches kojid format exactly (validated against reference)
- **Artifact Paths**: Valid and accessible by hub
- **Task Status**: Reported correctly (SUCCESS/FAILURE)
- **Error Reporting**: Errors formatted for hub consumption

## Test Reporting

### Test Results Format

**Success Criteria:**
- All smoke tests pass
- No container leaks
- All acceptance criteria validated
- Hub compatibility confirmed

**Failure Reporting:**
- Failed test names and error messages
- Container logs for failed tests
- Artifact locations for inspection
- Debug commands for troubleshooting

### Metrics Collection

**Execution Metrics:**
- Test execution time
- Container creation time
- Task execution time
- Cleanup time

**Resource Metrics:**
- Container count before/after tests
- Disk usage for test artifacts
- Memory usage during tests

**Coverage Metrics:**
- Code coverage for tested components
- Acceptance criteria coverage
- Task type coverage

## Troubleshooting

### Common Issues

**Container Creation Failures:**
- Verify Podman is running
- Check image availability
- Verify SELinux labels (if enforcing)
- Check mount permissions

**Mount Permission Errors:**
- Verify directory ownership (UID 1000 or root)
- Check SELinux contexts
- Verify mount source paths exist
- Check filesystem permissions

**Log Streaming Issues:**
- Verify LogSink implementation
- Check container output redirection
- Verify non-blocking log streaming
- Check log persistence path permissions

**Cleanup Failures:**
- Verify `remove()` is called in finally blocks
- Check force removal for stuck containers
- Verify container labels for identification
- Check Podman daemon health

### Debug Commands

```bash
# List all containers (including stopped)
podman ps -a

# Inspect container
podman inspect <container_id>

# Check container logs
podman logs <container_id>

# Verify mounts
podman inspect <container_id> | jq '.[0].Mounts'

# Check SELinux labels
ls -Z /mnt/koji/work/

# Verify image availability
podman images | grep koji-adjutant-task

# Check container resource usage
podman stats <container_id>
```

## Next Steps

1. **Implementation Lead**: Code smoke tests based on this plan
2. **Test Infrastructure**: Set up CI pipeline and test data
3. **Execution**: Run smoke tests and validate acceptance criteria
4. **Documentation**: Update with test results and any deviations
5. **Phase 2 Planning**: Use Phase 1 results to inform Phase 2 test requirements

## References

- **ADR 0001**: Container Lifecycle, Mounts, and Manager Boundaries
- **ADR 0002**: Container Image Bootstrap, Security, and Operational Details
- **Koji Reference**: `/home/siege/koji/builder/kojid` (original kojid implementation)
- **Container Interface**: `/home/siege/koji-adjutant/koji_adjutant/container/interface.py`
- **Task Adapters**: `/home/siege/koji-adjutant/koji_adjutant/task_adapters/base.py`
