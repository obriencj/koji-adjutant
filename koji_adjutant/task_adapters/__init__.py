"""Task adapters translate Koji tasks into container executions.

Boundary rules:
- Adapters depend only on `koji_adjutant.container.interface.ContainerManager`.
- No Podman API imports here; runtime specifics are injected via the interface.
- Each adapter constructs a `ContainerSpec` (image, command, env, mounts) and
  delegates execution to the container manager, wiring logs to Koji.
"""

from .base import BaseTaskAdapter, KojiLogSink, TaskContext, default_mounts
from .buildarch import BuildArchAdapter
from .createrepo import CreaterepoAdapter
from .logging import FileKojiLogSink

__all__ = [
    "BaseTaskAdapter",
    "BuildArchAdapter",
    "CreaterepoAdapter",
    "FileKojiLogSink",
    "KojiLogSink",
    "TaskContext",
    "default_mounts",
]
