"""Tests for MCP sync tool definitions and handlers.

Covers:
- Tool definitions have valid schemas
- handle_sync_tool dispatches correctly
- Error response for unknown profile
- dry_run parameter passes through
- doc_sync_status returns structured output
- Mock SyncEngine to avoid real sync
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import mcp.types as types

from trac_mcp_server.mcp.tools.sync import (
    SYNC_TOOLS,
    handle_sync_tool,
)
from trac_mcp_server.sync.models import (
    SyncAction,
    SyncReport,
    SyncResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync_profile_config(**overrides):
    """Build a mock SyncProfileConfig with defaults."""
    defaults = {
        "source": "/tmp/test-src",
        "destination": "wiki",
        "format": "auto",
        "direction": "bidirectional",
        "conflict_strategy": "interactive",
        "git_safety": "none",
        "mappings": [],
        "exclude": [],
        "state_dir": "/tmp/test-state",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_unified_config(profiles: dict | None = None):
    """Build a mock UnifiedConfig with optional sync profiles."""
    mock = MagicMock()
    mock.sync = profiles or {}
    return mock


def _make_report(dry_run: bool = False) -> SyncReport:
    """Build a minimal SyncReport for testing."""
    return SyncReport(
        profile_name="testing",
        dry_run=dry_run,
        results=[
            SyncResult(
                local_path="docs/readme.md",
                wiki_page="Wiki/Readme",
                action=SyncAction.PUSH,
                success=True,
            ),
        ],
        started_at="2026-02-07T10:00:00Z",
        completed_at="2026-02-07T10:01:00Z",
    )


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


class TestSyncToolDefinitions:
    """Tests for SYNC_TOOLS list."""

    def test_sync_tools_is_list(self):
        assert isinstance(SYNC_TOOLS, list)

    def test_has_two_tools(self):
        assert len(SYNC_TOOLS) == 2

    def test_tool_names(self):
        names = [t.name for t in SYNC_TOOLS]
        assert "doc_sync" in names
        assert "doc_sync_status" in names

    def test_doc_sync_schema(self):
        tool = next(t for t in SYNC_TOOLS if t.name == "doc_sync")
        schema = tool.inputSchema
        assert schema["type"] == "object"
        assert "profile" in schema["properties"]
        assert "dry_run" in schema["properties"]
        assert "source_root" in schema["properties"]
        assert "profile" in schema["required"]

    def test_doc_sync_status_schema(self):
        tool = next(
            t for t in SYNC_TOOLS if t.name == "doc_sync_status"
        )
        schema = tool.inputSchema
        assert schema["type"] == "object"
        assert "profile" in schema["properties"]
        assert "profile" in schema["required"]

    def test_all_tools_have_descriptions(self):
        for tool in SYNC_TOOLS:
            assert tool.description, f"{tool.name} missing description"

    def test_all_tools_have_annotations(self):
        for tool in SYNC_TOOLS:
            assert tool.annotations is not None, (
                f"{tool.name} missing annotations"
            )


# ---------------------------------------------------------------------------
# handle_sync_tool dispatch
# ---------------------------------------------------------------------------


class TestHandleSyncToolDispatch:
    """Tests for handle_sync_tool dispatcher."""

    async def test_unknown_tool_returns_error(self):
        client = MagicMock()
        result = await handle_sync_tool("unknown_tool", {}, client)
        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "Error" in result.content[0].text

    @patch("trac_mcp_server.mcp.tools.sync._load_unified_config")
    async def test_profile_not_found(self, mock_load_unified):
        """Unknown profile returns error with available profiles list."""
        mock_load_unified.return_value = _make_unified_config(
            {"planning": _make_sync_profile_config()}
        )
        client = MagicMock()
        result = await handle_sync_tool(
            "doc_sync", {"profile": "nonexistent"}, client
        )
        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "not found" in result.content[0].text.lower()
        assert "planning" in result.content[0].text

    @patch("trac_mcp_server.mcp.tools.sync._load_unified_config")
    async def test_missing_profile_param(self, mock_load_unified):
        """Missing profile parameter returns validation error."""
        mock_load_unified.return_value = _make_unified_config()
        client = MagicMock()
        result = await handle_sync_tool("doc_sync", {}, client)
        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "required" in result.content[0].text.lower()


# ---------------------------------------------------------------------------
# doc_sync
# ---------------------------------------------------------------------------


class TestDocSync:
    """Tests for doc_sync tool handler."""

    @patch("trac_mcp_server.mcp.tools.sync.SyncEngine")
    @patch("trac_mcp_server.mcp.tools.sync._load_unified_config")
    async def test_runs_sync_engine(
        self, mock_load_unified, mock_engine_cls
    ):
        """doc_sync creates SyncEngine and calls run()."""
        profile = _make_sync_profile_config()
        mock_load_unified.return_value = _make_unified_config(
            {"testing": profile}
        )

        mock_engine = MagicMock()
        mock_engine.run.return_value = _make_report()
        mock_engine_cls.return_value = mock_engine

        client = MagicMock()

        result = await handle_sync_tool(
            "doc_sync", {"profile": "testing"}, client
        )

        assert isinstance(result, types.CallToolResult)
        mock_engine.run.assert_called_once_with(dry_run=False)

    @patch("trac_mcp_server.mcp.tools.sync.SyncEngine")
    @patch("trac_mcp_server.mcp.tools.sync._load_unified_config")
    async def test_dry_run_passes_through(
        self, mock_load_unified, mock_engine_cls
    ):
        """dry_run=True is forwarded to SyncEngine.run()."""
        profile = _make_sync_profile_config()
        mock_load_unified.return_value = _make_unified_config(
            {"testing": profile}
        )

        mock_engine = MagicMock()
        mock_engine.run.return_value = _make_report(dry_run=True)
        mock_engine_cls.return_value = mock_engine

        client = MagicMock()
        result = await handle_sync_tool(
            "doc_sync",
            {"profile": "testing", "dry_run": True},
            client,
        )

        assert isinstance(result, types.CallToolResult)
        mock_engine.run.assert_called_once_with(dry_run=True)
        # Dry run output should contain the DRY RUN header
        first = result.content[0]
        assert isinstance(first, types.TextContent)
        assert "DRY RUN" in first.text

    @patch("trac_mcp_server.mcp.tools.sync.SyncEngine")
    @patch("trac_mcp_server.mcp.tools.sync._load_unified_config")
    async def test_structured_output(
        self, mock_load_unified, mock_engine_cls
    ):
        """Response includes structuredContent with report JSON."""
        profile = _make_sync_profile_config()
        mock_load_unified.return_value = _make_unified_config(
            {"testing": profile}
        )

        mock_engine = MagicMock()
        mock_engine.run.return_value = _make_report()
        mock_engine_cls.return_value = mock_engine

        client = MagicMock()
        result = await handle_sync_tool(
            "doc_sync", {"profile": "testing"}, client
        )

        assert isinstance(result, types.CallToolResult)
        structured = result.structuredContent
        assert structured is not None
        assert structured["profile_name"] == "testing"
        assert "counts" in structured
        assert "results" in structured

    @patch("trac_mcp_server.mcp.tools.sync.SyncEngine")
    @patch("trac_mcp_server.mcp.tools.sync._load_unified_config")
    async def test_source_root_override(
        self, mock_load_unified, mock_engine_cls
    ):
        """source_root parameter overrides profile source."""
        profile = _make_sync_profile_config(source="/original/path")
        mock_load_unified.return_value = _make_unified_config(
            {"testing": profile}
        )

        mock_engine = MagicMock()
        mock_engine.run.return_value = _make_report()
        mock_engine_cls.return_value = mock_engine

        client = MagicMock()
        await handle_sync_tool(
            "doc_sync",
            {"profile": "testing", "source_root": "/override/path"},
            client,
        )

        # Engine should have been created with the override path
        call_kwargs = mock_engine_cls.call_args
        assert call_kwargs.kwargs["source_root"] == Path(
            "/override/path"
        )


# ---------------------------------------------------------------------------
# doc_sync_status
# ---------------------------------------------------------------------------


class TestDocSyncStatus:
    """Tests for doc_sync_status tool handler."""

    @patch("trac_mcp_server.mcp.tools.sync.SyncState")
    @patch("trac_mcp_server.mcp.tools.sync._load_unified_config")
    async def test_returns_status(
        self, mock_load_unified, mock_state_cls
    ):
        """doc_sync_status returns profile status info."""
        profile = _make_sync_profile_config()
        mock_load_unified.return_value = _make_unified_config(
            {"testing": profile}
        )

        mock_state = MagicMock()
        mock_state.load.return_value = {
            "version": 1,
            "last_sync": "2026-02-07T09:00:00Z",
            "profile": "testing",
            "entries": {
                "a.md": {"wiki_page": "Wiki/A", "conflicted": False},
                "b.md": {"wiki_page": "Wiki/B", "conflicted": True},
            },
        }
        mock_state_cls.return_value = mock_state

        client = MagicMock()
        result = await handle_sync_tool(
            "doc_sync_status", {"profile": "testing"}, client
        )

        assert isinstance(result, types.CallToolResult)
        first = result.content[0]
        assert isinstance(first, types.TextContent)
        assert "testing" in first.text
        structured = result.structuredContent
        assert structured is not None
        assert structured["tracked_files"] == 2
        assert structured["conflicts"] == 1
        assert structured["last_sync"] == "2026-02-07T09:00:00Z"

    @patch("trac_mcp_server.mcp.tools.sync._load_unified_config")
    async def test_status_profile_not_found(self, mock_load_unified):
        """Unknown profile returns error."""
        mock_load_unified.return_value = _make_unified_config()
        client = MagicMock()
        result = await handle_sync_tool(
            "doc_sync_status", {"profile": "missing"}, client
        )
        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "not found" in result.content[0].text.lower()

    @patch("trac_mcp_server.mcp.tools.sync._load_unified_config")
    async def test_status_missing_profile_param(
        self, mock_load_unified
    ):
        """Missing profile parameter returns validation error."""
        mock_load_unified.return_value = _make_unified_config()
        client = MagicMock()
        result = await handle_sync_tool("doc_sync_status", {}, client)
        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "required" in result.content[0].text.lower()
