"""Tests for trac_mcp_server.config — env-var config loading and validation.

NOT to be confused with test_config_loader.py (hierarchical YAML config)
or test_config_schema.py (Pydantic models). This tests the standalone
server bootstrap path: validate_config() and load_config().
"""

import logging
from unittest.mock import patch

import pytest

from trac_mcp_server.config import Config, load_config, validate_config

# -------------------------------------------------------------------------
# validate_config()
# -------------------------------------------------------------------------


class TestValidateConfig:
    """Tests for validate_config() — URL format and credential checks."""

    def test_valid_config(self):
        config = Config(
            trac_url="https://trac.example.com/trac",
            username="admin",
            password="secret",
        )
        validate_config(config)  # should not raise

    def test_https_url_valid(self):
        config = Config(
            trac_url="https://trac.example.com/trac",
            username="user",
            password="pass",
        )
        validate_config(config)

    def test_http_url_valid(self):
        config = Config(
            trac_url="http://localhost:8080/trac",
            username="user",
            password="pass",
        )
        validate_config(config)

    def test_invalid_url_no_scheme(self):
        config = Config(
            trac_url="example.com",
            username="user",
            password="pass",
        )
        with pytest.raises(
            ValueError, match="must start with http:// or https://"
        ):
            validate_config(config)

    def test_invalid_url_ftp_scheme(self):
        config = Config(
            trac_url="ftp://example.com",
            username="user",
            password="pass",
        )
        with pytest.raises(
            ValueError, match="must start with http:// or https://"
        ):
            validate_config(config)

    def test_empty_username(self):
        config = Config(
            trac_url="https://trac.example.com",
            username="  ",
            password="pass",
        )
        with pytest.raises(
            ValueError, match="username cannot be empty"
        ):
            validate_config(config)

    def test_empty_password(self):
        config = Config(
            trac_url="https://trac.example.com",
            username="user",
            password="",
        )
        with pytest.raises(
            ValueError, match="password cannot be empty"
        ):
            validate_config(config)

    def test_whitespace_only_password(self):
        config = Config(
            trac_url="https://trac.example.com",
            username="user",
            password="   ",
        )
        with pytest.raises(
            ValueError, match="password cannot be empty"
        ):
            validate_config(config)

    # --- URL structure validation (empty host) ---

    def test_empty_host_url_http(self):
        """URL with scheme but no hostname should be rejected."""
        config = Config(
            trac_url="http://",
            username="user",
            password="pass",
        )
        with pytest.raises(ValueError, match="must include a hostname"):
            validate_config(config)

    def test_empty_host_url_https(self):
        """https:// with no hostname should be rejected."""
        config = Config(
            trac_url="https://",
            username="user",
            password="pass",
        )
        with pytest.raises(ValueError, match="must include a hostname"):
            validate_config(config)

    # --- URL trailing slash normalization ---

    def test_trailing_slash_stripped(self):
        """Trailing slash should be stripped during validation."""
        config = Config(
            trac_url="https://trac.example.com/",
            username="user",
            password="pass",
        )
        validate_config(config)
        assert config.trac_url == "https://trac.example.com"

    # --- URL whitespace handling in validate_config ---

    def test_whitespace_url_stripped_before_scheme_check(self):
        """Leading/trailing whitespace on URL should be stripped, not rejected."""
        config = Config(
            trac_url="  https://trac.example.com  ",
            username="user",
            password="pass",
        )
        validate_config(config)
        assert config.trac_url == "https://trac.example.com"

    def test_insecure_logs_warning(self, caplog):
        config = Config(
            trac_url="https://trac.example.com",
            username="user",
            password="pass",
            insecure=True,
        )
        with caplog.at_level(
            logging.WARNING, logger="trac_mcp_server.config"
        ):
            validate_config(config)
        assert "SSL verification disabled" in caplog.text

    def test_secure_no_warning(self, caplog):
        config = Config(
            trac_url="https://trac.example.com",
            username="user",
            password="pass",
            insecure=False,
        )
        with caplog.at_level(
            logging.WARNING, logger="trac_mcp_server.config"
        ):
            validate_config(config)
        assert "SSL verification disabled" not in caplog.text


# -------------------------------------------------------------------------
# load_config()
# -------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for load_config() — env var loading, CLI overrides, boolean parsing."""

    @pytest.fixture(autouse=True)
    def _patch_dotenv(self):
        """Prevent load_dotenv from reading real .env files during tests."""
        with patch("trac_mcp_server.config.load_dotenv"):
            yield

    def test_load_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com/trac")
        monkeypatch.setenv("TRAC_USERNAME", "admin")
        monkeypatch.setenv("TRAC_PASSWORD", "secret")

        config = load_config()

        assert config.trac_url == "https://trac.example.com/trac"
        assert config.username == "admin"
        assert config.password == "secret"

    def test_cli_args_override_env(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://env-url.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "env-user")
        monkeypatch.setenv("TRAC_PASSWORD", "env-pass")

        config = load_config(
            url="https://cli-url.example.com",
            username="cli-user",
            password="cli-pass",
        )

        assert config.trac_url == "https://cli-url.example.com"
        assert config.username == "cli-user"
        assert config.password == "cli-pass"

    def test_missing_url_raises(self, monkeypatch):
        monkeypatch.delenv("TRAC_URL", raising=False)
        monkeypatch.delenv("TRAC_USERNAME", raising=False)
        monkeypatch.delenv("TRAC_PASSWORD", raising=False)

        with pytest.raises(ValueError, match="Trac URL not found"):
            load_config()

    def test_missing_username_raises(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.delenv("TRAC_USERNAME", raising=False)
        monkeypatch.delenv("TRAC_PASSWORD", raising=False)

        with pytest.raises(ValueError, match="Trac username not found"):
            load_config()

    def test_missing_password_raises(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.delenv("TRAC_PASSWORD", raising=False)

        with pytest.raises(ValueError, match="Trac password not found"):
            load_config()

    # --- Boolean env var parsing ---

    def test_insecure_from_env(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_INSECURE", "true")

        config = load_config()
        assert config.insecure is True

    @pytest.mark.parametrize(
        "value", ["true", "1", "yes", "on", "TRUE", "True", "YES"]
    )
    def test_insecure_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_INSECURE", value)

        config = load_config()
        assert config.insecure is True

    @pytest.mark.parametrize(
        "value", ["false", "0", "no", "off", "FALSE", "random"]
    )
    def test_insecure_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_INSECURE", value)

        config = load_config()
        assert config.insecure is False

    def test_debug_from_env(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_DEBUG", "true")

        config = load_config()
        assert config.debug is True

    def test_debug_default_false(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.delenv("TRAC_DEBUG", raising=False)

        config = load_config()
        assert config.debug is False

    # --- Numeric env var parsing ---

    def test_max_parallel_from_env(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_MAX_PARALLEL_REQUESTS", "10")

        config = load_config()
        assert config.max_parallel_requests == 10

    def test_max_parallel_default(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.delenv("TRAC_MAX_PARALLEL_REQUESTS", raising=False)

        config = load_config()
        assert config.max_parallel_requests == 5

    # --- Numeric env var validation (edge cases) ---

    def test_max_parallel_non_numeric(self, monkeypatch):
        """Non-numeric TRAC_MAX_PARALLEL_REQUESTS should raise ValueError with clear message."""
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_MAX_PARALLEL_REQUESTS", "abc")

        with pytest.raises(
            ValueError, match="Invalid TRAC_MAX_PARALLEL_REQUESTS 'abc'"
        ):
            load_config()

    def test_max_parallel_zero(self, monkeypatch):
        """TRAC_MAX_PARALLEL_REQUESTS=0 should raise (must be >= 1)."""
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_MAX_PARALLEL_REQUESTS", "0")

        with pytest.raises(
            ValueError, match="must be a number between 1 and 100"
        ):
            load_config()

    def test_max_parallel_negative(self, monkeypatch):
        """TRAC_MAX_PARALLEL_REQUESTS=-5 should raise (must be >= 1)."""
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_MAX_PARALLEL_REQUESTS", "-5")

        with pytest.raises(
            ValueError, match="must be a number between 1 and 100"
        ):
            load_config()

    def test_max_parallel_too_high(self, monkeypatch):
        """TRAC_MAX_PARALLEL_REQUESTS=500 should raise (must be <= 100)."""
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_MAX_PARALLEL_REQUESTS", "500")

        with pytest.raises(
            ValueError, match="must be a number between 1 and 100"
        ):
            load_config()

    def test_max_parallel_minimum_valid(self, monkeypatch):
        """TRAC_MAX_PARALLEL_REQUESTS=1 should be accepted (minimum)."""
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_MAX_PARALLEL_REQUESTS", "1")

        config = load_config()
        assert config.max_parallel_requests == 1

    def test_max_parallel_maximum_valid(self, monkeypatch):
        """TRAC_MAX_PARALLEL_REQUESTS=100 should be accepted (maximum)."""
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_MAX_PARALLEL_REQUESTS", "100")

        config = load_config()
        assert config.max_parallel_requests == 100

    # --- Whitespace stripping in load_config ---

    def test_url_whitespace_stripped(self, monkeypatch):
        """Leading/trailing whitespace in TRAC_URL should be stripped."""
        monkeypatch.setenv("TRAC_URL", "  https://trac.example.com  ")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")

        config = load_config()
        assert config.trac_url == "https://trac.example.com"

    def test_url_trailing_slash_stripped(self, monkeypatch):
        """Trailing slash in TRAC_URL should be stripped."""
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com/")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")

        config = load_config()
        assert config.trac_url == "https://trac.example.com"

    def test_username_whitespace_stripped(self, monkeypatch):
        """Leading/trailing whitespace in TRAC_USERNAME should be stripped."""
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "  admin  ")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")

        config = load_config()
        assert config.username == "admin"

    def test_password_whitespace_stripped(self, monkeypatch):
        """Leading/trailing whitespace in TRAC_PASSWORD should be stripped."""
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "  secret  ")

        config = load_config()
        assert config.password == "secret"

    # --- URL empty host via load_config ---

    def test_empty_host_url_via_load(self, monkeypatch):
        """URL with scheme but no host via env var should be caught."""
        monkeypatch.setenv("TRAC_URL", "http://")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")

        with pytest.raises(ValueError, match="must include a hostname"):
            load_config()

    def test_no_scheme_url_via_load(self, monkeypatch):
        """URL without scheme via env var should be caught."""
        monkeypatch.setenv("TRAC_URL", "foobar")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")

        with pytest.raises(
            ValueError, match="must start with http:// or https://"
        ):
            load_config()

    # --- CLI overrides for booleans ---

    def test_cli_insecure_overrides_env(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_INSECURE", "false")

        config = load_config(insecure=True)
        assert config.insecure is True

    def test_cli_debug_overrides_env(self, monkeypatch):
        monkeypatch.setenv("TRAC_URL", "https://trac.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")
        monkeypatch.setenv("TRAC_DEBUG", "false")

        config = load_config(debug=True)
        assert config.debug is True

    # --- Validation integration ---

    def test_load_config_validates(self, monkeypatch):
        """load_config() calls validate_config() — invalid URL is caught."""
        monkeypatch.setenv("TRAC_URL", "ftp://bad-scheme.example.com")
        monkeypatch.setenv("TRAC_USERNAME", "user")
        monkeypatch.setenv("TRAC_PASSWORD", "pass")

        with pytest.raises(
            ValueError, match="must start with http:// or https://"
        ):
            load_config()
