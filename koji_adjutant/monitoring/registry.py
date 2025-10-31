"""Thread-safe registries for tracking containers and tasks."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ContainerInfo:
    """Container information stored in registry."""

    container_id: str
    task_id: Optional[int]
    image: str
    spec: Dict[str, Any]  # ContainerSpec serialized as dict
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str = "created"  # "created", "running", "exited", "removed"
    mounts: List[Dict[str, Any]] = field(default_factory=list)
    command: List[str] = field(default_factory=list)
    user: Optional[str] = None


@dataclass
class TaskInfo:
    """Task information stored in registry."""

    task_id: int
    task_type: str  # "buildArch", "createrepo", etc.
    status: str = "running"  # "running", "completed", "failed"
    arch: Optional[str] = None
    tag: Optional[str] = None
    srpm: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    container_id: Optional[str] = None
    log_path: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None


class ContainerRegistry:
    """Thread-safe container registry tracking active containers.

    Uses RLock for thread-safe operations and supports TTL-based cleanup
    of completed containers.
    """

    def __init__(self, history_ttl: int = 3600):
        """Initialize registry.

        Args:
            history_ttl: TTL in seconds for completed containers (default: 3600)
        """
        self._containers: Dict[str, ContainerInfo] = {}
        self._lock = threading.RLock()
        self._history_ttl = history_ttl

    def register(
        self,
        container_id: str,
        task_id: Optional[int],
        image: str,
        spec: Dict[str, Any],
        started_at: Optional[datetime] = None,
        mounts: Optional[List[Dict[str, Any]]] = None,
        command: Optional[List[str]] = None,
        user: Optional[str] = None,
    ) -> None:
        """Register a new container.

        Args:
            container_id: Container ID from podman
            task_id: Optional task ID associated with container
            image: Container image name
            spec: ContainerSpec serialized as dict
            started_at: Optional start time (defaults to now)
            mounts: Optional list of mount specs
            command: Optional command list
            user: Optional user string (e.g., "1000:1000")
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            self._containers[container_id] = ContainerInfo(
                container_id=container_id,
                task_id=task_id,
                image=image,
                spec=spec,
                created_at=now,
                started_at=started_at or now,
                status="created",
                mounts=mounts or [],
                command=command or [],
                user=user,
            )
            logger.debug("Registered container: %s (task_id=%s)", container_id, task_id)

    def unregister(self, container_id: str) -> None:
        """Unregister a container (marks as finished, keeps for TTL).

        Args:
            container_id: Container ID to unregister
        """
        with self._lock:
            if container_id in self._containers:
                container = self._containers[container_id]
                container.status = "removed"
                container.finished_at = datetime.now(timezone.utc)
                logger.debug("Unregistered container: %s", container_id)
                # Don't remove immediately - keep for history TTL
                # Cleanup happens in cleanup_old_entries()

    def update_status(self, container_id: str, status: str) -> None:
        """Update container status.

        Args:
            container_id: Container ID
            status: New status ("created", "running", "exited", "removed")
        """
        with self._lock:
            if container_id in self._containers:
                self._containers[container_id].status = status
                if status == "running" and not self._containers[container_id].started_at:
                    self._containers[container_id].started_at = datetime.now(timezone.utc)

    def get(self, container_id: str) -> Optional[ContainerInfo]:
        """Get container info by ID.

        Args:
            container_id: Container ID

        Returns:
            ContainerInfo if found, None otherwise
        """
        with self._lock:
            return self._containers.get(container_id)

    def list_containers(self, active_only: bool = False) -> List[ContainerInfo]:
        """List all containers.

        Args:
            active_only: If True, only return active containers (not removed)

        Returns:
            List of ContainerInfo objects
        """
        with self._lock:
            containers = list(self._containers.values())
            if active_only:
                containers = [c for c in containers if c.status != "removed"]
            return containers

    def cleanup_old_entries(self) -> int:
        """Remove entries older than TTL.

        Returns:
            Number of entries removed
        """
        with self._lock:
            now = time.time()
            removed = 0
            to_remove = []

            for container_id, container in self._containers.items():
                if container.finished_at:
                    # Check if finished container is older than TTL
                    finished_ts = container.finished_at.timestamp()
                    if now - finished_ts > self._history_ttl:
                        to_remove.append(container_id)

            for container_id in to_remove:
                del self._containers[container_id]
                removed += 1

            if removed > 0:
                logger.debug("Cleaned up %d old container entries", removed)

            return removed

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._containers.clear()


class TaskRegistry:
    """Thread-safe task registry tracking active tasks.

    Uses RLock for thread-safe operations and supports TTL-based cleanup
    of completed tasks.
    """

    def __init__(self, history_ttl: int = 3600):
        """Initialize registry.

        Args:
            history_ttl: TTL in seconds for completed tasks (default: 3600)
        """
        self._tasks: Dict[int, TaskInfo] = {}
        self._lock = threading.RLock()
        self._history_ttl = history_ttl

    def register_task(
        self,
        task_id: int,
        task_type: str,
        arch: Optional[str] = None,
        tag: Optional[str] = None,
        srpm: Optional[str] = None,
        container_id: Optional[str] = None,
        log_path: Optional[str] = None,
    ) -> None:
        """Register a new task.

        Args:
            task_id: Task ID
            task_type: Task type ("buildArch", "createrepo", etc.)
            arch: Optional architecture
            tag: Optional tag name
            srpm: Optional SRPM filename
            container_id: Optional container ID
            log_path: Optional log file path
        """
        with self._lock:
            self._tasks[task_id] = TaskInfo(
                task_id=task_id,
                task_type=task_type,
                status="running",
                arch=arch,
                tag=tag,
                srpm=srpm,
                started_at=datetime.now(timezone.utc),
                container_id=container_id,
                log_path=log_path,
            )
            logger.debug("Registered task: %d (type=%s)", task_id, task_type)

    def update_task_status(self, task_id: int, status: str) -> None:
        """Update task status.

        Args:
            task_id: Task ID
            status: New status ("running", "completed", "failed")
        """
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = status
                if status in ("completed", "failed"):
                    self._tasks[task_id].finished_at = datetime.now(timezone.utc)

    def update_task_progress(self, task_id: int, progress: Dict[str, Any]) -> None:
        """Update task progress.

        Args:
            task_id: Task ID
            progress: Progress dict with keys like "stage", "percent"
        """
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].progress = progress

    def update_container_id(self, task_id: int, container_id: str) -> None:
        """Update container ID for task.

        Args:
            task_id: Task ID
            container_id: Container ID
        """
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].container_id = container_id

    def get(self, task_id: int) -> Optional[TaskInfo]:
        """Get task info by ID.

        Args:
            task_id: Task ID

        Returns:
            TaskInfo if found, None otherwise
        """
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, active_only: bool = False) -> List[TaskInfo]:
        """List all tasks.

        Args:
            active_only: If True, only return active tasks (not completed/failed)

        Returns:
            List of TaskInfo objects
        """
        with self._lock:
            tasks = list(self._tasks.values())
            if active_only:
                tasks = [t for t in tasks if t.status == "running"]
            return tasks

    def cleanup_old_entries(self) -> int:
        """Remove entries older than TTL.

        Returns:
            Number of entries removed
        """
        with self._lock:
            now = time.time()
            removed = 0
            to_remove = []

            for task_id, task in self._tasks.items():
                if task.finished_at:
                    # Check if finished task is older than TTL
                    finished_ts = task.finished_at.timestamp()
                    if now - finished_ts > self._history_ttl:
                        to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                removed += 1

            if removed > 0:
                logger.debug("Cleaned up %d old task entries", removed)

            return removed

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._tasks.clear()