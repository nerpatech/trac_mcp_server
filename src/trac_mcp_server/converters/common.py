"""Common types and utilities for format conversion."""

import re
from dataclasses import dataclass, field

# =============================================================================
# Code Block Language Mapping
# =============================================================================
#
# Bidirectional mapping between Markdown code fence language identifiers and
# TracWiki processor directives.
#
# Markdown: ```python
# TracWiki: {{{#!python}}}
#
# Design:
# - Store Markdown->TracWiki as the canonical direction
# - Derive TracWiki->Markdown mapping automatically
# - Handle asymmetric cases where multiple Markdown names map to one TracWiki name
# - Unknown languages pass through unchanged for forward compatibility
# =============================================================================

# Markdown language identifier -> TracWiki processor directive
# Only include mappings where names differ or where we want to normalize
_MARKDOWN_TO_TRACWIKI_MAP: dict[str, str] = {
    # Shell scripting: Markdown uses bash/shell, TracWiki uses sh
    "bash": "sh",
    "shell": "sh",
    "zsh": "sh",
    # JavaScript variants
    "js": "javascript",
    # TypeScript variants
    "ts": "typescript",
    # C++ variants
    "c++": "cpp",
    # Text/plaintext normalization
    "text": "text",
    "plaintext": "text",
    "plain": "text",
}

# TracWiki processor directive -> Markdown language identifier (canonical form)
# Built from the inverse of _MARKDOWN_TO_TRACWIKI_MAP
# When multiple Markdown names map to the same TracWiki name, we pick one canonical form
_TRACWIKI_TO_MARKDOWN_CANONICAL: dict[str, str] = {
    # Shell: TracWiki 'sh' -> Markdown 'bash' (most common form)
    "sh": "bash",
    # These are identity or prefer the short form in Markdown
    "javascript": "javascript",
    "typescript": "typescript",
    "cpp": "cpp",
    "text": "text",
}

# Languages that are identical in both formats (no mapping needed, but listed for documentation)
# These pass through unchanged: python, java, c, ruby, go, rust, sql, html, css, xml, json, yaml, diff
_IDENTITY_LANGUAGES: frozenset[str] = frozenset(
    {
        "python",
        "java",
        "c",
        "ruby",
        "go",
        "rust",
        "sql",
        "html",
        "css",
        "xml",
        "json",
        "yaml",
        "diff",
        "markdown",
        "md",
        "perl",
        "php",
        "r",
        "scala",
        "swift",
        "kotlin",
        "lua",
        "makefile",
        "dockerfile",
        "nginx",
        "apache",
        "ini",
        "toml",
    }
)


def markdown_to_tracwiki_lang(lang: str) -> str:
    """
    Convert Markdown code fence language to TracWiki processor directive.

    Args:
        lang: Markdown language identifier (e.g., 'bash', 'python', 'js')

    Returns:
        TracWiki processor directive name. Returns input unchanged if no mapping exists.

    Examples:
        >>> markdown_to_tracwiki_lang("bash")
        'sh'
        >>> markdown_to_tracwiki_lang("python")
        'python'
        >>> markdown_to_tracwiki_lang("unknown")
        'unknown'
    """
    # Normalize to lowercase for consistent lookup
    lang_lower = lang.lower()

    # Check explicit mapping first
    if lang_lower in _MARKDOWN_TO_TRACWIKI_MAP:
        return _MARKDOWN_TO_TRACWIKI_MAP[lang_lower]

    # No mapping - pass through unchanged (identity languages and unknown)
    return lang


def tracwiki_to_markdown_lang(processor: str) -> str:
    """
    Convert TracWiki processor directive to Markdown code fence language.

    Args:
        processor: TracWiki processor directive (e.g., 'sh', 'python')

    Returns:
        Markdown language identifier in canonical form. Returns input unchanged
        if no mapping exists.

    Examples:
        >>> tracwiki_to_markdown_lang("sh")
        'bash'
        >>> tracwiki_to_markdown_lang("python")
        'python'
        >>> tracwiki_to_markdown_lang("unknown")
        'unknown'
    """
    # Normalize to lowercase for consistent lookup
    processor_lower = processor.lower()

    # Check explicit mapping first
    if processor_lower in _TRACWIKI_TO_MARKDOWN_CANONICAL:
        return _TRACWIKI_TO_MARKDOWN_CANONICAL[processor_lower]

    # No mapping - pass through unchanged (identity languages and unknown)
    return processor


@dataclass
class ConversionResult:
    """Result of format conversion with metadata and warnings.

    Attributes:
        text: Converted text output
        source_format: Format of input text ('markdown', 'tracwiki', or 'unknown')
        target_format: Format of output text ('markdown' or 'tracwiki')
        converted: True if conversion performed, False if pass-through (formats matched)
        warnings: List of warnings about lossy conversions or unsupported features
    """

    text: str
    source_format: str = "unknown"
    target_format: str = "unknown"
    converted: bool = False
    warnings: list[str] = field(default_factory=list)

    # Backward compatibility: tracwiki property returns text
    @property
    def tracwiki(self) -> str:
        """Backward compatibility property for old code expecting .tracwiki"""
        return self.text


def detect_format_heuristic(text: str) -> str:
    """Heuristic format detection (fallback when capabilities unavailable).

    Priority:
    1. Check for unambiguous markers (TracWiki heading with trailing =, Markdown # without)
    2. Score ambiguous markers (count syntax elements)
    3. Default to 'tracwiki' if unclear

    Returns 'markdown' or 'tracwiki'.
    """
    # Check for unambiguous TracWiki markers
    # Heading with trailing equals: = H1 = or == H2 ==
    if re.search(r"={1,6}\s+.+?\s+={1,6}", text, re.MULTILINE):
        return "tracwiki"

    # Check for unambiguous Markdown markers
    # Heading without trailing equals: # H1 or ## H2
    if re.search(r"^#{1,6}\s+[^=]", text, re.MULTILINE):
        return "markdown"

    # Score ambiguous markers
    md_score = (
        text.count("**")  # Markdown bold
        + text.count("```")  # Markdown code fence
        + text.count("](")  # Markdown link
    )
    tw_score = (
        text.count("'''")  # TracWiki bold
        + text.count("{{{")  # TracWiki code block
        + text.count("[[")  # TracWiki macro/image
    )

    # If scores are equal or unclear, default to TracWiki
    return "markdown" if md_score > tw_score else "tracwiki"


async def auto_convert(
    text: str, config, target_format: str | None = None
) -> ConversionResult:
    """Automatically convert text based on server capabilities and source format.

    If target_format specified, converts to that format.
    If target_format is None, uses server capabilities to determine target:
    - If server has markdown processor: prefer Markdown
    - If server has no markdown processor: use TracWiki

    Args:
        text: Text to convert
        config: Config with Trac server URL/credentials
        target_format: Optional 'markdown' or 'tracwiki' (None = auto-detect from server)

    Returns:
        ConversionResult with converted text and metadata
    """
    from trac_mcp_server.converters.markdown_to_tracwiki import (
        convert_with_warnings as markdown_to_tracwiki,
    )
    from trac_mcp_server.converters.tracwiki_to_markdown import (
        tracwiki_to_markdown,
    )
    from trac_mcp_server.detection.capabilities import (
        get_server_capabilities,
    )

    # Determine target format if not specified
    if target_format is None:
        try:
            caps = await get_server_capabilities(config)
            target_format = (
                "markdown" if caps.markdown_processor else "tracwiki"
            )
        except Exception:
            # Capabilities detection failed, default to TracWiki
            target_format = "tracwiki"

    # Detect source format
    source_format = detect_format_heuristic(text)

    # Convert if formats differ
    if source_format == target_format:
        # Pass-through - no conversion needed
        return ConversionResult(
            text=text,
            source_format=source_format,
            target_format=target_format,
            converted=False,
            warnings=[],
        )
    elif source_format == "markdown" and target_format == "tracwiki":
        return markdown_to_tracwiki(text)
    elif source_format == "tracwiki" and target_format == "markdown":
        return tracwiki_to_markdown(text)
    else:
        # Unknown format combination, pass through
        return ConversionResult(
            text=text,
            source_format=source_format,
            target_format=target_format,
            converted=False,
            warnings=[
                "Unknown format combination - text passed through unchanged"
            ],
        )
