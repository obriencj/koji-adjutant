"""BuildSRPMFromSCM task adapter for containerized SRPM builds from source control.

This adapter translates Koji buildSRPMFromSCM tasks into container executions,
checking out source from git/svn and building SRPMs in isolated containers.
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
from .scm import get_scm_handler

logger = logging.getLogger(__name__)

# Optional monitoring registry import
try:
    from ..monitoring import get_task_registry
except ImportError:
    def get_task_registry():
        return None


class BuildSRPMFromSCMAdapter(BaseTaskAdapter):
    """Adapter for executing buildSRPMFromSCM tasks in containers.
    
    Translates buildSRPMFromSCM task context into ContainerSpec and executes
    SRPM builds from source control inside isolated containers.
    """
    
    def build_spec(
        self,
        ctx: TaskContext,
        task_params: dict,
        session: Optional[Any] = None,
        event_id: Optional[int] = None,
    ) -> ContainerSpec:
        """Build ContainerSpec from buildSRPMFromSCM task context.
        
        Args:
            ctx: Task context
            task_params: Task parameters dict with keys:
                - url: SCM URL (e.g., git://example.com/package.git#branch)
                - build_tag: Build tag name or ID
                - opts: Optional dict with repo_id and other options
            session: Optional koji session for policy resolution
            event_id: Optional event ID for policy queries
            
        Returns:
            ContainerSpec configured for SRPM build from SCM
        """
        url = task_params["url"]
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
                        "build_tag is int (%d), assuming tag name lookup needed",
                        build_tag,
                    )
                image = resolver.resolve_image(
                    tag_name=str(tag_name),
                    arch="noarch",  # SRPM builds are always noarch
                    task_type="buildSRPMFromSCM",
                    event_id=event_id,
                )
                logger.debug("Resolved image via policy: %s", image)
            except Exception as exc:
                logger.warning("Policy resolution failed: %s", exc)
                image = adj_config.adjutant_task_image_default()
        else:
            image = adj_config.adjutant_task_image_default()
        
        work_target_path = f"/work/{ctx.task_id}"
        
        env = dict(ctx.environment)
        env.update({
            "KOJI_TASK_ID": str(ctx.task_id),
            "KOJI_BUILD_TAG": str(build_tag),
            "KOJI_REPO_ID": str(repo_id),
            "KOJI_SCM_URL": url,  # Additional: track SCM URL
        })
        
        mounts = [
            VolumeMount(
                source=ctx.koji_mount_root,
                target=Path("/mnt/koji"),
                read_only=False,
                selinux_label="Z",
            ),
            VolumeMount(
                source=ctx.work_dir,
                target=Path(work_target_path),
                read_only=False,
                selinux_label="Z",
            ),
        ]
        
        return ContainerSpec(
            image=image,
            command=["/bin/sleep", "infinity"],  # Exec pattern
            environment=env,
            workdir=Path(work_target_path),
            mounts=tuple(mounts),
            user_id=1000,
            group_id=1000,
            network_enabled=True,  # KEY DIFFERENCE: Network required for SCM checkout
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
        """Execute buildSRPMFromSCM task in container.
        
        Workflow:
        1. Create container with network enabled
        2. Initialize buildroot (srpm-build group)
        3. Checkout source from SCM
        4. Detect build method (make srpm vs rpmbuild -bs)
        5. Build SRPM
        6. Validate SRPM
        7. Return result
        
        Returns:
            Tuple of (exit_code, result_dict)
        """
        url = task_params["url"]
        build_tag = task_params["build_tag"]
        opts = task_params.get("opts") or {}
        repo_id = opts.get("repo_id")
        
        # Resolve event_id from repo if not provided
        if event_id is None and session is not None:
            try:
                repo_info = session.repoInfo(repo_id, strict=True)
                event_id = repo_info.get("create_event")
            except Exception:
                pass
        
        work_target_path = f"/work/{ctx.task_id}"
        source_dir = f"{work_target_path}/source"
        
        # Check if buildroot initialization is enabled
        use_buildroot = (
            session is not None
            and adj_config.adjutant_buildroot_enabled()
        )
        
        if not use_buildroot:
            raise ValueError(
                "Buildroot initialization required for BuildSRPMFromSCM adapter"
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
                    task_type="buildSRPMFromSCM",
                    tag=str(build_tag) if build_tag else None,
                    srpm=url,
                    container_id=None,  # Will be updated when container created
                    log_path=log_path,
                )
            except Exception as exc:
                logger.debug("Failed to register task with monitoring: %s", exc)
        
        exit_code = 0
        handle = None
        
        try:
            # Generate initialization data
            # For SCM builds, we need a dummy SRPM path for BuildrootInitializer
            # We'll use a placeholder that gets replaced
            dummy_srpm_path = ctx.work_dir / "dummy.src.rpm"
            # Create empty file for initializer (it will parse it)
            dummy_srpm_path.touch()
            
            initializer = BuildrootInitializer(session)
            init_result = initializer.initialize(
                srpm_path=dummy_srpm_path,
                build_tag=build_tag,
                arch="noarch",
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
            
            # Checkout source from SCM
            scm_metadata = self.checkout_scm(
                handle, manager, url, source_dir, sink
            )
            
            # Detect build method (make srpm vs rpmbuild -bs)
            build_method = self.detect_build_method(
                handle, manager, source_dir, sink
            )
            
            # Build SRPM
            rebuilt_srpm_pattern = self.build_srpm(
                handle, manager, source_dir, work_target_path, build_method, sink, init_result["environment"]
            )
            
            # Find built SRPM files
            result_dir = f"{work_target_path}/result"
            
            # List SRPMs in result directory to verify build succeeded
            manager.exec(
                handle,
                ["ls", "-lh", result_dir],
                sink,
                init_result["environment"],
            )
            
        except Exception as exc:
            logger.error("SRPM build from SCM execution failed: %s", exc, exc_info=True)
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
            # Use koji library to validate if available
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
                logger.debug("koji library not available, skipping SRPM validation")
            except Exception as exc:
                logger.warning("SRPM validation failed: %s", exc)
        
        # Build result dict matching kojid format
        srpm_rel_path = srpm_files[0] if srpm_files else ""
        srpm_basename = srpm_rel_path.split("/")[-1] if srpm_rel_path else ""
        
        # Include SCM metadata in source dict
        source_info = {
            "source": srpm_basename,
            "url": url,
        }
        # Add SCM-specific metadata if available
        if scm_metadata:
            source_info.update({
                "commit": scm_metadata.get("commit", ""),
                "branch": scm_metadata.get("branch", ""),
            })
        
        result_dict = {
            "srpm": srpm_rel_path,
            "logs": log_files,
            "brootid": ctx.task_id,  # Use task_id as brootid
            "source": source_info,
        }
        
        # Update task status on completion
        if registry:
            try:
                status = "completed" if exit_code == 0 else "failed"
                registry.update_task_status(ctx.task_id, status)
            except Exception:
                pass
        
        return (exit_code, result_dict)
    
    def checkout_scm(
        self,
        handle: Any,
        manager: ContainerManager,
        scm_url: str,
        dest_dir: str,
        sink: KojiLogSink,
    ) -> Dict[str, str]:
        """Checkout source from SCM.
        
        Args:
            handle: Container handle
            manager: Container manager
            scm_url: SCM URL with optional fragment
            dest_dir: Destination directory in container
            sink: Log sink
            
        Returns:
            SCM metadata dict (url, commit, branch, etc.)
        """
        # Get appropriate SCM handler
        handler = get_scm_handler(scm_url)
        
        # Perform checkout
        metadata = handler.checkout(manager, handle, dest_dir)
        
        logger.info("SCM checkout complete: %s", metadata)
        return metadata
    
    def detect_build_method(
        self,
        handle: Any,
        manager: ContainerManager,
        source_dir: str,
        sink: KojiLogSink,
    ) -> str:
        """Detect build method (make srpm vs rpmbuild -bs).
        
        Args:
            handle: Container handle
            manager: Container manager
            source_dir: Source directory
            sink: Log sink
            
        Returns:
            "make" or "rpmbuild"
        """
        # Check for Makefile with srpm target
        check_makefile = [
            "sh", "-c",
            f"test -f {source_dir}/Makefile && grep -q 'srpm:' {source_dir}/Makefile"
        ]
        exit_code = manager.exec(handle, check_makefile, sink, {})
        
        if exit_code == 0:
            return "make"
        else:
            return "rpmbuild"
    
    def build_srpm(
        self,
        handle: Any,
        manager: ContainerManager,
        source_dir: str,
        work_dir: str,
        method: str,
        sink: KojiLogSink,
        env: Dict[str, str],
    ) -> str:
        """Build SRPM from source.
        
        Args:
            handle: Container handle
            manager: Container manager
            source_dir: Source directory
            work_dir: Work directory
            method: "make" or "rpmbuild"
            sink: Log sink
            env: Environment variables
            
        Returns:
            Path pattern to built SRPM
        """
        result_dir = f"{work_dir}/result"
        manager.exec(handle, ["mkdir", "-p", result_dir], sink, env)
        
        if method == "make":
            # Use make srpm
            build_cmd = ["make", "-C", source_dir, "srpm"]
        else:
            # Use rpmbuild -bs
            # Find spec file first
            spec_file = f"{source_dir}/*.spec"  # Wildcard, use with sh -c
            build_cmd = [
                "sh", "-c",
                f"rpmbuild -bs --define '_topdir {work_dir}' --define '_sourcedir {source_dir}' --define '_srcrpmdir {result_dir}' {spec_file}"
            ]
        
        exit_code = manager.exec(handle, build_cmd, sink, env)
        if exit_code != 0:
            raise ContainerError(f"SRPM build failed with method: {method}")
        
        return f"{result_dir}/*.src.rpm"
