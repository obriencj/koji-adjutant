"""Configuration management for koji-adjutant.

This module provides configuration parsing from kojid.conf files and
maintains backward compatibility with Phase 1 hardcoded defaults.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Mapping, Optional

try:
    import koji
except ImportError:
    koji = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Module-level config cache
_config: Optional[Dict[str, Any]] = None
_options: Optional[Any] = None  # Kojid options object (initialized by kojid main)


def initialize(options: Any) -> None:
    """Initialize config module with kojid options object.

    This should be called once at kojid startup with the parsed options object.
    Avoids duplicate config file parsing.

    Args:
        options: Parsed options object from kojid get_options()
    """
    global _options
    _options = options
    logger.debug("Config module initialized with kojid options object")


def _parse_config_file(config_file: Optional[str] = None) -> Dict[str, Any]:
    """Parse kojid.conf file using koji library (FALLBACK ONLY).

    NOTE: This is now a fallback path. When kojid initializes config module
    via initialize(options), settings come from the options object instead.
    This fallback only runs if config module is used standalone (without kojid).

    Args:
        config_file: Optional path to config file. If None, uses default.

    Returns:
        Empty dict (settings come from options object when available)
    """
    logger.debug("Using fallback config parsing (options object not initialized)")
    # Return empty dict - when used with kojid, settings come from options object
    # This avoids duplicate config parsing and the NoSectionError
    return {}


def _get_config() -> Dict[str, Any]:
    """Get parsed config dict, initializing if needed.

    Returns:
        Config dict with [adjutant] section values.
    """
    global _config
    if _config is None:
        # Try to parse config file
        config_file = os.environ.get("KOJI_CONFIG")
        _config = _parse_config_file(config_file)
    return _config


def _get_config_value(
    key: str,
    default: Any,
    env_var: Optional[str] = None,
    converter: Optional[Callable[[Any], Any]] = None,
) -> Any:
    """Get config value with fallback chain: env var ? config file ? default.

    Args:
        key: Config key name (in [adjutant] section)
        default: Default value if not found
        env_var: Optional environment variable name (e.g., KOJI_ADJUTANT_KEY)
        converter: Optional function to convert string value (e.g., int, bool)

    Returns:
        Config value (converted if converter provided)
    """
    # Check environment variable first (highest priority)
    if env_var:
        env_value = os.environ.get(env_var)
        if env_value is not None:
            if converter:
                try:
                    return converter(env_value)
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "Invalid value for %s: %s, using default", env_var, env_value
                    )
            return env_value

    # Check options object (if initialized by kojid)
    if _options is not None:
        option_key = f"adjutant_{key}"
        if hasattr(_options, option_key):
            value = getattr(_options, option_key)
            if converter and isinstance(value, str):
                try:
                    return converter(value)
                except (ValueError, TypeError) as exc:
                    logger.warning("Invalid value for %s: %s, using default", key, value)
            return value

    # Check config file (fallback for standalone usage)
    config = _get_config()
    value = config.get(key)
    if value is not None:
        if converter:
            try:
                return converter(value)
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Invalid value for config key %s: %s, using default", key, value
                )
        return value

    # Return default
    return default


def _parse_bool(value: Any) -> bool:
    """Parse boolean value from config (string or bool).

    Accepts: True, "true", "True", "1", "yes", "on" ? True
             False, "false", "False", "0", "no", "off" ? False
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)


def _parse_timeouts(value: Any) -> Dict[str, int]:
    """Parse container timeouts from config.

    Accepts formats:
    - Dict: {"pull": 300, "start": 60, "stop_grace": 20}
    - String: "pull=300,start=60,stop_grace=20"
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        timeouts = {}
        for item in value.split(","):
            if "=" in item:
                key, val = item.split("=", 1)
                try:
                    timeouts[key.strip()] = int(val.strip())
                except ValueError:
                    logger.warning("Invalid timeout value: %s", item)
        return timeouts
    return {"pull": 300, "start": 60, "stop_grace": 20}


def _parse_mounts(value: Any) -> list[str]:
    """Parse container mounts from config.

    Accepts:
    - List: ["/mnt/koji:/mnt/koji:rw:Z"]
    - String (space or comma separated): "/mnt/koji:/mnt/koji:rw:Z"
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # Split by comma or space
        mounts = []
        for item in value.replace(",", " ").split():
            if item.strip():
                mounts.append(item.strip())
        return mounts
    return ["/mnt/koji:/mnt/koji:rw:Z"]


def _parse_labels(value: Any) -> Mapping[str, str]:
    """Parse container labels from config.

    Accepts:
    - Dict: {"key": "value"}
    - String: "key1=value1,key2=value2"
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        labels = {}
        for item in value.split(","):
            if "=" in item:
                key, val = item.split("=", 1)
                labels[key.strip()] = val.strip()
        return labels
    return {}


def adjutant_task_image_default() -> str:
    """Default task image (ADR 0001).

    Falls back to Phase 1 default if config unavailable.
    """
    return _get_config_value(
        "task_image_default",
        "registry/almalinux:10",
        env_var="KOJI_ADJUTANT_TASK_IMAGE_DEFAULT",
    )


def adjutant_image_pull_policy() -> str:
    """Image pull policy: 'if-not-present' | 'always' | 'never'."""
    return _get_config_value(
        "image_pull_policy",
        "if-not-present",
        env_var="KOJI_ADJUTANT_IMAGE_PULL_POLICY",
    )


def adjutant_container_mounts() -> list[str]:
    """Default mounts expressed as strings 'src:dst:mode:label'.

    Phase 1 default: mount /mnt/koji with :Z labeling.
    """
    value = _get_config_value(
        "container_mounts",
        ["/mnt/koji:/mnt/koji:rw:Z"],
        env_var="KOJI_ADJUTANT_CONTAINER_MOUNTS",
    )
    return _parse_mounts(value)


def adjutant_network_enabled() -> bool:
    """Network enabled by default (ADR 0001)."""
    return _get_config_value(
        "network_enabled",
        True,
        env_var="KOJI_ADJUTANT_NETWORK_ENABLED",
        converter=_parse_bool,
    )


def adjutant_container_labels() -> Mapping[str, str]:
    """Base labels to apply to all containers.

    Include worker id if available in environment/config in future.
    """
    value = _get_config_value(
        "container_labels",
        {},
        env_var="KOJI_ADJUTANT_CONTAINER_LABELS",
    )
    return _parse_labels(value)


def adjutant_container_timeouts() -> Dict[str, int]:
    """Container lifecycle timeouts in seconds.

    Keys: pull, start, stop_grace
    """
    value = _get_config_value(
        "container_timeouts",
        {"pull": 300, "start": 60, "stop_grace": 20},
        env_var="KOJI_ADJUTANT_CONTAINER_TIMEOUTS",
    )
    return _parse_timeouts(value)


def adjutant_policy_enabled() -> bool:
    """Enable hub policy-driven image selection (Phase 2.1)."""
    return _get_config_value(
        "policy_enabled",
        True,
        env_var="KOJI_ADJUTANT_POLICY_ENABLED",
        converter=_parse_bool,
    )


def adjutant_policy_cache_ttl() -> int:
    """Policy cache TTL in seconds (default: 300)."""
    return _get_config_value(
        "policy_cache_ttl",
        300,
        env_var="KOJI_ADJUTANT_POLICY_CACHE_TTL",
        converter=int,
    )


def adjutant_buildroot_enabled() -> bool:
    """Enable buildroot initialization (Phase 2.2).

    When enabled, BuildArchAdapter will use BuildrootInitializer to set up
    repositories, dependencies, and build environment. When disabled, falls back
    to Phase 1 simple build mode.
    """
    return _get_config_value(
        "buildroot_enabled",
        True,  # Default to enabled for Phase 2.2
        env_var="KOJI_ADJUTANT_BUILDROOT_ENABLED",
        converter=_parse_bool,
    )


def adjutant_monitoring_enabled() -> bool:
    """Enable operational monitoring server (Phase 2.3)."""
    return _get_config_value(
        "monitoring_enabled",
        False,
        env_var="KOJI_ADJUTANT_MONITORING_ENABLED",
        converter=_parse_bool,
    )


def adjutant_monitoring_bind() -> str:
    """Monitoring server bind address (default: "127.0.0.1:8080")."""
    value = _get_config_value(
        "monitoring_bind",
        "127.0.0.1:8080",
        env_var="KOJI_ADJUTANT_MONITORING_BIND",
    )
    # Validate format: "host:port"
    if ":" not in value:
        logger.warning("Invalid monitoring_bind format, using default: 127.0.0.1:8080")
        return "127.0.0.1:8080"
    return value


def adjutant_monitoring_container_history_ttl() -> int:
    """Container history TTL in seconds (default: 3600)."""
    return _get_config_value(
        "monitoring_container_history_ttl",
        3600,
        env_var="KOJI_ADJUTANT_MONITORING_CONTAINER_HISTORY_TTL",
        converter=int,
    )


def adjutant_monitoring_task_history_ttl() -> int:
    """Task history TTL in seconds (default: 3600)."""
    return _get_config_value(
        "monitoring_task_history_ttl",
        3600,
        env_var="KOJI_ADJUTANT_MONITORING_TASK_HISTORY_TTL",
        converter=int,
    )


def adjutant_podman_socket() -> str:
    """Podman socket path (default: unix:///var/run/podman.sock).

    URI format expected by podman-py PodmanClient:
    - unix:///var/run/podman.sock (local Unix socket)
    - http+unix:///var/run/podman.sock (HTTP over Unix socket)
    """
    return _get_config_value(
        "podman_socket",
        "unix:///var/run/podman.sock",
        env_var="KOJI_ADJUTANT_PODMAN_SOCKET",
    )


def adjutant_host_mount_map() -> Dict[str, str]:
    """Get container-to-host mount path mappings for podman-in-podman.

    When running inside a container that uses host Podman socket, we need to
    translate container paths to host paths for volume mounts.

    Returns dict like: {"/mnt/koji": "/host/path/to/koji"}
    """
    # Check environment variable first (manual override)
    env_map = os.environ.get("KOJI_ADJUTANT_HOST_MOUNT_MAP")
    if env_map:
        # Format: "/mnt/koji:/host/koji,/other:/host/other"
        result = {}
        for pair in env_map.split(","):
            if ":" in pair:
                container_path, host_path = pair.split(":", 1)
                result[container_path.strip()] = host_path.strip()
        return result

    # Auto-detect from current container's mounts
    return _introspect_container_mounts()


def _introspect_container_mounts() -> Dict[str, str]:
    """Auto-detect host mount paths by introspecting current container.

    Returns dict mapping container paths to host paths.
    """
    mount_map = {}

    try:
        # Read /proc/self/mountinfo to find bind mounts
        with open("/proc/self/mountinfo", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 10:
                    continue

                # mountinfo format: [mount_id] [parent_id] [major:minor] [root] [mount_point] ...
                mount_point = parts[4]  # Where it's mounted in container

                # Look for optional fields separator
                try:
                    sep_idx = parts.index("-")
                    fs_type = parts[sep_idx + 1]
                    source = parts[sep_idx + 2] if len(parts) > sep_idx + 2 else None

                    # Only map bind mounts
                    if source and mount_point.startswith("/mnt"):
                        mount_map[mount_point] = source
                        logger.debug("Detected mount: %s -> %s", mount_point, source)
                except (ValueError, IndexError):
                    continue

    except Exception as exc:
        logger.warning("Failed to introspect container mounts: %s", exc)

    return mount_map


def reset_config() -> None:
    """Reset config cache (useful for testing)."""
    global _config, _options
    _config = None
    _options = None
