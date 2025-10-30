from __future__ import annotations

import io
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from time import monotonic, sleep
from typing import Dict, Iterable, Optional, Sequence

from .interface import (
    ContainerError,
    ContainerHandle,
    ContainerManager,
    ContainerRunResult,
    ContainerSpec,
    LogSink,
)

# Podman Python API (podman-py)
try:  # pragma: no cover - import side effect
    from podman import PodmanClient
    from podman.errors import APIError, NotFound
except Exception:  # pragma: no cover - allow tests to stub
    PodmanClient = None  # type: ignore[assignment]
    APIError = Exception  # type: ignore[assignment]
    NotFound = Exception  # type: ignore[assignment]

from .. import config as adj_config


class PodmanManager(ContainerManager):
    """Podman-backed implementation of ContainerManager.

    Boundary rules:
    - Only this module talks to Podman Python APIs.
    - Upstream callers depend only on `ContainerManager` abstractions.
    - No Koji-specific logic: translation from tasks to `ContainerSpec` lives in task_adapters.
    """

    def __init__(
        self,
        *,
        pull_always: Optional[bool] = None,
        network_default: Optional[bool] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        # Policy defaults from config when not provided
        policy = (adj_config.adjutant_image_pull_policy() or "if-not-present").lower()
        self._pull_policy = policy  # values: always|if-not-present|never
        if pull_always is not None:
            self._pull_policy = "always" if pull_always else "if-not-present"

        self._network_default = (
            adj_config.adjutant_network_enabled() if network_default is None else network_default
        )
        # Lazy-init Podman client on first use to make tests lighter
        self._client = None  # type: ignore[var-annotated]
        # Timeouts
        t = adj_config.adjutant_container_timeouts()
        self._timeout_pull_s = int(t.get("pull", 300))
        self._timeout_start_s = int(t.get("start", 60))
        self._timeout_stop_grace_s = int(t.get("stop_grace", 20))
        # Labels base
        self._base_labels: Dict[str, str] = dict(adj_config.adjutant_container_labels() or {})
        if worker_id:
            self._base_labels.setdefault("io.koji.adjutant.worker_id", worker_id)

    # --- public interface ---

    def ensure_image_available(self, image: str) -> None:
        self._ensure_client()
        try:
            has_local = self._has_image(image)
        except APIError as exc:  # pragma: no cover - pass through as ContainerError
            raise ContainerError(f"failed to check image {image}", cause=exc)

        if self._pull_policy == "never":
            if not has_local:
                raise ContainerError(f"image not present locally and pull policy is 'never': {image}")
            return

        if self._pull_policy == "always" or not has_local:
            self._pull_image(image)

    def create(self, spec: ContainerSpec) -> ContainerHandle:
        self._ensure_client()
        try:
            container_id = self._create_container(spec)
        except APIError as exc:
            raise ContainerError("failed to create container", cause=exc)
        return ContainerHandle(container_id=container_id)

    def start(self, handle: ContainerHandle) -> None:
        self._ensure_client()
        try:
            self._start_container(handle.container_id)
        except APIError as exc:
            # Best-effort cleanup is handled by caller
            raise ContainerError("failed to start container", cause=exc)

    def stream_logs(self, handle: ContainerHandle, sink: LogSink, follow: bool = True) -> None:
        self._ensure_client()
        # Non-blocking stream: run in background, drop-oldest on pressure
        self._stream_container_logs(handle.container_id, sink, follow=follow)

    def wait(self, handle: ContainerHandle) -> int:
        self._ensure_client()
        try:
            return self._wait_container_exit_code(handle.container_id)
        except APIError as exc:
            raise ContainerError("failed waiting for container", cause=exc)

    def remove(self, handle: ContainerHandle, force: bool = False) -> None:
        self._ensure_client()
        try:
            self._remove_container(handle.container_id, force=force)
        except NotFound:
            return
        except APIError as exc:
            if force:
                raise ContainerError("failed to remove container (forced)", cause=exc)
            raise ContainerError("failed to remove container", cause=exc)

    def exec(
        self,
        handle: ContainerHandle,
        command: Sequence[str],
        sink: LogSink,
        environment: Optional[Dict[str, str]] = None,
    ) -> int:
        """Execute command in running container via podman exec."""
        self._ensure_client()
        try:
            container = self._client.containers.get(handle.container_id)
        except NotFound as exc:
            raise ContainerError(f"container not found: {handle.container_id}", cause=exc)
        except APIError as exc:
            raise ContainerError("failed to get container for exec", cause=exc)

        try:
            # Podman exec with streaming output
            # exec_run with stream=True returns (exit_code, generator)
            exec_result = container.exec_run(
                cmd=list(command),
                environment=environment or {},
                stream=True,
                demux=True,  # Separate stdout/stderr
            )

            # exec_result is (exit_code, generator) - unpack it
            if isinstance(exec_result, tuple) and len(exec_result) == 2:
                exit_code_hint, exec_gen = exec_result
            else:
                # Fallback: treat as generator directly
                exec_gen = exec_result
                exit_code_hint = None

            # Stream output to sink
            # Generator yields (stdout_bytes, stderr_bytes) tuples or raw bytes
            for chunk in exec_gen:
                if chunk is None:
                    continue
                # Handle both tuple (stdout, stderr) and bytes formats
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

            # Get exit code
            # If we got exit_code_hint from the streaming call, use it if valid
            if exit_code_hint is not None:
                return int(exit_code_hint) if exit_code_hint else 0

            # Otherwise, exec again to get exit code (podman-py doesn't always return it reliably)
            exit_result = container.exec_run(
                cmd=list(command),
                environment=environment or {},
                stream=False,
            )

            # Handle both tuple (exit_code, output) and direct exit_code
            if isinstance(exit_result, tuple):
                return int(exit_result[0]) if exit_result[0] is not None else 0
            else:
                return int(exit_result) if exit_result is not None else 0

        except APIError as exc:
            raise ContainerError(f"failed to execute command in container: {command}", cause=exc)

    def copy_to(
        self,
        handle: ContainerHandle,
        src_path: Path,
        dest_path: str,
    ) -> None:
        """Copy file to container using podman put_archive."""
        self._ensure_client()
        try:
            container = self._client.containers.get(handle.container_id)
        except NotFound as exc:
            raise ContainerError(f"container not found: {handle.container_id}", cause=exc)
        except APIError as exc:
            raise ContainerError("failed to get container for copy", cause=exc)

        # Validate source path exists
        src_path = Path(src_path)
        if not src_path.exists():
            raise ContainerError(f"source path does not exist: {src_path}")

        if not src_path.is_file():
            raise ContainerError(f"source path is not a file: {src_path}")

        try:
            # Create tar archive of single file
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                # Add file with basename as arcname, preserving permissions
                tar.add(src_path, arcname=os.path.basename(dest_path), recursive=False)
            tar_stream.seek(0)

            # Put archive in container at parent directory
            dest_dir = os.path.dirname(dest_path)
            container.put_archive(path=dest_dir, data=tar_stream.read())

        except APIError as exc:
            raise ContainerError(f"failed to copy file to container: {src_path} -> {dest_path}", cause=exc)
        except Exception as exc:
            raise ContainerError(f"failed to create archive for copy: {src_path}", cause=exc)

    def run(self, spec: ContainerSpec, sink: LogSink, attach_streams: bool = True) -> ContainerRunResult:
        self.ensure_image_available(spec.image)
        handle = self.create(spec)
        started_at = datetime.now(timezone.utc)
        try:
            self.start(handle)
            if attach_streams:
                # Start log following asynchronously; waiting is handled by wait()
                self.stream_logs(handle, sink, follow=True)
            exit_code = self.wait(handle)
        except BaseException as exc:  # ensure cleanup
            try:
                self.remove(handle, force=True)
            finally:
                raise ContainerError("container run failed", cause=exc)
        else:
            try:
                if spec.remove_after_exit:
                    self.remove(handle)
            finally:
                finished_at = datetime.now(timezone.utc)
        return ContainerRunResult(
            handle=handle,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished_at,
        )

    # --- private helpers (placeholders until wired with Podman API) ---

    def _ensure_client(self) -> None:
        if self._client is None:
            if PodmanClient is None:
                # In test environments without podman, allow stubbing
                raise ContainerError("Podman client not available")
            self._client = PodmanClient()

    def _has_image(self, image: str) -> bool:
        assert self._client is not None
        try:
            self._client.images.get(image)
            return True
        except NotFound:
            return False

    def _pull_image(self, image: str) -> None:
        assert self._client is not None
        deadline = monotonic() + self._timeout_pull_s
        last_exc: Optional[BaseException] = None
        while True:
            try:
                # Podman-py mirrors docker API: returns generator or image object
                self._client.images.pull(image)
                return
            except APIError as exc:
                last_exc = exc
            if monotonic() >= deadline:
                raise ContainerError(f"timeout pulling image: {image}", cause=last_exc)
            sleep(1.0)

    def _create_container(self, spec: ContainerSpec) -> str:
        assert self._client is not None
        mounts = [
            {
                "Type": "bind",
                "Source": str(vm.source),
                "Destination": str(vm.target),
                "ReadOnly": bool(vm.read_only),
                # Options are used by podman to carry SELinux label flags
                "Options": self._mount_options(vm),
            }
            for vm in spec.mounts
        ]

        labels = dict(self._base_labels)
        # Task label inferred from environment if available
        maybe_task_id = spec.environment.get("KOJI_TASK_ID")
        if maybe_task_id:
            labels.setdefault("io.koji.adjutant.task_id", maybe_task_id)

        create_kwargs = {
            "image": spec.image,
            "command": list(spec.command),
            "environment": dict(spec.environment or {}),
            "working_dir": str(spec.workdir) if spec.workdir else None,
            "labels": labels,
            "tty": False,
            "stdin_open": False,
            # Podman-specific
            "mounts": mounts,
            # Note: network_disabled not supported by current podman-py, use network mode instead
        }

        # Handle network configuration
        # If network is disabled, use 'none' network mode (when podman-py supports it)
        # For now, skip network_disabled as it's not supported
        if not (spec.network_enabled if spec.network_enabled is not None else self._network_default):
            # Future: create_kwargs["network_mode"] = "none" when supported
            pass

        if spec.user_id is not None:
            if spec.group_id is not None:
                create_kwargs["user"] = f"{spec.user_id}:{spec.group_id}"
            else:
                create_kwargs["user"] = str(spec.user_id)

        # Resource limits (best-effort mapping)
        host_config = {}
        rl = spec.resource_limits
        if rl is not None:
            if rl.memory_bytes is not None:
                host_config["mem_limit"] = rl.memory_bytes
            if rl.cpus is not None:
                host_config["cpus"] = rl.cpus
            if rl.cpu_quota is not None:
                host_config["cpu_quota"] = rl.cpu_quota
            if rl.pids_limit is not None:
                host_config["pids_limit"] = rl.pids_limit
            if rl.cpuset_cpus is not None:
                host_config["cpuset_cpus"] = rl.cpuset_cpus
        if host_config:
            create_kwargs["host_config"] = host_config

        container = self._client.containers.create(**create_kwargs)
        return container.id

    def _start_container(self, container_id: str) -> None:
        assert self._client is not None
        container = self._client.containers.get(container_id)
        container.start()
        # Wait for running or exited with start timeout
        deadline = monotonic() + self._timeout_start_s
        while True:
            container.reload()
            status = getattr(container, "status", None)
            if status in ("running", "exited", "dead"):
                return
            if monotonic() >= deadline:
                raise ContainerError("timeout waiting for container to start")
            sleep(0.2)

    def _stream_container_logs(self, container_id: str, sink: LogSink, *, follow: bool) -> None:
        assert self._client is not None
        container = self._client.containers.get(container_id)

        stop_event = Event()
        # Bounded queue; on overflow, drop oldest
        queue: Queue[tuple[str, bytes]] = Queue(maxsize=1024)

        def reader() -> None:
            try:
                # Podman-py logs(stream=True, follow=follow, stdout=True, stderr=True)
                for chunk in container.logs(stream=True, follow=follow, stdout=True, stderr=True):
                    if stop_event.is_set():
                        break
                    # Docker/Podman multiplexing: chunk may be bytes; assume stdout/stderr combined
                    # We cannot distinguish reliably here; write to stdout by default
                    # Prefer simple policy: write to stdout; if API exposes split, adapt later.
                    if isinstance(chunk, bytes):
                        _enqueue(queue, ("stdout", chunk))
                    else:
                        data = bytes(chunk)  # defensive
                        _enqueue(queue, ("stdout", data))
            except Exception:
                # Swallow streaming errors; wait() will surface exit issues
                stop_event.set()

        def writer() -> None:
            while not stop_event.is_set() or not queue.empty():
                try:
                    stream, data = queue.get(timeout=0.2)
                except Exception:
                    continue
                try:
                    if stream == "stderr":
                        sink.write_stderr(data)
                    else:
                        sink.write_stdout(data)
                finally:
                    queue.task_done()

        def _enqueue(q: Queue[tuple[str, bytes]], item: tuple[str, bytes]) -> None:
            try:
                q.put_nowait(item)
            except Exception:
                # Drop oldest (spillover policy)
                try:
                    q.get_nowait()
                    q.task_done()
                except Exception:
                    pass
                try:
                    q.put_nowait(item)
                except Exception:
                    pass

        t_reader = Thread(target=reader, name=f"podman-log-reader-{container_id}", daemon=True)
        t_writer = Thread(target=writer, name=f"podman-log-writer-{container_id}", daemon=True)
        t_reader.start()
        t_writer.start()

    def _wait_container_exit_code(self, container_id: str) -> int:
        assert self._client is not None
        container = self._client.containers.get(container_id)
        # Podman-py wait() returns dict or status code depending on version
        result = container.wait()
        if isinstance(result, dict):
            code = int(result.get("StatusCode", 1))
        else:
            code = int(result)
        return code

    def _remove_container(self, container_id: str, *, force: bool) -> None:
        assert self._client is not None
        container = self._client.containers.get(container_id)
        try:
            container.remove(force=force)
        except APIError as exc:
            # Attempt a graceful stop then force remove if not already forced
            if not force:
                try:
                    try:
                        container.stop(timeout=self._timeout_stop_grace_s)
                    except Exception:
                        pass
                    container.remove(force=True)
                    return
                except Exception:
                    pass
            raise

    def _mount_options(self, vm) -> Iterable[str]:
        # Honor selinux label; default Z for /mnt/koji when unspecified
        opts = []
        if vm.selinux_label:
            opts.append(vm.selinux_label)
        else:
            try:
                if Path(vm.target) == Path("/mnt/koji"):
                    opts.append("Z")
            except Exception:
                pass
        return opts

    def __doc__(self) -> str:  # type: ignore[override]
        return (
            """Podman-backed implementation of ContainerManager.\n\n"
            "Example:\n\n"
            "    from koji_adjutant.container import ContainerSpec, InMemoryLogSink\n"
            "    from koji_adjutant.container.podman_manager import PodmanManager\n\n"
            "    spec = ContainerSpec(\n"
            "        image='registry/almalinux:10',\n"
            "        command=['/bin/echo', 'hello'],\n"
            "        environment={'KOJI_TASK_ID': '123'},\n"
            "    )\n"
            "    sink = InMemoryLogSink()\n"
            "    mgr = PodmanManager()\n"
            "    result = mgr.run(spec, sink)\n"
            "    print(result.exit_code)\n"
            """
        )
