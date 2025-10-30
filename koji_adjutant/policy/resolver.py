"""PolicyResolver implementation for hub-driven image selection.

Implements ADR 0003: Hub Policy-Driven Container Image Selection.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .. import config as adj_config

logger = logging.getLogger(__name__)


@dataclass
class CachedPolicy:
    """Cached policy with TTL tracking."""

    policy: Dict[str, Any]
    cached_at: datetime
    ttl_seconds: int

    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        age = (datetime.now() - self.cached_at).total_seconds()
        return age < self.ttl_seconds


class PolicyResolver:
    """Resolves container images from hub policy or config fallback.

    Per ADR 0003, this class:
    1. Queries hub for policy (tag extra data → build config extra)
    2. Evaluates rules in precedence order (tag_arch → tag → task_type → default)
    3. Caches results with TTL to reduce hub queries
    4. Falls back to config default when hub unavailable or no match

    Example:
        resolver = PolicyResolver(session, config)
        image = resolver.resolve_image(
            tag_name="f39-build",
            arch="x86_64",
            task_type="buildArch",
        )
    """

    def __init__(self, session: Any, config: Optional[Dict[str, Any]] = None):
        """Initialize PolicyResolver.

        Args:
            session: Koji ClientSession instance (must have getTag, getBuildConfig methods)
            config: Optional config dict (uses adj_config module if None)
        """
        self.session = session
        self.config = config
        self._cache: Dict[tuple[str, str], CachedPolicy] = {}
        self._ttl_seconds = adj_config.adjutant_policy_cache_ttl()
        self._policy_enabled = adj_config.adjutant_policy_enabled()

    def resolve_image(
        self,
        tag_name: str,
        arch: str,
        task_type: str,
        event_id: Optional[int] = None,
    ) -> str:
        """Resolve container image from hub policy or config fallback.

        Evaluation order:
        1. Check cache (by tag+arch key)
        2. Query hub for policy (if enabled)
        3. Evaluate rules in precedence order
        4. Cache result (if from hub)
        5. Fallback to config default if no match

        Args:
            tag_name: Build tag name (e.g., "f39-build")
            arch: Architecture (e.g., "x86_64")
            task_type: Task type (e.g., "buildArch", "createrepo")
            event_id: Optional event ID for historical queries

        Returns:
            Container image reference (e.g., "registry/image:tag")
        """
        # Check cache first
        cache_key = (tag_name, arch)
        cached = self._get_cached_policy(cache_key)
        if cached:
            logger.debug(
                "Using cached policy for tag=%s arch=%s", tag_name, arch
            )
            image = self._evaluate_policy(cached.policy, tag_name, arch, task_type)
            if image:
                return image

        # If policy disabled, skip hub query
        if not self._policy_enabled:
            logger.debug("Policy disabled, using config default")
            return self._config_default()

        # Query hub for policy
        policy = self._fetch_policy(tag_name, event_id)
        if policy:
            # Cache the policy
            self._cache_policy(cache_key, policy)
            # Evaluate and return
            image = self._evaluate_policy(policy, tag_name, arch, task_type)
            if image:
                return image
            # Policy exists but no rule matched, use policy default if available
            logger.debug(
                "Policy found but no rule matched for tag=%s arch=%s task_type=%s",
                tag_name,
                arch,
                task_type,
            )

        # Fallback to config default
        logger.debug(
            "Falling back to config default for tag=%s arch=%s", tag_name, arch
        )
        return self._config_default()

    def _fetch_policy(
        self, tag_name: str, event_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch policy from hub (tag extra data → build config extra).

        Args:
            tag_name: Build tag name
            event_id: Optional event ID

        Returns:
            Policy dict or None if not found/unavailable
        """
        try:
            # Try tag extra data first
            tag_info = self.session.getTag(tag_name, event=event_id, strict=False)
            if tag_info:
                extra_data = tag_info.get("extra", {})
                policy_json = extra_data.get("adjutant_image_policy")
                if policy_json:
                    if isinstance(policy_json, str):
                        policy = json.loads(policy_json)
                    else:
                        policy = policy_json
                    logger.debug("Found policy in tag extra data for tag=%s", tag_name)
                    return self._extract_policy_dict(policy)

            # Try build config extra data as fallback
            build_config = self.session.getBuildConfig(tag_name, event=event_id)
            if build_config:
                extra_data = build_config.get("extra", {})
                policy_json = extra_data.get("adjutant_image_policy")
                if policy_json:
                    if isinstance(policy_json, str):
                        policy = json.loads(policy_json)
                    else:
                        policy = policy_json
                    logger.debug(
                        "Found policy in build config extra data for tag=%s", tag_name
                    )
                    return self._extract_policy_dict(policy)

        except Exception as exc:
            logger.warning(
                "Failed to fetch policy from hub for tag=%s: %s", tag_name, exc
            )
            # Don't cache failures - allow retry on next task

        return None

    def _extract_policy_dict(self, policy_data: Any) -> Optional[Dict[str, Any]]:
        """Extract policy dict from various formats.

        Handles:
        - Direct dict: {"rules": [...]}
        - Wrapped: {"adjutant_image_policy": {"rules": [...]}}
        - JSON string: '{"rules": [...]}'

        Args:
            policy_data: Policy data in various formats

        Returns:
            Policy dict with "rules" key, or None if invalid
        """
        if isinstance(policy_data, str):
            try:
                policy_data = json.loads(policy_data)
            except json.JSONDecodeError as exc:
                logger.error("Invalid JSON in policy: %s", exc)
                return None

        if not isinstance(policy_data, dict):
            logger.error("Policy must be a dict, got %s", type(policy_data))
            return None

        # Handle wrapped format: {"adjutant_image_policy": {...}}
        if "adjutant_image_policy" in policy_data:
            policy_data = policy_data["adjutant_image_policy"]

        # Ensure it has "rules" key
        if "rules" not in policy_data:
            logger.error("Policy missing 'rules' key")
            return None

        return policy_data

    def _evaluate_policy(
        self, policy: Dict[str, Any], tag_name: str, arch: str, task_type: str
    ) -> Optional[str]:
        """Evaluate policy rules in precedence order.

        Precedence:
        1. tag_arch: Match specific tag + architecture
        2. tag: Match tag regardless of architecture
        3. task_type: Match task type
        4. default: Fallback rule

        Args:
            policy: Policy dict with "rules" key
            tag_name: Build tag name
            arch: Architecture
            task_type: Task type

        Returns:
            Image string if match found, None otherwise
        """
        rules = policy.get("rules", [])
        if not isinstance(rules, list):
            logger.error("Policy rules must be a list")
            return None

        default_image = None

        for rule in rules:
            if not isinstance(rule, dict):
                logger.warning("Invalid rule format (not a dict): %s", rule)
                continue

            rule_type = rule.get("type")
            if rule_type == "tag_arch":
                if rule.get("tag") == tag_name and rule.get("arch") == arch:
                    image = rule.get("image")
                    if image:
                        logger.debug(
                            "Matched tag_arch rule: tag=%s arch=%s -> %s",
                            tag_name,
                            arch,
                            image,
                        )
                        return image
            elif rule_type == "tag":
                if rule.get("tag") == tag_name:
                    image = rule.get("image")
                    if image:
                        logger.debug(
                            "Matched tag rule: tag=%s -> %s", tag_name, image
                        )
                        return image
            elif rule_type == "task_type":
                if rule.get("task_type") == task_type:
                    image = rule.get("image")
                    if image:
                        logger.debug(
                            "Matched task_type rule: task_type=%s -> %s",
                            task_type,
                            image,
                        )
                        return image
            elif rule_type == "default":
                # Store default but continue checking for more specific matches
                default_image = rule.get("image")
                logger.debug("Found default rule: %s", default_image)

        # Return default if found, otherwise None
        if default_image:
            logger.debug("Using policy default image: %s", default_image)
        return default_image

    def _cache_policy(self, cache_key: tuple[str, str], policy: Dict[str, Any]) -> None:
        """Cache policy with TTL.

        Args:
            cache_key: (tag_name, arch) tuple
            policy: Policy dict to cache
        """
        self._cache[cache_key] = CachedPolicy(
            policy=policy,
            cached_at=datetime.now(),
            ttl_seconds=self._ttl_seconds,
        )
        logger.debug("Cached policy for key=%s", cache_key)

    def _get_cached_policy(
        self, cache_key: tuple[str, str]
    ) -> Optional[CachedPolicy]:
        """Get cached policy if valid.

        Args:
            cache_key: (tag_name, arch) tuple

        Returns:
            CachedPolicy if valid, None otherwise
        """
        cached = self._cache.get(cache_key)
        if cached and cached.is_valid():
            return cached
        # Remove expired entry
        if cached:
            del self._cache[cache_key]
            logger.debug("Cache entry expired for key=%s", cache_key)
        return None

    def _config_default(self) -> str:
        """Get config default image."""
        return adj_config.adjutant_task_image_default()

    def invalidate_cache(self, tag_name: Optional[str] = None, arch: Optional[str] = None) -> None:
        """Invalidate cache entries.

        Args:
            tag_name: Optional tag name (if None, invalidates all)
            arch: Optional architecture (if None, invalidates all for tag)
        """
        if tag_name is None:
            # Invalidate all
            self._cache.clear()
            logger.debug("Invalidated all cache entries")
        elif arch is None:
            # Invalidate all entries for this tag
            keys_to_remove = [
                key for key in self._cache.keys() if key[0] == tag_name
            ]
            for key in keys_to_remove:
                del self._cache[key]
            logger.debug("Invalidated cache entries for tag=%s", tag_name)
        else:
            # Invalidate specific entry
            cache_key = (tag_name, arch)
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.debug("Invalidated cache entry for tag=%s arch=%s", tag_name, arch)
