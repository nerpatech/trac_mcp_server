"""ToolSpec and ToolRegistry for permission-based tool filtering.

This module provides a centralized registry for MCP tools that supports
filtering based on Trac permissions, enabling operators to restrict which
tools are exposed to AI agents.

Key concepts:
- ToolSpec: Immutable dataclass linking a Tool definition, required permissions,
  and an async handler with standardized signature (client, args) -> CallToolResult.
- ToolRegistry: Filters specs by allowed permissions at construction time,
  then provides list_tools() and call_tool() dispatch.
- load_permissions_file: Reads a simple text file of Trac permission names.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import mcp.types as types

from ...core.client import TracClient


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Immutable specification for a single MCP tool.

    Attributes:
        tool: The MCP Tool definition (name, description, inputSchema).
        permissions: Trac permissions required to use this tool.
            Empty frozenset means the tool is always available (no permission needed).
        handler: Async handler with signature (client, args) -> CallToolResult.
    """

    tool: types.Tool
    permissions: frozenset[str]
    handler: Callable[[TracClient, dict], Awaitable[types.CallToolResult]]


class ToolRegistry:
    """Registry of ToolSpecs with optional permission-based filtering.

    If allowed_permissions is None, all specs are included (backward compat).
    Otherwise, a spec is included only if:
    - its permissions set is empty (always available), or
    - its permissions are a subset of allowed_permissions.
    """

    def __init__(
        self,
        specs: list[ToolSpec],
        allowed_permissions: frozenset[str] | None = None,
    ):
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            if (
                allowed_permissions is None
                or not spec.permissions
                or spec.permissions <= allowed_permissions
            ):
                self._specs[spec.tool.name] = spec

    def list_tools(self) -> list[types.Tool]:
        """Return list of types.Tool for all registered (permitted) specs."""
        return [spec.tool for spec in self._specs.values()]

    def tool_count(self) -> int:
        """Return number of registered tools."""
        return len(self._specs)

    async def call_tool(
        self,
        name: str,
        arguments: dict | None,
        client: TracClient,
    ) -> types.CallToolResult:
        """Dispatch tool call to registered handler.

        Args:
            name: Tool name to invoke.
            arguments: Tool arguments (may be None).
            client: TracClient instance.

        Returns:
            CallToolResult from the handler.

        Raises:
            ValueError: If tool name is not registered (unknown or filtered out).
        """
        spec = self._specs.get(name)
        if spec is None:
            raise ValueError(f"Unknown tool: {name}")
        args = arguments or {}
        return await spec.handler(client, args)


def load_permissions_file(path: str | Path) -> frozenset[str]:
    """Load permissions from a text file.

    Format: one permission per line, ``#`` for comments, blank lines ignored.

    Example file::

        # Read-only permissions
        TICKET_VIEW
        WIKI_VIEW
        MILESTONE_VIEW

    Args:
        path: Path to the permissions file.

    Returns:
        Frozenset of permission strings.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file contains invalid permissions or is empty.
    """
    path = Path(path)
    permissions: set[str] = set()
    for line_num, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Validate: Trac permissions are UPPER_SNAKE_CASE
        if not stripped.replace("_", "").isalpha() or not stripped.isupper():
            raise ValueError(
                f"Invalid permission '{stripped}' at line {line_num} in {path}. "
                "Expected UPPER_SNAKE_CASE (e.g., TICKET_VIEW)."
            )
        permissions.add(stripped)
    if not permissions:
        raise ValueError(
            f"No permissions found in {path}. File must contain at least one permission."
        )
    return frozenset(permissions)
