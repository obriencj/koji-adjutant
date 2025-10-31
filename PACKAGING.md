# Koji-Adjutant Packaging Guide

**Updated**: 2025-10-31
**Version**: 0.1.0

---

## Overview

Koji-adjutant is packaged as a standard Python package with a wheel distribution. The `kojid` daemon is available as a console script entry point after installation.

---

## Quick Start

### Build Wheel

```bash
make build
```

This creates: `dist/koji_adjutant-0.1.0-py3-none-any.whl`

### Install Package

```bash
# Install from wheel
pip install dist/koji_adjutant-0.1.0-py3-none-any.whl

# Or install from source (development mode)
make dev
```

### Run kojid

```bash
# After installation, kojid is in PATH:
kojid --help
kojid --fg --verbose --config=/etc/kojid/kojid.conf
```

---

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make build` | Build wheel distribution via tox |
| `make dist` | Build wheel and source distribution |
| `make install` | Install package locally |
| `make dev` | Install in editable/development mode |
| `make test` | Run test suite via tox |
| `make lint` | Run code quality checks |
| `make coverage` | Generate test coverage report |
| `make clean` | Remove build artifacts |
| `make check` | Run lint + test |
| `make help` | Show help message |

---

## Package Structure

```
koji-adjutant/
├── koji_adjutant/           # Main package
│   ├── __init__.py
│   ├── kojid.py            # Main daemon (with entry point)
│   ├── config.py
│   ├── container/          # Container abstraction
│   ├── task_adapters/      # Task adapters (buildArch, SRPM, etc.)
│   ├── buildroot/          # Buildroot initialization
│   ├── policy/             # Hub policy integration
│   └── monitoring/         # Monitoring server
├── tests/                   # Test suite
├── docs/                    # Documentation
├── setup.cfg               # Package configuration
├── setup.py                # Setup script
├── Makefile                # Build automation
└── README.md               # Project README
```

---

## Entry Point Configuration

**Console Script**: `kojid`

**Entry Point**: `koji_adjutant.kojid:main_entrypoint`

**Configuration** (in setup.cfg):
```ini
[options.entry_points]
console_scripts =
    kojid = koji_adjutant.kojid:main_entrypoint
```

**What This Means**:
- After installing koji-adjutant, `kojid` command is available in PATH
- No need to specify `python3 /path/to/kojid.py`
- Just run: `kojid --fg --verbose`

---

## Building for Distribution

### Local Build

```bash
# Build wheel
make build

# Output: dist/koji_adjutant-0.1.0-py3-none-any.whl
```

### Building for Containers

**In Dockerfile**:
```dockerfile
# Copy source
COPY koji-adjutant/ /mnt/koji-adjutant/

# Install
RUN python3 -m pip install --no-cache-dir -e /mnt/koji-adjutant/

# kojid is now available as 'kojid' command (no path needed)
```

**Or using wheel**:
```dockerfile
# Copy wheel
COPY koji-adjutant/dist/*.whl /tmp/

# Install wheel
RUN python3 -m pip install --no-cache-dir /tmp/*.whl

# kojid is available
```

**In entrypoint.sh**:
```bash
# Just call kojid (in PATH)
exec kojid --fg ${BUILDER_ARGS}
```

---

## Development Workflow

### Install for Development

```bash
# Editable install with dev dependencies
make dev

# Or manually:
pip install -e .[dev]
```

**Benefits**:
- Changes to source files reflected immediately
- No need to reinstall after code changes
- Includes dev tools (pytest, flake8, mypy, etc.)

### Run Tests

```bash
# Via Makefile
make test

# Via tox directly
tox -e py3

# Specific tests
tox -e py3 -- tests/unit/test_rebuild_srpm_adapter.py -v
```

### Run Linting

```bash
# Via Makefile
make lint

# Via tox
tox -e lint
```

### Generate Coverage

```bash
# Via Makefile
make coverage

# Opens htmlcov/index.html with results
```

---

## Installation Methods

### Method 1: From Wheel (Production)

```bash
# Build wheel
cd /home/siege/koji-adjutant
make build

# Install wheel
pip install dist/koji_adjutant-0.1.0-py3-none-any.whl

# Verify
which kojid
kojid --help
```

### Method 2: From Source (Development)

```bash
# Install editable
cd /home/siege/koji-adjutant
make dev

# Or manually
pip install -e .

# Verify
which kojid
kojid --help
```

### Method 3: From Git (Direct)

```bash
# Install directly from git checkout
pip install /path/to/koji-adjutant

# Or from git URL (future)
pip install git+https://github.com/koji-adjutant/koji-adjutant.git
```

---

## Dependencies

### Runtime Dependencies

**Required**:
- Python 3.11+
- podman >= 4.0.0 (podman-py Python package)
- koji (typically system-installed from RPM)

**System Packages** (for full functionality):
- podman (container runtime)
- rpm-build (for SRPM operations)
- git (for SCM checkout)
- createrepo_c (for repository generation)

### Development Dependencies

```bash
pip install -e .[dev]
```

**Includes**:
- pytest >= 8.0.0
- pytest-cov >= 4.0.0
- pytest-xdist >= 3.0.0
- black >= 24.0.0
- isort >= 5.13.0
- flake8 >= 7.0.0
- mypy >= 1.8.0
- types-setuptools

---

## Tox Environments

| Environment | Purpose | Command |
|-------------|---------|---------|
| `py3` | Run test suite | `tox -e py3` |
| `lint` | Code quality checks | `tox -e lint` |
| `coverage` | Coverage report | `tox -e coverage` |
| `build` | Build wheel | `tox -e build` |

---

## Entry Point Details

### How It Works

**Before** (manual execution):
```bash
python3 /path/to/koji_adjutant/kojid.py --fg --verbose
```

**After** (with entry point):
```bash
kojid --fg --verbose
```

### Implementation

**Entry Point Wrapper** (`kojid.py:main_entrypoint()`):
```python
def main_entrypoint():
    """Console script entry point for kojid daemon."""
    # Parse options
    options = get_options()

    # Setup logging
    # ... configure logging ...

    # Create session and authenticate
    glob_session = koji.ClientSession(...)
    glob_session.gssapi_login(...)

    # Run main daemon
    main(options, glob_session)
```

**Registered in setup.cfg**:
```ini
[options.entry_points]
console_scripts =
    kojid = koji_adjutant.kojid:main_entrypoint
```

---

## Verification

### Check Entry Point Installed

```bash
# Install package
pip install -e .

# Check kojid is in PATH
which kojid
# Output: /usr/local/bin/kojid (or similar)

# Check it's our version
kojid --version  # (if version flag implemented)

# Check it runs
kojid --help
```

### Check Wheel Contents

```bash
# Build wheel
make build

# List contents
python3 -m zipfile -l dist/koji_adjutant-0.1.0-py3-none-any.whl

# Should include:
# - koji_adjutant/ (package files)
# - koji_adjutant-0.1.0.dist-info/entry_points.txt
# - entry_points.txt should contain: kojid = koji_adjutant.kojid:main_entrypoint
```

---

## Usage in Containers

### Dockerfile Pattern

```dockerfile
# Install koji-adjutant
COPY adjutant/ /mnt/koji-adjutant/
RUN python3 -m pip install --no-cache-dir -e /mnt/koji-adjutant/

# kojid is now available in PATH
```

### Entrypoint Pattern

```bash
#!/bin/bash
# ... configuration ...

# Run kojid (no path needed)
exec kojid --fg ${BUILDER_ARGS}
```

**Benefits**:
- Cleaner Dockerfile (no file copying)
- Standard Python packaging
- Easier to upgrade (just reinstall package)
- Entry point handles all initialization

---

## Distribution

### Creating Release

```bash
# Clean previous builds
make clean

# Build distributions
make dist

# Creates:
# - dist/koji_adjutant-0.1.0-py3-none-any.whl (wheel)
# - dist/koji-adjutant-0.1.0.tar.gz (source)
```

### Publishing (Future)

```bash
# To PyPI (when ready)
twine upload dist/*

# To internal package repository
# ... repository-specific commands ...
```

---

## Troubleshooting

### Issue: kojid not found after install

**Solution**:
```bash
# Check installation
pip show koji-adjutant

# Reinstall
pip uninstall koji-adjutant
pip install -e .

# Check PATH
echo $PATH
which kojid
```

### Issue: Import errors when running kojid

**Solution**:
```bash
# Check dependencies installed
pip install podman

# Check koji is available
python3 -c "import koji; print(koji.__version__)"

# Reinstall with dependencies
pip install -e .[dev]
```

### Issue: Entry point not working

**Solution**:
```bash
# Check entry_points.txt
python3 -m zipfile -e dist/*.whl /tmp/check
cat /tmp/check/koji_adjutant-*.dist-info/entry_points.txt

# Should show:
# [console_scripts]
# kojid = koji_adjutant.kojid:main_entrypoint

# Reinstall
pip uninstall koji-adjutant
pip install dist/*.whl
```

---

## Integration with Koji-Boxed

### Updated Pattern

**Old** (direct file copy):
```dockerfile
RUN cp /mnt/koji-adjutant/koji_adjutant/kojid.py /app/kojid
CMD python3 /app/kojid --fg
```

**New** (entry point):
```dockerfile
RUN pip install -e /mnt/koji-adjutant/
CMD kojid --fg
```

**Benefits**:
- ✅ Cleaner and more maintainable
- ✅ Standard Python packaging
- ✅ Easier to update/upgrade
- ✅ No manual file copying
- ✅ Entry point in PATH

---

## Summary

### What Changed

✅ **Makefile added** - `make build` builds wheel
✅ **Entry point added** - `kojid` console script
✅ **Tox build env added** - Automated wheel building
✅ **Koji-boxed updated** - Uses entry point instead of file copy

### How to Use

```bash
# Development
cd koji-adjutant
make dev          # Install editable
make test         # Run tests
make lint         # Check code quality

# Production build
make build        # Create wheel
pip install dist/*.whl  # Install wheel
kojid --fg        # Run daemon
```

### In Koji-Boxed

```bash
# Worker Dockerfile now just needs:
COPY adjutant/ /mnt/koji-adjutant/
RUN pip install -e /mnt/koji-adjutant/

# Entrypoint just calls:
exec kojid --fg ${BUILDER_ARGS}
```

---

**Packaging Status**: ✅ COMPLETE

**Wheel Build**: ✅ Working (`make build`)
**Entry Point**: ✅ Configured (`kojid` command)
**Integration**: ✅ Ready for koji-boxed

---
