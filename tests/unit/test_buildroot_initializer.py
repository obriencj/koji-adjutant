"""Unit tests for BuildrootInitializer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from koji_adjutant.buildroot.initializer import BuildrootInitializer


class TestBuildrootInitializer:
    """Test BuildrootInitializer class."""

    def test_initialize_returns_structured_data(self, tmp_path):
        """Test that initialize() returns structured data instead of script."""
        session = MagicMock()
        session.getTag.return_value = {"id": 123, "name": "test-tag"}
        session.getRepo.return_value = {"id": 456}
        session.repoInfo.return_value = {"id": 456, "tag_id": 123}

        initializer = BuildrootInitializer(session)

        srpm_path = tmp_path / "test.src.rpm"
        srpm_path.write_bytes(b"fake srpm")

        with patch("koji_adjutant.buildroot.dependencies") as mock_deps, \
             patch("koji_adjutant.buildroot.repos") as mock_repos, \
             patch("koji_adjutant.buildroot.environment") as mock_env:

            # Mock dependencies
            mock_deps.extract_buildrequires_from_srpm.return_value = ["gcc", "make"]
            mock_deps.resolve_build_dependencies.return_value = ["gcc", "make", "python3-devel"]

            # Mock repos
            mock_repos.generate_repo_config.return_value = "[koji-repo]\nbaseurl=file:///mnt/koji/repos\n"

            # Mock environment
            mock_env.setup_build_environment.return_value = {
                "KOJI_TASK_ID": "0",
                "KOJI_BUILD_TAG": "test-tag",
                "KOJI_ARCH": "x86_64",
            }
            mock_env.generate_rpm_macros.return_value = {
                "dist": ".almalinux10",
                "_topdir": "/work/12345",
            }

            result = initializer.initialize(
                srpm_path=srpm_path,
                build_tag="test-tag",
                arch="x86_64",
                work_dir=Path("/work/12345"),
                repo_id=456,
            )

            # Verify new structure
            assert "repo_file_content" in result
            assert "repo_file_dest" in result
            assert result["repo_file_dest"] == "/etc/yum.repos.d/koji.repo"
            assert "macros_file_content" in result
            assert "macros_file_dest" in result
            assert result["macros_file_dest"] == "/etc/rpm/macros.koji"
            assert "init_commands" in result
            assert isinstance(result["init_commands"], list)
            assert "build_command" in result
            assert isinstance(result["build_command"], list)
            assert "environment" in result
            assert "dependencies" in result

            # Verify no script field (old structure)
            assert "script" not in result

    def test_init_commands_structure(self):
        """Test that init_commands are properly structured."""
        initializer = BuildrootInitializer(MagicMock())

        commands = initializer._generate_init_commands(
            work_dir=Path("/work/12345"),
            dependencies=["gcc", "make"],
        )

        assert len(commands) >= 1
        assert isinstance(commands[0], list)
        assert commands[0][0] == "mkdir"
        assert "-p" in commands[0]

        # If dependencies exist, should have dnf install command
        if len(commands) > 1:
            assert commands[1][0] == "dnf"
            assert "install" in commands[1]

    def test_format_macros_file(self):
        """Test macros file formatting."""
        initializer = BuildrootInitializer(MagicMock())

        macros = {
            "dist": ".almalinux10",
            "_topdir": "/work/12345",
            "_builddir": "/work/12345/build",
        }

        content = initializer._format_macros_file(macros)

        assert "%dist .almalinux10" in content
        assert "%_topdir /work/12345" in content
        assert "%_builddir /work/12345/build" in content
        assert content.endswith("\n")

    def test_generate_build_command(self):
        """Test build command generation."""
        initializer = BuildrootInitializer(MagicMock())

        macros = {
            "dist": ".almalinux10",
            "_topdir": "/work/12345",
        }

        command = initializer._generate_build_command(
            work_dir=Path("/work/12345"),
            srpm_path="/work/12345/work/test.src.rpm",
            macros=macros,
        )

        assert command[0] == "rpmbuild"
        assert "--rebuild" in command
        assert "/work/12345/work/test.src.rpm" in command
        assert "--define" in command
        assert "dist .almalinux10" in command or any("dist" in str(c) for c in command)
