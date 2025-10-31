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


class TestConfigInitialization:
    """Test config module initialization with options object."""

    def test_initialize_stores_options_object(self, monkeypatch):
        """Test config.initialize() stores options object."""
        adj_config.reset_config()
        monkeypatch.delenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", raising=False)

        # Create mock options object with adjutant_* attributes
        class MockOptions:
            adjutant_task_image_default = "options/image:tag"
            adjutant_image_pull_policy = "always"
            adjutant_network_enabled = True
            adjutant_policy_cache_ttl = 600

        options = MockOptions()

        # Initialize config module
        adj_config.initialize(options)

        # Verify _options is set by checking it affects config reads
        assert adj_config.adjutant_task_image_default() == "options/image:tag"

    def test_config_value_from_options_object(self, monkeypatch):
        """Test reading config value from initialized options object."""
        adj_config.reset_config()
        monkeypatch.delenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", raising=False)

        # Create mock options with various adjutant_* attributes
        class MockOptions:
            adjutant_task_image_default = "options/default:latest"
            adjutant_image_pull_policy = "never"
            adjutant_network_enabled = False
            adjutant_policy_cache_ttl = 900
            adjutant_buildroot_enabled = False

        options = MockOptions()
        adj_config.initialize(options)

        # Verify values come from options object
        assert adj_config.adjutant_task_image_default() == "options/default:latest"
        assert adj_config.adjutant_image_pull_policy() == "never"
        assert adj_config.adjutant_network_enabled() is False
        assert adj_config.adjutant_policy_cache_ttl() == 900
        assert adj_config.adjutant_buildroot_enabled() is False

    def test_fallback_to_defaults_when_not_initialized(self, monkeypatch):
        """Test fallback to defaults when options object not initialized."""
        adj_config.reset_config()
        monkeypatch.delenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_IMAGE_PULL_POLICY", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_NETWORK_ENABLED", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_POLICY_CACHE_TTL", raising=False)

        # Ensure _options is None (not initialized)
        adj_config.reset_config()

        # Verify defaults are used
        assert adj_config.adjutant_task_image_default() == "registry/almalinux:10"
        assert adj_config.adjutant_image_pull_policy() == "if-not-present"
        assert adj_config.adjutant_network_enabled() is True
        assert adj_config.adjutant_policy_cache_ttl() == 300

    def test_precedence_env_var_over_options(self, monkeypatch):
        """Test env var takes precedence over options object."""
        adj_config.reset_config()

        # Create mock options with one value
        class MockOptions:
            adjutant_task_image_default = "options/image:tag"
            adjutant_image_pull_policy = "never"
            adjutant_network_enabled = False

        options = MockOptions()
        adj_config.initialize(options)

        # Set env var with different value
        monkeypatch.setenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", "env/image:tag")
        monkeypatch.setenv("KOJI_ADJUTANT_IMAGE_PULL_POLICY", "always")
        monkeypatch.setenv("KOJI_ADJUTANT_NETWORK_ENABLED", "true")

        # Verify env var wins
        assert adj_config.adjutant_task_image_default() == "env/image:tag"
        assert adj_config.adjutant_image_pull_policy() == "always"
        assert adj_config.adjutant_network_enabled() is True

        # Remove env vars, verify options object values are used
        monkeypatch.delenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_IMAGE_PULL_POLICY", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_NETWORK_ENABLED", raising=False)

        assert adj_config.adjutant_task_image_default() == "options/image:tag"
        assert adj_config.adjutant_image_pull_policy() == "never"
        assert adj_config.adjutant_network_enabled() is False

    def test_precedence_options_over_defaults(self, monkeypatch):
        """Test options object takes precedence over defaults."""
        adj_config.reset_config()
        monkeypatch.delenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_IMAGE_PULL_POLICY", raising=False)

        # Create mock options
        class MockOptions:
            adjutant_task_image_default = "custom/image:latest"
            adjutant_image_pull_policy = "always"

        options = MockOptions()
        adj_config.initialize(options)

        # Verify options object values are used (not defaults)
        assert adj_config.adjutant_task_image_default() == "custom/image:latest"
        assert adj_config.adjutant_image_pull_policy() == "always"

    def test_options_with_string_type(self, monkeypatch):
        """Test options object with string values."""
        adj_config.reset_config()
        monkeypatch.delenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_IMAGE_PULL_POLICY", raising=False)

        class MockOptions:
            adjutant_task_image_default = "registry/almalinux:10"
            adjutant_image_pull_policy = "always"

        options = MockOptions()
        adj_config.initialize(options)

        value = adj_config.adjutant_task_image_default()
        assert isinstance(value, str)
        assert value == "registry/almalinux:10"

        value = adj_config.adjutant_image_pull_policy()
        assert isinstance(value, str)
        assert value == "always"

    def test_options_with_bool_type(self, monkeypatch):
        """Test options object with boolean values."""
        adj_config.reset_config()
        monkeypatch.delenv("KOJI_ADJUTANT_NETWORK_ENABLED", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_POLICY_ENABLED", raising=False)

        # Test with actual bool values
        class MockOptions:
            adjutant_network_enabled = True
            adjutant_policy_enabled = False

        options = MockOptions()
        adj_config.initialize(options)

        assert isinstance(adj_config.adjutant_network_enabled(), bool)
        assert adj_config.adjutant_network_enabled() is True
        assert isinstance(adj_config.adjutant_policy_enabled(), bool)
        assert adj_config.adjutant_policy_enabled() is False

        # Test with string bool values (should be converted)
        class MockOptionsStr:
            adjutant_network_enabled = "true"
            adjutant_policy_enabled = "false"

        options_str = MockOptionsStr()
        adj_config.initialize(options_str)

        assert adj_config.adjutant_network_enabled() is True
        assert adj_config.adjutant_policy_enabled() is False

    def test_options_with_int_type(self, monkeypatch):
        """Test options object with integer values."""
        adj_config.reset_config()
        monkeypatch.delenv("KOJI_ADJUTANT_POLICY_CACHE_TTL", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_MONITORING_CONTAINER_HISTORY_TTL", raising=False)

        # Test with actual int values
        class MockOptions:
            adjutant_policy_cache_ttl = 600
            adjutant_monitoring_container_history_ttl = 7200

        options = MockOptions()
        adj_config.initialize(options)

        value = adj_config.adjutant_policy_cache_ttl()
        assert isinstance(value, int)
        assert value == 600

        value = adj_config.adjutant_monitoring_container_history_ttl()
        assert isinstance(value, int)
        assert value == 7200

        # Test with string int values (should be converted)
        class MockOptionsStr:
            adjutant_policy_cache_ttl = "900"
            adjutant_monitoring_container_history_ttl = "3600"

        options_str = MockOptionsStr()
        adj_config.initialize(options_str)

        assert adj_config.adjutant_policy_cache_ttl() == 900
        assert adj_config.adjutant_monitoring_container_history_ttl() == 3600

    def test_options_missing_attribute_falls_back(self, monkeypatch):
        """Test that missing attributes in options object fall back to defaults."""
        adj_config.reset_config()
        monkeypatch.delenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", raising=False)
        monkeypatch.delenv("KOJI_ADJUTANT_IMAGE_PULL_POLICY", raising=False)

        # Create mock options with only some attributes
        class MockOptions:
            adjutant_task_image_default = "options/image:tag"
            # adjutant_image_pull_policy is missing

        options = MockOptions()
        adj_config.initialize(options)

        # Attribute in options should be used
        assert adj_config.adjutant_task_image_default() == "options/image:tag"

        # Missing attribute should fall back to default
        assert adj_config.adjutant_image_pull_policy() == "if-not-present"

    def test_reset_config_clears_options(self, monkeypatch):
        """Test that reset_config() clears both _config and _options."""
        adj_config.reset_config()
        monkeypatch.delenv("KOJI_ADJUTANT_TASK_IMAGE_DEFAULT", raising=False)

        # Initialize with options
        class MockOptions:
            adjutant_task_image_default = "options/image:tag"

        options = MockOptions()
        adj_config.initialize(options)
        assert adj_config.adjutant_task_image_default() == "options/image:tag"

        # Reset config
        adj_config.reset_config()

        # Should now use defaults
        assert adj_config.adjutant_task_image_default() == "registry/almalinux:10"
