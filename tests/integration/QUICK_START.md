# Phase 1 Smoke Tests - Quick Start Guide

## TL;DR

```bash
# Install dependencies
pip install pytest podman

# Run all tests
cd /home/siege/koji-adjutant
pytest tests/integration/test_phase1_smoke.py -v

# Run specific test
pytest tests/integration/test_phase1_smoke.py::test_st1_1_image_availability -v
```

## What Was Implemented

### Test Files
- `test_phase1_smoke.py` - Main test suite with 7 smoke tests
- `README.md` - Detailed test documentation
- `TEST_EXECUTION_REPORT.md` - Template for test execution results
- `VALIDATED_AC_SUMMARY.md` - Acceptance criteria validation summary

### Tests Implemented

#### ST1: Container Lifecycle (3 tests)
1. **ST1.1** - Image availability validation
2. **ST1.3** - Log streaming to LogSink
3. **ST1.5** - Container cleanup on success/failure

#### ST2: Mount Configuration (1 test)
1. **ST2.2** - Mount permissions (read/write access)

#### ST3: buildArch Task (1 test)
1. **ST3.1** - BuildArch adapter spec generation

#### ST4: createrepo Task (1 test)
1. **ST4.1** - Createrepo adapter spec generation

#### Additional (1 test)
1. **Log Persistence** - Filesystem log file creation

## Prerequisites

### Minimum Requirements
- Python 3.11+
- pytest
- Podman Python API (`podman` package)
- Podman 4.0+ (for actual test execution)

### Optional
- Test container image (defaults to `registry.almalinux.org/almalinux/9-minimal:latest`)
- Override with: `export KOJI_ADJUTANT_TEST_IMAGE=<image>`

## Running Tests

### Check Prerequisites
```bash
# Check Podman
podman --version

# Check Python packages
python3 -c "import pytest, podman; print('OK')"
```

### Run All Tests
```bash
pytest tests/integration/test_phase1_smoke.py -v
```

### Run by Category
```bash
# Lifecycle tests
pytest tests/integration/test_phase1_smoke.py -k "st1" -v

# Mount tests
pytest tests/integration/test_phase1_smoke.py -k "st2" -v

# Task adapter tests
pytest tests/integration/test_phase1_smoke.py -k "st3 or st4" -v
```

### With Coverage
```bash
pip install pytest-cov
pytest tests/integration/test_phase1_smoke.py --cov=koji_adjutant --cov-report=html
```

## Expected Results

### Success Case
```
test_st1_1_image_availability PASSED
test_st1_3_log_streaming PASSED
test_st1_5_container_cleanup PASSED
test_st2_2_mount_permissions PASSED
test_st3_1_buildarch_task_execution PASSED
test_st4_1_createrepo_task_execution PASSED
test_log_persistence_to_filesystem PASSED

======================== 7 passed in XX.XXs ========================
```

### Skip Case (No Podman)
```
test_st1_1_image_availability SKIPPED [1] Podman Python API not available
...
```

## What Gets Validated

### ✅ Fully Validated (9 criteria)
- AC1.1: Image availability
- AC1.4: Log streaming
- AC1.6: Container cleanup
- AC2.2: Mount permissions
- AC3.1: BuildArch task context
- AC4.1: Createrepo task context
- AC5.2: Log persistence
- AC6.1: Success cleanup
- AC6.2: Failure cleanup

### ⚠️ Partially Validated (4 criteria)
- AC1.2-AC1.3, AC1.5, AC1.7: Covered by other tests

### 📋 Deferred to Phase 2 (19 criteria)
- Full task execution (requires build dependencies)
- Hub integration (requires koji hub)
- SELinux labeling (requires SELinux system)
- Comprehensive error scenarios

## Troubleshooting

### Test Skips Due to Missing Podman
**Solution**: Install Podman Python API
```bash
pip install podman
```

### Image Pull Failures
**Solution**: Check network and image availability
```bash
podman pull registry.almalinux.org/almalinux/9-minimal:latest
```

### Permission Errors
**Solution**: Ensure Podman is running and accessible
```bash
podman info
```

## Next Steps

1. **Execute Tests**: Run the test suite in your environment
2. **Fill Report**: Complete `TEST_EXECUTION_REPORT.md` with results
3. **Phase 2 Planning**: Use validation summary for Phase 2 test requirements

## Files Reference

| File | Purpose |
|------|---------|
| `test_phase1_smoke.py` | Main test implementation |
| `README.md` | Detailed documentation |
| `TEST_EXECUTION_REPORT.md` | Test results template |
| `VALIDATED_AC_SUMMARY.md` | Acceptance criteria validation |
| `QUICK_START.md` | This file |

## Support

For issues or questions:
1. Check `tests/integration/README.md` for detailed troubleshooting
2. Review test plan: `docs/implementation/tests/phase1-smoke.md`
3. Check acceptance criteria: `docs/implementation/tests/phase1-smoke.md` (AC1-AC7)
