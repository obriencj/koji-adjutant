"""Buildroot initialization orchestrator.

Coordinates dependency resolution, repository configuration, and environment
setup to prepare containers for RPM builds.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import dependencies, environment, repos

logger = logging.getLogger(__name__)


class BuildrootInitializer:
    """Orchestrates buildroot initialization for containerized RPM builds.

    This class coordinates the full buildroot initialization sequence:
    1. Parse SRPM for BuildRequires
    2. Query hub for repo configuration
    3. Generate repo files
    4. Resolve and prepare dependency list
    5. Setup build environment
    6. Generate initialization script

    The initialization happens inside the container via a generated script.
    """

    def __init__(self, session: Any):
        """Initialize BuildrootInitializer.

        Args:
            session: Koji session object for hub API queries
        """
        self.session = session
        self.logger = logging.getLogger(__name__)

    def initialize(
        self,
        srpm_path: Path,
        build_tag: str | int,
        arch: str,
        work_dir: Path,
        repo_id: int,
        event_id: Optional[int] = None,
        dist: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Initialize buildroot configuration.

        This method gathers all information needed for buildroot initialization
        but does NOT execute inside container. It returns configuration data
        that can be used to generate an initialization script.

        Args:
            srpm_path: Path to SRPM file
            build_tag: Build tag name or ID
            arch: Target architecture
            work_dir: Work directory path (will be mounted in container)
            repo_id: Repository ID
            event_id: Optional event ID for historical queries
            dist: Optional distribution tag (e.g., ".almalinux10")

        Returns:
            Dict with initialization data:
            - repo_file_content: Repository config file content (string)
            - repo_file_dest: Destination path in container (e.g., "/etc/yum.repos.d/koji.repo")
            - macros_file_content: RPM macros file content (string)
            - macros_file_dest: Destination path in container (e.g., "/etc/rpm/macros.koji")
            - init_commands: List of command lists to execute for initialization
            - build_command: Command list for RPM build execution
            - environment: Environment variables dict
            - dependencies: List of package names to install (for reference)
            - tag_id: Tag ID
            - tag_name: Tag name

        Raises:
            ValueError: If required parameters are missing
            koji.GenericError: If hub queries fail
        """
        # Resolve tag_id if build_tag is name
        tag_id = build_tag
        tag_name = str(build_tag)
        if isinstance(build_tag, str):
            try:
                tag_info = self.session.getTag(build_tag, strict=True, event=event_id)
                tag_id = tag_info["id"]
                tag_name = tag_info["name"]
            except Exception as exc:
                self.logger.warning(
                    "Could not resolve tag name '%s' to ID: %s. Using as-is.", build_tag, exc
                )

        # 1. Parse SRPM for BuildRequires
        srpm_deps: List[str] = []
        if srpm_path.exists():
            try:
                srpm_deps = dependencies.extract_buildrequires_from_srpm(srpm_path)
            except Exception as exc:
                self.logger.warning("Failed to parse SRPM BuildRequires: %s", exc)

        # 2. Resolve complete dependency list
        all_deps = dependencies.resolve_build_dependencies(
            session=self.session,
            tag_id=tag_id,
            arch=arch,
            srpm_path=srpm_path if srpm_path.exists() else None,
            event_id=event_id,
        )

        # 3. Get repository configuration
        try:
            repo_config = repos.generate_repo_config(
                session=self.session,
                tag_id=tag_id,
                repo_id=repo_id,
                arch=arch,
                event_id=event_id,
            )
        except Exception as exc:
            self.logger.error("Failed to generate repo config: %s", exc)
            raise

        # 4. Generate environment variables
        env_vars = environment.setup_build_environment(
            work_dir=work_dir,
            task_id=0,  # Will be set by caller
            build_tag=tag_name,
            arch=arch,
            repo_id=repo_id,
            dist=dist,
        )

        # 5. Generate RPM macros
        macros = environment.generate_rpm_macros(work_dir=work_dir, dist=dist)

        # 6. Generate structured initialization data
        work_dir_str = str(work_dir)
        srpm_filename = srpm_path.name if srpm_path.exists() else ""

        # Generate init commands
        init_commands = self._generate_init_commands(
            work_dir=work_dir,
            dependencies=all_deps,
        )

        # Generate macros file content
        macros_file_content = self._format_macros_file(macros)

        # Generate build command
        build_command = self._generate_build_command(
            work_dir=work_dir,
            srpm_path=f"{work_dir_str}/work/{srpm_filename}",
            macros=macros,
        )

        return {
            "repo_file_content": repo_config,
            "repo_file_dest": "/etc/yum.repos.d/koji.repo",
            "macros_file_content": macros_file_content,
            "macros_file_dest": "/etc/rpm/macros.koji",
            "init_commands": init_commands,
            "build_command": build_command,
            "environment": env_vars,
            "dependencies": all_deps,
            "tag_id": tag_id,
            "tag_name": tag_name,
        }

    def _generate_init_commands(
        self,
        work_dir: Path,
        dependencies: List[str],
    ) -> List[List[str]]:
        """Generate initialization commands as structured command lists.

        Args:
            work_dir: Work directory path (inside container)
            dependencies: List of packages to install

        Returns:
            List of command lists to execute in order
        """
        work_dir_str = str(work_dir)
        commands: List[List[str]] = []

        # Step 1: Create directory structure
        commands.append([
            "mkdir", "-p",
            f"{work_dir_str}/work",
            f"{work_dir_str}/build",
            f"{work_dir_str}/BUILDROOT",
            f"{work_dir_str}/result",
        ])

        # Step 2: Install dependencies (if any)
        deps_command = ["dnf", "install", "-y",
                        "--setopt=install_weak_deps=False",
                        "--setopt=skip_missing_names_on_install=False",
                        "--setopt=keepcache=True"]
        if dependencies:
            commands.append(deps_command + dependencies)

        return commands

    def _format_macros_file(self, macros: Dict[str, str]) -> str:
        """Format RPM macros dict as macros file content.

        Args:
            macros: Dict mapping macro names to values

        Returns:
            String content for /etc/rpm/macros.koji file
        """
        lines = []
        for macro_name, macro_value in macros.items():
            # Format as %macro_name macro_value
            lines.append(f"%{macro_name} {macro_value}")
        return "\n".join(lines) + "\n"

    def _generate_build_command(
        self,
        work_dir: Path,
        srpm_path: str,
        macros: Dict[str, str],
    ) -> List[str]:
        """Generate RPM build command as structured command list.

        Args:
            work_dir: Work directory path (inside container)
            srpm_path: Path to SRPM file (relative to work_dir or absolute)
            macros: RPM macros dict

        Returns:
            Command list for rpmbuild execution
        """
        work_dir_str = str(work_dir)
        command = ["rpmbuild", "--rebuild", srpm_path]

        # Add macro definitions as --define flags
        for macro_name, macro_value in macros.items():
            command.extend(["--define", f"{macro_name} {macro_value}"])

        return command
