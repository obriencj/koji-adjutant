# Phase 2.2 exec() Pattern Fix Report

**Date**: 2024
**Quality Engineer**: Fixing integration test failures for exec() pattern

## Issue Summary

Integration tests for Phase 2.2 exec() pattern were failing with "not enough values to unpack" errors at line 157 in `koji_adjutant/container/podman_manager.py`.

**Root Cause**: The podman-py `exec_run(stream=True, demux=True)` API can return chunks in different formats:
- Tuples `(stdout_bytes, stderr_bytes)` when demux works correctly
- Raw `bytes` when demux doesn't separate streams properly
- `None` values (already handled)
- Tuples with unexpected lengths

The original code assumed all chunks would be 2-element tuples, causing unpacking errors.

## Fixes Applied

### 1. Fixed exec() Method (`koji_adjutant/container/podman_manager.py`)

**Location**: Lines 153-185

**Changes**:
- Added robust handling for different chunk formats from podman-py
- Handle tuple format with defensive length checking
- Handle bytes format (when demux doesn't work)
- Add fallback for other types with conversion attempt

**Code Changes**:
```python
# Before (line 157):
stdout_data, stderr_data = chunk

# After (lines 160-185):
if isinstance(chunk, tuple):
    # Handle tuple format: (stdout_bytes, stderr_bytes)
    # Some versions may return tuples with different lengths
    if len(chunk) >= 2:
        stdout_data, stderr_data = chunk[0], chunk[1]
    elif len(chunk) == 1:
        stdout_data, stderr_data = chunk[0], None
    else:
        continue  # Skip empty tuples
    
    if stdout_data:
        sink.write_stdout(stdout_data)
    if stderr_data:
        sink.write_stderr(stderr_data)
elif isinstance(chunk, bytes):
    # When demux doesn't work, treat as stdout
    sink.write_stdout(chunk)
else:
    # Defensive: convert to bytes if possible
    try:
        data = bytes(chunk)
        sink.write_stdout(data)
    except (TypeError, ValueError):
        # Skip chunks we can't handle
        continue
```

### 2. Created Manual Validation Script

**Location**: `tests/manual/validate_exec_pattern.py`

**Purpose**: Provides manual validation of exec() and copy_to() methods with real podman containers.

**Features**:
- Test basic exec() command execution
- Test copy_to() file copy functionality
- Test exec() with environment variables
- Comprehensive error reporting and cleanup

**Usage**:
```bash
python tests/manual/validate_exec_pattern.py
```

## Testing Plan

### Integration Tests

Run Phase 2.2 exec pattern tests:
```bash
tox -e py3 -- tests/integration/test_exec_pattern.py -v
```

**Expected Results**: All 5 tests should pass:
1. `test_exec_basic_command` - Basic exec() execution
2. `test_copy_to_basic` - File copy functionality
3. `test_exec_pattern_full_flow` - Full exec pattern workflow
4. `test_exec_error_handling` - Error handling validation
5. `test_copy_to_error_handling` - Copy error handling

### Backward Compatibility Tests

Verify Phase 1 tests still pass:
```bash
tox -e py3 -- tests/integration/test_phase1_smoke.py -v
```

**Expected Results**: 6/7 tests should pass (same as before Phase 2.2)

### Unit Tests

Unit tests should continue to pass (they mock the expected tuple format):
```bash
tox -e py3 -- tests/unit/test_container_exec.py -v
```

## Validation Checklist

- [x] Fixed exec() method to handle different return formats
- [x] Added defensive tuple length checking
- [x] Added bytes format handling
- [x] Created manual validation script
- [x] Code passes linter checks
- [ ] Integration tests pass (requires manual execution)
- [ ] Backward compatibility confirmed (requires manual execution)

## Technical Details

### Podman-py exec_run Behavior

The `exec_run()` method with `stream=True` and `demux=True` returns a generator that yields:

1. **When demux works**: Tuples of `(stdout_bytes, stderr_bytes)`
   - Either element can be `None` if that stream had no data
   - Example: `(b"hello", None)` or `(None, b"error")` or `(b"out", b"err")`

2. **When demux doesn't work**: Raw bytes
   - Combined stdout/stderr output
   - Example: `b"combined output"`

3. **Edge cases**:
   - `None` values (already handled)
   - Empty tuples `()`
   - Single-element tuples `(bytes,)`

### Defensive Programming Approach

The fix uses a layered approach:
1. Type checking (`isinstance(chunk, tuple)`)
2. Length validation before unpacking
3. Fallback to bytes handling
4. Graceful degradation (skip unhandled chunks)

This ensures compatibility across different podman-py versions and API behaviors.

## Files Modified

1. `koji_adjutant/container/podman_manager.py` - Fixed exec() method
2. `tests/manual/validate_exec_pattern.py` - Created manual validation script
3. `docs/implementation/phase2.2-exec-pattern-fix-report.md` - This report

## Next Steps

1. **Run Integration Tests**: Execute test suite to verify fixes
2. **Manual Validation**: Run manual validation script if needed
3. **Backward Compatibility**: Verify Phase 1 tests still pass
4. **Documentation**: Update any relevant docs if behavior changed

## Notes

- The fix maintains backward compatibility with existing code
- Unit tests should continue to pass (they mock tuple format)
- The fix is defensive and handles edge cases gracefully
- Exit code retrieval logic unchanged (still executes command twice due to podman-py limitation)

## References

- Original issue: Integration test failures with "not enough values to unpack"
- Related: Phase 2.2 exec pattern implementation
- Podman-py API: `container.exec_run(stream=True, demux=True)`
