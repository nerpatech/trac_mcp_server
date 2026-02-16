"""Tests for trac_mcp_server.mcp.lifespan — server startup/shutdown lifecycle.

Tests the server_lifespan() async context manager which:
- Loads config from YAML config files or env vars (with optional CLI overrides)
- Creates TracClient and validates connection
- Initializes concurrency semaphore
- Fails fast on config errors or connection failures
- Prints status messages to stderr
"""

from unittest.mock import MagicMock, patch

import pytest

from trac_mcp_server.config import Config
from trac_mcp_server.mcp.lifespan import server_lifespan

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

# Shorthand for patching discover_config_files to return no files
_NO_CONFIG_FILES = patch(
    "trac_mcp_server.mcp.lifespan.discover_config_files", return_value=[]
)


def _make_config(**overrides):
    """Create a valid Config for testing."""
    defaults = {
        "trac_url": "https://trac.example.com/trac",
        "username": "testuser",
        "password": "testpass",
        "insecure": False,
        "debug": False,
        "max_parallel_requests": 5,
    }
    defaults.update(overrides)
    return Config(**defaults)


# -------------------------------------------------------------------------
# server_lifespan() — successful startup (env var path)
# -------------------------------------------------------------------------


class TestServerLifespanSuccess:
    """Tests for the happy path through server_lifespan()."""

    async def test_successful_startup(self):
        mock_client = MagicMock()
        config = _make_config()

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ) as mock_run_sync,
            patch(
                "trac_mcp_server.mcp.lifespan.init_semaphore"
            ) as mock_init_sem,
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            async with server_lifespan() as ctx:
                assert ctx["client"] is mock_client
                mock_run_sync.assert_called_once_with(
                    mock_client.validate_connection
                )
                mock_init_sem.assert_called_once_with(5)

    async def test_semaphore_uses_max_parallel_from_config(self):
        mock_client = MagicMock()
        config = _make_config(max_parallel_requests=12)

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.init_semaphore"
            ) as mock_init_sem,
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            async with server_lifespan() as _:
                mock_init_sem.assert_called_once_with(12)

    async def test_startup_with_config_overrides(self):
        mock_client = MagicMock()
        config = _make_config()
        overrides = {
            "url": "http://test",
            "username": "u",
            "password": "p",
            "insecure": True,
        }

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ) as mock_load,
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            async with server_lifespan(config_overrides=overrides) as _:
                mock_load.assert_called_once_with(
                    url="http://test",
                    username="u",
                    password="p",
                    insecure=True,
                )

    async def test_startup_without_overrides_calls_load_config_bare(
        self,
    ):
        mock_client = MagicMock()
        config = _make_config()

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ) as mock_load,
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            async with server_lifespan() as _:
                mock_load.assert_called_once_with()


# -------------------------------------------------------------------------
# server_lifespan() — YAML config file path
# -------------------------------------------------------------------------


class TestServerLifespanYamlConfig:
    """Tests for loading config from .trac_mcp/config.yml."""

    async def test_yaml_config_used_when_file_exists(self, tmp_path):
        """When a YAML config file exists, lifespan uses config_loader pipeline."""
        # Create a config file in tmp_path
        config_dir = tmp_path / ".trac_mcp"
        config_dir.mkdir()
        config_file = config_dir / "config.yml"
        config_file.write_text(
            "trac:\n"
            "  url: https://yaml-trac.example.com\n"
            "  username: yamluser\n"
            "  password: yamlpass\n"
        )

        mock_client = MagicMock()

        with (
            patch(
                "trac_mcp_server.mcp.lifespan.discover_config_files",
                return_value=[config_file],
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.load_hierarchical_config",
                return_value={
                    "trac": {
                        "url": "https://yaml-trac.example.com",
                        "username": "yamluser",
                        "password": "yamlpass",
                    }
                },
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            async with server_lifespan() as ctx:
                assert ctx["client"] is mock_client

    async def test_yaml_config_values_used(self, tmp_path):
        """Verify that values from YAML config end up in the Config object."""
        config_dir = tmp_path / ".trac_mcp"
        config_dir.mkdir()
        config_file = config_dir / "config.yml"
        config_file.write_text(
            "trac:\n"
            "  url: https://yaml-trac.example.com\n"
            "  username: yamluser\n"
            "  password: yamlpass\n"
            "  max_parallel_requests: 3\n"
        )

        mock_client = MagicMock()
        captured_config = {}

        def capture_client(config):
            captured_config["config"] = config
            return mock_client

        with (
            patch(
                "trac_mcp_server.mcp.lifespan.discover_config_files",
                return_value=[config_file],
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.load_hierarchical_config",
                return_value={
                    "trac": {
                        "url": "https://yaml-trac.example.com",
                        "username": "yamluser",
                        "password": "yamlpass",
                        "max_parallel_requests": 3,
                    }
                },
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                side_effect=capture_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            async with server_lifespan() as _:
                pass

        config = captured_config["config"]
        assert config.trac_url == "https://yaml-trac.example.com"
        assert config.username == "yamluser"
        assert config.password == "yamlpass"
        assert config.max_parallel_requests == 3

    async def test_yaml_config_with_cli_overrides(self, tmp_path):
        """CLI overrides take precedence over YAML config values."""
        config_dir = tmp_path / ".trac_mcp"
        config_dir.mkdir()
        config_file = config_dir / "config.yml"
        config_file.write_text(
            "trac:\n"
            "  url: https://yaml-trac.example.com\n"
            "  username: yamluser\n"
            "  password: yamlpass\n"
        )

        mock_client = MagicMock()
        captured_config = {}

        def capture_client(config):
            captured_config["config"] = config
            return mock_client

        overrides = {"url": "https://cli-override.example.com"}

        with (
            patch(
                "trac_mcp_server.mcp.lifespan.discover_config_files",
                return_value=[config_file],
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.load_hierarchical_config",
                return_value={
                    "trac": {
                        "url": "https://yaml-trac.example.com",
                        "username": "yamluser",
                        "password": "yamlpass",
                    }
                },
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                side_effect=capture_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            async with server_lifespan(config_overrides=overrides) as _:
                pass

        config = captured_config["config"]
        # CLI override wins for url
        assert config.trac_url == "https://cli-override.example.com"
        # YAML values used for non-overridden fields
        assert config.username == "yamluser"
        assert config.password == "yamlpass"

    async def test_yaml_config_stderr_mentions_config_file(self, tmp_path):
        """Stderr output should mention the config file path."""
        config_dir = tmp_path / ".trac_mcp"
        config_dir.mkdir()
        config_file = config_dir / "config.yml"
        config_file.write_text(
            "trac:\n"
            "  url: https://yaml-trac.example.com\n"
            "  username: yamluser\n"
            "  password: yamlpass\n"
        )

        mock_client = MagicMock()
        stderr_messages = []

        with (
            patch(
                "trac_mcp_server.mcp.lifespan.discover_config_files",
                return_value=[config_file],
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.load_hierarchical_config",
                return_value={
                    "trac": {
                        "url": "https://yaml-trac.example.com",
                        "username": "yamluser",
                        "password": "yamlpass",
                    }
                },
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch(
                "trac_mcp_server.mcp.lifespan._stderr_print",
                side_effect=lambda msg: stderr_messages.append(msg),
            ),
        ):
            async with server_lifespan() as _:
                pass

        full_output = "\n".join(stderr_messages)
        assert "config file" in full_output.lower()
        assert str(config_file) in full_output

    async def test_env_var_path_when_no_config_files(self):
        """When no YAML config files exist, falls back to env var loading."""
        mock_client = MagicMock()
        config = _make_config()
        stderr_messages = []

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ) as mock_load,
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch(
                "trac_mcp_server.mcp.lifespan._stderr_print",
                side_effect=lambda msg: stderr_messages.append(msg),
            ),
        ):
            async with server_lifespan() as _:
                mock_load.assert_called_once_with()

        full_output = "\n".join(stderr_messages)
        assert "environment variables" in full_output.lower()


# -------------------------------------------------------------------------
# server_lifespan() — config error path
# -------------------------------------------------------------------------


class TestServerLifespanConfigError:
    """Tests for config validation failures in server_lifespan()."""

    async def test_config_error_raises_runtime_error(self):
        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                side_effect=ValueError("Trac URL not found"),
            ),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            with pytest.raises(
                RuntimeError, match="Configuration error"
            ):
                async with server_lifespan() as _:
                    pass  # pragma: no cover -- should not reach here

    async def test_config_error_includes_original_message(self):
        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                side_effect=ValueError("Trac URL not found"),
            ),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            with pytest.raises(
                RuntimeError, match="Trac URL not found"
            ):
                async with server_lifespan() as _:
                    pass  # pragma: no cover

    async def test_config_error_stderr_messages(self):
        stderr_messages = []

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                side_effect=ValueError("missing URL"),
            ),
            patch(
                "trac_mcp_server.mcp.lifespan._stderr_print",
                side_effect=lambda msg: stderr_messages.append(msg),
            ),
        ):
            with pytest.raises(RuntimeError):
                async with server_lifespan() as _:
                    pass  # pragma: no cover

        # Should print startup message, then error messages
        assert any("starting" in m.lower() for m in stderr_messages)
        assert any("Configuration error" in m for m in stderr_messages)
        assert any("TRAC_URL" in m for m in stderr_messages)


# -------------------------------------------------------------------------
# server_lifespan() — connection error path
# -------------------------------------------------------------------------


class TestServerLifespanConnectionError:
    """Tests for Trac connection failures in server_lifespan()."""

    async def test_connection_error_raises_runtime_error(self):
        config = _make_config()
        mock_client = MagicMock()

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                side_effect=ConnectionError("Connection refused"),
            ),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            with pytest.raises(RuntimeError, match="connection failed"):
                async with server_lifespan() as _:
                    pass  # pragma: no cover

    async def test_connection_error_includes_original_message(self):
        config = _make_config()
        mock_client = MagicMock()

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                side_effect=ConnectionError("Connection refused"),
            ),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            with pytest.raises(
                RuntimeError, match="Connection refused"
            ):
                async with server_lifespan() as _:
                    pass  # pragma: no cover

    async def test_connection_error_stderr_messages(self):
        config = _make_config()
        mock_client = MagicMock()
        stderr_messages = []

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                side_effect=ConnectionError("Connection refused"),
            ),
            patch(
                "trac_mcp_server.mcp.lifespan._stderr_print",
                side_effect=lambda msg: stderr_messages.append(msg),
            ),
        ):
            with pytest.raises(RuntimeError):
                async with server_lifespan() as _:
                    pass  # pragma: no cover

        assert any(
            "connection failed" in m.lower() for m in stderr_messages
        )
        assert any("Connection refused" in m for m in stderr_messages)
        assert any("TRAC_URL" in m for m in stderr_messages)

    async def test_generic_exception_also_caught(self):
        """Non-ConnectionError exceptions from validate_connection are also caught."""
        config = _make_config()
        mock_client = MagicMock()

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                side_effect=Exception("Unexpected XML-RPC fault"),
            ),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            with pytest.raises(RuntimeError, match="connection failed"):
                async with server_lifespan() as _:
                    pass  # pragma: no cover


# -------------------------------------------------------------------------
# server_lifespan() — shutdown path
# -------------------------------------------------------------------------


class TestServerLifespanShutdown:
    """Tests for the shutdown (exit) path of server_lifespan()."""

    async def test_shutdown_completes_without_error(self):
        config = _make_config()
        mock_client = MagicMock()

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch("trac_mcp_server.mcp.lifespan._stderr_print"),
        ):
            async with server_lifespan() as _:
                pass  # enter and exit cleanly

    async def test_shutdown_prints_message(self):
        config = _make_config()
        mock_client = MagicMock()
        stderr_messages = []

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch(
                "trac_mcp_server.mcp.lifespan._stderr_print",
                side_effect=lambda msg: stderr_messages.append(msg),
            ),
        ):
            async with server_lifespan() as _:
                pass  # enter and exit

        assert any(
            "shutting down" in m.lower() for m in stderr_messages
        )

    async def test_success_stderr_messages_full_sequence(self):
        """Verify the full sequence of stderr messages on successful startup."""
        config = _make_config()
        mock_client = MagicMock()
        stderr_messages = []

        with (
            _NO_CONFIG_FILES,
            patch(
                "trac_mcp_server.mcp.lifespan.load_config",
                return_value=config,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.TracClient",
                return_value=mock_client,
            ),
            patch(
                "trac_mcp_server.mcp.lifespan.run_sync",
                return_value="1.3.5",
            ),
            patch("trac_mcp_server.mcp.lifespan.init_semaphore"),
            patch(
                "trac_mcp_server.mcp.lifespan._stderr_print",
                side_effect=lambda msg: stderr_messages.append(msg),
            ),
        ):
            async with server_lifespan() as _:
                pass

        # Verify key startup messages in order
        full_output = "\n".join(stderr_messages)
        assert "starting" in full_output.lower()
        assert "Configuration loaded" in full_output
        assert "Connected to Trac API version" in full_output
        assert "1.3.5" in full_output
        assert "Server ready" in full_output
        assert "shutting down" in full_output.lower()
