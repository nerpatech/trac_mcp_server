"""Shared pytest fixtures for trac-mcp-server tests."""

from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv

from trac_mcp_server.config import Config

load_dotenv()


def pytest_addoption(parser):
    """Add custom CLI options for test filtering."""
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run tests that require a live Trac instance",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "live: mark test as requiring a live Trac instance"
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless --run-live is passed."""
    if config.getoption("--run-live"):
        # --run-live given: do not skip live tests
        return
    skip_live = pytest.mark.skip(reason="need --run-live option to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def mock_config():
    """Create a mock Config instance for testing."""
    return Config(
        trac_url="https://trac.example.com/trac",
        username="testuser",
        password="testpass",
        insecure=False,
    )


@pytest.fixture
def mock_trac_client(mock_config):
    """Create a mock TracClient instance for testing."""
    from trac_mcp_server.core.client import TracClient

    client = MagicMock(spec=TracClient)
    client.config = mock_config
    return client


@pytest.fixture
def mock_xml_response():
    """Factory fixture for creating XML-RPC response mocks."""

    def _create_response(content):
        """Create a mock response with given XML content."""
        from unittest.mock import Mock

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = (
            content.encode() if isinstance(content, str) else content
        )
        return mock_response

    return _create_response
