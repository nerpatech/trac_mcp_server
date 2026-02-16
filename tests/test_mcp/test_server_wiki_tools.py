"""Tests for wiki tool registration and routing in MCP server.

Verifies:
- Wiki tools appear in handle_list_tools with correct schemas
- Wiki tool calls route to the correct handler (read vs write)
- Unknown wiki tools return error response

Note: Detailed handler behavior and error handling are tested in
tests/test_mcp/tools/test_wiki.py — this file only tests the server
routing layer.
"""

import asyncio
from unittest.mock import MagicMock, patch

import mcp.types as types

from trac_mcp_server.mcp.server import (
    handle_call_tool,
    handle_list_tools,
)


# ---------------------------------------------------------------------------
# Registration tests — verify tool schemas
# ---------------------------------------------------------------------------


class TestWikiToolRegistration:
    """Test wiki tools are registered in handle_list_tools."""

    def test_wiki_tools_registered(self):
        """All 4 wiki tools appear in handle_list_tools response."""
        tools = asyncio.run(handle_list_tools())
        tool_names = [t.name for t in tools]

        assert "wiki_get" in tool_names
        assert "wiki_search" in tool_names
        assert "wiki_create" in tool_names
        assert "wiki_update" in tool_names

    def test_wiki_tool_schemas(self):
        """Wiki tools have expected inputSchema structure."""
        tools = asyncio.run(handle_list_tools())
        wiki_tools = [t for t in tools if t.name.startswith("wiki_")]

        for tool in wiki_tools:
            assert tool.inputSchema is not None
            assert tool.inputSchema["type"] == "object"
            assert "properties" in tool.inputSchema
            assert "required" in tool.inputSchema

    def test_wiki_get_schema_details(self):
        """wiki_get has correct schema."""
        tools = asyncio.run(handle_list_tools())
        get_tool = next(t for t in tools if t.name == "wiki_get")

        assert "page_name" in get_tool.inputSchema["properties"]
        assert "version" in get_tool.inputSchema["properties"]
        assert get_tool.inputSchema["required"] == ["page_name"]

    def test_wiki_search_schema_details(self):
        """wiki_search has correct schema."""
        tools = asyncio.run(handle_list_tools())
        search_tool = next(t for t in tools if t.name == "wiki_search")

        assert "query" in search_tool.inputSchema["properties"]
        assert "prefix" in search_tool.inputSchema["properties"]
        assert "limit" in search_tool.inputSchema["properties"]
        assert "cursor" in search_tool.inputSchema["properties"]
        assert search_tool.inputSchema["required"] == ["query"]

    def test_wiki_create_schema_details(self):
        """wiki_create has correct schema."""
        tools = asyncio.run(handle_list_tools())
        create_tool = next(t for t in tools if t.name == "wiki_create")

        assert "page_name" in create_tool.inputSchema["properties"]
        assert "content" in create_tool.inputSchema["properties"]
        assert "comment" in create_tool.inputSchema["properties"]
        assert sorted(create_tool.inputSchema["required"]) == [
            "content",
            "page_name",
        ]

    def test_wiki_update_schema_details(self):
        """wiki_update has correct schema."""
        tools = asyncio.run(handle_list_tools())
        update_tool = next(t for t in tools if t.name == "wiki_update")

        assert "page_name" in update_tool.inputSchema["properties"]
        assert "content" in update_tool.inputSchema["properties"]
        assert "version" in update_tool.inputSchema["properties"]
        assert "comment" in update_tool.inputSchema["properties"]
        assert sorted(update_tool.inputSchema["required"]) == [
            "content",
            "page_name",
            "version",
        ]


# ---------------------------------------------------------------------------
# Routing tests — verify dispatch to correct handler
# ---------------------------------------------------------------------------


class TestWikiToolRouting:
    """Test wiki tool calls route to the correct handler."""

    @patch("trac_mcp_server.mcp.server.handle_wiki_read_tool")
    @patch("trac_mcp_server.mcp.server.get_client")
    def test_wiki_read_tools_route_to_read_handler(
        self, mock_get_client, mock_handler
    ):
        """wiki_get routes to handle_wiki_read_tool."""
        mock_get_client.return_value = MagicMock()
        mock_handler.return_value = types.CallToolResult(
            content=[types.TextContent(type="text", text="ok")]
        )

        result = asyncio.run(
            handle_call_tool("wiki_get", {"page_name": "Test"})
        )

        mock_handler.assert_called_once()
        assert not result.isError

    @patch("trac_mcp_server.mcp.server.handle_wiki_write_tool")
    @patch("trac_mcp_server.mcp.server.get_client")
    def test_wiki_write_tools_route_to_write_handler(
        self, mock_get_client, mock_handler
    ):
        """wiki_create routes to handle_wiki_write_tool."""
        mock_get_client.return_value = MagicMock()
        mock_handler.return_value = types.CallToolResult(
            content=[types.TextContent(type="text", text="created")]
        )

        result = asyncio.run(
            handle_call_tool(
                "wiki_create",
                {"page_name": "New", "content": "# New"},
            )
        )

        mock_handler.assert_called_once()
        assert not result.isError

    @patch("trac_mcp_server.mcp.server.get_client")
    def test_unknown_wiki_tool_returns_error(self, mock_get_client):
        """Unknown wiki_* tool returns error response."""
        mock_get_client.return_value = MagicMock()

        result = asyncio.run(handle_call_tool("wiki_unknown", {}))

        assert isinstance(result, types.CallToolResult)
        assert result.isError
        assert "Unknown wiki" in result.content[0].text
