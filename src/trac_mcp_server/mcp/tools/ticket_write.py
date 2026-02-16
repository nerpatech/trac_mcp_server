"""Write ticket tool handlers for MCP server.

This module implements ticket write operations: create, update, and delete.
All tools use async handlers with run_sync() to bridge synchronous TracClient calls,
automatic Markdown conversion, and structured error responses.
"""

import xmlrpc.client
from typing import Any

import mcp.types as types

from ...converters import markdown_to_tracwiki
from ...core.async_utils import run_sync
from ...core.client import TracClient
from .constants import DEFAULT_TICKET_TYPE, TICKET_TYPE_LIST
from .errors import build_error_response, translate_xmlrpc_error


def _build_ticket_create_tool() -> types.Tool:
    """Build ticket_create tool definition with hardcoded defaults."""
    default_type = DEFAULT_TICKET_TYPE
    type_list = TICKET_TYPE_LIST
    return types.Tool(
        name="ticket_create",
        description="Create a new ticket. Accepts Markdown for description (auto-converted to TracWiki).",
        inputSchema={
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Ticket title (required)",
                },
                "description": {
                    "type": "string",
                    "description": "Ticket body in Markdown (will be converted to TracWiki)",
                },
                "ticket_type": {
                    "type": "string",
                    "description": f"Ticket type (default: {default_type}). Available types: {type_list}.",
                    "default": default_type,
                },
                "priority": {
                    "type": "string",
                    "description": "Priority level",
                },
                "component": {
                    "type": "string",
                    "description": "Component name",
                },
                "milestone": {
                    "type": "string",
                    "description": "Target milestone",
                },
                "owner": {
                    "type": "string",
                    "description": "Assignee username",
                },
                "cc": {
                    "type": "string",
                    "description": "CC email addresses",
                },
                "keywords": {
                    "type": "string",
                    "description": "Keywords/tags",
                },
            },
            "required": ["summary", "description"],
        },
    )


# Tool definitions for list_tools()
TICKET_WRITE_TOOLS = [
    _build_ticket_create_tool(),
    types.Tool(
        name="ticket_update",
        description="Update ticket attributes and/or add comments. Uses optimistic locking to prevent conflicts. Accepts Markdown for comments.",
        inputSchema={
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "Ticket number to update",
                    "minimum": 1,
                },
                "comment": {
                    "type": "string",
                    "description": "Comment in Markdown (optional, max 10000 chars)",
                },
                "status": {
                    "type": "string",
                    "description": "New status",
                },
                "priority": {
                    "type": "string",
                    "description": "New priority",
                },
                "component": {
                    "type": "string",
                    "description": "New component",
                },
                "milestone": {
                    "type": "string",
                    "description": "New milestone",
                },
                "owner": {"type": "string", "description": "New owner"},
                "resolution": {
                    "type": "string",
                    "description": "Resolution (when closing)",
                },
                "cc": {
                    "type": "string",
                    "description": "CC email addresses",
                },
                "keywords": {
                    "type": "string",
                    "description": "Keywords/tags",
                },
            },
            "required": ["ticket_id"],
        },
    ),
    types.Tool(
        name="ticket_delete",
        description="Delete a ticket permanently. Warning: This cannot be undone. Requires TICKET_ADMIN permission and 'tracopt.ticket.deleter' enabled in trac.ini.",
        inputSchema={
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "Ticket number to delete",
                    "minimum": 1,
                }
            },
            "required": ["ticket_id"],
        },
    ),
]


async def handle_ticket_write_tool(
    name: str,
    arguments: dict | None,
    client: TracClient,
) -> types.CallToolResult:
    """Handle write ticket tool execution.

    Args:
        name: Tool name (ticket_create, ticket_update, ticket_delete)
        arguments: Tool arguments (dict or None)
        client: Pre-configured TracClient instance

    Returns:
        CallToolResult for success messages, or CallToolResult with isError=True for errors

    Raises:
        ValueError: If tool name is unknown
    """
    # Ensure arguments is a dict
    args = arguments or {}

    try:
        match name:
            case "ticket_create":
                return await _handle_create(client, args)
            case "ticket_update":
                return await _handle_update(client, args)
            case "ticket_delete":
                return await _handle_delete(client, args)
            case _:
                raise ValueError(f"Unknown ticket write tool: {name}")

    except xmlrpc.client.Fault as e:
        return translate_xmlrpc_error(e, "ticket")
    except ValueError as e:
        return build_error_response(
            "validation_error",
            str(e),
            "Check parameter values and retry.",
        )
    except Exception as e:
        return build_error_response(
            "server_error",
            str(e),
            "Contact Trac administrator or retry later.",
        )


async def _handle_create(
    client: TracClient, args: dict
) -> types.CallToolResult:
    """Handle ticket_create."""
    summary = args.get("summary")
    description = args.get("description")

    if not summary:
        return build_error_response(
            "validation_error",
            "summary is required",
            "Provide summary parameter.",
        )
    if not description:
        return build_error_response(
            "validation_error",
            "description is required",
            "Provide description parameter.",
        )

    # Convert description from Markdown to TracWiki
    description_tracwiki = markdown_to_tracwiki(description)

    # Build attributes (hardcoded default for standalone server)
    ticket_type = args.get("ticket_type", DEFAULT_TICKET_TYPE)
    attributes: dict[str, Any] = {}

    # Add optional fields if provided
    if "priority" in args:
        attributes["priority"] = args["priority"]
    if "component" in args:
        attributes["component"] = args["component"]
    if "milestone" in args:
        attributes["milestone"] = args["milestone"]
    if "owner" in args:
        attributes["owner"] = args["owner"]
    if "cc" in args:
        attributes["cc"] = args["cc"]
    if "keywords" in args:
        attributes["keywords"] = args["keywords"]

    # Create ticket
    ticket_id = await run_sync(
        client.create_ticket,
        summary,
        description_tracwiki,
        ticket_type,
        attributes,
    )

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=f"Created ticket #{ticket_id}: {summary}",
            )
        ]
    )


async def _handle_update(
    client: TracClient, args: dict
) -> types.CallToolResult:
    """Handle ticket_update."""
    ticket_id = args.get("ticket_id")
    if not ticket_id:
        return build_error_response(
            "validation_error",
            "ticket_id is required",
            "Provide ticket_id parameter.",
        )

    # Convert comment from Markdown to TracWiki if provided
    comment = args.get("comment", "")
    if comment:
        comment = markdown_to_tracwiki(comment)

    # Build attributes dict (skip None values)
    attributes: dict[str, Any] = {}

    if "status" in args:
        attributes["status"] = args["status"]
    if "priority" in args:
        attributes["priority"] = args["priority"]
    if "component" in args:
        attributes["component"] = args["component"]
    if "milestone" in args:
        attributes["milestone"] = args["milestone"]
    if "owner" in args:
        attributes["owner"] = args["owner"]
    if "resolution" in args:
        attributes["resolution"] = args["resolution"]
    if "cc" in args:
        attributes["cc"] = args["cc"]
    if "keywords" in args:
        attributes["keywords"] = args["keywords"]

    # Update ticket (client handles optimistic locking)
    await run_sync(client.update_ticket, ticket_id, comment, attributes)

    # Build summary of changes
    changes = []
    if comment:
        changes.append("added comment")
    if attributes:
        changes.append(f"updated {len(attributes)} field(s)")

    change_summary = ", ".join(changes) if changes else "no changes"

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=f"Updated ticket #{ticket_id} ({change_summary})",
            )
        ]
    )


async def _handle_delete(
    client: TracClient, args: dict
) -> types.CallToolResult:
    """Handle ticket_delete."""
    ticket_id = args.get("ticket_id")
    if not ticket_id:
        return build_error_response(
            "validation_error",
            "ticket_id is required",
            "Provide ticket_id parameter.",
        )

    # Verify ticket exists before attempting deletion
    await run_sync(client.get_ticket, ticket_id)

    # Delete the ticket
    try:
        await run_sync(client.delete_ticket, ticket_id)
    except xmlrpc.client.Fault as e:
        # Provide specific guidance for permission errors
        if (
            "permission" in e.faultString.lower()
            or "denied" in e.faultString.lower()
        ):
            return build_error_response(
                "permission_denied",
                e.faultString,
                "This tool requires TICKET_ADMIN permission and 'tracopt.ticket.deleter' enabled in trac.ini. Contact Trac administrator.",
            )
        raise

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text", text=f"Deleted ticket #{ticket_id}."
            )
        ]
    )


