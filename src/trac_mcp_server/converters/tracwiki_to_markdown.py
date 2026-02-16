"""TracWiki to Markdown conversion using regex patterns."""

import re

from .common import ConversionResult, tracwiki_to_markdown_lang


class TracWikiParser:
    """Parser for converting TracWiki syntax to Markdown format."""

    def __init__(self):
        """Initialize parser with empty warnings list."""
        self.warnings: list[str] = []

    def parse(self, tracwiki_text: str) -> ConversionResult:
        """
        Parse TracWiki text and convert to Markdown format.

        This is a best-effort conversion using regex replacements. Unknown TracWiki
        macros and unsupported features pass through unchanged without errors.

        Args:
            tracwiki_text: TracWiki formatted text

        Returns:
            ConversionResult with Markdown text and warnings about lossy conversions
        """
        self.warnings = []
        self._detect_lossy_elements(tracwiki_text)

        text = tracwiki_text
        text = self._convert_processor_cells(text)
        text = self._convert_code_blocks(text)
        text = self._convert_macros(text)
        text = self._convert_headings(text)
        text = self._convert_formatting(text)
        text = self._convert_links(text)
        text = self._convert_lists(text)
        text = self._convert_other_elements(text)
        text = self._convert_tables(text)
        text = self._restore_macro_placeholders(text)

        return ConversionResult(
            text=text,
            source_format="tracwiki",
            target_format="markdown",
            converted=True,
            warnings=self.warnings,
        )

    def _detect_lossy_elements(self, text: str) -> None:
        """Detect lossy elements before conversion and add warnings."""
        # Detect unsupported macros (preserved but not functional)
        if re.search(r"\[\[(?!Image|BR)\w+", text):
            self.warnings.append(
                "Unknown macros detected - preserved as [MACRO: ...] notation (not functional in Markdown)"
            )

        # Detect definition lists
        if re.search(r"^\s*.+?::\s*.+$", text, re.MULTILINE):
            self.warnings.append(
                "Definition lists detected - converted to bold text (semantic preservation)"
            )

        # Detect tables and their features
        has_regular_tables = re.search(r"\|\|.*\|\|", text)
        has_processor_tables = re.search(r"\{\{\{#!t[dh]", text)

        if has_regular_tables:
            # Check for cell spanning (|||| indicates spanning)
            if re.search(r"\|\|\|\|", text):
                self.warnings.append(
                    "Table cell spanning detected - merged into single cell (Markdown limitation)"
                )
            # Check for multi-line rows (backslash continuation)
            if re.search(r"\\\s*\n\s*\|\|", text):
                self.warnings.append(
                    "Multi-line table rows detected - joined into single line (Markdown limitation)"
                )

        # Check for processor-based tables (can exist without regular || tables)
        if has_processor_tables:
            self.warnings.append(
                "Processor-based table cells (#td/#th) detected - converted to plain text (Markdown limitation)"
            )

        # Detect TracLinks
        if re.search(r"(#\d+|ticket:\d+|wiki:\w+|changeset:\w+)", text):
            self.warnings.append(
                "TracLinks detected - preserved as-is (agents can interpret, but not clickable in Markdown renderers)"
            )

    def _convert_processor_cells(self, text: str) -> str:
        """Convert processor-based table cells BEFORE code blocks.

        {{{#!td ... }}} or {{{#!th ... }}} - these are table cells, not code blocks.
        Convert to regular table cell content with marker for later table processing.
        """

        def convert_processor_cell(match):
            cell_type = match.group(1)  # 'td' or 'th'
            content = match.group(2).strip()
            # Replace newlines with spaces for single-line cell content
            content = " ".join(content.split())
            if cell_type == "th":
                return f"||={content}=||"
            else:
                return f"||{content}||"

        return re.sub(
            r"\{\{\{#!(t[dh])\s*(.*?)\s*\}\}\}",
            convert_processor_cell,
            text,
            flags=re.DOTALL,
        )

    def _convert_code_blocks(self, text: str) -> str:
        """Convert code blocks (after processor cells).

        Code block with language: {{{#!lang\ncode\n}}} -> ```lang\ncode\n```
        Code block without language: {{{\ncode\n}}} -> ```\ncode\n```
        """

        # Map TracWiki processor directive to Markdown language (e.g., 'sh' -> 'bash')
        def convert_code_block_with_lang(match: re.Match[str]) -> str:
            tracwiki_lang = match.group(1)
            code = match.group(2)
            md_lang = tracwiki_to_markdown_lang(tracwiki_lang)
            return f"```{md_lang}\n{code}\n```"

        text = re.sub(
            r"\{\{\{#!(\w+)\n(.*?)\n\}\}\}",
            convert_code_block_with_lang,
            text,
            flags=re.DOTALL,
        )
        # Code block without language
        text = re.sub(
            r"\{\{\{\n(.*?)\n\}\}\}",
            r"```\n\1\n```",
            text,
            flags=re.DOTALL,
        )
        return text

    def _convert_macros(self, text: str) -> str:
        """Convert macros (before links, since they use square brackets).

        Images: [[Image(url)]] -> ![](url)
        Line break: [[BR]] -> newline
        Unknown macros: [[MacroName(args)]] -> placeholder for later restoration
        """
        # Images
        text = re.sub(
            r"\[\[Image\(([^)]+)\)\]\]",
            r"![](\1)",
            text,
            flags=re.IGNORECASE,
        )

        # Line break
        text = re.sub(r"\[\[BR\]\]", "\n", text, flags=re.IGNORECASE)

        # TracLinks: Keep as-is since Markdown has no equivalent
        # Examples: #123, ticket:1, wiki:Page, changeset:abc123
        # These should pass through unchanged - they're not ambiguous with Markdown
        # Already valid in plaintext, agents can understand the notation

        # Preserve unknown macros as plaintext for reference
        # [[PageOutline]], [[TOC]], [[RecentChanges]] etc.
        # Convert [[MacroName(args)]] to [MACRO: MacroName(args)]
        # This makes them visible but non-functional (lossy but documented)
        # Use a placeholder that won't be caught by link patterns
        def preserve_unknown_macro(match):
            macro_name = match.group(1)
            args = match.group(2) if match.group(2) else ""
            return f"\x00MACRO:{macro_name}{args}\x00"

        text = re.sub(
            r"\[\[(?!Image|BR)(\w+)(\([^)]*\))?\]\]",
            preserve_unknown_macro,
            text,
            flags=re.IGNORECASE,
        )
        return text

    def _convert_headings(self, text: str) -> str:
        """Convert headings: = H1 = -> # H1.

        Handle headings with or without trailing equals (trailing = is optional in TracWiki).
        """
        # Process from H6 to H1 to avoid conflicts
        for level in range(6, 0, -1):
            marker = "=" * level
            text = re.sub(
                rf"^{re.escape(marker)}\s+(.*?)(?:\s+{re.escape(marker)})?\s*$",
                r"%s \1" % ("#" * level),
                text,
                flags=re.MULTILINE,
            )
        return text

    def _convert_formatting(self, text: str) -> str:
        """Convert bold/italic formatting (bold before italic to handle nesting).

        Bold+italic: '''''text''''' -> ***text***
        Bold: '''text''' -> **text**
        Italic: ''text'' -> *text*
        """
        text = re.sub(r"'''''(.*?)'''''", r"***\1***", text)
        text = re.sub(r"'''(.*?)'''", r"**\1**", text)
        text = re.sub(r"''(.*?)''", r"*\1*", text)
        return text

    def _convert_links(self, text: str) -> str:
        """Convert links.

        Link with text: [url text] -> [text](url)
        Link without text: [url] -> <url>
        """
        # Link with text
        text = re.sub(r"\[(\S+)\s+([^\]]+)\]", r"[\2](\1)", text)

        # Link without text
        # Must not match if followed by (url), which would be a Markdown link we just created
        # Must not match if content starts with [, which would be a macro like [[TOC]]
        def convert_simple_link(match):
            content = match.group(1)
            if content.startswith("["):
                return match.group(0)  # Keep macros unchanged
            return f"<{content}>"

        text = re.sub(r"\[(\S+)\](?!\()", convert_simple_link, text)
        return text

    def _convert_lists(self, text: str) -> str:
        """Convert lists.

        Unordered lists: ' * item' -> '- item'
        Handle nested lists: ' * * item' -> ' - - item'
        Ordered lists are already compatible: ' 1. item' is valid in both
        """

        def convert_list_marker(match):
            leading_space = match.group(1)
            full_match = match.group(0)
            asterisk_part = full_match[len(leading_space) :]
            # Count how many '* ' patterns there are
            count = asterisk_part.count("* ")
            return leading_space + "- " * count

        text = re.sub(
            r"^( +)(\* )+",
            convert_list_marker,
            text,
            flags=re.MULTILINE,
        )
        return text

    def _convert_other_elements(self, text: str) -> str:
        """Convert other elements (horizontal rules, blockquotes, definition lists).

        Horizontal rule: ---- -> ---
        Blockquote: two-space indent -> > prefix
        Definition lists: term:: definition -> **term**: definition
        """
        # Horizontal rule
        text = re.sub(r"^----+\s*$", r"---", text, flags=re.MULTILINE)

        # Blockquote: two-space indent -> > prefix
        # This is tricky because two-space indent is also used for other things in TracWiki
        # We'll do a simple conversion for lines that start with exactly two spaces
        def convert_blockquote(match):
            lines = match.group(0).split("\n")
            converted = []
            for line in lines:
                if line.startswith("  ") and not line.startswith("   "):
                    converted.append("> " + line[2:])
                else:
                    converted.append(line)
            return "\n".join(converted)

        # Apply blockquote conversion to paragraphs (between blank lines)
        text = re.sub(
            r"(?:^|\n\n)((?:  [^\n]+\n?)+)",
            convert_blockquote,
            text,
            flags=re.MULTILINE,
        )

        # Definition lists: term:: definition -> **term**: definition
        # TracWiki uses :: separator, Markdown has no native definition list
        # Convert to bold term + regular text (semantic preservation)
        text = re.sub(
            r"^(\s*)(.+?)::\s*(.+)$",
            r"\1**\2**: \3",
            text,
            flags=re.MULTILINE,
        )

        return text

    def _convert_tables(self, text: str) -> str:
        """Convert tables: TracWiki ||c1||c2|| -> Markdown |c1|c2|.

        Enhanced conversion with header detection, alignment, spanning, and multi-line support.
        """
        # Handle multi-line rows (backslash continuation) before parsing
        # Join lines that end with \ followed by lines starting with ||
        text = re.sub(r"\\\s*\n\s*\|\|", "||", text)

        # Note: Processor-based table cells ({{{#!td}}} / {{{#!th}}}) are already
        # handled at the beginning of conversion, before code block processing.

        # Parse and convert table rows
        lines = text.split("\n")
        result = []
        table_rows = []  # Accumulate table rows for processing
        table_alignments = []  # Track alignments from first row

        def flush_table():
            """Process accumulated table rows and add to result."""
            nonlocal table_rows, table_alignments
            if not table_rows:
                return

            # Determine number of columns from first row
            num_cols = len(table_rows[0][0]) if table_rows else 0

            # Build separator row from alignments
            if table_alignments:
                separator = (
                    "|"
                    + "|".join(
                        self._alignment_to_separator(a)
                        for a in table_alignments
                    )
                    + "|"
                )
            else:
                separator = "|" + " --- |" * num_cols

            # Check if first row is header
            first_cells, _, first_is_header = table_rows[0]

            if first_is_header:
                # First row is header - use it directly
                result.append("| " + " | ".join(first_cells) + " |")
                result.append(separator)
                # Add remaining rows as body
                for cells, _, _ in table_rows[1:]:
                    result.append("| " + " | ".join(cells) + " |")
            else:
                # No header row - first row becomes header (Markdown requires header)
                result.append("| " + " | ".join(first_cells) + " |")
                result.append(separator)
                # Add remaining rows as body
                for cells, _, _ in table_rows[1:]:
                    result.append("| " + " | ".join(cells) + " |")

            table_rows = []
            table_alignments = []

        for line in lines:
            if re.match(r"^\s*\|\|.*\|\|\s*$", line):
                cells, aligns, is_header = self._parse_tracwiki_row(
                    line
                )
                table_rows.append((cells, aligns, is_header))
                # Use alignments from first row
                if not table_alignments:
                    table_alignments = aligns
            else:
                # End of table - flush accumulated rows
                flush_table()
                result.append(line)

        # Flush any remaining table at end of document
        flush_table()

        return "\n".join(result)

    def _detect_cell_alignment(self, cell_content: str) -> str | None:
        """Detect TracWiki cell alignment from whitespace.

        TracWiki alignment:
        - Left: 'text ' (flush left, space right)
        - Right: ' text' (space left, flush right)
        - Center: ' text ' (space both sides)

        Returns: 'left', 'right', 'center', or None
        """
        if not cell_content:
            return None
        has_leading_space = (
            cell_content.startswith(" ") and len(cell_content) > 1
        )
        has_trailing_space = (
            cell_content.endswith(" ") and len(cell_content) > 1
        )
        if has_leading_space and has_trailing_space:
            return "center"
        elif has_leading_space:
            return "right"
        elif has_trailing_space:
            return "left"
        return None

    def _parse_tracwiki_row(
        self, row: str
    ) -> tuple[list[str], list[str | None], bool]:
        """Parse a TracWiki table row into cells with alignment info.

        Returns: (cells, alignments, is_header)
        - cells: list of cell content strings
        - alignments: list of alignment values ('left', 'right', 'center', None)
        - is_header: True if this row contains header cells (||= ... =||)
        """
        cells: list[str] = []
        alignments: list[str | None] = []
        is_header = False

        # Check if row has header markers
        if re.search(r"\|\|=.*=\|\|", row):
            is_header = True

        # Split by || but preserve empty cells for spanning detection
        # First, strip leading/trailing ||
        row = row.strip()
        if row.startswith("||"):
            row = row[2:]
        if row.endswith("||"):
            row = row[:-2]

        # Split by ||
        raw_cells = row.split("||")

        # Process cells, handling spanning (empty cells merge with previous)
        pending_span = 0
        for raw_cell in raw_cells:
            if raw_cell == "":
                # Empty cell indicates spanning - will merge with next non-empty
                pending_span += 1
            else:
                # Extract content, handling header markers
                cell = raw_cell

                # Check for header markers: =text= or = text =
                header_match = re.match(r"^=(.*)=$", cell.strip())
                if header_match:
                    cell = header_match.group(1)
                    is_header = True

                # Detect alignment before stripping
                align = self._detect_cell_alignment(cell)

                # Strip and clean the content
                cell = cell.strip()

                # If there were preceding empty cells, this is a spanned cell
                # Add indicator text if spanning occurred
                if pending_span > 0:
                    # Markdown doesn't support spanning - merge content
                    cell = (
                        f"[span:{pending_span + 1}] {cell}"
                        if cell
                        else f"[span:{pending_span + 1}]"
                    )
                    pending_span = 0

                cells.append(cell)
                alignments.append(align)

        # Handle trailing empty cells (would indicate colspan to end)
        # These are already stripped off, but raw_cells might have them
        if pending_span > 0 and cells:
            cells[-1] = f"{cells[-1]} [span:{pending_span + 1}]"

        return cells, alignments, is_header

    def _alignment_to_separator(self, align: str | None) -> str:
        """Convert alignment to Markdown separator format."""
        match align:
            case "left":
                return ":---"
            case "right":
                return "---:"
            case "center":
                return ":---:"
            case _:
                return "---"

    def _restore_macro_placeholders(self, text: str) -> str:
        """Restore macro placeholders.

        Convert \x00MACRO:Name(args)\x00 back to [MACRO: Name(args)]
        """
        return re.sub(
            r"\x00MACRO:([^)]+(?:\([^)]*\))?)\x00", r"[MACRO: \1]", text
        )


def tracwiki_to_markdown(tracwiki_text: str) -> ConversionResult:
    """
    Convert TracWiki text to Markdown format.

    This is a best-effort conversion using regex replacements. Unknown TracWiki
    macros and unsupported features pass through unchanged without errors.

    Args:
        tracwiki_text: TracWiki formatted text

    Returns:
        ConversionResult with Markdown text and warnings about lossy conversions
    """
    parser = TracWikiParser()
    return parser.parse(tracwiki_text)
