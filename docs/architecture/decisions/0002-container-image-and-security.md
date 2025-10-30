---
title: "ADR 0002: Container Image Bootstrap, Security, and Operational Details"
status: Accepted
date: 2025-01-27
deciders: Container Engineer, Systems Architect, Implementation Lead
---

## Context

ADR 0001 established the container lifecycle and `ContainerManager` interface. We now need to specify the concrete container image contents, security boundaries, and operational details for Phase 1 implementation. Task containers must support both `buildArch` and `createrepo` tasks while maintaining security isolation and compatibility with koji-boxed infrastructure.

## Decision

We define a Phase 1 AlmaLinux 10-based task container image with specific package requirements, rootless-first execution strategy, SELinux labeling guidance, network policy defaults, and container image lifecycle management. Security boundaries enforce minimal capabilities, filesystem isolation, and controlled secrets/keytab handling.

### Phase 1 Task Container Image

**Base Image**: AlmaLinux 10 (official `almalinux:10` or equivalent from configured registry)

**Required Packages** (installed via derived image or runtime):

1. **Build Toolchain**:
   - `rpm-build` - Core RPM build tools
   - `gcc`, `gcc-c++` - Compiler toolchain
   - `make` - Build automation
   - `binutils` - Binary utilities
   - `patch` - Source patching

2. **Package Management**:
   - `dnf` - Package manager (included in base image)
   - `yum-utils` - DNF/yum utilities for repo management

3. **Repository Management**:
   - `createrepo_c` - Modern createrepo tool for repository generation

4. **Build Essentials**:
   - `bash` - Shell environment (included in base)
   - `git` - Source control (for SCM-based builds)
   - `python3`, `python3-devel` - Python runtime (required by many build scripts)

5. **Mock Compatibility** (Phase 1 transition):
   - `mock-core-configs` - Mock configuration files (needed for some koji task expectations, but containers replace mock chroots)
   - Note: `mock` binary itself is optional; we use podman instead

**Image Build Strategy**:

Option A (Recommended for Phase 1): Pre-built derived image
- Create a derived image `koji-adjutant-task:almalinux10` that installs all required packages
- Store in registry configured via `adjutant_task_image_default`
- Worker pulls and caches this image

Option B (Alternative): Runtime package installation
- Start from minimal `almalinux:10` base
- Install packages via `dnf install` in container entrypoint
- Slower startup but more flexible for experimentation

**Phase 1 Default**: Option A with pre-built image. Package list above defines the contents.

**Image Recipe Example**:
```dockerfile
FROM almalinux:10

RUN dnf install -qy \
    rpm-build \
    gcc \
    gcc-c++ \
    make \
    binutils \
    patch \
    yum-utils \
    createrepo_c \
    git \
    python3 \
    python3-devel \
    mock-core-configs && \
    dnf clean all

# Optional: create unprivileged user for rootless execution
RUN useradd -u 1000 -g 1000 -m -s /bin/bash koji || true
```

**Tagging Strategy**:
- Phase 1: Single image tag (e.g., `koji-adjutant-task:almalinux10` or `registry/koji-adjutant-task:almalinux10`)
- Future: Tag per koji tag/arch combination when hub policy-driven selection is implemented
- Registry location: Configurable via `adjutant_task_image_default` (default: `registry/almalinux:10` for Phase 1 backward compatibility, should be updated to point to task image)

### UID/GID Strategy

**Preference**: Rootless execution (non-root user)

**Phase 1 Default**:
- Container user: `koji` (UID 1000, GID 1000) when rootless mode is enabled
- Alignment: Matches koji-boxed worker user (`koji:koji` with UID/GID 1000)

**Implementation**:
- `ContainerSpec.user_id` and `ContainerSpec.group_id` are set by task adapters
- Default: `user_id=1000, group_id=1000` when rootless is feasible
- Root execution (`user_id=None`) is a fallback when:
  - Tooling requires root (rare, but some legacy build scripts may expect it)
  - Mount permissions are incompatible with non-root user

**Mount Ownership**:
- Host `/mnt/koji` must be accessible by UID 1000 or container root
- Task workspace `/mnt/koji/work/<task_id>` is created by worker (running as koji user) and mounted read-write
- SELinux labels (`:Z` or `:z`) handle access control beyond traditional Unix permissions

**Fallback to Root**:
- When `user_id` is not specified or tooling fails as non-root, run as root
- Root containers are acceptable for Phase 1 when necessary; security comes from container isolation, SELinux, and minimal capabilities

**Future Enhancement**:
- Investigate user namespace mapping for better rootless support
- Consider per-task dynamic UID allocation if security policy requires it

### SELinux Labeling Guidance

**Context**: RHEL/AlmaLinux systems enforce SELinux by default. Podman must apply correct labels to bind mounts.

**Default Policy**:
- `/mnt/koji` mount: Apply `:Z` label (private unshared label) by default
  - Rationale: Each container gets its own SELinux context, preventing cross-container access
  - Implementation: `PodmanManager._mount_options()` defaults to `:Z` for `/mnt/koji` targets
- Task workspace `/work/<task_id>`: Inherit from parent mount or apply `:Z`

**Shared vs. Private Labels**:
- `:Z` (private): Recommended default; each container gets isolated context
- `:z` (shared): Use only when multiple containers must concurrently access the same volume with different labels (not typical for Phase 1)
- No label suffix: Relies on host SELinux policy defaults (may fail if SELinux is enforcing)

**Configuration**:
- Default behavior via `adjutant_container_mounts` config (see ADR 0001)
- Task adapters may override `selinux_label` in `VolumeMount` for specialized needs
- Worker logs SELinux denials if they occur; operations team must address host policy conflicts

**Host Preparation**:
- Host must have SELinux in enforcing or permissive mode (not disabled)
- Ensure `/mnt/koji` host path has appropriate SELinux context type (e.g., `container_file_t` or custom type)

### Network Policy

**Phase 1 Default**: Network enabled (`adjutant_network_enabled = true`)

**Rationale**:
- Build tasks need network access for:
  - Downloading source packages from koji hub
  - Fetching dependencies via dnf/yum
  - Uploading build artifacts to hub
- Repository metadata retrieval requires network
- SCM operations (git, svn, etc.) need network

**Network Namespace**:
- Each container gets its own network namespace (isolated by default)
- Default podman bridge networking provides host connectivity
- Containers can resolve host DNS and access external networks

**Future Constraints** (post-Phase 1):
- Policy-driven network disable: When `adjutant_network_enabled = false`, containers run with `network_disabled = true`
- Restricted networks: Use podman network policies or CNI plugins for isolated task networks
- Hub-controlled policy: Future enhancement where hub specifies network requirements per task

**Security Considerations**:
- Network access is broad in Phase 1; future enhancements may restrict to specific endpoints
- No network isolation between concurrent tasks (acceptable for Phase 1; each task runs in separate container)
- Firewall rules on host can restrict outbound traffic if needed

### Container Image Lifecycle

**Pull Policy** (from ADR 0001):
- `adjutant_image_pull_policy = if-not-present` (default)
  - Pull image only if not locally cached
  - Reduces network overhead and startup time
- `always`: Always pull (useful for development or when image tags are mutable)
- `never`: Use only local cache (requires pre-populated images)

**Image Caching**:
- Podman caches pulled images in local storage (`~/.local/share/containers/storage` or configured location)
- Worker startup: Optionally pre-pull task image to warm cache (future enhancement)
- Cache invalidation: Manual via `podman rmi` or automatic via Podman's garbage collection

**Image Updates**:
- Phase 1: Immutable image tags (e.g., `koji-adjutant-task:almalinux10`)
- Updates: Build new image, tag appropriately, update worker config to point to new tag
- Rollback: Revert config to previous tag
- Future: Semantic versioning (e.g., `koji-adjutant-task:almalinux10-v1.2.3`) for reproducible builds

**Image Registry**:
- Registry location: Configurable via `adjutant_task_image_default`
- Default Phase 1: `registry/almalinux:10` (backward compatibility placeholder)
- Production: Should point to dedicated registry hosting `koji-adjutant-task:almalinux10`
- Authentication: Registry credentials via Podman's credential helpers or `~/.config/containers/auth.json`

**Image Validation**:
- Worker validates image availability on startup (if pull policy allows)
- Pull failures surface as `ContainerError` during task execution
- Image corruption: Podman detects and re-pulls automatically (or raises `ContainerError`)

### Security Boundaries

**Container Capabilities**:
- Default: Podman drops most capabilities; containers run with minimal privilege
- Explicit capability drops: None required for Phase 1 (Podman default is secure)
- Capability additions: Avoid unless absolutely necessary; document justification if added

**Filesystem Isolation**:
- Containers see only explicitly mounted volumes (no host filesystem access beyond mounts)
- Read-only mounts: Apply to source SRPMs, repo metadata, config files
- Read-write mounts: Limited to `/mnt/koji` (shared) and `/work/<task_id>` (task-specific)
- No bind mount of `/`, `/usr`, `/etc` (except task-specific config files)

**Secrets and Keytabs**:
- **Preference**: Avoid mounting keytabs into containers
- **Phase 1 Approach**: Use environment-based authentication where possible
  - Kerberos credentials via environment variables (if supported by koji libraries)
  - Leverage existing orch service patterns for credential injection
- **Fallback**: Mount keytab read-only with minimal scope
  - Path: `/etc/krb5.keytab` (read-only) or task-specific keytab under `/work/<task_id>/keytab` (read-only)
  - SELinux label: `:Z` to prevent other containers from accessing
  - Cleanup: Keytab removed with container and task workspace
- **Future**: Use Podman secrets management or external credential service

**Process Isolation**:
- Each container runs a single task process (no daemon processes)
- Container PID namespace isolation (containers cannot see host or other container processes)
- Resource limits: Applied via `ResourceLimits` (memory, CPU, PIDs)

**Host Interaction**:
- Containers cannot access host devices (blocked by default)
- No `--privileged` mode: Never enable privileged containers
- Host IPC/UTS namespaces: Not shared (default Podman behavior)

### Worker Shutdown and Container Cleanup

**Shutdown Signal Flow**:
1. Worker receives `SIGTERM` (via signal handler in main loop)
2. Worker sets shutdown flag and stops accepting new tasks
3. Worker waits for in-flight tasks to complete (with timeout)
4. For each running container:
   - Send `SIGTERM` to container (via `podman stop` or container process signal)
   - Wait up to `stop_grace` seconds (default: 20s from `adjutant_container_timeouts`)
   - If container still running after grace period: Force stop (`SIGKILL` equivalent)
   - Remove container (`podman rm -f`)
5. Worker exits after all containers are cleaned up

**Implementation**:
- `PodmanManager.remove(handle, force=True)` already handles graceful stop → force remove pattern
- Task manager maintains registry of running containers via `ContainerHandle` objects
- On shutdown, iterate containers and call `remove(handle, force=True)`
- Container labels (`io.koji.adjutant.worker_id`, `io.koji.adjutant.task_id`) enable enumeration for orphan cleanup

**Timeout Handling**:
- Graceful stop timeout: `adjutant_container_timeouts.stop_grace = 20` (seconds)
- If task is stuck (e.g., build hanging), force removal after timeout
- Log warnings for containers requiring force removal

**Orphan Cleanup** (future enhancement):
- Periodic cleanup job scans for containers with worker labels but no active task
- Useful for recovery after worker crashes

### Bootstrap Implementation Notes

**Task Adapter Integration**:
- `BuildArchTask` adapter: Uses task image, mounts `/mnt/koji` and `/work/<task_id>`, runs build command
- `CreaterepoTask` adapter: Uses same image, mounts repo directory, runs `createrepo_c` command
- Both adapters construct `ContainerSpec` with appropriate image, command, mounts, and user

**Image Selection Logic** (Phase 1):
- Single image for all tasks: `adjutant_task_image_default`
- Future: Hub policy may specify image per task/tag via task options

**Startup Sequence**:
1. Worker initializes `PodmanManager` with config
2. Worker calls `ensure_image_available(image)` for default task image (warms cache)
3. Worker begins task polling and execution

## Alternatives Considered

- **Minimal base image with runtime package installation**: Rejected for Phase 1 due to startup latency; acceptable for future flexibility if needed.
- **Multiple images per task type**: Rejected for Phase 1 complexity; single image with all tools is simpler to maintain.
- **Always run as root**: Rejected; rootless is preferred for security, with root as fallback only when necessary.
- **No SELinux labeling**: Rejected; SELinux is default on RHEL/AlmaLinux and ignoring it causes failures.
- **Network disabled by default**: Rejected; builds require network access, so enabled is the practical default.

## Work Items

- Build and publish Phase 1 task image `koji-adjutant-task:almalinux10` to configured registry with required packages.
- Update `adjutant_task_image_default` config to point to task image (replace placeholder `registry/almalinux:10`).
- Implement graceful shutdown handler in task manager that iterates containers and calls `remove(handle, force=True)`.
- Wire `ContainerSpec.user_id=1000, group_id=1000` in task adapters for rootless execution.
- Verify SELinux labeling (`:Z`) works correctly on target host with enforcing SELinux.
- Document host preparation requirements (SELinux context, mount permissions, registry auth).

## Consequences and Notes

- Phase 1 image is "fat" (includes all tools); future may optimize with task-specific images.
- Rootless execution may require host filesystem permission tuning; operations team must ensure `/mnt/koji` is accessible.
- SELinux policy must allow container file access; if denials occur, adjust host policy or use permissive mode for testing.
- Image registry must be accessible from worker nodes; consider mirroring for air-gapped environments.
- Worker shutdown cleanup is critical; orphaned containers consume resources and may interfere with subsequent tasks.
- Future enhancements (user namespaces, network policies, hub-driven image selection) build on this foundation.
