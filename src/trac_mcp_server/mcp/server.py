"""MCP Server for Trac integration using stdio transport.

This module implements the Model Context Protocol server that enables
AI agents to interact with Trac via standardized tools and resources.

Transport: stdio (for Claude Desktop/Code integration)
Protocol: JSON-RPC 2.0 over MCP

Note: Resources capability enables wiki page access via MCP resource protocol.
"""

import argparse
import asyncio
import logging
import sys

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic_core import Url

from .. import __version__
from ..core.async_utils import run_sync
from ..core.client import TracClient
from ..logger import setup_logging
from ..version import check_version_consistency
from .lifespan import server_lifespan
from .resources.wiki import (
    handle_list_wiki_resources,
    handle_read_wiki_resource,
)
from .tools import (
    ALL_SPECS,
    ToolRegistry,
    build_error_response,
    load_permissions_file,
)
from .tools.registry import ToolSpec

logger = logging.getLogger(__name__)

# Initialize server instance
server = Server("trac-mcp-server")

# Global client instance (initialized in lifespan)
_trac_client: TracClient | None = None

# Global registry instance (initialized in main)
_registry: ToolRegistry | None = None


# ---------------------------------------------------------------------------
# Ping tool (always available, no Trac permission required)
# ---------------------------------------------------------------------------


async def _handle_ping(
    client: TracClient, args: dict
) -> types.CallToolResult:
    """Handle ping tool -- test Trac connectivity."""
    try:
        version = await run_sync(client.validate_connection)
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"Trac MCP server connected successfully. API version: {version}",
                )
            ]
        )
    except Exception as e:
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"Trac connection failed: {e}. Check TRAC_URL, TRAC_USERNAME, TRAC_PASSWORD.",
                )
            ],
            isError=True,
        )


PING_SPEC = ToolSpec(
    tool=types.Tool(
        name="ping",
        description="Test Trac MCP server connectivity and return API version",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    permissions=frozenset(),
    handler=_handle_ping,
)


# ---------------------------------------------------------------------------
# Global accessors (same pattern as _trac_client)
# ---------------------------------------------------------------------------


def get_client() -> TracClient:
    """Get the global TracClient instance.

    Returns:
        TracClient instance

    Raises:
        RuntimeError: If client is not initialized
    """
    if _trac_client is None:
        raise RuntimeError(
            "TracClient not initialized. Server lifespan not started."
        )
    return _trac_client


def set_client(client: TracClient | None) -> None:
    """Set the global TracClient instance.

    Args:
        client: TracClient instance to set, or None to clear
    """
    global _trac_client
    _trac_client = client


def get_registry() -> ToolRegistry:
    """Get the global ToolRegistry instance.

    Returns:
        ToolRegistry instance

    Raises:
        RuntimeError: If registry is not initialized
    """
    if _registry is None:
        raise RuntimeError("ToolRegistry not initialized.")
    return _registry


def set_registry(registry: ToolRegistry | None) -> None:
    """Set the global ToolRegistry instance.

    Args:
        registry: ToolRegistry instance to set, or None to clear
    """
    global _registry
    _registry = registry


# ---------------------------------------------------------------------------
# MCP protocol handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available Trac tools.

    Returns all registered (and permitted) tools from the ToolRegistry.
    """
    return get_registry().list_tools()


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """List available Trac resources.

    Returns wiki resources for reading wiki pages via URI templates.
    """
    return await handle_list_wiki_resources()


@server.read_resource()  # type: ignore[arg-type]  # MCP Url type mismatch
async def handle_read_resource(uri: Url) -> str:
    """Read a Trac resource by URI.

    Supports:
    - trac://wiki/{page_name} - Read wiki page (Markdown by default)
    - trac://wiki/{page_name}?format=tracwiki - Read raw TracWiki
    - trac://wiki/{page_name}?version=N - Read historical version
    - trac://wiki/_index - List all wiki pages with tree structure

    Args:
        uri: Resource URI (e.g., trac://wiki/WikiStart)

    Returns:
        Resource content as formatted text

    Raises:
        ValueError: If URI scheme or path is not recognized
    """
    # Validate URI scheme
    if uri.scheme != "trac":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    # Route by resource type (host portion of URI)
    if uri.host == "wiki":
        client = get_client()
        return await handle_read_wiki_resource(uri, client)

    raise ValueError(f"Unknown resource type: {uri.host}")


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> types.CallToolResult:
    """Handle tool execution via ToolRegistry dispatch.

    Args:
        name: The name of the tool to execute.
        arguments: Tool arguments (optional).

    Returns:
        CallToolResult with tool output content and optional isError flag.
    """
    client = get_client()
    try:
        return await get_registry().call_tool(name, arguments, client)
    except ValueError as e:
        # Unknown or filtered-out tool name
        return build_error_response(
            "unknown_tool",
            str(e),
            "Use list_tools to see available tools.",
        )


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


async def main(config_overrides: dict | None = None):
    """Run the MCP server with stdio transport.

    This function sets up logging for MCP mode (file only, never stdout),
    validates Trac connection via lifespan manager, and starts the server
    with stdio transport for JSON-RPC communication.

    Args:
        config_overrides: Optional dict with config values to override (url, username, password, insecure, log_file)
    """
    # Extract log file override if provided
    log_file = (
        config_overrides.get("log_file") if config_overrides else None
    )

    # Setup logging for MCP mode (file only, never stdout)
    # CRITICAL: This must be called BEFORE stdio_server context
    # to prevent any stdout contamination during protocol negotiation
    setup_logging(mode="mcp", log_file=log_file)

    # Version check (non-blocking warning for stale binaries)
    is_consistent, message = check_version_consistency()
    if not is_consistent:
        logger.warning(message)
        sys.stderr.write(f"\u26a0\ufe0f  Warning: {message}\n")
    else:
        logger.info(message)

    # Build ToolRegistry with optional permission filtering
    permissions_file = (
        config_overrides.get("permissions_file")
        if config_overrides
        else None
    )
    allowed_permissions = None
    if permissions_file:
        allowed_permissions = load_permissions_file(permissions_file)
        logger.info(
            "Loaded %d permissions from %s",
            len(allowed_permissions),
            permissions_file,
        )

    all_specs = [PING_SPEC] + ALL_SPECS
    registry = ToolRegistry(all_specs, allowed_permissions)
    logger.info(
        "Registered %d tools (of %d total)",
        registry.tool_count(),
        len(all_specs),
    )

    if permissions_file:
        print(
            f"Permissions file: {permissions_file} "
            f"({registry.tool_count()} of {len(all_specs)} tools enabled)",
            file=sys.stderr,
        )

    set_registry(registry)

    # Use lifespan manager for startup validation with config overrides.
    # NOTE: We call set_client() directly here rather than in the lifespan
    # to avoid the Python __main__ module duplication bug. When this file
    # is run via `python -m trac_mcp_server.mcp.server`, the module is
    # loaded as __main__, but `from . import server` in lifespan.py would
    # re-import it as trac_mcp_server.mcp.server (a separate copy),
    # causing set_client() to modify the wrong module's _trac_client.
    async with server_lifespan(
        config_overrides=config_overrides
    ) as ctx:
        set_client(ctx["client"])
        try:
            async with mcp.server.stdio.stdio_server() as (
                read_stream,
                write_stream,
            ):
                init_options = InitializationOptions(
                    server_name="trac-mcp-server",
                    server_version=__version__,
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                )
                await server.run(
                    read_stream, write_stream, init_options
                )
        finally:
            set_client(None)
            set_registry(None)


def run() -> None:
    """Entry point that handles errors gracefully and parses CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Trac MCP Server - Model Context Protocol server for Trac integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default config (from .env or config.yaml)
  trac-mcp-server

  # Override Trac URL
  trac-mcp-server --url https://trac.example.com

  # Override all connection settings
  trac-mcp-server --url https://trac.example.com --username admin --password secret

  # Use with insecure SSL (development only)
  trac-mcp-server --url http://localhost:8000 --insecure

  # Custom log file location
  trac-mcp-server --log-file /var/log/trac-mcp-server.log

  # Restrict tools by Trac permissions
  trac-mcp-server --permissions-file /etc/trac-mcp/read-only.permissions

Note: This server uses stdio transport for JSON-RPC communication with MCP clients.
All user-facing messages are written to stderr. Do not pipe stdin/stdout manually.
        """,
    )

    parser.add_argument(
        "--url",
        help="Override Trac instance URL (takes precedence over TRAC_URL env var and config files)",
    )
    parser.add_argument(
        "--username",
        help="Override Trac username (takes precedence over TRAC_USERNAME env var and config files)",
    )
    parser.add_argument(
        "--password",
        help="Override Trac password (takes precedence over TRAC_PASSWORD env var and config files)"
        " (visible in process list -- prefer TRAC_PASSWORD env var for security)",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip SSL certificate verification (use only for development)",
    )
    parser.add_argument(
        "--log-file",
        default="/tmp/trac-mcp-server.log",
        help="Log file path (default: /tmp/trac-mcp-server.log)",
    )
    parser.add_argument(
        "--permissions-file",
        help="Path to permissions file restricting available tools. "
        "Format: one Trac permission per line (e.g., TICKET_VIEW), # for comments. "
        "If not specified, all tools are available.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"trac-mcp-server version {__version__}",
    )

    args = parser.parse_args()

    # Build config overrides dict from CLI args
    config_overrides = {}
    if args.url:
        config_overrides["url"] = args.url
    if args.username:
        config_overrides["username"] = args.username
    if args.password:
        config_overrides["password"] = args.password
    if args.insecure:
        config_overrides["insecure"] = True
    if args.log_file:
        config_overrides["log_file"] = args.log_file
    if args.permissions_file:
        config_overrides["permissions_file"] = args.permissions_file

    # Log config overrides to stderr (before stdio transport starts)
    if config_overrides:
        override_keys = [
            k for k in config_overrides.keys() if k != "password"
        ]
        print(
            f"Config overrides from CLI: {', '.join(override_keys)}",
            file=sys.stderr,
        )

    try:
        asyncio.run(
            main(
                config_overrides=config_overrides
                if config_overrides
                else None
            )
        )
    except RuntimeError:
        # Error already printed to stderr by lifespan manager
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    run()
