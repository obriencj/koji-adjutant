"""Operational monitoring module for koji-adjutant.

Provides HTTP status server and registries for tracking containers and tasks.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Global registries (initialized when monitoring server starts)
_container_registry: Optional["ContainerRegistry"] = None
_task_registry: Optional["TaskRegistry"] = None
_registry_lock = threading.Lock()


def get_container_registry() -> Optional["ContainerRegistry"]:
    """Get global container registry instance."""
    return _container_registry


def get_task_registry() -> Optional["TaskRegistry"]:
    """Get global task registry instance."""
    return _task_registry


def start_monitoring_server(
    bind_address: str,
    port: int,
    worker_id: str,
    container_history_ttl: int = 3600,
    task_history_ttl: int = 3600,
) -> Optional["MonitoringServer"]:
    """Start monitoring HTTP server in background thread.

    Args:
        bind_address: IP address to bind to (e.g., "127.0.0.1")
        port: Port number to listen on
        worker_id: Worker identifier for status endpoint
        container_history_ttl: TTL in seconds for completed containers
        task_history_ttl: TTL in seconds for completed tasks

    Returns:
        MonitoringServer instance if started successfully, None if disabled
    """
    global _container_registry, _task_registry

    try:
        from .registry import ContainerRegistry, TaskRegistry
        from .server import MonitoringServer

        # Initialize registries
        with _registry_lock:
            _container_registry = ContainerRegistry(history_ttl=container_history_ttl)
            _task_registry = TaskRegistry(history_ttl=task_history_ttl)

        # Create and start server
        server = MonitoringServer(
            bind_address=bind_address,
            port=port,
            worker_id=worker_id,
            container_registry=_container_registry,
            task_registry=_task_registry,
        )

        # Start server in daemon thread
        server_thread = threading.Thread(
            target=server.serve_forever,
            name="monitoring-server",
            daemon=True,
        )
        server_thread.start()

        logger.info(
            "Monitoring server started on %s:%d (worker_id=%s)",
            bind_address,
            port,
            worker_id,
        )

        return server

    except Exception as exc:
        logger.error("Failed to start monitoring server: %s", exc, exc_info=True)
        return None


def stop_monitoring_server() -> None:
    """Stop monitoring server and clear registries."""
    global _container_registry, _task_registry

    with _registry_lock:
        if _container_registry:
            _container_registry.clear()
            _container_registry = None
        if _task_registry:
            _task_registry.clear()
            _task_registry = None

    logger.info("Monitoring server stopped")


# Import registry classes for type hints
from .registry import ContainerRegistry, TaskRegistry  # noqa: E402
from .server import MonitoringServer  # noqa: E402