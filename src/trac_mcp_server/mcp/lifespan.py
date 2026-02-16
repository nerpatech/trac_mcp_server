"""Lifespan management for MCP server startup and shutdown."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from ..config import load_config, validate_config
from ..config_loader import discover_config_files, load_hierarchical_config
from ..config_schema import build_config, to_legacy_config
from ..core.async_utils import init_semaphore, run_sync
from ..core.client import TracClient

logger = logging.getLogger(__name__)


def _stderr_print(msg: str) -> None:
    """Print message to stderr for user feedback (safe in MCP mode)."""
    print(msg, file=sys.stderr, flush=True)


@asynccontextmanager
async def server_lifespan(
    config_overrides: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Manage server startup and shutdown lifecycle.

    On startup:
    - Load configuration from environment (with optional CLI overrides)
    - Create TracClient and validate connection
    - Fail fast if Trac is unreachable

    On shutdown:
    - Log shutdown message
    - Cleanup (minimal for XML-RPC stateless client)

    Args:
        config_overrides: Optional dict with config values from CLI (url, username, password, insecure)

    Yields:
        Dict with 'client' key containing the initialized TracClient

    Raises:
        RuntimeError: If configuration is invalid or Trac connection fails.
    """
    logger.info("MCP server starting...")
    _stderr_print("Trac MCP Server starting...")

    # Load configuration with optional overrides
    # Precedence: CLI args > YAML config file > env vars > defaults
    try:
        # Check for YAML config files first
        config_files = discover_config_files()
        if config_files:
            # Use hierarchical config pipeline (YAML + CLI overrides)
            config_path = config_files[0]
            raw = load_hierarchical_config()
            unified = build_config(raw)
            config = to_legacy_config(unified, cli_overrides=config_overrides)
            validate_config(config)
            logger.info(
                "Configuration loaded from config file: %s", config_path
            )
            _stderr_print(
                f"  Configuration loaded from config file: {config_path}"
            )
        elif config_overrides:
            # No config files — use env vars with CLI overrides
            config = load_config(
                url=config_overrides.get("url"),
                username=config_overrides.get("username"),
                password=config_overrides.get("password"),
                insecure=config_overrides.get("insecure", False),
            )
            logger.info("Configuration loaded from environment variables")
            _stderr_print("  Configuration loaded from environment variables")
        else:
            # No config files, no CLI overrides — pure env var mode
            config = load_config()
            logger.info("Configuration loaded from environment variables")
            _stderr_print("  Configuration loaded from environment variables")
        logger.info("Trac URL: %s", config.trac_url)
        _stderr_print(f"  Trac URL: {config.trac_url}")
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        _stderr_print(f"ERROR: Configuration error: {e}")
        _stderr_print(
            "  Ensure TRAC_URL, TRAC_USERNAME, TRAC_PASSWORD are set."
        )
        raise RuntimeError(
            f"Configuration error: {e}. Ensure TRAC_URL, TRAC_USERNAME, TRAC_PASSWORD are set."
        ) from e

    # Validate Trac connection
    logger.info("Validating Trac connection...")
    _stderr_print("  Validating Trac connection...")
    try:
        client = TracClient(config)
        version = await run_sync(client.validate_connection)
        logger.info(
            "Successfully connected to Trac API version %s", version
        )
        _stderr_print(f"  Connected to Trac API version {version}")
        init_semaphore(config.max_parallel_requests)
        _stderr_print(
            f"  Parallel requests: {config.max_parallel_requests}"
        )
        _stderr_print(
            "Server ready. Waiting for MCP client connection..."
        )
    except Exception as e:
        logger.error("Failed to connect to Trac: %s", e)
        _stderr_print("ERROR: Trac connection failed.")
        _stderr_print(f"  {e}")
        _stderr_print("  Check TRAC_URL, TRAC_USERNAME, TRAC_PASSWORD.")
        raise RuntimeError(
            f"Trac connection failed: {e}. Check TRAC_URL, TRAC_USERNAME, TRAC_PASSWORD."
        ) from e

    # Server is ready - yield client for caller to install
    yield {"client": client}

    # Shutdown
    logger.info("MCP server shutting down")
    _stderr_print("Trac MCP Server shutting down.")
