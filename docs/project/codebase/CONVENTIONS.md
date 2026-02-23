# Coding Conventions

**Analysis Date:** 2026-02-14

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python source files
- Source files: `src/trac_mcp_server/validators.py`, `src/trac_mcp_server/file_handler.py`
- Tool modules named by domain: `ticket_read.py`, `ticket_write.py`, `wiki_read.py`, `wiki_write.py`
- Test files: `test_<module_name>.py` (e.g., `tests/test_client.py`, `tests/test_converter.py`)
- Init files: every package has `__init__.py` with `__all__` exports

**Functions:**
- Use `snake_case` for all functions and methods
- Public methods: descriptive verbs (`search_tickets`, `get_wiki_page`, `validate_connection`)
- Private methods: prefix with single underscore (`_rpc_request`, `_parse_xmlrpc_value`, `_handle_search`)
- Module-level private helpers: single underscore prefix (`_stderr_print`, `_format_timestamp`, `_translate_xmlrpc_error`)
- Test functions: `test_<descriptive_name>` (e.g., `test_rpc_url_construction`, `test_cache_expiry`)
- Factory/helper functions in tests: prefix with underscore (`_make_profile`, `_setup_engine`)

**Variables:**
- Use `snake_case` for local variables and parameters
- Constants: `UPPER_SNAKE_CASE` (e.g., `TICKET_READ_TOOLS`, `WIKI_TOOLS`, `SYNC_TOOLS`)
- Module-level logger: `logger = logging.getLogger(__name__)` (see `src/trac_mcp_server/config.py`, `src/trac_mcp_server/mcp/server.py`)
- Module-level globals: underscore prefix (`_trac_client`, `_semaphore`)

**Classes:**
- Use `PascalCase` for class names
- Source classes: `TracClient`, `Config`, `SyncEngine`, `PathMapper`, `JsonFormatter`
- Test classes: `TestTracClient`, `TestCachePersistence`, `TestPushFlow`, `TestDryRun`
- Pydantic models: `SyncEntry`, `ConflictInfo`, `SyncResult`, `SyncReport`
- Enum classes: `SyncAction` (inherits `str, Enum`)

**Types:**
- Use `PascalCase` for type aliases and generics
- TypeVar: `T = TypeVar("T")` in `src/trac_mcp_server/core/async_utils.py`
- Use `typing.Optional`, `typing.Dict`, `typing.List` alongside Python 3.10+ `X | None`, `dict`, `list` syntax (mixed usage -- newer code prefers built-in generics)

## Code Style

**Formatting:**
- No explicit formatter configured (no `.prettierrc`, `ruff.toml`, `[tool.black]`, or `[tool.ruff]` in `pyproject.toml`)
- De facto style: 4-space indentation, double quotes for strings
- Line length: generally under 100 characters, some lines extend to ~120
- Trailing commas used in multi-line function calls and data structures

**String Quotes:**
- Double quotes (`"`) are the dominant convention
- f-strings used extensively for interpolation: `f"Error: {e}"`, `f"{config.trac_url.rstrip('/')}/login/rpc"`
- Docstrings use triple double quotes: `"""..."""`

**Semicolons:**
- Not used (standard Python)

**Blank Lines:**
- Two blank lines between top-level definitions (functions, classes)
- One blank line between methods within a class
- Occasional blank line within method body for logical grouping

## Import Organization

**Order:**
1. Standard library imports (`import os`, `import logging`, `import json`, `import asyncio`)
2. Third-party imports (`import requests`, `import mcp.types as types`, `from pydantic import BaseModel`)
3. Local/package imports (`from ..config import Config`, `from ...core.client import TracClient`)

**Style:**
- `import module` for standard lib modules
- `from module import X, Y` for specific items
- Relative imports within the package: `from ..config import Config`, `from ...core.async_utils import run_sync`
- Absolute imports in tests: `from trac_mcp_server.core.client import TracClient`
- `import X as Y` aliasing: `import mcp.types as types`

**Path Aliases:**
- None configured. All imports use relative paths within `src/trac_mcp_server/` or absolute `trac_mcp_server.*` in tests.

**Example (from `src/trac_mcp_server/mcp/tools/ticket_read.py`):**
```python
import xmlrpc.client
from datetime import datetime
from typing import Any

import mcp.types as types

from ...core.client import TracClient
from ...core.async_utils import run_sync, run_sync_limited, gather_limited
from ...converters import tracwiki_to_markdown
from .errors import build_error_response
```

## Error Handling

**Patterns:**
- **Raise ValueError for input validation** -- validate early, raise `ValueError` with descriptive messages (see `src/trac_mcp_server/core/client.py` lines 147-150, `src/trac_mcp_server/config.py` lines 43-56)
- **Catch and translate XML-RPC faults** -- `xmlrpc.client.Fault` exceptions are caught and translated to structured error responses with `build_error_response()` (see `src/trac_mcp_server/mcp/tools/ticket_read.py` lines 146-151)
- **Structured error responses for MCP tools** -- use `build_error_response(error_type, message, corrective_action)` from `src/trac_mcp_server/mcp/tools/errors.py`
  - Error types: `not_found`, `permission_denied`, `version_conflict`, `validation_error`, `server_error`, `method_not_available`
  - Every error includes a corrective action string to guide AI agents
- **RuntimeError for system failures** -- configuration errors and connection failures raise `RuntimeError` in `src/trac_mcp_server/mcp/lifespan.py`
- **Bare Exception catch for graceful degradation** -- `except Exception:` used sparingly for non-critical operations like page iteration (see `src/trac_mcp_server/core/client.py` line 395, 539)

**Error response format:**
```python
build_error_response("not_found", error.faultString, "Use ticket_search to verify ticket exists.")
# Returns: [TextContent(text="Error (not_found): ...\n\nAction: Use ticket_search to verify...")]
```

**Validation pattern (from `src/trac_mcp_server/validators.py`):**
```python
def validate_page_name(page_name: str) -> Tuple[bool, str]:
    """Returns (True, "") if valid, (False, reason) if invalid."""
    if not page_name or not page_name.strip():
        return (False, format_validation_error("Page name", "cannot be empty"))
    ...
    return (True, "")
```

## Logging

**Framework:** Python `logging` module (standard library)

**Setup:** `src/trac_mcp_server/logger.py`
- Two modes: `mcp` (file-only, never stdout) and `cli` (stderr)
- JSON structured logging available via `JsonFormatter` class
- Default levels: WARNING (MCP mode), INFO (CLI mode)
- Environment variable overrides: `LOG_LEVEL`, `LOG_FILE`
- Third-party loggers silenced at non-DEBUG: `urllib3`, `httpx`, `httpcore`

**Patterns:**
- Obtain logger per module: `logger = logging.getLogger(__name__)`
- Use `logger.info()` for operational messages, `logger.error()` for failures, `logger.warning()` for non-critical issues
- User-facing messages in MCP mode go to `sys.stderr` via `_stderr_print()` helper in `src/trac_mcp_server/mcp/lifespan.py`
- f-string formatting in log calls: `logger.info(f"Configuration loaded for {config.trac_url}")`
- **CRITICAL: Never log to stdout in MCP mode** -- stdout is reserved for JSON-RPC protocol messages

## Comments

**When to Comment:**
- Module-level docstrings on every `.py` file explaining purpose and contents
- Section divider comments using `# ----` for organizing related code blocks (see `src/trac_mcp_server/validators.py`, `tests/test_sync_engine.py`)
- Inline comments for non-obvious logic: `# [id, created, modified, attributes]`, `# Construct path to XML-RPC endpoint`
- `# type: ignore` annotations for known type checker limitations: `# type: ignore[arg-type]`, `# pyright: ignore[reportReturnType]`

**Docstrings:**
- Google-style docstrings with `Args:`, `Returns:`, `Raises:` sections
- Used on all public functions and classes
- Private functions/methods also have docstrings when logic is non-trivial
- Class-level docstrings describe purpose; attribute docstrings use `Attributes:` section in Pydantic models

**Example docstring (from `src/trac_mcp_server/core/client.py`):**
```python
def create_ticket(self, summary: str, description: str,
                  ticket_type: str | None = None,
                  attributes: Optional[Dict[str, Any]] = None,
                  notify: bool = False) -> int:
    """
    Create a new ticket in Trac.

    Args:
        summary: Ticket title (required)
        description: Ticket body with WikiFormatting (required)
        ticket_type: Ticket type string. If None, uses default.
        attributes: Optional fields (priority, milestone, component, owner, cc, keywords)
        notify: Send email notifications

    Returns:
        Ticket ID (int)

    Raises:
        ValueError: If summary or description is empty
        xmlrpc.client.Fault: If server validation fails or permissions denied
    """
```

**Section dividers (from test files):**
```python
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
```

## Function Design

**Size:** Functions range from 3-50 lines. Larger tool handlers decompose into private `_handle_*` functions.

**Parameters:**
- Use keyword arguments with defaults for optional params: `max_results: int = 10`, `version: Optional[int] = None`
- Group optional fields into a single `dict` parameter: `attributes: Optional[Dict[str, Any]] = None`
- Tool handler signature pattern: `async def handler(name: str, arguments: dict | None, client: TracClient)`

**Return Values:**
- Validation functions return `Tuple[bool, str]` -- `(is_valid, error_message)`
- Client methods return typed values: `List[str]`, `Dict[str, Any]`, `int`, `bool`
- MCP tool handlers return `list[types.TextContent]` or `types.CallToolResult`
- Use `typing.cast()` for XML-RPC response type narrowing (see `src/trac_mcp_server/core/client.py`)

**Async bridging pattern:**
```python
# Wrap synchronous TracClient calls for async MCP handlers
result = await run_sync(client.get_ticket, ticket_id)           # unbounded
result = await run_sync_limited(client.get_ticket, tid)         # semaphore-bounded
results = await gather_limited([_fetch(tid) for tid in ids])    # parallel bounded
```

## Module Design

**Exports:**
- Every `__init__.py` declares `__all__` with explicit exports
- Tool modules export two items: constant list + handler function (e.g., `TICKET_READ_TOOLS`, `handle_ticket_read_tool`)
- Barrel pattern in `src/trac_mcp_server/mcp/tools/__init__.py` aggregates all tool modules

**Barrel Files:**
- `src/trac_mcp_server/converters/__init__.py` -- re-exports all converter functions
- `src/trac_mcp_server/mcp/tools/__init__.py` -- combines read/write tools into `TICKET_TOOLS`, `WIKI_TOOLS`
- `src/trac_mcp_server/core/__init__.py` -- empty, package marker only

**Module organization pattern:**
- Domain split by read/write: `ticket_read.py` + `ticket_write.py`, `wiki_read.py` + `wiki_write.py`
- Shared error handling in `errors.py`
- Configuration: `config.py` (runtime), `config_schema.py` (Pydantic validation), `config_loader.py` (YAML loading)
- Sync subsystem: `sync/engine.py`, `sync/mapper.py`, `sync/resolver.py`, `sync/state.py`, `sync/models.py`, `sync/merger.py`, `sync/reporter.py`

---

*Convention analysis: 2026-02-14*
