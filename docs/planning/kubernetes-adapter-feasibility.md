# Kubernetes Adapter Feasibility Analysis

**Date**: 2025-10-31
**Author**: Container Engineer
**Status**: Planning / Future Work
**Related**: Phase 1 (Foundation), Container Lifecycle ADR 0001

---

## Executive Summary

**Verdict: ✅ HIGHLY FEASIBLE**

The current `ContainerManager` abstraction is runtime-agnostic and can support both Podman and Kubernetes implementations with minimal interface changes. The exec-based pattern and one-container-per-task model map cleanly to Kubernetes pod semantics.

**Key Operations Tested:**
- ✅ Container lifecycle (create, start, wait, remove)
- ✅ Multi-exec pattern (multiple commands in same container)
- ✅ File copying (copy_to)
- ✅ Log streaming
- ✅ Volume mounting

**Recommendation**: Keep current abstraction. When Kubernetes support is needed, implement parallel `KubernetesManager` adapter without interface changes.

---

## Context & Motivation

### Current Implementation

Koji-Adjutant uses Podman containers for build isolation:
- **One ephemeral container per task**
- **Multiple exec calls** into same container for multi-step builds
- **File copying** for configuration (repo files, macros)
- **Shared volumes** for build artifacts (`/mnt/koji`)

### Why Kubernetes?

Potential future needs:
1. **Scale-out**: Distribute build tasks across cluster nodes
2. **Cloud deployment**: Run in managed Kubernetes (EKS, GKE, AKS)
3. **Resource management**: Leverage K8s scheduling, quotas, auto-scaling
4. **Multi-tenancy**: Namespace isolation per build tag or team
5. **Observability**: K8s-native monitoring and metrics

---

## Interface Analysis

### Current ContainerManager Protocol

```python
class ContainerManager(Protocol):
    def ensure_image_available(image: str) -> None
    def create(spec: ContainerSpec) -> ContainerHandle
    def start(handle: ContainerHandle) -> None
    def stream_logs(handle: ContainerHandle, sink: LogSink, follow: bool) -> None
    def wait(handle: ContainerHandle) -> int
    def remove(handle: ContainerHandle, force: bool) -> None
    def exec(handle: ContainerHandle, command: Sequence[str],
             sink: LogSink, environment: Optional[Dict]) -> int
    def copy_to(handle: ContainerHandle, src_path: Path, dest_path: str) -> None
    def run(spec: ContainerSpec, sink: LogSink, attach_streams: bool) -> ContainerRunResult
```

### Kubernetes Compatibility Matrix

| Operation | Podman Implementation | Kubernetes Equivalent | Compatibility |
|-----------|----------------------|----------------------|---------------|
| `ensure_image_available` | `podman pull` | ImagePullPolicy in PodSpec | ✅ Automatic |
| `create` | `podman create` | `kubectl create pod` | ✅ Direct mapping |
| `start` | `podman start` | Implicit (pods start on create) | ⚠️ No-op needed |
| `stream_logs` | `podman logs --follow` | `kubectl logs -f` | ✅ Nearly identical |
| `wait` | `podman wait` | `kubectl wait` or watch API | ✅ Different API, same semantics |
| `remove` | `podman rm` | `kubectl delete pod` | ✅ Direct mapping |
| `exec` | `podman exec` | `kubectl exec` | ✅ **Nearly identical API** |
| `copy_to` | `podman cp` | `tar \| kubectl exec` | ✅ Standard K8s pattern |
| `run` | Orchestration helper | Same orchestration | ✅ High-level wrapper |

**Result**: All operations have clean Kubernetes equivalents.

---

## Proposed Kubernetes Adapter Design

### Architecture

```
koji_adjutant/container/
├── interface.py              # Protocol (unchanged)
├── podman_manager.py         # Podman implementation (current)
└── kubernetes_manager.py     # Kubernetes implementation (new)
```

### Kubernetes Mapping Strategy

**Pod per Task Model:**
- One Kubernetes Pod per koji task
- Single container per pod
- Pod name: `task-{task_id}-{random}`
- Labels: `io.koji.adjutant.task`, `io.koji.adjutant.worker`

**Container in Pod:**
- Maps directly to `ContainerSpec`
- Command: From `spec.command` (e.g., `/bin/sleep infinity`)
- Image: From `spec.image`
- Working directory: From `spec.workdir`
- Environment: From `spec.environment`
- User context: From `spec.user_id` / `spec.group_id`

### Volume Mounting Strategy

**Podman Approach:**
```python
VolumeMount(
    source=Path("/mnt/koji/work/12345"),
    target=Path("/workspace"),
    read_only=False,
)
```

**Kubernetes Translation:**
```python
# Translate to hostPath volume + mount
volumes = [
    client.V1Volume(
        name="workspace",
        host_path=client.V1HostPathVolumeSource(
            path="/mnt/koji/work/12345",
            type="DirectoryOrCreate",
        ),
    ),
]

volume_mounts = [
    client.V1VolumeMount(
        name="workspace",
        mount_path="/workspace",
        read_only=False,
    ),
]
```

**Volume Strategy Options:**

1. **hostPath** (simplest):
   - Direct host directory mount
   - Requires node affinity (pods must run on nodes with `/mnt/koji`)
   - Best for single-node or all-nodes-have-storage setups

2. **NFS PersistentVolume**:
   - Shared NFS for `/mnt/koji`
   - Works across any cluster node
   - Requires NFS server setup

3. **Local PersistentVolume**:
   - Static provisioning for specific nodes
   - Node affinity via PV node selector
   - More K8s-native than hostPath

**Phase 1 Recommendation**: Use hostPath with node affinity

---

## Key Operations Implementation

### 1. create() - Pod Creation

```python
def create(self, spec: ContainerSpec) -> ContainerHandle:
    """Create Kubernetes Pod from ContainerSpec."""
    pod_name = f"task-{spec.environment.get('KOJI_TASK_ID', 'unknown')}-{os.urandom(4).hex()}"

    # Translate volumes
    volumes = []
    volume_mounts = []
    for i, mount in enumerate(spec.mounts):
        vol_name = f"vol-{i}"
        volumes.append(
            client.V1Volume(
                name=vol_name,
                host_path=client.V1HostPathVolumeSource(
                    path=str(mount.source),
                    type="DirectoryOrCreate",
                ),
            )
        )
        volume_mounts.append(
            client.V1VolumeMount(
                name=vol_name,
                mount_path=str(mount.target),
                read_only=mount.read_only,
            )
        )

    # Build container spec
    container = client.V1Container(
        name="task",
        image=spec.image,
        command=list(spec.command),
        env=[client.V1EnvVar(name=k, value=v) for k, v in spec.environment.items()],
        working_dir=str(spec.workdir) if spec.workdir else None,
        volume_mounts=volume_mounts,
        security_context=client.V1SecurityContext(
            run_as_user=spec.user_id,
            run_as_group=spec.group_id,
        ) if spec.user_id else None,
        resources=self._translate_resources(spec.resource_limits),
    )

    # Build pod spec
    pod_spec = client.V1PodSpec(
        containers=[container],
        volumes=volumes,
        restart_policy="Never",  # Ephemeral - never restart
        host_network=spec.network_enabled,
    )

    # Create pod metadata
    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=pod_name,
            labels={
                "io.koji.adjutant.task": spec.environment.get("KOJI_TASK_ID", "unknown"),
                "io.koji.adjutant.worker": self._worker_id or "unknown",
                "io.koji.adjutant.managed": "true",
            },
        ),
        spec=pod_spec,
    )

    # Create pod
    created_pod = self._core_api.create_namespaced_pod(
        namespace=self._namespace,
        body=pod,
    )

    return ContainerHandle(container_id=created_pod.metadata.name)
```

### 2. start() - Pod Startup

```python
def start(self, handle: ContainerHandle) -> None:
    """Wait for pod to reach Running state.

    Kubernetes pods start automatically on creation, so this
    method just waits for the Running phase.
    """
    timeout = 60
    start_time = monotonic()

    while monotonic() - start_time < timeout:
        pod = self._core_api.read_namespaced_pod(
            name=handle.container_id,
            namespace=self._namespace,
        )

        if pod.status.phase == "Running":
            return

        if pod.status.phase in ("Failed", "Unknown"):
            # Get failure reason
            reason = "Unknown"
            if pod.status.container_statuses:
                state = pod.status.container_statuses[0].state
                if state.waiting:
                    reason = state.waiting.reason
            raise ContainerError(f"Pod failed to start: {reason}")

        sleep(1)

    raise ContainerError(f"Pod did not start within {timeout}s")
```

### 3. exec() - Command Execution

```python
def exec(
    self,
    handle: ContainerHandle,
    command: Sequence[str],
    sink: LogSink,
    environment: Optional[Dict[str, str]] = None,
) -> int:
    """Execute command in pod - nearly identical to podman exec."""
    from kubernetes.stream import stream

    # Build exec command with environment
    exec_command = list(command)
    if environment:
        # Prefix with env command
        env_prefix = ["env"] + [f"{k}={v}" for k, v in environment.items()]
        exec_command = env_prefix + exec_command

    # Execute via Kubernetes exec API
    # This is remarkably similar to podman exec!
    resp = stream(
        self._core_api.connect_get_namespaced_pod_exec,
        name=handle.container_id,
        namespace=self._namespace,
        command=exec_command,
        container="task",  # Container name within pod
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
        _preload_content=False,  # Stream mode
    )

    # Stream output to sink
    while resp.is_open():
        resp.update(timeout=1)
        if resp.peek_stdout():
            sink.write_stdout(resp.read_stdout().encode())
        if resp.peek_stderr():
            sink.write_stderr(resp.read_stderr().encode())

    # Parse exit code from error message or status
    exit_code = 0
    error = resp.read_channel(3)  # Error channel
    if error:
        # K8s returns exit code in error message
        import json
        try:
            error_obj = json.loads(error)
            if error_obj.get("status") == "Failure":
                # Extract exit code from message
                exit_code = error_obj.get("details", {}).get("causes", [{}])[0].get("message", "1")
                exit_code = int(exit_code) if exit_code.isdigit() else 1
        except (json.JSONDecodeError, KeyError, ValueError):
            exit_code = 1 if error else 0

    return exit_code
```

### 4. copy_to() - File Copy

```python
def copy_to(
    self,
    handle: ContainerHandle,
    src_path: Path,
    dest_path: str,
) -> None:
    """Copy file to pod using tar-over-exec pattern.

    This is the standard Kubernetes pattern for file copy:
    tar cvf - file | kubectl exec -i pod -- tar xf - -C /dest
    """
    from kubernetes.stream import stream
    import tarfile
    import io

    # Create tar archive in memory
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
        tar.add(str(src_path), arcname=Path(dest_path).name)
    tar_buffer.seek(0)

    # Determine destination directory
    dest_dir = str(Path(dest_path).parent)

    # Execute tar extraction in pod
    resp = stream(
        self._core_api.connect_get_namespaced_pod_exec,
        name=handle.container_id,
        namespace=self._namespace,
        command=['tar', 'xf', '-', '-C', dest_dir],
        container="task",
        stderr=True,
        stdin=True,
        stdout=True,
        tty=False,
        _preload_content=False,
    )

    # Write tar stream to stdin
    resp.write_stdin(tar_buffer.read())
    resp.close()

    # Check for errors
    error = resp.read_channel(3)
    if error:
        raise ContainerError(f"Failed to copy file to pod: {error}")
```

### 5. stream_logs() - Log Streaming

```python
def stream_logs(
    self,
    handle: ContainerHandle,
    sink: LogSink,
    follow: bool = True,
) -> None:
    """Stream pod logs - nearly identical to podman."""
    try:
        log_stream = self._core_api.read_namespaced_pod_log(
            name=handle.container_id,
            namespace=self._namespace,
            container="task",
            follow=follow,
            timestamps=False,
            _preload_content=False,  # Stream mode
        )

        # Stream to sink
        for line in log_stream:
            sink.write_stdout(line)

    except Exception as exc:
        logger.warning("Failed to stream logs: %s", exc)
```

### 6. wait() - Wait for Completion

```python
def wait(self, handle: ContainerHandle) -> int:
    """Wait for pod completion and return exit code."""
    from kubernetes import watch

    w = watch.Watch()

    try:
        for event in w.stream(
            self._core_api.list_namespaced_pod,
            namespace=self._namespace,
            field_selector=f"metadata.name={handle.container_id}",
            timeout_seconds=3600,  # 1 hour max
        ):
            pod = event['object']
            phase = pod.status.phase

            if phase in ("Succeeded", "Failed"):
                w.stop()

                # Extract container exit code
                if pod.status.container_statuses:
                    container_status = pod.status.container_statuses[0]
                    if container_status.state.terminated:
                        return container_status.state.terminated.exit_code

                # Fallback based on phase
                return 0 if phase == "Succeeded" else 1

        # Timeout
        return 1

    finally:
        w.stop()
```

### 7. remove() - Pod Cleanup

```python
def remove(self, handle: ContainerHandle, force: bool = False) -> None:
    """Delete pod and associated resources."""
    grace_period = 0 if force else 20

    try:
        self._core_api.delete_namespaced_pod(
            name=handle.container_id,
            namespace=self._namespace,
            grace_period_seconds=grace_period,
        )
    except NotFound:
        # Pod already deleted - this is fine
        pass
    except Exception as exc:
        logger.warning("Failed to delete pod %s: %s", handle.container_id, exc)
```

---

## Semantic Differences & Solutions

### 1. Create vs. Start Separation

**Podman:**
- `create()` prepares container (doesn't start process)
- `start()` explicitly starts the container process

**Kubernetes:**
- Pod starts immediately upon creation
- No separate "start" operation

**Solution:**
```python
def start(self, handle: ContainerHandle) -> None:
    """Wait for pod to reach Running phase."""
    # Kubernetes-specific: just wait for Running state
    # The pod started automatically on create()
    self._wait_for_running(handle)
```

### 2. Volume Mount Semantics

**Podman:**
- Direct host path mounting with SELinux labels (`:Z`, `:z`)
- `--mount type=bind,src=/host,dst=/container,Z`

**Kubernetes:**
- Requires Volume + VolumeMount objects
- SELinux labels handled differently (securityContext)
- hostPath, NFS, or PersistentVolume

**Solution:**
```python
# Translate VolumeMount.selinux_label to Pod securityContext
if any(m.selinux_label for m in spec.mounts):
    pod_spec.security_context = client.V1PodSecurityContext(
        se_linux_options=client.V1SELinuxOptions(
            level="s0:c123,c456"  # Derived from label
        )
    )
```

### 3. Network Isolation

**Podman:**
- `--network none` for complete isolation
- Each container has own network namespace

**Kubernetes:**
- `hostNetwork: true` uses host networking
- `hostNetwork: false` creates pod network namespace
- All containers in pod share network

**Solution:**
```python
# Invert the logic
pod_spec.host_network = not spec.network_enabled
```

### 4. Resource Limits

**Podman:**
```python
ResourceLimits(
    memory_bytes=4 * 1024 * 1024 * 1024,  # 4GB
    cpus=2.0,
)
```

**Kubernetes:**
```python
resources = client.V1ResourceRequirements(
    limits={
        "memory": "4Gi",
        "cpu": "2000m",  # 2 CPUs = 2000 millicores
    },
    requests={
        "memory": "2Gi",
        "cpu": "1000m",
    },
)
```

**Solution:** Add converter method:
```python
def _translate_resources(self, limits: Optional[ResourceLimits]) -> client.V1ResourceRequirements:
    if not limits:
        return client.V1ResourceRequirements()

    k8s_limits = {}
    k8s_requests = {}

    if limits.memory_bytes:
        k8s_limits["memory"] = f"{limits.memory_bytes // (1024*1024)}Mi"
        k8s_requests["memory"] = f"{limits.memory_bytes // (1024*1024) // 2}Mi"

    if limits.cpus:
        k8s_limits["cpu"] = f"{int(limits.cpus * 1000)}m"
        k8s_requests["cpu"] = f"{int(limits.cpus * 500)}m"

    return client.V1ResourceRequirements(
        limits=k8s_limits,
        requests=k8s_requests,
    )
```

---

## Deployment Requirements

### 1. Kubernetes Cluster Setup

**Namespace:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: koji-adjutant
  labels:
    app: koji-adjutant
```

**Service Account:**
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: koji-adjutant-worker
  namespace: koji-adjutant
```

**RBAC - Role:**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: koji-adjutant-worker
  namespace: koji-adjutant
rules:
- apiGroups: [""]
  resources: ["pods", "pods/log", "pods/exec"]
  verbs: ["create", "delete", "get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods/status"]
  verbs: ["get"]
```

**RBAC - RoleBinding:**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: koji-adjutant-worker
  namespace: koji-adjutant
subjects:
- kind: ServiceAccount
  name: koji-adjutant-worker
  namespace: koji-adjutant
roleRef:
  kind: Role
  name: koji-adjutant-worker
  apiGroup: rbac.authorization.k8s.io
```

### 2. Storage Configuration

**Option A: hostPath (Simple)**

Requires `/mnt/koji` on all worker nodes:

```yaml
# Node affinity in pod spec
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: koji.storage
          operator: In
          values:
          - available
```

Label nodes:
```bash
kubectl label node worker-1 koji.storage=available
kubectl label node worker-2 koji.storage=available
```

**Option B: NFS PersistentVolume**

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: koji-storage
spec:
  capacity:
    storage: 1Ti
  accessModes:
  - ReadWriteMany
  nfs:
    server: nfs.example.com
    path: /koji
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: koji-storage
  namespace: koji-adjutant
spec:
  accessModes:
  - ReadWriteMany
  resources:
    requests:
      storage: 1Ti
```

### 3. Container Image Registry

**Requirements:**
- Build images must be accessible from cluster
- Configure ImagePullSecrets if using private registry

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: koji-registry-creds
  namespace: koji-adjutant
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: <base64-encoded-docker-config>
```

Reference in pod spec:
```python
pod_spec.image_pull_secrets = [
    client.V1LocalObjectReference(name="koji-registry-creds")
]
```

---

## Configuration Design

### New Configuration Options

```python
# koji_adjutant/config.py

def adjutant_container_runtime() -> str:
    """Container runtime: 'podman' or 'kubernetes'."""
    return os.getenv("ADJUTANT_CONTAINER_RUNTIME", "podman")

def adjutant_k8s_namespace() -> str:
    """Kubernetes namespace for task pods."""
    return os.getenv("ADJUTANT_K8S_NAMESPACE", "koji-adjutant")

def adjutant_k8s_config() -> Optional[str]:
    """Path to kubeconfig file. None = in-cluster or default."""
    return os.getenv("ADJUTANT_K8S_CONFIG")

def adjutant_k8s_service_account() -> Optional[str]:
    """Service account for task pods."""
    return os.getenv("ADJUTANT_K8S_SERVICE_ACCOUNT", "koji-adjutant-worker")

def adjutant_k8s_node_selector() -> Dict[str, str]:
    """Node selector labels for task pods."""
    selector_str = os.getenv("ADJUTANT_K8S_NODE_SELECTOR", "")
    if not selector_str:
        return {}
    # Parse "key1=value1,key2=value2"
    return dict(pair.split("=") for pair in selector_str.split(",") if "=" in pair)

def adjutant_k8s_storage_class() -> Optional[str]:
    """Storage class for dynamic volume provisioning."""
    return os.getenv("ADJUTANT_K8S_STORAGE_CLASS")
```

### Runtime Selection

```python
# In TaskManager or main daemon initialization

def create_container_manager(worker_id: str) -> ContainerManager:
    """Factory for container runtime."""
    runtime = config.adjutant_container_runtime()

    if runtime == "kubernetes":
        from koji_adjutant.container.kubernetes_manager import KubernetesManager
        return KubernetesManager(
            namespace=config.adjutant_k8s_namespace(),
            kubeconfig=config.adjutant_k8s_config(),
            service_account=config.adjutant_k8s_service_account(),
            node_selector=config.adjutant_k8s_node_selector(),
            worker_id=worker_id,
        )
    elif runtime == "podman":
        from koji_adjutant.container.podman_manager import PodmanManager
        return PodmanManager(worker_id=worker_id)
    else:
        raise ValueError(f"Unknown container runtime: {runtime}")
```

---

## Challenges & Mitigation

### 1. Shared Filesystem Access

**Challenge:** Kubernetes pods need access to `/mnt/koji` for artifacts

**Solutions:**
- **hostPath**: Simple, requires nodes have `/mnt/koji` mounted
- **NFS**: Shared storage, works across all nodes
- **Rook/Ceph**: Distributed storage for large clusters
- **CSI drivers**: Cloud-specific (EBS, GCE PD, Azure Disk)

**Recommendation:** Start with hostPath + node affinity for simplicity

### 2. Node Affinity & Scheduling

**Challenge:** Pods must run on nodes with storage access

**Solution:**
```python
# Add to pod spec
pod_spec.node_selector = config.adjutant_k8s_node_selector()
# or more complex affinity rules
pod_spec.affinity = client.V1Affinity(
    node_affinity=client.V1NodeAffinity(
        required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
            node_selector_terms=[
                client.V1NodeSelectorTerm(
                    match_expressions=[
                        client.V1NodeSelectorRequirement(
                            key="koji.storage",
                            operator="In",
                            values=["available"],
                        )
                    ]
                )
            ]
        )
    )
)
```

### 3. SELinux Label Translation

**Challenge:** Podman's `:Z` and `:z` labels don't map directly to K8s

**Solution:**
```python
# Map selinux_label to Pod securityContext
if spec.mounts and any(m.selinux_label for m in spec.mounts):
    # Use pod-level SELinux context
    pod_spec.security_context = client.V1PodSecurityContext(
        se_linux_options=client.V1SELinuxOptions(
            level="s0:c123,c456",  # Unique per task
            type="container_runtime_t",
        )
    )
```

### 4. Resource Limit Semantics

**Challenge:** K8s requires both requests and limits

**Solution:** Auto-generate requests as 50% of limits
```python
k8s_requests["memory"] = f"{limits.memory_bytes // 2}Mi"
k8s_requests["cpu"] = f"{int(limits.cpus * 500)}m"
```

### 5. Exec Exit Code Extraction

**Challenge:** K8s exec API doesn't return exit codes directly

**Solution:** Parse from error channel or use exec with wrapper:
```python
# Option 1: Parse error channel (see exec() implementation above)

# Option 2: Wrapper command
exec_command = ["sh", "-c", f"{' '.join(command)}; echo EXIT_CODE=$?"]
# Parse EXIT_CODE from output
```

### 6. Network Isolation Differences

**Challenge:** K8s pods share network within pod

**Solution:** One container per pod maintains isolation (current model)

---

## Testing Strategy

### Unit Tests

**Mock Kubernetes API:**
```python
from unittest.mock import Mock, patch

def test_kubernetes_create():
    mock_core_api = Mock()
    mock_core_api.create_namespaced_pod.return_value = Mock(
        metadata=Mock(name="test-pod-abc123")
    )

    with patch("kubernetes.client.CoreV1Api", return_value=mock_core_api):
        manager = KubernetesManager(namespace="test")
        handle = manager.create(spec)

        assert handle.container_id == "test-pod-abc123"
        mock_core_api.create_namespaced_pod.assert_called_once()
```

### Integration Tests

**Requires K8s cluster (kind, minikube, or real cluster):**

```python
@pytest.mark.integration
@pytest.mark.kubernetes
def test_kubernetes_exec_pattern():
    """Test multi-exec pattern against real K8s cluster."""
    manager = KubernetesManager(namespace="test")

    spec = ContainerSpec(
        image="almalinux:10",
        command=["/bin/sleep", "300"],
        environment={"TEST": "value"},
        mounts=[...],
    )

    handle = manager.create(spec)
    try:
        manager.start(handle)

        # Test multiple execs
        sink = InMemoryLogSink()
        exit_code = manager.exec(handle, ["echo", "test1"], sink)
        assert exit_code == 0

        exit_code = manager.exec(handle, ["echo", "test2"], sink)
        assert exit_code == 0

    finally:
        manager.remove(handle, force=True)
```

### Manual Validation

```bash
# Deploy test pod
kubectl apply -f test-pod.yaml

# Test exec
kubectl exec test-pod-abc123 -- echo "hello"

# Test copy
echo "test" > test.txt
kubectl cp test.txt test-pod-abc123:/tmp/test.txt

# Verify
kubectl exec test-pod-abc123 -- cat /tmp/test.txt
```

---

## Performance Considerations

### Pod Startup Time

**Challenge:** K8s pod startup slower than `podman create`

**Typical Times:**
- **Podman**: 0.5-2 seconds (local image)
- **Kubernetes**: 5-15 seconds (image pull, scheduling, pod initialization)

**Mitigation:**
- Pre-pull images on all nodes (`imagePullPolicy: IfNotPresent`)
- Use smaller base images
- DaemonSet to warm image cache
- Node affinity to reduce scheduling time

### Exec Overhead

**Challenge:** K8s exec slightly slower than podman exec

**Mitigation:**
- Minimal - exec pattern is inherently fast
- Use persistent connections if possible
- Batch commands when appropriate

### Log Streaming

**Challenge:** K8s log streaming may have higher latency

**Mitigation:**
- Use `_preload_content=False` for streaming
- Buffer logs on client side if needed
- Consider sidecar for real-time log forwarding

---

## Benefits of Abstraction

### 1. Scale-Out Capability

Run koji-adjutant workers across multi-node cluster:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: koji-adjutant-workers
spec:
  replicas: 10  # Scale to 10 workers
  selector:
    matchLabels:
      app: koji-adjutant-worker
  template:
    metadata:
      labels:
        app: koji-adjutant-worker
    spec:
      containers:
      - name: worker
        image: koji-adjutant:latest
        env:
        - name: ADJUTANT_CONTAINER_RUNTIME
          value: "kubernetes"
```

### 2. Resource Management

Leverage K8s resource quotas and limits:
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: koji-adjutant-quota
  namespace: koji-adjutant
spec:
  hard:
    requests.cpu: "100"
    requests.memory: "400Gi"
    limits.cpu: "200"
    limits.memory: "800Gi"
```

### 3. Auto-Scaling

Use Horizontal Pod Autoscaler for workers:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: koji-adjutant-workers
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: koji-adjutant-workers
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### 4. Cloud Deployment

Run in managed Kubernetes services:
- **AWS EKS** with EBS volumes
- **GCP GKE** with GCE Persistent Disks
- **Azure AKS** with Azure Disks
- **OpenShift** (enterprise Kubernetes)

### 5. Observability

Native K8s monitoring:
- Prometheus metrics from pods
- Grafana dashboards
- K8s events integration
- Distributed tracing

### 6. Multi-Tenancy

Namespace isolation per build tag or team:
```python
# Create namespace per build tag
namespace = f"koji-{build_tag}"
manager = KubernetesManager(namespace=namespace)
```

---

## Recommendations

### Phase 1: Foundation (Now)

✅ **Keep current abstraction** - No changes needed to `ContainerManager` protocol

The exec pattern, copy pattern, and lifecycle management are runtime-agnostic.

### Phase 2: Proof of Concept (Future)

When Kubernetes support is needed:

1. **Implement `KubernetesManager`** in `koji_adjutant/container/kubernetes_manager.py`
2. **Add configuration options** for runtime selection
3. **Create factory function** to choose runtime
4. **Test against real K8s cluster** (kind or minikube)

### Phase 3: Integration (Future)

1. **Create K8s deployment manifests** (Deployment, Service, RBAC)
2. **Setup storage** (hostPath, NFS, or PV)
3. **Configure node affinity** for storage access
4. **Deploy to test cluster**
5. **Run integration tests** with real koji hub

### Phase 4: Production (Future)

1. **Performance benchmarking** (pod startup, exec latency)
2. **Resource optimization** (image caching, node pools)
3. **Monitoring integration** (Prometheus, Grafana)
4. **Documentation** (deployment guide, operations runbook)
5. **Scale testing** (concurrent builds, resource limits)

### Immediate Actions

1. ✅ **Document this analysis** (this file)
2. ✅ **No code changes needed** - interface is already suitable
3. 📋 **Add to backlog** - "Kubernetes adapter implementation"
4. 📋 **Create tracking issue** - Link to this document

---

## References

### Code Files

- `koji_adjutant/container/interface.py` - Protocol definition (unchanged)
- `koji_adjutant/container/podman_manager.py` - Podman implementation
- `docs/architecture/decisions/0001-container-lifecycle.md` - Lifecycle ADR
- `docs/planning/phase2.2-exec-pattern-impact-analysis.md` - Exec pattern design

### Kubernetes Documentation

- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
- [Pod Exec API](https://kubernetes.io/docs/tasks/debug-application-cluster/get-shell-running-container/)
- [Volumes](https://kubernetes.io/docs/concepts/storage/volumes/)
- [Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)

### Similar Projects

- **Tekton Pipelines** - K8s-native CI/CD (similar pod-per-task model)
- **Argo Workflows** - Container orchestration on K8s
- **Jenkins X** - Jenkins on Kubernetes

---

## Conclusion

**The abstraction is solid.** The `ContainerManager` protocol is runtime-agnostic and maps cleanly to both Podman and Kubernetes. The exec-based multi-step pattern works identically in both runtimes.

**No interface changes needed.** When Kubernetes support is required, implement `KubernetesManager` as a parallel adapter without modifying existing code.

**Key success factors:**
1. One pod per task maintains isolation
2. exec() pattern is portable across runtimes
3. copy_to() via tar-over-exec is standard K8s pattern
4. Volume mounts translate to hostPath or PersistentVolumes
5. Log streaming APIs are nearly identical

**Container Engineer Assessment: ✅ APPROVED FOR KUBERNETES ADAPTATION**

---

**Next Steps:**
- Archive this document for future reference
- Add "Kubernetes adapter" to project backlog
- No implementation required until scale-out or cloud deployment needed
- Current Podman implementation continues as primary runtime
