# Changelog

All notable changes to trac-mcp-server will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [2.1.1] - Unreleased

### Added
- Batch ticket operations: `ticket_batch_create`, `ticket_batch_delete`, `ticket_batch_update` -- best-effort processing with per-item results and bounded parallelism via `gather_limited`
- `TRAC_MAX_BATCH_SIZE` environment variable (default: 500, range: 1-10000) for controlling maximum items per batch operation
- Config path resolution (`resolve_config_path()`) and bootstrapping (`ensure_config()`) utilities in config_loader.py
- Package version display in test script output
- Shared error translation utility (`translate_xmlrpc_error`) consolidating 5 duplicate implementations
- Shared timestamp formatting utility (`format_timestamp`) with timezone-aware UTC
- Shared constants module (`constants.py`) for tool handlers
- Network timeout (10s connect, 60s read) on XML-RPC requests
- 79 new tests covering TracClient methods, error handlers, auto_convert, and logger (781 -> 860 -> 641 after sync removal)
- `CHANGELOG.md` version history extracted from planning documents

### Changed
- Modernized typing across all source files to Python 3.10+ style (`X | None` instead of `Optional[X]`, built-in generics)
- Renamed `TRAC_ASSIST_CONFIG` env var to `TRAC_MCP_CONFIG` (backward compatible with deprecation warning)
- Unified `max_parallel_requests` default to 5 (was 2 in TracConfig)
- Moved `max_batch_size` from standalone function to TracConfig field with Pydantic validation
- Consolidated redundant wiki tool tests (457 -> 158 lines, 65% reduction)
- Reorganized test files into consistent `tests/test_mcp/tools/` directory structure
- Migrated 2 test files from unittest.TestCase to pytest style

### Fixed
- `ticket_get` now includes keywords, cc, reporter, and resolution fields in both text and structured JSON output (were previously omitted)
- Lazy logger formatting (`%s` instead of f-strings) in lifespan and system modules
- `ConversionResult` type mismatch in wiki resources (was passing object as string)
- `set_client()` signature to accept `TracClient | None` (removed type: ignore)
- Dead code removal: duplicate `get_version()`, unused validator loop, stale imports
- Live test configuration: `.env` now loaded in conftest for `TRAC_URL` availability

### Removed
- Sync subsystem: `doc_sync` and `doc_sync_status` MCP tools, `src/trac_mcp_server/sync/` module, and all sync-related tests (213 tests)
- `scripts/test_trac.py` live test script and associated report
- Sync config schema models (`SyncMappingRule`, `SyncProfileConfig`) and sync profile support in `UnifiedConfig`

## [2.1.0] - 2026-02-15

Post-extraction cleanup release. Hardens the standalone package after splitting from trac_assist v1.3.2.

### Changed
- Rewrote all documentation for standalone usage (README, configuration, deployment, troubleshooting, tool reference)
- Removed orphaned trac_assist references from source, comments, and docstrings
- Cleaned import paths and removed unused dependencies (cssselect, anyio from direct deps)
- Promoted pydantic and charset-normalizer to direct dependencies
- Standardized all error returns to MCP CallToolResult format (fixed isError boolean bug)
- Bumped setuptools requirement to >=77.0 for PEP 639 support

### Added
- Config validation: URL structure, max_parallel bounds (1-20), whitespace rejection
- .env.example with all supported environment variables
- MIT LICENSE file with PEP 639 SPDX metadata
- PyInstaller build.sh and install.sh scripts for standalone binary distribution
- GitHub Actions CI workflow (lint, test, live-test, build jobs)
- Local ci.sh script mirroring CI checks
- Ruff linter (E4/E7/E9/F/B/I rules) with zero-violation baseline
- Comprehensive test coverage: 741 tests (up from ~200 extracted tests)

### Fixed
- isError field in error responses now correctly set to True (was always False)
- Detection tests relying on trac_assist fixtures
- Stale monolith references in test_trac.py integration script

## [2.0.0] - 2026-02-14

Initial standalone release. Extracted from trac_assist v1.3.2 as independent MCP server package.

### Added
- 24 MCP tools (tickets, wiki, milestones, system)
- Wiki page resources via MCP resource protocol
- Markdown to TracWiki bidirectional format conversion
- stdio transport for MCP client integration
- Environment variable configuration (TRAC_URL, TRAC_USERNAME, TRAC_PASSWORD)
- `trac-mcp-server` CLI entry point
- Independent test suite
