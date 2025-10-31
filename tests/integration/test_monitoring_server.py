"""Integration tests for monitoring HTTP server."""

from __future__ import annotations

import json
import socket
import threading
import time
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path

import pytest

from koji_adjutant.monitoring.registry import ContainerRegistry, TaskRegistry
from koji_adjutant.monitoring.server import MonitoringServer


class TestMonitoringServer:
    """Test monitoring HTTP server endpoints."""

    @pytest.fixture
    def server(self):
        """Create and start test server."""
        container_registry = ContainerRegistry()
        task_registry = TaskRegistry()
        server = MonitoringServer(
            bind_address="127.0.0.1",
            port=0,  # Use random port
            worker_id="test-worker",
            container_registry=container_registry,
            task_registry=task_registry,
        )

        # Start server in background thread
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        # Give server time to start
        time.sleep(0.2)

        yield server, container_registry, task_registry

        # Cleanup
        server.shutdown()

    def get_connection(self, server):
        """Get HTTP connection to server."""
        address, port = server.server_address
        return HTTPConnection(address, port)

    def test_status_endpoint(self, server):
        """Test GET /api/v1/status."""
        server_instance, _, _ = server
        conn = self.get_connection(server_instance)

        conn.request("GET", "/api/v1/status")
        response = conn.getresponse()

        assert response.status == 200
        assert response.getheader("Content-Type") == "application/json; charset=utf-8"

        data = json.loads(response.read())
        assert data["worker_id"] == "test-worker"
        assert "uptime_seconds" in data
        assert data["status"] == "healthy"
        assert "active_tasks" in data
        assert "containers_active" in data

        conn.close()

    def test_list_containers_empty(self, server):
        """Test GET /api/v1/containers with no containers."""
        server_instance, _, _ = server
        conn = self.get_connection(server_instance)

        conn.request("GET", "/api/v1/containers")
        response = conn.getresponse()

        assert response.status == 200
        data = json.loads(response.read())
        assert data["containers"] == []
        assert data["total"] == 0

        conn.close()

    def test_list_containers_with_data(self, server):
        """Test GET /api/v1/containers with containers."""
        server_instance, container_registry, _ = server

        # Register test container
        container_registry.register(
            container_id="test-container-1",
            task_id=12345,
            image="test/image:latest",
            spec={"image": "test/image:latest"},
            started_at=datetime.now(timezone.utc),
        )

        conn = self.get_connection(server_instance)
        conn.request("GET", "/api/v1/containers")
        response = conn.getresponse()

        assert response.status == 200
        data = json.loads(response.read())
        assert data["total"] == 1
        assert len(data["containers"]) == 1
        assert data["containers"][0]["container_id"] == "test-container-1"
        assert data["containers"][0]["task_id"] == 12345

        conn.close()

    def test_container_details(self, server):
        """Test GET /api/v1/containers/<id>."""
        server_instance, container_registry, _ = server

        # Register test container
        container_registry.register(
            container_id="test-container-1",
            task_id=12345,
            image="test/image:latest",
            spec={"image": "test/image:latest", "command": ["/bin/sh"]},
            mounts=[{"source": "/mnt/koji", "target": "/mnt/koji", "read_only": False}],
            command=["/bin/sh"],
        )

        conn = self.get_connection(server_instance)
        conn.request("GET", "/api/v1/containers/test-container-1")
        response = conn.getresponse()

        assert response.status == 200
        data = json.loads(response.read())
        assert data["container_id"] == "test-container-1"
        assert data["task_id"] == 12345
        assert data["image"] == "test/image:latest"
        assert "mounts" in data

        conn.close()

    def test_container_details_not_found(self, server):
        """Test GET /api/v1/containers/<id> with non-existent container."""
        server_instance, _, _ = server
        conn = self.get_connection(server_instance)

        conn.request("GET", "/api/v1/containers/nonexistent")
        response = conn.getresponse()

        assert response.status == 404
        data = json.loads(response.read())
        assert "error" in data

        conn.close()

    def test_list_tasks_empty(self, server):
        """Test GET /api/v1/tasks with no tasks."""
        server_instance, _, _ = server
        conn = self.get_connection(server_instance)

        conn.request("GET", "/api/v1/tasks")
        response = conn.getresponse()

        assert response.status == 200
        data = json.loads(response.read())
        assert data["tasks"] == []
        assert data["total"] == 0

        conn.close()

    def test_list_tasks_with_data(self, server):
        """Test GET /api/v1/tasks with tasks."""
        server_instance, _, task_registry = server

        # Register test task
        task_registry.register_task(
            task_id=12345,
            task_type="buildArch",
            arch="x86_64",
            tag="el10-build",
        )

        conn = self.get_connection(server_instance)
        conn.request("GET", "/api/v1/tasks")
        response = conn.getresponse()

        assert response.status == 200
        data = json.loads(response.read())
        assert data["total"] == 1
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["task_id"] == 12345
        assert data["tasks"][0]["type"] == "buildArch"

        conn.close()

    def test_task_details(self, server):
        """Test GET /api/v1/tasks/<id>."""
        server_instance, _, task_registry = server

        # Register test task
        task_registry.register_task(
            task_id=12345,
            task_type="buildArch",
            arch="x86_64",
            tag="el10-build",
            srpm="test-1.0-1.src.rpm",
            container_id="test-container-1",
            log_path="/mnt/koji/logs/12345/container.log",
        )

        conn = self.get_connection(server_instance)
        conn.request("GET", "/api/v1/tasks/12345")
        response = conn.getresponse()

        assert response.status == 200
        data = json.loads(response.read())
        assert data["task_id"] == 12345
        assert data["type"] == "buildArch"
        assert data["arch"] == "x86_64"
        assert data["tag"] == "el10-build"
        assert data["srpm"] == "test-1.0-1.src.rpm"
        assert data["container_id"] == "test-container-1"
        assert data["log_path"] == "/mnt/koji/logs/12345/container.log"

        conn.close()

    def test_task_details_not_found(self, server):
        """Test GET /api/v1/tasks/<id> with non-existent task."""
        server_instance, _, _ = server
        conn = self.get_connection(server_instance)

        conn.request("GET", "/api/v1/tasks/99999")
        response = conn.getresponse()

        assert response.status == 404
        data = json.loads(response.read())
        assert "error" in data

        conn.close()

    def test_task_logs_endpoint(self, server, tmp_path):
        """Test GET /api/v1/tasks/<id>/logs."""
        server_instance, _, task_registry = server

        # Create test log file
        log_file = tmp_path / "test.log"
        log_file.write_text("line 1\nline 2\nline 3\n")

        # Register test task with log path
        task_registry.register_task(
            task_id=12345,
            task_type="buildArch",
            log_path=str(log_file),
        )

        conn = self.get_connection(server_instance)
        conn.request("GET", "/api/v1/tasks/12345/logs")
        response = conn.getresponse()

        assert response.status == 200
        assert response.getheader("Content-Type") == "text/plain; charset=utf-8"
        content = response.read().decode("utf-8")
        assert "line 1" in content

        conn.close()

    def test_task_logs_with_tail(self, server, tmp_path):
        """Test GET /api/v1/tasks/<id>/logs?tail=2."""
        server_instance, _, task_registry = server

        # Create test log file with many lines
        log_file = tmp_path / "test.log"
        log_file.write_text("\n".join([f"line {i}" for i in range(1, 101)]))

        task_registry.register_task(
            task_id=12345,
            task_type="buildArch",
            log_path=str(log_file),
        )

        conn = self.get_connection(server_instance)
        conn.request("GET", "/api/v1/tasks/12345/logs?tail=2")
        response = conn.getresponse()

        assert response.status == 200
        content = response.read().decode("utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert "line 99" in content
        assert "line 100" in content

        conn.close()

    def test_task_logs_not_found(self, server):
        """Test GET /api/v1/tasks/<id>/logs with non-existent task."""
        server_instance, _, _ = server
        conn = self.get_connection(server_instance)

        conn.request("GET", "/api/v1/tasks/99999/logs")
        response = conn.getresponse()

        assert response.status == 404
        data = json.loads(response.read())
        assert "error" in data

        conn.close()

    def test_cors_headers(self, server):
        """Test CORS headers are present."""
        server_instance, _, _ = server
        conn = self.get_connection(server_instance)

        conn.request("GET", "/api/v1/status")
        response = conn.getresponse()

        assert response.getheader("Access-Control-Allow-Origin") == "*"

        conn.close()

    def test_unknown_endpoint(self, server):
        """Test 404 for unknown endpoint."""
        server_instance, _, _ = server
        conn = self.get_connection(server_instance)

        conn.request("GET", "/api/v1/unknown")
        response = conn.getresponse()

        assert response.status == 404
        data = json.loads(response.read())
        assert "error" in data

        conn.close()