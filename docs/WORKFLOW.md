# Koji-Adjutant Workflow Guide

**Version**: Phase 2.2 (in progress)
**Date**: 2025-10-30
**Purpose**: Simplified explanation of how koji-adjutant works from startup to task completion

---

## Table of Contents

1. [System Startup](#system-startup)
2. [Task Reception](#task-reception)
3. [Container-Based Execution](#container-based-execution)
4. [Build Process (BuildArch)](#build-process-buildarch)
5. [Repository Generation (Createrepo)](#repository-generation-createrepo)
6. [Result Reporting](#result-reporting)
7. [Cleanup](#cleanup)
8. [Key Components Reference](#key-components-reference)

---

## System Startup

### 1. Kojid Launch

```
User/SystemD starts kojid:
  → /usr/sbin/kojid --config=/etc/kojid/kojid.conf
```

**What happens:**
- `kojid.py` main() function is called
- Configuration loaded from `/etc/kojid/kojid.conf`
- Koji hub connection established (XMLRPC)
- Worker registers with hub
- Task polling loop begins

**Key Configuration** (`[adjutant]` section):
```ini
[adjutant]
task_image_default = docker.io/almalinux/9-minimal:latest
policy_enabled = true
policy_cache_ttl = 300
buildroot_enabled = true
network_enabled = true
```

**Files Involved:**
- `koji_adjutant/kojid.py` (main daemon)
- `koji_adjutant/config.py` (config parsing)

---

## Task Reception

### 2. Hub Assigns Task

```
Hub → Worker: "Here's a buildArch task"
  Task ID: 12345
  SRPM: mypackage-1.0-1.src.rpm
  Build Tag: f39-build
  Architecture: x86_64
```

**What happens:**
- Worker polls hub: `session.getNextTask()`
- Hub assigns task to worker
- Worker creates task handler based on task type
- Task handler initialized with task parameters

**Task Types Supported:**
- `buildArch` → RPM build for specific architecture
- `createrepo` → Generate repository metadata

**Task Parameters (buildArch example):**
```python
{
    'pkg': 'mypackage-1.0-1.src.rpm',
    'root': 'f39-build',           # build tag
    'arch': 'x86_64',
    'keep_srpm': True,
    'opts': {
        'repo_id': 98765
    }
}
```

**Files Involved:**
- `koji_adjutant/kojid.py` (BuildArchTask.handler, CreaterepoTask.handler)

---

## Container-Based Execution

### 3. Task Preparation

```
Task Handler receives parameters
  ↓
Creates TaskContext
  ↓
Selects container image (via PolicyResolver)
  ↓
Initializes buildroot (if enabled)
  ↓
Creates ContainerSpec
  ↓
Executes via PodmanManager
```

### 3.1 TaskContext Creation

**What happens:**
```python
ctx = TaskContext(
    task_id=12345,
    work_dir=Path("/mnt/koji/work/12345"),
    koji_mount_root=Path("/mnt/koji"),
    environment={}
)
```

**Purpose:** Provides task-specific paths and metadata to adapters

**Files Involved:**
- `koji_adjutant/task_adapters/base.py` (TaskContext dataclass)

### 3.2 Image Selection (Phase 2.1+)

```
PolicyResolver.resolve_image()
  ↓
Query Hub for Policy (tag extra data)
  ↓
Check Cache (TTL: 300s)
  ↓
Evaluate Rules:
    - tag_arch match?  (f39-build + x86_64)
    - tag match?       (f39-build)
    - task_type match? (buildArch)
    - default?
  ↓
Fallback to config if no match
  ↓
Return: "registry.io/koji-buildroot:f39-x86_64"
```

**Policy Example (from hub tag extra data):**
```json
{
  "rules": [
    {
      "type": "tag_arch",
      "tag": "f39-build",
      "arch": "x86_64",
      "image": "registry.io/koji-buildroot:f39-x86_64"
    },
    {
      "type": "default",
      "image": "docker.io/almalinux/9-minimal:latest"
    }
  ]
}
```

**Files Involved:**
- `koji_adjutant/policy/resolver.py` (PolicyResolver class)
- `koji_adjutant/config.py` (fallback defaults)

### 3.3 Buildroot Initialization (Phase 2.2)

**For BuildArch tasks, if `buildroot_enabled=true`:**

```
BuildrootInitializer.initialize()
  ↓
1. Parse SRPM → Extract BuildRequires
   rpm -qp --requires mypackage-1.0-1.src.rpm
  ↓
2. Query Hub → Get repo configuration
   session.repoInfo(repo_id)
   session.getBuildConfig(tag, event_id)
  ↓
3. Generate Repo Files → /etc/yum.repos.d/koji.repo
   [koji-f39-build]
   baseurl=http://koji.example.com/repos/f39-build/latest/x86_64
  ↓
4. Create Initialization Script → init-buildroot.sh
   #!/bin/bash
   dnf install -y gcc make python3-devel ...
   mkdir -p /builddir/{BUILD,RPMS,SRPMS,SOURCES,SPECS}
  ↓
5. Return: InitializationResult
   - script_path: /mnt/koji/work/12345/init-buildroot.sh
   - repo_files: [koji.repo]
   - build_requires: [gcc, make, ...]
```

**Files Involved:**
- `koji_adjutant/buildroot/initializer.py` (orchestration)
- `koji_adjutant/buildroot/dependencies.py` (parse SRPM)
- `koji_adjutant/buildroot/repos.py` (generate repo files)
- `koji_adjutant/buildroot/environment.py` (RPM macros, env vars)

### 3.4 ContainerSpec Creation

**What happens:**
```python
spec = ContainerSpec(
    image="registry.io/koji-buildroot:f39-x86_64",
    command=["/bin/bash", "-c", "...build script..."],
    environment={
        "KOJI_TASK_ID": "12345",
        "KOJI_BUILD_TAG": "f39-build",
        "KOJI_ARCH": "x86_64",
        ...
    },
    mounts=[
        VolumeMount(
            source=Path("/mnt/koji"),
            target=Path("/mnt/koji"),
            read_only=False,
            selinux_label="Z"
        ),
        VolumeMount(
            source=Path("/mnt/koji/work/12345"),
            target=Path("/work/12345"),
            read_only=False,
            selinux_label="Z"
        )
    ],
    workdir=Path("/work/12345"),
    user_id=1000,
    group_id=1000,
    network_enabled=True,
    remove_after_exit=True
)
```

**Files Involved:**
- `koji_adjutant/container/interface.py` (ContainerSpec, VolumeMount)
- `koji_adjutant/task_adapters/buildarch.py` (BuildArchAdapter.build_spec)
- `koji_adjutant/task_adapters/createrepo.py` (CreaterepoAdapter.build_spec)

---

## Build Process (BuildArch)

### 4. Container Execution

```
PodmanManager.run(spec, log_sink)
  ↓
1. ensure_image_available()
   podman images | grep registry.io/koji-buildroot:f39-x86_64
   (pull if missing)
  ↓
2. create(spec)
   podman create \
     --label io.koji.adjutant.task_id=12345 \
     --mount type=bind,src=/mnt/koji,dst=/mnt/koji,Z \
     --mount type=bind,src=/mnt/koji/work/12345,dst=/work/12345,Z \
     --workdir /work/12345 \
     --user 1000:1000 \
     registry.io/koji-buildroot:f39-x86_64 \
     /bin/bash -c "..."
  ↓
3. start(container_id)
   podman start abc123def456
  ↓
4. stream_logs(container_id, log_sink)
   - stdout → koji logger + /mnt/koji/logs/12345/container.log
   - stderr → koji logger + /mnt/koji/logs/12345/container.log
  ↓
5. wait(container_id)
   podman wait abc123def456
   → exit_code: 0 (success) or non-zero (failure)
  ↓
6. remove(container_id)
   podman rm abc123def456
```

**Files Involved:**
- `koji_adjutant/container/podman_manager.py` (PodmanManager class)
- `koji_adjutant/task_adapters/logging.py` (FileKojiLogSink)

### 4.1 Inside the Container

**What the container does:**

```bash
# Phase 1 (Simple Build):
cd /work/12345
rpmbuild --rebuild work/mypackage-1.0-1.src.rpm \
  --define "_topdir /work/12345" \
  --define "_rpmdir /work/12345/result" \
  ...

# Phase 2.2 (Full Buildroot):
# Step 1: Run initialization script
bash /work/12345/init-buildroot.sh
  → dnf install gcc make python3-devel ...
  → mkdir -p /builddir/{BUILD,RPMS,SRPMS,...}
  → export RPM_BUILD_DIR=/builddir/BUILD
  → ...

# Step 2: Build SRPM
cd /work/12345
rpmbuild --rebuild work/mypackage-1.0-1.src.rpm \
  --define "_topdir /builddir" \
  --define "_builddir /builddir/BUILD" \
  --define "_rpmdir /work/12345/result" \
  --define "_srcrpmdir /work/12345/result" \
  --define "dist .fc39" \
  ...

# Step 3: Results placed in /work/12345/result/
# (which is /mnt/koji/work/12345/result on host)
```

**Outputs:**
- RPMs: `/mnt/koji/work/12345/result/*.rpm`
- SRPMs: `/mnt/koji/work/12345/result/*.src.rpm` (if keep_srpm=True)
- Logs: `/mnt/koji/work/12345/result/*.log`

---

## Repository Generation (Createrepo)

### 5. Createrepo Task Flow

```
CreaterepoAdapter.run()
  ↓
1. Build ContainerSpec
   - image: (from PolicyResolver or default)
   - command: createrepo_c -vd -o /work/12345/repo ...
   - mounts: /mnt/koji, /work/12345, repo directory
  ↓
2. Execute via PodmanManager
   (same lifecycle: create → start → stream → wait → remove)
  ↓
3. Inside Container:
   createrepo_c -vd -o /work/12345/repo \
     -i /mnt/koji/repos/f39-build/latest/x86_64/pkglist \
     /mnt/koji/repos/f39-build/latest/x86_64
  ↓
4. Results:
   /mnt/koji/work/12345/repo/repodata/
     - primary.xml.gz
     - filelists.xml.gz
     - other.xml.gz
     - repomd.xml
  ↓
5. Adapter collects file list
   Return: ["work/12345/repo", ["primary.xml.gz", ...]]
```

**Files Involved:**
- `koji_adjutant/task_adapters/createrepo.py` (CreaterepoAdapter)

---

## SRPM Rebuild Process (RebuildSRPM)

### 7. RebuildSRPM Task Flow

```
RebuildSRPMAdapter.run()
  ↓
1. Build ContainerSpec
   - image: (from PolicyResolver or default)
   - command: /bin/sleep infinity (exec pattern)
   - mounts: /mnt/koji, /work/12345
   - network_enabled: false (no network needed)
   ↓
2. Initialize buildroot with srpm-build group
   - Parse SRPM → Extract BuildRequires
   - Generate repo configuration
   - Create initialization commands
   ↓
3. Execute via PodmanManager (exec pattern)
   - Create container with sleep
   - Start container
   - Stream logs
   - Copy config files (/etc/yum.repos.d/koji.repo, /etc/rpm/macros.koji)
   - Execute init commands (mkdir, dnf install)
   ↓
4. Inside Container:
   # Step 1: Install dependencies
   dnf install -y @srpm-build gcc make ...
   
   # Step 2: Unpack SRPM
   rpm -ivh /work/12345/work/mypackage-1.0-1.src.rpm
   
   # Step 3: Rebuild SRPM with dist tags
   rpmbuild -bs /work/12345/work/mypackage-1.0-1.src.rpm \\
     --define "_topdir /work/12345" \\
     --define "_sourcedir /work/12345/work" \\
     --define "_srcrpmdir /work/12345/result" \\
     --define "dist .fc39"
   ↓
5. Collect Results:
   result = {
     'srpm': 'work/12345/result/mypackage-1.0-1.fc39.src.rpm',
     'logs': ['work/12345/result/build.log'],
     'brootid': 12345,
     'source': {'source': 'mypackage-1.0-1.src.rpm'}
   }
```

**Files Involved**:
- `koji_adjutant/task_adapters/rebuild_srpm.py` (RebuildSRPMAdapter)

---

## SRPM Build from SCM Process (BuildSRPMFromSCM)

### 8. BuildSRPMFromSCM Task Flow

```
BuildSRPMFromSCMAdapter.run()
  ↓
1. Build ContainerSpec
   - image: (from PolicyResolver or default)
   - command: /bin/sleep infinity (exec pattern)
   - mounts: /mnt/koji, /work/12345
   - network_enabled: true (KEY: Required for git checkout)
   ↓
2. Initialize buildroot with srpm-build group
   - Generate repo configuration
   - Create initialization commands
   ↓
3. Execute via PodmanManager (exec pattern)
   - Create container with sleep
   - Start container
   - Stream logs
   - Copy config files
   - Execute init commands
   ↓
4. Inside Container:
   # Step 1: Checkout source from git
   git clone --depth 1 --branch main git://example.com/repo.git /work/12345/source
   # OR for commits:
   git clone git://example.com/repo.git /work/12345/source
   git -C /work/12345/source checkout abc123
   
   # Step 2: Detect build method
   test -f /work/12345/source/Makefile && grep -q 'srpm:' /work/12345/source/Makefile
   # → "make" or "rpmbuild"
   
   # Step 3: Build SRPM
   # Method 1: make srpm
   make -C /work/12345/source srpm
   
   # Method 2: rpmbuild -bs
   rpmbuild -bs /work/12345/source/*.spec \\
     --define "_topdir /work/12345" \\
     --define "_sourcedir /work/12345/source" \\
     --define "_srcrpmdir /work/12345/result"
   ↓
5. Collect Results:
   result = {
     'srpm': 'work/12345/result/mypackage-1.0-1.src.rpm',
     'logs': ['work/12345/result/build.log'],
     'brootid': 12345,
     'source': {
       'source': 'mypackage-1.0-1.src.rpm',
       'url': 'git://example.com/repo.git',
       'commit': 'abc123',
       'branch': 'main'
     }
   }
```

**Files Involved**:
- `koji_adjutant/task_adapters/buildsrpm_scm.py` (BuildSRPMFromSCMAdapter)
- `koji_adjutant/task_adapters/scm/git.py` (GitHandler)

---

## Complete Workflow (SCM → SRPM → RPM)

### 9. End-to-End Build Workflow

```
User: koji build f39 git://example.com/package.git

1. BuildTask (parent coordinator)
   ↓
2. buildSRPMFromSCM subtask ← BuildSRPMFromSCMAdapter ✅
   - Checkout: git://example.com/package.git#main
   - Build: rpmbuild -bs or make srpm
   - Result: mypackage-1.0-1.src.rpm
   ↓
3. buildArch subtasks (parallel) ← BuildArchAdapter ✅
   - x86_64: rpmbuild --rebuild mypackage-1.0-1.src.rpm
   - aarch64: rpmbuild --rebuild mypackage-1.0-1.src.rpm
   - Results: mypackage-1.0-1.x86_64.rpm, mypackage-1.0-1.aarch64.rpm
   ↓
4. Upload all artifacts to hub
   ↓
5. Build complete!
```

**Key Points**:
- ✅ Full workflow supported (SCM → SRPM → RPM)
- ✅ Network enabled for SCM checkout
- ✅ Network disabled for RPM builds (security)
- ✅ Policy-driven image selection
- ✅ Buildroot initialization for both steps

---

## Result Reporting

### 6. Upload and Report to Hub

**BuildArch Results:**
```python
result = {
    'rpms': [
        'work/12345/result/mypackage-1.0-1.fc39.x86_64.rpm',
        'work/12345/result/mypackage-debuginfo-1.0-1.fc39.x86_64.rpm'
    ],
    'srpms': [
        'work/12345/result/mypackage-1.0-1.fc39.src.rpm'
    ],
    'logs': [
        'work/12345/result/build.log',
        'work/12345/result/root.log'
    ],
    'brootid': 12345  # task_id used as buildroot ID
}
```

**What happens:**
```
Task Handler
  ↓
For each file in result:
  session.uploadFile(local_path, remote_path)
  (uploads to koji hub storage)
  ↓
Complete task:
  session.host.taskFinished(task_id, result)
  ↓
Hub marks task CLOSED, stores result in database
```

**Files Involved:**
- `koji_adjutant/kojid.py` (BuildArchTask.handler, uploadFile calls)

**RebuildSRPM Results:**
```python
result = {
    'srpm': 'work/12345/result/mypackage-1.0-1.fc39.src.rpm',
    'logs': ['work/12345/result/build.log'],
    'brootid': 12345,
    'source': {
        'source': 'mypackage-1.0-1.src.rpm'
    }
}
```

**BuildSRPMFromSCM Results:**
```python
result = {
    'srpm': 'work/12345/result/mypackage-1.0-1.src.rpm',
    'logs': ['work/12345/result/build.log'],
    'brootid': 12345,
    'source': {
        'source': 'mypackage-1.0-1.src.rpm',
        'url': 'git://example.com/repo.git',
        'commit': 'abc123def456',
        'branch': 'main'
    }
}
```

**Createrepo Results:**
```python
result = [
    'work/12345/repo',  # uploadpath
    [                   # files
        'repodata/primary.xml.gz',
        'repodata/filelists.xml.gz',
        'repodata/other.xml.gz',
        'repodata/repomd.xml'
    ]
]
```

---

## Cleanup

### 7. Resource Cleanup

**Container Cleanup (Automatic):**
```
PodmanManager.run() guarantees:
  - Always calls remove() in finally block
  - Force removal if stuck (with timeout)
  - Container gone even if build failed
```

**Workspace Cleanup (Manual/Periodic):**
```
/mnt/koji/work/12345/ remains for:
  - Hub to download artifacts
  - Debugging failed builds

Cleaned up by:
  - Koji hub (after successful upload)
  - Worker periodic cleanup job (old/abandoned tasks)
  - Manual cleanup scripts
```

**Log Persistence:**
```
Container logs saved to:
  /mnt/koji/logs/12345/container.log

Kept permanently for debugging and audit trail
```

**Files Involved:**
- `koji_adjutant/container/podman_manager.py` (cleanup in finally blocks)

---

## Key Components Reference

### Data Flow Summary

```
kojid startup
  ↓
Read /etc/kojid/kojid.conf [config.py]
  ↓
Connect to hub (XMLRPC)
  ↓
Poll for tasks [kojid.py]
  ↓
Receive task → Create handler [kojid.py BuildArchTask/CreaterepoTask]
  ↓
Create TaskContext [task_adapters/base.py]
  ↓
Resolve image [policy/resolver.py] ← Query hub for policy
  ↓
Initialize buildroot [buildroot/initializer.py] ← Query hub for repos/deps
  ↓
Build ContainerSpec [task_adapters/buildarch.py or createrepo.py]
  ↓
Execute container [container/podman_manager.py] ← Use podman API
  ↓
Stream logs [task_adapters/logging.py] → Koji logger + filesystem
  ↓
Wait for completion
  ↓
Collect artifacts [task_adapters/*.py]
  ↓
Upload to hub [kojid.py]
  ↓
Report completion [kojid.py]
  ↓
Cleanup container [container/podman_manager.py]
```

### Module Overview

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `kojid.py` | Main daemon, task handlers | `BuildArchTask`, `CreaterepoTask` |
| `config.py` | Configuration parsing | `adjutant_*()` functions |
| `policy/resolver.py` | Image selection | `PolicyResolver` |
| `buildroot/initializer.py` | Buildroot setup | `BuildrootInitializer` |
| `buildroot/dependencies.py` | Dependency resolution | `parse_buildrequires()` |
| `buildroot/repos.py` | Repo configuration | `generate_repo_files()` |
| `buildroot/environment.py` | Build environment | `generate_rpm_macros()` |
| `container/interface.py` | Container abstraction | `ContainerManager`, `ContainerSpec` |
| `container/podman_manager.py` | Podman implementation | `PodmanManager` |
| `task_adapters/buildarch.py` | RPM build adapter | `BuildArchAdapter` |
| `task_adapters/createrepo.py` | Repo adapter | `CreaterepoAdapter` |
| `task_adapters/rebuild_srpm.py` | SRPM rebuild adapter ✨ | `RebuildSRPMAdapter` |
| `task_adapters/buildsrpm_scm.py` | SRPM from SCM adapter ✨ | `BuildSRPMFromSCMAdapter` |
| `task_adapters/scm/git.py` | Git SCM handler ✨ | `GitHandler` |
| `task_adapters/logging.py` | Log streaming | `FileKojiLogSink` |

### Configuration Keys

| Key | Default | Purpose |
|-----|---------|---------|
| `task_image_default` | `docker.io/almalinux/9-minimal:latest` | Fallback image |
| `image_pull_policy` | `if-not-present` | When to pull images |
| `policy_enabled` | `true` | Use hub policy for images |
| `policy_cache_ttl` | `300` | Policy cache seconds |
| `buildroot_enabled` | `true` | Full buildroot init |
| `network_enabled` | `true` | Container network access |
| `container_mounts` | `/mnt/koji:/mnt/koji:rw:Z` | Default mounts |
| `container_labels` | `worker_id=...` | Container labels |
| `container_timeouts` | `pull=300,start=60,stop_grace=20` | Timeouts |

### API Interactions (with Koji Hub)

| API Call | Purpose | Used By |
|----------|---------|---------|
| `session.getNextTask()` | Get task to execute | kojid main loop |
| `session.getTag(tag_id)` | Get tag metadata + policy | PolicyResolver |
| `session.getBuildConfig(tag)` | Get build config + repos | BuildrootInitializer |
| `session.repoInfo(repo_id)` | Get repo metadata | BuildrootInitializer |
| `session.uploadFile()` | Upload artifacts | Task handlers |
| `session.host.taskFinished()` | Report completion | Task handlers |

---

## Execution Example: Complete Flow

**Scenario:** Build mypackage-1.0-1 for Fedora 39 x86_64

```
1. Hub assigns task 12345:
   buildArch(pkg="mypackage-1.0-1.src.rpm", root="f39-build", arch="x86_64")

2. Worker receives task, creates TaskContext:
   task_id=12345, work_dir=/mnt/koji/work/12345

3. PolicyResolver queries hub:
   "What image for f39-build + x86_64?"
   → Hub policy: "registry.io/koji-buildroot:f39-x86_64"

4. BuildrootInitializer prepares:
   a. Parse SRPM → BuildRequires: gcc, make, python3-devel
   b. Query hub → repo URL: http://koji.example.com/repos/f39-build/98765/x86_64
   c. Generate /mnt/koji/work/12345/init-buildroot.sh:
      dnf install -y gcc make python3-devel
      mkdir -p /builddir/{BUILD,RPMS,SRPMS,SOURCES,SPECS}
   d. Generate /mnt/koji/work/12345/koji.repo

5. BuildArchAdapter creates ContainerSpec:
   - image: registry.io/koji-buildroot:f39-x86_64
   - command: bash -c "bash init-buildroot.sh && rpmbuild ..."
   - mounts: /mnt/koji, /work/12345
   - user: 1000:1000

6. PodmanManager executes:
   a. Pull image (if not present)
   b. Create container
   c. Start container
   d. Stream logs to FileKojiLogSink:
      → koji logger (INFO/ERROR)
      → /mnt/koji/logs/12345/container.log
   e. Wait for exit (blocks)
   f. Remove container

7. Inside container:
   a. Run init-buildroot.sh:
      dnf install gcc make python3-devel → success
   b. Run rpmbuild:
      rpmbuild --rebuild work/mypackage-1.0-1.src.rpm
      → RPMs in /work/12345/result/

8. BuildArchAdapter collects results:
   result = {
     'rpms': ['work/12345/result/mypackage-1.0-1.fc39.x86_64.rpm'],
     'srpms': ['work/12345/result/mypackage-1.0-1.fc39.src.rpm'],
     'logs': ['work/12345/result/build.log'],
     'brootid': 12345
   }

9. Task handler uploads:
   For each file → session.uploadFile()

10. Task handler reports:
    session.host.taskFinished(12345, result)

11. Hub marks task CLOSED, build complete!
```

---

## Phase Implementation Status

### ✅ Phase 1 (Complete)
- Container abstraction (ContainerManager, PodmanManager)
- Basic task adapters (BuildArch, Createrepo)
- Simple RPM builds (no dependency resolution)
- Test suite with 65% coverage

### ✅ Phase 2.1 (Complete)
- Real kojid.conf parsing
- Hub policy-driven image selection
- Cache for policy lookups
- 43 tests passing

### 🔄 Phase 2.2 (In Progress)
- Full buildroot initialization
- Dependency resolution from SRPM
- Repository configuration
- Build environment setup
- ~70% complete, testing pending

### ✅ Phase 2.5 (Complete)
- SRPM rebuild adapter (RebuildSRPMAdapter)
- SRPM from SCM adapter (BuildSRPMFromSCMAdapter)
- SCM integration (git handler)
- Complete workflow support (SCM → SRPM → RPM)
- 52 tests passing (100%)
- 85% coverage

### ⏳ Phase 2.3 (Planned)
- Performance optimization
- Benchmarking vs mock
- Container image caching

### ⏳ Phase 2.4 (Planned)
- Production readiness
- Comprehensive testing
- Documentation
- Integration with koji-boxed

---

## Troubleshooting

### Common Issues

**Container fails to start:**
- Check image availability: `podman images`
- Check SELinux labels on `/mnt/koji`
- Verify user ID 1000 has access to work directories

**Build fails with missing dependencies:**
- Check buildroot_enabled config
- Verify hub repo configuration
- Check container network access
- Review init-buildroot.sh script in work directory

**Policy not being used:**
- Check policy_enabled=true in config
- Verify tag has adjutant_image_policy extra data on hub
- Check cache TTL hasn't expired
- Review PolicyResolver logs

**Logs not appearing:**
- Check /mnt/koji/logs/<task_id>/container.log exists
- Verify FileKojiLogSink permissions
- Check koji logger configuration

### Debug Commands

```bash
# Check container status
podman ps -a --filter label=io.koji.adjutant.task_id=12345

# View container logs
podman logs <container_id>

# Inspect container
podman inspect <container_id>

# Check mounts
podman inspect <container_id> | jq '.[0].Mounts'

# View work directory
ls -la /mnt/koji/work/12345/

# View task logs
cat /mnt/koji/logs/12345/container.log

# Test policy resolution
python3 -c "from koji_adjutant.policy import PolicyResolver; ..."
```

---

**End of Workflow Guide**
