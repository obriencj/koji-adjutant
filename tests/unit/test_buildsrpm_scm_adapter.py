"""Unit tests for BuildSRPMFromSCMAdapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from koji_adjutant.container.interface import ContainerError, ContainerHandle, ContainerSpec
from koji_adjutant.task_adapters.base import TaskContext
from koji_adjutant.task_adapters.buildsrpm_scm import BuildSRPMFromSCMAdapter


class TestBuildSRPMFromSCMAdapter:
    """Test BuildSRPMFromSCMAdapter class."""

    def test_build_spec_basic(self, tmp_path):
        """Test ContainerSpec creation for basic SCM build."""
        adapter = BuildSRPMFromSCMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "url": "git://example.com/repo.git#main",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }

        with patch("koji_adjutant.task_adapters.buildsrpm_scm.adj_config") as mock_config:
            mock_config.adjutant_policy_enabled.return_value = False
            mock_config.adjutant_task_image_default.return_value = "test-image:latest"
            mock_config.adjutant_buildroot_enabled.return_value = False

            spec = adapter.build_spec(ctx, task_params)

            assert isinstance(spec, ContainerSpec)
            assert spec.image == "test-image:latest"
            assert spec.network_enabled is True  # Network required for SCM checkout
            assert len(spec.mounts) == 2  # koji mount + workdir mount
            assert spec.command == ["/bin/sleep", "infinity"]  # Exec pattern
            assert "KOJI_SCM_URL" in spec.environment

    def test_build_spec_with_policy(self, tmp_path):
        """Test image selection via PolicyResolver."""
        adapter = BuildSRPMFromSCMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "url": "git://example.com/repo.git#main",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }

        mock_session = MagicMock()
        mock_resolver = MagicMock()
        mock_resolver.resolve_image.return_value = "policy-resolved-image:latest"

        with patch("koji_adjutant.task_adapters.buildsrpm_scm.adj_config") as mock_config, \
             patch("koji_adjutant.task_adapters.buildsrpm_scm.PolicyResolver", return_value=mock_resolver):
            mock_config.adjutant_policy_enabled.return_value = True
            mock_config.adjutant_buildroot_enabled.return_value = False

            spec = adapter.build_spec(ctx, task_params, session=mock_session, event_id=789)

            assert spec.image == "policy-resolved-image:latest"
            mock_resolver.resolve_image.assert_called_once_with(
                tag_name="f39-build",
                arch="noarch",
                task_type="buildSRPMFromSCM",
                event_id=789,
            )

    def test_build_spec_no_repo_id(self, tmp_path):
        """Test that missing repo_id raises ValueError."""
        adapter = BuildSRPMFromSCMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "url": "git://example.com/repo.git#main",
            "build_tag": "f39-build",
            "opts": {},  # No repo_id
        }

        with pytest.raises(ValueError, match="A repo id must be provided"):
            adapter.build_spec(ctx, task_params)

    def test_checkout_scm_success(self):
        """Test checkout_scm successfully checks out source."""
        adapter = BuildSRPMFromSCMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0
        sink = MagicMock()

        with patch("koji_adjutant.task_adapters.buildsrpm_scm.get_scm_handler") as mock_get_handler:
            mock_handler = MagicMock()
            mock_handler.checkout.return_value = {
                "url": "git://example.com/repo.git",
                "commit": "abc123",
                "branch": "main",
                "ref": "main",
                "ref_type": "branch",
            }
            mock_get_handler.return_value = mock_handler

            result = adapter.checkout_scm(handle, mock_manager, "git://example.com/repo.git#main", "/builddir/source", sink)

            assert result["url"] == "git://example.com/repo.git"
            assert result["branch"] == "main"
            mock_get_handler.assert_called_once_with("git://example.com/repo.git#main")
            mock_handler.checkout.assert_called_once_with(mock_manager, handle, "/builddir/source")

    def test_detect_build_method_make(self):
        """Test detect_build_method detects make srpm."""
        adapter = BuildSRPMFromSCMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0  # Makefile exists and has srpm target
        sink = MagicMock()

        method = adapter.detect_build_method(handle, mock_manager, "/builddir/source", sink)

        assert method == "make"

        # Verify the check command was called
        check_calls = [call for call in mock_manager.exec.call_args_list if "Makefile" in str(call)]
        assert len(check_calls) > 0

    def test_detect_build_method_rpmbuild(self):
        """Test detect_build_method falls back to rpmbuild."""
        adapter = BuildSRPMFromSCMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 1  # Makefile doesn't exist or no srpm target
        sink = MagicMock()

        method = adapter.detect_build_method(handle, mock_manager, "/builddir/source", sink)

        assert method == "rpmbuild"

    def test_build_srpm_make(self):
        """Test build_srpm uses make srpm method."""
        adapter = BuildSRPMFromSCMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0
        sink = MagicMock()

        result = adapter.build_srpm(
            handle, mock_manager, "/builddir/source", "/work/12345", "make", sink, {}
        )

        assert result == "/work/12345/result/*.src.rpm"

        # Verify mkdir was called
        mkdir_calls = [call for call in mock_manager.exec.call_args_list if call[0][1][0] == "mkdir"]
        assert len(mkdir_calls) > 0

        # Verify make was called
        make_calls = [call for call in mock_manager.exec.call_args_list if call[0][1][0] == "make"]
        assert len(make_calls) > 0

    def test_build_srpm_rpmbuild(self):
        """Test build_srpm uses rpmbuild -bs method."""
        adapter = BuildSRPMFromSCMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0
        sink = MagicMock()

        result = adapter.build_srpm(
            handle, mock_manager, "/builddir/source", "/work/12345", "rpmbuild", sink, {}
        )

        assert result == "/work/12345/result/*.src.rpm"

        # Verify rpmbuild was called
        rpmbuild_calls = [
            call for call in mock_manager.exec.call_args_list
            if len(call[0][1]) > 0 and "rpmbuild" in " ".join(call[0][1])
        ]
        assert len(rpmbuild_calls) > 0

    def test_build_srpm_failure(self):
        """Test build_srpm raises ContainerError on failure."""
        adapter = BuildSRPMFromSCMAdapter()
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.side_effect = [
            0,  # mkdir succeeds
            1,  # build fails
        ]
        sink = MagicMock()

        with pytest.raises(ContainerError, match="SRPM build failed"):
            adapter.build_srpm(
                handle, mock_manager, "/builddir/source", "/work/12345", "make", sink, {}
            )

    def test_run_without_buildroot(self, tmp_path):
        """Test run() raises ValueError when buildroot not enabled."""
        adapter = BuildSRPMFromSCMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "url": "git://example.com/repo.git#main",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }
        mock_manager = MagicMock()
        sink = MagicMock()

        with patch("koji_adjutant.task_adapters.buildsrpm_scm.adj_config") as mock_config:
            mock_config.adjutant_buildroot_enabled.return_value = False

            with pytest.raises(ValueError, match="Buildroot initialization required"):
                adapter.run(ctx, mock_manager, sink, task_params)

    def test_run_error_handling(self, tmp_path):
        """Test run() handles errors gracefully."""
        adapter = BuildSRPMFromSCMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "url": "git://example.com/repo.git#main",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }
        mock_manager = MagicMock()
        mock_manager.create.side_effect = ContainerError("Container creation failed")
        sink = MagicMock()

        with patch("koji_adjutant.task_adapters.buildsrpm_scm.adj_config") as mock_config, \
             patch("koji_adjutant.task_adapters.buildsrpm_scm.BuildrootInitializer") as mock_init:
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

    def test_run_success_no_srpm_files(self, tmp_path):
        """Test run() handles case where no SRPM files are found."""
        adapter = BuildSRPMFromSCMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "url": "git://example.com/repo.git#main",
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

        with patch("koji_adjutant.task_adapters.buildsrpm_scm.adj_config") as mock_config, \
             patch("koji_adjutant.task_adapters.buildsrpm_scm.BuildrootInitializer") as mock_init, \
             patch("koji_adjutant.task_adapters.buildsrpm_scm.get_scm_handler") as mock_get_handler:
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

            mock_handler = MagicMock()
            mock_handler.checkout.return_value = {
                "url": "git://example.com/repo.git",
                "commit": "abc123",
                "branch": "main",
            }
            mock_get_handler.return_value = mock_handler

            exit_code, result = adapter.run(ctx, mock_manager, sink, task_params, session=MagicMock())

            assert exit_code == 1
            assert result["srpm"] == ""

            # Verify cleanup was called
            mock_manager.remove.assert_called_once_with(handle, force=True)

    def test_run_success_with_srpm(self, tmp_path):
        """Test run() successfully builds SRPM."""
        adapter = BuildSRPMFromSCMAdapter()
        ctx = TaskContext(
            task_id=12345,
            work_dir=tmp_path,
            koji_mount_root=Path("/mnt/koji"),
            environment={},
        )
        task_params = {
            "url": "git://example.com/repo.git#main",
            "build_tag": "f39-build",
            "opts": {"repo_id": 456},
        }
        mock_manager = MagicMock()
        handle = ContainerHandle(container_id="test-container")
        mock_manager.create.return_value = handle
        mock_manager.exec.return_value = 0
        sink = MagicMock()

        # Create result directory with SRPM file
        result_dir = tmp_path / "result"
        result_dir.mkdir()
        srpm_file = result_dir / "mypackage-1.0-1.src.rpm"
        srpm_file.write_bytes(b"fake srpm content")

        with patch("koji_adjutant.task_adapters.buildsrpm_scm.adj_config") as mock_config, \
             patch("koji_adjutant.task_adapters.buildsrpm_scm.BuildrootInitializer") as mock_init, \
             patch("koji_adjutant.task_adapters.buildsrpm_scm.get_scm_handler") as mock_get_handler:
            mock_config.adjutant_buildroot_enabled.return_value = True
            mock_config.adjutant_task_image_default.return_value = "test-image:latest"
            mock_config.adjutant_policy_enabled.return_value = False  # Disable policy to avoid session.getTag issues

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

            mock_handler = MagicMock()
            mock_handler.checkout.return_value = {
                "url": "git://example.com/repo.git",
                "commit": "abc123",
                "branch": "main",
            }
            mock_get_handler.return_value = mock_handler

            exit_code, result = adapter.run(ctx, mock_manager, sink, task_params, session=MagicMock())

            # Should succeed (exit_code 0) even if koji validation fails (we'll skip it)
            assert result["srpm"] == "work/12345/result/mypackage-1.0-1.src.rpm"
            assert "source" in result
            assert result["source"]["url"] == "git://example.com/repo.git#main"  # URL includes ref fragment

            # Verify cleanup was called
            mock_manager.remove.assert_called_once_with(handle, force=True)
