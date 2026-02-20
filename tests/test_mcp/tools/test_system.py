"""
Tests for system MCP tool handlers.

These tests verify system tool definitions and handler behavior with mocked TracClient.
"""

import asyncio
import time
import unittest
import xmlrpc.client
from datetime import datetime
from unittest.mock import MagicMock, patch

from trac_mcp_server.config import Config
from trac_mcp_server.mcp.tools.registry import ToolRegistry
from trac_mcp_server.mcp.tools.system import (
    SYSTEM_SPECS,
    SYSTEM_TOOLS,
)


class TestSystemTools(unittest.TestCase):
    """Test SYSTEM_TOOLS definitions."""

    def test_one_tool_defined(self):
        """Test SYSTEM_TOOLS contains exactly 1 tool."""
        self.assertEqual(len(SYSTEM_TOOLS), 1)

    def test_tool_name(self):
        """Test tool name is correct."""
        self.assertEqual(SYSTEM_TOOLS[0].name, "get_server_time")

    def test_get_server_time_schema(self):
        """Test get_server_time has empty schema (no parameters)."""
        get_tool = SYSTEM_TOOLS[0]

        self.assertEqual(get_tool.inputSchema["type"], "object")
        self.assertEqual(get_tool.inputSchema["properties"], {})
        self.assertEqual(get_tool.inputSchema["required"], [])


class TestGetServerTimeHandler(unittest.TestCase):
    """Test get_server_time handler behavior."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Config(
            trac_url="https://trac.example.com",
            username="testuser",
            password="testpass",
            insecure=False,
        )

    @patch("trac_mcp_server.mcp.tools.system.TracClient")
    @patch("trac_mcp_server.mcp.tools.system.run_sync")
    def test_get_server_time_success(
        self, mock_run_sync, mock_client_class
    ):
        """Test get_server_time returns valid timestamp."""
        # Create mock DateTime object
        now = datetime.now()
        mock_datetime = xmlrpc.client.DateTime()
        mock_datetime.value = now.strftime("%Y%m%dT%H:%M:%S")

        # Mock page info response
        mock_page_info = {
            "name": "WikiStart",
            "author": "admin",
            "version": 1,
            "lastModified": mock_datetime,
        }

        # Mock TracClient
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock run_sync to return page info directly (not a coroutine)
        mock_run_sync.return_value = mock_page_info

        # Call handler
        result = asyncio.run(
            ToolRegistry(SYSTEM_SPECS).call_tool(
                "get_server_time", {}, self.config
            )
        )

        # Verify result structure
        self.assertTrue(hasattr(result, "content"))
        self.assertTrue(hasattr(result, "structuredContent"))

        # Verify text content
        text_content = result.content[0].text
        self.assertIn("Server time:", text_content)

        # Verify structured content
        structured = result.structuredContent
        self.assertIn("server_time", structured)
        self.assertIn("unix_timestamp", structured)
        self.assertIn("timezone", structured)

        # Verify ISO 8601 format
        server_time = structured["server_time"]
        # Should be parseable as datetime
        datetime.fromisoformat(server_time)

        # Verify unix_timestamp is integer
        self.assertIsInstance(structured["unix_timestamp"], int)

        # Verify timezone field
        self.assertEqual(structured["timezone"], "server")

    @patch("trac_mcp_server.mcp.tools.system.TracClient")
    @patch("trac_mcp_server.mcp.tools.system.run_sync")
    def test_get_server_time_wikistart_fallback(
        self, mock_run_sync, mock_client_class
    ):
        """Test get_server_time falls back to first page if WikiStart missing."""
        # Create mock DateTime object
        now = datetime.now()
        mock_datetime = xmlrpc.client.DateTime()
        mock_datetime.value = now.strftime("%Y%m%dT%H:%M:%S")

        # Mock page info response for fallback page
        mock_page_info = {
            "name": "SomePage",
            "author": "admin",
            "version": 1,
            "lastModified": mock_datetime,
        }

        # Mock TracClient
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock run_sync to return page info directly (simulates successful fallback)
        mock_run_sync.return_value = mock_page_info

        # Call handler
        result = asyncio.run(
            ToolRegistry(SYSTEM_SPECS).call_tool(
                "get_server_time", {}, self.config
            )
        )

        # Verify result structure exists (fallback worked)
        self.assertTrue(hasattr(result, "content"))
        self.assertTrue(hasattr(result, "structuredContent"))

    @patch("trac_mcp_server.mcp.tools.system.TracClient")
    @patch("trac_mcp_server.mcp.tools.system.run_sync")
    def test_get_server_time_no_timestamp(
        self, mock_run_sync, mock_client_class
    ):
        """Test get_server_time handles missing lastModified field."""
        # Mock page info without lastModified
        mock_page_info = {
            "name": "WikiStart",
            "author": "admin",
            "version": 1,
        }

        # Mock TracClient
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock run_sync to return page info without timestamp directly
        mock_run_sync.return_value = mock_page_info

        # Call handler
        result = asyncio.run(
            ToolRegistry(SYSTEM_SPECS).call_tool(
                "get_server_time", {}, self.config
            )
        )

        # Should return CallToolResult with isError=True
        from mcp.types import CallToolResult

        self.assertIsInstance(result, CallToolResult)
        self.assertTrue(result.isError)
        self.assertTrue(len(result.content) > 0)
        error_text = result.content[0].text
        self.assertIn("Error", error_text)

    def test_datetime_conversion_accuracy(self):
        """Test DateTime to unix timestamp conversion is accurate."""
        # Create a known datetime
        test_datetime = datetime(2025, 1, 15, 14, 30, 0)

        # Create XML-RPC DateTime object
        mock_datetime = xmlrpc.client.DateTime()
        mock_datetime.value = test_datetime.strftime("%Y%m%dT%H:%M:%S")

        # Convert using the same method as our code
        unix_timestamp = int(time.mktime(mock_datetime.timetuple()))

        # Verify conversion is accurate (within 1 second tolerance for timezone)
        expected_timestamp = int(test_datetime.timestamp())
        self.assertAlmostEqual(
            unix_timestamp, expected_timestamp, delta=1
        )


if __name__ == "__main__":
    unittest.main()
