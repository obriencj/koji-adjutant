# Phase 2.2: exec() Pattern Impact Analysis

**Date**: 2025-10-30
**Change**: Switch from single bash -c command to exec()-based step execution
**Rationale**: Cleaner config file placement, better debugging, explicit step control

---

## Current Approach (As Implemented)

### Flow
```
1. Generate init script on host → /mnt/koji/work/12345/buildroot-init.sh
2. Mount /mnt/koji and /work into container
3. Single command: bash -c "run init script && rpmbuild"
4. Init script writes repo config using heredoc (cat > /etc/yum.repos.d/koji.repo)
5. Results collected via mounted volume
```

### Problems
- Init script embeds repo config as heredoc (awkward)
- RPM macros could be files but are passed as --define flags
- All-or-nothing execution (can't debug intermediate steps)
- Complex bash -c escaping

---

## New Approach (exec() Pattern)

### Flow
```
1. Generate config files on host:
   - /mnt/koji/work/12345/koji.repo
   - /mnt/koji/work/12345/macros.koji
   - /mnt/koji/work/12345/init-env.sh (simplified)

2. Create container with /mnt/koji and /work mounts + sleep infinity

3. Copy files to proper locations:
   manager.copy_to(handle, koji_repo, "/etc/yum.repos.d/koji.repo")
   manager.copy_to(handle, macros, "/etc/rpm/macros.koji")

4. Execute initialization steps:
   manager.exec(handle, ["bash", "/work/12345/init-env.sh"])  # Just env setup
   manager.exec(handle, ["dnf", "install", "-y", "gcc", "make", ...])

5. Execute build:
   manager.exec(handle, ["rpmbuild", "--rebuild", "/work/12345/work/pkg.src.rpm"])

6. Remove container (results already on host via mount)
```

### Benefits
- Config files go directly where they belong
- Each step is explicit and debuggable
- No heredoc escaping in bash scripts
- Can pause/inspect between steps
- Better error attribution (know which step failed)

---

## Files Impacted

### 1. `koji_adjutant/container/interface.py` ✏️ **MODIFY**

**Add to ContainerManager protocol:**
```python
def exec(
    self,
    handle: ContainerHandle,
    command: Sequence[str],
    sink: LogSink,
    environment: Optional[Dict[str, str]] = None
) -> int:
    """Execute command in running container.

    Args:
        handle: Container to execute in
        command: Command and arguments to execute
        sink: Log sink for stdout/stderr
        environment: Optional environment variables

    Returns:
        Exit code from command

    Raises:
        ContainerError: If execution fails
    """
    ...

def copy_to(
    self,
    handle: ContainerHandle,
    src_path: Path,
    dest_path: str
) -> None:
    """Copy file from host to container.

    Args:
        handle: Container to copy to
        src_path: Host filesystem path
        dest_path: Container filesystem path (absolute)

    Raises:
        ContainerError: If copy fails
    """
    ...
```

**Impact**: Protocol addition (backward compatible - existing code doesn't break)

---

### 2. `koji_adjutant/container/podman_manager.py` ✏️ **MODIFY**

**Add two new methods:**

```python
def exec(self, handle, command, sink, environment=None):
    """Execute command in running container via podman exec."""
    self._ensure_client()
    container = self._client.containers.get(handle.container_id)

    # Podman exec
    exec_result = container.exec_run(
        cmd=list(command),
        environment=environment or {},
        stream=True,
        demux=True  # Separate stdout/stderr
    )

    # Stream output to sink
    for stream_type, data in exec_result.output:
        if stream_type == 'stdout':
            sink.write_stdout(data)
        else:
            sink.write_stderr(data)

    return exec_result.exit_code

def copy_to(self, handle, src_path, dest_path):
    """Copy file to container using podman cp."""
    self._ensure_client()
    container = self._client.containers.get(handle.container_id)

    # Podman Python API uses put_archive (tar-based)
    import tarfile
    import io

    # Create tar archive of single file
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
        tar.add(src_path, arcname=os.path.basename(dest_path))
    tar_stream.seek(0)

    # Put archive in container at parent directory
    dest_dir = os.path.dirname(dest_path)
    container.put_archive(path=dest_dir, data=tar_stream.read())
```

**Impact**: Two new methods, ~50 lines of code

**Testing needed**:
- Unit tests for exec() and copy_to()
- Integration test with real container

---

### 3. `koji_adjutant/buildroot/initializer.py` ✏️ **MODIFY**

**Changes to `initialize()` method:**

Current returns:
```python
{
    "script": "#!/bin/bash\n...",  # Big bash script with heredocs
    "repo_config": "...",
    "dependencies": [...],
    "macros": {...},
    "environment": {...}
}
```

New returns:
```python
{
    "repo_file_content": "[koji-repo]\nbaseurl=...",  # Content only
    "repo_file_dest": "/etc/yum.repos.d/koji.repo",   # Where it goes

    "macros_file_content": "%dist .fc39\n%_topdir /builddir\n...",
    "macros_file_dest": "/etc/rpm/macros.koji",

    "init_commands": [  # Explicit command list instead of script
        ["mkdir", "-p", "/builddir/BUILD", "/builddir/RPMS", ...],
        ["dnf", "install", "-y", "gcc", "make", "python3-devel", ...],
    ],

    "build_command": [  # Explicit RPM build command
        "rpmbuild",
        "--rebuild",
        "/work/12345/work/mypackage.src.rpm",
        "--define", "_topdir /builddir",
        "--define", "_rpmdir /work/12345/result",
        ...
    ],

    "dependencies": [...],    # Keep for reference
    "environment": {...},     # Keep for exec environment
    "tag_id": 123,
    "tag_name": "f39-build"
}
```

**Changes to `_generate_init_script()`:**

**REMOVE** (or simplify to just env setup):
- Heredoc for repo config → becomes file content
- Heredoc for macros → becomes file content
- dnf install command → becomes explicit command in list

**Impact**: Refactor ~100 lines, more structured output

---

### 4. `koji_adjutant/buildroot/repos.py` - **NO CHANGE** ✅

Already returns repo config content as string. Perfect!

---

### 5. `koji_adjutant/buildroot/environment.py` - **NO CHANGE** ✅

Already returns macros as dict and env vars as dict. Perfect!

---

### 6. `koji_adjutant/task_adapters/buildarch.py` ✏️ **MAJOR REFACTOR**

**Current approach (lines 110-217):**
```python
# Generate init script
init_result = initializer.initialize(...)
init_script_path = ctx.work_dir / "buildroot-init.sh"
init_script_path.write_text(init_result["script"])

# Single bash -c command
command = ["/bin/bash", "-c", "bash init-script.sh && rpmbuild ..."]

# Execute
result = manager.run(spec, sink)
```

**New approach:**
```python
# Generate initialization data
init_result = initializer.initialize(...)

# Write config files to host work dir
repo_file = ctx.work_dir / "koji.repo"
repo_file.write_text(init_result["repo_file_content"])

macros_file = ctx.work_dir / "macros.koji"
macros_file.write_text(init_result["macros_file_content"])

# Create container spec with sleep command
spec = ContainerSpec(
    image=image,
    command=["/bin/sleep", "infinity"],  # Keep alive
    mounts=[...],
    ...
)

# Create and start container
handle = manager.create(spec)
manager.start(handle)
manager.stream_logs(handle, sink, follow=False)  # Background logging

try:
    # Copy config files to proper locations
    manager.copy_to(handle, repo_file, init_result["repo_file_dest"])
    manager.copy_to(handle, macros_file, init_result["macros_file_dest"])

    # Execute initialization commands
    for cmd in init_result["init_commands"]:
        exit_code = manager.exec(handle, cmd, sink, init_result["environment"])
        if exit_code != 0:
            raise ContainerError(f"Init command failed: {cmd}")

    # Execute build
    exit_code = manager.exec(
        handle,
        init_result["build_command"],
        sink,
        init_result["environment"]
    )

    if exit_code != 0:
        raise ContainerError(f"Build failed with exit code {exit_code}")

finally:
    # Always cleanup
    manager.remove(handle, force=True)

# Collect results (same as before)
result_dir = ctx.work_dir / "result"
...
```

**Impact**: Refactor ~150 lines in build_spec() and run()

**Key changes:**
- Replace `manager.run()` with create/start/exec/remove sequence
- Write config files on host, copy them in
- Execute commands explicitly instead of bash -c
- Better error handling per step

---

### 7. `koji_adjutant/task_adapters/createrepo.py` - **MINOR CHANGE** ⚠️

**Current**: Uses manager.run() with single command

**New**: Could stay as-is (simple task) OR refactor for consistency

**Recommendation**: Leave as-is for Phase 2.2, refactor in Phase 2.3 for consistency

**Impact**: Optional, ~20 lines if refactored

---

## Testing Impact

### Unit Tests to Add/Modify

1. **`tests/unit/test_podman_manager.py`** - NEW
   - Test `exec()` method
   - Test `copy_to()` method
   - Mock container.exec_run() and container.put_archive()

2. **`tests/unit/test_buildroot_initializer.py`** - MODIFY
   - Update assertions for new return structure
   - Verify repo_file_content, macros_file_content
   - Verify init_commands list structure

3. **`tests/integration/test_buildarch_adapter.py`** - MODIFY
   - Test full flow with exec pattern
   - Verify config files copied correctly
   - Verify commands execute in order
   - Test failure at each step

### Integration Tests

**New test**: `tests/integration/test_phase2_exec_pattern.py`
```python
def test_exec_pattern_buildroot_init():
    """Verify exec() pattern works for buildroot initialization."""
    # Create container with sleep
    # Copy config files
    # Exec init commands
    # Verify files exist in container
    # Verify commands executed
```

---

## Migration Strategy

### Option A: Clean Break (Recommended)
1. Implement exec() and copy_to() in PodmanManager
2. Refactor BuildrootInitializer return structure
3. Refactor BuildArchAdapter to use new pattern
4. Update tests
5. Remove old bash -c generation code

**Timeline**: 1 session

### Option B: Gradual (Safer but more work)
1. Implement exec() and copy_to() alongside existing run()
2. Add config flag: `adjutant_use_exec_pattern = true/false`
3. Implement new pattern in parallel with old
4. Test both paths
5. Deprecate old pattern in Phase 2.3

**Timeline**: 2 sessions

**Recommendation**: Option A - we're already in Phase 2.2 development, not production yet

---

## Backward Compatibility

### Breaking Changes: **NONE** ✅

- `ContainerManager` protocol gets new methods (additions only)
- Existing `run()` method still works
- Phase 1 simple builds unaffected (don't use buildroot init)
- Config-based fallback still works

### Forward Compatibility

- exec() pattern enables future enhancements:
  - Interactive debugging (exec into running container)
  - Progress reporting (step-by-step status)
  - Partial retry (re-run failed step only)
  - Build caching (skip already-completed steps)

---

## Summary of Changes

| File | Type | Lines Changed | Complexity |
|------|------|---------------|------------|
| `container/interface.py` | Add | +30 | Low |
| `container/podman_manager.py` | Add | +50 | Medium |
| `buildroot/initializer.py` | Refactor | ~100 | Medium |
| `task_adapters/buildarch.py` | Refactor | ~150 | High |
| `tests/unit/test_podman_manager.py` | New | +100 | Medium |
| `tests/unit/test_buildroot_initializer.py` | Modify | ~50 | Low |
| `tests/integration/test_phase2_exec.py` | New | +150 | Medium |
| **TOTAL** | | **~630 lines** | **Medium** |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| exec() API differs from run() | Low | Medium | Comprehensive unit tests |
| Log streaming complexity | Medium | Low | Reuse existing LogSink pattern |
| File copy failures | Low | Medium | Error handling + cleanup in finally |
| Performance regression | Low | Low | Multiple exec calls are fast |
| Container lifecycle issues | Medium | High | Always cleanup in finally block |

---

## Next Steps

1. ✅ Create this impact analysis
2. ⏳ Implement exec() and copy_to() in PodmanManager
3. ⏳ Refactor BuildrootInitializer return structure
4. ⏳ Refactor BuildArchAdapter to use exec pattern
5. ⏳ Write unit tests for new methods
6. ⏳ Write integration test for full flow
7. ⏳ Update WORKFLOW.md with new pattern
8. ⏳ Test with real SRPM build

**Estimated effort**: 4-6 hours of focused development + testing

---

## Open Questions

1. Should we also refactor CreaterepoAdapter for consistency? **Decision: Not in Phase 2.2**
2. Should init_commands include environment per-command? **Decision: Use global env from init_result**
3. Should we keep old bash script generation as fallback? **Decision: No, clean break**
4. Log streaming: per-exec or global? **Decision: Global stream_logs() + per-exec output to sink**

---

**Approval Status**: Pending review
**Ready to implement**: Yes, pending stakeholder approval
