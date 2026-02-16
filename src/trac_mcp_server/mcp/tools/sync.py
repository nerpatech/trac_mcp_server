"""MCP tool handlers for bidirectional document sync.

Defines two tools:

- ``doc_sync`` -- run a named sync profile (with optional dry-run).
- ``doc_sync_status`` -- show state summary for a named sync profile.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import mcp.types as types

from ...config_loader import load_hierarchical_config
from ...config_schema import build_config
from ...core.client import TracClient
from ...sync.engine import SyncEngine
from ...sync.reporter import (
    format_dry_run_preview,
    format_sync_report,
    report_to_json,
)
from ...sync.state import SyncState
from .errors import build_error_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


SYNC_TOOLS: list[types.Tool] = [
    types.Tool(
        name="doc_sync",
        description=(
            "Synchronize local project files with Trac wiki pages using "
            "a named sync profile. Supports bidirectional sync with "
            "conflict detection."
        ),
        annotations=types.ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile": {
                    "type": "string",
                    "description": "Name of sync profile from config",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "Preview changes without applying them",
                },
                "source_root": {
                    "type": "string",
                    "description": (
                        "Override source directory (absolute path). Defaults to profile source."
                    ),
                },
            },
            "required": ["profile"],
        },
    ),
    types.Tool(
        name="doc_sync_status",
        description=(
            "Show sync state for a profile -- last sync time, number of tracked files, any unresolved conflicts."
        ),
        annotations=types.ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile": {
                    "type": "string",
                    "description": "Name of sync profile from config",
                },
            },
            "required": ["profile"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


async def handle_sync_tool(
    name: str,
    arguments: dict[str, Any] | None,
    client: TracClient,
) -> types.CallToolResult:
    """Dispatch and execute a sync tool.

    Args:
        name: Tool name (``doc_sync`` or ``doc_sync_status``).
        arguments: Tool arguments dict.
        client: Pre-configured TracClient instance.

    Returns:
        ``CallToolResult`` with tool output or error details.
    """
    args = arguments or {}

    try:
        match name:
            case "doc_sync":
                return await _handle_doc_sync(args, client)
            case "doc_sync_status":
                return await _handle_doc_sync_status(args)
            case _:
                raise ValueError(f"Unknown sync tool: {name}")

    except ValueError as exc:
        return build_error_response(
            "validation_error",
            str(exc),
            "Check parameter values and retry.",
        )
    except Exception as exc:
        logger.exception("Sync tool error: %s", exc)
        return build_error_response(
            "server_error",
            str(exc),
            "Check sync profile configuration and Trac connectivity.",
        )


# ---------------------------------------------------------------------------
# Individual handlers
# ---------------------------------------------------------------------------


def _load_unified_config():
    """Load the unified config from the hierarchical config system."""
    raw = load_hierarchical_config()
    return build_config(raw)


async def _handle_doc_sync(
    args: dict[str, Any],
    client: TracClient,
) -> types.CallToolResult:
    """Handle the ``doc_sync`` tool."""
    profile_name = args.get("profile")
    if not profile_name:
        return build_error_response(
            "validation_error",
            "profile is required",
            "Provide the 'profile' parameter with a sync profile name.",
        )

    dry_run = args.get("dry_run", False)
    source_root_override = args.get("source_root")

    # Load unified config to get sync profiles
    unified = _load_unified_config()

    if profile_name not in unified.sync:
        available = list(unified.sync.keys())
        return build_error_response(
            "not_found",
            f"Sync profile '{profile_name}' not found.",
            f"Available profiles: {available}. "
            "Check your sync configuration file (.trac_mcp/config.yaml) for valid sync profiles.",
        )

    profile = unified.sync[profile_name]

    # Determine source root
    if source_root_override:
        source_root = Path(source_root_override)
    else:
        source_root = Path(profile.source).resolve()

    # Use provided TracClient instance

    # Create engine and run
    engine = SyncEngine(
        client=client,
        profile=profile,
        profile_name=profile_name,
        source_root=source_root,
    )
    report = engine.run(dry_run=dry_run)

    # Format output
    if dry_run:
        text = format_dry_run_preview(report)
    else:
        text = format_sync_report(report)

    structured = report_to_json(report)

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=structured,
    )


async def _handle_doc_sync_status(
    args: dict[str, Any],
) -> types.CallToolResult:
    """Handle the ``doc_sync_status`` tool."""
    profile_name = args.get("profile")
    if not profile_name:
        return build_error_response(
            "validation_error",
            "profile is required",
            "Provide the 'profile' parameter with a sync profile name.",
        )

    # Load unified config to validate profile exists
    unified = _load_unified_config()

    if profile_name not in unified.sync:
        available = list(unified.sync.keys())
        return build_error_response(
            "not_found",
            f"Sync profile '{profile_name}' not found.",
            f"Available profiles: {available}. "
            "Check your sync configuration file (.trac_mcp/config.yaml) for valid sync profiles.",
        )

    profile = unified.sync[profile_name]

    # Load sync state
    state_store = SyncState(Path(profile.state_dir))
    state = state_store.load(profile_name)

    # Build status summary
    entries = state.get("entries", {})
    total_files = len(entries)
    conflicted = sum(
        1 for e in entries.values() if e.get("conflicted", False)
    )
    last_sync = state.get("last_sync", "never")

    lines = [
        f"Sync status for '{profile_name}'",
        f"  Direction:   {profile.direction}",
        f"  Source:      {profile.source}",
        f"  Destination: {profile.destination}",
        f"  Last sync:   {last_sync}",
        f"  Tracked files: {total_files}",
        f"  Conflicts:     {conflicted}",
    ]
    text = "\n".join(lines)

    structured = {
        "profile_name": profile_name,
        "direction": profile.direction,
        "source": profile.source,
        "destination": profile.destination,
        "last_sync": last_sync,
        "tracked_files": total_files,
        "conflicts": conflicted,
    }

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=structured,
    )
