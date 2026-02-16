"""
Input validation functions for Trac MCP Server.

Provides validation for wiki page names, content, and other user inputs
to ensure they meet requirements before making XML-RPC calls.
"""


# ---------------------------------------------------------------------------
# Error message formatting helpers
# ---------------------------------------------------------------------------


def format_validation_error(field_name: str, reason: str) -> str:
    """
    Generate consistent error message for validation failures.

    Args:
        field_name: Human-readable field name (e.g., "Page name")
        reason: Description of validation failure (e.g., "cannot be empty")

    Returns:
        Formatted error message string
    """
    return f"{field_name} {reason}"


def validate_page_name(page_name: str) -> tuple[bool, str]:
    """
    Validate a wiki page name.

    Args:
        page_name: The page name to validate

    Returns:
        Tuple of (is_valid, error_message).
        Returns (True, "") if valid, (False, reason) if invalid.

    Validation rules:
        - Cannot be empty or whitespace-only
        - Cannot contain '..' (path traversal protection)
        - Cannot have empty path segments (e.g., 'Page//Name')
        - Each path segment should match ^[A-Za-z][A-Za-z0-9_]*$ (warning only)
    """
    # Check if empty or whitespace
    if not page_name or not page_name.strip():
        return (
            False,
            format_validation_error("Page name", "cannot be empty"),
        )

    # Check for path traversal attempts
    if ".." in page_name:
        return (
            False,
            format_validation_error("Page name", "cannot contain '..'"),
        )

    # Check for empty path segments (double slashes)
    if "//" in page_name:
        return (
            False,
            format_validation_error(
                "Page name", "cannot have empty path segments"
            ),
        )

    return (True, "")


def validate_content(
    content: str, max_size: int = 1_000_000
) -> tuple[bool, str]:
    """
    Validate wiki page content.

    Args:
        content: The content to validate
        max_size: Maximum size in bytes (default: 1,000,000)

    Returns:
        Tuple of (is_valid, error_message).
        Returns (True, "") if valid, (False, reason) if invalid.

    Validation rules:
        - Cannot be empty
        - Cannot exceed max_size bytes
    """
    # Check if empty
    if not content:
        return (
            False,
            format_validation_error("Content", "cannot be empty"),
        )

    # Check size limit
    content_bytes = len(content.encode("utf-8"))
    if content_bytes > max_size:
        return (
            False,
            format_validation_error(
                "Content", f"exceeds maximum size of {max_size} bytes"
            ),
        )

    return (True, "")
