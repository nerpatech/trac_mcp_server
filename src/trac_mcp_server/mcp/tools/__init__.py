"""MCP tool handlers for Trac operations.

This package contains MCP tool implementations that wrap the core TracClient
with async handlers, Markdown conversion, and structured error responses.
"""

from .errors import build_error_response
from .milestone import MILESTONE_TOOLS, handle_milestone_tool
from .system import SYSTEM_TOOLS, handle_system_tool
from .ticket_batch import TICKET_BATCH_TOOLS, handle_ticket_batch_tool
from .ticket_read import TICKET_READ_TOOLS, handle_ticket_read_tool
from .ticket_write import TICKET_WRITE_TOOLS, handle_ticket_write_tool
from .wiki_file import WIKI_FILE_TOOLS, handle_wiki_file_tool
from .wiki_read import WIKI_READ_TOOLS, handle_wiki_read_tool
from .wiki_write import WIKI_WRITE_TOOLS, handle_wiki_write_tool

# Combine ticket tools for backward compatibility
TICKET_TOOLS = (
    TICKET_READ_TOOLS + TICKET_WRITE_TOOLS + TICKET_BATCH_TOOLS
)
WIKI_TOOLS = WIKI_READ_TOOLS + WIKI_WRITE_TOOLS

__all__ = [
    "build_error_response",
    "TICKET_TOOLS",
    "TICKET_READ_TOOLS",
    "TICKET_WRITE_TOOLS",
    "TICKET_BATCH_TOOLS",
    "handle_ticket_read_tool",
    "handle_ticket_write_tool",
    "handle_ticket_batch_tool",
    "WIKI_TOOLS",
    "WIKI_READ_TOOLS",
    "WIKI_WRITE_TOOLS",
    "handle_wiki_read_tool",
    "handle_wiki_write_tool",
    "WIKI_FILE_TOOLS",
    "handle_wiki_file_tool",
    "MILESTONE_TOOLS",
    "handle_milestone_tool",
    "SYSTEM_TOOLS",
    "handle_system_tool",
]
