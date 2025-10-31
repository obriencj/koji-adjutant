---
title: "ADR 0005: Operational Monitoring and Status Server Architecture"
status: Proposed
date: 2025-01-27
deciders: Systems Architect, Implementation Lead
---

## Context

Phase 2.2 (exec pattern + buildroot) is validated and working. Phase 2.3 adds operational monitoring for production visibility. Production operators need real-time visibility into worker state, active containers, and task progress to debug issues, monitor performance, and ensure system health.

**Problem Statement**: Without operational monitoring, operators cannot:
- See which tasks are currently executing
- Monitor active containers and their resource usage
- Debug stuck builds or failed containers
- Track worker capacity and utilization
- Access task logs without SSH access to worker

**Constraints**:
- Must not interfere with task execution (low overhead)
- Must be optional (can be disabled via config)
- Must be secure (localhost-only by default)
- Must be lightweight (minimal dependencies)
- Must integrate cleanly with existing kojid architecture

## Decision

We implement a **lightweight HTTP status server** running in a background thread that provides RESTful endpoints for worker status, container tracking, and task monitoring. The server uses Python's standard library `http.server` with minimal dependencies, ensuring low overhead and maximum compatibility.

### HTTP Server Choice

**Decision**: Use Python `http.server` (stdlib) with simple JSON responses.

**Rationale**:
- **Zero dependencies**: Already available in Python stdlib
- **Minimal overhead**: Lightweight HTTP server suitable for status endpoints
- **Simple maintenance**: No external library updates or compatibility issues
- **Sufficient for needs**: Status endpoints don't require advanced features

**Alternatives Considered**:
- **bottle**: Single-file library, minimal dependencies. Rejected: Still requires external dependency.
- **flask**: Popular, well-documented. Rejected: Overkill for simple status endpoints, larger dependency.
- **FastAPI**: Modern, async-capable. Rejected: Requires async/await refactoring, larger dependency.
- **http.server**: Standard library, synchronous. **Selected**: Meets requirements without dependencies.

**Dependency Management**: No new dependencies required. Uses only Python stdlib (`http.server`, `json`, `threading`, `urllib.parse`).

### API Endpoints

**Base Path**: `/api/v1` (versioned for future changes)

**Core Endpoints**:

1. **`GET /api/v1/status`** - Worker health and status
   - Returns: Worker uptime, capacity, active task count, worker ID
   - Response time: < 10ms (cached metrics)
   - Example response:
     ```json
     {
       "worker_id": "worker-01",
       "uptime_seconds": 86400,
       "status": "healthy",
       "capacity": 4,
       "active_tasks": 2,
       "containers_active": 2,
       "tasks_completed_today": 45,
       "last_task_time": "2025-01-27T10:30:00Z"
     }
     ```

2. **`GET /api/v1/containers`** - List all active containers
   - Returns: List of containers with metadata (task_id, image, status, created_at)
   - Response time: < 50ms (queries container registry)
   - Example response:
     ```json
     {
       "containers": [
         {
           "container_id": "abc123...",
           "task_id": 12345,
           "image": "registry/koji-adjutant-buildroot:el10-x86_64",
           "status": "running",
           "created_at": "2025-01-27T10:15:00Z",
           "started_at": "2025-01-27T10:15:05Z"
         }
       ],
       "total": 2
     }
     ```

3. **`GET /api/v1/containers/<container_id>`** - Container details
   - Returns: Detailed container information (spec, mounts, resource limits)
   - Response time: < 100ms (queries podman API)
   - Example response:
     ```json
     {
       "container_id": "abc123...",
       "task_id": 12345,
       "image": "registry/koji-adjutant-buildroot:el10-x86_64",
       "status": "running",
       "spec": {
         "command": ["/bin/bash", "-c", "..."],
         "workdir": "/builddir",
         "user": "1000:1000"
       },
       "mounts": [
         {
           "source": "/mnt/koji",
           "target": "/mnt/koji",
           "read_only": false
         }
       ],
       "resource_limits": {
         "memory_bytes": null,
         "cpus": null
       },
       "created_at": "2025-01-27T10:15:00Z",
       "started_at": "2025-01-27T10:15:05Z"
     }
     ```

4. **`GET /api/v1/tasks`** - List all active tasks
   - Returns: List of active tasks with metadata
   - Response time: < 50ms (queries task registry)
   - Example response:
     ```json
     {
       "tasks": [
         {
           "task_id": 12345,
           "type": "buildArch",
           "status": "running",
           "arch": "x86_64",
           "tag": "el10-build",
           "started_at": "2025-01-27T10:15:00Z",
           "container_id": "abc123..."
         }
       ],
       "total": 2
     }
     ```

5. **`GET /api/v1/tasks/<task_id>`** - Task details
   - Returns: Detailed task information (type, parameters, progress, logs path)
   - Response time: < 50ms (queries task registry)
   - Example response:
     ```json
     {
       "task_id": 12345,
       "type": "buildArch",
       "status": "running",
       "arch": "x86_64",
       "tag": "el10-build",
       "srpm": "mypackage-1.0-1.src.rpm",
       "started_at": "2025-01-27T10:15:00Z",
       "container_id": "abc123...",
       "log_path": "/mnt/koji/logs/12345/container.log",
       "progress": {
         "stage": "buildroot_init",
         "percent": 45
       }
     }
     ```

6. **`GET /api/v1/tasks/<task_id>/logs`** - Stream task logs
   - Returns: Log content (last N lines or tail -f style streaming)
   - Query params: `tail=<lines>` (default: 100), `follow=<true|false>` (default: false)
   - Response time: < 100ms (reads log file)
   - Content-Type: `text/plain` or `text/event-stream` (if follow=true)
   - Example: `GET /api/v1/tasks/12345/logs?tail=500`

7. **`GET /api/v1/metrics`** (Optional) - Prometheus-style metrics
   - Returns: Prometheus text format metrics
   - Response time: < 10ms (cached metrics)
   - Example response:
     ```
     # HELP koji_adjutant_tasks_total Total tasks executed
     # TYPE koji_adjutant_tasks_total counter
     koji_adjutant_tasks_total 45
     # HELP koji_adjutant_containers_active Active containers
     # TYPE koji_adjutant_containers_active gauge
     koji_adjutant_containers_active 2
     ```

8. **`GET /`** - Simple HTML dashboard (optional)
   - Returns: HTML page with auto-refresh, showing worker status and active tasks
   - Response time: < 50ms (renders from template)
   - Can be disabled via config for minimal installations

**Error Responses**:
- `404 Not Found`: Task/container not found
- `500 Internal Server Error`: Server error (with error message in JSON)
- `503 Service Unavailable`: Monitoring disabled or server error

**Error Format**:
```json
{
  "error": "Task not found",
  "error_code": "TASK_NOT_FOUND",
  "task_id": 12345
}
```

### Container Registry Design

**Purpose**: Track active containers with metadata for status endpoints.

**Data Structure**: Thread-safe registry using `threading.RLock` and `dict`.

**Registry Schema**:
```python
class ContainerRegistry:
    """Thread-safe container registry tracking active containers."""
    
    _containers: Dict[str, ContainerInfo]  # container_id -> ContainerInfo
    _lock: threading.RLock
    
    class ContainerInfo:
        container_id: str
        task_id: Optional[int]
        image: str
        spec: ContainerSpec  # Copy of spec used to create container
        created_at: datetime
        started_at: Optional[datetime]
        finished_at: Optional[datetime]
        status: str  # "created", "running", "exited", "removed"
```

**Thread Safety**:
- All registry operations protected by `threading.RLock`
- Read operations: Acquire read lock (shared)
- Write operations: Acquire write lock (exclusive)
- Atomic updates: Use context managers for lock acquisition

**Lifecycle Integration**:
- **Registration**: When container created in `PodmanManager.create()` → `registry.register(container_id, task_id, spec)`
- **Status Updates**: When container started → `registry.update_status(container_id, "running")`
- **Unregistration**: When container removed → `registry.unregister(container_id)` (with cleanup delay for history)
- **Cleanup**: On worker shutdown → `registry.clear()`

**Cleanup on Crashes**:
- On startup: Query podman for all containers with `io.koji.adjutant.worker_id` label
- Reconstruct registry from podman state (best-effort)
- Stale entries: Remove containers not found in podman (orphaned entries)

**Retention Policy**:
- Active containers: Keep until removed
- Finished containers: Keep for 1 hour after removal (for debugging)
- Configurable retention: `adjutant_monitoring_container_history_ttl` (default: 3600 seconds)

### Task Registry Design

**Purpose**: Track active tasks with metadata for status endpoints.

**Data Structure**: Thread-safe registry similar to container registry.

**Registry Schema**:
```python
class TaskRegistry:
    """Thread-safe task registry tracking active tasks."""
    
    _tasks: Dict[int, TaskInfo]  # task_id -> TaskInfo
    _lock: threading.RLock
    
    class TaskInfo:
        task_id: int
        task_type: str  # "buildArch", "createrepo", etc.
        status: str  # "running", "completed", "failed"
        arch: Optional[str]
        tag: Optional[str]
        srpm: Optional[str]
        started_at: datetime
        finished_at: Optional[datetime]
        container_id: Optional[str]
        log_path: Optional[str]
        progress: Optional[Dict[str, Any]]  # Stage, percent, etc.
```

**Lifecycle Integration**:
- **Registration**: When task handler starts → `registry.register(task_id, task_type, params)`
- **Status Updates**: Task progress updates → `registry.update_progress(task_id, stage, percent)`
- **Completion**: When task completes → `registry.update_status(task_id, "completed"|"failed")`
- **Cleanup**: After retention period → `registry.unregister(task_id)`

**Retention Policy**:
- Active tasks: Keep until completion
- Completed tasks: Keep for 1 hour after completion (for debugging)
- Configurable retention: `adjutant_monitoring_task_history_ttl` (default: 3600 seconds)

### Integration Points

**1. Server Startup** (`kojid.py` main loop):
- Start monitoring server in background thread after TaskManager initialization
- Check config: `adjutant_monitoring_enabled = true` (default: false)
- Bind address: `adjutant_monitoring_bind` (default: "127.0.0.1:8080")
- Start thread: `monitoring_server = MonitoringServer(...)` → `server.start()`
- Graceful shutdown: On SIGTERM/SIGINT, stop server thread before TaskManager shutdown

**2. Container Registration** (`PodmanManager.create()`):
- After successful container creation, register with registry:
  ```python
  container_id = self._create_container(spec)
  if monitoring_registry:
      monitoring_registry.register(container_id, task_id, spec)
  return ContainerHandle(container_id=container_id)
  ```

**3. Container Unregistration** (`PodmanManager.remove()`):
- After container removal, unregister from registry:
  ```python
  container.remove(force=force)
  if monitoring_registry:
      monitoring_registry.unregister(container_id)
  ```

**4. Task Registration** (Task adapters):
- In `BuildArchAdapter.build()` or similar, register task:
  ```python
  if monitoring_registry:
      monitoring_registry.register_task(task_id, "buildArch", params)
  ```

**5. Task Completion** (Task adapters):
- On task completion, update registry:
  ```python
  if monitoring_registry:
      monitoring_registry.update_task_status(task_id, "completed")
  ```

**6. Log Access**:
- Log path stored in task registry: `/mnt/koji/logs/<task_id>/container.log`
- Log endpoint reads directly from filesystem (no streaming for now)
- Future: Add streaming support with Server-Sent Events (SSE)

### Data Collection

**Worker Metrics** (from kojid state):
- Uptime: Track worker start time (`datetime.now()` at startup)
- Capacity: From `options.capacity` (config)
- Active tasks: Count from TaskRegistry
- Completed tasks: Count from TaskRegistry history
- Worker ID: From config or environment

**Container Metrics** (from podman API):
- Container status: Query podman API (`container.status`)
- Resource usage: Query podman stats API (optional, future)
- Container logs: Access via podman logs API or filesystem

**Task Metadata** (from task handlers):
- Task type: From task handler class
- Task parameters: From task handler context
- Progress: Task handlers update progress via registry
- Log path: From `FileKojiLogSink` (already implemented)

**Log Access**:
- Primary: Filesystem (`/mnt/koji/logs/<task_id>/container.log`)
- Fallback: Podman logs API if file not found
- Streaming: Read file in chunks with `tail -f` style behavior

### Security Model

**Bind Address**:
- Default: `127.0.0.1:8080` (localhost only)
- Configurable: `adjutant_monitoring_bind = "0.0.0.0:8080"` (for remote access)
- Security warning: Exposing to network requires authentication

**Authentication** (Optional, Future):
- Simple token auth: `adjutant_monitoring_token = "secret-token"`
- Header: `Authorization: Bearer <token>`
- Phase 2.3: No authentication (localhost only)
- Phase 2.4: Add token authentication for network exposure

**Read-Only Access**:
- All endpoints are read-only (no task control)
- No endpoints to stop tasks, kill containers, or modify state
- Status-only: Information retrieval only

**Data Exposure**:
- **Expose**: Task IDs, container IDs, status, logs (already accessible via filesystem)
- **Hide**: Sensitive data (passwords, tokens) from logs
- **Sanitize**: Log endpoints filter sensitive patterns (if needed)

**Network Security**:
- Default: localhost-only binding prevents network exposure
- Firewall: Operators can add firewall rules if needed
- TLS: Not required for localhost, optional for network (future)

### Performance Considerations

**Background Thread**:
- Server runs in separate thread: `threading.Thread(target=server.serve_forever, daemon=True)`
- Daemon thread: Exits when main thread exits
- Non-blocking: Main task loop not affected by server requests

**Request Handling Overhead**:
- Synchronous requests: Each request handled in separate thread (via `ThreadingHTTPServer`)
- Request timeout: 5 seconds (prevents hanging requests)
- Response caching: Worker metrics cached for 1 second (reduce overhead)

**Podman API Query Rate Limits**:
- Container list: Query podman API directly (no caching, ~50ms overhead)
- Container details: Query podman API on-demand (no caching, ~100ms overhead)
- Optimization: Cache container list for 1 second (reduce podman queries)

**Memory Overhead**:
- Registry size: ~1KB per container/task (minimal)
- Expected: < 100KB for 50 active containers/tasks
- Acceptable: < 1MB total overhead

**CPU Overhead**:
- Idle: < 0.1% CPU (HTTP server listening)
- Active: < 1% CPU per request (JSON serialization, registry queries)
- Acceptable: < 1% total overhead for typical usage

**Concurrent Requests**:
- ThreadingHTTPServer: Handles multiple concurrent requests
- Max threads: 10 concurrent requests (configurable)
- Overflow: 503 Service Unavailable if overloaded

## Consequences

### Positive Consequences

1. **Operational Visibility**: Operators can monitor worker state without SSH access
2. **Debugging**: Easy access to task logs and container status
3. **Integration**: Can integrate with monitoring systems (Prometheus, Grafana)
4. **Low Overhead**: Minimal performance impact (< 1% CPU/memory)
5. **Optional**: Can be disabled for minimal installations

### Negative Consequences

1. **Code Complexity**: Adds monitoring server module and registry management
2. **Maintenance**: Additional code to maintain and test
3. **Thread Safety**: Requires careful locking in registry operations
4. **Startup Overhead**: Slight delay on worker startup (< 100ms)

### Performance Impact

**Expected Overhead**:
- CPU: < 1% total overhead (idle + active requests)
- Memory: < 1MB for registries and server state
- Network: Negligible (localhost only by default)
- Task execution: No impact (background thread)

**Mitigation**:
- Caching: Cache worker metrics for 1 second
- Lazy queries: Query podman API only when needed
- Background thread: Server doesn't block task execution

### Security Considerations

1. **Default Security**: localhost-only binding prevents network exposure
2. **Future Authentication**: Token auth can be added for network exposure
3. **Read-Only**: No endpoints to modify worker state
4. **Data Sanitization**: Log endpoints may need sensitive data filtering (future)

### Operational Considerations

1. **Configuration**: Simple config keys enable/disable monitoring
2. **Port Conflicts**: Default port 8080 may conflict (configurable)
3. **Monitoring Tools**: Can integrate with Prometheus, Grafana, etc.
4. **Troubleshooting**: Server logs help debug monitoring issues

## Alternatives Considered

### Alternative 1: External Monitoring Tool (Prometheus Exporter)
**Approach**: Export metrics via Prometheus exporter, separate monitoring infrastructure
**Rejected Because**:
- Requires external Prometheus setup
- Doesn't provide task/container details (only metrics)
- More complex deployment

### Alternative 2: Log File-Based Monitoring
**Approach**: Parse log files or use file watchers for status
**Rejected Because**:
- No real-time visibility
- Harder to query task/container status
- Doesn't provide REST API for integration

### Alternative 3: Syslog/Structured Logging
**Approach**: Emit structured logs, parse externally
**Rejected Because**:
- Requires external log aggregation
- No real-time query capability
- More complex operational setup

### Alternative 4: GraphQL API
**Approach**: Use GraphQL for flexible queries
**Rejected Because**:
- Requires GraphQL library (dependency)
- Overkill for simple status queries
- More complex to implement

## Work Items for Implementation Lead

### Phase 2.3: Operational Monitoring Implementation

**1. Create Monitoring Module** (`koji_adjutant/monitoring/`)
- [ ] `__init__.py`: Module exports
- [ ] `server.py`: HTTP server implementation (`MonitoringServer` class)
- [ ] `registry.py`: Container and task registry (`ContainerRegistry`, `TaskRegistry`)
- [ ] `endpoints.py`: Endpoint handlers (status, containers, tasks, logs)

**2. HTTP Server Implementation**
- [ ] `MonitoringServer` class using `http.server.ThreadingHTTPServer`
- [ ] Request routing (path-based routing)
- [ ] JSON response serialization
- [ ] Error handling (404, 500, 503)
- [ ] Graceful shutdown support

**3. Container Registry**
- [ ] `ContainerRegistry` class with thread-safe operations
- [ ] `register()`: Register container with metadata
- [ ] `unregister()`: Remove container from registry
- [ ] `get_all()`: List all containers
- [ ] `get()`: Get container by ID
- [ ] Cleanup on startup (reconstruct from podman)

**4. Task Registry**
- [ ] `TaskRegistry` class with thread-safe operations
- [ ] `register_task()`: Register task with metadata
- [ ] `update_task_status()`: Update task status
- [ ] `update_task_progress()`: Update task progress
- [ ] `get_all()`: List all tasks
- [ ] `get()`: Get task by ID

**5. API Endpoints**
- [ ] `GET /api/v1/status`: Worker status
- [ ] `GET /api/v1/containers`: List containers
- [ ] `GET /api/v1/containers/<id>`: Container details
- [ ] `GET /api/v1/tasks`: List tasks
- [ ] `GET /api/v1/tasks/<id>`: Task details
- [ ] `GET /api/v1/tasks/<id>/logs`: Task logs
- [ ] `GET /api/v1/metrics`: Prometheus metrics (optional)
- [ ] `GET /`: HTML dashboard (optional)

**6. Integration with PodmanManager**
- [ ] Register containers in `create()` method
- [ ] Update container status in `start()` method
- [ ] Unregister containers in `remove()` method
- [ ] Handle registry unavailable gracefully (no crash)

**7. Integration with Task Adapters**
- [ ] Register tasks in `BuildArchAdapter.build()`
- [ ] Update task progress in task handlers
- [ ] Update task status on completion
- [ ] Handle registry unavailable gracefully

**8. Integration with kojid.py**
- [ ] Start monitoring server in main loop
- [ ] Stop server on shutdown
- [ ] Config parsing for monitoring settings
- [ ] Worker ID detection

**9. Configuration**
- [ ] `adjutant_monitoring_enabled`: Enable/disable monitoring (default: false)
- [ ] `adjutant_monitoring_bind`: Bind address (default: "127.0.0.1:8080")
- [ ] `adjutant_monitoring_container_history_ttl`: Container retention (default: 3600)
- [ ] `adjutant_monitoring_task_history_ttl`: Task retention (default: 3600)

**10. Unit Tests**
- [ ] Test registry thread safety
- [ ] Test endpoint handlers
- [ ] Test error handling
- [ ] Test graceful shutdown

**11. Integration Tests**
- [ ] Test server startup/shutdown
- [ ] Test container registration/unregistration
- [ ] Test task registration/completion
- [ ] Test endpoint responses

**12. Documentation**
- [ ] API endpoint documentation
- [ ] Configuration guide
- [ ] Monitoring dashboard guide
- [ ] Troubleshooting guide

## References

- ADR 0001: Container Lifecycle and Interface Boundaries
- ADR 0002: Container Image Bootstrap and Security
- ADR 0004: Production Buildroot Container Images
- Phase 2 Roadmap: `docs/planning/phase2-roadmap.md`
- Python `http.server` documentation: https://docs.python.org/3/library/http.server.html

---

**Decision Status**: Proposed for Phase 2.3 implementation.

**Next Steps**:
1. Review and approve ADR
2. Implementation Lead creates monitoring module structure
3. Implement HTTP server and registries
4. Integrate with PodmanManager and task adapters
5. Add configuration support
6. Write tests and documentation
7. Test with real worker deployment
