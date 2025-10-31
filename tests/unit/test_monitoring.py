"""Unit tests for monitoring registries."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest

from koji_adjutant.monitoring.registry import ContainerInfo, ContainerRegistry, TaskInfo, TaskRegistry


class TestContainerRegistry:
    """Test ContainerRegistry thread-safe operations."""

    def test_register_and_get(self):
        """Test basic register and get operations."""
        registry = ContainerRegistry()
        registry.register(
            container_id="test-container-1",
            task_id=12345,
            image="test/image:latest",
            spec={"image": "test/image:latest", "command": ["/bin/sh"]},
        )

        container = registry.get("test-container-1")
        assert container is not None
        assert container.container_id == "test-container-1"
        assert container.task_id == 12345
        assert container.image == "test/image:latest"
        assert container.status == "created"

    def test_unregister(self):
        """Test unregister operation."""
        registry = ContainerRegistry()
        registry.register(
            container_id="test-container-1",
            task_id=12345,
            image="test/image:latest",
            spec={},
        )

        registry.unregister("test-container-1")
        container = registry.get("test-container-1")
        assert container is not None
        assert container.status == "removed"
        assert container.finished_at is not None

    def test_update_status(self):
        """Test status update."""
        registry = ContainerRegistry()
        registry.register(
            container_id="test-container-1",
            task_id=12345,
            image="test/image:latest",
            spec={},
        )

        registry.update_status("test-container-1", "running")
        container = registry.get("test-container-1")
        assert container.status == "running"

    def test_list_containers(self):
        """Test list operations."""
        registry = ContainerRegistry()
        registry.register(
            container_id="container-1",
            task_id=1,
            image="test/image:latest",
            spec={},
        )
        registry.register(
            container_id="container-2",
            task_id=2,
            image="test/image:latest",
            spec={},
        )

        containers = registry.list_containers(active_only=True)
        assert len(containers) == 2

        registry.unregister("container-1")
        containers = registry.list_containers(active_only=True)
        assert len(containers) == 1
        assert containers[0].container_id == "container-2"

    def test_cleanup_old_entries(self):
        """Test TTL-based cleanup."""
        registry = ContainerRegistry(history_ttl=1)  # 1 second TTL
        registry.register(
            container_id="container-1",
            task_id=1,
            image="test/image:latest",
            spec={},
        )
        registry.unregister("container-1")

        # Should still exist
        assert registry.get("container-1") is not None

        # Wait for TTL to expire
        time.sleep(1.5)

        # Cleanup should remove it
        removed = registry.cleanup_old_entries()
        assert removed == 1
        assert registry.get("container-1") is None

    def test_thread_safety(self):
        """Test concurrent access thread safety."""
        registry = ContainerRegistry()
        results = []

        def register_containers():
            for i in range(100):
                registry.register(
                    container_id=f"container-{i}",
                    task_id=i,
                    image="test/image:latest",
                    spec={},
                )

        def list_containers():
            for _ in range(100):
                containers = registry.list_containers()
                results.append(len(containers))

        threads = []
        for _ in range(10):
            t = threading.Thread(target=register_containers)
            threads.append(t)
            t.start()

        list_thread = threading.Thread(target=list_containers)
        list_thread.start()
        threads.append(list_thread)

        for t in threads:
            t.join()

        # Should have registered all containers
        containers = registry.list_containers()
        assert len(containers) == 1000  # 10 threads * 100 containers


class TestTaskRegistry:
    """Test TaskRegistry thread-safe operations."""

    def test_register_task_and_get(self):
        """Test basic register and get operations."""
        registry = TaskRegistry()
        registry.register_task(
            task_id=12345,
            task_type="buildArch",
            arch="x86_64",
            tag="el10-build",
            srpm="test-1.0-1.src.rpm",
        )

        task = registry.get(12345)
        assert task is not None
        assert task.task_id == 12345
        assert task.task_type == "buildArch"
        assert task.arch == "x86_64"
        assert task.status == "running"

    def test_update_task_status(self):
        """Test status update."""
        registry = TaskRegistry()
        registry.register_task(
            task_id=12345,
            task_type="buildArch",
        )

        registry.update_task_status(12345, "completed")
        task = registry.get(12345)
        assert task.status == "completed"
        assert task.finished_at is not None

    def test_update_task_progress(self):
        """Test progress update."""
        registry = TaskRegistry()
        registry.register_task(
            task_id=12345,
            task_type="buildArch",
        )

        registry.update_task_progress(12345, {"stage": "buildroot_init", "percent": 50})
        task = registry.get(12345)
        assert task.progress == {"stage": "buildroot_init", "percent": 50}

    def test_update_container_id(self):
        """Test container ID update."""
        registry = TaskRegistry()
        registry.register_task(
            task_id=12345,
            task_type="buildArch",
        )

        registry.update_container_id(12345, "container-abc123")
        task = registry.get(12345)
        assert task.container_id == "container-abc123"

    def test_list_tasks(self):
        """Test list operations."""
        registry = TaskRegistry()
        registry.register_task(task_id=1, task_type="buildArch")
        registry.register_task(task_id=2, task_type="createrepo")

        tasks = registry.list_tasks(active_only=True)
        assert len(tasks) == 2

        registry.update_task_status(1, "completed")
        tasks = registry.list_tasks(active_only=True)
        assert len(tasks) == 1
        assert tasks[0].task_id == 2

    def test_cleanup_old_entries(self):
        """Test TTL-based cleanup."""
        registry = TaskRegistry(history_ttl=1)  # 1 second TTL
        registry.register_task(task_id=1, task_type="buildArch")
        registry.update_task_status(1, "completed")

        # Should still exist
        assert registry.get(1) is not None

        # Wait for TTL to expire
        time.sleep(1.5)

        # Cleanup should remove it
        removed = registry.cleanup_old_entries()
        assert removed == 1
        assert registry.get(1) is None

    def test_thread_safety(self):
        """Test concurrent access thread safety."""
        registry = TaskRegistry()
        results = []

        def register_tasks():
            for i in range(100):
                registry.register_task(
                    task_id=i,
                    task_type="buildArch",
                )

        def list_tasks():
            for _ in range(100):
                tasks = registry.list_tasks()
                results.append(len(tasks))

        threads = []
        for _ in range(10):
            t = threading.Thread(target=register_tasks)
            threads.append(t)
            t.start()

        list_thread = threading.Thread(target=list_tasks)
        list_thread.start()
        threads.append(list_thread)

        for t in threads:
            t.join()

        # Should have registered all tasks
        tasks = registry.list_tasks()
        assert len(tasks) == 1000  # 10 threads * 100 tasks