---
title: "ADR 0004: Production Buildroot Container Images and Initialization"
status: Proposed
date: 2025-01-27
deciders: Container Engineer, Systems Architect, Implementation Lead
---

## Context

Phase 2.1 is complete (config parsing, hub policy). Phase 2.2 focuses on full buildroot implementation to enable production RPM builds. Currently, Phase 1 uses a simplified `rpmbuild` command that lacks dependency resolution, repository configuration, and proper buildroot environment setup. This limits builds to packages with no dependencies.

**Problem Statement**: To build real RPM packages, containers must replicate mock's buildroot capabilities:
- Dependency resolution and installation
- Repository configuration (koji repos, external repos)
- Build environment setup (RPM macros, environment variables, directory structure)
- Proper isolation while maintaining build compatibility

**Constraints**:
- Must work with PolicyResolver (dynamic image selection per tag/arch)
- Compatible with existing ContainerManager interface (ADR 0001)
- Support AlmaLinux 8/9/10 initially (expandable to Fedora)
- Performance: minimize build time overhead
- Security: maintain rootless/isolation from Phase 1 (ADR 0002)

## Decision

We adopt a **Hybrid Image Strategy** with **Runtime Buildroot Initialization**:

1. **Image Strategy**: Base images with essential build tools pre-installed; project-specific dependencies installed at runtime
2. **Per-Distribution Images**: Separate images per distribution (AlmaLinux 8/9/10) and architecture (x86_64, aarch64)
3. **Buildroot Initialization**: Runtime script that configures repos, installs dependencies, and sets up build environment
4. **Repository Integration**: Dynamic repo configuration from koji hub API
5. **Dependency Resolution**: Via koji buildroot API and SRPM spec parsing

This approach balances image size, build startup time, and flexibility while ensuring compatibility with mock-based builds.

## Gap Analysis: Phase 1 vs Mock

### What Mock Provides

**Dependency Resolution**:
- `mock --install <packages>` installs build dependencies from configured repos
- Resolves BuildRequires from SRPM spec automatically
- Handles circular dependencies and conflicts
- Installs packages into isolated chroot

**Repository Configuration**:
- Reads koji build tag repo configuration
- Configures `/etc/yum.repos.d/koji.repo` with tag-specific repos
- Handles repo priorities and GPG keys
- Supports external repos from hub config

**Build Environment**:
- Sets RPM macros (`%dist`, `%_topdir`, `%_builddir`, etc.)
- Configures environment variables (`BUILDROOT`, `RPM_BUILD_DIR`, etc.)
- Creates standard directory structure (`/builddir`, `/result`, etc.)
- Sets locale and timezone

**Buildroot Configuration**:
- Uses koji buildroot config format
- Configures package groups and install options
- Handles multilib and arch-specific settings

### What Phase 1 Lacks

| Capability | Phase 1 State | Critical Gap |
|------------|---------------|--------------|
| Dependency resolution | ❌ None | **Critical**: Cannot build packages requiring deps |
| Repository setup | ❌ None | **Critical**: No access to koji repos for deps/sources |
| Buildroot config | ❌ None | **Critical**: Missing koji buildroot format support |
| Environment vars | ⚠️ Minimal (`KOJI_*` only) | **High**: Missing RPM build environment |
| Build macros | ⚠️ Basic (`%dist` only) | **High**: Incomplete RPM macro setup |
| Buildroot initialization | ❌ None | **Critical**: No pre-build setup sequence |

**Critical Gaps to Address**:
1. **Dependency Installation**: Without this, builds fail for any package with BuildRequires
2. **Repository Access**: Without koji repos, cannot fetch dependencies or sources
3. **Build Environment**: Missing RPM macros and environment variables cause build failures
4. **Buildroot Format**: Must support koji buildroot configuration for compatibility

## Image Strategy

### Base Image Options Analysis

**Option A: Fat Image (Pre-install Everything)**
- **Approach**: Pre-install all common build tools and dependencies
- **Pros**: Fast startup, predictable, minimal runtime deps
- **Cons**: Large images (500MB+), less flexible, hard to maintain
- **Use Case**: Suitable for single-distro deployments with fixed toolchains

**Option B: Thin Image (Minimal Base)**
- **Approach**: Minimal base image, install all deps at runtime
- **Pros**: Small images (100MB), highly flexible, easy to maintain
- **Cons**: Slower builds (dnf install overhead), network dependent
- **Use Case**: Suitable for experimental builds, multiple distros

**Option C: Hybrid (Recommended)**
- **Approach**: Base tools pre-installed, project deps at runtime
- **Pros**: Balance of speed (30-60s startup) and size (200-300MB), flexible
- **Cons**: More complexity in image management
- **Use Case**: **Production deployments** (recommended)

### Recommended Architecture: Hybrid Approach

**Layer 1: Base Distribution Image**
- **Source**: Official AlmaLinux minimal image (`almalinux:9-minimal`, `almalinux:10-minimal`)
- **Contents**: Base OS, package manager (dnf), basic utilities
- **Size**: ~100-150MB
- **Tagging**: `almalinux:9-minimal`, `almalinux:10-minimal`

**Layer 2: Build Tools Layer**
- **Source**: Derived from base, adds build essentials
- **Contents**: 
  - Build toolchain: `rpm-build`, `gcc`, `gcc-c++`, `make`, `binutils`, `patch`
  - Development tools: `git`, `python3`, `python3-devel`
  - Package management: `yum-utils`, `dnf-plugins-core`
  - Koji integration: `koji` client (if available)
- **Size**: ~200-300MB total
- **Tagging**: `koji-adjutant-buildroot:el9`, `koji-adjutant-buildroot:el10`

**Layer 3: Per-Distribution/Arch Variants**
- **Source**: Derived from build tools layer
- **Architecture-specific**: Separate images per arch (x86_64, aarch64)
- **Contents**: Architecture-specific toolchain packages if needed
- **Tagging**: `koji-adjutant-buildroot:el9-x86_64`, `koji-adjutant-buildroot:el10-aarch64`

**Image Recipe Example** (AlmaLinux 10, x86_64):
```dockerfile
FROM almalinux:10-minimal

# Install build essentials (Layer 2)
RUN dnf install -qy --setopt=install_weak_deps=False \
    rpm-build \
    gcc \
    gcc-c++ \
    make \
    binutils \
    patch \
    git \
    python3 \
    python3-devel \
    yum-utils \
    dnf-plugins-core \
    bash \
    coreutils \
    findutils \
    tar \
    gzip \
    && dnf clean all

# Create koji user (rootless execution)
RUN useradd -u 1000 -g 1000 -m -s /bin/bash koji || true

# Set up buildroot directories structure
RUN mkdir -p /builddir /result && \
    chown -R koji:koji /builddir /result

# Default workdir
WORKDIR /builddir

# Default user
USER koji
```

### Tagging Convention

**Format**: `registry/koji-adjutant-buildroot:<distro>-<arch>[-variant]`

**Examples**:
- `registry/koji-adjutant-buildroot:el9-x86_64` - AlmaLinux 9, x86_64
- `registry/koji-adjutant-buildroot:el10-aarch64` - AlmaLinux 10, aarch64
- `registry/koji-adjutant-buildroot:f39-x86_64` - Fedora 39, x86_64 (future)

**Policy Mapping** (via ADR 0003):
- Tag `el10-build` + arch `x86_64` → `koji-adjutant-buildroot:el10-x86_64`
- Tag `el9-build` + arch `aarch64` → `koji-adjutant-buildroot:el9-aarch64`

**Registry Location**: Configurable via `adjutant_task_image_default` (fallback) or hub policy

### Image Build Strategy

**Pre-built Images** (Recommended for Production):
- Build images via CI/CD pipeline
- Push to registry configured in worker
- Tag with distribution/arch combination
- Version pinning: Use digests for reproducibility (future enhancement)

**Build Script Location**: `scripts/build-images/` (to be created)
- `build-images.sh`: Builds all distribution/arch combinations
- Per-distro Dockerfiles: `Dockerfile.el9`, `Dockerfile.el10`

**Image Updates**:
- Rebuild images when base distro updates
- Update build tools layer independently
- Workers pull updates based on pull policy (ADR 0002)

## Buildroot Initialization Sequence

### Initialization Flow

```
┌─────────────────────────────────────────────────────────┐
│ 1. Container Start (PodmanManager)                      │
│    - Image selected via PolicyResolver                  │
│    - Container created with mounts                       │
│    - Container started                                   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Buildroot Setup Script Execution                     │
│    - Script injected via mount or command                │
│    - Runs as container entrypoint or first command       │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Repository Configuration                             │
│    - Query koji hub for repo URLs (tag + repo_id)      │
│    - Generate /etc/yum.repos.d/koji.repo               │
│    - Configure GPG keys if needed                       │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Dependency Resolution                                │
│    - Extract BuildRequires from SRPM spec               │
│    - Query koji buildroot API for dependency list       │
│    - Resolve package names for dnf                      │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 5. Dependency Installation                              │
│    - Run: dnf install -y <build-deps>                   │
│    - Handle circular deps and conflicts                 │
│    - Cache packages if beneficial                       │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 6. Environment Setup                                    │
│    - Set RPM macros (%dist, %_topdir, etc.)             │
│    - Set environment variables (BUILDROOT, etc.)        │
│    - Create directory structure                         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 7. Build Execution                                      │
│    - Execute rpmbuild or koji build helper              │
│    - Stream logs to koji logging system                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 8. Artifact Collection                                  │
│    - Collect RPMs from result directory                │
│    - Collect logs                                       │
│    - Upload to koji hub                                 │
└─────────────────────────────────────────────────────────┘
```

### Buildroot Setup Script

**Location**: Generated by BuildArchAdapter or mounted as file

**Script Structure** (`/buildroot-init.sh`):
```bash
#!/bin/bash
set -euo pipefail

# Parameters (from environment or command line)
TAG_NAME="${KOJI_BUILD_TAG}"
ARCH="${KOJI_ARCH}"
REPO_ID="${KOJI_REPO_ID}"
SRPM_PATH="${KOJI_SRPM_PATH}"
WORK_DIR="${KOJI_WORK_DIR:-/builddir}"

# Step 1: Repository Configuration
echo "Configuring koji repositories..."
# Query hub for repo URLs (via koji CLI or API)
# Generate /etc/yum.repos.d/koji.repo
koji download-repo --tag="${TAG_NAME}" --arch="${ARCH}" --repo-id="${REPO_ID}" /tmp/koji-repo.conf
# Or use koji API directly to get repo URLs
# Place repo config in /etc/yum.repos.d/koji.repo

# Step 2: Dependency Resolution
echo "Resolving build dependencies..."
# Extract BuildRequires from SRPM
BUILD_DEPS=$(rpm -qp --requires "${SRPM_PATH}" | grep -E "^BuildRequires" || true)
# Query koji buildroot API for complete dependency list
# Format: package1 package2 package3

# Step 3: Install Dependencies
echo "Installing build dependencies..."
dnf install -y --setopt=install_weak_deps=False \
    --setopt=skip_missing_names_on_install=False \
    ${BUILD_DEPS} || {
    echo "ERROR: Failed to install dependencies" >&2
    exit 1
}

# Step 4: Environment Setup
echo "Setting up build environment..."

# RPM Macros
export DIST=".almalinux10"  # Derived from image/distro
export _topdir="${WORK_DIR}"
export _builddir="${WORK_DIR}/build"
export _rpmdir="${WORK_DIR}/result"
export _srcrpmdir="${WORK_DIR}/result"
export _sourcedir="${WORK_DIR}/work"
export _specdir="${WORK_DIR}/work"

# Environment Variables
export BUILDROOT="${WORK_DIR}/BUILDROOT"
export RPM_BUILD_DIR="${WORK_DIR}/build"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

# Create directory structure
mkdir -p "${WORK_DIR}"/{build,BUILDROOT,result,work}

# Step 5: Ready for build
echo "Buildroot initialization complete"
```

**Execution**: Script runs as first command in container, before actual build

### Integration with BuildArchAdapter

**Current Phase 1 Command** (simplified):
```python
command = ["/bin/bash", "-c", "rpmbuild --rebuild <srpm>"]
```

**Phase 2.2 Command** (with buildroot init):
```python
command = [
    "/bin/bash", "-c",
    """
    /buildroot-init.sh && \
    rpmbuild --define "_topdir /builddir" \
             --define "dist .almalinux10" \
             --rebuild "${KOJI_SRPM_PATH}"
    """
]
```

**Script Injection Options**:

**Option 1: Mount Script File** (Recommended)
- Generate script in BuildArchAdapter
- Write to `ctx.work_dir / "buildroot-init.sh"`
- Mount work_dir to container
- Execute script from mount

**Option 2: Inline Script**
- Embed script in command string
- Pros: No file I/O, simpler
- Cons: Harder to debug, command length limits

**Option 3: Image-Baked Script**
- Include script in image (`/usr/bin/koji-buildroot-init`)
- Pros: Reusable, versioned with image
- Cons: Less flexible, requires image rebuilds

**Recommendation**: Option 1 (mount script) for flexibility and debuggability

## Dependency Resolution

### Dependency Sources

**Source 1: SRPM Spec File**
- Extract `BuildRequires:` lines from SRPM spec
- Parse package names (may include version constraints)
- Format: `rpm -qp --requires <srpm> | grep BuildRequires`

**Source 2: Koji Buildroot API**
- Query hub for complete dependency list for tag/arch
- API: `session.getBuildConfig(tag, arch)` → dependency list
- Includes transitive dependencies and package groups

**Source 3: Koji Tag Configuration**
- Read tag extra data for buildroot config
- May specify package groups or extra dependencies
- Format: Tag extra `buildroot_packages` or `install_groups`

### Dependency Resolution Algorithm

```python
def resolve_build_dependencies(session, tag_name, arch, srpm_path):
    """Resolve complete build dependency list.
    
    Returns: List of package names for dnf install
    """
    deps = set()
    
    # 1. Extract BuildRequires from SRPM spec
    srpm_deps = extract_buildrequires_from_srpm(srpm_path)
    deps.update(srpm_deps)
    
    # 2. Query koji buildroot API
    build_config = session.getBuildConfig(tag_name, arch=arch)
    if build_config:
        # Get install groups or packages
        install_groups = build_config.get('install_groups', [])
        extra_packages = build_config.get('extra_packages', [])
        deps.update(extra_packages)
        # Resolve package groups to individual packages
        for group in install_groups:
            group_packages = resolve_package_group(group, arch)
            deps.update(group_packages)
    
    # 3. Query tag extra data
    tag_info = session.getTag(tag_name)
    extra = tag_info.get('extra', {})
    if 'buildroot_packages' in extra:
        deps.update(extra['buildroot_packages'])
    
    # 4. Resolve package names (handle provides/requires)
    # Query dnf/yum to resolve package names
    resolved_deps = resolve_package_names(list(deps), arch)
    
    return resolved_deps
```

### Dependency Installation

**dnf Command**:
```bash
dnf install -y \
    --setopt=install_weak_deps=False \
    --setopt=skip_missing_names_on_install=False \
    --setopt=keepcache=True \
    <package1> <package2> ...
```

**Error Handling**:
- Missing packages: Log warning, fail build (or allow skip based on config)
- Circular dependencies: dnf handles automatically
- Conflicts: Fail build with clear error message

**Caching Strategy**:
- `keepcache=True`: Preserve downloaded packages in container
- Benefit: Faster subsequent installs within same container
- Trade-off: Increased container size

## Repository Configuration

### Repository Sources

**Source 1: Koji Tag Repositories**
- Query hub: `session.getRepo(tag_name, repo_id, arch)`
- Returns: Repo URLs, GPG keys, priorities
- Format: Multiple repos per tag (base, updates, extras, etc.)

**Source 2: External Repositories**
- From tag extra data: `external_repos` list
- Format: List of repo URLs or repo IDs
- May require authentication (handled separately)

**Source 3: Koji-Boxed Repository Layout**
- Standard layout: `/mnt/koji/repos/<tag>/<arch>/`
- May be mounted read-only into container
- Use `file://` URLs for local repos

### Repository Configuration Generation

**Script**: Generate `/etc/yum.repos.d/koji.repo` inside container

**Format**:
```ini
[koji-base]
name=Koji Base Repository
baseurl=http://koji-hub.example.com/repos/el10-build/latest/x86_64/
enabled=1
gpgcheck=0
priority=10

[koji-updates]
name=Koji Updates Repository
baseurl=http://koji-hub.example.com/repos/el10-build/latest/x86_64/updates/
enabled=1
gpgcheck=0
priority=20
```

**Generation** (in buildroot-init.sh):
```bash
# Query hub for repo URLs
REPO_INFO=$(koji get-repo --tag="${TAG_NAME}" --repo-id="${REPO_ID}" --arch="${ARCH}")

# Generate repo config
cat > /etc/yum.repos.d/koji.repo <<EOF
[koji-base]
name=Koji Base Repository
baseurl=${REPO_INFO['baseurl']}
enabled=1
gpgcheck=0
priority=10
EOF
```

**Alternative**: Use koji CLI `koji download-repo` if available in image

### Repository Authentication

**Current**: Most koji repos are public (no auth required)

**Future**: If authentication needed:
- Mount keytabs or credentials into container (read-only)
- Configure dnf to use credentials
- Scope credentials to specific repos

## Build Environment Specification

### RPM Macros

**Required Macros** (matching mock):
```bash
%dist .almalinux10          # Distribution tag (from image/distro)
%_topdir /builddir          # Base build directory
%_builddir /builddir/build  # Build directory
%_rpmdir /builddir/result   # RPM output directory
%_srcrpmdir /builddir/result # SRPM output directory
%_sourcedir /builddir/work  # Source directory
%_specdir /builddir/work    # Spec directory
%_buildrootdir /builddir/BUILDROOT # Buildroot directory
```

**Configuration**: Set via `rpmbuild --define` or `/etc/rpm/macros.d/` file

### Environment Variables

**Required Variables**:
```bash
BUILDROOT=/builddir/BUILDROOT
RPM_BUILD_DIR=/builddir/build
KOJI_TASK_ID=<task_id>
KOJI_BUILD_TAG=<tag_name>
KOJI_ARCH=<arch>
KOJI_REPO_ID=<repo_id>
LANG=en_US.UTF-8
LC_ALL=en_US.UTF-8
TZ=UTC
```

**Source**: Set in ContainerSpec.environment or buildroot-init.sh

### Directory Structure

**Standard Layout** (matching mock):
```
/builddir/              # Work directory (mounted from /mnt/koji/work/<task_id>)
├── work/               # Source files, SRPM
├── build/              # Build output (compiled sources)
├── BUILDROOT/          # Install root (packages installed here)
└── result/             # Final RPMs and logs
    ├── *.rpm
    ├── *.src.rpm
    └── *.log
```

**Creation**: buildroot-init.sh creates directories with proper permissions

### User Context

**User**: `koji` (UID 1000, GID 1000) - matches koji-boxed worker user

**Permissions**: Ensure work_dir and result_dir are writable by koji user

**Security**: Rootless execution per ADR 0002

## Implementation Recommendations

### Component Design

**New Module**: `koji_adjutant/buildroot/` (to be created)
- `resolver.py`: Dependency resolution logic
- `repo_config.py`: Repository configuration generation
- `init_script.py`: Buildroot initialization script generator
- `environment.py`: Environment variable and macro configuration

**Integration Points**:
- `BuildArchAdapter.build_spec()`: Calls buildroot components
- `PolicyResolver`: Provides image selection (already implemented)
- `ContainerManager`: Executes initialization + build sequence

### Buildroot Initialization Script Generator

**Function**: `generate_buildroot_init_script()`
- Input: Task context (tag, arch, repo_id, srpm_path)
- Output: Shell script content (string)
- Location: `koji_adjutant/buildroot/init_script.py`

**Usage**:
```python
from ..buildroot import generate_buildroot_init_script

script_content = generate_buildroot_init_script(
    tag_name=tag_name,
    arch=arch,
    repo_id=repo_id,
    srpm_path=srpm_path,
    work_dir=work_dir,
    session=session,
)

# Write script to work_dir
script_path = ctx.work_dir / "buildroot-init.sh"
script_path.write_text(script_content)
script_path.chmod(0o755)
```

### Dependency Resolver Integration

**Function**: `resolve_build_dependencies()`
- Input: Session, tag_name, arch, srpm_path
- Output: List of package names
- Location: `koji_adjutant/buildroot/resolver.py`

**Implementation**:
- Query koji API for buildroot config
- Extract BuildRequires from SRPM
- Resolve package names via dnf/yum (or koji API)
- Return formatted list for dnf install

### Repository Config Generator

**Function**: `generate_repo_config()`
- Input: Session, tag_name, repo_id, arch
- Output: Repo config file content (string)
- Location: `koji_adjutant/buildroot/repo_config.py`

**Implementation**:
- Query `session.getRepo(tag_name, repo_id, arch)`
- Format as `/etc/yum.repos.d/koji.repo` content
- Handle multiple repos, priorities, GPG keys

### BuildArchAdapter Updates

**Changes Required**:
1. Generate buildroot-init.sh script
2. Mount script into container
3. Update command to execute script before build
4. Pass buildroot dependencies to script via environment

**Example**:
```python
# Generate buildroot init script
init_script = generate_buildroot_init_script(...)
script_path = ctx.work_dir / "buildroot-init.sh"
script_path.write_text(init_script)

# Update command
command = [
    "/bin/bash", "-c",
    f"{script_path} && rpmbuild --rebuild {srpm_path}"
]

# Mount script
mounts.append(VolumeMount(
    source=script_path,
    target=Path("/buildroot-init.sh"),
    read_only=True,
))
```

## Work Items for Implementation Lead

### Phase 2.2: Buildroot Implementation

**1. Create Buildroot Module** (`koji_adjutant/buildroot/`)
- [ ] `__init__.py`: Module exports
- [ ] `resolver.py`: Dependency resolution (`resolve_build_dependencies()`)
- [ ] `repo_config.py`: Repo config generation (`generate_repo_config()`)
- [ ] `init_script.py`: Init script generation (`generate_buildroot_init_script()`)
- [ ] `environment.py`: Environment/macro configuration helpers

**2. Dependency Resolution Implementation**
- [ ] SRPM spec parsing (extract BuildRequires)
- [ ] Koji buildroot API integration (`session.getBuildConfig()`)
- [ ] Tag extra data parsing (`buildroot_packages`, `install_groups`)
- [ ] Package name resolution (handles provides/requires)
- [ ] Error handling (missing packages, conflicts)

**3. Repository Configuration Implementation**
- [ ] Koji repo API integration (`session.getRepo()`)
- [ ] Repo config file generation (`/etc/yum.repos.d/koji.repo`)
- [ ] Support for multiple repos per tag
- [ ] GPG key handling (if needed)
- [ ] Local repo support (`file://` URLs)

**4. Buildroot Initialization Script**
- [ ] Script template with all steps
- [ ] Parameter injection (tag, arch, repo_id, srpm_path)
- [ ] Repository configuration step
- [ ] Dependency installation step
- [ ] Environment setup step (macros, vars, directories)
- [ ] Error handling and logging

**5. BuildArchAdapter Integration**
- [ ] Generate buildroot-init.sh in `build_spec()`
- [ ] Mount script into container
- [ ] Update command to execute script before build
- [ ] Pass required parameters via environment
- [ ] Handle script execution failures

**6. Unit Tests**
- [ ] Test dependency resolution (SRPM parsing, API queries)
- [ ] Test repo config generation (multiple repos, priorities)
- [ ] Test init script generation (all steps, error cases)
- [ ] Test BuildArchAdapter integration (script generation, mounting)

**7. Integration Tests**
- [ ] Test with real SRPM (simple package, no deps)
- [ ] Test with SRPM requiring dependencies
- [ ] Test with multiple repos
- [ ] Test buildroot initialization end-to-end
- [ ] Test build execution with complete buildroot

**8. Documentation**
- [ ] Buildroot initialization sequence diagram
- [ ] Image build instructions (`scripts/build-images/`)
- [ ] Troubleshooting guide (common issues, debugging)
- [ ] Operator guide (image management, repo configuration)

## Alternatives Considered

### Alternative 1: Fat Images (Pre-install All Dependencies)
**Approach**: Build images with all common build dependencies pre-installed
**Rejected Because**:
- Images become very large (500MB+)
- Cannot support all possible package combinations
- Less flexible for different build tags
- Harder to maintain and update

### Alternative 2: Thin Images (Install Everything at Runtime)
**Approach**: Minimal base image, install all deps via dnf at container start
**Rejected Because**:
- Slower startup (2-5 minutes for complex builds)
- Network dependency for every build
- Less predictable (network failures affect builds)
- Higher resource usage (every build downloads packages)

### Alternative 3: Buildroot Caching (Reuse Containers)
**Approach**: Cache buildroot state, reuse containers for same tag/arch
**Deferred Because**:
- Adds significant complexity (container state management)
- May not provide sufficient benefit (containers are fast to create)
- Can be added later if benchmarks show benefit
- Current focus: Correctness over optimization

### Alternative 4: Mock-Inside-Container
**Approach**: Run mock inside container to handle buildroot setup
**Rejected Because**:
- Defeats purpose of replacing mock with containers
- Adds unnecessary complexity (chroot inside container)
- Mock requires root privileges (conflicts with rootless goal)
- Does not leverage container benefits

## Consequences

### Positive Consequences

1. **Production Readiness**: Enables real RPM builds with dependencies
2. **Flexibility**: Runtime dependency installation supports diverse packages
3. **Compatibility**: Matches mock behavior for hub compatibility
4. **Maintainability**: Hybrid approach balances size and flexibility
5. **Performance**: Pre-installed tools reduce startup time vs thin images

### Negative Consequences

1. **Complexity**: Adds buildroot initialization layer (script generation, execution)
2. **Startup Overhead**: Runtime dependency installation adds 30-120s per build
3. **Network Dependency**: Requires network access for dependency installation
4. **Image Management**: Multiple images per distro/arch increase operational burden
5. **Testing Overhead**: More components to test (dependency resolution, repo config, init script)

### Performance Impact

**Expected Overhead**:
- Buildroot initialization: 30-120 seconds (depends on dependency count)
- Dependency installation: 20-90 seconds (dnf install time)
- Total overhead: 50-210 seconds per build

**Mitigation**:
- Pre-installed build tools reduce some overhead
- dnf caching within container speeds up subsequent installs
- Future: Buildroot caching (container reuse) can reduce overhead further

### Security Considerations

1. **Network Access**: Required for dependency installation (acceptable per ADR 0002)
2. **Repository Trust**: Repos come from koji hub (trusted source)
3. **Script Execution**: Init script runs with container user privileges (koji, UID 1000)
4. **Package Installation**: dnf installs packages as root (or via sudo) - acceptable in container isolation

### Operational Considerations

1. **Image Building**: Requires CI/CD pipeline to build and push images
2. **Image Updates**: Workers pull updates based on pull policy
3. **Registry Management**: Multiple images increase registry storage needs
4. **Monitoring**: Track buildroot initialization time, dependency install failures
5. **Troubleshooting**: Init script logs help debug buildroot setup issues

## Migration Path

### Phase 2.1 → Phase 2.2

1. **Image Preparation**: Build and push buildroot images to registry
2. **Code Implementation**: Implement buildroot module and BuildArchAdapter updates
3. **Testing**: Test with simple and complex packages
4. **Rollout**: Enable buildroot initialization via config flag
5. **Validation**: Compare builds with mock-based kojid

### Backward Compatibility

- **Phase 1 Fallback**: If buildroot initialization fails, fall back to Phase 1 simple build
- **Config Control**: `adjutant_buildroot_enabled = true/false` flag
- **Gradual Migration**: Test with simple packages first, then complex

## References

- ADR 0001: Container Lifecycle and Interface Boundaries
- ADR 0002: Container Image Bootstrap and Security
- ADR 0003: Hub Policy-Driven Container Image Selection
- Phase 2 Roadmap: `docs/planning/phase2-roadmap.md`
- Mock Documentation: Mock chroot behavior reference
- Koji Buildroot API: `session.getBuildConfig()`, `session.getRepo()`

---

**Decision Status**: Proposed for Phase 2.2 implementation.

**Next Steps**:
1. Review and approve ADR
2. Implementation Lead creates buildroot module structure
3. Container Engineer designs image build pipeline
4. Build and test initial buildroot images
5. Implement dependency resolution and repo config
6. Integrate with BuildArchAdapter
7. Test with real packages
