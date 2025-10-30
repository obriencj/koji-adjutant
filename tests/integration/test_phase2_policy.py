"""Phase 2.1 Integration Tests: Policy Resolution and Config Parsing.

This test suite validates Phase 2.1 implementation:
- Policy resolution with mock hub
- Config parsing with sample kojid.conf
- End-to-end image selection flow
- Fallback behavior validation
- Cache effectiveness tests

Tests use mocked koji hub XMLRPC calls and do not require live hub.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import pytest

from koji_adjutant import config as adj_config
from koji_adjutant.policy.resolver import PolicyResolver, CachedPolicy
from koji_adjutant.task_adapters.buildarch import BuildArchAdapter
from koji_adjutant.task_adapters.createrepo import CreaterepoAdapter
from koji_adjutant.task_adapters.base import TaskContext


class TestPolicyResolutionIntegration:
    """Integration tests for PolicyResolver with mock hub."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock koji session."""
        session = MagicMock()
        return session

    @pytest.fixture
    def resolver(self, mock_session):
        """Create a PolicyResolver instance."""
        return PolicyResolver(mock_session)

    def test_policy_resolution_with_tag_extra_data(self, resolver, mock_session):
        """Test policy resolution when policy is in tag extra data."""
        # Setup policy in tag extra data
        policy = {
            "rules": [
                {
                    "type": "tag_arch",
                    "tag": "f39-build",
                    "arch": "x86_64",
                    "image": "registry/koji-adjutant-task:f39-x86_64",
                },
                {"type": "default", "image": "registry/koji-adjutant-task:default"},
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info
        mock_session.getBuildConfig.return_value = None

        # Resolve image
        image = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )

        assert image == "registry/koji-adjutant-task:f39-x86_64"
        mock_session.getTag.assert_called_once_with("f39-build", event=None, strict=False)

    def test_policy_resolution_with_build_config_fallback(self, resolver, mock_session):
        """Test policy resolution falls back to build config when tag extra unavailable."""
        policy = {
            "rules": [
                {"type": "default", "image": "registry/koji-adjutant-task:from-config"},
            ]
        }

        mock_session.getTag.return_value = None
        build_config = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getBuildConfig.return_value = build_config

        image = resolver.resolve_image(
            tag_name="test-tag", arch="x86_64", task_type="buildArch"
        )

        assert image == "registry/koji-adjutant-task:from-config"
        mock_session.getTag.assert_called_once()
        mock_session.getBuildConfig.assert_called_once_with("test-tag", event=None)

    def test_policy_resolution_fallback_to_config_default(self, resolver, mock_session):
        """Test fallback to config default when hub unavailable."""
        mock_session.getTag.side_effect = Exception("Hub unavailable")
        mock_session.getBuildConfig.side_effect = Exception("Hub unavailable")

        # Should fall back to config default without raising
        image = resolver.resolve_image(
            tag_name="test-tag", arch="x86_64", task_type="buildArch"
        )

        assert image == "registry/almalinux:10"  # Config default

    def test_policy_cache_effectiveness(self, resolver, mock_session):
        """Test that policy caching reduces hub queries."""
        policy = {
            "rules": [
                {
                    "type": "tag_arch",
                    "tag": "f39-build",
                    "arch": "x86_64",
                    "image": "registry/koji-adjutant-task:f39-x86_64",
                },
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info

        # First call - should query hub
        image1 = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert image1 == "registry/koji-adjutant-task:f39-x86_64"
        assert mock_session.getTag.call_count == 1

        # Second call - should use cache (no new query)
        image2 = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert image2 == "registry/koji-adjutant-task:f39-x86_64"
        assert mock_session.getTag.call_count == 1  # Still 1, cached

        # Different arch - should query again (different cache key)
        image3 = resolver.resolve_image(
            tag_name="f39-build", arch="aarch64", task_type="buildArch"
        )
        # Should fall back to config default (no rule for aarch64)
        assert image3 == "registry/almalinux:10"
        assert mock_session.getTag.call_count == 2  # New query for different arch

    def test_policy_rule_precedence(self, resolver, mock_session):
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


class TestConfigParsingIntegration:
    """Integration tests for config parsing with real kojid.conf format."""

    def test_config_parsing_with_real_kojid_conf(self, monkeypatch):
        """Test config parsing with sample kojid.conf file."""
        adj_config.reset_config()

        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf") as f:
            f.write(
                """[adjutant]
task_image_default = registry/test:latest
image_pull_policy = always
network_enabled = false
policy_enabled = false
policy_cache_ttl = 900
container_mounts = /mnt/test:/mnt/test:rw:Z /other:/other:ro
container_labels = key1=value1,key2=value2
container_timeouts = pull=600,start=120,stop_grace=30
"""
            )
            config_file = f.name

        try:
            monkeypatch.setenv("KOJI_CONFIG", config_file)

            # Mock koji.read_config_files
            mock_config = {
                "adjutant": {
                    "task_image_default": "registry/test:latest",
                    "image_pull_policy": "always",
                    "network_enabled": "false",
                    "policy_enabled": "false",
                    "policy_cache_ttl": "900",
                    "container_mounts": "/mnt/test:/mnt/test:rw:Z /other:/other:ro",
                    "container_labels": "key1=value1,key2=value2",
                    "container_timeouts": "pull=600,start=120,stop_grace=30",
                }
            }

            class MockKoji:
                @staticmethod
                def read_config_files(files=None):
                    return mock_config

            monkeypatch.setattr(adj_config, "koji", MockKoji)

            # Verify config values
            assert adj_config.adjutant_task_image_default() == "registry/test:latest"
            assert adj_config.adjutant_image_pull_policy() == "always"
            assert adj_config.adjutant_network_enabled() is False
            assert adj_config.adjutant_policy_enabled() is False
            assert adj_config.adjutant_policy_cache_ttl() == 900

            mounts = adj_config.adjutant_container_mounts()
            assert len(mounts) == 2
            assert "/mnt/test:/mnt/test:rw:Z" in mounts

            labels = adj_config.adjutant_container_labels()
            assert labels["key1"] == "value1"
            assert labels["key2"] == "value2"

            timeouts = adj_config.adjutant_container_timeouts()
            assert timeouts["pull"] == 600
            assert timeouts["start"] == 120
            assert timeouts["stop_grace"] == 30

        finally:
            os.unlink(config_file)

    def test_env_var_overrides_config_file(self, monkeypatch):
        """Test that environment variables override config file values."""
        adj_config.reset_config()

        # Mock config file with one value
        mock_config = {
            "adjutant": {
                "task_image_default": "config/image:tag",
            }
        }

        class MockKoji:
            @staticmethod
            def read_config_files(files=None):
                return mock_config

        monkeypatch.setattr(adj_config, "koji", MockKoji)

        # Env var should override
        monkeypatch.setenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", "env/image:tag")
        assert adj_config.adjutant_task_image_default() == "env/image:tag"

        # Without env var, config should be used
        monkeypatch.delenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", raising=False)
        assert adj_config.adjutant_task_image_default() == "config/image:tag"

    def test_config_fallback_when_koji_unavailable(self, monkeypatch):
        """Test fallback to defaults when koji library unavailable."""
        adj_config.reset_config()
        monkeypatch.setattr(adj_config, "koji", None)

        # Should use Phase 1 defaults
        assert adj_config.adjutant_task_image_default() == "registry/almalinux:10"
        assert adj_config.adjutant_image_pull_policy() == "if-not-present"
        assert adj_config.adjutant_network_enabled() is True
        assert adj_config.adjutant_policy_enabled() is True


class TestEndToEndImageSelection:
    """End-to-end tests for image selection flow."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock koji session."""
        return MagicMock()

    @pytest.fixture
    def temp_koji_root(self, tmp_path):
        """Create a temporary /mnt/koji-like directory structure."""
        koji_root = tmp_path / "mnt" / "koji"
        koji_root.mkdir(parents=True, exist_ok=True)
        (koji_root / "work").mkdir(exist_ok=True)
        (koji_root / "logs").mkdir(exist_ok=True)
        (koji_root / "repos").mkdir(exist_ok=True)
        return koji_root

    @pytest.fixture
    def test_task_context(self, temp_koji_root):
        """Create a TaskContext for testing."""
        task_id = 12345
        work_dir = temp_koji_root / "work" / str(task_id)
        work_dir.mkdir(parents=True, exist_ok=True)

        return TaskContext(
            task_id=task_id,
            work_dir=work_dir,
            koji_mount_root=temp_koji_root,
            environment={"TEST": "1"},
        )

    def test_buildarch_adapter_with_policy(self, mock_session, test_task_context):
        """Test BuildArchAdapter uses PolicyResolver when session provided."""
        # Setup policy
        policy = {
            "rules": [
                {
                    "type": "tag_arch",
                    "tag": "f39-build",
                    "arch": "x86_64",
                    "image": "registry/koji-adjutant-task:f39-x86_64",
                },
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info

        # Enable policy
        with patch("koji_adjutant.config.adjutant_policy_enabled", return_value=True):
            adapter = BuildArchAdapter()
            task_params = {
                "pkg": "test.src.rpm",
                "root": "f39-build",
                "arch": "x86_64",
                "keep_srpm": False,
                "opts": {"repo_id": 1},
            }

            spec = adapter.build_spec(
                test_task_context, task_params, session=mock_session
            )

            # Verify image was resolved from policy
            assert spec.image == "registry/koji-adjutant-task:f39-x86_64"
            mock_session.getTag.assert_called_once()

    def test_buildarch_adapter_fallback_without_session(self, test_task_context):
        """Test BuildArchAdapter falls back to config default without session."""
        adapter = BuildArchAdapter()
        task_params = {
            "pkg": "test.src.rpm",
            "root": "f39-build",
            "arch": "x86_64",
            "keep_srpm": False,
            "opts": {"repo_id": 1},
        }

        spec = adapter.build_spec(test_task_context, task_params, session=None)

        # Should use config default (Phase 1 compatibility)
        assert spec.image == "registry/almalinux:10"

    def test_createrepo_adapter_with_policy(self, mock_session, test_task_context):
        """Test CreaterepoAdapter uses PolicyResolver when session and tag_name provided."""
        # Setup policy
        policy = {
            "rules": [
                {
                    "type": "task_type",
                    "task_type": "createrepo",
                    "image": "registry/koji-adjutant-task:repo",
                },
            ]
        }

        tag_info = {"extra": {"adjutant_image_policy": json.dumps(policy)}}
        mock_session.getTag.return_value = tag_info

        # Enable policy
        with patch("koji_adjutant.config.adjutant_policy_enabled", return_value=True):
            adapter = CreaterepoAdapter()
            task_params = {
                "repo_id": 1,
                "arch": "x86_64",
            }

            spec = adapter.build_spec(
                test_task_context,
                task_params,
                session=mock_session,
                tag_name="f39-build",
            )

            # Verify image was resolved from policy
            assert spec.image == "registry/koji-adjutant-task:repo"
            mock_session.getTag.assert_called_once()

    def test_policy_disabled_fallback(self, mock_session, test_task_context):
        """Test that adapters fall back to config when policy disabled."""
        # Disable policy
        with patch("koji_adjutant.config.adjutant_policy_enabled", return_value=False):
            adapter = BuildArchAdapter()
            task_params = {
                "pkg": "test.src.rpm",
                "root": "f39-build",
                "arch": "x86_64",
                "keep_srpm": False,
                "opts": {"repo_id": 1},
            }

            spec = adapter.build_spec(
                test_task_context, task_params, session=mock_session
            )

            # Should use config default (policy disabled)
            assert spec.image == "registry/almalinux:10"
            # Should not query hub
            mock_session.getTag.assert_not_called()


class TestCacheEffectiveness:
    """Tests for policy cache effectiveness."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock koji session."""
        return MagicMock()

    @pytest.fixture
    def resolver(self, mock_session):
        """Create a PolicyResolver instance."""
        return PolicyResolver(mock_session)

    def test_cache_reduces_hub_queries(self, resolver, mock_session):
        """Test that cache reduces hub queries for same tag+arch."""
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

        # First call - queries hub
        image1 = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert image1 == "registry/image:f39-x86_64"
        assert mock_session.getTag.call_count == 1

        # Second call - uses cache, no new query
        image2 = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert image2 == "registry/image:f39-x86_64"
        assert mock_session.getTag.call_count == 1  # Still 1

        # Third call - still cached
        image3 = resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="createrepo"
        )
        assert image3 == "registry/image:f39-x86_64"
        assert mock_session.getTag.call_count == 1  # Still 1

    def test_cache_invalidation(self, resolver, mock_session):
        """Test cache invalidation removes entries."""
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

        # Cache an entry
        resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert len(resolver._cache) == 1

        # Invalidate all
        resolver.invalidate_cache()
        assert len(resolver._cache) == 0

        # Next call should query hub again
        resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert mock_session.getTag.call_count == 2  # New query after invalidation

    def test_cache_ttl_expiration(self, resolver, mock_session):
        """Test that cache entries expire after TTL."""
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

        # Create resolver with short TTL
        resolver._ttl_seconds = 1  # 1 second TTL

        # Cache an entry
        resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert mock_session.getTag.call_count == 1

        # Manually expire the cache entry
        cache_key = ("f39-build", "x86_64")
        cached = resolver._cache[cache_key]
        cached.cached_at = datetime.now() - timedelta(seconds=2)  # Expired

        # Next call should query hub again (cache expired)
        resolver.resolve_image(
            tag_name="f39-build", arch="x86_64", task_type="buildArch"
        )
        assert mock_session.getTag.call_count == 2  # New query after expiration


class TestBackwardCompatibility:
    """Tests for Phase 1 backward compatibility."""

    @pytest.fixture
    def temp_koji_root(self, tmp_path):
        """Create a temporary /mnt/koji-like directory structure."""
        koji_root = tmp_path / "mnt" / "koji"
        koji_root.mkdir(parents=True, exist_ok=True)
        (koji_root / "work").mkdir(exist_ok=True)
        return koji_root

    @pytest.fixture
    def test_task_context(self, temp_koji_root):
        """Create a TaskContext for testing."""
        task_id = 12345
        work_dir = temp_koji_root / "work" / str(task_id)
        work_dir.mkdir(parents=True, exist_ok=True)

        return TaskContext(
            task_id=task_id,
            work_dir=work_dir,
            koji_mount_root=temp_koji_root,
            environment={},
        )

    def test_phase1_code_still_works(self, test_task_context):
        """Test that Phase 1 code paths still work without session."""
        # BuildArchAdapter without session should use config default
        adapter = BuildArchAdapter()
        task_params = {
            "pkg": "test.src.rpm",
            "root": "f39-build",
            "arch": "x86_64",
            "keep_srpm": False,
            "opts": {"repo_id": 1},
        }

        spec = adapter.build_spec(test_task_context, task_params)
        # Should work without session (Phase 1 compatibility)
        assert spec.image == "registry/almalinux:10"
        assert len(spec.command) > 0
        assert len(spec.mounts) > 0

    def test_config_defaults_match_phase1(self, monkeypatch):
        """Test that config defaults match Phase 1 hardcoded values."""
        adj_config.reset_config()
        monkeypatch.setattr(adj_config, "koji", None)

        # Should match Phase 1 defaults
        assert adj_config.adjutant_task_image_default() == "registry/almalinux:10"
        assert adj_config.adjutant_image_pull_policy() == "if-not-present"
        assert adj_config.adjutant_network_enabled() is True
        assert adj_config.adjutant_container_mounts() == ["/mnt/koji:/mnt/koji:rw:Z"]