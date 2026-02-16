"""
Trac capability detection module.

Detects Trac server capabilities including:
- Trac version
- XML-RPC availability
- Markdown processor support
- Wiki processors available
"""

from .capabilities import CapabilityDetector, get_server_capabilities

__all__ = ["CapabilityDetector", "get_server_capabilities"]
