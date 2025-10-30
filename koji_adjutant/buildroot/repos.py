"""Repository configuration for buildroot initialization.

Handles querying koji hub for repository information and generating
/etc/yum.repos.d/koji.repo configuration files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_repo_info(session: Any, repo_id: int, strict: bool = True) -> Dict[str, Any]:
    """Query koji hub for repository information.

    Args:
        session: Koji session object with repoInfo method
        repo_id: Repository ID to query
        strict: If True, raise exception if repo not found

    Returns:
        Dict with repo information (id, create_event, tag_id, etc.)

    Raises:
        koji.GenericError: If repo not found and strict=True
    """
    try:
        repo_info = session.repoInfo(repo_id, strict=strict)
        logger.debug("Retrieved repo info for repo_id=%d: %s", repo_id, repo_info)
        return repo_info
    except Exception as exc:
        logger.error("Failed to get repo info for repo_id=%d: %s", repo_id, exc)
        raise


def get_tag_repos(
    session: Any, tag_id: int, event_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Query koji hub for repositories associated with a tag.

    Args:
        session: Koji session object
        tag_id: Tag ID to query repos for
        event_id: Optional event ID for historical queries

    Returns:
        List of repo info dicts
    """
    try:
        # Try to get repo for tag
        # session.getRepo(tag_id) returns repo info for tag
        repo_info = session.getRepo(tag_id, event=event_id)
        if repo_info:
            # getRepo may return single repo or list
            if isinstance(repo_info, list):
                return repo_info
            return [repo_info]
        return []
    except Exception as exc:
        logger.warning("Failed to get repos for tag_id=%d: %s", tag_id, exc)
        return []


def generate_repo_config(
    session: Any,
    tag_id: int,
    repo_id: int,
    arch: str,
    event_id: Optional[int] = None,
    topurl: Optional[str] = None,
) -> str:
    """Generate /etc/yum.repos.d/koji.repo file content.

    Args:
        session: Koji session object
        tag_id: Build tag ID
        repo_id: Repository ID
        arch: Target architecture
        event_id: Optional event ID for historical queries
        topurl: Optional koji topurl for constructing repo URLs.
                If None, tries to get from repo_info or config.

    Returns:
        String content for /etc/yum.repos.d/koji.repo file

    Raises:
        koji.GenericError: If repo info cannot be retrieved
    """
    # Get repo info
    repo_info = get_repo_info(session, repo_id, strict=True)

    # Get tag info to find tag name
    try:
        tag_info = session.getTag(tag_id, strict=True, event=event_id)
        tag_name = tag_info.get("name", str(tag_id))
    except Exception:
        tag_name = str(tag_id)
        logger.warning("Could not get tag name for tag_id=%d, using ID", tag_id)

    # Determine topurl
    if topurl is None:
        # Try to get from session or config
        # For now, construct from repo_info if available
        # In koji-boxed, repos are typically at /mnt/koji/repos/<tag>/<arch>/
        # For HTTP, use session.options.topurl if available
        try:
            if hasattr(session, "options") and hasattr(session.options, "topurl"):
                topurl = session.options.topurl
            else:
                # Fallback: use file:// for local repos
                topurl = "/mnt/koji"
        except Exception:
            topurl = "/mnt/koji"

    # Construct repo path
    # Format: <topurl>/repos/<tag>/<repo_id>/<arch>/
    # Or: <topurl>/repos/<tag>/latest/<arch>/ (for latest repo)
    repo_path = f"{topurl}/repos/{tag_name}/{repo_id}/{arch}/"

    # Generate repo config content
    repo_content = f"""[koji-{tag_name}]
name=Koji Repository for {tag_name}
baseurl=file://{repo_path}
enabled=1
gpgcheck=0
priority=10
skip_if_unavailable=0
"""

    # If topurl is HTTP, use http:// URL instead
    if topurl.startswith("http"):
        repo_path_http = f"{topurl}/repos/{tag_name}/{repo_id}/{arch}/"
        repo_content = f"""[koji-{tag_name}]
name=Koji Repository for {tag_name}
baseurl={repo_path_http}
enabled=1
gpgcheck=0
priority=10
skip_if_unavailable=0
"""

    logger.debug("Generated repo config for tag=%s repo_id=%d arch=%s", tag_name, repo_id, arch)
    return repo_content


def write_repo_file(repo_config: str, target_dir: Path, filename: str = "koji.repo") -> Path:
    """Write repository configuration to file.

    Args:
        repo_config: Repository config content (from generate_repo_config)
        target_dir: Directory to write repo file to (e.g., /etc/yum.repos.d)
        filename: Repo file name (default: koji.repo)

    Returns:
        Path to written repo file
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    repo_file = target_dir / filename
    repo_file.write_text(repo_config)
    logger.debug("Wrote repo config to %s", repo_file)

    return repo_file
