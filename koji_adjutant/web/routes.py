"""Web routes for monitoring dashboard."""

from flask import Blueprint, render_template

web_bp = Blueprint("web", __name__)


@web_bp.route("/")
def dashboard():
    """Render main dashboard page."""
    return render_template("dashboard.html")


@web_bp.route("/tasks/<int:task_id>")
def task_details(task_id):
    """Render task details page.

    Args:
        task_id: Task ID to display
    """
    return render_template("task_details.html", task_id=task_id)


@web_bp.route("/containers/<string:container_id>")
def container_details(container_id):
    """Render container details page.

    Args:
        container_id: Container ID to display
    """
    return render_template("container_details.html", container_id=container_id)
