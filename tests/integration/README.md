# Phase 1 Smoke Tests

This directory contains integration smoke tests for Phase 1 of Koji-Adjutant, validating container-based task execution.

## Prerequisites

### Required

1. **Podman 4.0+**
   ```bash
   podman --version
   ```

2. **Podman Python API** (`podman` package)
   ```bash
   pip install podman
   # or
   python3 -m pip install podman
   ```

3. **pytest**
   ```bash
   pip install pytest
   # or
   python3 -m pip install pytest
   ```

### Optional (for full test coverage)

- Test container image (default: `registry.almalinux.org/almalinux/9-minimal:latest`)
- Override with: `export KOJI_ADJUTANT_TEST_IMAGE=<your-image>`

### Filesystem Setup

Tests use temporary directories by default (via pytest `tmp_path` fixture), but if you want to test with actual `/mnt/koji` paths:

```bash
# Create test directories (optional - tests create temporary dirs)
sudo mkdir -p /mnt/koji/work /mnt/koji/logs /mnt/koji/repos
sudo chmod 755 /mnt/koji/work /mnt/koji/logs /mnt/koji/repos
```

## Running Tests

### Run All Smoke Tests

```bash
cd /home/siege/koji-adjutant
pytest tests/integration/test_phase1_smoke.py -v
```

### Run Specific Test

```bash
# Image availability test
pytest tests/integration/test_phase1_smoke.py::test_st1_1_image_availability -v

# Log streaming test
pytest tests/integration/test_phase1_smoke.py::test_st1_3_log_streaming -v

# Container cleanup test
pytest tests/integration/test_phase1_smoke.py::test_st1_5_container_cleanup -v

# Mount permissions test
pytest tests/integration/test_phase1_smoke.py::test_st2_2_mount_permissions -v

# BuildArch adapter test
pytest tests/integration/test_phase1_smoke.py::test_st3_1_buildarch_task_execution -v

# Createrepo adapter test
pytest tests/integration/test_phase1_smoke.py::test_st4_1_createrepo_task_execution -v
```

### Run with Coverage

```bash
pip install pytest-cov
pytest tests/integration/test_phase1_smoke.py --cov=koji_adjutant --cov-report=html
```

### Run with Verbose Output

```bash
pytest tests/integration/test_phase1_smoke.py -v -s
```

## Test Structure

### ST1: Container Lifecycle Tests
- `test_st1_1_image_availability`: Image pull and validation
- `test_st1_3_log_streaming`: Log streaming to LogSink
- `test_st1_5_container_cleanup`: Container cleanup on success/failure

### ST2: Mount Configuration Tests
- `test_st2_2_mount_permissions`: Read/write access to mounted directories

### ST3: buildArch Task Tests
- `test_st3_1_buildarch_task_execution`: BuildArch adapter spec generation and validation

### ST4: createrepo Task Tests
- `test_st4_1_createrepo_task_execution`: Createrepo adapter spec generation and validation

### Additional Tests
- `test_log_persistence_to_filesystem`: Log file persistence validation

## Test Environment Variables

- `KOJI_ADJUTANT_TEST_IMAGE`: Override default test container image
  ```bash
  export KOJI_ADJUTANT_TEST_IMAGE=registry.almalinux.org/almalinux/9-minimal:latest
  ```

## Troubleshooting

### Podman Not Available

Tests will skip automatically if Podman Python API is not available:
```
SKIPPED [1] tests/integration/test_phase1_smoke.py: Podman Python API not available
```

### Image Pull Failures

If test image cannot be pulled:
```
SKIPPED [1] tests/integration/test_phase1_smoke.py: Test image not available: ...
```

Ensure:
1. Network connectivity for image pull
2. Image registry is accessible
3. Podman is configured for rootless access (if running non-root)

### Permission Errors

If tests fail with permission errors:
1. Ensure Podman is running: `podman info`
2. Check rootless podman setup: `podman unshare id`
3. Verify test directories are writable

### Container Cleanup Issues

If containers remain after tests:
```bash
# List all containers
podman ps -a

# Remove test containers
podman ps -a --filter "label=io.koji.adjutant.worker_id=test-worker" -q | xargs -r podman rm -f
```

## Expected Test Duration

- Individual tests: 5-30 seconds each
- Full suite: ~2-5 minutes (depending on image pull time)

## Integration with CI

See main test plan document for CI configuration:
`/home/siege/koji-adjutant/docs/implementation/tests/phase1-smoke.md`
