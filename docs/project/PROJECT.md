# Project: trac-mcp-server

## What This Is

Standalone MCP (Model Context Protocol) server for Trac integration via XML-RPC protocol. Provides AI agents with standardized access to Trac project management features including tickets, wiki pages, milestones, and document sync — with structured JSON output, batch operations, and format conversion.

## Core Value

Enables AI agents to interact with Trac instances (wiki, tickets, search, milestones) via the standardized MCP protocol. Any MCP-compatible client (Claude Desktop, Claude Code, pydantic-ai agents, etc.) can use this server to read and write Trac data.

## Requirements

### Validated

- MCP Tools (29 total) — v2.1.1
- Wiki page resources via MCP resource protocol — v2.0.0
- Markdown <-> TracWiki format conversion — v2.0.0
- Structured error responses across all tools — v2.1.0
- Config validation (URL, max_parallel, whitespace) — v2.1.0
- CI pipeline (GitHub Actions + Ruff linting) — v2.1.0
- Batch ticket operations (create, update, delete) — v2.1.1
- Standalone documentation (no monolith references) — v2.1.0

### MCP Tools (29 total)

**Tickets:**
- `ticket_search` - Search tickets with Trac query language
- `ticket_get` - Get ticket details by ID (all fields including keywords, cc, reporter, resolution)
- `ticket_create` - Create new tickets
- `ticket_update` - Update existing tickets
- `ticket_delete` - Delete tickets
- `ticket_changelog` - Get ticket change history
- `ticket_fields` - List available ticket fields
- `ticket_actions` - Get available ticket actions
- `ticket_batch_create` - Create multiple tickets in one call
- `ticket_batch_update` - Update multiple tickets in one call
- `ticket_batch_delete` - Delete multiple tickets in one call

**Wiki:**
- `wiki_get` - Get wiki page content
- `wiki_search` - Search wiki pages
- `wiki_create` - Create new wiki pages
- `wiki_update` - Update existing wiki pages
- `wiki_delete` - Delete wiki pages
- `wiki_recent_changes` - List recent wiki changes

**Wiki Files:**
- `wiki_file_push` - Push local file to wiki (with format conversion)
- `wiki_file_pull` - Pull wiki page to local file
- `wiki_file_detect_format` - Detect format of wiki content

**Milestones:**
- `milestone_list` - List all milestones
- `milestone_get` - Get milestone details
- `milestone_create` - Create new milestones
- `milestone_update` - Update existing milestones
- `milestone_delete` - Delete milestones

**Sync:**
- `doc_sync` - Synchronize documents between local files and wiki
- `doc_sync_status` - Check sync status

**System:**
- `ping` - Test server connectivity
- `get_server_time` - Get Trac server time

### Out of Scope

- Config file support — env vars are the natural MCP server config mechanism
- Interactive authentication — MCP servers run as subprocesses
- Mobile/web UI — this is a protocol server, not a user-facing application

## Context

Extracted from trac_assist v1.3.2 monolith (Phase 59). Now operates as standalone package v2.1.1 with its own repository, test suite, CI pipeline, and release lifecycle.

The trac_assist package (AI agent layer) depends on this server as an external binary, launching it via `trac-mcp-server` command over stdio transport.

**Current state:** 23,100 LOC Python (src/ + tests/). 781 unit tests passing. 29 MCP tools. Ruff linting clean.

## Constraints

- **Protocol:** MCP (Model Context Protocol) - JSON-RPC 2.0 over stdio
- **Backend:** XML-RPC for all Trac communication
- **Transport:** stdio (for MCP client integration)
- **Configuration:** Environment variables (TRAC_URL, TRAC_USERNAME, TRAC_PASSWORD, TRAC_INSECURE, TRAC_MAX_PARALLEL_REQUESTS, TRAC_MAX_BATCH_SIZE)
- **Python:** >=3.10
- **Dependencies:** mcp[cli], requests, mistune, PyYAML, lxml, pydantic, charset-normalizer, merge3

## Key Decisions

| Decision | Rationale | Date | Outcome |
|----------|-----------|------|---------|
| Env-var configuration (no config file) | MCP servers are launched as subprocesses; env vars are the natural config mechanism | 2026-02-14 | Good |
| Standalone binary via pip/pipx | `trac-mcp-server` entry point for easy installation and MCP client config | 2026-02-14 | Good |
| stdio transport | Standard MCP transport for Claude Desktop/Code integration | 2026-02-14 | Good |
| Version 2.0.0 | Breaking change from monolith (was embedded in trac_assist v1.3.x) | 2026-02-14 | Good |
| Hardcoded "defect" default ticket_type | Replaces enum_loader lookup from trac_assist (standalone has no YAML config) | 2026-02-14 | Good |
| Promote pydantic and charset-normalizer to direct deps | Both imported directly; transitive-only is fragile | 2026-02-15 | Good |
| removesuffix("/") for URL normalization | rstrip("/") corrupts scheme double-slash | 2026-02-15 | Good |
| Per-item exception catching for batch ops | Matches _fetch_ticket pattern; best-effort semantics | 2026-02-15 | Good |
| _get_max_batch_size() reads env at call time | Allows runtime override without restart | 2026-02-15 | Good |

---
*Last updated: 2026-02-15 after v2.1.0 milestone*
