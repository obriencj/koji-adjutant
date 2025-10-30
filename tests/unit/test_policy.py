"""Unit tests for PolicyResolver."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from koji_adjutant.policy.resolver import CachedPolicy, PolicyResolver


class TestCachedPolicy:
    """Test CachedPolicy dataclass."""

    def test_is_valid(self):
        """Test cache validity checking."""
        policy = {"rules": []}
        cached = CachedPolicy(
            policy=policy, cached_at=datetime.now(), ttl_seconds=300
        )
        assert cached.is_valid() is True

        # Expired cache
        cached = CachedPolicy(
            policy=policy,
            cached_at=datetime.now() - timedelta(seconds=400),
            ttl_seconds=300,
        )
        assert cached.is_valid() is False


class TestPolicyResolver:
    """Test PolicyResolver class."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock koji session."""
        session = MagicMock()
        return session

    @pytest.fixture
    def resolver(self, mock_session):
        """Create a PolicyResolver instance."""
        return PolicyResolver(mock_session)

    def test_resolve_image_config_fallback(self, resolver, mock_session):
        """Test fallback to config default when policy disabled."""
        mock_session.getTag.return_value = None
        mock_session.getBuildConfig.return_value = None

        # Policy disabled (default should be True, but we'll test the fallback path)
        image = resolver.resolve_image(
            tag_name="test-tag", arch="x86_64", task_type="buildArch"
        )
        # Should get config default
        assert image == "registry/almalinux:10"

    def test_resolve_image_tag_arch_match(self, resolver, mock_session):
        """Test policy resolution with tag_arch match."""
        policy = {
            "rules": [
                {
                    "type": "tag_arch",
                    "tag": "f39-build",
                    "arch": "x86_64",
                    "image": "registry/image:f39-x86_64",
                },
                {"type": "default", "image": "registry/image:default"},
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info

        image = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert image == "registry/image:f39-x86_64"

    def test_resolve_image_tag_match(self, resolver, mock_session):
        """Test policy resolution with tag match."""
        policy = {
            "rules": [
                {
                    "type": "tag",
                    "tag": "f39-build",
                    "image": "registry/image:f39",
                },
                {"type": "default", "image": "registry/image:default"},
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info

        image = resolver.resolve_image(
            tag_name="f39-build", arch="aarch64", task_type="buildArch"
        )
        assert image == "registry/image:f39"

    def test_resolve_image_task_type_match(self, resolver, mock_session):
        """Test policy resolution with task_type match."""
        policy = {
            "rules": [
                {
                    "type": "task_type",
                    "task_type": "createrepo",
                    "image": "registry/image:repo",
                },
                {"type": "default", "image": "registry/image:default"},
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info

        image = resolver.resolve_image(
            tag_name="any-tag", arch="x86_64", task_type="createrepo"
        )
        assert image == "registry/image:repo"

    def test_resolve_image_default_fallback(self, resolver, mock_session):
        """Test policy resolution with default rule."""
        policy = {
            "rules": [
                {"type": "default", "image": "registry/image:default"},
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info

        image = resolver.resolve_image(
            tag_name="unknown-tag", arch="x86_64", task_type="buildArch"
        )
        assert image == "registry/image:default"

    def test_resolve_image_config_fallback_no_policy(self, resolver, mock_session):
        """Test fallback to config when no policy found."""
        mock_session.getTag.return_value = None
        mock_session.getBuildConfig.return_value = None

        image = resolver.resolve_image(
            tag_name="test-tag", arch="x86_64", task_type="buildArch"
        )
        assert image == "registry/almalinux:10"

    def test_resolve_image_build_config_fallback(self, resolver, mock_session):
        """Test fallback to build config when tag extra unavailable."""
        policy = {
            "rules": [
                {"type": "default", "image": "registry/image:from-config"},
            ]
        }

        mock_session.getTag.return_value = None
        build_config = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getBuildConfig.return_value = build_config

        image = resolver.resolve_image(
            tag_name="test-tag", arch="x86_64", task_type="buildArch"
        )
        assert image == "registry/image:from-config"

    def test_resolve_image_caching(self, resolver, mock_session):
        """Test that policy results are cached."""
        policy = {
            "rules": [
                {
                    "type": "tag_arch",
                    "tag": "f39-build",
                    "arch": "x86_64",
                    "image": "registry/image:f39-x86_64",
                },
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info

        # First call - should query hub
        image1 = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert image1 == "registry/image:f39-x86_64"
        assert mock_session.getTag.call_count == 1

        # Second call - should use cache
        image2 = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert image2 == "registry/image:f39-x86_64"
        # Should still be 1 (cached, no new query)
        assert mock_session.getTag.call_count == 1

    def test_resolve_image_precedence(self, resolver, mock_session):
        """Test rule precedence: tag_arch > tag > task_type > default."""
        policy = {
            "rules": [
                {"type": "default", "image": "registry/image:default"},
                {
                    "type": "task_type",
                    "task_type": "buildArch",
                    "image": "registry/image:build",
                },
                {
                    "type": "tag",
                    "tag": "f39-build",
                    "image": "registry/image:f39",
                },
                {
                    "type": "tag_arch",
                    "tag": "f39-build",
                    "arch": "x86_64",
                    "image": "registry/image:f39-x86_64",
                },
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info

        # Should match tag_arch (highest precedence)
        image = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert image == "registry/image:f39-x86_64"

        # Should match tag (second precedence)
        image = resolver.resolve_image(
            tag_name="f39-build", arch="aarch64", task_type="buildArch"
        )
        assert image == "registry/image:f39"

        # Should match task_type (third precedence)
        image = resolver.resolve_image(
            tag_name="other-tag", arch="x86_64", task_type="buildArch"
        )
        assert image == "registry/image:build"

        # Should match default (lowest precedence)
        image = resolver.resolve_image(
            tag_name="other-tag", arch="x86_64", task_type="createrepo"
        )
        assert image == "registry/image:default"

    def test_resolve_image_wrapped_policy_format(self, resolver, mock_session):
        """Test handling of wrapped policy format."""
        wrapped_policy = {
            "adjutant_image_policy": {
                "rules": [
                    {"type": "default", "image": "registry/image:wrapped"},
                ]
            }
        }

        tag_info = {"extra": {"adjutant_image_policy": wrapped_policy}}
        mock_session.getTag.return_value = tag_info

        image = resolver.resolve_image(
            tag_name="test-tag", arch="x86_64", task_type="buildArch"
        )
        assert image == "registry/image:wrapped"

    def test_resolve_image_hub_error_handling(self, resolver, mock_session):
        """Test graceful handling of hub errors."""
        mock_session.getTag.side_effect = Exception("Hub unavailable")
        mock_session.getBuildConfig.side_effect = Exception("Hub unavailable")

        # Should fall back to config default without raising
        image = resolver.resolve_image(
            tag_name="test-tag", arch="x86_64", task_type="buildArch"
        )
        assert image == "registry/almalinux:10"

    def test_resolve_image_invalid_json(self, resolver, mock_session):
        """Test handling of invalid JSON in policy."""
        tag_info = {"extra": {"adjutant_image_policy": "invalid json"}}
        mock_session.getTag.return_value = tag_info

        # Should fall back to config default
        image = resolver.resolve_image(
            tag_name="test-tag", arch="x86_64", task_type="buildArch"
        )
        assert image == "registry/almalinux:10"

    def test_invalidate_cache(self, resolver):
        """Test cache invalidation."""
        # Add some cache entries
        resolver._cache[("tag1", "x86_64")] = CachedPolicy(
            policy={"rules": []}, cached_at=datetime.now(), ttl_seconds=300
        )
        resolver._cache[("tag1", "aarch64")] = CachedPolicy(
            policy={"rules": []}, cached_at=datetime.now(), ttl_seconds=300
        )
        resolver._cache[("tag2", "x86_64")] = CachedPolicy(
            policy={"rules": []}, cached_at=datetime.now(), ttl_seconds=300
        )

        # Invalidate all
        resolver.invalidate_cache()
        assert len(resolver._cache) == 0

        # Re-add entries
        resolver._cache[("tag1", "x86_64")] = CachedPolicy(
            policy={"rules": []}, cached_at=datetime.now(), ttl_seconds=300
        )
        resolver._cache[("tag1", "aarch64")] = CachedPolicy(
            policy={"rules": []}, cached_at=datetime.now(), ttl_seconds=300
        )

        # Invalidate specific tag
        resolver.invalidate_cache(tag_name="tag1")
        assert len(resolver._cache) == 0

        # Re-add entries
        resolver._cache[("tag1", "x86_64")] = CachedPolicy(
            policy={"rules": []}, cached_at=datetime.now(), ttl_seconds=300
        )

        # Invalidate specific tag+arch
        resolver.invalidate_cache(tag_name="tag1", arch="x86_64")
        assert len(resolver._cache) == 0
