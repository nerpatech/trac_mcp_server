"""Simplified configuration for standalone MCP server.

Reads Trac connection settings from CLI args, environment variables,
.env files, and YAML config file fallbacks.

Precedence (highest to lowest):
    CLI args > Environment variables > .env file > YAML config > Built-in defaults

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
    yaml_fallbacks: dict | None = None,
) -> Config:
    """Load configuration with unified precedence.

    Resolution order for each field (highest to lowest):
        CLI arg > env var / .env > yaml_fallbacks > built-in default

    The caller is responsible for calling ``load_dotenv()`` before this
    function so that .env values are available via ``os.getenv()``.

    Args:
        url: Override Trac URL (takes precedence over env var and YAML).
        username: Override username (takes precedence over env var and YAML).
        password: Override password (takes precedence over env var and YAML).
        insecure: Skip SSL verification (CLI flag).
        debug: Enable debug logging (CLI flag).
        yaml_fallbacks: Dict of values from YAML config file ``trac`` section.
            Used as fallback when CLI arg and env var are both unset.

    Returns:
        Validated Config instance.

    Raises:
        ValueError: If required config (URL, username, password) is missing
            after checking all sources.
    """
    fb = yaml_fallbacks or {}

    # --- String fields: CLI > env > YAML > error ---

    trac_url = url or os.getenv("TRAC_URL") or fb.get("url")
    if not trac_url:
        raise ValueError(
            "Trac URL not found. Set TRAC_URL environment variable, "
            "pass --url CLI argument, or add 'url' to config.yaml."
        )
    trac_url = trac_url.strip()

    trac_username = username or os.getenv("TRAC_USERNAME") or fb.get("username")
    if not trac_username:
        raise ValueError(
            "Trac username not found. Set TRAC_USERNAME environment variable, "
            "pass --username CLI argument, or add 'username' to config.yaml."
        )
    trac_username = trac_username.strip()

    trac_password = password or os.getenv("TRAC_PASSWORD") or fb.get("password")
    if not trac_password:
        raise ValueError(
            "Trac password not found. Set TRAC_PASSWORD environment variable, "
            "pass --password CLI argument, or add 'password' to config.yaml."
        )
    trac_password = trac_password.strip()

    # --- Boolean fields: CLI > env > YAML > default ---

    def get_bool_env(key: str) -> bool | None:
        """Return True/False from env var, or None if unset."""
        val = os.getenv(key)
        if val is None:
            return None
        return val.lower() in ("true", "1", "yes", "on")

    if insecure:
        final_insecure = True
    else:
        env_insecure = get_bool_env("TRAC_INSECURE")
        if env_insecure is not None:
            final_insecure = env_insecure
        else:
            final_insecure = bool(fb.get("insecure", False))

    if debug:
        final_debug = True
    else:
        env_debug = get_bool_env("TRAC_DEBUG")
        if env_debug is not None:
            final_debug = env_debug
        else:
            final_debug = bool(fb.get("debug", False))

    # --- Numeric fields: env > YAML > default ---
    # (No CLI args for numeric fields currently)

    max_parallel_raw = os.getenv("TRAC_MAX_PARALLEL_REQUESTS")
    if max_parallel_raw is not None:
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
    elif "max_parallel_requests" in fb:
        final_max_parallel = int(fb["max_parallel_requests"])
    else:
        final_max_parallel = 5

    max_batch_raw = os.getenv("TRAC_MAX_BATCH_SIZE")
    if max_batch_raw is not None:
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
    elif "max_batch_size" in fb:
        final_max_batch = int(fb["max_batch_size"])
    else:
        final_max_batch = 500

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
