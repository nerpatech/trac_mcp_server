"""Tests for ticket tool handlers."""

import asyncio
import unittest
import xmlrpc.client
from datetime import datetime
from unittest.mock import MagicMock, patch

import mcp.types as types

from trac_mcp_server.config import Config
from trac_mcp_server.converters.common import ConversionResult
from trac_mcp_server.core.client import TracClient
from trac_mcp_server.mcp.tools import TICKET_TOOLS
from trac_mcp_server.mcp.tools.ticket_read import (
    _handle_actions,
    _handle_changelog,
    _handle_fields,
    _handle_get,
    _handle_search,
    handle_ticket_read_tool,
)
from trac_mcp_server.mcp.tools.ticket_write import (
    _handle_create,
    _handle_delete,
    _handle_update,
)
from trac_mcp_server.mcp.tools.ticket_write import (
    handle_ticket_write_tool as handle_ticket_tool,
)


class TestTicketDeleteSchema(unittest.TestCase):
    """Tests for ticket_delete tool schema."""

    def test_ticket_delete_schema(self):
        """Test ticket_delete tool has correct schema."""
        tool = next(
            t for t in TICKET_TOOLS if t.name == "ticket_delete"
        )
        self.assertEqual(tool.name, "ticket_delete")
        description = tool.description or ""
        self.assertIn("delete", description.lower())
        self.assertIn("TICKET_ADMIN", description)
        schema = tool.inputSchema
        self.assertIn("ticket_id", schema["properties"])
        self.assertEqual(schema["required"], ["ticket_id"])
        self.assertEqual(
            schema["properties"]["ticket_id"]["type"], "integer"
        )
        self.assertEqual(
            schema["properties"]["ticket_id"]["minimum"], 1
        )


class TestHandleDelete(unittest.TestCase):
    """Tests for _handle_delete handler."""

    def setUp(self):
        self.mock_client = MagicMock()

    def test_handle_delete_success(self):
        """Test _handle_delete deletes ticket successfully."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write.run_sync"
        ) as mock_run_sync:
            # First call: get_ticket (existence check), Second call: delete_ticket
            mock_run_sync.return_value = True

            result = asyncio.run(
                _handle_delete(self.mock_client, {"ticket_id": 42})
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Deleted ticket #42", result.content[0].text)

            # Verify both get_ticket (existence check) and delete_ticket were called
            self.assertEqual(mock_run_sync.call_count, 2)
            # First call: existence check with get_ticket
            first_call_args = mock_run_sync.call_args_list[0][0]
            self.assertEqual(
                first_call_args[0], self.mock_client.get_ticket
            )
            self.assertEqual(first_call_args[1], 42)
            # Second call: delete_ticket
            second_call_args = mock_run_sync.call_args_list[1][0]
            self.assertEqual(
                second_call_args[0], self.mock_client.delete_ticket
            )
            self.assertEqual(second_call_args[1], 42)

    def test_handle_delete_missing_ticket_id(self):
        """Test _handle_delete returns error when ticket_id is missing."""
        result = asyncio.run(_handle_delete(self.mock_client, {}))

        self.assertIsInstance(result, types.CallToolResult)
        self.assertTrue(result.isError)
        self.assertEqual(len(result.content), 1)
        self.assertIn(
            "Error (validation_error)", result.content[0].text
        )
        self.assertIn("ticket_id is required", result.content[0].text)

    def test_handle_delete_ticket_not_found(self):
        """Test _handle_delete handles ticket not found via handle_ticket_tool error translation."""
        config = Config(
            trac_url="http://test", username="test", password="test"
        )
        mock_client = MagicMock()
        mock_client.config = config

        with patch(
            "trac_mcp_server.mcp.tools.ticket_write.run_sync"
        ) as mock_run_sync:
            mock_run_sync.side_effect = xmlrpc.client.Fault(
                404, "Ticket 99999 not found"
            )

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_delete", {"ticket_id": 99999}, mock_client
                )
            )

            assert isinstance(result, types.CallToolResult)
            self.assertTrue(result.isError)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Error (not_found)", result.content[0].text)

    def test_handle_delete_permission_denied(self):
        """Test _handle_delete handles permission denied with specific error message."""
        config = Config(
            trac_url="http://test", username="test", password="test"
        )
        mock_client = MagicMock()
        mock_client.config = config

        with patch(
            "trac_mcp_server.mcp.tools.ticket_write.run_sync"
        ) as mock_run_sync:
            # First call (get_ticket) succeeds, second call (delete_ticket) raises permission error
            mock_run_sync.side_effect = [
                True,  # get_ticket succeeds
                xmlrpc.client.Fault(
                    403, "Permission denied: TICKET_ADMIN required"
                ),  # delete_ticket fails
            ]

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_delete", {"ticket_id": 42}, mock_client
                )
            )

            assert isinstance(result, types.CallToolResult)
            self.assertTrue(result.isError)
            self.assertEqual(len(result.content), 1)
            self.assertIn(
                "Error (permission_denied)", result.content[0].text
            )
            self.assertIn(
                "TICKET_ADMIN permission", result.content[0].text
            )
            self.assertIn(
                "tracopt.ticket.deleter", result.content[0].text
            )


# ---------------------------------------------------------------------------
# Ticket Create handler tests
# ---------------------------------------------------------------------------


class TestHandleTicketCreate(unittest.TestCase):
    """Tests for _handle_create handler."""

    def setUp(self):
        self.mock_client = MagicMock()

    def test_create_success(self):
        """Create ticket with summary and markdown description."""
        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.markdown_to_tracwiki"
            ) as mock_convert,
        ):
            mock_run_sync.return_value = 42
            mock_convert.return_value = (
                "== Description ==\n\nWith '''markdown'''"
            )

            result = asyncio.run(
                _handle_create(
                    self.mock_client,
                    {
                        "summary": "Test ticket",
                        "description": "## Description\n\nWith **markdown**",
                    },
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Created ticket #42", result.content[0].text)
            self.assertIn("Test ticket", result.content[0].text)

            # Verify markdown_to_tracwiki was called on description
            mock_convert.assert_called_once_with(
                "## Description\n\nWith **markdown**"
            )

            # Verify run_sync called with correct args
            mock_run_sync.assert_called_once()
            call_args = mock_run_sync.call_args[0]
            self.assertEqual(
                call_args[0], self.mock_client.create_ticket
            )
            self.assertEqual(call_args[1], "Test ticket")  # summary
            self.assertEqual(
                call_args[2], "== Description ==\n\nWith '''markdown'''"
            )  # converted desc
            self.assertEqual(
                call_args[3], "defect"
            )  # default ticket_type

    def test_create_minimal(self):
        """Create ticket with summary and minimal description uses default type."""
        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.markdown_to_tracwiki"
            ) as mock_convert,
        ):
            mock_run_sync.return_value = 1
            mock_convert.return_value = "Simple description"

            result = asyncio.run(
                _handle_create(
                    self.mock_client,
                    {
                        "summary": "Minimal ticket",
                        "description": "Simple description",
                    },
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Created ticket #1", result.content[0].text)

            # Verify default ticket_type is "defect"
            call_args = mock_run_sync.call_args[0]
            self.assertEqual(call_args[3], "defect")
            # Verify empty attributes dict (no optional fields)
            self.assertEqual(call_args[4], {})

    def test_create_with_all_fields(self):
        """Create ticket with all optional fields passed through."""
        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.markdown_to_tracwiki"
            ) as mock_convert,
        ):
            mock_run_sync.return_value = 99
            mock_convert.return_value = "Converted description"

            result = asyncio.run(
                _handle_create(
                    self.mock_client,
                    {
                        "summary": "Full ticket",
                        "description": "Full description",
                        "ticket_type": "enhancement",
                        "priority": "major",
                        "component": "core",
                        "milestone": "v1.0",
                        "owner": "alice",
                        "cc": "bob@test.com",
                        "keywords": "test",
                    },
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Created ticket #99", result.content[0].text)

            # Verify ticket_type override
            call_args = mock_run_sync.call_args[0]
            self.assertEqual(call_args[3], "enhancement")

            # Verify all optional attributes passed
            attributes = call_args[4]
            self.assertEqual(attributes["priority"], "major")
            self.assertEqual(attributes["component"], "core")
            self.assertEqual(attributes["milestone"], "v1.0")
            self.assertEqual(attributes["owner"], "alice")
            self.assertEqual(attributes["cc"], "bob@test.com")
            self.assertEqual(attributes["keywords"], "test")

    def test_create_missing_summary(self):
        """Missing summary returns validation_error."""
        result = asyncio.run(
            _handle_create(
                self.mock_client,
                {
                    "description": "No summary provided",
                },
            )
        )

        self.assertIsInstance(result, types.CallToolResult)
        self.assertTrue(result.isError)
        self.assertEqual(len(result.content), 1)
        self.assertIn(
            "Error (validation_error)", result.content[0].text
        )
        self.assertIn("summary is required", result.content[0].text)

    def test_create_empty_summary(self):
        """Empty summary returns validation_error."""
        result = asyncio.run(
            _handle_create(
                self.mock_client,
                {
                    "summary": "",
                    "description": "Has description",
                },
            )
        )

        self.assertIsInstance(result, types.CallToolResult)
        self.assertTrue(result.isError)
        self.assertEqual(len(result.content), 1)
        self.assertIn(
            "Error (validation_error)", result.content[0].text
        )
        self.assertIn("summary is required", result.content[0].text)

    def test_create_missing_description(self):
        """Missing description returns validation_error."""
        result = asyncio.run(
            _handle_create(
                self.mock_client,
                {
                    "summary": "Has summary",
                },
            )
        )

        self.assertIsInstance(result, types.CallToolResult)
        self.assertTrue(result.isError)
        self.assertEqual(len(result.content), 1)
        self.assertIn(
            "Error (validation_error)", result.content[0].text
        )
        self.assertIn("description is required", result.content[0].text)

    def test_create_empty_description(self):
        """Empty description returns validation_error."""
        result = asyncio.run(
            _handle_create(
                self.mock_client,
                {
                    "summary": "Has summary",
                    "description": "",
                },
            )
        )

        self.assertIsInstance(result, types.CallToolResult)
        self.assertTrue(result.isError)
        self.assertEqual(len(result.content), 1)
        self.assertIn(
            "Error (validation_error)", result.content[0].text
        )
        self.assertIn("description is required", result.content[0].text)

    def test_create_xmlrpc_fault(self):
        """XML-RPC fault during create produces structured error via dispatcher."""
        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.markdown_to_tracwiki"
            ) as mock_convert,
        ):
            mock_convert.return_value = "Converted"
            mock_run_sync.side_effect = xmlrpc.client.Fault(
                500, "Internal server error"
            )

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_create",
                    {
                        "summary": "Test",
                        "description": "Test desc",
                    },
                    self.mock_client,
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertTrue(result.isError)
            self.assertEqual(len(result.content), 1)
            self.assertIn(
                "Error (server_error)", result.content[0].text
            )

    def test_create_permission_denied(self):
        """Permission denied fault returns permission_denied error."""
        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.markdown_to_tracwiki"
            ) as mock_convert,
        ):
            mock_convert.return_value = "Converted"
            mock_run_sync.side_effect = xmlrpc.client.Fault(
                403, "TICKET_CREATE permission denied"
            )

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_create",
                    {
                        "summary": "Test",
                        "description": "Test desc",
                    },
                    self.mock_client,
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertTrue(result.isError)
            self.assertEqual(len(result.content), 1)
            self.assertIn(
                "Error (permission_denied)", result.content[0].text
            )


# ---------------------------------------------------------------------------
# Ticket Update handler tests
# ---------------------------------------------------------------------------


class TestHandleTicketUpdate(unittest.TestCase):
    """Tests for _handle_update handler."""

    def setUp(self):
        self.mock_client = MagicMock()

    def test_update_with_comment(self):
        """Update ticket with markdown comment converts and includes it."""
        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.markdown_to_tracwiki"
            ) as mock_convert,
        ):
            mock_run_sync.return_value = True
            mock_convert.return_value = (
                "=== Update ===\n\nWith '''markdown'''"
            )

            result = asyncio.run(
                _handle_update(
                    self.mock_client,
                    {
                        "ticket_id": 42,
                        "comment": "### Update\n\nWith **markdown**",
                    },
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Updated ticket #42", result.content[0].text)
            self.assertIn("added comment", result.content[0].text)

            # Verify markdown_to_tracwiki was called on comment
            mock_convert.assert_called_once_with(
                "### Update\n\nWith **markdown**"
            )

            # Verify run_sync called with converted comment
            call_args = mock_run_sync.call_args[0]
            self.assertEqual(
                call_args[0], self.mock_client.update_ticket
            )
            self.assertEqual(call_args[1], 42)
            self.assertEqual(
                call_args[2], "=== Update ===\n\nWith '''markdown'''"
            )
            self.assertEqual(call_args[3], {})  # no attribute changes

    def test_update_fields(self):
        """Update ticket fields without comment."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = True

            result = asyncio.run(
                _handle_update(
                    self.mock_client,
                    {
                        "ticket_id": 42,
                        "priority": "major",
                        "keywords": "updated",
                    },
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Updated ticket #42", result.content[0].text)
            self.assertIn("updated 2 field(s)", result.content[0].text)

            # Verify attributes passed to client
            call_args = mock_run_sync.call_args[0]
            self.assertEqual(call_args[1], 42)
            self.assertEqual(call_args[2], "")  # empty comment
            self.assertEqual(
                call_args[3],
                {"priority": "major", "keywords": "updated"},
            )

    def test_update_comment_and_fields(self):
        """Update ticket with both comment and field changes."""
        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_write.markdown_to_tracwiki"
            ) as mock_convert,
        ):
            mock_run_sync.return_value = True
            mock_convert.return_value = "Converted comment"

            result = asyncio.run(
                _handle_update(
                    self.mock_client,
                    {
                        "ticket_id": 10,
                        "comment": "Adding a note",
                        "status": "assigned",
                        "owner": "alice",
                        "milestone": "v2.0",
                    },
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Updated ticket #10", result.content[0].text)
            self.assertIn("added comment", result.content[0].text)
            self.assertIn("updated 3 field(s)", result.content[0].text)

            # Verify both comment and attributes passed
            call_args = mock_run_sync.call_args[0]
            self.assertEqual(call_args[2], "Converted comment")
            self.assertEqual(
                call_args[3],
                {
                    "status": "assigned",
                    "owner": "alice",
                    "milestone": "v2.0",
                },
            )

    def test_update_missing_ticket_id(self):
        """Missing ticket_id returns validation_error."""
        result = asyncio.run(
            _handle_update(
                self.mock_client,
                {
                    "comment": "orphan comment",
                },
            )
        )

        self.assertIsInstance(result, types.CallToolResult)
        self.assertTrue(result.isError)
        self.assertEqual(len(result.content), 1)
        self.assertIn(
            "Error (validation_error)", result.content[0].text
        )
        self.assertIn("ticket_id is required", result.content[0].text)

    def test_update_no_changes(self):
        """Update with ticket_id only but no comment or fields returns no-changes."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = True

            result = asyncio.run(
                _handle_update(
                    self.mock_client,
                    {
                        "ticket_id": 42,
                    },
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Updated ticket #42", result.content[0].text)
            self.assertIn("no changes", result.content[0].text)

    def test_update_not_found(self):
        """Ticket not found returns not_found error via dispatcher."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write.run_sync"
        ) as mock_run_sync:
            mock_run_sync.side_effect = xmlrpc.client.Fault(
                404, "Ticket 99999 not found"
            )

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_update",
                    {
                        "ticket_id": 99999,
                    },
                    self.mock_client,
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertTrue(result.isError)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Error (not_found)", result.content[0].text)

    def test_update_permission_denied(self):
        """Permission denied fault returns permission_denied error."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write.run_sync"
        ) as mock_run_sync:
            mock_run_sync.side_effect = xmlrpc.client.Fault(
                403, "TICKET_MODIFY permission denied"
            )

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_update",
                    {
                        "ticket_id": 42,
                    },
                    self.mock_client,
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertTrue(result.isError)
            self.assertEqual(len(result.content), 1)
            self.assertIn(
                "Error (permission_denied)", result.content[0].text
            )

    def test_update_all_attribute_fields(self):
        """All supported update attributes are passed through."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = True

            result = asyncio.run(
                _handle_update(
                    self.mock_client,
                    {
                        "ticket_id": 7,
                        "status": "closed",
                        "priority": "critical",
                        "component": "auth",
                        "milestone": "v3.0",
                        "owner": "bob",
                        "resolution": "fixed",
                        "cc": "team@test.com",
                        "keywords": "release",
                    },
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertEqual(len(result.content), 1)
            self.assertIn("Updated ticket #7", result.content[0].text)
            self.assertIn("updated 8 field(s)", result.content[0].text)

            call_args = mock_run_sync.call_args[0]
            attrs = call_args[3]
            self.assertEqual(attrs["status"], "closed")
            self.assertEqual(attrs["priority"], "critical")
            self.assertEqual(attrs["component"], "auth")
            self.assertEqual(attrs["milestone"], "v3.0")
            self.assertEqual(attrs["owner"], "bob")
            self.assertEqual(attrs["resolution"], "fixed")
            self.assertEqual(attrs["cc"], "team@test.com")
            self.assertEqual(attrs["keywords"], "release")


# ---------------------------------------------------------------------------
# Ticket Write Tool Dispatcher tests
# ---------------------------------------------------------------------------


class TestHandleTicketWriteTool(unittest.TestCase):
    """Tests for handle_ticket_write_tool dispatcher."""

    def setUp(self):
        self.mock_client = MagicMock()

    def test_routes_to_create(self):
        """Dispatcher routes ticket_create to _handle_create."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write._handle_create"
        ) as mock_handler:
            mock_handler.return_value = types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text", text="Created ticket #1: Test"
                    )
                ]
            )

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_create",
                    {
                        "summary": "Test",
                        "description": "Desc",
                    },
                    self.mock_client,
                )
            )

            mock_handler.assert_awaited_once_with(
                self.mock_client,
                {
                    "summary": "Test",
                    "description": "Desc",
                },
            )
            self.assertEqual(
                result.content[0].text, "Created ticket #1: Test"
            )

    def test_routes_to_update(self):
        """Dispatcher routes ticket_update to _handle_update."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write._handle_update"
        ) as mock_handler:
            mock_handler.return_value = types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text", text="Updated ticket #42"
                    )
                ]
            )

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_update",
                    {
                        "ticket_id": 42,
                    },
                    self.mock_client,
                )
            )

            mock_handler.assert_awaited_once_with(
                self.mock_client, {"ticket_id": 42}
            )
            self.assertEqual(
                result.content[0].text, "Updated ticket #42"
            )

    def test_routes_to_delete(self):
        """Dispatcher routes ticket_delete to _handle_delete."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write._handle_delete"
        ) as mock_handler:
            mock_handler.return_value = types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text", text="Deleted ticket #42."
                    )
                ]
            )

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_delete",
                    {
                        "ticket_id": 42,
                    },
                    self.mock_client,
                )
            )

            mock_handler.assert_awaited_once_with(
                self.mock_client, {"ticket_id": 42}
            )
            self.assertEqual(
                result.content[0].text, "Deleted ticket #42."
            )

    def test_unknown_tool(self):
        """Unknown tool name returns validation_error (ValueError caught by dispatcher)."""
        result = asyncio.run(
            handle_ticket_tool("ticket_unknown", {}, self.mock_client)
        )

        self.assertIsInstance(result, types.CallToolResult)
        self.assertTrue(result.isError)
        self.assertEqual(len(result.content), 1)
        self.assertIn(
            "Error (validation_error)", result.content[0].text
        )
        self.assertIn(
            "Unknown ticket write tool", result.content[0].text
        )

    def test_none_arguments_defaults_to_empty_dict(self):
        """Passing None arguments is handled gracefully (converted to empty dict)."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write._handle_create"
        ) as mock_handler:
            mock_handler.return_value = types.CallToolResult(
                content=[types.TextContent(type="text", text="error")]
            )

            asyncio.run(
                handle_ticket_tool(
                    "ticket_create", None, self.mock_client
                )
            )

            # The dispatcher converts None to {} before passing
            mock_handler.assert_awaited_once_with(self.mock_client, {})

    def test_generic_exception_returns_server_error(self):
        """Unexpected exception returns server_error."""
        with patch(
            "trac_mcp_server.mcp.tools.ticket_write._handle_update"
        ) as mock_handler:
            mock_handler.side_effect = RuntimeError("connection reset")

            result = asyncio.run(
                handle_ticket_tool(
                    "ticket_update",
                    {
                        "ticket_id": 1,
                    },
                    self.mock_client,
                )
            )

            self.assertIsInstance(result, types.CallToolResult)
            self.assertTrue(result.isError)
            self.assertEqual(len(result.content), 1)
            self.assertIn(
                "Error (server_error)", result.content[0].text
            )
            self.assertIn("connection reset", result.content[0].text)


# ---------------------------------------------------------------------------
# Ticket Read handler tests
# ---------------------------------------------------------------------------


class TestHandleTicketSearch:
    """Tests for _handle_search handler."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_search_default_query(self):
        """Search with no args uses default query and returns ticket summaries."""
        client = MagicMock(spec=TracClient)

        mock_data = [
            {
                "id": 1,
                "summary": "Bug A",
                "status": "new",
                "owner": "alice",
            },
            {
                "id": 2,
                "summary": "Bug B",
                "status": "assigned",
                "owner": "bob",
            },
            {
                "id": 3,
                "summary": "Bug C",
                "status": "new",
                "owner": "charlie",
            },
        ]

        def _close_coros_and_return(coros):
            for coro in coros:
                coro.close()
            return mock_data

        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.gather_limited",
                side_effect=_close_coros_and_return,
            ) as _mock_gather,
        ):
            mock_run_sync.return_value = [1, 2, 3]

            result = self._run(_handle_search(client, {}))

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "Found 3 tickets" in text
            assert "#1" in text
            assert "#2" in text
            assert "#3" in text
            # Default query
            mock_run_sync.assert_called_once()
            call_args = mock_run_sync.call_args[0]
            assert call_args[0] == client.search_tickets
            assert call_args[1] == "status!=closed"

    def test_search_custom_query_with_max_results(self):
        """Custom query and max_results are forwarded correctly."""
        client = MagicMock(spec=TracClient)

        mock_data = [
            {
                "id": 10,
                "summary": "T10",
                "status": "closed",
                "owner": "x",
            },
            {
                "id": 20,
                "summary": "T20",
                "status": "closed",
                "owner": "x",
            },
            {
                "id": 30,
                "summary": "T30",
                "status": "closed",
                "owner": "x",
            },
            {
                "id": 40,
                "summary": "T40",
                "status": "closed",
                "owner": "x",
            },
            {
                "id": 50,
                "summary": "T50",
                "status": "closed",
                "owner": "x",
            },
        ]

        def _close_coros_and_return(coros):
            for coro in coros:
                coro.close()
            return mock_data

        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.gather_limited",
                side_effect=_close_coros_and_return,
            ) as _mock_gather,
        ):
            mock_run_sync.return_value = [10, 20, 30, 40, 50, 60]

            result = self._run(
                _handle_search(
                    client, {"query": "status=closed", "max_results": 5}
                )
            )

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "Found 6 tickets" in text
            assert "showing 5" in text
            # Verify query passed correctly
            call_args = mock_run_sync.call_args[0]
            assert call_args[1] == "status=closed"
            # Verify structured content
            assert result.structuredContent["total"] == 6
            assert result.structuredContent["showing"] == 5

    def test_search_empty_results(self):
        """Empty search returns no-tickets message."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = []

            result = self._run(_handle_search(client, {}))

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "No tickets found" in text
            assert result.structuredContent["tickets"] == []
            assert result.structuredContent["total"] == 0

    def test_search_with_ticket_details(self):
        """Search fetches details for each ticket via gather_limited."""
        client = MagicMock(spec=TracClient)

        mock_data = [
            {
                "id": 7,
                "summary": "Feature request",
                "status": "new",
                "owner": "dev1",
            },
            {
                "id": 8,
                "summary": "Enhancement",
                "status": "accepted",
                "owner": "dev2",
            },
        ]

        def _close_coros_and_return(coros):
            for coro in coros:
                coro.close()
            return mock_data

        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.gather_limited",
                side_effect=_close_coros_and_return,
            ) as mock_gather,
        ):
            mock_run_sync.return_value = [7, 8]

            result = self._run(_handle_search(client, {}))

            text = result.content[0].text
            assert "Feature request" in text
            assert "Enhancement" in text
            assert "status: new" in text
            assert "owner: dev1" in text
            # Verify gather_limited was called
            mock_gather.assert_called_once()

    def test_search_xmlrpc_fault(self):
        """XML-RPC fault during search produces structured error."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.side_effect = xmlrpc.client.Fault(
                500, "Internal server error"
            )

            # Call through dispatcher so the fault is caught and translated
            result = self._run(
                handle_ticket_read_tool("ticket_search", {}, client)
            )

            assert isinstance(result, types.CallToolResult)
            assert result.isError is True
            assert "Error" in result.content[0].text
            assert "server_error" in result.content[0].text


class TestHandleTicketGet:
    """Tests for _handle_get handler."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_get_success(self):
        """Get ticket returns full details with Markdown-converted description."""
        client = MagicMock(spec=TracClient)
        created = datetime(2026, 1, 10, 9, 0, 0)
        modified = datetime(2026, 1, 15, 14, 30, 0)

        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.tracwiki_to_markdown"
            ) as mock_convert,
        ):
            mock_run_sync.return_value = [
                42,
                created,
                modified,
                {
                    "summary": "Fix login bug",
                    "description": "= Problem =\nLogin fails",
                    "status": "new",
                    "owner": "alice",
                    "type": "defect",
                    "priority": "high",
                    "component": "auth",
                    "milestone": "v2.0",
                },
            ]
            mock_convert.return_value = ConversionResult(
                text="# Problem\nLogin fails",
                source_format="tracwiki",
                target_format="markdown",
                converted=True,
            )

            result = self._run(_handle_get(client, {"ticket_id": 42}))

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "Ticket #42" in text
            assert "Fix login bug" in text
            assert "# Problem" in text  # converted description
            assert "new" in text
            assert "alice" in text
            # Structured content
            assert result.structuredContent["id"] == 42
            assert (
                result.structuredContent["summary"] == "Fix login bug"
            )

    def test_get_raw_mode(self):
        """Raw mode returns TracWiki description without conversion."""
        client = MagicMock(spec=TracClient)
        created = datetime(2026, 1, 10, 9, 0, 0)
        modified = datetime(2026, 1, 15, 14, 30, 0)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = [
                1,
                created,
                modified,
                {
                    "summary": "Raw test",
                    "description": "= TracWiki heading =",
                    "status": "new",
                    "owner": "bob",
                    "type": "task",
                    "priority": "normal",
                    "component": "core",
                    "milestone": "",
                },
            ]

            result = self._run(
                _handle_get(client, {"ticket_id": 1, "raw": True})
            )

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "(TracWiki)" in text
            assert "= TracWiki heading =" in text

    def test_get_missing_ticket_id(self):
        """Missing ticket_id returns validation error."""
        client = MagicMock(spec=TracClient)

        result = self._run(_handle_get(client, {}))

        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "Error (validation_error)" in result.content[0].text
        assert "ticket_id is required" in result.content[0].text

    def test_get_not_found(self):
        """Ticket not found returns structured error via dispatcher."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.side_effect = xmlrpc.client.Fault(
                404, "Ticket 99999 not found"
            )

            result = self._run(
                handle_ticket_read_tool(
                    "ticket_get", {"ticket_id": 99999}, client
                )
            )

            assert isinstance(result, types.CallToolResult)
            assert result.isError is True
            assert "Error (not_found)" in result.content[0].text


class TestHandleTicketChangelog:
    """Tests for _handle_changelog handler."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_changelog_success(self):
        """Changelog returns formatted change entries."""
        client = MagicMock(spec=TracClient)
        ts = datetime(2026, 1, 20, 10, 0, 0)

        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.tracwiki_to_markdown"
            ) as mock_convert,
        ):
            mock_run_sync.return_value = [
                [ts, "alice", "status", "new", "assigned", 1],
                [ts, "bob", "comment", "", "Fixed the bug", 1],
            ]
            mock_convert.return_value = ConversionResult(
                text="Fixed the bug",
                source_format="tracwiki",
                target_format="markdown",
                converted=True,
            )

            result = self._run(
                _handle_changelog(client, {"ticket_id": 5})
            )

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "Changelog for ticket #5" in text
            assert "alice" in text
            assert "status" in text
            assert "new" in text
            assert "assigned" in text
            assert "bob" in text
            assert "comment" in text
            assert "Fixed the bug" in text

    def test_changelog_raw_mode(self):
        """Raw mode skips Markdown conversion for comment content."""
        client = MagicMock(spec=TracClient)
        ts = datetime(2026, 1, 20, 10, 0, 0)

        with (
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.run_sync"
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.tools.ticket_read.tracwiki_to_markdown"
            ) as mock_convert,
        ):
            mock_run_sync.return_value = [
                [ts, "alice", "comment", "", "= Wiki heading =", 1],
            ]

            result = self._run(
                _handle_changelog(client, {"ticket_id": 5, "raw": True})
            )

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "(TracWiki format)" in text
            assert "= Wiki heading =" in text
            # tracwiki_to_markdown should NOT have been called
            mock_convert.assert_not_called()

    def test_changelog_empty(self):
        """Empty changelog returns appropriate message."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = []

            result = self._run(
                _handle_changelog(client, {"ticket_id": 99})
            )

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "No changelog" in text
            assert "#99" in text

    def test_changelog_missing_ticket_id(self):
        """Missing ticket_id returns validation error."""
        client = MagicMock(spec=TracClient)

        result = self._run(_handle_changelog(client, {}))

        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "Error (validation_error)" in result.content[0].text
        assert "ticket_id is required" in result.content[0].text


class TestHandleTicketFields:
    """Tests for _handle_fields handler."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_fields_success(self):
        """Fields returns structured field definitions."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = [
                {
                    "name": "summary",
                    "type": "text",
                    "label": "Summary",
                    "custom": False,
                },
                {
                    "name": "status",
                    "type": "select",
                    "label": "Status",
                    "options": ["new", "assigned", "closed"],
                    "custom": False,
                },
            ]

            result = self._run(_handle_fields(client, {}))

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "Ticket Fields (2 total)" in text
            assert "summary" in text
            assert "Standard Fields" in text
            # Structured content
            fields = result.structuredContent["fields"]
            assert len(fields) == 2
            assert fields[0]["name"] == "summary"

    def test_fields_includes_custom(self):
        """Custom fields appear in Custom Fields section."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = [
                {
                    "name": "summary",
                    "type": "text",
                    "label": "Summary",
                    "custom": False,
                },
                {
                    "name": "department",
                    "type": "select",
                    "label": "Department",
                    "options": ["eng", "sales"],
                    "custom": True,
                },
            ]

            result = self._run(_handle_fields(client, {}))

            text = result.content[0].text
            assert "Custom Fields" in text
            assert "department" in text
            assert "eng, sales" in text
            # Structured content
            fields = result.structuredContent["fields"]
            custom = [f for f in fields if f["custom"]]
            assert len(custom) == 1
            assert custom[0]["name"] == "department"


class TestHandleTicketActions:
    """Tests for _handle_actions handler."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_actions_success(self):
        """Actions returns formatted list of workflow actions."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = [
                ["leave", "leave as new", {}, []],
                ["accept", "accept ticket", {}, []],
                [
                    "resolve",
                    "resolve ticket",
                    {},
                    ["action_resolve_resolve_resolution"],
                ],
            ]

            result = self._run(
                _handle_actions(client, {"ticket_id": 10})
            )

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "Available actions for ticket #10" in text
            assert "leave" in text
            assert "accept" in text
            assert "resolve" in text
            # Structured content
            actions = result.structuredContent["actions"]
            assert len(actions) == 3
            assert actions[0]["name"] == "leave"

    def test_actions_missing_ticket_id(self):
        """Missing ticket_id raises ValueError caught by dispatcher."""
        client = MagicMock(spec=TracClient)

        # _handle_actions raises ValueError when ticket_id missing,
        # dispatcher catches it and returns validation_error
        result = self._run(
            handle_ticket_read_tool("ticket_actions", {}, client)
        )

        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "Error (validation_error)" in result.content[0].text
        assert "ticket_id is required" in result.content[0].text

    def test_actions_empty(self):
        """Empty actions list returns appropriate message."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = []

            result = self._run(
                _handle_actions(client, {"ticket_id": 5})
            )

            assert isinstance(result, types.CallToolResult)
            text = result.content[0].text
            assert "No available actions" in text
            assert result.structuredContent["actions"] == []

    def test_actions_method_not_available(self):
        """getActions not available returns helpful error."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.side_effect = xmlrpc.client.Fault(
                1, "No such method 'ticket.getActions'"
            )

            result = self._run(
                _handle_actions(client, {"ticket_id": 5})
            )

            assert isinstance(result, types.CallToolResult)
            assert result.isError is True
            assert "method_not_available" in result.content[0].text

    def test_actions_with_hints_and_input_fields(self):
        """Actions with list hints and input fields are formatted correctly."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            mock_run_sync.return_value = [
                [
                    "resolve",
                    "resolve ticket",
                    ["set to closed"],
                    ["resolution"],
                ],
            ]

            result = self._run(
                _handle_actions(client, {"ticket_id": 10})
            )

            text = result.content[0].text
            assert "resolve" in text
            assert "set to closed" in text
            assert "requires: resolution" in text


class TestHandleTicketReadTool:
    """Tests for handle_ticket_read_tool dispatcher."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_routes_to_search(self):
        """Dispatcher routes ticket_search to _handle_search."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read._handle_search"
        ) as mock_handler:
            mock_handler.return_value = types.CallToolResult(
                content=[
                    types.TextContent(type="text", text="search result")
                ],
            )

            result = self._run(
                handle_ticket_read_tool(
                    "ticket_search", {"query": "status=new"}, client
                )
            )

            mock_handler.assert_awaited_once_with(
                client, {"query": "status=new"}
            )
            assert result.content[0].text == "search result"

    def test_routes_to_get(self):
        """Dispatcher routes ticket_get to _handle_get."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read._handle_get"
        ) as mock_handler:
            mock_handler.return_value = types.CallToolResult(
                content=[
                    types.TextContent(type="text", text="get result")
                ],
            )

            self._run(
                handle_ticket_read_tool(
                    "ticket_get", {"ticket_id": 1}, client
                )
            )

            mock_handler.assert_awaited_once_with(
                client, {"ticket_id": 1}
            )

    def test_routes_to_changelog(self):
        """Dispatcher routes ticket_changelog to _handle_changelog."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read._handle_changelog"
        ) as mock_handler:
            mock_handler.return_value = types.CallToolResult(
                content=[
                    types.TextContent(type="text", text="changelog")
                ]
            )

            self._run(
                handle_ticket_read_tool(
                    "ticket_changelog", {"ticket_id": 1}, client
                )
            )

            mock_handler.assert_awaited_once_with(
                client, {"ticket_id": 1}
            )

    def test_routes_to_fields(self):
        """Dispatcher routes ticket_fields to _handle_fields."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read._handle_fields"
        ) as mock_handler:
            mock_handler.return_value = types.CallToolResult(
                content=[types.TextContent(type="text", text="fields")],
            )

            self._run(
                handle_ticket_read_tool("ticket_fields", {}, client)
            )

            mock_handler.assert_awaited_once_with(client, {})

    def test_routes_to_actions(self):
        """Dispatcher routes ticket_actions to _handle_actions."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read._handle_actions"
        ) as mock_handler:
            mock_handler.return_value = types.CallToolResult(
                content=[
                    types.TextContent(type="text", text="actions")
                ],
            )

            self._run(
                handle_ticket_read_tool(
                    "ticket_actions", {"ticket_id": 1}, client
                )
            )

            mock_handler.assert_awaited_once_with(
                client, {"ticket_id": 1}
            )

    def test_unknown_tool_raises(self):
        """Unknown tool name raises ValueError caught as validation_error."""
        client = MagicMock(spec=TracClient)

        result = self._run(
            handle_ticket_read_tool("ticket_unknown", {}, client)
        )

        # ValueError is caught by dispatcher and translated to validation_error
        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "Error (validation_error)" in result.content[0].text
        assert "Unknown ticket read tool" in result.content[0].text

    def test_xmlrpc_fault_translated(self):
        """XML-RPC fault from handler is translated to structured error."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read._handle_get"
        ) as mock_handler:
            mock_handler.side_effect = xmlrpc.client.Fault(
                403, "Permission denied"
            )

            result = self._run(
                handle_ticket_read_tool(
                    "ticket_get", {"ticket_id": 1}, client
                )
            )

            assert isinstance(result, types.CallToolResult)
            assert result.isError is True
            assert "Error (permission_denied)" in result.content[0].text

    def test_generic_exception_translated(self):
        """Unexpected exception is caught and returned as server_error."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read._handle_search"
        ) as mock_handler:
            mock_handler.side_effect = RuntimeError("connection reset")

            result = self._run(
                handle_ticket_read_tool("ticket_search", {}, client)
            )

            assert isinstance(result, types.CallToolResult)
            assert result.isError is True
            assert "Error (server_error)" in result.content[0].text
            assert "connection reset" in result.content[0].text

    def test_get_invalid_ticket_data_format(self):
        """Invalid ticket data format from server returns error."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read.run_sync"
        ) as mock_run_sync:
            # Return invalid format (not a list with 4 elements)
            mock_run_sync.return_value = "unexpected"

            result = self._run(_handle_get(client, {"ticket_id": 1}))

            assert isinstance(result, types.CallToolResult)
            assert result.isError is True
            assert "Error (server_error)" in result.content[0].text
            assert (
                "Invalid ticket data format" in result.content[0].text
            )

    def test_xmlrpc_version_conflict_translated(self):
        """Version conflict fault is translated to version_conflict error."""
        client = MagicMock(spec=TracClient)

        with patch(
            "trac_mcp_server.mcp.tools.ticket_read._handle_get"
        ) as mock_handler:
            mock_handler.side_effect = xmlrpc.client.Fault(
                409, "Version conflict - not modified"
            )

            result = self._run(
                handle_ticket_read_tool(
                    "ticket_get", {"ticket_id": 1}, client
                )
            )

            assert isinstance(result, types.CallToolResult)
            assert result.isError is True
            assert "Error (version_conflict)" in result.content[0].text
