"""Lifespan management for MCP server startup and shutdown."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv

from ..config import load_config
from ..config_loader import (
    discover_config_files,
    load_hierarchical_config,
)
from ..config_schema import build_config
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
    - Load .env file (so values are available for env var lookups and YAML interpolation)
    - Load YAML config file if present (as fallback values)
    - Merge all sources via load_config(): CLI > env vars > .env > YAML > defaults
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

    # Load configuration with unified precedence:
    # CLI args > env vars (.env loaded first) > YAML config > defaults
    try:
        # 1. Load .env early (before YAML, so ${VAR} interpolation can use .env values)
        load_dotenv()

        # 2. Load YAML config if present, extract trac section as fallbacks
        yaml_fallbacks: dict[str, Any] | None = None
        config_files = discover_config_files()
        sources = []

        if config_files:
            config_path = config_files[0]
            raw = load_hierarchical_config()
            unified = build_config(raw)
            # Extract non-None trac values as fallbacks
            yaml_fallbacks = {
                k: v
                for k, v in unified.trac.model_dump().items()
                if v is not None
            }
            sources.append(f"config file: {config_path}")

        # 3. Single call to load_config with all sources merged
        overrides = config_overrides or {}
        config = load_config(
            url=overrides.get("url"),
            username=overrides.get("username"),
            password=overrides.get("password"),
            insecure=overrides.get("insecure", False),
            debug=overrides.get("debug", False),
            yaml_fallbacks=yaml_fallbacks,
        )

        # Log which sources contributed
        if overrides:
            sources.append("CLI arguments")
        sources.append("environment variables")
        source_desc = ", ".join(sources) if sources else "defaults"
        logger.info("Configuration loaded from: %s", source_desc)
        _stderr_print(f"  Configuration loaded from: {source_desc}")
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
