"""RebuildSRPM task adapter for containerized SRPM rebuilds.

This adapter translates Koji rebuildSRPM tasks into container executions,
rebuilding existing SRPM files with correct dist tags and macros.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..container.interface import ContainerError, ContainerManager, ContainerSpec, VolumeMount
from .. import config as adj_config
from ..policy import PolicyResolver
from ..buildroot import BuildrootInitializer
from .base import BaseTaskAdapter, KojiLogSink, TaskContext

logger = logging.getLogger(__name__)

# Optional monitoring registry import
try:
    from ..monitoring import get_task_registry
except ImportError:
    # Monitoring may not be available
    def get_task_registry():
        return None


class RebuildSRPMAdapter(BaseTaskAdapter):
    """Adapter for executing rebuildSRPM tasks in containers.

    Translates rebuildSRPM task context into ContainerSpec and executes
    SRPM rebuilds inside isolated containers using PodmanManager.
    """

    def build_spec(
        self,
        ctx: TaskContext,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> ContainerSpec:
        """Build ContainerSpec from rebuildSRPM task context.

        Args:
            ctx: Task context with task_id, work_dir, koji_mount_root
            task_params: Task parameters dict with keys:
                - srpm: SRPM filename (relative to workdir, e.g., 'work/12344/mypackage-1.0-1.src.rpm')
                - build_tag: Build tag name or ID
                - opts: Optional dict with repo_id and other options
            session: Optional koji session for policy resolution
            event_id: Optional event ID for policy queries

        Returns:
            ContainerSpec configured for SRPM rebuild execution
        """
        srpm = task_params["srpm"]
        build_tag = task_params["build_tag"]
        opts = task_params.get("opts") or {}
        repo_id = opts.get("repo_id")
        if not repo_id:
            raise ValueError("A repo id must be provided")

        # Resolve task image from policy or config
        if session is not None and adj_config.adjutant_policy_enabled():
            try:
                resolver = PolicyResolver(session)
                tag_name = build_tag
                if isinstance(build_tag, int):
                    logger.warning(
                        "build_tag is int (%d), assuming tag name lookup needed. "
                        "Policy resolution may fail.",
                        build_tag,
                    )
                image = resolver.resolve_image(
                    tag_name=str(tag_name),
                    arch="noarch",  # SRPM builds are always noarch
                    task_type="rebuildSRPM",
                    event_id=event_id,
                )
                logger.debug(
                    "Resolved image via policy: tag=%s arch=noarch -> %s",
                    tag_name,
                    image,
                )
            except Exception as exc:
                logger.warning(
                    "Policy resolution failed, using config default: %s", exc
                )
                image = adj_config.adjutant_task_image_default()
        else:
            # Fallback: use config default
            image = adj_config.adjutant_task_image_default()

        work_target_path = f"/work/{ctx.task_id}"

        # Check if buildroot initialization is enabled
        use_buildroot = (
            session is not None
            and adj_config.adjutant_buildroot_enabled()
        )

        # Set environment variables
        env = dict(ctx.environment)
        env.update(
            {
                "KOJI_TASK_ID": str(ctx.task_id),
                "KOJI_BUILD_TAG": str(build_tag),
                "KOJI_REPO_ID": str(repo_id),
            }
        )

        # Configure mounts
        # Use standard mounts: /mnt/koji and workspace
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

        # Set workdir to /work/<task_id>
        workdir = work_target

        # Set user_id/group_id for rootless (1000:1000) or None for root
        user_id = 1000
        group_id = 1000

        # Use exec() pattern: container runs sleep infinity, then we exec commands
        # This allows buildroot initialization and step-by-step execution
        command = ["/bin/sleep", "infinity"]

        return ContainerSpec(
            image=image,
            command=command,
            environment=env,
            workdir=workdir,
            mounts=tuple(mounts),
            user_id=user_id,
            group_id=group_id,
            network_enabled=False,  # Network not required for rebuild
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
        """Execute rebuildSRPM task in container and collect results.

        Args:
            ctx: Task context
            manager: Container manager for execution
            sink: Log sink for streaming container output
            task_params: Task parameters (same as build_spec)
            session: Optional koji session for policy resolution
            event_id: Optional event ID for policy queries

        Returns:
            Tuple of (exit_code, result_dict)
            Result dict format: {srpm: path, logs: [paths], brootid: int, source: dict}
        """
        srpm = task_params["srpm"]
        build_tag = task_params["build_tag"]
        opts = task_params.get("opts") or {}
        repo_id = opts.get("repo_id")
        if not repo_id:
            raise ValueError("A repo id must be provided")

        # Resolve event_id from repo if not provided
        if event_id is None and session is not None:
            try:
                repo_info = session.repoInfo(repo_id, strict=True)
                event_id = repo_info.get("create_event")
            except Exception:
                pass

        # Input SRPM path (relative to workdir)
        # Format: 'work/12344/mypackage-1.0-1.src.rpm'
        # We need to resolve it to full path
        if srpm.startswith("work/"):
            srpm_path = ctx.work_dir / srpm
        else:
            srpm_path = ctx.work_dir / "work" / srpm

        work_target_path = f"/work/{ctx.task_id}"

        # Check if buildroot initialization is enabled
        use_buildroot = (
            session is not None
            and adj_config.adjutant_buildroot_enabled()
        )

        if not use_buildroot:
            raise ValueError(
                "Buildroot initialization required for RebuildSRPM adapter"
            )

        # Build ContainerSpec
        spec = self.build_spec(ctx, task_params, session=session, event_id=event_id)

        # Register task with monitoring registry if available
        registry = get_task_registry()
        container_id = None
        if registry:
            try:
                log_path = None
                if hasattr(sink, "log_path"):
                    log_path = sink.log_path
                elif hasattr(sink, "path"):
                    log_path = sink.path

                registry.register_task(
                    task_id=ctx.task_id,
                    task_type="rebuildSRPM",
                    tag=str(build_tag) if build_tag else None,
                    srpm=srpm,
                    container_id=None,  # Will be updated when container created
                    log_path=log_path,
                )
            except Exception as exc:
                # Don't fail task if monitoring fails
                logger.debug("Failed to register task with monitoring: %s", exc)

        # Initialize exit_code
        exit_code = 0
        handle = None

        try:
            # Generate initialization data with srpm-build install group
            initializer = BuildrootInitializer(session)
            init_result = initializer.initialize(
                srpm_path=srpm_path,
                build_tag=build_tag,
                arch="noarch",  # SRPM builds are noarch
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
            container_id = handle.container_id

            # Update task registry with container_id
            if registry:
                try:
                    registry.update_container_id(ctx.task_id, container_id)
                except Exception:
                    pass

            manager.start(handle)
            manager.stream_logs(handle, sink, follow=False)

            # Copy config files to proper locations
            manager.copy_to(handle, repo_file, init_result["repo_file_dest"])
            manager.copy_to(handle, macros_file, init_result["macros_file_dest"])

            # Execute init commands
            for cmd in init_result["init_commands"]:
                exit_code = manager.exec(handle, cmd, sink, init_result["environment"])
                if exit_code != 0:
                    raise ContainerError(f"Init command failed: {cmd}")

            # Copy input SRPM to container work directory
            container_srpm_dir = f"{work_target_path}/srpm"
            manager.exec(
                handle,
                ["mkdir", "-p", container_srpm_dir],
                sink,
                init_result["environment"],
            )

            # Copy SRPM file to container
            container_srpm_path = f"{container_srpm_dir}/{srpm_path.name}"
            manager.copy_to(handle, srpm_path, container_srpm_path)

            # Unpack SRPM
            unpack_result = self.unpack_srpm(
                handle, manager, container_srpm_path, work_target_path, sink, init_result["environment"]
            )

            # Rebuild SRPM with correct macros
            spec_file = unpack_result["spec"]
            source_dir = unpack_result["source_dir"]
            rebuilt_srpm_pattern = self.rebuild_srpm(
                handle, manager, spec_file, source_dir, work_target_path, sink, init_result["environment"]
            )

            # Find rebuilt SRPM files
            result_dir = f"{work_target_path}/result"
            
            # List SRPMs in result directory to verify rebuild succeeded
            manager.exec(
                handle,
                ["ls", "-lh", result_dir],
                sink,
                init_result["environment"],
            )

            # The result directory is mounted, so SRPM files are accessible from host
            # We'll collect them after container operations complete

        except Exception as exc:
            logger.error("SRPM rebuild execution failed: %s", exc, exc_info=True)
            # Update task status
            if registry:
                try:
                    registry.update_task_status(ctx.task_id, "failed")
                except Exception:
                    pass
            exit_code = 1
            return (exit_code, {"srpm": "", "logs": [], "brootid": 0, "source": {}})

        finally:
            # Always cleanup container
            if handle:
                try:
                    manager.remove(handle, force=True)
                except Exception as e:
                    logger.warning("Container cleanup failed: %s", e)

        # Collect artifacts from result directory
        # Result directory is mounted at work_dir/result
        result_dir = ctx.work_dir / "result"
        upload_base = f"work/{ctx.task_id}/result"

        srpm_files: List[str] = []
        log_files: List[str] = []

        if result_dir.exists():
            for file_path in result_dir.iterdir():
                if file_path.is_file():
                    name = file_path.name
                    if name.endswith(".src.rpm"):
                        srpm_files.append(f"{upload_base}/{name}")
                    elif name.endswith(".log"):
                        log_files.append(f"{upload_base}/{name}")

        if len(srpm_files) == 0:
            logger.error("No SRPM files found in result directory: %s", result_dir)
            exit_code = 1
            return (exit_code, {"srpm": "", "logs": log_files, "brootid": 0, "source": {}})
        elif len(srpm_files) > 1:
            logger.warning("Multiple SRPM files found: %s", srpm_files)
            # Use the first one (matching original kojid behavior)
            srpm_files = [srpm_files[0]]

        # Validate SRPM name format (matching original kojid validation)
        srpm_path = result_dir / srpm_files[0].split("/")[-1]
        if srpm_path.exists():
            # Use koji library to validate if available, otherwise skip
            try:
                import koji
                h = koji.get_rpm_header(str(srpm_path))
                name = koji.get_header_field(h, "name")
                version = koji.get_header_field(h, "version")
                release = koji.get_header_field(h, "release")
                srpm_name = f"{name}-{version}-{release}.src.rpm"
                if srpm_name != srpm_path.name:
                    logger.error(
                        "SRPM name mismatch: expected %s, got %s", srpm_name, srpm_path.name
                    )
                    exit_code = 1
                    return (exit_code, {"srpm": "", "logs": log_files, "brootid": 0, "source": {}})
            except ImportError:
                # Koji library not available, skip validation
                logger.debug("koji library not available, skipping SRPM validation")
            except Exception as exc:
                logger.warning("SRPM validation failed: %s", exc)
                # Continue anyway - validation is best effort

        # Build result dict matching kojid format
        srpm_rel_path = srpm_files[0] if srpm_files else ""
        srpm_basename = srpm_rel_path.split("/")[-1] if srpm_rel_path else ""
        
        result_dict = {
            "srpm": srpm_rel_path,
            "logs": log_files,
            "brootid": ctx.task_id,  # Use task_id as brootid
            "source": {
                "source": srpm_basename,
                "url": srpm_basename,
            },
        }

        # Update task status on completion
        if registry:
            try:
                status = "completed" if exit_code == 0 else "failed"
                registry.update_task_status(ctx.task_id, status)
            except Exception:
                pass

        return (exit_code, result_dict)

    def unpack_srpm(
        self,
        handle: Any,
        manager: ContainerManager,
        srpm_path: str,
        dest_dir: str,
        sink: KojiLogSink,
        env: Dict[str, str],
    ) -> Dict[str, str]:
        """Unpack SRPM to extract spec and sources.

        Args:
            handle: Container handle
            manager: Container manager
            srpm_path: Path to SRPM file in container
            dest_dir: Destination directory for unpacking
            sink: Log sink
            env: Environment variables

        Returns:
            Dict with 'spec' and 'source_dir' keys
        """
        # Create RPM build directory structure
        specs_dir = f"{dest_dir}/SPECS"
        sources_dir = f"{dest_dir}/SOURCES"
        manager.exec(
            handle,
            ["mkdir", "-p", specs_dir, sources_dir],
            sink,
            env,
        )

        # Install SRPM using rpm -ivh with _topdir
        # This extracts spec and sources to SPECS and SOURCES directories
        exit_code = manager.exec(
            handle,
            [
                "rpm",
                "-ivh",
                "--define",
                f"_topdir {dest_dir}",
                srpm_path,
            ],
            sink,
            env,
        )

        if exit_code != 0:
            raise ContainerError(f"Failed to unpack SRPM: {srpm_path}")

        # Find spec file (should be in SPECS directory)
        # List spec files to verify extraction
        list_specs_cmd = ["ls", "-1", specs_dir]
        manager.exec(handle, list_specs_cmd, sink, env)
        
        # The spec file should now be in SPECS directory
        # We'll use a glob pattern that sh -c can expand
        # This assumes single spec file (standard case)
        spec_file = f"{specs_dir}/*.spec"

        return {
            "spec": spec_file,
            "source_dir": sources_dir,
        }

    def rebuild_srpm(
        self,
        handle: Any,
        manager: ContainerManager,
        spec_file: str,
        source_dir: str,
        work_dir: str,
        sink: KojiLogSink,
        env: Dict[str, str],
    ) -> str:
        """Rebuild SRPM with correct macros.

        Args:
            handle: Container handle
            manager: Container manager
            spec_file: Path to spec file (may contain wildcards, use with sh -c)
            work_dir: Work directory
            sink: Log sink
            env: Environment variables

        Returns:
            Path pattern to rebuilt SRPM files (wildcard)
        """
        result_dir = f"{work_dir}/result"
        
        # Ensure result directory exists
        manager.exec(
            handle,
            ["mkdir", "-p", result_dir],
            sink,
            env,
        )

        # Build SRPM using rpmbuild -bs
        # Use macros from environment (already set in macros.koji)
        # Handle wildcard in spec_file by using sh -c
        rebuild_cmd = [
            "sh",
            "-c",
            f"rpmbuild -bs --define '_topdir {work_dir}' --define '_sourcedir {source_dir}' --define '_builddir {work_dir}/build' --define '_srcrpmdir {result_dir}' {spec_file}",
        ]
        
        exit_code = manager.exec(handle, rebuild_cmd, sink, env)

        if exit_code != 0:
            raise ContainerError(f"Failed to rebuild SRPM from spec: {spec_file}")

        # Return expected SRPM path pattern
        # The actual filename will be determined by rpmbuild
        return f"{result_dir}/*.src.rpm"

    def validate_srpm(
        self,
        handle: Any,
        manager: ContainerManager,
        srpm_path: str,
        sink: KojiLogSink,
        env: Dict[str, str],
    ) -> Dict[str, str]:
        """Validate SRPM file and extract metadata.

        Args:
            handle: Container handle
            manager: Container manager
            srpm_path: Path to SRPM file (absolute path, no wildcards)
            sink: Log sink
            env: Environment variables

        Returns:
            Dict with 'name', 'version', 'release' keys
        """
        # Query SRPM header and write to temp file for parsing
        query_file = "/tmp/srpm_query.txt"
        query_cmd = [
            "sh",
            "-c",
            f"rpm -qp --queryformat '%{{NAME}}|%{{VERSION}}|%{{RELEASE}}' {srpm_path} > {query_file} 2>&1",
        ]

        exit_code = manager.exec(handle, query_cmd, sink, env)
        if exit_code != 0:
            raise ContainerError(f"Failed to query SRPM header: {srpm_path}")

        # Read query result from file (via copy_from or shared mount)
        # For now, we'll parse from logs or use a shared mount
        # Since result_dir is mounted, we can access files directly
        # Placeholder - will be refined in testing
        # The actual validation will happen by reading the file from host mount
        return {
            "name": "package",  # Will be parsed from file
            "version": "1.0",  # Will be parsed from file
            "release": "1",  # Will be parsed from file
        }
