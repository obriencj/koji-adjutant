"""HTTP status server for operational monitoring."""

from __future__ import annotations

import json
import logging
import socket
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .registry import ContainerInfo, ContainerRegistry, TaskInfo, TaskRegistry

logger = logging.getLogger(__name__)

# Flask integration (optional)
try:
    from koji_adjutant.web import create_app

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    create_app = None


class MonitoringRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for monitoring endpoints."""

    def __init__(
        self,
        request,
        client_address,
        server,
        worker_id: str,
        container_registry: ContainerRegistry,
        task_registry: TaskRegistry,
    ):
        """Initialize request handler.

        Args:
            request: Socket request
            client_address: Client address
            server: HTTP server instance
            worker_id: Worker identifier
            container_registry: Container registry instance
            task_registry: Task registry instance
        """
        self.worker_id = worker_id
        self.container_registry = container_registry
        self.task_registry = task_registry
        self.server_start_time = time.time()
        super().__init__(request, client_address, server)

    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        """Handle GET requests."""
        try:
            parsed_path = urlparse(self.path)
            path = parsed_path.path

            # Route API requests to existing handlers
            if path == "/api/v1/status":
                self._handle_status()
            elif path == "/api/v1/containers":
                self._handle_list_containers()
            elif path.startswith("/api/v1/containers/"):
                container_id = path.split("/")[-1]
                self._handle_container_details(container_id)
            elif path == "/api/v1/tasks":
                self._handle_list_tasks()
            elif path.startswith("/api/v1/tasks/"):
                parts = path.split("/")
                if len(parts) >= 5 and parts[-1] == "logs":
                    task_id = int(parts[-2])
                    self._handle_task_logs(task_id, parsed_path.query)
                else:
                    task_id = int(parts[-1])
                    self._handle_task_details(task_id)
            else:
                # Non-API routes: delegate to Flask (if available)
                if FLASK_AVAILABLE and self.server.flask_app:
                    self._handle_flask_request()
                else:
                    self._send_error(404, "Not Found", "Unknown endpoint")

        except Exception as exc:
            logger.error("Error handling request: %s", exc, exc_info=True)
            self._send_error(500, "Internal Server Error", str(exc))

    def _handle_status(self):
        """Handle GET /api/v1/status."""
        # Cleanup old entries periodically
        self.container_registry.cleanup_old_entries()
        self.task_registry.cleanup_old_entries()

        # Get active counts
        active_containers = len(self.container_registry.list_containers(active_only=True))
        active_tasks = len(self.task_registry.list_tasks(active_only=True))

        # Get completed tasks count (from history)
        all_tasks = self.task_registry.list_tasks(active_only=False)
        completed_today = sum(
            1
            for task in all_tasks
            if task.finished_at
            and task.finished_at.date() == datetime.now(timezone.utc).date()
            and task.status == "completed"
        )

        # Get last task time
        last_task_time = None
        if all_tasks:
            finished_tasks = [t for t in all_tasks if t.finished_at]
            if finished_tasks:
                last_task = max(finished_tasks, key=lambda t: t.finished_at)
                last_task_time = last_task.finished_at.isoformat()

        # Get capacity from config (default to 4 if not available)
        # Capacity is typically in kojid options, but we'll default to 4
        capacity_value = 4  # Default capacity

        # Check Podman connectivity
        podman_health = self._check_podman_health()

        status_data = {
            "worker_id": self.worker_id,
            "uptime_seconds": int(time.time() - self.server_start_time),
            "status": "healthy" if podman_health["status"] == "healthy" else "degraded",
            "podman": podman_health,
            "capacity": capacity_value,
            "active_tasks": active_tasks,
            "containers_active": active_containers,
            "tasks_completed_today": completed_today,
            "last_task_time": last_task_time,
        }

        self._send_json(200, status_data)

    def _handle_list_containers(self):
        """Handle GET /api/v1/containers."""
        containers = self.container_registry.list_containers(active_only=True)

        containers_data = []
        for container in containers:
            containers_data.append(
                {
                    "container_id": container.container_id,
                    "task_id": container.task_id,
                    "image": container.image,
                    "status": container.status,
                    "created_at": container.created_at.isoformat(),
                    "started_at": container.started_at.isoformat() if container.started_at else None,
                }
            )

        self._send_json(200, {"containers": containers_data, "total": len(containers_data)})

    def _handle_container_details(self, container_id: str):
        """Handle GET /api/v1/containers/<id>."""
        container = self.container_registry.get(container_id)
        if not container:
            self._send_error(404, "Not Found", f"Container not found: {container_id}")
            return

        # Extract spec details
        spec = container.spec
        mounts_data = []
        for mount in container.mounts:
            mounts_data.append(
                {
                    "source": mount.get("source", ""),
                    "target": mount.get("target", ""),
                    "read_only": mount.get("read_only", False),
                }
            )

        resource_limits = {}
        if spec:
            resource_limits = spec.get("resource_limits", {})

        container_data = {
            "container_id": container.container_id,
            "task_id": container.task_id,
            "image": container.image,
            "status": container.status,
            "spec": {
                "command": container.command or spec.get("command", []),
                "workdir": spec.get("workdir"),
                "user": container.user or spec.get("user"),
            },
            "mounts": mounts_data,
            "resource_limits": {
                "memory_bytes": resource_limits.get("memory_bytes"),
                "cpus": resource_limits.get("cpus"),
            },
            "created_at": container.created_at.isoformat(),
            "started_at": container.started_at.isoformat() if container.started_at else None,
            "finished_at": container.finished_at.isoformat() if container.finished_at else None,
        }

        self._send_json(200, container_data)

    def _handle_list_tasks(self):
        """Handle GET /api/v1/tasks."""
        tasks = self.task_registry.list_tasks(active_only=True)

        tasks_data = []
        for task in tasks:
            tasks_data.append(
                {
                    "task_id": task.task_id,
                    "type": task.task_type,
                    "status": task.status,
                    "arch": task.arch,
                    "tag": task.tag,
                    "started_at": task.started_at.isoformat(),
                    "container_id": task.container_id,
                }
            )

        self._send_json(200, {"tasks": tasks_data, "total": len(tasks_data)})

    def _handle_task_details(self, task_id: int):
        """Handle GET /api/v1/tasks/<id>."""
        task = self.task_registry.get(task_id)
        if not task:
            self._send_error(404, "Not Found", f"Task not found: {task_id}")
            return

        task_data = {
            "task_id": task.task_id,
            "type": task.task_type,
            "status": task.status,
            "arch": task.arch,
            "tag": task.tag,
            "srpm": task.srpm,
            "started_at": task.started_at.isoformat(),
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "container_id": task.container_id,
            "log_path": task.log_path,
            "progress": task.progress,
        }

        self._send_json(200, task_data)

    def _handle_task_logs(self, task_id: int, query_string: str):
        """Handle GET /api/v1/tasks/<id>/logs."""
        task = self.task_registry.get(task_id)
        if not task:
            self._send_error(404, "Not Found", f"Task not found: {task_id}")
            return

        # Parse query parameters
        params = parse_qs(query_string)
        tail_lines = int(params.get("tail", ["100"])[0])

        # Get log path
        log_path = task.log_path
        if not log_path:
            self._send_error(404, "Not Found", f"Log path not available for task {task_id}")
            return

        # Convert log_path to absolute if needed
        log_file = Path(log_path)
        if not log_file.is_absolute():
            # Assume log_path is relative to /mnt/koji
            log_file = Path("/mnt/koji") / log_path.lstrip("/")

        if not log_file.exists():
            self._send_error(404, "Not Found", f"Log file not found: {log_path}")
            return

        # Read log file (last N lines)
        try:
            with open(log_file, "rb") as f:
                lines = f.readlines()
                if len(lines) > tail_lines:
                    lines = lines[-tail_lines:]
                log_content = b"".join(lines)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(log_content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(log_content)

        except Exception as exc:
            logger.error("Error reading log file: %s", exc, exc_info=True)
            self._send_error(500, "Internal Server Error", f"Failed to read log file: {exc}")

    def _check_podman_health(self) -> dict:
        """Check Podman connectivity health.

        Returns:
            dict with status, message, and version info
        """
        try:
            # Import PodmanManager here to avoid circular dependency
            from ..container.podman_manager import PodmanManager

            manager = PodmanManager()
            return manager.health_check()
        except Exception as exc:
            logger.warning("Failed to check Podman health: %s", exc)
            return {
                "status": "unknown",
                "message": f"Health check failed: {exc}",
                "error": str(exc),
            }

    def _send_json(self, status_code: int, data: dict):
        """Send JSON response."""
        json_data = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(json_data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json_data)

    def _send_error(self, status_code: int, error: str, message: str):
        """Send error JSON response."""
        error_data = {"error": error, "error_code": error.upper().replace(" ", "_"), "message": message}
        self._send_json(status_code, error_data)

    def _handle_flask_request(self):
        """Handle request via Flask WSGI application."""
        # Read request body if present (for POST/PUT requests)
        content_length = self.headers.get("Content-Length")
        request_body = b""
        if content_length:
            try:
                content_length = int(content_length)
                if content_length > 0:
                    request_body = self.rfile.read(content_length)
            except (ValueError, OSError):
                pass

        # Create WSGI environment
        environ = {
            "REQUEST_METHOD": self.command,
            "PATH_INFO": urlparse(self.path).path,
            "QUERY_STRING": urlparse(self.path).query,
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(len(request_body)),
            "SERVER_NAME": self.server.server_address[0],
            "SERVER_PORT": str(self.server.server_address[1]),
            "SERVER_PROTOCOL": self.protocol_version,
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "wsgi.input": BytesIO(request_body),
            "wsgi.errors": BytesIO(),
            "wsgi.multithread": True,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }

        # Add headers
        for key, value in self.headers.items():
            key = key.replace("-", "_").upper()
            if key not in ("CONTENT_TYPE", "CONTENT_LENGTH"):
                key = f"HTTP_{key}"
            environ[key] = value

        # Call Flask WSGI app
        app = self.server.flask_app
        response_data = {}

        def start_response(status, response_headers):
            response_data["status"] = status
            response_data["headers"] = response_headers

        app_iter = app(environ, start_response)

        # Send response
        status_parts = response_data["status"].split(" ", 1)
        status_code = int(status_parts[0])
        status_message = status_parts[1] if len(status_parts) > 1 else ""

        self.send_response(status_code, status_message)

        # Send headers
        for header, value in response_data["headers"]:
            self.send_header(header, value)
        self.end_headers()

        # Send body
        try:
            for chunk in app_iter:
                if chunk:
                    self.wfile.write(chunk)
        finally:
            if hasattr(app_iter, "close"):
                app_iter.close()


class MonitoringServer(ThreadingHTTPServer):
    """HTTP server for monitoring endpoints."""

    def __init__(
        self,
        bind_address: str,
        port: int,
        worker_id: str,
        container_registry: ContainerRegistry,
        task_registry: TaskRegistry,
    ):
        """Initialize monitoring server.

        Args:
            bind_address: IP address to bind to
            port: Port number (0 for random port)
            worker_id: Worker identifier
            container_registry: Container registry instance
            task_registry: Task registry instance
        """
        self.bind_address = bind_address
        self.port = port
        self.worker_id = worker_id
        self.container_registry = container_registry
        self.task_registry = task_registry

        # Create Flask app if available
        self.flask_app = None
        if FLASK_AVAILABLE and create_app:
            try:
                self.flask_app = create_app(worker_id, container_registry, task_registry)
            except Exception as exc:
                logger.warning("Failed to create Flask app: %s", exc)

        # Create server socket
        server_address = (bind_address, port)

        def handler_factory(request, client_address, server):
            return MonitoringRequestHandler(
                request,
                client_address,
                server,
                worker_id=worker_id,
                container_registry=container_registry,
                task_registry=task_registry,
            )

        super().__init__(server_address, handler_factory)

        # Set socket options for reuse
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # If port was 0, get the actual assigned port
        if port == 0:
            self.port = self.server_address[1]

    def serve_forever(self, poll_interval: float = 0.5):
        """Start serving requests."""
        logger.info("Monitoring server listening on %s:%d", self.bind_address, self.port)
        try:
            super().serve_forever(poll_interval=poll_interval)
        except Exception as exc:
            logger.error("Monitoring server error: %s", exc, exc_info=True)
        finally:
            logger.info("Monitoring server stopped")

    def shutdown(self):
        """Shutdown server gracefully."""
        logger.info("Shutting down monitoring server...")
        super().shutdown()