"""Unit tests for config parsing module."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from koji_adjutant import config as adj_config


class TestConfigParsing:
    """Test config file parsing."""

    def test_defaults_without_config(self, monkeypatch):
        """Test that defaults work when no config file exists."""
        # Reset config cache
        adj_config.reset_config()
        # Ensure no config file is found
        monkeypatch.delenv("KOJI_CONFIG", raising=False)
        monkeypatch.setattr(adj_config, "koji", None)

        assert adj_config.adjutant_task_image_default() == "registry/almalinux:10"
        assert adj_config.adjutant_image_pull_policy() == "if-not-present"
        assert adj_config.adjutant_network_enabled() is True
        assert adj_config.adjutant_policy_enabled() is True
        assert adj_config.adjutant_policy_cache_ttl() == 300

    def test_env_var_overrides(self, monkeypatch):
        """Test that environment variables override defaults."""
        adj_config.reset_config()
        monkeypatch.setenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", "custom/image:tag")
        monkeypatch.setenv("KOJI_ADJUTANT_IMAGE_PULL_POLICY", "always")
        monkeypatch.setenv("KOJI_ADJUTANT_NETWORK_ENABLED", "false")
        monkeypatch.setenv("KOJI_ADJUTANT_POLICY_ENABLED", "false")
        monkeypatch.setenv("KOJI_ADJUTANT_POLICY_CACHE_TTL", "600")

        assert adj_config.adjutant_task_image_default() == "custom/image:tag"
        assert adj_config.adjutant_image_pull_policy() == "always"
        assert adj_config.adjutant_network_enabled() is False
        assert adj_config.adjutant_policy_enabled() is False
        assert adj_config.adjutant_policy_cache_ttl() == 600

    def test_config_file_parsing(self, monkeypatch):
        """Test parsing from config file."""
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

            # Mock koji module
            class MockKoji:
                @staticmethod
                def read_config_files(files=None):
                    return mock_config

            monkeypatch.setattr(adj_config, "koji", MockKoji)

            assert adj_config.adjutant_task_image_default() == "registry/test:latest"
            assert adj_config.adjutant_image_pull_policy() == "always"
            assert adj_config.adjutant_network_enabled() is False
            assert adj_config.adjutant_policy_enabled() is False
            assert adj_config.adjutant_policy_cache_ttl() == 900

            mounts = adj_config.adjutant_container_mounts()
            assert len(mounts) == 2
            assert "/mnt/test:/mnt/test:rw:Z" in mounts
            assert "/other:/other:ro" in mounts

            labels = adj_config.adjutant_container_labels()
            assert labels["key1"] == "value1"
            assert labels["key2"] == "value2"

            timeouts = adj_config.adjutant_container_timeouts()
            assert timeouts["pull"] == 600
            assert timeouts["start"] == 120
            assert timeouts["stop_grace"] == 30

        finally:
            os.unlink(config_file)

    def test_bool_parsing(self, monkeypatch):
        """Test boolean value parsing."""
        adj_config.reset_config()

        test_cases = [
            ("true", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
            ("off", False),
        ]

        for value, expected in test_cases:
            monkeypatch.setenv("KOJI_ADJUTANT_NETWORK_ENABLED", value)
            assert adj_config.adjutant_network_enabled() == expected

    def test_mounts_parsing(self, monkeypatch):
        """Test mount specification parsing."""
        adj_config.reset_config()

        # Test space-separated
        monkeypatch.setenv(
            "KOJI_ADJUTANT_CONTAINER_MOUNTS",
            "/mnt/koji:/mnt/koji:rw:Z /other:/other:ro",
        )
        mounts = adj_config.adjutant_container_mounts()
        assert len(mounts) == 2

        # Test comma-separated
        monkeypatch.setenv(
            "KOJI_ADJUTANT_CONTAINER_MOUNTS", "/mnt/koji:/mnt/koji:rw:Z,/other:/other:ro"
        )
        mounts = adj_config.adjutant_container_mounts()
        assert len(mounts) == 2

    def test_labels_parsing(self, monkeypatch):
        """Test label parsing."""
        adj_config.reset_config()

        monkeypatch.setenv("KOJI_ADJUTANT_CONTAINER_LABELS", "key1=value1,key2=value2")
        labels = adj_config.adjutant_container_labels()
        assert labels["key1"] == "value1"
        assert labels["key2"] == "value2"

    def test_timeouts_parsing(self, monkeypatch):
        """Test timeout parsing."""
        adj_config.reset_config()

        monkeypatch.setenv(
            "KOJI_ADJUTANT_CONTAINER_TIMEOUTS", "pull=600,start=120,stop_grace=30"
        )
        timeouts = adj_config.adjutant_container_timeouts()
        assert timeouts["pull"] == 600
        assert timeouts["start"] == 120
        assert timeouts["stop_grace"] == 30

    def test_env_overrides_config(self, monkeypatch):
        """Test that env vars override config file values."""
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
