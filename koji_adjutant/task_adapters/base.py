from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Protocol, Sequence

from ..container.interface import ContainerManager, ContainerSpec, VolumeMount


class KojiLogSink(Protocol):
    def write_stdout(self, data: bytes) -> None:  # pragma: no cover - protocol
        ...

    def write_stderr(self, data: bytes) -> None:  # pragma: no cover - protocol
        ...


@dataclass(frozen=True)
class TaskContext:
    task_id: int
    work_dir: Path
    koji_mount_root: Path  # typically /mnt/koji
    environment: Mapping[str, str]


class BaseTaskAdapter(Protocol):
    """Adapter boundary for executing a Koji task inside a container.

    Implementations must:
    - Build a `ContainerSpec` from `TaskContext` and task-specific data.
    - Use only the `ContainerManager` interface for runtime operations.
    - Stream logs to Koji via provided sink.
    """

    def build_spec(self, ctx: TaskContext) -> ContainerSpec:  # pragma: no cover - protocol
        ...

    def run(self, ctx: TaskContext, manager: ContainerManager, sink: KojiLogSink) -> int:  # pragma: no cover - protocol
        ...


def default_mounts(ctx: TaskContext, extra: Sequence[VolumeMount] | None = None) -> Sequence[VolumeMount]:
    mounts: list[VolumeMount] = [
        VolumeMount(source=ctx.koji_mount_root, target=Path("/mnt/koji"), read_only=False, selinux_label="Z"),
        VolumeMount(source=ctx.work_dir, target=Path("/workspace"), read_only=False, selinux_label="Z"),
    ]
    if extra:
        mounts.extend(extra)
    return tuple(mounts)
