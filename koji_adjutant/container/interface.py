from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Protocol, Sequence


@dataclass(frozen=True)
class VolumeMount:
    """Host volume to mount into the container.

    - source: absolute host path
    - target: container path
    - read_only: mount as read-only when True
    - selinux_label: optional label suffix (e.g., "Z" or "z") if needed
    """

    source: Path
    target: Path
    read_only: bool = False
    selinux_label: Optional[str] = None


@dataclass(frozen=True)
class ResourceLimits:
    """Optional resource constraints for a container runtime."""

    memory_bytes: Optional[int] = None
    cpu_quota: Optional[int] = None
    cpus: Optional[float] = None
    pids_limit: Optional[int] = None
    cpuset_cpus: Optional[str] = None


@dataclass(frozen=True)
class ContainerSpec:
    """Complete specification for launching a task container."""

    image: str
    command: Sequence[str]
    environment: Dict[str, str]
    workdir: Optional[Path] = None
    mounts: Sequence[VolumeMount] = ()
    user_id: Optional[int] = None
    group_id: Optional[int] = None
    network_enabled: bool = True
    resource_limits: Optional[ResourceLimits] = None
    remove_after_exit: bool = True


@dataclass(frozen=True)
class ContainerHandle:
    """Opaque reference to a created container instance."""

    container_id: str


@dataclass(frozen=True)
class ContainerRunResult:
    """Outcome of a containerized task execution."""

    handle: ContainerHandle
    exit_code: int
    started_at: datetime
    finished_at: datetime


class LogSink(Protocol):
    """Destination for container stdout/stderr streams."""

    def write_stdout(self, data: bytes) -> None:  # pragma: no cover - protocol
        ...

    def write_stderr(self, data: bytes) -> None:  # pragma: no cover - protocol
        ...


class ContainerManager(Protocol):
    """Abstract container runtime used by task adapters.

    Implementations must provide robust cleanup and ensure log streaming
    continues until process termination. No hub-specific behavior here.
    """

    def ensure_image_available(self, image: str) -> None:  # pragma: no cover - protocol
        """Pull or verify availability of the given image locally."""
        ...

    def create(self, spec: ContainerSpec) -> ContainerHandle:  # pragma: no cover - protocol
        """Create a container for the given spec without starting it."""
        ...

    def start(self, handle: ContainerHandle) -> None:  # pragma: no cover - protocol
        """Start a previously created container."""
        ...

    def stream_logs(
        self,
        handle: ContainerHandle,
        sink: LogSink,
        follow: bool = True,
    ) -> None:  # pragma: no cover - protocol
        """Stream container logs to the provided sink until completion when follow=True."""
        ...

    def wait(self, handle: ContainerHandle) -> int:  # pragma: no cover - protocol
        """Block until container exits and return exit code."""
        ...

    def remove(self, handle: ContainerHandle, force: bool = False) -> None:  # pragma: no cover - protocol
        """Remove container and associated resources."""
        ...

    def exec(
        self,
        handle: ContainerHandle,
        command: Sequence[str],
        sink: LogSink,
        environment: Optional[Dict[str, str]] = None,
    ) -> int:  # pragma: no cover - protocol
        """Execute command in running container.
        
        Args:
            handle: Container to execute in
            command: Command and arguments to execute
            sink: Log sink for stdout/stderr
            environment: Optional environment variables
            
        Returns:
            Exit code from command execution
            
        Raises:
            ContainerError: If execution fails
        """
        ...

    def copy_to(
        self,
        handle: ContainerHandle,
        src_path: Path,
        dest_path: str,
    ) -> None:  # pragma: no cover - protocol
        """Copy file from host to container at specified path.
        
        Args:
            handle: Container to copy to
            src_path: Host filesystem path
            dest_path: Container filesystem path (absolute)
            
        Raises:
            ContainerError: If copy fails
        """
        ...

    def run(
        self,
        spec: ContainerSpec,
        sink: LogSink,
        attach_streams: bool = True,
    ) -> ContainerRunResult:  # pragma: no cover - protocol
        """High-level helper: create → start → stream → wait → (optional remove)."""
        ...


class ContainerError(RuntimeError):
    """Raised for container runtime failures that should fail the task."""

    def __init__(self, message: str, *, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class InMemoryLogSink:
    """Simple bytes-accumulating sink useful for tests and bootstrap wiring."""

    def __init__(self) -> None:
        self._stdout: bytearray = bytearray()
        self._stderr: bytearray = bytearray()

    def write_stdout(self, data: bytes) -> None:
        self._stdout.extend(data)

    def write_stderr(self, data: bytes) -> None:
        self._stderr.extend(data)

    @property
    def stdout(self) -> bytes:
        return bytes(self._stdout)

    @property
    def stderr(self) -> bytes:
        return bytes(self._stderr)
