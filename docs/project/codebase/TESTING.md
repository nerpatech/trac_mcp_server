# Testing Patterns

**Analysis Date:** 2026-02-14

## Test Framework

**Runner:**
- pytest >= 8.0.0
- Config: `pyproject.toml` `[tool.pytest.ini_options]` section

**Async Support:**
- pytest-asyncio >= 0.23.0
- `asyncio_mode = "auto"` (auto-detects async tests without `@pytest.mark.asyncio`)
- `asyncio_default_fixture_loop_scope = "function"` (new event loop per test)

**Assertion Library:**
- pytest native `assert` statements (most tests)
- `unittest.TestCase` assertion methods (`self.assertEqual`, `self.assertIn`, `self.assertRaises`) in older/conversion tests

**Run Commands:**
```bash
pytest                           # Run all tests
pytest tests/test_client.py      # Run specific test file
pytest -k "test_push"            # Run by keyword
pytest --run-live                # Include live Trac integration tests
pytest -v                        # Verbose output
```

## Test File Organization

**Location:**
- Separate `tests/` directory at project root (not co-located with source)
- Source: `src/trac_mcp_server/`
- Tests: `tests/`

**Naming:**
- Pattern: `test_<module_or_feature>.py`
- Examples: `tests/test_client.py` tests `src/trac_mcp_server/core/client.py`
- `tests/test_converter.py` tests `src/trac_mcp_server/converters/`
- `tests/test_sync_engine.py` tests `src/trac_mcp_server/sync/engine.py`

**Structure:**
```
tests/
├── __init__.py
├── conftest.py                          # Shared fixtures
├── test_client.py                       # Core TracClient tests
├── test_config_loader.py                # Config YAML loading tests
├── test_config_schema.py                # Pydantic config validation tests
├── test_config_schema_sync.py           # Sync profile config tests
├── test_converter.py                    # Markdown <-> TracWiki conversion
├── test_detection.py                    # Capability detection tests
├── test_file_handler.py                 # File handler tests
├── test_mcp_resources.py                # MCP resource handler tests
├── test_sync_engine.py                  # Sync engine core tests
├── test_sync_integration.py             # Sync end-to-end integration tests
├── test_sync_mapper.py                  # Path mapper tests
├── test_sync_reporter.py                # Sync report formatting tests
├── test_sync_resolver.py                # Conflict resolver tests
├── test_sync_state.py                   # State persistence tests
├── test_sync_tools.py                   # Sync MCP tool handler tests
├── test_wiki_file_integration.py        # Wiki file attachment integration
├── test_wiki_file_tools.py              # Wiki file MCP tool tests
├── test_wiki_resources.py               # Wiki resource handler tests
├── test_mcp/                            # MCP server tool tests (subdirectory)
│   ├── __init__.py
│   ├── test_server_milestone_tools.py   # Milestone tool handler tests
│   ├── test_server_wiki_tools.py        # Wiki tool handler tests (legacy)
│   └── tools/
│       ├── __init__.py
│       ├── test_system.py               # System tool tests
│       ├── test_ticket.py               # Ticket tool handler tests
│       └── test_wiki.py                 # Wiki tool handler tests
```

## Test Structure

**Two styles coexist:**

**Style 1: pytest classes (preferred for new code)**
```python
class TestDryRun:
    """Dry-run should produce a report without executing changes."""

    def test_dry_run_no_changes(self, tmp_path: Path) -> None:
        """Dry run with local file but no remote produces CREATE_REMOTE."""
        engine, client = _setup_engine(
            tmp_path,
            local_files={"readme.md": "# Hello\n"},
        )
        report = engine.run(dry_run=True)
        assert report.dry_run is True
        assert len(report.results) == 1
        assert report.results[0].action == SyncAction.CREATE_REMOTE
```
- Used in: `tests/test_sync_engine.py`, `tests/test_sync_mapper.py`, `tests/test_sync_state.py`, `tests/test_detection.py`
- Plain classes (no `unittest.TestCase` inheritance)
- Use pytest `tmp_path` fixture directly as parameter
- Use bare `assert` statements

**Style 2: unittest.TestCase classes (older tests)**
```python
class TestTracWikiConverter(unittest.TestCase):
    """Test Markdown to TracWiki conversion."""

    def test_heading_level_1(self):
        """Test H1 heading conversion."""
        result = markdown_to_tracwiki("# Heading 1")
        self.assertEqual(result, "= Heading 1 =")
```
- Used in: `tests/test_converter.py`, `tests/test_mcp/tools/test_wiki.py`, `tests/test_mcp/tools/test_ticket.py`, `tests/test_mcp_resources.py`
- Uses `self.assertEqual`, `self.assertIn`, `self.assertRaises`
- Async tests use `asyncio.run()` wrapper: `result = asyncio.run(handler(...))`

**Style 3: Top-level functions (minimal tests)**
```python
def test_rpc_url_construction(mock_config):
    """Test that RPC URL is constructed correctly."""
    client = TracClient(mock_config)
    assert client.rpc_url == "https://trac.example.com/trac/login/rpc"
```
- Used in: `tests/test_client.py`
- Uses conftest fixtures as function parameters

**Convention: Use pytest classes (Style 1) for new tests.** Group related tests in a class with a descriptive docstring. Use bare `assert` with pytest, not `unittest.TestCase` methods.

## Mocking

**Framework:** `unittest.mock` (standard library)

**Common mock imports:**
```python
from unittest.mock import MagicMock, Mock, patch, AsyncMock
```

**Pattern 1: Decorator-based patching (TracClient HTTP layer)**
```python
@patch('trac_mcp_server.core.client.requests.Session.post')
def test_search_tickets_success(mock_post, mock_config):
    """Test search_tickets method with successful response."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b'''<?xml version="1.0"?>
    <methodResponse>...</methodResponse>'''
    mock_post.return_value = mock_response

    client = TracClient(mock_config)
    result = client.search_tickets("status=new")
    assert result == [1, 2, 3]
```
- Used extensively in `tests/test_client.py`
- Patches `requests.Session.post` to intercept XML-RPC calls
- Mock responses contain actual XML-RPC response XML

**Pattern 2: Fake objects (sync engine tests)**
```python
class FakeTracClient:
    """Minimal TracClient replacement for testing."""
    def __init__(self, pages=None, versions=None):
        self.pages = pages or {}
        self.versions = versions or {}
        self.put_calls = []

    def get_wiki_page(self, page_name, version=None):
        if page_name not in self.pages:
            raise Fault(1, f"Page '{page_name}' not found")
        return self.pages[page_name]
```
- Used in: `tests/test_sync_engine.py`, `tests/test_sync_integration.py`
- In-memory dict simulates wiki page storage
- Tracks method calls via `put_calls` list

**Pattern 3: Context manager patching (for `run_sync`)**
```python
with patch("trac_mcp_server.mcp.tools.ticket_write.run_sync") as mock_run_sync:
    mock_run_sync.return_value = True
    result = asyncio.run(_handle_delete(self.mock_client, {"ticket_id": 42}))
```

**Pattern 4: Mock with spec for type safety**
```python
client = MagicMock(spec=TracClient)
client.config = mock_config
```
- Used in `tests/conftest.py` for `mock_trac_client` fixture

**What to Mock:**
- HTTP layer (`requests.Session.post`) for TracClient unit tests
- `run_sync` for async MCP handler tests
- `subprocess.run` for git safety checks in sync tests
- External services (web scraper HTTP calls)

**What NOT to Mock:**
- Pydantic model validation (test real validation)
- Pure functions (converters, reconciler, validators)
- File I/O in integration tests (use `tmp_path` fixture instead)

## Fixtures and Factories

**Shared fixtures (`tests/conftest.py`):**
```python
@pytest.fixture
def mock_config():
    """Create a mock Config instance for testing."""
    return Config(
        trac_url="https://trac.example.com/trac",
        username="testuser",
        password="testpass",
        insecure=False
    )

@pytest.fixture
def mock_trac_client(mock_config):
    """Create a mock TracClient instance for testing."""
    client = MagicMock(spec=TracClient)
    client.config = mock_config
    return client

@pytest.fixture
def mock_xml_response():
    """Factory fixture for creating XML-RPC response mocks."""
    def _create_response(content):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = content.encode() if isinstance(content, str) else content
        return mock_response
    return _create_response
```

**Test-local helper factories (in test files):**
```python
def _make_profile(**overrides) -> SyncProfileConfig:
    """Build a minimal SyncProfileConfig for testing."""
    defaults = {
        "source": "docs/",
        "destination": "Docs",
        "format": "auto",
        "direction": "bidirectional",
        "conflict_strategy": "local-wins",
        "git_safety": "none",
        "mappings": [],
        "exclude": [],
    }
    defaults.update(overrides)
    return SyncProfileConfig(**defaults)

def _setup_engine(tmp_path, profile_overrides=None, client=None, local_files=None, state_entries=None):
    """Create a SyncEngine with a temp directory and mock client."""
    ...
    return engine, fake_client
```
- Pattern: `_make_*` for creating config/model objects
- Pattern: `_setup_*` for creating full test harnesses

**Location:**
- Shared fixtures: `tests/conftest.py`
- Test-local helpers: top of individual test files, before test classes

## Coverage

**Requirements:** No coverage target enforced (no `[tool.coverage]` or `--cov` in config)

**View Coverage:**
```bash
pip install pytest-cov
pytest --cov=trac_mcp_server --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Scope: Individual functions and classes in isolation
- Files: `tests/test_client.py`, `tests/test_converter.py`, `tests/test_sync_mapper.py`, `tests/test_sync_state.py`, `tests/test_sync_resolver.py`
- Mock external dependencies (HTTP, filesystem in some cases)
- Pure function tests for converters and reconciler use no mocks

**Integration Tests:**
- Scope: Multiple modules interacting together
- Files: `tests/test_sync_integration.py`, `tests/test_sync_engine.py`, `tests/test_wiki_file_integration.py`
- Use `FakeTracClient` (in-memory) + real filesystem (`tmp_path`)
- Test full sync cycles including state persistence

**Live Integration Tests (gated):**
- Marker: `@pytest.mark.live`
- Enabled with: `pytest --run-live`
- Require a real Trac instance
- Configured in `tests/conftest.py` via `pytest_addoption` and `pytest_collection_modifyitems`
- Skipped by default: `skip_live = pytest.mark.skip(reason="need --run-live option to run")`

**E2E Tests:**
- Not present as a separate category
- Live integration tests serve as the closest equivalent

## Common Patterns

**Async Testing:**
```python
# Style 1: asyncio.run() in unittest.TestCase (older pattern)
def test_handle_delete_success(self):
    with patch("trac_mcp_server.mcp.tools.ticket_write.run_sync") as mock_run_sync:
        mock_run_sync.return_value = True
        result = asyncio.run(_handle_delete(self.mock_client, {"ticket_id": 42}))
    self.assertEqual(len(result), 1)

# Style 2: pytest-asyncio auto mode (preferred for new code)
# Any async def test function is automatically run as async
# asyncio_mode = "auto" in pyproject.toml means no @pytest.mark.asyncio needed
```

**Error Testing:**
```python
# pytest.raises (preferred)
with pytest.raises(ValueError) as exc_info:
    client.create_ticket("", "Test description")
assert "Summary is required" in str(exc_info.value)

# unittest assertRaises (older tests)
with self.assertRaises(ValueError):
    decode_cursor("not-valid-base64")
```

**XML-RPC Response Mocking:**
```python
# Create mock HTTP response with XML-RPC payload
mock_response = Mock()
mock_response.status_code = 200
mock_response.content = b'''<?xml version="1.0"?>
<methodResponse>
  <params>
    <param>
      <value><int>42</int></value>
    </param>
  </params>
</methodResponse>'''
mock_post.return_value = mock_response
```

**Sequential mock responses (for multi-call operations):**
```python
# Use side_effect for ordered responses
mock_post.side_effect = [get_response, update_response]

# First call returns get_response, second returns update_response
client.update_ticket(42, attributes={"status": "accepted"})
assert mock_post.call_count == 2
```

**Filesystem tests with tmp_path:**
```python
class TestSyncStateSave:
    def test_save_creates_file(self, tmp_path: Path):
        state_dir = tmp_path / ".trac_assist"
        ss = SyncState(state_dir)
        state = ss.load("demo")
        ss.save("demo", state)
        path = state_dir / "sync_demo.json"
        assert path.exists()
```

**Verifying RPC call payloads:**
```python
# After calling client method, inspect the mock call
mock_post.assert_called_once()
payload = mock_post.call_args[1]['data']
assert 'ticket.create' in payload
assert 'Test ticket' in payload
```

**Test class organization by behavior:**
```python
class TestDryRun:
    """Dry-run should produce a report without executing changes."""

class TestPushFlow:
    """Test pushing local changes to remote."""

class TestPullFlow:
    """Test pulling remote changes to local."""

class TestConflictDelegation:
    """Test that conflicts are delegated to the resolver."""
```

**Test docstring convention:**
- Every test method has a one-line docstring describing what it tests
- Class docstrings describe the category of behavior being tested
- Example: `"""Test _handle_delete handles permission denied with specific error message."""`

---

*Testing analysis: 2026-02-14*
