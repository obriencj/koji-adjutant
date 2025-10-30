"""Dependency resolution for buildroot initialization.

Handles parsing SRPM spec files for BuildRequires and querying koji hub
for buildroot package lists.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def extract_buildrequires_from_srpm(srpm_path: Path) -> List[str]:
    """Extract BuildRequires from SRPM spec file.

    Uses rpm command to query SRPM for BuildRequires dependencies.

    Args:
        srpm_path: Path to SRPM file

    Returns:
        List of package names from BuildRequires (without version constraints)

    Raises:
        FileNotFoundError: If SRPM file doesn't exist
        subprocess.CalledProcessError: If rpm command fails
    """
    if not srpm_path.exists():
        raise FileNotFoundError(f"SRPM file not found: {srpm_path}")

    try:
        # Query SRPM for BuildRequires
        # rpm -qp --requires <srpm> | grep -E "^BuildRequires" extracts BuildRequires lines
        result = subprocess.run(
            ["rpm", "-qp", "--requires", str(srpm_path)],
            capture_output=True,
            text=True,
            check=True,
        )

        build_requires = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("BuildRequires:"):
                # Format: "BuildRequires: package-name [version-constraint]"
                # Extract package name (first word after "BuildRequires:")
                parts = line.split(":", 1)
                if len(parts) == 2:
                    req_line = parts[1].strip()
                    # Parse package name (may have version constraints)
                    # Examples: "gcc", "python3-devel >= 3.6", "perl(Test::More)"
                    # Extract first word (package name or provide name)
                    package = req_line.split()[0] if req_line.split() else ""
                    if package:
                        build_requires.append(package)

        logger.debug(
            "Extracted %d BuildRequires from %s: %s",
            len(build_requires),
            srpm_path,
            build_requires,
        )
        return build_requires

    except subprocess.CalledProcessError as exc:
        logger.error("Failed to extract BuildRequires from %s: %s", srpm_path, exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error extracting BuildRequires: %s", exc)
        raise


def get_buildroot_packages(
    session: Any,
    tag_id: int,
    arch: str,
    event_id: Optional[int] = None,
) -> List[str]:
    """Query koji hub for buildroot package list.

    Args:
        session: Koji session object with getBuildConfig method
        tag_id: Build tag ID
        arch: Target architecture
        event_id: Optional event ID for historical queries

    Returns:
        List of package names to install in buildroot

    Note:
        This queries koji's buildroot configuration which may include:
        - Install groups (e.g., "build", "srpm-build")
        - Extra packages
        - Tag-specific buildroot packages
    """
    try:
        build_config = session.getBuildConfig(tag_id, event=event_id)
        if not build_config:
            logger.warning("No build config found for tag_id=%d", tag_id)
            return []

        packages = []

        # Extract install groups
        install_groups = build_config.get("install_groups", [])
        if install_groups:
            logger.debug("Found install groups: %s", install_groups)
            # Note: Resolving package groups to individual packages requires
            # additional koji API calls or dnf group info. For now, we'll
            # return group names and let dnf handle resolution during install.

        # Extract extra packages
        extra_packages = build_config.get("extra_packages", [])
        if extra_packages:
            packages.extend(extra_packages)
            logger.debug("Found extra packages: %s", extra_packages)

        # Extract tag extra data for buildroot packages
        try:
            tag_info = session.getTag(tag_id, strict=True, event=event_id)
            extra = tag_info.get("extra", {})
            if "buildroot_packages" in extra:
                tag_packages = extra["buildroot_packages"]
                if isinstance(tag_packages, list):
                    packages.extend(tag_packages)
                elif isinstance(tag_packages, str):
                    # Space or comma separated
                    tag_packages_list = tag_packages.replace(",", " ").split()
                    packages.extend(tag_packages_list)
                logger.debug("Found tag buildroot packages: %s", tag_packages)
        except Exception as exc:
            logger.debug("Could not get tag extra data: %s", exc)

        # Add install groups as "@group" for dnf
        for group in install_groups:
            packages.append(f"@{group}")

        logger.debug("Resolved buildroot packages for tag_id=%d: %s", tag_id, packages)
        return packages

    except Exception as exc:
        logger.warning("Failed to get buildroot packages: %s", exc)
        return []


def resolve_build_dependencies(
    session: Any,
    tag_id: int,
    arch: str,
    srpm_path: Optional[Path] = None,
    event_id: Optional[int] = None,
) -> List[str]:
    """Resolve complete build dependency list.

    Combines dependencies from:
    1. SRPM BuildRequires (if srpm_path provided)
    2. Koji buildroot configuration (install groups, extra packages)
    3. Tag extra data (buildroot_packages)

    Args:
        session: Koji session object
        tag_id: Build tag ID
        arch: Target architecture
        srpm_path: Optional path to SRPM file
        event_id: Optional event ID for historical queries

    Returns:
        List of package names and groups for dnf install
        (groups are prefixed with "@")

    Example:
        ["gcc", "python3-devel", "@build", "custom-package"]
    """
    dependencies: Set[str] = set()

    # 1. Extract BuildRequires from SRPM
    if srpm_path and srpm_path.exists():
        try:
            srpm_deps = extract_buildrequires_from_srpm(srpm_path)
            dependencies.update(srpm_deps)
        except Exception as exc:
            logger.warning("Failed to extract SRPM dependencies: %s", exc)

    # 2. Query koji buildroot config
    buildroot_packages = get_buildroot_packages(session, tag_id, arch, event_id=event_id)
    dependencies.update(buildroot_packages)

    # Return as sorted list for consistency
    result = sorted(dependencies)
    logger.info(
        "Resolved %d build dependencies for tag_id=%d arch=%s",
        len(result),
        tag_id,
        arch,
    )
    return result
