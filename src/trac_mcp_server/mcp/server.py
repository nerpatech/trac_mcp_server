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
    TICKET_TOOLS,
    WIKI_TOOLS,
    handle_ticket_batch_tool,
    handle_ticket_read_tool,
    handle_ticket_write_tool,
    handle_wiki_read_tool,
    handle_wiki_write_tool,
)
from .tools.milestone import MILESTONE_TOOLS, handle_milestone_tool
from .tools.system import SYSTEM_TOOLS, handle_system_tool
from .tools.wiki_file import WIKI_FILE_TOOLS, handle_wiki_file_tool

logger = logging.getLogger(__name__)

# Initialize server instance
server = Server("trac-mcp-server")

# Global client instance (initialized in lifespan)
_trac_client: TracClient | None = None


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


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available Trac tools.

    Returns all registered tools including trac_ping for connectivity testing,
    all ticket tools (search, get, create, update, changelog, fields),
    wiki tools (get, search, create, update), and milestone tools
    (list, get, create, update, delete).
    """
    return (
        [
            types.Tool(
                name="ping",
                description="Test Trac MCP server connectivity and return API version",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            )
        ]
        + SYSTEM_TOOLS
        + TICKET_TOOLS
        + WIKI_TOOLS
        + WIKI_FILE_TOOLS
        + MILESTONE_TOOLS
    )


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
    """Handle tool execution.

    Args:
        name: The name of the tool to execute.
        arguments: Tool arguments (optional).

    Returns:
        CallToolResult with tool output content and optional isError flag.

    Raises:
        ValueError: If the tool name is unknown.
    """
    # Get the shared TracClient instance
    client = get_client()

    match name:
        case "ping":
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

        case _ if name.startswith("ticket_"):
            # Route to read, batch, or write handler based on tool name
            if name in (
                "ticket_search",
                "ticket_get",
                "ticket_changelog",
                "ticket_fields",
                "ticket_actions",
            ):
                return await handle_ticket_read_tool(
                    name, arguments, client
                )
            elif name.startswith("ticket_batch_"):
                return await handle_ticket_batch_tool(
                    name, arguments, client
                )
            else:
                return await handle_ticket_write_tool(
                    name, arguments, client
                )

        case _ if name.startswith("wiki_file_"):
            return await handle_wiki_file_tool(name, arguments, client)

        case _ if name.startswith("wiki_"):
            # Route to read or write handler based on tool name
            if name in (
                "wiki_get",
                "wiki_search",
                "wiki_recent_changes",
            ):
                return await handle_wiki_read_tool(
                    name, arguments, client
                )
            else:
                return await handle_wiki_write_tool(
                    name, arguments, client
                )

        case _ if name.startswith("milestone_"):
            return await handle_milestone_tool(name, arguments, client)

        case "get_server_time":
            return await handle_system_tool(name, arguments, client)

        case _:
            raise ValueError(f"Unknown tool: {name}")


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
        sys.stderr.write(f"⚠️  Warning: {message}\n")
    else:
        logger.info(message)

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
        " (visible in process list — prefer TRAC_PASSWORD env var for security)",
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
