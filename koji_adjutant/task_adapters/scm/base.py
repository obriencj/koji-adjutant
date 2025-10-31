"""Base SCM handler protocol."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from ...container.interface import ContainerManager


class SCMHandler(Protocol):
    """Protocol for SCM checkout handlers.
    
    All SCM implementations (git, svn, cvs) must implement this protocol.
    """
    
    @staticmethod
    def is_scm_url(url: str) -> bool:
        """Check if URL matches this SCM type.
        
        Args:
            url: URL to check (e.g., git://example.com/repo.git)
            
        Returns:
            True if this handler can process the URL
            
        Examples:
            GitHandler.is_scm_url("git://example.com/repo.git") -> True
            GitHandler.is_scm_url("svn://example.com/repo") -> False
        """
        ...
        
    def __init__(self, url: str, options: Optional[Dict] = None):
        """Initialize handler for SCM URL.
        
        Args:
            url: SCM URL with optional fragment (#branch, #tag, #commit)
            options: Optional dict with checkout options
                - branch: Branch name to checkout
                - commit: Specific commit hash
                - tag: Tag name to checkout
                
        Examples:
            GitHandler("git://example.com/repo.git#main")
            GitHandler("git://example.com/repo.git", {"commit": "abc123"})
        """
        ...
        
    def checkout(
        self,
        container_manager: ContainerManager,
        container_handle: Any,
        dest_dir: str,
    ) -> Dict[str, str]:
        """Checkout source code to destination directory in container.
        
        Args:
            container_manager: Container manager for executing commands
            container_handle: Container handle (not just ID)
            dest_dir: Destination directory path (in container)
            
        Returns:
            Metadata dict with keys:
            - url: Original SCM URL
            - commit: Resolved commit hash (for git)
            - branch: Branch name (if applicable)
            - revision: Revision number (for svn)
            
        Raises:
            ContainerError: If checkout fails
            
        Example:
            metadata = handler.checkout(manager, handle, "/builddir/source")
            # Returns: {
            #     'url': 'git://example.com/repo.git',
            #     'commit': 'abc123def456...',
            #     'branch': 'main'
            # }
        """
        ...
