"""
Fetch strand - backward compatibility layer.

This module provides a compatibility shim for legacy imports.
The canonical fetch implementation is in orchestrator.py and commands.py.

DEPRECATED: Import from commands.py and orchestrator.py directly.
"""

# Re-export KUBECTL_PROXIES for backward compatibility
from .commands import KUBECTL_PROXIES

__all__ = ["KUBECTL_PROXIES"]
