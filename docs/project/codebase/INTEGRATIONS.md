# External Integrations

**Analysis Date:** 2026-02-14

## APIs & External Services

**Trac XML-RPC API (primary integration):**
- The entire server exists to bridge MCP clients to Trac via XML-RPC
- SDK/Client: Custom `TracClient` class - `src/trac_mcp_server/core/client.py`
- Protocol: XML-RPC over HTTP/HTTPS (payloads built with `xmlrpc.client.dumps()`, parsed with `xml.etree.ElementTree`)
- Endpoint: `{TRAC_URL}/login/rpc`
- Auth: HTTP Basic Authentication via `requests.Session`
- Transport: `requests` library with thread-local sessions for thread safety
- SSL: Configurable verification (`config.insecure` flag)
- Concurrency: Bounded by `asyncio.Semaphore` initialized at startup (`src/trac_mcp_server/core/async_utils.py`)

**Trac XML-RPC Namespaces Used:**
- `ticket.*` - search, get, create, update, delete, changeLog, getActions, getTicketFields (`src/trac_mcp_server/core/client.py` lines 93-646)
- `wiki.*` - getAllPages, getPage, getPageVersion, getPageInfo, getPageHTML, putPage, deletePage, getRecentChanges (`src/trac_mcp_server/core/client.py` lines 221-544)
- `ticket.milestone.*` - getAll, get, create, update, delete (`src/trac_mcp_server/core/client.py` lines 548-613)
- `system.*` - getAPIVersion, listMethods (`src/trac_mcp_server/core/client.py` lines 111-123)

**Trac Web Scraping (secondary, capability detection):**
- Scrapes `/about` page for Trac version and plugin info
- SDK/Client: `requests.get()` with `lxml.html.fromstring()` - `src/trac_mcp_server/detection/web_scraper.py`
- Auth: HTTP Basic Authentication
- Purpose: Detect Trac version, installed plugins, markdown processor availability
- Fallback: Graceful degradation if scraping fails (returns empty dict)

**MCP Protocol (served):**
- Server implements Model Context Protocol over stdio transport
- Protocol: JSON-RPC 2.0 over stdin/stdout
- SDK: `mcp` Python package (`mcp.server.Server`, `mcp.server.stdio`)
- Entry point: `src/trac_mcp_server/mcp/server.py`
- Designed for: Claude Desktop, Claude Code, and other MCP-compatible clients

**MCP Tools Exposed (26 total):**
- `ping` - Connection test (`src/trac_mcp_server/mcp/server.py`)
- `get_server_time` - Server timestamp (`src/trac_mcp_server/mcp/tools/system.py`)
- `ticket_search`, `ticket_get`, `ticket_changelog`, `ticket_fields`, `ticket_actions` - Read ops (`src/trac_mcp_server/mcp/tools/ticket_read.py`)
- `ticket_create`, `ticket_update`, `ticket_delete` - Write ops (`src/trac_mcp_server/mcp/tools/ticket_write.py`)
- `wiki_get`, `wiki_search`, `wiki_recent_changes` - Read ops (`src/trac_mcp_server/mcp/tools/wiki_read.py`)
- `wiki_create`, `wiki_update` - Write ops (`src/trac_mcp_server/mcp/tools/wiki_write.py`)
- `wiki_file_read`, `wiki_file_convert`, `wiki_file_push` - File operations (`src/trac_mcp_server/mcp/tools/wiki_file.py`)
- `milestone_list`, `milestone_get`, `milestone_create`, `milestone_update`, `milestone_delete` - Milestones (`src/trac_mcp_server/mcp/tools/milestone.py`)
- `doc_sync_*` - Bidirectional sync tools (`src/trac_mcp_server/mcp/tools/sync.py`)

**MCP Resources Exposed:**
- `trac://wiki/{page_name}` - Read wiki pages with format/version options (`src/trac_mcp_server/mcp/resources/wiki.py`)
- `trac://wiki/_index` - List all wiki pages with tree structure

## Data Storage

**Databases:**
- None. All data is stored in the remote Trac server (accessed via XML-RPC).
- No local database required.

**File Storage (local):**
- Sync state files: `.trac_assist/sync_{profile_name}.json` - JSON files tracking per-path sync metadata (`src/trac_mcp_server/sync/state.py`)
  - Atomic writes via `os.replace()` for crash safety
  - Content: version info, SHA-256 content hashes, timestamps, conflict markers
- Capability cache: `.trac_assist/capabilities.json` - 24-hour TTL cache of Trac server capabilities (`src/trac_mcp_server/detection/capabilities.py`)
- Log files: `/tmp/trac-mcp-server.log` (default) or custom path via `--log-file` CLI arg (`src/trac_mcp_server/logger.py`)
- Config files: `.trac_assist/config.yml` or `~/.config/trac_assist/config.yml` (YAML) (`src/trac_mcp_server/config_loader.py`)

**Caching:**
- Capability detection results cached to local JSON file with 24-hour expiry (`src/trac_mcp_server/detection/capabilities.py` line 29)
- No in-memory caching of Trac data (all requests go to server)

## Authentication & Identity

**Auth Provider:**
- Trac server's built-in HTTP Basic Authentication
  - Implementation: `requests.Session.auth = (username, password)` in `src/trac_mcp_server/core/client.py` line 34
  - Credentials source: `TRAC_URL`, `TRAC_USERNAME`, `TRAC_PASSWORD` env vars or CLI args
  - No token refresh, no OAuth, no session management beyond HTTP Basic

**MCP Client Authentication:**
- None. The MCP server trusts the stdio transport (local process).
- MCP client connects via stdin/stdout (no network auth needed).

## Monitoring & Observability

**Error Tracking:**
- No external error tracking service (no Sentry, Bugsnag, etc.)
- Errors logged to file and returned as structured MCP error responses

**Logs:**
- Python `logging` module with two modes (`src/trac_mcp_server/logger.py`):
  - **MCP mode**: File-only logging (never stdout, to protect JSON-RPC transport)
  - **CLI mode**: stderr logging with optional file handler
- Format: `[%(asctime)s] [%(levelname)s] %(message)s`
- Optional JSON structured logging via `JsonFormatter` class (`src/trac_mcp_server/logger.py` lines 7-23)
- Third-party lib silencing: urllib3, httpx, httpcore set to WARNING unless DEBUG (`src/trac_mcp_server/logger.py` lines 96-99)
- Default log file: `/tmp/trac-mcp-server.log`

**Health Check:**
- `ping` MCP tool validates Trac connectivity and returns API version (`src/trac_mcp_server/mcp/server.py` lines 157-168)
- Connection validation at startup via `client.validate_connection()` in lifespan (`src/trac_mcp_server/mcp/lifespan.py` lines 73-74)
- Version consistency check at startup for stale PyInstaller binaries (`src/trac_mcp_server/version.py`)

## CI/CD & Deployment

**Hosting:**
- Local process (stdio transport) - designed to run as a subprocess of MCP clients (Claude Desktop, Claude Code)
- No web server deployment (stdio only, not HTTP)

**CI Pipeline:**
- Not detected. No `.github/workflows/`, no `.gitlab-ci.yml`, no `Jenkinsfile` found.

**Distribution Methods:**
- pip install from source: `pip install -e ".[dev]"`
- Entry point script: `trac-mcp-server` (installed via `pyproject.toml` `[project.scripts]`)
- PyInstaller binary: mentioned in version check (`src/trac_mcp_server/version.py` line 52)
- Package module: `python -m trac_mcp_server.mcp` (`src/trac_mcp_server/mcp/__main__.py`)

## Environment Configuration

**Required env vars:**
- `TRAC_URL` - Full URL to Trac instance (e.g., `https://trac.example.com/trac`)
- `TRAC_USERNAME` - Trac login username
- `TRAC_PASSWORD` - Trac login password

**Optional env vars:**
- `TRAC_INSECURE` - Set to `true`/`1`/`yes`/`on` to skip SSL verification
- `TRAC_DEBUG` - Enable debug logging
- `TRAC_MAX_PARALLEL_REQUESTS` - Max concurrent XML-RPC requests (default: 5)
- `LOG_LEVEL` - Override log level (DEBUG, INFO, WARNING, ERROR)
- `LOG_FILE` - Custom log file path
- `TRAC_ASSIST_CONFIG` - Explicit path to YAML config file

**Secrets location:**
- Environment variables (recommended) or `.env` file (gitignored)
- YAML config files support `${VAR}` and `${VAR:-default}` interpolation for secrets (`src/trac_mcp_server/config_loader.py` lines 28-49)
- No secrets management service integration (no Vault, AWS Secrets Manager, etc.)

**`.env` file:**
- Loaded via `python-dotenv` in `src/trac_mcp_server/config.py` line 90: `load_dotenv()`
- `.env` is in `.gitignore`
- No `.env.example` file detected

## Webhooks & Callbacks

**Incoming:**
- None. The server does not expose HTTP endpoints.
- Communication is via stdio transport only (stdin/stdout JSON-RPC).

**Outgoing:**
- None. The server does not send webhooks.
- All communication with Trac is synchronous request/response via XML-RPC.

## Integration Architecture Summary

```
MCP Client (Claude Desktop/Code)
    |
    | stdio (JSON-RPC 2.0)
    v
trac-mcp-server (Python process)
    |
    | HTTP/HTTPS (XML-RPC)
    v
Trac Server (with XML-RPC plugin)
```

**Key architectural note:** The server bridges async MCP protocol to synchronous XML-RPC calls using `asyncio.to_thread()` with a semaphore-bounded thread pool (`src/trac_mcp_server/core/async_utils.py`). Each XML-RPC call uses a thread-local `requests.Session` for connection pooling (`src/trac_mcp_server/core/client.py` lines 14, 26-29).

---

*Integration audit: 2026-02-14*
