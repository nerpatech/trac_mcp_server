"""Markdown to TracWiki conversion using mistune AST rendering."""

import re
from typing import Any

import mistune

from .common import ConversionResult, markdown_to_tracwiki_lang


class TracWikiRenderer(mistune.BaseRenderer):
    """Renderer that converts Markdown AST to TracWiki syntax."""

    NAME = "tracwiki"

    def __init__(self):
        """Initialize renderer with state tracking for table rendering."""
        super().__init__()
        # Track column alignments for current table
        self._table_alignments: list[str | None] = []

    def text(self, text: str) -> str:
        """Render plain text."""
        return text

    def emphasis(self, text: str) -> str:
        """Render italic text (single emphasis)."""
        return f"''{text}''"

    def strong(self, text: str) -> str:
        """Render bold text (double emphasis)."""
        return f"'''{text}'''"

    def codespan(self, text: str) -> str:
        """Render inline code."""
        return f"`{text}`"

    def linebreak(self) -> str:
        """Render line break."""
        return "[[BR]]\n"

    def softbreak(self) -> str:
        """Render soft break."""
        return "\n"

    def blank_line(self) -> str:
        """Render blank line."""
        return ""

    def heading(self, text: str, level: int, **attrs) -> str:
        """Render heading.

        TracWiki heading syntax uses leading = markers (trailing = optional).
        We produce the canonical form with trailing markers for readability:
        = H1 =
        == H2 ==
        """
        marker = "=" * level
        return f"{marker} {text} {marker}\n"

    def paragraph(self, text: str) -> str:
        """Render paragraph."""
        return f"{text}\n\n"

    def block_text(self, text: str) -> str:
        """Render block text."""
        return text

    def block_code(self, code: str, info: str | None = None) -> str:
        """Render code block.

        TracWiki syntax:
        {{{#!language
        code
        }}}

        Language identifiers are mapped from Markdown to TracWiki equivalents
        (e.g., 'bash' -> 'sh').
        """
        code = code.rstrip("\n")
        if info:
            # Map Markdown language to TracWiki processor directive
            tracwiki_lang = markdown_to_tracwiki_lang(info)
            return f"{{{{{{#!{tracwiki_lang}\n{code}\n}}}}}}\n"
        else:
            return f"{{{{{{\n{code}\n}}}}}}\n"

    def block_quote(self, text: str) -> str:
        """Render blockquote.

        TracWiki uses two-space indent for quotes.
        """
        lines = text.rstrip("\n").split("\n")
        quoted = "\n".join(f"  {line}" for line in lines)
        return f"{quoted}\n"

    def block_html(self, html: str) -> str:
        """Render block HTML (pass through)."""
        return html + "\n"

    def block_error(self, text: str) -> str:
        """Render block error."""
        return text

    def thematic_break(self) -> str:
        """Render horizontal rule."""
        return "----\n"

    def list(self, text: str, ordered: bool, **attrs) -> str:
        """Render list."""
        return text

    def list_item(self, text: str) -> str:
        """Render list item.

        TracWiki uses space prefix:
        Unordered: ' * item'
        Ordered: ' 1. item'
        Nested: ' * * nested'

        The nesting is handled by tracking depth in the render_token override.
        """
        # Clean up extra newlines from nested content
        text = text.rstrip("\n")
        return text + "\n"

    def link(self, text: str, url: str, title=None) -> str:
        """Render link.

        Markdown: [text](url)
        TracWiki: [url text] for external URLs
                  [wiki:page text] for internal wiki pages
        """
        # External URLs - no prefix needed
        if url.startswith(("http://", "https://", "ftp://", "mailto:")):
            return f"[{url} {text}]"

        # Anchor-only links - keep as-is
        if url.startswith("#"):
            return f"[{url} {text}]"

        # Internal wiki links - add wiki: prefix
        return f"[wiki:{url} {text}]"

    def image(self, text: str, url: str, title=None) -> str:
        """Render image.

        Markdown: ![alt](url)
        TracWiki: [[Image(url)]]
        """
        return f"[[Image({url})]]"

    def newline(self) -> str:
        """Render newline."""
        return ""

    def inline_html(self, html: str) -> str:
        """Render inline HTML (pass through)."""
        return html

    # Table rendering methods for GFM tables
    def table(self, text: str) -> str:
        """Render complete table.

        TracWiki tables use ||cell|| syntax.
        Tables are block elements and should be separated from other content.
        """
        # Reset alignments after table is complete
        self._table_alignments = []
        # Table is a block element, add trailing newlines for paragraph separation
        return text.rstrip("\n") + "\n\n"

    def table_head(self, text: str) -> str:
        """Render table header section.

        Header cells are concatenated by mistune with || between them.
        We strip the trailing || from cells and wrap the whole row.
        """
        # Cells are concatenated with || between them (each cell adds trailing ||)
        # Remove the trailing || and wrap with || on both ends
        text = text.rstrip("|")
        return f"||{text}||\n"

    def table_body(self, text: str) -> str:
        """Render table body section."""
        return text

    def table_row(self, text: str) -> str:
        """Render table row.

        Body cells are concatenated by mistune with || between them.
        We strip the trailing || from cells and wrap the whole row.
        """
        # Cells are concatenated with || between them (each cell adds trailing ||)
        # Remove the trailing || and wrap with || on both ends
        text = text.rstrip("|")
        return f"||{text}||\n"

    def table_cell(
        self, text: str, align: str | None = None, head: bool = False
    ) -> str:
        """Render table cell.

        Args:
            text: Cell content
            align: Alignment ('left', 'center', 'right', or None)
            head: True if this is a header cell

        TracWiki alignment is determined by whitespace:
        - Left aligned: ||text || (text flush left, space right)
        - Right aligned: || text|| (space left, text flush right)
        - Centered: || text || (space both sides)

        TracWiki header cells use ||= Header =|| syntax.

        Note: Cells are concatenated by mistune. We add || after each cell,
        and table_row/table_head will strip the trailing || and wrap properly.
        """
        # For header cells, wrap with = markers and apply alignment
        if head:
            # Handle empty cells
            if not text:
                cell_content = ""
            elif align == "left":
                cell_content = f"={text} ="
            elif align == "right":
                cell_content = f"= {text}="
            elif align == "center":
                cell_content = f"= {text} ="
            else:
                # No alignment: minimal spacing
                cell_content = f"={text}="
        else:
            # Apply TracWiki alignment via whitespace for body cells
            if align == "left":
                # Left aligned: text flush left, space on right
                cell_content = f"{text} "
            elif align == "right":
                # Right aligned: space on left, text flush right
                cell_content = f" {text}"
            elif align == "center":
                # Centered: space on both sides
                cell_content = f" {text} "
            else:
                # No alignment: just the text
                cell_content = text

        # Add || separator after cell (will be concatenated with next cell)
        return cell_content + "||"

    def render_token(self, token: dict[str, Any], state) -> str:
        """Override token rendering to handle list depth tracking and extract text/attrs."""
        # Get the token type
        token_type: str = token.get("type") or ""
        func = self._get_method(token_type)
        attrs = token.get("attrs")

        # For lists, track ordered state and reset item counter
        if token_type == "list":
            ordered = token.get("attrs", {}).get("ordered", False)
            depth = getattr(
                state, "list_depth", -1
            )  # Start at -1 so first level is 0

            # Save current state
            old_ordered = getattr(state, "list_ordered", False)
            old_depth = depth
            old_item_num = getattr(state, "list_item_num", 0)

            # Set new state
            state.list_ordered = ordered  # type: ignore[attr-defined]  # mistune BlockState dynamic attr
            state.list_depth = depth + 1  # type: ignore[attr-defined]  # mistune BlockState dynamic attr
            state.list_item_num = 0  # type: ignore[attr-defined]  # mistune BlockState dynamic attr

            # Render children
            if "children" in token:
                text = self.render_tokens(token["children"], state)
            else:
                text = ""

            # Restore state
            state.list_ordered = old_ordered  # type: ignore[attr-defined]  # mistune BlockState dynamic attr
            state.list_depth = old_depth  # type: ignore[attr-defined]  # mistune BlockState dynamic attr
            state.list_item_num = old_item_num  # type: ignore[attr-defined]  # mistune BlockState dynamic attr

            # Call list renderer with text and ordered flag
            if attrs:
                return func(text, **attrs)
            else:
                return func(text, False)

        # For list items, we need to determine depth and type
        elif token_type == "list_item":
            # Track list depth from state
            depth = getattr(state, "list_depth", 0)

            # Check if parent list is ordered
            ordered = getattr(state, "list_ordered", False)

            # Increment and get item number
            item_num = getattr(state, "list_item_num", 0) + 1
            state.list_item_num = item_num  # type: ignore[attr-defined]  # mistune BlockState dynamic attr

            # Determine marker
            if ordered:
                marker = f"{item_num}."
            else:
                marker = "*"

            # Render children - check if there's a nested list
            if "children" in token:
                children = token["children"]
                # Separate inline content from nested lists
                inline_parts = []
                nested_lists = []

                for child in children:
                    if child.get("type") == "list":
                        nested_lists.append(child)
                    else:
                        inline_parts.append(child)

                # Render inline content
                if inline_parts:
                    text = self.render_tokens(inline_parts, state)
                else:
                    text = ""

                # Render nested lists (they handle their own newlines)
                if nested_lists:
                    nested_text = self.render_tokens(
                        nested_lists, state
                    )
                    # The nested list adds its items directly, don't add to text
                    nested_text = nested_text.rstrip("\n")
                else:
                    nested_text = ""
            else:
                text = token.get("raw", "")
                nested_text = ""

            # Build TracWiki list item with proper depth
            # TracWiki uses indentation for nesting: 1 space for level 0, +2 spaces per level
            # Depth 0: " * item" (1 space + marker)
            # Depth 1: "   * item" (3 spaces + marker)
            # Depth 2: "     * item" (5 spaces + marker)
            indent = " " * (depth * 2 + 1)
            prefix = f"{indent}{marker}"

            text = text.rstrip("\n")

            # Combine text and nested list
            if nested_text:
                return f"{prefix} {text}\n{nested_text}\n"
            else:
                return f"{prefix} {text}\n"

        # Default rendering: extract text from raw, text, or children, pass attrs
        else:
            if "raw" in token:
                text = token["raw"]
            elif "text" in token:
                # Used by table_cell tokens
                text = token["text"]
            elif "children" in token:
                text = self.render_tokens(token["children"], state)
            else:
                # No text content, just call with attrs
                if attrs:
                    return func(**attrs)
                else:
                    return func()

            # Call function with text and attrs
            if attrs:
                return func(text, **attrs)
            else:
                return func(text)


def markdown_to_tracwiki(markdown_text: str) -> str:
    """
    Convert Markdown text to TracWiki format.

    Args:
        markdown_text: Markdown formatted text

    Returns:
        TracWiki formatted text
    """
    # Create renderer and parser with table plugin enabled
    renderer = TracWikiRenderer()
    markdown = mistune.create_markdown(
        renderer=renderer, plugins=["table"]
    )

    # Parse and render
    result: str = markdown(markdown_text)  # type: ignore[assignment]

    # Clean up extra newlines (but preserve double newlines for paragraph separation)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = result.rstrip("\n")

    return result


def convert_with_warnings(markdown_text: str) -> ConversionResult:
    """
    Convert Markdown to TracWiki and detect unsupported features.

    Args:
        markdown_text: Markdown formatted text

    Returns:
        ConversionResult with TracWiki text and any warnings
    """
    warnings = []

    # Tables are now fully supported via mistune table plugin

    # Check for HTML tags
    if re.search(r"<[a-zA-Z][^>]*>", markdown_text):
        warnings.append(
            "HTML tags detected - these may not render correctly in TracWiki."
        )

    # Check for TOC macros
    if re.search(r"\[TOC\]|\[\[TOC\]\]", markdown_text, re.IGNORECASE):
        warnings.append(
            "TOC macro detected - use [[PageOutline]] in TracWiki instead."
        )

    # Convert the markdown
    tracwiki = markdown_to_tracwiki(markdown_text)

    return ConversionResult(
        text=tracwiki,
        source_format="markdown",
        target_format="tracwiki",
        converted=True,
        warnings=warnings,
    )
