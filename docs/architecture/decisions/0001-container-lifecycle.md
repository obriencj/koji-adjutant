---
title: "ADR 0001: Container Lifecycle, Mounts, and Manager Boundaries"
status: Accepted
date: 2025-10-30
deciders: Systems Architect, Implementation Lead, Container Engineer
---

## Context

Koji-Adjutant replaces mock-based chroots with Podman containers while preserving Koji hub compatibility and task semantics. We need a clear container lifecycle, mount strategy, and clean interfaces so task handlers can execute in containers without depending on Podman specifics.

## Decision

We introduce a runtime-agnostic `ContainerManager` interface with a Podman-backed implementation `PodmanManager`. Task handlers interact only with `ContainerManager`. One ephemeral container is created per task. Mounts are explicit and minimal, aligned with Koji artifact layout and koji-boxed storage.

### Lifecycle (per task)

1) Resolve image: `ensure_image_available(image)` ensures the image exists (pull if needed).
2) Create: `create(spec)` with fully resolved `ContainerSpec` (command, env, mounts, user, workdir, resources).
3) Start: `start(handle)` immediately after creation.
4) Stream logs: `stream_logs(handle, sink, follow=True)` begins as soon as the container starts.
5) Wait: `wait(handle)` blocks until process exit and returns exit code.
6) Cleanup: `remove(handle)` always runs; forced when container is stuck or on failure paths.

All steps are orchestrated by `ContainerManager.run(spec, sink, attach_streams=True)` as a convenience that guarantees cleanup on exceptions. Task handlers may use low-level steps when needed (e.g., pre-start setup) but must respect the same cleanup guarantees.

Timeouts/backoff (Phase 1 defaults): controlled by `adjutant_container_timeouts` (see Config). Default: pull=300s, start=60s, stop_grace=20s.

### Mount Strategy

Mounts are explicit `VolumeMount` entries inside `ContainerSpec`:

- Build artifacts: host `/mnt/koji` mounted read-write into container at `/mnt/koji` with SELinux label `:Z` by default (configurable via `adjutant_container_mounts`). Use `:z` only when multiple containers must concurrently share a volume with different labels; Phase 1 default is `:Z`.
- Read-only inputs (srpm, repo metadata, config): mounted read-only.
- Temporary workspace: standardized host path `/mnt/koji/work/<task_id>` mounted read-write to container path `/work/<task_id>`. The task adapter creates and cleans up this directory.
- Optional read-only repo config: e.g., mount host `/etc/yum.repos.d/koji.repo` to container `/etc/yum.repos.d/koji.repo:ro` when required.
- Keytabs/creds: mounted read-only only when absolutely required and scoped to the task; prefer environment-based auth via existing orch patterns.
- Minimal host exposure: only paths required by the task are mounted; no broad host filesystem access.

SELinux: Respect host SELinux; the `selinux_label` field maps to Podman `:Z`/`:z` flags. Default for `/mnt/koji` is `:Z` via config; adapters may override for specialized mounts.

User/Group: Prefer rootless execution via `user_id`/`group_id`. If not feasible (tooling requires root), run as root but ensure mount ownership/permissions permit write access to `/mnt/koji` and `/work/<task_id>`. Rationale: maximize isolation and least-privilege; fallback preserves build compatibility.

Networking: Enabled by default in Phase 1. Future knob `adjutant_network_enabled` allows disabling network when policy permits.

Resource Limits: Exposed via `ResourceLimits` and enforced by the runtime. Defaults are unlimited; the worker configuration may set policy defaults.

### Failure Handling and Cleanup

- All lifecycle operations must be exception-safe and idempotent where possible.
- `run()` guarantees `remove()` in a finally block when `remove_after_exit=True`.
- If `start()` fails, attempt `remove()` best-effort.
- Log streaming must not mask container exit errors; collect exit code and surfaces it.
- On worker shutdown, containers are signaled to stop gracefully, waiting `stop_grace` seconds, then force-removed. Containers carry labels `io.koji.adjutant.task_id` and `io.koji.adjutant.worker_id` for enumeration and GC.

### Interface Boundaries

- `koji_adjutant.container.interface` defines `ContainerManager`, `ContainerSpec`, `VolumeMount`, `ResourceLimits`, and logging sink protocol.
- `koji_adjutant.container.podman_manager` implements `ContainerManager` using Podman Python API only (no shelling out). All Podman types are confined to this module.
- `koji_adjutant.task_adapters.*` build `ContainerSpec` from Koji task context and call the interface. They never import Podman-specific modules.

Configuration flows into task adapters (which compute mounts/env/command) and into the Podman manager (which handles runtime policy like pull policy, timeouts, and low-level flags). Podman specifics remain isolated to `koji_adjutant/container/podman_manager.py`; adapters never import Podman.

### Logging

Container stdout/stderr are streamed non-blockingly to a `LogSink` connected to Koji logs. Streaming begins after `start()` and continues until exit. A copy is persisted at `/mnt/koji/logs/<task_id>/container.log`. Bounded buffering applies; on overflow, oldest data is dropped (drop-oldest policy).

### Observability

Minimal metrics in Phase 1: image pull duration, container start/stop timings, and exit code counts. Metric sinks are TBD; emit via the worker’s metrics interface when available.

### Rationale

This separation preserves hub compatibility, reduces coupling, and enables testing task adapters against an in-memory or stub `ContainerManager`. It also allows future runtime swaps if needed.

### Consequences

- Initial work to wire `PodmanManager` and adapters.
- Clear separation simplifies unit testing and future enhancements (e.g., network policies, cgroups tuning).
- Per-task containers match mock isolation with modern container ergonomics.

## Alternatives Considered

- Using subprocess for `podman` CLI: rejected due to poorer control, error handling, and portability compared to Podman Python API.
- Long-lived per-builder containers: rejected; conflicts with isolation and resource cleanup expectations matching mock.

## Phase 1 Configuration Keys (defaults)

- `adjutant_task_image_default = registry/almalinux:10`
- `adjutant_image_pull_policy = if-not-present`  (values: `if-not-present|always|never`)
- `adjutant_container_mounts = /mnt/koji:/mnt/koji:rw:Z`
- `adjutant_network_enabled = true`
- `adjutant_container_labels = worker_id=<id>`
- `adjutant_container_timeouts = pull=300,start=60,stop_grace=20`

## Work Items

- Implement `PodmanManager` with create/start/stream/wait/remove and image ensure. Respect pull policy and timeouts.
- Define base task adapter(s) to translate Koji tasks into `ContainerSpec`.
- Wire log streaming to Koji log upload and file persistence under `/mnt/koji/logs/<task_id>/`.

## Consequences and Notes

- cgroups v2 and rootless constraints may limit certain kernel features; evaluate per-task needs.
- Storage driver considerations (e.g., overlayfs) may affect SELinux labeling and performance; document operations guidance separately.
