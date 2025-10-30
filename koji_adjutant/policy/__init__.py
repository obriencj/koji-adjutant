"""Hub policy-driven container image selection.

This module provides PolicyResolver for resolving container images
based on hub-configured policies (ADR 0003).
"""

from .resolver import PolicyResolver

__all__ = ["PolicyResolver"]
