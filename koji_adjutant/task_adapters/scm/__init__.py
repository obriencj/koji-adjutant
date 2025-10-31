"""SCM integration module for source checkout operations.

Provides protocol-based abstraction for different SCM types (git, svn, cvs).
"""

from .base import SCMHandler
from .git import GitHandler, get_scm_handler

__all__ = [
    "SCMHandler",
    "GitHandler",
    "get_scm_handler",
]
