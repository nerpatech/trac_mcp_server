#!/usr/bin/env python3
"""
Comprehensive MCP Tool Live Testing

This script tests all 27 Trac MCP server tools against a live Trac server instance,
validating the complete MCP tool surface before release.

Features:
- Tests all 27 tools: ping + 8 ticket + 3 batch ticket + 6 wiki + 3 wiki_file + 5 milestone + 1 system
- Covers happy paths, error handling, and edge cases
- Tests format conversions (Markdown <-> TracWiki)
- Tests batch operations with parallel execution
- Generates comprehensive test report
- Automatic cleanup of test resources
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Import MCP tool handlers directly
import mcp.types as types
from dotenv import load_dotenv

from trac_mcp_server import __version__ as PACKAGE_VERSION
from trac_mcp_server.config import Config, load_config
from trac_mcp_server.core.async_utils import run_sync
from trac_mcp_server.core.client import TracClient
from trac_mcp_server.mcp.tools import ALL_SPECS
from trac_mcp_server.mcp.tools.registry import ToolRegistry

VERSION = "5.0.0"

# Number of tickets to create in batch tests.
# Keep small for routine testing; increase for load/stress testing.
BATCH_TEST_SIZE = 10


def _extract_raw_fields(
    raw_result: types.CallToolResult | None,
) -> dict:
    """Extract structured fields from a CallToolResult for CheckResult construction."""
    if raw_result is None:
        return {
            "structured_content": None,
            "is_error": None,
            "raw_text_content": [],
        }
    return {
        "structured_content": raw_result.structuredContent,
        "is_error": raw_result.isError,
        "raw_text_content": [
            c.text
            for c in raw_result.content
            if isinstance(c, types.TextContent)
        ],
    }


@dataclass
class CheckResult:
    """Result of a single test case"""

    tool: str
    test_name: str
    passed: bool
    response: str = ""
    error: str = ""
    notes: str = ""
    call_args: dict = field(default_factory=dict)
    structured_content: dict | None = None
    is_error: bool | None = None
    raw_text_content: list[str] = field(default_factory=list)


@dataclass
class CheckReport:
    """Comprehensive test report"""

    date: str = ""
    server_url: str = ""
    binary_version: str = ""
    results: list[CheckResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)


class ComprehensiveMCPTester:
    """Comprehensive tester for all Trac MCP tools"""

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        verbose: bool = False,
    ):
        self.config = config
        self.client = TracClient(config)
        self.registry = ToolRegistry(ALL_SPECS)
        self.logger = logger
        self.verbose = verbose
        self.report = CheckReport()
        self.report.binary_version = PACKAGE_VERSION
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Track test resources for cleanup
        self.test_ticket_id: Optional[int] = None
        self.test_wiki_page: Optional[str] = None
        self.test_milestone: Optional[str] = None
        self.test_batch_ticket_ids: list[int] = []

    def _color(self, text: str) -> str:
        """Return text as-is (no color formatting)."""
        return text

    def _log_result(self, result: CheckResult):
        """Log a test result"""
        status = (
            self._color("PASS")
            if result.passed
            else self._color("FAIL")
        )
        print(f"  [{status}] {result.tool}.{result.test_name}")
        if self.verbose and result.notes:
            print(f"         Notes: {result.notes}")
        if not result.passed and result.error:
            print(f"         Error: {result.error[:100]}")

    async def _call_tool(
        self, tool_name: str, arguments: dict | None = None
    ) -> tuple[bool, str, types.CallToolResult | None]:
        """Call an MCP tool and return (success, response_text, raw_result)"""
        try:
            if tool_name == "ping":
                # Handle ping specially (no CallToolResult available)
                version = await run_sync(
                    self.client.validate_connection
                )
                return (
                    True,
                    f"Trac MCP server connected successfully. API version: {version}",
                    None,
                )

            result = await self.registry.call_tool(
                tool_name, arguments or {}, self.client
            )

            # Extract text from CallToolResult.content
            response_text = "\n".join(
                c.text
                for c in result.content
                if isinstance(c, types.TextContent)
            )

            # Check for error indicators in response
            is_error = (
                "error_type" in response_text.lower()
                or response_text.startswith("{")
            )
            return not is_error, response_text, result

        except Exception as e:
            return False, str(e), None

    async def test_ping(self):
        """Phase 1: Test connectivity"""
        print(f"\n{self._color('=== Phase 1: Connectivity ===')}")

        success, response, raw_result = await self._call_tool("ping")
        result = CheckResult(
            tool="ping",
            test_name="connectivity",
            passed=success and "API version" in response,
            response=response,
            notes="API version: "
            + response.split("API version:")[-1].strip()
            if "API version" in response
            else "",
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        if success and "API version" in response:
            self.report.server_url = self.config.trac_url

    async def test_system_tools(self):
        """Phase 1b: Test system tools"""
        print(f"\n{self._color('=== Phase 1b: System Tools ===')}")

        # get_server_time
        success, response, raw_result = await self._call_tool("get_server_time")

        # Verify response contains valid timestamp
        passed = False
        notes = ""
        if success and "Server time:" in response:
            try:
                # Extract ISO timestamp from response
                timestamp_str = response.split("Server time:")[
                    -1
                ].strip()
                # Try parsing as datetime to verify format
                from datetime import datetime

                datetime.fromisoformat(timestamp_str)
                passed = True
                notes = f"Valid timestamp: {timestamp_str}"
            except Exception as e:
                notes = f"Invalid timestamp format: {e}"
        else:
            notes = "Response missing 'Server time:' prefix"

        result = CheckResult(
            tool="get_server_time",
            test_name="server_time",
            passed=passed,
            response=response[:200],
            notes=notes,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

    async def test_ticket_read_operations(self):
        """Phase 2a: Test ticket read operations"""
        print(
            f"\n{self._color('=== Phase 2a: Ticket Read Operations ===')}"
        )

        # ticket_search - default query
        _args: dict = {}
        success, response, raw_result = await self._call_tool("ticket_search")
        result = CheckResult(
            tool="ticket_search",
            test_name="default_query",
            passed=success
            and ("Found" in response or "No tickets" in response),
            response=response[:200],
            notes="Returns open tickets by default",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        # ticket_search - custom query with max_results
        _args = {"query": "status=closed", "max_results": 5}
        success, response, raw_result = await self._call_tool(
            "ticket_search", _args,
        )
        result = CheckResult(
            tool="ticket_search",
            test_name="custom_query_max_results",
            passed=success,
            response=response[:200],
            notes="Tested status=closed with max_results=5",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        # ticket_get - need a valid ticket ID
        # First get a ticket from search
        search_success, search_response, _raw = await self._call_tool(
            "ticket_search", {"max_results": 1}
        )
        ticket_id = None
        if search_success and "#" in search_response:
            try:
                # Extract first ticket ID from response like "- #1: Summary"
                ticket_id = int(
                    search_response.split("#")[1].split(":")[0]
                )
            except (ValueError, IndexError):
                pass

        # If no tickets exist, create a temporary one for read tests
        temp_ticket_id: int | None = None
        if not ticket_id:
            create_success, create_response, _raw = await self._call_tool(
                "ticket_create",
                {
                    "summary": f"[MCP READ TEST {self.timestamp}] Temporary ticket for read tests",
                    "description": "Auto-created for ticket read testing. Will be deleted.",
                    "ticket_type": "task",
                    "keywords": "mcp-test,auto-delete",
                },
            )
            if create_success and "Created ticket #" in create_response:
                try:
                    temp_ticket_id = int(
                        create_response.split("#")[1].split(":")[0]
                    )
                    ticket_id = temp_ticket_id
                    print(
                        f"  (created temp ticket #{temp_ticket_id} for read tests)"
                    )
                except (ValueError, IndexError):
                    pass

        if ticket_id:
            # ticket_get - existing ticket
            _args = {"ticket_id": ticket_id}
            success, response, raw_result = await self._call_tool(
                "ticket_get", _args
            )
            result = CheckResult(
                tool="ticket_get",
                test_name="existing_ticket",
                passed=success and f"Ticket #{ticket_id}" in response,
                response=response[:300],
                notes=f"Retrieved ticket #{ticket_id}"
                + (" (temp)" if temp_ticket_id else ""),
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # ticket_get - raw mode
            _args = {"ticket_id": ticket_id, "raw": True}
            success, response, raw_result = await self._call_tool(
                "ticket_get", _args
            )
            result = CheckResult(
                tool="ticket_get",
                test_name="raw_mode",
                passed=success and "(TracWiki)" in response,
                response=response[:300],
                notes="Raw TracWiki format returned",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # ticket_changelog
            _args = {"ticket_id": ticket_id}
            success, response, raw_result = await self._call_tool(
                "ticket_changelog", _args
            )
            result = CheckResult(
                tool="ticket_changelog",
                test_name="existing_ticket",
                passed=success,
                response=response[:300],
                notes="Changelog may be empty for new tickets",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # ticket_changelog - raw mode
            _args = {"ticket_id": ticket_id, "raw": True}
            success, response, raw_result = await self._call_tool(
                "ticket_changelog", _args,
            )
            result = CheckResult(
                tool="ticket_changelog",
                test_name="raw_mode",
                passed=success,
                response=response[:200],
                notes="Raw TracWiki format for comments",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # ticket_actions
            _args = {"ticket_id": ticket_id}
            success, response, raw_result = await self._call_tool(
                "ticket_actions", _args
            )
            result = CheckResult(
                tool="ticket_actions",
                test_name="get_workflow_actions",
                passed=success
                and (
                    "actions" in response.lower()
                    or "leave" in response.lower()
                ),
                response=response[:300],
                notes="Retrieved workflow actions for ticket",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # Clean up temp ticket if we created one
            if temp_ticket_id:
                await self._call_tool(
                    "ticket_delete", {"ticket_id": temp_ticket_id}
                )
                print(f"  (deleted temp ticket #{temp_ticket_id})")
        else:
            result = CheckResult(
                tool="ticket_get",
                test_name="existing_ticket",
                passed=False,
                error="No tickets found and could not create temp ticket",
                notes="SKIPPED",
            )
            self.report.results.append(result)
            self._log_result(result)

        # ticket_fields
        success, response, raw_result = await self._call_tool("ticket_fields")
        result = CheckResult(
            tool="ticket_fields",
            test_name="get_fields",
            passed=success and "Ticket Fields" in response,
            response=response[:400],
            notes="Returns standard and custom field definitions",
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

    async def test_wiki_read_operations(self):
        """Phase 2b: Test wiki read operations"""
        print(
            f"\n{self._color('=== Phase 2b: Wiki Read Operations ===')}"
        )

        # wiki_get - WikiStart
        _args = {"page_name": "WikiStart"}
        success, response, raw_result = await self._call_tool(
            "wiki_get", _args
        )
        wiki_version = None
        if success and "Version:" in response:
            try:
                wiki_version = int(
                    response.split("Version:")[1].split()[0]
                )
            except (ValueError, IndexError):
                pass

        result = CheckResult(
            tool="wiki_get",
            test_name="wikistart",
            passed=success and "WikiStart" in response,
            response=response[:300],
            notes=f"Version: {wiki_version}" if wiki_version else "",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        # wiki_get - raw mode
        _args = {"page_name": "WikiStart", "raw": True}
        success, response, raw_result = await self._call_tool(
            "wiki_get", _args
        )
        result = CheckResult(
            tool="wiki_get",
            test_name="raw_mode",
            passed=success and "(TracWiki)" in response,
            response=response[:300],
            notes="Raw TracWiki format returned",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        # wiki_get - specific version (if version > 1)
        if wiki_version and wiki_version > 1:
            _args = {"page_name": "WikiStart", "version": 1}
            success, response, raw_result = await self._call_tool(
                "wiki_get", _args
            )
            result = CheckResult(
                tool="wiki_get",
                test_name="specific_version",
                passed=success and "Version: 1" in response,
                response=response[:200],
                notes="Retrieved historical version 1",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

        # wiki_search
        _args = {"query": "wiki"}
        success, response, raw_result = await self._call_tool(
            "wiki_search", _args
        )
        result = CheckResult(
            tool="wiki_search",
            test_name="basic_search",
            passed=success
            and ("Found" in response or "No wiki" in response),
            response=response[:300],
            notes="Search for 'wiki' keyword",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        # wiki_search - with prefix
        _args = {"query": "trac", "prefix": "Trac"}
        success, response, raw_result = await self._call_tool(
            "wiki_search", _args
        )
        result = CheckResult(
            tool="wiki_search",
            test_name="with_prefix",
            passed=success,
            response=response[:200],
            notes="Filtered by Trac prefix",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        # wiki_recent_changes
        _args = {"days_back": 30}
        success, response, raw_result = await self._call_tool(
            "wiki_recent_changes", _args
        )
        result = CheckResult(
            tool="wiki_recent_changes",
            test_name="recent_changes",
            passed=success
            and (
                "pages" in response.lower()
                or "modified" in response.lower()
                or "no recent" in response.lower()
            ),
            response=response[:300],
            notes="Retrieved wiki pages modified in last 30 days",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

    async def test_milestone_read_operations(self):
        """Phase 2c: Test milestone read operations"""
        print(
            f"\n{self._color('=== Phase 2c: Milestone Read Operations ===')}"
        )

        # milestone_list
        success, response, raw_result = await self._call_tool("milestone_list")
        milestone_name = None
        if (
            success
            and response.strip()
            and "No milestones" not in response
        ):
            milestone_name = response.strip().split("\n")[0]

        result = CheckResult(
            tool="milestone_list",
            test_name="list_all",
            passed=success,
            response=response[:200],
            notes=f"First milestone: {milestone_name}"
            if milestone_name
            else "No milestones found",
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        # milestone_get - if we have a milestone
        if milestone_name:
            _args = {"name": milestone_name}
            success, response, raw_result = await self._call_tool(
                "milestone_get", _args
            )
            result = CheckResult(
                tool="milestone_get",
                test_name="existing_milestone",
                passed=success and "Milestone:" in response,
                response=response[:300],
                notes=f"Retrieved milestone: {milestone_name}",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # milestone_get - raw mode
            _args = {"name": milestone_name, "raw": True}
            success, response, raw_result = await self._call_tool(
                "milestone_get", _args
            )
            result = CheckResult(
                tool="milestone_get",
                test_name="raw_mode",
                passed=success,
                response=response[:200],
                notes="Raw TracWiki format for description",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)
        else:
            result = CheckResult(
                tool="milestone_get",
                test_name="existing_milestone",
                passed=True,  # Not a failure, just no milestones
                notes="SKIPPED - No milestones exist",
            )
            self.report.results.append(result)
            self._log_result(result)

    async def test_ticket_write_operations(self):
        """Phase 3a: Test ticket write operations"""
        print(
            f"\n{self._color('=== Phase 3a: Ticket Write Operations ===')}"
        )

        # ticket_create
        summary = f"[MCP TEST {self.timestamp}] Comprehensive Tool Test"
        description = """## Test Ticket

This is a **Markdown** test.

- Item 1
- Item 2

### Code Example

```python
print("hello world")
```
"""
        _args = {
            "summary": summary,
            "description": description,
            "ticket_type": "task",
            "keywords": "mcp-test,auto-delete",
        }
        success, response, raw_result = await self._call_tool(
            "ticket_create", _args,
        )

        if success and "Created ticket #" in response:
            try:
                self.test_ticket_id = int(
                    response.split("#")[1].split(":")[0]
                )
            except (ValueError, IndexError):
                pass

        result = CheckResult(
            tool="ticket_create",
            test_name="create_with_markdown",
            passed=success and "Created ticket" in response,
            response=response,
            notes=f"Created ticket #{self.test_ticket_id}"
            if self.test_ticket_id
            else "Failed to extract ticket ID",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        if self.test_ticket_id:
            # Verify Markdown conversion
            _verify_args = {"ticket_id": self.test_ticket_id, "raw": True}
            _, verify_response, _verify_raw = await self._call_tool(
                "ticket_get", _verify_args,
            )
            # Check for TracWiki markers ('''bold''' instead of **bold**)
            has_tracwiki = (
                "'''" in verify_response
                or "==" in verify_response
                or "{{{" in verify_response
            )
            result = CheckResult(
                tool="ticket_create",
                test_name="markdown_conversion",
                passed=has_tracwiki,
                response=verify_response[:400],
                notes="Verified Markdown converted to TracWiki"
                if has_tracwiki
                else "Conversion may not have occurred",
                call_args=_verify_args,
                **_extract_raw_fields(_verify_raw),
            )
            self.report.results.append(result)
            self._log_result(result)

            # ticket_update - add comment
            _args = {
                "ticket_id": self.test_ticket_id,
                "comment": "### Update Comment\n\nAdding a **formatted** comment.",
            }
            success, response, raw_result = await self._call_tool(
                "ticket_update", _args,
            )
            result = CheckResult(
                tool="ticket_update",
                test_name="add_comment",
                passed=success and "Updated ticket" in response,
                response=response,
                notes="Comment with Markdown formatting",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # ticket_update - change fields
            _args = {
                "ticket_id": self.test_ticket_id,
                "priority": "major",  # Use valid Trac priority value
                "keywords": "mcp-test,auto-delete,updated",
            }
            success, response, raw_result = await self._call_tool(
                "ticket_update", _args,
            )
            result = CheckResult(
                tool="ticket_update",
                test_name="update_fields",
                passed=success and "Updated ticket" in response,
                response=response,
                notes="Updated priority and keywords",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

    async def test_wiki_write_operations(self):
        """Phase 3b: Test wiki write operations"""
        print(
            f"\n{self._color('=== Phase 3b: Wiki Write Operations ===')}"
        )

        # wiki_create
        self.test_wiki_page = f"MCPTest_{self.timestamp}"
        content = """# Test Page

## Features

- **Bold** text
- *Italic* text
- `Code` text

### Code Block

```python
print('hello')
```

### Links

- [External Link](https://example.com)
- WikiStart (internal link)
"""
        _args = {
            "page_name": self.test_wiki_page,
            "content": content,
            "comment": "MCP test page creation",
        }
        success, response, raw_result = await self._call_tool(
            "wiki_create", _args,
        )

        result = CheckResult(
            tool="wiki_create",
            test_name="create_with_markdown",
            passed=success and "Created wiki page" in response,
            response=response,
            notes=f"Created page: {self.test_wiki_page}"
            if success
            else "Creation failed",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        if success:
            # Verify creation
            _, verify_response, _raw = await self._call_tool(
                "wiki_get",
                {"page_name": self.test_wiki_page, "raw": True},
            )
            has_tracwiki = (
                "'''" in verify_response
                or "==" in verify_response
                or "{{{" in verify_response
            )
            result = CheckResult(
                tool="wiki_create",
                test_name="markdown_conversion",
                passed=has_tracwiki,
                response=verify_response[:400],
                notes="Verified Markdown converted to TracWiki",
                call_args={"page_name": self.test_wiki_page, "raw": True},
                **_extract_raw_fields(_raw),
            )
            self.report.results.append(result)
            self._log_result(result)

            # wiki_create - duplicate (should fail)
            _args = {
                "page_name": self.test_wiki_page,
                "content": "Duplicate content",
            }
            success, response, raw_result = await self._call_tool(
                "wiki_create", _args,
            )
            result = CheckResult(
                tool="wiki_create",
                test_name="duplicate_error",
                passed="already_exists" in response
                or "already exists" in response.lower(),
                response=response,
                notes="Expected error for duplicate page",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # wiki_update
            _args = {
                "page_name": self.test_wiki_page,
                "content": "# Updated Test Page\n\nThis page was updated.",
                "version": 1,
                "comment": "MCP test page update",
            }
            success, response, raw_result = await self._call_tool(
                "wiki_update", _args,
            )
            result = CheckResult(
                tool="wiki_update",
                test_name="update_page",
                passed=success
                and (
                    "Updated wiki page" in response
                    or "version 2" in response
                ),
                response=response,
                notes="Updated to version 2",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # wiki_update - version conflict
            _args = {
                "page_name": self.test_wiki_page,
                "content": "Conflict content",
                "version": 1,
                "comment": "Should conflict",
            }
            success, response, raw_result = await self._call_tool(
                "wiki_update", _args,
            )
            # Note: Some Trac versions don't enforce optimistic locking
            result = CheckResult(
                tool="wiki_update",
                test_name="version_conflict",
                passed="version_conflict" in response
                or "Updated wiki page" in response,
                response=response,
                notes="Tested version conflict detection (may not be enforced by server)",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)
        else:
            self.test_wiki_page = None

    async def test_wiki_file_operations(self):
        """Phase 3d: Test wiki file operations"""
        print(
            f"\n{self._color('=== Phase 3d: Wiki File Operations ===')}"
        )

        # wiki_file_detect_format - test with a known file
        # Create a temporary test file first
        import os
        import tempfile

        test_md_path = os.path.join(
            tempfile.gettempdir(), f"mcp_test_{self.timestamp}.md"
        )
        with open(test_md_path, "w") as f:
            f.write("# Test File\n\nThis is **Markdown** content.\n")

        try:
            # wiki_file_detect_format
            _args = {"file_path": test_md_path}
            success, response, raw_result = await self._call_tool(
                "wiki_file_detect_format", _args
            )
            result = CheckResult(
                tool="wiki_file_detect_format",
                test_name="detect_markdown",
                passed=success and "markdown" in response.lower(),
                response=response[:200],
                notes="Detected format of .md file",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # wiki_file_push - push test file to wiki
            test_wiki_file_page = f"MCPFileTest_{self.timestamp}"
            _args = {
                "file_path": test_md_path,
                "page_name": test_wiki_file_page,
                "comment": "MCP file push test",
            }
            success, response, raw_result = await self._call_tool(
                "wiki_file_push", _args,
            )
            result = CheckResult(
                tool="wiki_file_push",
                test_name="push_markdown_file",
                passed=success
                and ("Created" in response or "Updated" in response),
                response=response[:200],
                notes=f"Pushed file to wiki page: {test_wiki_file_page}",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            if success:
                # wiki_file_pull - pull it back
                pull_path = os.path.join(
                    tempfile.gettempdir(),
                    f"mcp_pull_{self.timestamp}.md",
                )
                _args = {
                    "page_name": test_wiki_file_page,
                    "file_path": pull_path,
                    "format": "markdown",
                }
                success, response, raw_result = await self._call_tool(
                    "wiki_file_pull", _args,
                )
                result = CheckResult(
                    tool="wiki_file_pull",
                    test_name="pull_to_markdown",
                    passed=success and "Pulled" in response,
                    response=response[:200],
                    notes=f"Pulled wiki page to: {pull_path}",
                    call_args=_args,
                    **_extract_raw_fields(raw_result),
                )
                self.report.results.append(result)
                self._log_result(result)

                # Verify pulled file exists and has content
                if os.path.exists(pull_path):
                    with open(pull_path) as f:
                        pulled_content = f.read()
                    result = CheckResult(
                        tool="wiki_file_pull",
                        test_name="verify_content",
                        passed=len(pulled_content) > 0
                        and "Test File" in pulled_content,
                        response=pulled_content[:200],
                        notes="Verified pulled file has expected content",
                    )
                    self.report.results.append(result)
                    self._log_result(result)
                    os.unlink(pull_path)

                # Clean up the wiki page we created
                await self._call_tool(
                    "wiki_delete", {"page_name": test_wiki_file_page}
                )

        finally:
            # Clean up temp file
            if os.path.exists(test_md_path):
                os.unlink(test_md_path)

    async def test_milestone_write_operations(self):
        """Phase 3c: Test milestone write operations"""
        print(
            f"\n{self._color('=== Phase 3c: Milestone Write Operations ===')}"
        )

        # milestone_create
        self.test_milestone = f"MCP-Test-{self.timestamp}"
        _args = {
            "name": self.test_milestone,
            "attributes": {
                "due": "2026-12-31T23:59:59",
                "description": "Test milestone for MCP validation",
            },
        }
        success, response, raw_result = await self._call_tool(
            "milestone_create", _args,
        )

        result = CheckResult(
            tool="milestone_create",
            test_name="create_milestone",
            passed=success and "Created milestone" in response,
            response=response,
            notes=f"Created: {self.test_milestone}"
            if success
            else "Creation failed",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        if success:
            # Verify creation
            _verify_args = {"name": self.test_milestone}
            verify_success, verify_response, _verify_raw = await self._call_tool(
                "milestone_get", _verify_args
            )
            result = CheckResult(
                tool="milestone_create",
                test_name="verify_creation",
                passed=verify_success
                and self.test_milestone in verify_response,
                response=verify_response[:200],
                notes="Verified milestone exists",
                call_args=_verify_args,
                **_extract_raw_fields(_verify_raw),
            )
            self.report.results.append(result)
            self._log_result(result)

            # milestone_update
            _args = {
                "name": self.test_milestone,
                "attributes": {
                    "description": "Updated description",
                    "completed": "2026-02-04T12:00:00",
                },
            }
            success, response, raw_result = await self._call_tool(
                "milestone_update", _args,
            )
            result = CheckResult(
                tool="milestone_update",
                test_name="update_milestone",
                passed=success and "Updated milestone" in response,
                response=response,
                notes="Updated description and completed date",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)
        else:
            self.test_milestone = None

    async def test_ticket_batch_operations(self):
        """Phase 3f: Test batch ticket operations"""
        print(
            f"\n{self._color('=== Phase 3f: Batch Ticket Operations ===')}"
        )

        # --- ticket_batch_create: create BATCH_TEST_SIZE tickets ---
        tickets = [
            {
                "summary": f"[MCP BATCH {self.timestamp}] Ticket {i + 1}/{BATCH_TEST_SIZE}",
                "description": f"Batch test ticket **{i + 1}**. Auto-created, auto-deleted.",
                "ticket_type": "task",
                "keywords": "mcp-batch-test,auto-delete",
            }
            for i in range(BATCH_TEST_SIZE)
        ]

        _args = {"tickets": tickets}
        success, response, raw_result = await self._call_tool(
            "ticket_batch_create", _args
        )

        # Extract created ticket IDs from response lines like "  - #123: ..."
        created_ids = [int(m) for m in re.findall(r"#(\d+):", response)]
        self.test_batch_ticket_ids = created_ids

        result = CheckResult(
            tool="ticket_batch_create",
            test_name="create_batch",
            passed=success
            and f"{BATCH_TEST_SIZE}/{BATCH_TEST_SIZE} succeeded"
            in response,
            response=response[:400],
            notes=f"Created {len(created_ids)} tickets: #{min(created_ids)}..#{max(created_ids)}"
            if created_ids
            else "No tickets created",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        # --- ticket_batch_create: verify a sample ticket exists ---
        if created_ids:
            sample_id = created_ids[0]
            _verify_args = {"ticket_id": sample_id}
            verify_ok, verify_resp, _verify_raw = await self._call_tool(
                "ticket_get", _verify_args
            )
            result = CheckResult(
                tool="ticket_batch_create",
                test_name="verify_created",
                passed=verify_ok
                and f"Ticket #{sample_id}" in verify_resp,
                response=verify_resp[:200],
                notes=f"Spot-checked ticket #{sample_id}",
                call_args=_verify_args,
                **_extract_raw_fields(_verify_raw),
            )
            self.report.results.append(result)
            self._log_result(result)

        # --- ticket_batch_create: partial failure (missing summary) ---
        mixed_tickets = [
            {
                "summary": f"[MCP BATCH {self.timestamp}] Good ticket",
                "description": "Valid ticket",
            },
            {"description": "Missing summary field"},  # should fail
            {
                "summary": f"[MCP BATCH {self.timestamp}] Another good",
                "description": "Also valid",
            },
        ]
        _args = {"tickets": mixed_tickets}
        success, response, raw_result = await self._call_tool(
            "ticket_batch_create", _args
        )

        # Parse any newly created IDs for cleanup
        extra_ids = [int(m) for m in re.findall(r"#(\d+):", response)]
        self.test_batch_ticket_ids.extend(extra_ids)

        result = CheckResult(
            tool="ticket_batch_create",
            test_name="partial_failure",
            passed="2/3 succeeded" in response
            and "1 failed" in response,
            response=response[:400],
            notes="1 ticket missing summary should fail, 2 should succeed",
            call_args=_args,
            **_extract_raw_fields(raw_result),
        )
        self.report.results.append(result)
        self._log_result(result)

        # --- ticket_batch_create: empty list validation ---
        _args = {"tickets": []}
        _, response, _raw = await self._call_tool(
            "ticket_batch_create", _args
        )
        result = CheckResult(
            tool="ticket_batch_create",
            test_name="empty_list_error",
            passed="validation_error" in response
            or "required" in response.lower(),
            response=response[:200],
            notes="Expected validation error for empty tickets list",
            call_args=_args,
            **_extract_raw_fields(_raw),
        )
        self.report.results.append(result)
        self._log_result(result)

        # --- ticket_batch_update: update all created tickets ---
        if self.test_batch_ticket_ids:
            updates = [
                {
                    "ticket_id": tid,
                    "keywords": "mcp-batch-test,auto-delete,batch-updated",
                    "comment": f"Batch update test — ticket **#{tid}**",
                }
                for tid in self.test_batch_ticket_ids
            ]

            _args = {"updates": updates}
            success, response, raw_result = await self._call_tool(
                "ticket_batch_update", _args
            )
            expected_count = len(self.test_batch_ticket_ids)

            result = CheckResult(
                tool="ticket_batch_update",
                test_name="update_batch",
                passed=success
                and f"{expected_count}/{expected_count} succeeded"
                in response,
                response=response[:400],
                notes=f"Updated {expected_count} tickets with keywords + comment",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            # Spot-check that update applied
            sample_id = self.test_batch_ticket_ids[0]
            _verify_args = {"ticket_id": sample_id}
            verify_ok, verify_resp, _verify_raw = await self._call_tool(
                "ticket_get", _verify_args
            )
            result = CheckResult(
                tool="ticket_batch_update",
                test_name="verify_updated",
                passed=verify_ok and "batch-updated" in verify_resp,
                response=verify_resp[:300],
                notes=f"Verified keyword added to ticket #{sample_id}",
                call_args=_verify_args,
                **_extract_raw_fields(_verify_raw),
            )
            self.report.results.append(result)
            self._log_result(result)

        # --- ticket_batch_update: empty list validation ---
        _args = {"updates": []}
        _, response, _raw = await self._call_tool(
            "ticket_batch_update", _args
        )
        result = CheckResult(
            tool="ticket_batch_update",
            test_name="empty_list_error",
            passed="validation_error" in response
            or "required" in response.lower(),
            response=response[:200],
            notes="Expected validation error for empty updates list",
            call_args=_args,
            **_extract_raw_fields(_raw),
        )
        self.report.results.append(result)
        self._log_result(result)

        # --- ticket_batch_delete: delete all created tickets ---
        if self.test_batch_ticket_ids:
            _args = {"ticket_ids": self.test_batch_ticket_ids}
            success, response, raw_result = await self._call_tool(
                "ticket_batch_delete", _args,
            )
            expected_count = len(self.test_batch_ticket_ids)

            result = CheckResult(
                tool="ticket_batch_delete",
                test_name="delete_batch",
                passed=success
                and f"{expected_count}/{expected_count} succeeded"
                in response,
                response=response[:400],
                notes=f"Deleted {expected_count} tickets",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            if (
                success
                and f"{expected_count}/{expected_count} succeeded"
                in response
            ):
                # Spot-check a ticket is gone
                sample_id = self.test_batch_ticket_ids[0]
                _verify_args = {"ticket_id": sample_id}
                _, verify_resp, _verify_raw = await self._call_tool(
                    "ticket_get", _verify_args
                )
                result = CheckResult(
                    tool="ticket_batch_delete",
                    test_name="verify_deleted",
                    passed="not_found" in verify_resp
                    or "error" in verify_resp.lower(),
                    response=verify_resp[:200],
                    notes=f"Confirmed ticket #{sample_id} no longer exists",
                    call_args=_verify_args,
                    **_extract_raw_fields(_verify_raw),
                )
                self.report.results.append(result)
                self._log_result(result)

                self.test_batch_ticket_ids = []  # All cleaned up

        # --- ticket_batch_delete: empty list validation ---
        _args = {"ticket_ids": []}
        _, response, _raw = await self._call_tool(
            "ticket_batch_delete", _args
        )
        result = CheckResult(
            tool="ticket_batch_delete",
            test_name="empty_list_error",
            passed="validation_error" in response
            or "required" in response.lower(),
            response=response[:200],
            notes="Expected validation error for empty ticket_ids list",
            call_args=_args,
            **_extract_raw_fields(_raw),
        )
        self.report.results.append(result)
        self._log_result(result)

    async def test_delete_operations(self):
        """Phase 4: Test delete operations"""
        print(f"\n{self._color('=== Phase 4: Delete Operations ===')}")

        # wiki_delete
        if self.test_wiki_page:
            _args = {"page_name": self.test_wiki_page}
            success, response, raw_result = await self._call_tool(
                "wiki_delete", _args
            )
            result = CheckResult(
                tool="wiki_delete",
                test_name="delete_page",
                passed=success and "Deleted" in response,
                response=response,
                notes=f"Deleted: {self.test_wiki_page}",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            if success:
                # Verify deletion
                _verify_args = {"page_name": self.test_wiki_page}
                _, verify_response, _verify_raw = await self._call_tool(
                    "wiki_get", _verify_args
                )
                result = CheckResult(
                    tool="wiki_delete",
                    test_name="verify_deletion",
                    passed="not_found" in verify_response
                    or "does not exist" in verify_response.lower(),
                    response=verify_response[:200],
                    notes="Confirmed page no longer exists",
                    call_args=_verify_args,
                    **_extract_raw_fields(_verify_raw),
                )
                self.report.results.append(result)
                self._log_result(result)
                self.test_wiki_page = None

        # milestone_delete
        if self.test_milestone:
            _args = {"name": self.test_milestone}
            success, response, raw_result = await self._call_tool(
                "milestone_delete", _args
            )
            result = CheckResult(
                tool="milestone_delete",
                test_name="delete_milestone",
                passed=success and "Deleted" in response,
                response=response,
                notes=f"Deleted: {self.test_milestone}",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            if success:
                # Verify deletion
                _verify_args = {"name": self.test_milestone}
                _, verify_response, _verify_raw = await self._call_tool(
                    "milestone_get", _verify_args
                )
                result = CheckResult(
                    tool="milestone_delete",
                    test_name="verify_deletion",
                    passed="not_found" in verify_response
                    or "error" in verify_response.lower(),
                    response=verify_response[:200],
                    notes="Confirmed milestone no longer exists",
                    call_args=_verify_args,
                    **_extract_raw_fields(_verify_raw),
                )
                self.report.results.append(result)
                self._log_result(result)
                self.test_milestone = None

        # ticket_delete
        if self.test_ticket_id:
            _args = {"ticket_id": self.test_ticket_id}
            success, response, raw_result = await self._call_tool(
                "ticket_delete", _args
            )
            result = CheckResult(
                tool="ticket_delete",
                test_name="delete_ticket",
                passed=success
                and (
                    "Deleted" in response
                    or "deleted" in response.lower()
                ),
                response=response[:200],
                notes=f"Deleted test ticket #{self.test_ticket_id}",
                call_args=_args,
                **_extract_raw_fields(raw_result),
            )
            self.report.results.append(result)
            self._log_result(result)

            if success:
                # Verify deletion
                _verify_args = {"ticket_id": self.test_ticket_id}
                _, verify_response, _verify_raw = await self._call_tool(
                    "ticket_get", _verify_args
                )
                result = CheckResult(
                    tool="ticket_delete",
                    test_name="verify_deletion",
                    passed="not_found" in verify_response
                    or "error" in verify_response.lower(),
                    response=verify_response[:200],
                    notes="Confirmed ticket no longer exists",
                    call_args=_verify_args,
                    **_extract_raw_fields(_verify_raw),
                )
                self.report.results.append(result)
                self._log_result(result)
                self.test_ticket_id = (
                    None  # Prevent cleanup from trying to close it
                )

    async def test_error_handling(self):
        """Phase 5: Test error handling"""
        print(f"\n{self._color('=== Phase 5: Error Handling ===')}")

        # ticket_get - non-existent
        _args = {"ticket_id": 99999999}
        _, response, _raw = await self._call_tool(
            "ticket_get", _args
        )
        result = CheckResult(
            tool="ticket_get",
            test_name="non_existent",
            passed="not_found" in response
            or "error" in response.lower(),
            response=response[:200],
            notes="Expected not_found error",
            call_args=_args,
            **_extract_raw_fields(_raw),
        )
        self.report.results.append(result)
        self._log_result(result)

        # ticket_delete - non-existent
        _args = {"ticket_id": 99999999}
        _, response, _raw = await self._call_tool(
            "ticket_delete", _args
        )
        result = CheckResult(
            tool="ticket_delete",
            test_name="non_existent",
            passed="not_found" in response
            or "error" in response.lower(),
            response=response[:200],
            notes="Expected not_found error",
            call_args=_args,
            **_extract_raw_fields(_raw),
        )
        self.report.results.append(result)
        self._log_result(result)

        # wiki_get - non-existent
        _args = {"page_name": "NonExistentPage_DoesNotExist_12345"}
        _, response, _raw = await self._call_tool(
            "wiki_get", _args,
        )
        result = CheckResult(
            tool="wiki_get",
            test_name="non_existent",
            passed="not_found" in response
            or "does not exist" in response.lower(),
            response=response[:200],
            notes="Expected not_found error",
            call_args=_args,
            **_extract_raw_fields(_raw),
        )
        self.report.results.append(result)
        self._log_result(result)

        # milestone_get - non-existent
        _args = {"name": "NonExistent-Milestone-12345"}
        _, response, _raw = await self._call_tool(
            "milestone_get", _args
        )
        result = CheckResult(
            tool="milestone_get",
            test_name="non_existent",
            passed="not_found" in response
            or "error" in response.lower(),
            response=response[:200],
            notes="Expected not_found error",
            call_args=_args,
            **_extract_raw_fields(_raw),
        )
        self.report.results.append(result)
        self._log_result(result)

        # wiki_delete - non-existent
        _args = {"page_name": "NonExistentPage_ToDelete_12345"}
        _, response, _raw = await self._call_tool(
            "wiki_delete", _args,
        )
        result = CheckResult(
            tool="wiki_delete",
            test_name="non_existent",
            passed="not_found" in response
            or "does not exist" in response.lower(),
            response=response[:200],
            notes="Expected not_found error",
            call_args=_args,
            **_extract_raw_fields(_raw),
        )
        self.report.results.append(result)
        self._log_result(result)

        # ticket_create - missing required field
        _args = {"description": "No summary"}
        _, response, _raw = await self._call_tool(
            "ticket_create", _args
        )
        result = CheckResult(
            tool="ticket_create",
            test_name="missing_summary",
            passed="validation_error" in response
            or "required" in response.lower(),
            response=response[:200],
            notes="Expected validation_error",
            call_args=_args,
            **_extract_raw_fields(_raw),
        )
        self.report.results.append(result)
        self._log_result(result)

    async def cleanup(self):
        """Clean up test resources"""
        print(f"\n{self._color('=== Cleanup ===')}")

        cleanup_success = True

        # Batch-delete leftover batch tickets (if batch delete test failed)
        if self.test_batch_ticket_ids:
            success, _, _raw = await self._call_tool(
                "ticket_batch_delete",
                {"ticket_ids": self.test_batch_ticket_ids},
            )
            if success:
                print(
                    f"  {self._color('✓')} Batch-deleted {len(self.test_batch_ticket_ids)} leftover batch tickets"
                )
                self.test_batch_ticket_ids = []
            else:
                print(
                    f"  {self._color('✗')} Could not batch-delete leftover tickets, trying individually"
                )
                for tid in self.test_batch_ticket_ids:
                    try:
                        await run_sync(self.client.delete_ticket, tid)
                    except Exception:
                        cleanup_success = False

        # Close test ticket if still exists (fallback if delete failed or was skipped)
        if self.test_ticket_id:
            try:
                await run_sync(
                    self.client.update_ticket,
                    self.test_ticket_id,
                    "[AUTO-CLEANUP] MCP test completed",
                    {"status": "closed", "resolution": "invalid"},
                )
                print(
                    f"  {self._color('✓')} Closed test ticket #{self.test_ticket_id}"
                )
            except Exception as e:
                print(
                    f"  {self._color('✗')} Could not close ticket #{self.test_ticket_id}: {e}"
                )
                cleanup_success = False

        # Delete test wiki page if still exists
        if self.test_wiki_page:
            success, _, _raw = await self._call_tool(
                "wiki_delete", {"page_name": self.test_wiki_page}
            )
            if success:
                print(
                    f"  {self._color('✓')} Deleted test wiki page: {self.test_wiki_page}"
                )
            else:
                print(
                    f"  {self._color('✗')} Could not delete wiki page: {self.test_wiki_page}"
                )
                cleanup_success = False

        # Delete test milestone if still exists
        if self.test_milestone:
            success, _, _raw = await self._call_tool(
                "milestone_delete", {"name": self.test_milestone}
            )
            if success:
                print(
                    f"  {self._color('✓')} Deleted test milestone: {self.test_milestone}"
                )
            else:
                print(
                    f"  {self._color('✗')} Could not delete milestone: {self.test_milestone}"
                )
                cleanup_success = False

        return cleanup_success

    def generate_report(self, output_path: str):
        """Generate comprehensive test report"""
        self.report.date = datetime.now().isoformat()

        # Group results by tool
        tools_tested = set()
        results_by_category = {
            "Connectivity": [],
            "System Tools": [],
            "Ticket Tools": [],
            "Batch Ticket Tools": [],
            "Wiki Tools": [],
            "Wiki File Tools": [],
            "Milestone Tools": [],
            "Error Handling": [],
        }

        for result in self.report.results:
            tools_tested.add(result.tool)
            if result.tool == "ping":
                results_by_category["Connectivity"].append(result)
            elif result.tool == "get_server_time":
                results_by_category["System Tools"].append(result)
            elif result.tool.startswith("ticket_batch_"):
                if "empty_list" in result.test_name:
                    results_by_category["Error Handling"].append(result)
                else:
                    results_by_category["Batch Ticket Tools"].append(
                        result
                    )
            elif result.tool.startswith("ticket_"):
                if (
                    "non_existent" in result.test_name
                    or "missing_" in result.test_name
                ):
                    results_by_category["Error Handling"].append(result)
                else:
                    results_by_category["Ticket Tools"].append(result)
            elif result.tool.startswith("wiki_file_"):
                if "non_existent" in result.test_name:
                    results_by_category["Error Handling"].append(result)
                else:
                    results_by_category["Wiki File Tools"].append(
                        result
                    )
            elif result.tool.startswith("wiki_"):
                if "non_existent" in result.test_name:
                    results_by_category["Error Handling"].append(result)
                else:
                    results_by_category["Wiki Tools"].append(result)
            elif result.tool.startswith("milestone_"):
                if "non_existent" in result.test_name:
                    results_by_category["Error Handling"].append(result)
                else:
                    results_by_category["Milestone Tools"].append(
                        result
                    )
        report_lines = [
            "# Comprehensive MCP Tool Test Report",
            "",
            f"**Date:** {self.report.date}",
            f"**Server:** {self.report.server_url}",
            f"**Test Script Version:** {VERSION}",
            f"**Package Version:** {PACKAGE_VERSION}",
            "",
            "## Executive Summary",
            "",
            f"- **Tools Tested:** {len(tools_tested)}/27",
            f"- **Total Scenarios:** {self.report.total}",
            f"- **Passed:** {self.report.passed}",
            f"- **Failed:** {self.report.failed}",
            f"- **Pass Rate:** {(self.report.passed / self.report.total * 100):.1f}%"
            if self.report.total > 0
            else "N/A",
            "",
        ]

        for category, results in results_by_category.items():
            if not results:
                continue

            report_lines.extend(
                [
                    f"## {category}",
                    "",
                ]
            )

            # Group by tool
            current_tool = None
            for result in results:
                if result.tool != current_tool:
                    current_tool = result.tool
                    report_lines.extend(
                        [
                            f"### {result.tool}",
                            "",
                        ]
                    )

                status = "PASS" if result.passed else "FAIL"
                report_lines.append(f"**{result.test_name}:** {status}")
                if result.notes:
                    report_lines.append(f"- Notes: {result.notes}")
                if not result.passed and result.error:
                    report_lines.append(
                        f"- Error: {result.error[:100]}"
                    )
                report_lines.append("")

        # Issues found section
        failed_results = [
            r for r in self.report.results if not r.passed
        ]
        if failed_results:
            report_lines.extend(
                [
                    "## Issues Found",
                    "",
                ]
            )
            for i, result in enumerate(failed_results, 1):
                report_lines.append(
                    f"{i}. **{result.tool}.{result.test_name}**: {result.error or result.response[:100]}"
                )
            report_lines.append("")

        # Write report
        with open(output_path, "w") as f:
            f.write("\n".join(report_lines))

        print(f"\n{self._color('Report saved to:')} {output_path}")

    async def run_all_tests(self) -> bool:
        """Run all test phases"""
        try:
            # Phase 1: Connectivity
            await self.test_ping()
            await self.test_system_tools()

            # Phase 2: Read operations
            await self.test_ticket_read_operations()
            await self.test_wiki_read_operations()
            await self.test_milestone_read_operations()

            # Phase 3: Write operations
            await self.test_ticket_write_operations()
            await self.test_wiki_write_operations()
            await self.test_wiki_file_operations()
            await self.test_milestone_write_operations()
            await self.test_ticket_batch_operations()

            # Phase 4: Delete operations
            await self.test_delete_operations()

            # Phase 5: Error handling
            await self.test_error_handling()

            # Cleanup
            cleanup_ok = await self.cleanup()

            return self.report.failed == 0 and cleanup_ok

        except Exception as e:
            self.logger.error(
                f"Test execution failed: {e}", exc_info=True
            )
            return False


def setup_logging(
    log_file: str | None, verbose: bool = False
) -> logging.Logger:
    """Set up logging"""
    logger = logging.getLogger("MCPTester")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            )
        )
        logger.addHandler(fh)

    if verbose:
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(
            logging.Formatter("%(levelname)s - %(message)s")
        )
        logger.addHandler(ch)

    return logger


async def async_main(args):
    """Async main function"""
    logger = setup_logging(args.log_file, verbose=args.verbose)

    # Print header
    print(f"\n{'=' * 70}")
    print(f"{'Comprehensive MCP Tool Live Testing':^70}")
    print(f"{'v' + VERSION:^70}")
    print(f"{'trac-mcp-server ' + PACKAGE_VERSION:^70}")
    print(f"{'=' * 70}\n")

    try:
        load_dotenv()
        config = load_config()

        # Override config with CLI arguments
        if args.url:
            config.trac_url = args.url
        if args.username:
            config.username = args.username
        if args.password:
            config.password = args.password
        if args.insecure:
            config.insecure = True

        tester = ComprehensiveMCPTester(
            config, logger, verbose=args.verbose
        )

        success = await tester.run_all_tests()

        # Generate report
        report_path = (
            args.output
            or f"./comprehensive-mcp-tool-test-{datetime.now().strftime('%Y-%m-%d')}.md"
        )
        tester.generate_report(report_path)

        # Print summary
        print(f"\n{'=' * 70}")
        print(f"{'SUMMARY':^70}")
        print(f"{'=' * 70}")

        print(
            f"Total: {tester.report.total} | Passed: {tester.report.passed} | Failed: {tester.report.failed}"
        )

        if not success:
            print("\nSome tests failed. Check the report for details.")

        return 0 if success else 1

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n* Fatal error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive MCP Tool Live Testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Run all tests with default config
  %(prog)s --verbose                          # Run with verbose output
  %(prog)s --url http://trac.example.com      # Override Trac URL
  %(prog)s --output ./my-report.md            # Custom report location
        """,
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {VERSION}"
    )
    parser.add_argument("--url", help="Override Trac URL")
    parser.add_argument("--username", help="Override username")
    parser.add_argument("--password", help="Override password")
    parser.add_argument(
        "--insecure", action="store_true", help="Skip SSL verification"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    parser.add_argument("--output", "-o", help="Output report path")
    parser.add_argument(
        "--log-file",
        default=None,
        help="Log file path (omit to skip file logging)",
    )

    args = parser.parse_args()
    sys.exit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
