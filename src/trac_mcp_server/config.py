"""Simplified configuration for standalone MCP server.

Reads Trac connection settings from environment variables only.
No YAML config files, no hierarchical config, no config_loader/config_schema.

Environment variables:
    TRAC_URL: Trac instance URL (required)
    TRAC_USERNAME: Trac username (required)
    TRAC_PASSWORD: Trac password (required)
    TRAC_INSECURE: Skip SSL verification (optional, default: false)
    TRAC_MAX_PARALLEL_REQUESTS: Max parallel XML-RPC requests (optional, default: 5)
    TRAC_MAX_BATCH_SIZE: Max items per batch operation (optional, default: 500)
"""

import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@dataclass
class Config:
    trac_url: str
    username: str
    password: str
    insecure: bool = False
    debug: bool = False
    max_parallel_requests: int = 5
    max_batch_size: int = 500


def validate_config(config: Config) -> None:
    """Validate configuration values and raise ValueError if invalid.

    Args:
        config: Config instance to validate.

    Raises:
        ValueError: If URL format is invalid or credentials are empty.
    """
    # Normalize URL: strip whitespace
    config.trac_url = config.trac_url.strip()

    if not config.trac_url.startswith(("http://", "https://")):
        raise ValueError(
            f"Invalid Trac URL '{config.trac_url}': must start with http:// or https://"
        )

    parsed = urlparse(config.trac_url)
    if not parsed.hostname:
        raise ValueError(
            f"Invalid Trac URL '{config.trac_url}': URL must include a hostname"
        )

    # Strip trailing slash after validation (safe now that scheme/host are verified)
    config.trac_url = config.trac_url.removesuffix("/")

    if not config.username.strip():
        raise ValueError(
            "Trac username cannot be empty. Set TRAC_USERNAME environment variable."
        )

    if not config.password.strip():
        raise ValueError(
            "Trac password cannot be empty. Set TRAC_PASSWORD environment variable."
        )

    if config.insecure:
        logger.warning(
            "WARNING: SSL verification disabled (insecure=True). Use only for development."
        )


def load_config(
    url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    insecure: bool = False,
    debug: bool = False,
) -> Config:
    """Load configuration from CLI args and environment variables.

    Priority: CLI args > Environment variables

    Args:
        url: Override Trac URL (takes precedence over TRAC_URL env var).
        username: Override username (takes precedence over TRAC_USERNAME env var).
        password: Override password (takes precedence over TRAC_PASSWORD env var).
        insecure: Skip SSL verification.
        debug: Enable debug logging.

    Returns:
        Validated Config instance.

    Raises:
        ValueError: If required config (URL, username, password) is missing.
    """
    # Load .env file if present
    load_dotenv()

    trac_url = url or os.getenv("TRAC_URL")
    if not trac_url:
        raise ValueError(
            "Trac URL not found. Set TRAC_URL environment variable or pass --url CLI argument."
        )

    # Strip whitespace from URL (trailing slash stripped in validate_config)
    trac_url = trac_url.strip()

    trac_username = username or os.getenv("TRAC_USERNAME")
    if not trac_username:
        raise ValueError(
            "Trac username not found. Set TRAC_USERNAME environment variable or pass --username CLI argument."
        )

    # Strip whitespace from username
    trac_username = trac_username.strip()

    trac_password = password or os.getenv("TRAC_PASSWORD")
    if not trac_password:
        raise ValueError(
            "Trac password not found. Set TRAC_PASSWORD environment variable or pass --password CLI argument."
        )

    # Strip whitespace from password
    trac_password = trac_password.strip()

    # Boolean env var parsing
    def get_bool_env(key: str, default: bool = False) -> bool:
        val = os.getenv(key)
        if val is None:
            return default
        return val.lower() in ("true", "1", "yes", "on")

    final_insecure = insecure or get_bool_env("TRAC_INSECURE")
    final_debug = debug or get_bool_env("TRAC_DEBUG")

    # Parse and validate max_parallel_requests with bounds checking
    max_parallel_raw = os.getenv("TRAC_MAX_PARALLEL_REQUESTS", "5")
    try:
        final_max_parallel = int(max_parallel_raw)
    except ValueError:
        raise ValueError(
            f"Invalid TRAC_MAX_PARALLEL_REQUESTS '{max_parallel_raw}': must be a number between 1 and 100"
        ) from None
    if not (1 <= final_max_parallel <= 100):
        raise ValueError(
            f"Invalid TRAC_MAX_PARALLEL_REQUESTS '{max_parallel_raw}': must be a number between 1 and 100"
        )

    # Parse and validate max_batch_size with bounds checking
    max_batch_raw = os.getenv("TRAC_MAX_BATCH_SIZE", "500")
    try:
        final_max_batch = int(max_batch_raw)
    except ValueError:
        raise ValueError(
            f"Invalid TRAC_MAX_BATCH_SIZE '{max_batch_raw}': must be a number between 1 and 10000"
        ) from None
    if not (1 <= final_max_batch <= 10000):
        raise ValueError(
            f"Invalid TRAC_MAX_BATCH_SIZE '{max_batch_raw}': must be a number between 1 and 10000"
        )

    config = Config(
        trac_url=trac_url,
        username=trac_username,
        password=trac_password,
        insecure=final_insecure,
        debug=final_debug,
        max_parallel_requests=final_max_parallel,
        max_batch_size=final_max_batch,
    )

    validate_config(config)

    return config
