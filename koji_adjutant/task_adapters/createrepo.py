"""Createrepo task adapter for containerized repository generation.

This adapter translates Koji createrepo tasks into container executions,
running createrepo_c inside isolated containers.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..container.interface import ContainerManager, ContainerSpec, VolumeMount
from .. import config as adj_config
from ..policy import PolicyResolver
from .base import BaseTaskAdapter, KojiLogSink, TaskContext, default_mounts

logger = logging.getLogger(__name__)

# Optional monitoring registry import
try:
    from ..monitoring import get_task_registry
except ImportError:
    # Monitoring may not be available
    def get_task_registry():
        return None


class CreaterepoAdapter(BaseTaskAdapter):
    """Adapter for executing createrepo tasks in containers.

    Translates createrepo task context into ContainerSpec and executes
    createrepo_c inside isolated containers using PodmanManager.
    """

    def build_spec(
        self,
        ctx: TaskContext,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
        tag_name: Optional[str] = None,
    ) -> ContainerSpec:
        """Build ContainerSpec from createrepo task context.

        Args:
            ctx: Task context with task_id, work_dir, koji_mount_root
            task_params: Task parameters dict with keys:
                - repo_id: Repository ID
                - arch: Architecture for the repository
                - oldrepo: Optional old repository info dict (for --update)
                - Additional options may be in task_params
            session: Optional koji session for policy resolution (Phase 2.1)
            event_id: Optional event ID for policy queries
            tag_name: Optional tag name for policy resolution

        Returns:
            ContainerSpec configured for createrepo_c execution
        """
        repo_id = task_params["repo_id"]
        arch = task_params["arch"]
        oldrepo = task_params.get("oldrepo")

        # Resolve task image from policy or config (Phase 2.1)
        # If session provided and policy enabled, use PolicyResolver
        # Otherwise fall back to config default (Phase 1 compatibility)
        if (
            session is not None
            and tag_name is not None
            and adj_config.adjutant_policy_enabled()
        ):
            try:
                resolver = PolicyResolver(session)
                image = resolver.resolve_image(
                    tag_name=tag_name,
                    arch=arch,
                    task_type="createrepo",
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

        # Build createrepo_c command
        # Based on kojid's CreaterepoTask.create_local_repo pattern
        work_target_path = f"/work/{ctx.task_id}"
        outdir = f"{work_target_path}/repo"
        datadir = f"{outdir}/repodata"

        # Repository directory structure (from kojid pattern)
        # repodir = <toprepodir>/<arch>
        # We'll need to construct this path, but for Phase 1 we'll use
        # a simplified approach where repo_dir is provided or constructed
        repo_dir = task_params.get("repodir", f"/mnt/koji/repos/{repo_id}/{arch}")
        pkglist = task_params.get("pkglist", f"{repo_dir}/pkglist")
        groupdata = task_params.get("groupdata")

        # Build createrepo_c command
        cmd_parts = [
            "/usr/bin/createrepo_c",
            "--error-exit-val",  # Exit with error code on failure
            "-vd",  # Verbose, output directory
            "-o",
            outdir,
        ]

        # Add pkglist if provided and not empty
        if pkglist and os.path.getsize(pkglist) > 0:
            cmd_parts.extend(["-i", pkglist])

        # Add groupdata if provided
        if groupdata and os.path.isfile(groupdata):
            cmd_parts.extend(["-g", groupdata])

        # Add --update if oldrepo is provided (createrepo_update option)
        if oldrepo and task_params.get("createrepo_update", True):
            oldrepodata = task_params.get("oldrepodata")
            if oldrepodata and os.path.isdir(oldrepodata):
                # Copy old repodata (done by adapter setup, not container)
                cmd_parts.append("--update")
                if task_params.get("createrepo_skip_stat", False):
                    cmd_parts.append("--skip-stat")

        # Final argument: repository directory or output directory
        if pkglist and os.path.getsize(pkglist) > 0:
            cmd_parts.append(repo_dir)
        else:
            cmd_parts.append(outdir)

        command = cmd_parts

        # Set environment variables
        env = dict(ctx.environment)
        env.update(
            {
                "KOJI_TASK_ID": str(ctx.task_id),
                "KOJI_REPO_ID": str(repo_id),
                "KOJI_ARCH": arch,
                "TMPDIR": work_target_path,  # Temp directory for createrepo
            }
        )

        # Configure mounts
        # Match ADR 0001: /mnt/koji/work/<task_id> -> /work/<task_id>
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

        # Add repository directory mount
        repo_host_path = Path(repo_dir.replace("/mnt/koji", str(ctx.koji_mount_root)))
        if repo_host_path.exists():
            mounts.append(
                VolumeMount(
                    source=repo_host_path,
                    target=Path(repo_dir),
                    read_only=True,  # Read-only for Phase 1
                    selinux_label="Z",
                )
            )

        # Add groupdata mount if provided
        if groupdata:
            groupdata_host_path = Path(
                groupdata.replace("/mnt/koji", str(ctx.koji_mount_root))
            )
            if groupdata_host_path.exists():
                mounts.append(
                    VolumeMount(
                        source=groupdata_host_path,
                        target=Path(groupdata),
                        read_only=True,
                        selinux_label="Z",
                    )
                )

        # Set workdir to /work/<task_id> (matching ADR 0001)
        workdir = work_target

        # Set user_id/group_id for rootless (1000:1000) or None for root
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
            network_enabled=True,  # Repository operations may need network
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
        tag_name: Optional[str] = None,
    ) -> Tuple[int, List]:
        """Execute createrepo task in container and validate results.

        Args:
            ctx: Task context
            manager: Container manager for execution
            sink: Log sink for streaming container output
            task_params: Task parameters (same as build_spec)
            session: Optional koji session for policy resolution (Phase 2.1)
            event_id: Optional event ID for policy queries
            tag_name: Optional tag name for policy resolution

        Returns:
            Tuple of (exit_code, result_list)
            Result format: [uploadpath, files] matching kojid format
        """
        # Build ContainerSpec
        spec = self.build_spec(
            ctx, task_params, session=session, event_id=event_id, tag_name=tag_name
        )

        # Register task with monitoring registry if available
        registry = get_task_registry()
        if registry:
            try:
                repo_id = task_params["repo_id"]
                arch = task_params["arch"]

                # Determine log path (from sink if available)
                log_path = None
                if hasattr(sink, "log_path"):
                    log_path = sink.log_path
                elif hasattr(sink, "path"):
                    log_path = sink.path

                registry.register_task(
                    task_id=ctx.task_id,
                    task_type="createrepo",
                    arch=arch,
                    tag=tag_name,
                    srpm=None,
                    container_id=None,  # Will be updated when container created
                    log_path=log_path,
                )
            except Exception as exc:
                # Don't fail task if monitoring fails
                logger.debug("Failed to register task with monitoring: %s", exc)

        # Execute container
        try:
            result = manager.run(spec, sink, attach_streams=True)
            exit_code = result.exit_code
            container_id = result.handle.container_id

            # Update task registry with container_id
            if registry:
                try:
                    registry.update_container_id(ctx.task_id, container_id)
                except Exception:
                    pass
        except Exception as exc:
            logger.error("Container execution failed: %s", exc, exc_info=True)
            # Update task status
            if registry:
                try:
                    registry.update_task_status(ctx.task_id, "failed")
                except Exception:
                    pass
            return (1, ["", []])

        if exit_code != 0:
            logger.warning("Createrepo exited with non-zero code: %d", exit_code)
            # Update task status
            if registry:
                try:
                    registry.update_task_status(ctx.task_id, "failed")
                except Exception:
                    pass
            return (exit_code, ["", []])

        # Validate repodata generation
        # Output was written to /work/<task_id>/repo/repodata in container
        # which maps to ctx.work_dir/repo/repodata on host
        outdir_host = ctx.work_dir / "repo"
        datadir_host = outdir_host / "repodata"
        uploadpath = f"work/{ctx.task_id}/repo"

        files: List[str] = []

        if datadir_host.exists():
            # Collect all files in repodata directory
            for file_path in datadir_host.iterdir():
                if file_path.is_file():
                    files.append(file_path.name)

        if not files:
            logger.warning("No repodata files generated by createrepo")
            # Still return success if command succeeded (empty repo case)

        # Update task status on completion
        if registry:
            try:
                status = "completed" if exit_code == 0 else "failed"
                registry.update_task_status(ctx.task_id, status)
            except Exception:
                pass

        # Return result matching kojid format: [uploadpath, files]
        return (exit_code, [uploadpath, files])
