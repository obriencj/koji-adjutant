"""Web UI module for koji-adjutant monitoring dashboard."""

from pathlib import Path

from flask import Flask


def create_app(worker_id: str, container_registry, task_registry):
    """Create and configure Flask application.

    Args:
        worker_id: Worker identifier
        container_registry: Container registry instance
        task_registry: Task registry instance

    Returns:
        Configured Flask application
    """
    # Get absolute paths for templates and static files
    web_dir = Path(__file__).parent
    template_dir = web_dir / "templates"
    static_dir = web_dir / "static"

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )

    # Store registries in app config for route handlers
    app.config["worker_id"] = worker_id
    app.config["container_registry"] = container_registry
    app.config["task_registry"] = task_registry

    # Register blueprints
    from . import routes

    app.register_blueprint(routes.web_bp)

    return app
