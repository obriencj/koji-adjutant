"""Build environment setup for buildroot initialization.

Provides RPM macro generation, environment variable configuration, and
directory structure setup matching mock's buildroot behavior.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def generate_rpm_macros(
    work_dir: Path,
    dist: Optional[str] = None,
    buildroot_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """Generate RPM macro definitions matching mock's buildroot.

    Args:
        work_dir: Base work directory (e.g., /builddir)
        dist: Distribution tag (e.g., ".almalinux10"). If None, auto-detects.
        buildroot_dir: Optional buildroot directory. Defaults to work_dir/BUILDROOT.

    Returns:
        Dict mapping macro names to values (without % prefix)
    """
    if buildroot_dir is None:
        buildroot_dir = work_dir / "BUILDROOT"

    # Default dist if not provided (can be overridden per distro)
    if dist is None:
        dist = ".almalinux10"  # Default for AlmaLinux 10

    macros = {
        "dist": dist,
        "_topdir": str(work_dir),
        "_builddir": str(work_dir / "build"),
        "_rpmdir": str(work_dir / "result"),
        "_srcrpmdir": str(work_dir / "result"),
        "_sourcedir": str(work_dir / "work"),
        "_specdir": str(work_dir / "work"),
        "_buildrootdir": str(buildroot_dir),
    }

    return macros


def setup_build_environment(
    work_dir: Path,
    task_id: int,
    build_tag: str,
    arch: str,
    repo_id: int,
    dist: Optional[str] = None,
) -> Dict[str, str]:
    """Generate environment variables for build execution.

    Args:
        work_dir: Base work directory
        task_id: Koji task ID
        build_tag: Build tag name
        arch: Target architecture
        repo_id: Repository ID
        dist: Optional distribution tag for RPM macros

    Returns:
        Dict of environment variable names to values
    """
    buildroot_dir = work_dir / "BUILDROOT"
    build_dir = work_dir / "build"

    env = {
        # Koji task context
        "KOJI_TASK_ID": str(task_id),
        "KOJI_BUILD_TAG": str(build_tag),
        "KOJI_ARCH": arch,
        "KOJI_REPO_ID": str(repo_id),
        # Build directories
        "BUILDROOT": str(buildroot_dir),
        "RPM_BUILD_DIR": str(build_dir),
        "_topdir": str(work_dir),
        # Locale and timezone
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TZ": "UTC",
        # Home directory (for koji user)
        "HOME": str(work_dir),
    }

    # Add RPM macros as environment variables (rpmbuild reads these)
    macros = generate_rpm_macros(work_dir, dist=dist, buildroot_dir=buildroot_dir)
    for macro_name, macro_value in macros.items():
        # RPM macros accessible via environment variables with RPM_ prefix
        env[f"RPM_{macro_name}"] = macro_value

    return env


def create_directory_structure(work_dir: Path) -> None:
    """Create standard buildroot directory structure.

    Creates directories matching mock's layout:
    - work_dir/work/     (sources, SRPMs)
    - work_dir/build/    (build output)
    - work_dir/BUILDROOT/ (install root)
    - work_dir/result/   (final RPMs)

    Args:
        work_dir: Base work directory to create structure under
    """
    directories = [
        work_dir / "work",
        work_dir / "build",
        work_dir / "BUILDROOT",
        work_dir / "result",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug("Created directory: %s", directory)
