"""Unit tests for RebuildSRPMAdapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from koji_adjutant.container.interface import ContainerError, ContainerHandle, ContainerSpec
from koji_adjutant.task_adapters.base import TaskContext
from koji_adjutant.task_adapters.rebuild_srpm import RebuildSRPMAdapter


class TestRebuildSRPMAdapter:
    """Test RebuildSRPMAdapter class."""

    def test_build_spec_basic(self, tmp_path):
        """Test ContainerSpec creation for basic rebuild."""
        adapter = RebuildSRPMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "srpm": "work/12344/mypackage-1.0-1.src.rpm",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }

        with patch("koji_adjutant.task_adapters.rebuild_srpm.adj_config") as mock_config:
            mock_config.adjutant_policy_enabled.return_value = False
            mock_config.adjutant_task_image_default.return_value = "test-image:latest"
            mock_config.adjutant_buildroot_enabled.return_value = False

            spec = adapter.build_spec(ctx, task_params)

            assert isinstance(spec, ContainerSpec)
            assert spec.image == "test-image:latest"
            assert spec.network_enabled is False  # Network not required for rebuild
            assert len(spec.mounts) == 2  # koji mount + workdir mount
            assert spec.command == ["/bin/sleep", "infinity"]  # Exec pattern

    def test_build_spec_with_policy(self, tmp_path):
        """Test image selection via PolicyResolver."""
        adapter = RebuildSRPMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "srpm": "work/12344/mypackage-1.0-1.src.rpm",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }

        mock_session = MagicMock()
        mock_resolver = MagicMock()
        mock_resolver.resolve_image.return_value = "policy-resolved-image:latest"

        with patch("koji_adjutant.task_adapters.rebuild_srpm.adj_config") as mock_config, \
             patch("koji_adjutant.task_adapters.rebuild_srpm.PolicyResolver", return_value=mock_resolver):
            mock_config.adjutant_policy_enabled.return_value = True
            mock_config.adjutant_buildroot_enabled.return_value = False

            spec = adapter.build_spec(ctx, task_params, session=mock_session, event_id=789)

            assert spec.image == "policy-resolved-image:latest"
            mock_resolver.resolve_image.assert_called_once_with(
                tag_name="f39-build",
                arch="noarch",
                task_type="rebuildSRPM",
                event_id=789,
            )

    def test_build_spec_no_repo_id(self, tmp_path):
        """Test that missing repo_id raises ValueError."""
        adapter = RebuildSRPMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "srpm": "work/12344/mypackage-1.0-1.src.rpm",
            "build_tag": "f39-build",
            "opts": {},  # No repo_id
        }

        with pytest.raises(ValueError, match="A repo id must be provided"):
            adapter.build_spec(ctx, task_params)

    def test_unpack_srpm_structure(self):
        """Test unpack_srpm returns correct structure."""
        adapter = RebuildSRPMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0
        sink = MagicMock()

        result = adapter.unpack_srpm(
            handle,
            mock_manager,
            "/container/srpm/mypackage-1.0-1.src.rpm",
            "/work/12345",
            sink,
            {},
        )

        assert "spec" in result
        assert "source_dir" in result
        assert result["source_dir"] == "/work/12345/SOURCES"
        assert "SPECS" in result["spec"]
        assert "*.spec" in result["spec"]

        # Verify mkdir was called
        mkdir_calls = [call for call in mock_manager.exec.call_args_list if call[0][1][0] == "mkdir"]
        assert len(mkdir_calls) > 0

        # Verify rpm -ivh was called
        rpm_calls = [call for call in mock_manager.exec.call_args_list if call[0][1][0] == "rpm"]
        assert len(rpm_calls) > 0

    def test_unpack_srpm_failure(self):
        """Test unpack_srpm raises ContainerError on failure."""
        adapter = RebuildSRPMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.side_effect = [
            0,  # mkdir succeeds
            1,  # rpm -ivh fails
        ]
        sink = MagicMock()

        with pytest.raises(ContainerError, match="Failed to unpack SRPM"):
            adapter.unpack_srpm(
                handle,
                mock_manager,
                "/container/srpm/mypackage-1.0-1.src.rpm",
                "/work/12345",
                sink,
                {},
            )

    def test_rebuild_srpm_structure(self):
        """Test rebuild_srpm returns correct path pattern."""
        adapter = RebuildSRPMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0
        sink = MagicMock()

        result = adapter.rebuild_srpm(
            handle,
            mock_manager,
            "/work/12345/SPECS/*.spec",
            "/work/12345/SOURCES",
            "/work/12345",
            sink,
            {},
        )

        assert result == "/work/12345/result/*.src.rpm"

        # Verify mkdir was called for result directory
        mkdir_calls = [call for call in mock_manager.exec.call_args_list if call[0][1][0] == "mkdir"]
        assert len(mkdir_calls) > 0

        # Verify rpmbuild was called
        rebuild_calls = [
            call for call in mock_manager.exec.call_args_list
            if len(call[0][1]) > 0 and "rpmbuild" in " ".join(call[0][1])
        ]
        assert len(rebuild_calls) > 0

    def test_rebuild_srpm_failure(self):
        """Test rebuild_srpm raises ContainerError on failure."""
        adapter = RebuildSRPMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.side_effect = [
            0,  # mkdir succeeds
            1,  # rpmbuild fails
        ]
        sink = MagicMock()

        with pytest.raises(ContainerError, match="Failed to rebuild SRPM"):
            adapter.rebuild_srpm(
                handle,
                mock_manager,
                "/work/12345/SPECS/*.spec",
                "/work/12345/SOURCES",
                "/work/12345",
                sink,
                {},
            )

    def test_validate_srpm_structure(self):
        """Test validate_srpm returns correct structure."""
        adapter = RebuildSRPMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0
        sink = MagicMock()

        result = adapter.validate_srpm(
            handle,
            mock_manager,
            "/work/12345/result/mypackage-1.0-1.src.rpm",
            sink,
            {},
        )

        assert "name" in result
        assert "version" in result
        assert "release" in result

        # Verify rpm -qp was called
        query_calls = [
            call for call in mock_manager.exec.call_args_list
            if len(call[0][1]) > 0 and "rpm" in " ".join(call[0][1])
        ]
        assert len(query_calls) > 0

    def test_validate_srpm_failure(self):
        """Test validate_srpm raises ContainerError on failure."""
        adapter = RebuildSRPMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 1  # rpm -qp fails
        sink = MagicMock()

        with pytest.raises(ContainerError, match="Failed to query SRPM header"):
            adapter.validate_srpm(
                handle,
                mock_manager,
                "/work/12345/result/mypackage-1.0-1.src.rpm",
                sink,
                {},
            )

    def test_run_without_buildroot(self, tmp_path):
        """Test run() raises ValueError when buildroot not enabled."""
        adapter = RebuildSRPMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "srpm": "work/12344/mypackage-1.0-1.src.rpm",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }
        mock_manager = MagicMock()
        sink = MagicMock()

        with patch("koji_adjutant.task_adapters.rebuild_srpm.adj_config") as mock_config:
            mock_config.adjutant_buildroot_enabled.return_value = False

            with pytest.raises(ValueError, match="Buildroot initialization required"):
                adapter.run(ctx, mock_manager, sink, task_params)

    def test_run_error_handling(self, tmp_path):
        """Test run() handles errors gracefully."""
        adapter = RebuildSRPMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "srpm": "work/12344/mypackage-1.0-1.src.rpm",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }
        mock_manager = MagicMock()
        mock_manager.create.side_effect = ContainerError("Container creation failed")
        sink = MagicMock()

        with patch("koji_adjutant.task_adapters.rebuild_srpm.adj_config") as mock_config, \
             patch("koji_adjutant.task_adapters.rebuild_srpm.BuildrootInitializer") as mock_init:
            mock_config.adjutant_buildroot_enabled.return_value = True
            mock_config.adjutant_task_image_default.return_value = "test-image:latest"

            mock_initializer = MagicMock()
            mock_initializer.initialize.return_value = {
                "repo_file_content": "[koji-repo]\n",
                "repo_file_dest": "/etc/yum.repos.d/koji.repo",
                "macros_file_content": "%dist .almalinux10\n",
                "macros_file_dest": "/etc/rpm/macros.koji",
                "init_commands": [["mkdir", "-p", "/work/12345/build"]],
                "build_command": ["echo", "test"],
                "environment": {},
            }
            mock_init.return_value = mock_initializer

            exit_code, result = adapter.run(ctx, mock_manager, sink, task_params, session=MagicMock())

            assert exit_code == 1
            assert result["srpm"] == ""
            assert result["logs"] == []
            assert result["brootid"] == 0

            # Verify cleanup was attempted
            # (container creation failed, so no cleanup needed)

    def test_run_success_no_srpm_files(self, tmp_path):
        """Test run() handles case where no SRPM files are found."""
        adapter = RebuildSRPMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "srpm": "work/12344/mypackage-1.0-1.src.rpm",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }
        mock_manager = MagicMock()
        handle = ContainerHandle(container_id="test-container")
        mock_manager.create.return_value = handle
        mock_manager.exec.return_value = 0
        sink = MagicMock()

        # Create empty result directory
        result_dir = tmp_path / "result"
        result_dir.mkdir()

        with patch("koji_adjutant.task_adapters.rebuild_srpm.adj_config") as mock_config, \
             patch("koji_adjutant.task_adapters.rebuild_srpm.BuildrootInitializer") as mock_init:
            mock_config.adjutant_buildroot_enabled.return_value = True
            mock_config.adjutant_task_image_default.return_value = "test-image:latest"

            mock_initializer = MagicMock()
            mock_initializer.initialize.return_value = {
                "repo_file_content": "[koji-repo]\n",
                "repo_file_dest": "/etc/yum.repos.d/koji.repo",
                "macros_file_content": "%dist .almalinux10\n",
                "macros_file_dest": "/etc/rpm/macros.koji",
                "init_commands": [["mkdir", "-p", "/work/12345/build"]],
                "build_command": ["echo", "test"],
                "environment": {},
            }
            mock_init.return_value = mock_initializer

            exit_code, result = adapter.run(ctx, mock_manager, sink, task_params, session=MagicMock())

            assert exit_code == 1
            assert result["srpm"] == ""
            assert "No SRPM files found" in str(result) or result["srpm"] == ""

            # Verify cleanup was called
            mock_manager.remove.assert_called_once_with(handle, force=True)
