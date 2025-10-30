"""BuildArch task adapter for containerized RPM builds.

This adapter translates Koji buildArch tasks into container executions,
replacing mock-based buildroots with podman containers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..container.interface import ContainerError, ContainerManager, ContainerSpec, VolumeMount
from .. import config as adj_config
from ..policy import PolicyResolver
from ..buildroot import BuildrootInitializer
from .base import BaseTaskAdapter, KojiLogSink, TaskContext, default_mounts

logger = logging.getLogger(__name__)


class BuildArchAdapter(BaseTaskAdapter):
    """Adapter for executing buildArch tasks in containers.

    Translates buildArch task context into ContainerSpec and executes
    RPM builds inside isolated containers using PodmanManager.
    """

    def build_spec(
        self,
        ctx: TaskContext,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> ContainerSpec:
        """Build ContainerSpec from buildArch task context.

        Args:
            ctx: Task context with task_id, work_dir, koji_mount_root
            task_params: Task parameters dict with keys:
                - pkg: SRPM filename (relative to workdir)
                - root: Build tag/root ID
                - arch: Target architecture
                - keep_srpm: Boolean to keep SRPM in results
                - opts: Optional dict with repo_id and other options
            session: Optional koji session for policy resolution (Phase 2.1)
            event_id: Optional event ID for policy queries

        Returns:
            ContainerSpec configured for RPM build execution
        """
        pkg = task_params["pkg"]
        root = task_params["root"]
        arch = task_params["arch"]
        keep_srpm = task_params.get("keep_srpm", False)
        opts = task_params.get("opts") or {}
        repo_id = opts.get("repo_id")
        if not repo_id:
            raise ValueError("A repo id must be provided")

        # Resolve task image from policy or config (Phase 2.1)
        # If session provided and policy enabled, use PolicyResolver
        # Otherwise fall back to config default (Phase 1 compatibility)
        if session is not None and adj_config.adjutant_policy_enabled():
            try:
                resolver = PolicyResolver(session)
                # root can be tag name (string) or tag ID (int)
                # For policy resolution, we need tag name
                tag_name = root
                if isinstance(root, int):
                    # If root is ID, we'd need to query tag name from session
                    # For now, assume root is tag name (common case)
                    # Future: Could query session.getTag(root) to get name
                    logger.warning(
                        "root is int (%d), assuming tag name lookup needed. "
                        "Policy resolution may fail.",
                        root,
                    )
                image = resolver.resolve_image(
                    tag_name=str(tag_name),
                    arch=arch,
                    task_type="buildArch",
                    event_id=event_id,
                )
                logger.debug(
                    "Resolved image via policy: tag=%s arch=%s -> %s",
                    tag_name,
                    arch,
                    image,
                )
            except Exception as exc:
                logger.warning(
                    "Policy resolution failed, using config default: %s", exc
                )
                image = adj_config.adjutant_task_image_default()
        else:
            # Phase 1 fallback: use config default
            image = adj_config.adjutant_task_image_default()

        # Build command: For Phase 1, use a simple rpmbuild command
        # Future: Replace with mock-like build script or koji build helper
        srpm_path = ctx.work_dir / "work" / pkg
        result_dir = ctx.work_dir / "result"

        # Ensure result directory exists (container will write here)
        result_dir.mkdir(parents=True, exist_ok=True)

        work_target_path = f"/work/{ctx.task_id}"

        # Check if buildroot initialization is enabled
        use_buildroot = (
            session is not None
            and adj_config.adjutant_buildroot_enabled()
        )

        # Store init_result for later use (environment variables, mounts)
        init_result = None

        if use_buildroot:
            # Phase 2.2: Use BuildrootInitializer
            try:
                initializer = BuildrootInitializer(session)
                init_result = initializer.initialize(
                    srpm_path=srpm_path,
                    build_tag=root,
                    arch=arch,
                    work_dir=Path(work_target_path),
                    repo_id=repo_id,
                    event_id=event_id,
                )

                # Write initialization script to work_dir
                init_script_path = ctx.work_dir / "buildroot-init.sh"
                init_script_path.write_text(init_result["script"])
                init_script_path.chmod(0o755)

                # Generate build command that runs init script then builds
                # Use macros from initialization
                macros_str = " ".join(
                    [f'--define "{k} {v}"' for k, v in init_result["macros"].items()]
                )

                command = [
                    "/bin/bash",
                    "-c",
                    f"""
set -euo pipefail
cd {work_target_path}

# Verify SRPM exists
srpm_path="work/{pkg}"
if [ ! -f "$srpm_path" ]; then
    echo "ERROR: SRPM file missing: $srpm_path" >&2
    exit 1
fi

# Run buildroot initialization
echo "Running buildroot initialization..."
{work_target_path}/buildroot-init.sh || {{
    echo "ERROR: Buildroot initialization failed" >&2
    exit 1
}}

# Execute RPM build with initialized environment
echo "Starting RPM build..."
rpmbuild {macros_str} \\
         --rebuild "$srpm_path" || exit $?

echo "Build completed successfully"
""",
                ]

                logger.info(
                    "Using buildroot initialization for tag=%s arch=%s (Phase 2.2)",
                    root,
                    arch,
                )

            except Exception as exc:
                logger.warning(
                    "Buildroot initialization failed, falling back to Phase 1: %s", exc
                )
                use_buildroot = False

        if not use_buildroot:
            # Phase 1 fallback: Simple rpmbuild command
            command = [
            "/bin/bash",
            "-c",
            f"""
set -euo pipefail
# Basic RPM build setup (Phase 1 simplified)
cd {work_target_path}

# Verify SRPM exists
srpm_path="work/{pkg}"
if [ ! -f "$srpm_path" ]; then
    echo "ERROR: SRPM file missing: $srpm_path" >&2
    exit 1
fi

# Create build directories
mkdir -p result build BUILDROOT

# Extract and build (simplified - Phase 1)
# In full implementation, this would use koji buildroot setup
rpmbuild --define "_topdir {work_target_path}" \
         --define "_sourcedir {work_target_path}/work" \
         --define "_builddir {work_target_path}/build" \
         --define "_rpmdir {work_target_path}/result" \
         --define "_srcrpmdir {work_target_path}/result" \
         --define "dist .almalinux10" \
         --rebuild "$srpm_path" || exit $?

# Results are in result/ directory, will be collected via /mnt/koji mount
""",
        ]

        # Set environment variables
        env = dict(ctx.environment)
        env.update(
            {
                "KOJI_TASK_ID": str(ctx.task_id),
                "KOJI_BUILD_TAG": str(root),
                "KOJI_ARCH": arch,
                "KOJI_REPO_ID": str(repo_id),
                "KOJI_KEEP_SRPM": "1" if keep_srpm else "0",
            }
        )

        # If using buildroot initialization, add environment from initializer
        if use_buildroot and init_result is not None:
            try:
                # Merge buildroot environment variables from already-computed result
                env.update(init_result["environment"])
            except Exception:
                # Already logged above, continue with basic env
                pass

        # Configure mounts
        # Use default mounts (/mnt/koji, workspace) but override work_dir mount
        # to match ADR 0001: /mnt/koji/work/<task_id> -> /work/<task_id>
        work_target = Path(f"/work/{ctx.task_id}")
        mounts = [
            VolumeMount(
                source=ctx.koji_mount_root,
                target=Path("/mnt/koji"),
                read_only=False,
                selinux_label="Z",
            ),
            VolumeMount(
                source=ctx.work_dir,
                target=work_target,
                read_only=False,
                selinux_label="Z",
            ),
        ]

        # Store init_result in spec for use in run() method
        # We'll use a private attribute to pass data between build_spec and run
        # This is a temporary solution - in future we could refactor to pass context differently

        # Set workdir to /work/<task_id> (matching ADR 0001)
        workdir = work_target

        # Set user_id/group_id for rootless (1000:1000) or None for root
        # Phase 1: Default to rootless, but allow override
        user_id = 1000
        group_id = 1000

        return ContainerSpec(
            image=image,
            command=command,
            environment=env,
            workdir=workdir,
            mounts=tuple(mounts),
            user_id=user_id,
            group_id=group_id,
            network_enabled=True,  # Builds need network for deps
            remove_after_exit=True,
        )

    def run(
        self,
        ctx: TaskContext,
        manager: ContainerManager,
        sink: KojiLogSink,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> tuple[int, Dict]:
        """Execute buildArch task in container and collect results.

        Args:
            ctx: Task context
            manager: Container manager for execution
            sink: Log sink for streaming container output
            task_params: Task parameters (same as build_spec)
            session: Optional koji session for policy resolution (Phase 2.1)
            event_id: Optional event ID for policy queries

        Returns:
            Tuple of (exit_code, result_dict)
            Result dict format: {rpms: [paths], srpms: [paths], logs: [paths], brootid: int}
        """
        pkg = task_params["pkg"]
        root = task_params["root"]
        arch = task_params["arch"]
        opts = task_params.get("opts") or {}
        repo_id = opts.get("repo_id")
        if not repo_id:
            raise ValueError("A repo id must be provided")

        srpm_path = ctx.work_dir / "work" / pkg
        work_target_path = f"/work/{ctx.task_id}"

        # Check if buildroot initialization is enabled
        use_buildroot = (
            session is not None
            and adj_config.adjutant_buildroot_enabled()
        )

        # Build ContainerSpec
        spec = self.build_spec(ctx, task_params, session=session, event_id=event_id)

        # Initialize exit_code
        exit_code = 0

        # If using exec pattern (buildroot enabled), use exec pattern
        if use_buildroot and spec.command == ["/bin/sleep", "infinity"]:
            # Phase 2.2: Exec pattern
            try:
                # Generate initialization data
                initializer = BuildrootInitializer(session)
                init_result = initializer.initialize(
                    srpm_path=srpm_path,
                    build_tag=root,
                    arch=arch,
                    work_dir=Path(work_target_path),
                    repo_id=repo_id,
                    event_id=event_id,
                )

                # Write config files to host
                repo_file = ctx.work_dir / "koji.repo"
                repo_file.write_text(init_result["repo_file_content"])

                macros_file = ctx.work_dir / "macros.koji"
                macros_file.write_text(init_result["macros_file_content"])

                # Ensure image is available
                manager.ensure_image_available(spec.image)

                # Create container with sleep
                handle = manager.create(spec)
                manager.start(handle)
                manager.stream_logs(handle, sink, follow=False)

                try:
                    # Copy config files to proper locations
                    manager.copy_to(handle, repo_file, init_result["repo_file_dest"])
                    manager.copy_to(handle, macros_file, init_result["macros_file_dest"])

                    # Execute init commands
                    for cmd in init_result["init_commands"]:
                        exit_code = manager.exec(handle, cmd, sink, init_result["environment"])
                        if exit_code != 0:
                            raise ContainerError(f"Init command failed: {cmd}")

                    # Execute build command
                    exit_code = manager.exec(
                        handle,
                        init_result["build_command"],
                        sink,
                        init_result["environment"],
                    )

                    if exit_code != 0:
                        logger.warning("Build exited with non-zero code: %d", exit_code)
                        # Continue to result collection even on failure

                finally:
                    # Always cleanup
                    manager.remove(handle, force=True)

            except Exception as exc:
                logger.error("Exec pattern execution failed: %s", exc, exc_info=True)
                return (1, {"rpms": [], "srpms": [], "logs": [], "brootid": 0})
        else:
            # Phase 1 fallback: Use run() method
            try:
                result = manager.run(spec, sink, attach_streams=True)
                exit_code = result.exit_code
            except Exception as exc:
                logger.error("Container execution failed: %s", exc, exc_info=True)
                return (1, {"rpms": [], "srpms": [], "logs": [], "brootid": 0})

            if exit_code != 0:
                logger.warning("Build exited with non-zero code: %d", exit_code)
                # Continue to result collection even on failure

        # Collect artifacts from /mnt/koji paths
        # Result structure matches kojid format
        # work_dir is already /mnt/koji/work/<task_id>, so result is work_dir/result
        result_dir = ctx.work_dir / "result"
        upload_base = f"work/{ctx.task_id}/result"

        rpm_files: List[str] = []
        srpm_files: List[str] = []
        log_files: List[str] = []

        if result_dir.exists():
            for file_path in result_dir.iterdir():
                if file_path.is_file():
                    name = file_path.name
                    if name.endswith(".src.rpm"):
                        srpm_files.append(f"{upload_base}/{name}")
                    elif name.endswith(".rpm"):
                        rpm_files.append(f"{upload_base}/{name}")
                    elif name.endswith(".log"):
                        log_files.append(f"{upload_base}/{name}")

        # Handle keep_srpm flag
        keep_srpm = task_params.get("keep_srpm", False)
        if not keep_srpm:
            srpm_files = []

        # Build result dict matching kojid format
        result_dict = {
            "rpms": rpm_files,
            "srpms": srpm_files if keep_srpm else [],
            "logs": log_files,
            "brootid": ctx.task_id,  # Use task_id as brootid for Phase 1
        }

        return (exit_code, result_dict)
