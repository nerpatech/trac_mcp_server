import json
import logging
import os
import sys


class JsonFormatter(logging.Formatter):
    """Single-line JSON formatter for structured debug output.

    Produces one JSON object per log record with fields: ts, level, logger, msg.
    Exception info is included as an "exc" field when present.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(
    mode: str = "cli",
    debug: bool = False,
    log_file: str | None = None,
    debug_format: str = "text",
) -> None:
    """
    Configure logging based on execution mode.

    Args:
        mode: "mcp" for file logging (never stdout), "cli" for stderr logging.
        debug: If True, overrides LOG_LEVEL to DEBUG.
        log_file: Custom log file path (overrides LOG_FILE env var).
        debug_format: "text" (default) or "json" for structured output.

    Environment variables:
        LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR).
                   Default: WARNING for MCP mode, INFO for CLI mode.
        LOG_FILE: Custom log file path for MCP mode.
                  Default: /tmp/trac-mcp-server.log
    """
    # Determine log level from environment or defaults
    default_level = "WARNING" if mode == "mcp" else "INFO"
    env_level = os.getenv("LOG_LEVEL", default_level).upper()

    # debug parameter overrides environment
    if debug:
        log_level = logging.DEBUG
    else:
        log_level = getattr(logging, env_level, logging.INFO)

    if mode == "mcp":
        # MCP mode: Log to file to avoid stdout contamination
        # stdio transport uses stdout for JSON-RPC messages
        # Priority: log_file param > LOG_FILE env var > default
        final_log_file = log_file or os.getenv(
            "LOG_FILE", "/tmp/trac-mcp-server.log"
        )
        logging.basicConfig(
            level=log_level,
            format="[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            filename=final_log_file,
            filemode="a",
        )
    else:
        # CLI mode: Log to stderr (safe, doesn't interfere with output)
        # When a log_file is specified (e.g., --debug myfile.log), also write to file
        handlers: list[logging.Handler] = []
        stderr_handler = logging.StreamHandler(sys.stderr)

        if debug_format == "json":
            stderr_handler.setFormatter(
                JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
            )
        else:
            stderr_handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        handlers.append(stderr_handler)

        if log_file:
            file_handler = logging.FileHandler(log_file, mode="a")
            if debug_format == "json":
                file_handler.setFormatter(
                    JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
                )
            else:
                file_handler.setFormatter(
                    logging.Formatter(
                        "[%(asctime)s] [%(levelname)s] %(name)s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                    )
                )
            handlers.append(file_handler)

        logging.basicConfig(
            level=log_level,
            handlers=handlers,
        )

    # Silence third-party libs unless DEBUG
    if log_level != logging.DEBUG:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
