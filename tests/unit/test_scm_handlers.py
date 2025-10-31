"""Unit tests for SCM handlers."""

from unittest.mock import MagicMock

import pytest

from koji_adjutant.container.interface import ContainerError, ContainerHandle
from koji_adjutant.task_adapters.scm.git import GitHandler, get_scm_handler


class TestGitHandler:
    """Test GitHandler class."""
    
    def test_is_scm_url_git_protocol(self):
        """Test git:// URL detection."""
        assert GitHandler.is_scm_url("git://example.com/repo.git") is True
        assert GitHandler.is_scm_url("git+https://example.com/repo.git") is True
        assert GitHandler.is_scm_url("git+http://example.com/repo.git") is True
        
    def test_is_scm_url_https_git(self):
        """Test https://*.git URL detection."""
        assert GitHandler.is_scm_url("https://github.com/user/repo.git") is True
        assert GitHandler.is_scm_url("https://gitlab.com/user/repo.git") is True
        assert GitHandler.is_scm_url("http://example.com/repo.git") is True
        
    def test_is_scm_url_non_git(self):
        """Test non-git URL rejection."""
        assert GitHandler.is_scm_url("svn://example.com/repo") is False
        assert GitHandler.is_scm_url("https://example.com/file.tar.gz") is False
        assert GitHandler.is_scm_url("ftp://example.com/file.tar.gz") is False
    
    def test_init_with_branch(self):
        """Test GitHandler initialization with branch in fragment."""
        handler = GitHandler("git://example.com/repo.git#develop")
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "develop"
        assert handler.ref_type == "branch"
    
    def test_init_with_tag(self):
        """Test GitHandler initialization with tag in fragment."""
        handler = GitHandler("git://example.com/repo.git#v1.0.0")
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "v1.0.0"
        assert handler.ref_type == "tag"
    
    def test_init_with_commit(self):
        """Test GitHandler initialization with commit in fragment."""
        handler = GitHandler("git://example.com/repo.git#abc123def456")
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "abc123def456"
        assert handler.ref_type == "commit"
    
    def test_init_default_ref(self):
        """Test GitHandler initialization without fragment defaults to main."""
        handler = GitHandler("git://example.com/repo.git")
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "main"
        assert handler.ref_type == "branch"
    
    def test_init_with_options_branch(self):
        """Test GitHandler initialization with branch in options."""
        handler = GitHandler("git://example.com/repo.git", {"branch": "feature"})
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "feature"
        assert handler.ref_type == "branch"
    
    def test_init_with_options_commit(self):
        """Test GitHandler initialization with commit in options."""
        handler = GitHandler("git://example.com/repo.git", {"commit": "abc123"})
        assert handler.url == "git://example.com/repo.git"
        assert handler.ref == "abc123"
        assert handler.ref_type == "commit"
    
    def test_checkout_success_branch(self):
        """Test successful git checkout with branch."""
        handler = GitHandler("git://example.com/repo.git#main")
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0
        
        result = handler.checkout(mock_manager, handle, "/builddir/source")
        
        assert result["url"] == "git://example.com/repo.git"
        assert "commit" in result
        assert result["branch"] == "main"
        assert result["ref"] == "main"
        assert result["ref_type"] == "branch"
        
        # Verify git clone was called with correct args
        calls = mock_manager.exec.call_args_list
        clone_calls = [call for call in calls if "clone" in str(call)]
        assert len(clone_calls) > 0
        
        # Check that --depth 1 and --branch were used for branch checkout
        clone_call = clone_calls[0]
        clone_cmd = clone_call[0][1]  # Second arg is command list
        assert "clone" in clone_cmd
        assert "--depth" in clone_cmd
        assert "--branch" in clone_cmd
    
    def test_checkout_success_commit(self):
        """Test successful git checkout with commit."""
        handler = GitHandler("git://example.com/repo.git#abc123def456")
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.return_value = 0
        
        result = handler.checkout(mock_manager, handle, "/builddir/source")
        
        assert result["url"] == "git://example.com/repo.git"
        assert result["ref"] == "abc123def456"
        assert result["ref_type"] == "commit"
        
        # Verify git clone was called without --depth for commit checkout
        calls = mock_manager.exec.call_args_list
        clone_calls = [call for call in calls if "clone" in str(call)]
        assert len(clone_calls) > 0
        
        # Check that checkout command was also called
        checkout_calls = [call for call in calls if "checkout" in str(call)]
        assert len(checkout_calls) > 0
    
    def test_checkout_failure_mkdir(self):
        """Test git checkout failure on mkdir."""
        handler = GitHandler("git://example.com/repo.git")
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.side_effect = [
            1,  # mkdir fails
        ]
        
        with pytest.raises(ContainerError, match="Failed to create directory"):
            handler.checkout(mock_manager, handle, "/builddir/source")
    
    def test_checkout_failure_clone(self):
        """Test git checkout failure on clone."""
        handler = GitHandler("git://example.com/repo.git")
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.side_effect = [
            0,  # mkdir succeeds
            1,  # git clone fails
        ]
        
        with pytest.raises(ContainerError, match="Git clone failed"):
            handler.checkout(mock_manager, handle, "/builddir/source")
    
    def test_checkout_failure_checkout_commit(self):
        """Test git checkout failure on commit checkout."""
        handler = GitHandler("git://example.com/repo.git#abc123")
        handle = ContainerHandle(container_id="test-container")
        mock_manager = MagicMock()
        mock_manager.exec.side_effect = [
            0,  # mkdir succeeds
            0,  # git clone succeeds
            1,  # git checkout fails
        ]
        
        with pytest.raises(ContainerError, match="Git checkout commit failed"):
            handler.checkout(mock_manager, handle, "/builddir/source")


class TestGetSCMHandler:
    """Test get_scm_handler factory function."""
    
    def test_get_git_handler(self):
        """Test getting git handler."""
        handler = get_scm_handler("git://example.com/repo.git")
        assert isinstance(handler, GitHandler)
    
    def test_get_git_handler_https(self):
        """Test getting git handler for https URL."""
        handler = get_scm_handler("https://github.com/user/repo.git")
        assert isinstance(handler, GitHandler)
    
    def test_unsupported_scm(self):
        """Test unsupported SCM URL."""
        with pytest.raises(ValueError, match="Unsupported SCM URL"):
            get_scm_handler("ftp://example.com/file.tar.gz")
    
    def test_get_scm_handler_with_options(self):
        """Test getting handler with options."""
        handler = get_scm_handler("git://example.com/repo.git", {"branch": "dev"})
        assert isinstance(handler, GitHandler)
        assert handler.ref == "dev"
        assert handler.ref_type == "branch"
