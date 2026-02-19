# Technology Stack

**Analysis Date:** 2026-02-14

## Languages

**Primary:**
- Python 3.12 (runtime observed), requires `>=3.10` - `pyproject.toml` line 13
- All source code is Python (`.py` files exclusively)

**Secondary:**
- XML (XML-RPC protocol payloads built/parsed in `src/trac_mcp_server/core/client.py`)
- YAML (hierarchical config files parsed via PyYAML in `src/trac_mcp_server/config_loader.py`)
- JSON (sync state persistence in `src/trac_mcp_server/sync/state.py`, capability caching in `src/trac_mcp_server/detection/capabilities.py`)

## Runtime

**Environment:**
- Python 3.12.8 (current runtime)
- Minimum: Python 3.10 (`pyproject.toml` `requires-python = ">=3.10"`)
- Uses `asyncio` event loop with `asyncio.to_thread()` for sync-to-async bridging (`src/trac_mcp_server/core/async_utils.py`)
- `tomllib` (stdlib 3.11+) used for TOML parsing with `tomli` fallback for 3.10 (`src/trac_mcp_server/mcp/server.py` lines 253-256)

**Package Manager:**
- pip with setuptools build backend (`pyproject.toml` line 2: `requires = ["setuptools>=61.0"]`)
- Lockfile: **missing** - no `requirements.lock`, `poetry.lock`, `uv.lock`, or `Pipfile.lock` detected
- Virtual environment: `.venv/` directory present

## Frameworks

**Core:**
- MCP SDK `>=1.26.0,<2.0.0` (`mcp[cli]`) - Model Context Protocol server framework - `pyproject.toml` line 18
  - Provides: `mcp.server.Server`, `mcp.server.stdio`, `mcp.types`, `mcp.server.models`
  - Transport: stdio (JSON-RPC 2.0)
  - Transitive deps: pydantic, httpx, starlette, uvicorn, anyio, jsonschema
- Pydantic (via MCP SDK) - Data validation and schema models - `src/trac_mcp_server/config_schema.py`, `src/trac_mcp_server/sync/models.py`

**Testing:**
- pytest `>=8.0.0` - Test runner - `pyproject.toml` line 28
- pytest-asyncio `>=0.23.0` - Async test support - `pyproject.toml` line 29
- unittest.mock (stdlib) - Mocking framework - `tests/conftest.py`

**Build/Dev:**
- setuptools `>=61.0` - Build backend - `pyproject.toml` line 2
- Entry point: `trac-mcp-server = "trac_mcp_server.mcp.server:run"` - `pyproject.toml` line 33
- PyInstaller support mentioned in `src/trac_mcp_server/version.py` (version consistency check for stale binaries)

## Key Dependencies

**Critical (declared in `pyproject.toml`):**
- `mcp[cli]>=1.26.0,<2.0.0` - MCP protocol server implementation; the entire server architecture depends on this
- `requests` - HTTP client for XML-RPC communication with Trac server (`src/trac_mcp_server/core/client.py`)
- `mistune>=3.0.0` - Markdown parser/renderer for Markdown-to-TracWiki conversion (`src/trac_mcp_server/converters/markdown_to_tracwiki.py`)
- `lxml>=5.0.0` - HTML parsing for web scraping Trac `/about` page (`src/trac_mcp_server/detection/web_scraper.py`)
- `merge3>=0.0.15` - Three-way merge algorithm for sync conflict resolution (`src/trac_mcp_server/sync/merger.py`)
- `PyYAML>=6.0` - YAML config file parsing (`src/trac_mcp_server/config_loader.py`)
- `python-dotenv` - `.env` file loading (`src/trac_mcp_server/config.py` line 19)
- `anyio>=4.0` - Async I/O abstraction (used by MCP SDK)
- `cssselect>=1.2.0` - CSS selector support for lxml HTML parsing

**Transitive (via MCP SDK, not declared):**
- `pydantic` - Used directly for config schema and sync models
- `pydantic-core` - `Url` type used in `src/trac_mcp_server/mcp/server.py` and `src/trac_mcp_server/mcp/resources/wiki.py`
- `charset-normalizer` (via requests) - Used directly for file encoding detection in `src/trac_mcp_server/file_handler.py`
- `httpx`, `starlette`, `uvicorn` - Transitive MCP SDK deps (not used directly)

**Standard Library (notable usage):**
- `xmlrpc.client` - XML-RPC payload serialization/deserialization (`src/trac_mcp_server/core/client.py`)
- `xml.etree.ElementTree` - XML response parsing (`src/trac_mcp_server/core/client.py`)
- `asyncio` - Event loop and thread pool (`src/trac_mcp_server/core/async_utils.py`)
- `threading` - Thread-local session storage (`src/trac_mcp_server/core/client.py`)
- `hashlib` - SHA-256 content hashing for sync state (`src/trac_mcp_server/sync/state.py`)
- `difflib` - Unified diff generation (`src/trac_mcp_server/sync/merger.py`)
- `subprocess` - Git status check for sync safety (`src/trac_mcp_server/sync/engine.py`)
- `argparse` - CLI argument parsing (`src/trac_mcp_server/mcp/server.py`)

## Configuration

**Environment Variables (primary method):**
- `TRAC_URL` - Trac instance URL (required) - `src/trac_mcp_server/config.py`
- `TRAC_USERNAME` - Trac username (required) - `src/trac_mcp_server/config.py`
- `TRAC_PASSWORD` - Trac password (required) - `src/trac_mcp_server/config.py`
- `TRAC_INSECURE` - Skip SSL verification (optional, default: false) - `src/trac_mcp_server/config.py`
- `TRAC_DEBUG` - Enable debug logging (optional, default: false) - `src/trac_mcp_server/config.py`
- `TRAC_MAX_PARALLEL_REQUESTS` - Concurrency limit (optional, default: 5) - `src/trac_mcp_server/config.py`
- `LOG_LEVEL` - Logging level (optional) - `src/trac_mcp_server/logger.py`
- `LOG_FILE` - Log file path (optional, default: `/tmp/trac-mcp-server.log`) - `src/trac_mcp_server/logger.py`

**Configuration Priority (highest to lowest):**
1. CLI arguments (`--url`, `--username`, `--password`, `--insecure`, `--log-file`)
2. Environment variables (incl. `.env` file via python-dotenv)
3. YAML config files (hierarchical, via `src/trac_mcp_server/config_loader.py`)

**YAML Config Discovery Order** (`src/trac_mcp_server/config_loader.py`):
1. `TRAC_ASSIST_CONFIG` env var (explicit path)
2. `.trac_assist/config.yml` in CWD
3. `.trac_assist/config.yaml` in CWD
4. `~/.config/trac_assist/config.yml` (XDG)
5. `~/.trac_assist/config.yaml` (legacy)

**Build Configuration:**
- `pyproject.toml` - Package metadata, dependencies, build system, pytest config
- `.gitignore` - Standard Python gitignore

**Pytest Configuration** (in `pyproject.toml`):
- Test paths: `tests/`
- File pattern: `test_*.py`
- Function pattern: `test_*`
- Async mode: `auto` (pytest-asyncio)

## Platform Requirements

**Development:**
- Python 3.10+ (3.12 recommended)
- pip with virtualenv (`.venv/` convention)
- Install: `pip install -e ".[dev]"`
- Access to a Trac instance with XML-RPC plugin enabled (for live testing)

**Production:**
- Python 3.10+ runtime
- Network access to Trac server (HTTP/HTTPS)
- Trac server must have XML-RPC plugin enabled (`/login/rpc` endpoint)
- stdio transport (designed for Claude Desktop/Code integration)
- Optional: PyInstaller binary distribution (version consistency check in `src/trac_mcp_server/version.py`)

**No containerization detected** - No Dockerfile, docker-compose, or Makefile present.

---

*Stack analysis: 2026-02-14*
