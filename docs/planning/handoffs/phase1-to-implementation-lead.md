# Phase 1 Handoff: Implementation Lead - Task Adapters

**Date**: 2025-01-27
**From**: Strategic Planner
**To**: Implementation Lead
**Status**: Ready for Implementation

## Context

Phase 1 foundation work is complete:
- ✅ **ADR 0001**: Container lifecycle and manager boundaries (Accepted)
- ✅ **ADR 0002**: Container image bootstrap and security (Accepted)
- ✅ **PodmanManager**: Fully implemented with all lifecycle methods
- ✅ **Test Plan**: Comprehensive smoke test plan with acceptance criteria

Remaining Phase 1 work: Wire task adapters to execute buildArch and createrepo tasks inside containers.

## Scope

### Primary Tasks

1. **Implement buildArch Task Adapter**
   - Translate Koji buildArch task context to `ContainerSpec`
   - Execute RPM build inside container
   - Collect artifacts (RPMs, SRPMs, logs) and format result for hub
   - Handle errors and cleanup

2. **Implement createrepo Task Adapter**
   - Translate Koji createrepo task context to `ContainerSpec`
   - Execute `createrepo_c` inside container
   - Generate repository metadata and format result for hub
   - Handle errors and cleanup

3. **Integrate with Koji Task Handlers**
   - Wire adapters into existing kojid task handler pattern
   - Maintain hub API compatibility (task result structures)
   - Stream container logs to Koji log system
   - Handle task lifecycle (start, execute, complete, cleanup)

### Secondary Tasks (if time permits)

4. **Log Persistence**
   - Write container logs to `/mnt/koji/logs/<task_id>/container.log`
   - Ensure log file creation even on failures

5. **Config Integration**
   - Parse adjutant config keys from `kojid.conf` (beyond stubs)
   - Apply defaults from ADR 0001/0002

## Reference Materials

### Architecture Decisions
- **ADR 0001**: `/home/siege/koji-adjutant/docs/architecture/decisions/0001-container-lifecycle.md`
  - Container lifecycle steps
  - Mount strategy (`/mnt/koji`, `/work/<task_id>`)
  - SELinux labeling (`:Z` default)
  - Network policy (enabled by default)
  - Cleanup guarantees

- **ADR 0002**: `/home/siege/koji-adjutant/docs/architecture/decisions/0002-container-image-and-security.md`
  - Task image: `koji-adjutant-task:almalinux10` (or configured default)
  - UID/GID: Rootless preferred (1000:1000), root fallback
  - Image packages: `rpm-build`, `gcc`, `createrepo_c`, etc.
  - Worker shutdown handling

### Existing Code
- **Container Interface**: `/home/siege/koji-adjutant/koji_adjutant/container/interface.py`
  - `ContainerManager` protocol
  - `ContainerSpec`, `VolumeMount`, `ResourceLimits`
  - `LogSink` protocol

- **PodmanManager**: `/home/siege/koji-adjutant/koji_adjutant/container/podman_manager.py`
  - Full implementation ready to use
  - Methods: `ensure_image_available`, `create`, `start`, `stream_logs`, `wait`, `remove`, `run`

- **Task Adapter Base**: `/home/siege/koji-adjutant/koji_adjutant/task_adapters/base.py`
  - `BaseTaskAdapter` protocol
  - `TaskContext` dataclass
  - `default_mounts()` helper

- **Original kojid**: `/home/siege/koji/builder/kojid`
  - Reference for task handler patterns
  - Reference for result structure format
  - Reference for hub API compatibility

### Test Plan
- **Smoke Tests**: `/home/siege/koji-adjutant/docs/implementation/tests/phase1-smoke.md`
  - Acceptance criteria for both task types
  - Test structure and prerequisites
  - Success metrics

## Key Constraints

1. **Hub Compatibility**: Task result structures must match kojid format exactly
   - buildArch: `{rpms: [paths], srpms: [paths], logs: [paths], brootid: int}`
   - createrepo: Success/failure status reported to hub

2. **Mount Strategy**: Use `default_mounts()` helper from `task_adapters/base.py`
   - `/mnt/koji` → `/mnt/koji` (rw, :Z)
   - `/mnt/koji/work/<task_id>` → `/work/<task_id>` (rw, :Z)

3. **Image Selection**: Phase 1 uses single default image
   - Config: `adjutant_task_image_default` (default: `registry/almalinux:10`)
   - Future: Hub policy-driven selection (deferred)

4. **Logging**: Stream to Koji via `LogSink`, persist to filesystem
   - Container logs → Koji task logs (real-time)
   - Container logs → `/mnt/koji/logs/<task_id>/container.log` (persistence)

5. **Cleanup**: Always remove containers (success or failure)
   - Use `ContainerManager.run()` which guarantees cleanup
   - Or manually ensure `remove()` in finally blocks

## Implementation Approach

### Step 1: BuildArch Adapter Structure

Create `koji_adjutant/task_adapters/buildarch.py`:

```python
class BuildArchAdapter(BaseTaskAdapter):
    def build_spec(self, ctx: TaskContext, task_params: dict) -> ContainerSpec:
        # 1. Resolve task image from config
        # 2. Build command (rpmbuild or mock-like build)
        # 3. Set environment (KOJI_TASK_ID, build tag, arch, paths)
        # 4. Configure mounts (default_mounts + any task-specific)
        # 5. Set workdir to /work/<task_id>
        # 6. Set user_id/group_id (1000:1000 for rootless, or None)
        # 7. Return ContainerSpec

    def run(self, ctx: TaskContext, manager: ContainerManager, sink: LogSink) -> int:
        # 1. Build ContainerSpec via build_spec()
        # 2. Call manager.run(spec, sink)
        # 3. Collect artifacts from /mnt/koji paths
        # 4. Format result dict (rpms, srpms, logs, brootid)
        # 5. Return exit code
```

### Step 2: Createrepo Adapter Structure

Create `koji_adjutant/task_adapters/createrepo.py`:

```python
class CreaterepoAdapter(BaseTaskAdapter):
    def build_spec(self, ctx: TaskContext, task_params: dict) -> ContainerSpec:
        # 1. Resolve task image
        # 2. Build createrepo_c command with arguments
        # 3. Set environment (KOJI_TASK_ID, repo path, etc.)
        # 4. Configure mounts (repo directory, /mnt/koji)
        # 5. Set workdir
        # 6. Return ContainerSpec

    def run(self, ctx: TaskContext, manager: ContainerManager, sink: LogSink) -> int:
        # 1. Build ContainerSpec
        # 2. Call manager.run(spec, sink)
        # 3. Validate repodata generation
        # 4. Return exit code
```

### Step 3: Integration with kojid Task Handlers

Reference `/home/siege/koji/builder/kojid` for original handler patterns:
- `BuildTask.handler()` method signature
- Task parameter parsing
- Result structure format
- Hub upload mechanisms

Wire adapters into handler methods:
- Replace mock chroot setup with `ContainerManager` usage
- Maintain same handler signatures for hub compatibility
- Preserve task result format

## Deliverables

1. **Code Files**:
   - `koji_adjutant/task_adapters/buildarch.py` - BuildArch adapter
   - `koji_adjutant/task_adapters/createrepo.py` - Createrepo adapter
   - Updates to `koji_adjutant/task_adapters/__init__.py` - Export adapters

2. **Integration**:
   - Wire adapters into kojid task handlers (preserve hub compatibility)
   - Ensure container logs stream to Koji
   - Ensure log persistence to filesystem

3. **Testing**:
   - Manual validation: Can execute buildArch and createrepo tasks
   - Verify artifact generation and result structure
   - Verify cleanup occurs

## Acceptance Criteria (from Test Plan)

- ✅ **AC3.1-AC3.5**: buildArch task execution, artifacts, result structure, error handling, hub compatibility
- ✅ **AC4.1-AC4.5**: createrepo task execution, metadata generation, error handling
- ✅ **AC5.1-AC5.4**: Log streaming and persistence
- ✅ **AC6.1-AC6.4**: Cleanup on success/failure, worker shutdown
- ✅ **AC7.1-AC7.4**: Hub compatibility (result format, artifact upload, error reporting, API compatibility)

## Risks and Mitigations

1. **Build Command Complexity**: RPM builds involve complex mock-like setup
   - **Mitigation**: Start with minimal build command, iterate on complexity
   - Reference: Original kojid build command construction

2. **Artifact Path Resolution**: Need to locate RPMs/logs after container execution
   - **Mitigation**: Use predictable paths under `/mnt/koji`, match kojid conventions
   - Reference: Original kojid artifact layout

3. **Hub Result Format**: Must match exact kojid structure
   - **Mitigation**: Compare against original kojid result format
   - Test: Submit result to mock hub and validate

4. **Log Streaming Integration**: Wire container logs to Koji log system
   - **Mitigation**: Implement `KojiLogSink` that calls Koji log upload API
   - Reference: Original kojid log handling

## Questions for Implementation Lead

If unclear, consult:
- Systems Architect: Interface boundaries, component design
- Container Engineer: Image contents, mount/security specifics
- Quality Engineer: Test expectations and acceptance criteria

## Success Criteria

Phase 1 is complete when:
1. buildArch task executes in container and produces valid artifacts
2. createrepo task executes in container and generates valid repo metadata
3. Both tasks report results to hub in kojid-compatible format
4. Containers are cleaned up on success and failure
5. Logs are streamed to Koji and persisted to filesystem

## Next Steps After Completion

1. Quality Engineer reviews implementation against acceptance criteria
2. Smoke tests are executed and validated
3. Phase 1 documentation updated with findings
4. Phase 2 planning begins (hub policy-driven image selection, performance optimization)
