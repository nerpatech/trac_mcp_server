"""
Tests for Markdown to TracWiki converter and TracWiki to Markdown converter.
"""

import unittest
from unittest.mock import MagicMock, patch

from trac_mcp_server.converters import (
    ConversionResult,
    convert_with_warnings,
    markdown_to_tracwiki,
    tracwiki_to_markdown,
)
from trac_mcp_server.converters.common import (
    markdown_to_tracwiki_lang,
    tracwiki_to_markdown_lang,
)


class TestTracWikiConverter(unittest.TestCase):
    """Test Markdown to TracWiki conversion."""

    def test_heading_level_1(self):
        """Test H1 heading conversion."""
        result = markdown_to_tracwiki("# Heading 1")
        self.assertEqual(result, "= Heading 1 =")

    def test_heading_level_2(self):
        """Test H2 heading conversion."""
        result = markdown_to_tracwiki("## Heading 2")
        self.assertEqual(result, "== Heading 2 ==")

    def test_heading_level_3(self):
        """Test H3 heading conversion."""
        result = markdown_to_tracwiki("### Heading 3")
        self.assertEqual(result, "=== Heading 3 ===")

    def test_heading_level_4(self):
        """Test H4 heading conversion."""
        result = markdown_to_tracwiki("#### Heading 4")
        self.assertEqual(result, "==== Heading 4 ====")

    def test_bold_text(self):
        """Test bold text conversion."""
        result = markdown_to_tracwiki("**bold text**")
        self.assertEqual(result, "'''bold text'''")

    def test_italic_text(self):
        """Test italic text conversion."""
        result = markdown_to_tracwiki("*italic text*")
        self.assertEqual(result, "''italic text''")

    def test_bold_italic_text(self):
        """Test bold italic text conversion."""
        result = markdown_to_tracwiki("***bold italic***")
        self.assertEqual(result, "'''''bold italic'''''")

    def test_inline_code(self):
        """Test inline code conversion."""
        result = markdown_to_tracwiki("`inline code`")
        self.assertEqual(result, "`inline code`")

    def test_code_block_with_language(self):
        """Test code block with language conversion."""
        markdown = """```python
def hello():
    print("world")
```"""
        expected = """{{{#!python
def hello():
    print("world")
}}}"""
        result = markdown_to_tracwiki(markdown)
        self.assertEqual(result, expected)

    def test_code_block_without_language(self):
        """Test code block without language conversion."""
        markdown = """```
plain code
```"""
        expected = """{{{
plain code
}}}"""
        result = markdown_to_tracwiki(markdown)
        self.assertEqual(result, expected)

    def test_link_conversion(self):
        """Test external link conversion (https)."""
        result = markdown_to_tracwiki(
            "[link text](https://example.com)"
        )
        self.assertEqual(result, "[https://example.com link text]")

    def test_link_conversion_http(self):
        """Test external link conversion (http)."""
        result = markdown_to_tracwiki("[link text](http://example.com)")
        self.assertEqual(result, "[http://example.com link text]")

    def test_link_conversion_ftp(self):
        """Test external link conversion (ftp)."""
        result = markdown_to_tracwiki(
            "[file](ftp://ftp.example.com/file.txt)"
        )
        self.assertEqual(
            result, "[ftp://ftp.example.com/file.txt file]"
        )

    def test_link_conversion_mailto(self):
        """Test mailto link conversion."""
        result = markdown_to_tracwiki(
            "[email](mailto:test@example.com)"
        )
        self.assertEqual(result, "[mailto:test@example.com email]")

    def test_internal_wiki_link(self):
        """Test internal wiki link gets wiki: prefix."""
        result = markdown_to_tracwiki(
            "[Phase 1](Planning/Phases/Phase01)"
        )
        self.assertEqual(
            result, "[wiki:Planning/Phases/Phase01 Phase 1]"
        )

    def test_internal_wiki_link_simple(self):
        """Test simple wiki page link gets wiki: prefix."""
        result = markdown_to_tracwiki("[Home](HomePage)")
        self.assertEqual(result, "[wiki:HomePage Home]")

    def test_internal_wiki_link_relative_parent(self):
        """Test relative wiki link with ../ gets wiki: prefix."""
        result = markdown_to_tracwiki("[Back](../Overview)")
        self.assertEqual(result, "[wiki:../Overview Back]")

    def test_internal_wiki_link_relative_current(self):
        """Test relative wiki link with ./ gets wiki: prefix."""
        result = markdown_to_tracwiki("[Current](./SubPage)")
        self.assertEqual(result, "[wiki:./SubPage Current]")

    def test_anchor_link(self):
        """Test anchor-only link has no prefix."""
        result = markdown_to_tracwiki("[Section](#section)")
        self.assertEqual(result, "[#section Section]")

    def test_image_conversion(self):
        """Test image conversion."""
        result = markdown_to_tracwiki("![alt text](image.png)")
        self.assertEqual(result, "[[Image(image.png)]]")

    def test_unordered_list(self):
        """Test unordered list conversion."""
        markdown = """- item 1
- item 2
- item 3"""
        expected = """ * item 1
 * item 2
 * item 3"""
        result = markdown_to_tracwiki(markdown)
        self.assertEqual(result, expected)

    def test_ordered_list(self):
        """Test ordered list conversion."""
        markdown = """1. first
2. second
3. third"""
        expected = """ 1. first
 2. second
 3. third"""
        result = markdown_to_tracwiki(markdown)
        self.assertEqual(result, expected)

    def test_nested_unordered_list(self):
        """Test nested unordered list conversion.

        TracWiki uses indentation for nesting:
        - Level 0: ' * item' (1 space + marker)
        - Level 1: '   * item' (3 spaces + marker)
        """
        markdown = """- item 1
  - nested 1
  - nested 2
- item 2"""
        expected = """ * item 1
   * nested 1
   * nested 2
 * item 2"""
        result = markdown_to_tracwiki(markdown)
        self.assertEqual(result, expected)

    def test_nested_unordered_list_with_bold(self):
        """Test nested unordered list with formatted content (like README Features).

        This specifically tests the bug fix where nested lists were producing
        double asterisks like ' * * item' instead of proper indentation.
        """
        markdown = """- **Ticket Operations**
  - Search and query tickets
  - Read ticket details"""
        expected = """ * '''Ticket Operations'''
   * Search and query tickets
   * Read ticket details"""
        result = markdown_to_tracwiki(markdown)
        self.assertEqual(result, expected)
        # Verify no double asterisks appear
        self.assertNotIn(" * *", result)

    def test_deeply_nested_unordered_list(self):
        """Test deeply nested (3 levels) unordered list conversion.

        TracWiki indentation pattern: (depth * 2 + 1) leading spaces
        - Level 0: ' * item' (1 space)
        - Level 1: '   * item' (3 spaces)
        - Level 2: '     * item' (5 spaces)
        """
        markdown = """- level 0
  - level 1
    - level 2"""
        expected = """ * level 0
   * level 1
     * level 2"""
        result = markdown_to_tracwiki(markdown)
        self.assertEqual(result, expected)

    def test_nested_ordered_list(self):
        """Test nested ordered list conversion with proper indentation."""
        markdown = """1. first
   1. nested first
   2. nested second
2. second"""
        expected = """ 1. first
   1. nested first
   2. nested second
 2. second"""
        result = markdown_to_tracwiki(markdown)
        self.assertEqual(result, expected)

    def test_blockquote(self):
        """Test blockquote conversion."""
        result = markdown_to_tracwiki("> quoted text")
        self.assertEqual(result, "  quoted text")

    def test_horizontal_rule(self):
        """Test horizontal rule conversion."""
        result = markdown_to_tracwiki("---")
        self.assertEqual(result, "----")

    def test_paragraph_separation(self):
        """Test paragraph separation with blank lines."""
        markdown = """First paragraph.

Second paragraph."""
        result = markdown_to_tracwiki(markdown)
        self.assertIn("\n\n", result)

    def test_convert_with_warnings_no_warnings(self):
        """Test conversion without warnings."""
        result = convert_with_warnings("# Simple heading")
        self.assertIsInstance(result, ConversionResult)
        self.assertEqual(result.tracwiki, "= Simple heading =")
        self.assertEqual(len(result.warnings), 0)

    def test_convert_with_warnings_table_converted(self):
        """Test tables are converted without warning (now supported)."""
        markdown = """| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |"""
        result = convert_with_warnings(markdown)
        # Tables should now be converted without warnings
        self.assertFalse(
            any("table" in w.lower() for w in result.warnings)
        )
        # Output should be valid TracWiki
        self.assertIn("||=Header 1=||=Header 2=||", result.text)
        self.assertIn("||Cell 1||Cell 2||", result.text)

    def test_convert_with_warnings_html_detected(self):
        """Test warning for HTML tags."""
        markdown = "Some text with <div>HTML</div> tags"
        result = convert_with_warnings(markdown)
        self.assertGreater(len(result.warnings), 0)
        self.assertTrue(
            any("html" in w.lower() for w in result.warnings)
        )

    def test_mixed_formatting(self):
        """Test mixed formatting in single line."""
        result = markdown_to_tracwiki(
            "This is **bold** and *italic* text"
        )
        self.assertIn("'''bold'''", result)
        self.assertIn("''italic''", result)

    def test_multiple_headings(self):
        """Test multiple headings in document."""
        markdown = """# Title
## Section
### Subsection"""
        result = markdown_to_tracwiki(markdown)
        self.assertIn("= Title =", result)
        self.assertIn("== Section ==", result)
        self.assertIn("=== Subsection ===", result)


class TestTracWikiToMarkdownConverter(unittest.TestCase):
    """Test TracWiki to Markdown conversion."""

    def test_heading_level_1(self):
        """Test H1 heading conversion."""
        result = tracwiki_to_markdown("= Heading 1 =")
        self.assertEqual(result.text, "# Heading 1")

    def test_heading_level_2(self):
        """Test H2 heading conversion."""
        result = tracwiki_to_markdown("== Heading 2 ==")
        self.assertEqual(result.text, "## Heading 2")

    def test_heading_level_3(self):
        """Test H3 heading conversion."""
        result = tracwiki_to_markdown("=== Heading 3 ===")
        self.assertEqual(result.text, "### Heading 3")

    def test_heading_level_4(self):
        """Test H4 heading conversion."""
        result = tracwiki_to_markdown("==== Heading 4 ====")
        self.assertEqual(result.text, "#### Heading 4")

    def test_heading_level_5(self):
        """Test H5 heading conversion."""
        result = tracwiki_to_markdown("===== Heading 5 =====")
        self.assertEqual(result.text, "##### Heading 5")

    def test_heading_level_6(self):
        """Test H6 heading conversion."""
        result = tracwiki_to_markdown("====== Heading 6 ======")
        self.assertEqual(result.text, "###### Heading 6")

    def test_heading_without_trailing_equals(self):
        """Trailing = is optional in TracWiki."""
        result = tracwiki_to_markdown("= Heading 1")
        self.assertEqual(result.text, "# Heading 1")

    def test_heading_h2_without_trailing_equals(self):
        """Trailing == is optional in TracWiki."""
        result = tracwiki_to_markdown("== Heading 2")
        self.assertEqual(result.text, "## Heading 2")

    def test_heading_h3_without_trailing_equals(self):
        """Trailing === is optional in TracWiki."""
        result = tracwiki_to_markdown("=== Heading 3")
        self.assertEqual(result.text, "### Heading 3")

    def test_bold_text(self):
        """Test bold text conversion."""
        result = tracwiki_to_markdown("'''bold text'''")
        self.assertEqual(result.text, "**bold text**")

    def test_italic_text(self):
        """Test italic text conversion."""
        result = tracwiki_to_markdown("''italic text''")
        self.assertEqual(result.text, "*italic text*")

    def test_bold_italic_text(self):
        """Test bold italic text conversion."""
        result = tracwiki_to_markdown("'''''bold italic'''''")
        self.assertEqual(result.text, "***bold italic***")

    def test_link_with_text(self):
        """Test link with text conversion."""
        result = tracwiki_to_markdown("[https://example.com link text]")
        self.assertEqual(
            result.text, "[link text](https://example.com)"
        )

    def test_link_without_text(self):
        """Test link without text conversion."""
        result = tracwiki_to_markdown("[https://example.com]")
        self.assertEqual(result.text, "<https://example.com>")

    def test_code_block_with_language(self):
        """Test code block with language conversion."""
        tracwiki = """{{{#!python
def hello():
    print("world")
}}}"""
        expected = """```python
def hello():
    print("world")
```"""
        result = tracwiki_to_markdown(tracwiki)
        self.assertEqual(result.text, expected)

    def test_code_block_without_language(self):
        """Test code block without language conversion."""
        tracwiki = """{{{
plain code
}}}"""
        expected = """```
plain code
```"""
        result = tracwiki_to_markdown(tracwiki)
        self.assertEqual(result.text, expected)

    def test_unordered_list(self):
        """Test unordered list conversion."""
        tracwiki = """ * item 1
 * item 2
 * item 3"""
        expected = """ - item 1
 - item 2
 - item 3"""
        result = tracwiki_to_markdown(tracwiki)
        self.assertEqual(result.text, expected)

    def test_ordered_list(self):
        """Test ordered list conversion."""
        tracwiki = """ 1. first
 2. second
 3. third"""
        # Ordered lists are already compatible
        result = tracwiki_to_markdown(tracwiki)
        self.assertEqual(result.text, tracwiki)

    def test_horizontal_rule(self):
        """Test horizontal rule conversion."""
        result = tracwiki_to_markdown("----")
        self.assertEqual(result.text, "---")

    def test_line_break(self):
        """Test line break conversion."""
        result = tracwiki_to_markdown("Line one[[BR]]Line two")
        self.assertEqual(result.text, "Line one\nLine two")

    def test_line_break_case_insensitive(self):
        """Test line break is case insensitive."""
        result = tracwiki_to_markdown("Line one[[br]]Line two")
        self.assertEqual(result.text, "Line one\nLine two")

    def test_image(self):
        """Test image conversion."""
        result = tracwiki_to_markdown("[[Image(screenshot.png)]]")
        self.assertEqual(result.text, "![](screenshot.png)")

    def test_image_case_insensitive(self):
        """Test image macro is case insensitive."""
        result = tracwiki_to_markdown("[[image(screenshot.png)]]")
        self.assertEqual(result.text, "![](screenshot.png)")

    def test_unknown_macro_passthrough(self):
        """Test unknown macros are preserved with [MACRO: ...] notation."""
        result = tracwiki_to_markdown("[[TOC]]")
        self.assertEqual(result.text, "[MACRO: TOC]")

    def test_blockquote(self):
        """Test blockquote conversion."""
        tracwiki = """  This is quoted
  Another quoted line"""
        expected = """> This is quoted
> Another quoted line"""
        result = tracwiki_to_markdown(tracwiki)
        self.assertEqual(result.text, expected)

    def test_mixed_content(self):
        """Test real-world mixed content."""
        tracwiki = """= Bug Report =

This is a '''critical''' bug in the ''login'' system.

Reproduction steps:
 1. Navigate to [https://example.com login page]
 2. Enter invalid credentials
 3. Observe error

Code that fails:
{{{#!python
def login(user, password):
    return False
}}}

See screenshot: [[Image(error.png)]]"""

        result = tracwiki_to_markdown(tracwiki)

        # Check key conversions
        self.assertIn("# Bug Report", result.text)
        self.assertIn("**critical**", result.text)
        self.assertIn("*login*", result.text)
        self.assertIn(
            "1. Navigate to [login page](https://example.com)",
            result.text,
        )
        self.assertIn("```python", result.text)
        self.assertIn("![](error.png)", result.text)

    def test_inline_code_passthrough(self):
        """Test inline code passes through unchanged."""
        result = tracwiki_to_markdown("`inline code`")
        self.assertEqual(result.text, "`inline code`")

    def test_nested_lists(self):
        """Test nested list conversion with proper indentation format."""
        tracwiki = """ * item 1
   * nested 1
   * nested 2
 * item 2"""
        expected = """ - item 1
   - nested 1
   - nested 2
 - item 2"""
        result = tracwiki_to_markdown(tracwiki)
        self.assertEqual(result.text, expected)

    def test_multiple_headings(self):
        """Test multiple headings in document."""
        tracwiki = """= Title =
== Section ==
=== Subsection ==="""
        expected = """# Title
## Section
### Subsection"""
        result = tracwiki_to_markdown(tracwiki)
        self.assertEqual(result.text, expected)

    def test_mixed_formatting_inline(self):
        """Test mixed formatting in single line."""
        result = tracwiki_to_markdown(
            "This is '''bold''' and ''italic'' text"
        )
        self.assertEqual(
            result.text, "This is **bold** and *italic* text"
        )

    def test_longer_horizontal_rule(self):
        """Test longer horizontal rule converts."""
        result = tracwiki_to_markdown("--------")
        self.assertEqual(result.text, "---")


class TestTracWikiEnhancements(unittest.TestCase):
    """Test TracWiki to Markdown enhancements (macros, TracLinks, tables, etc)."""

    def test_tracwiki_unknown_macros(self):
        """Test unknown macros are preserved with [MACRO: ...] notation."""
        result = tracwiki_to_markdown("[[PageOutline]]")
        self.assertIn("[MACRO: PageOutline]", result.text)
        self.assertTrue(
            any("macro" in w.lower() for w in result.warnings)
        )

    def test_tracwiki_traclinks_preserved(self):
        """Test TracLinks are preserved and warnings issued."""
        result = tracwiki_to_markdown("See #123 and ticket:456")
        # TracLinks should be preserved in text
        self.assertIn("#123", result.text)
        self.assertIn("ticket:456", result.text)
        # Should issue warning about TracLinks
        self.assertTrue(
            any("traclink" in w.lower() for w in result.warnings)
        )

    def test_tracwiki_definition_lists(self):
        """Test definition lists conversion with warnings."""
        result = tracwiki_to_markdown("term:: definition")
        # Should convert to bold with colon
        self.assertIn("**term**:", result.text)
        # Should warn about lossy conversion
        self.assertTrue(
            any("definition" in w.lower() for w in result.warnings)
        )

    def test_tracwiki_tables(self):
        """Test basic table conversion from TracWiki to Markdown."""
        result = tracwiki_to_markdown("||cell1||cell2||")
        # Should convert to Markdown table
        self.assertIn("| cell1 | cell2 |", result.text)
        self.assertIn("|---|---|", result.text)

    def test_tracwiki_table_headers(self):
        """Test TracWiki header row (||= ... =||) converts to Markdown header."""
        result = tracwiki_to_markdown("||= H1 =||= H2 =||\n||a||b||")
        lines = result.text.split("\n")
        self.assertEqual(lines[0], "| H1 | H2 |")
        # Header cells with = markers are centered by default
        self.assertIn(":---:", lines[1])
        self.assertEqual(lines[2], "| a | b |")

    def test_tracwiki_table_alignment(self):
        """Test TracWiki table alignment converts to Markdown separator."""
        # TracWiki: space on right = left, space on left = right, both = center
        result = tracwiki_to_markdown(
            "||=Left =||= Center =||= Right=||\n||left || center || right||"
        )
        lines = result.text.split("\n")
        # Check separator row has correct alignment markers
        self.assertIn(":---", lines[1])  # left
        self.assertIn(":---:", lines[1])  # center
        self.assertIn("---:", lines[1])  # right

    def test_tracwiki_table_spanning(self):
        """Test TracWiki cell spanning with warning."""
        result = tracwiki_to_markdown(
            "||= A =||= B =||= C =||\n|||| Span 2 || 3 ||"
        )
        # Should have span indicator
        self.assertIn("[span:", result.text)
        # Should warn about spanning
        self.assertTrue(
            any("span" in w.lower() for w in result.warnings)
        )

    def test_tracwiki_table_multiline(self):
        """Test TracWiki multi-line rows (backslash continuation)."""
        result = tracwiki_to_markdown(
            "||= H1 =||= H2 =||\n|| column 1 \\\n|| column 2 ||"
        )
        # Should join into single row
        self.assertIn("| column 1 | column 2 |", result.text)
        # Should warn about multi-line
        self.assertTrue(
            any("multi-line" in w.lower() for w in result.warnings)
        )


class TestFormatDetection(unittest.TestCase):
    """Test format detection heuristics."""

    def test_detect_format_tracwiki_heading(self):
        """Test TracWiki heading with trailing equals is detected."""
        from trac_mcp_server.converters.common import (
            detect_format_heuristic,
        )

        self.assertEqual(
            detect_format_heuristic("= Heading ="), "tracwiki"
        )

    def test_detect_format_tracwiki_bold(self):
        """Test TracWiki bold syntax is detected."""
        from trac_mcp_server.converters.common import (
            detect_format_heuristic,
        )

        self.assertEqual(
            detect_format_heuristic("'''bold'''"), "tracwiki"
        )

    def test_detect_format_markdown_heading(self):
        """Test Markdown heading without trailing equals is detected."""
        from trac_mcp_server.converters.common import (
            detect_format_heuristic,
        )

        self.assertEqual(
            detect_format_heuristic("# Heading"), "markdown"
        )

    def test_detect_format_markdown_bold(self):
        """Test Markdown bold syntax is detected."""
        from trac_mcp_server.converters.common import (
            detect_format_heuristic,
        )

        self.assertEqual(
            detect_format_heuristic("**bold**"), "markdown"
        )

    def test_detect_format_ambiguous_defaults_tracwiki(self):
        """Test ambiguous text defaults to TracWiki."""
        from trac_mcp_server.converters.common import (
            detect_format_heuristic,
        )

        self.assertEqual(
            detect_format_heuristic("plain text"), "tracwiki"
        )


class TestConversionResultMetadata(unittest.TestCase):
    """Test ConversionResult metadata and backward compatibility."""

    def test_conversion_result_metadata(self):
        """Test ConversionResult contains correct metadata."""
        result = tracwiki_to_markdown("= Test =")
        self.assertEqual(result.source_format, "tracwiki")
        self.assertEqual(result.target_format, "markdown")
        self.assertEqual(result.converted, True)
        self.assertIn("# Test", result.text)

    def test_conversion_result_backward_compat(self):
        """Test backward compatibility with old .tracwiki property."""
        from trac_mcp_server.converters import convert_with_warnings

        result = convert_with_warnings("# Test")
        # Old code expects .tracwiki property
        self.assertTrue(hasattr(result, "tracwiki"))
        self.assertEqual(result.text, result.tracwiki)


class TestTableConversion(unittest.TestCase):
    """Test bidirectional table conversion between Markdown and TracWiki."""

    # Markdown to TracWiki tests

    def test_md_to_tw_basic_table(self):
        """Test basic Markdown table converts to TracWiki."""
        md = """| A | B |
| --- | --- |
| 1 | 2 |"""
        result = markdown_to_tracwiki(md)
        self.assertIn("||=A=||=B=||", result)
        self.assertIn("||1||2||", result)

    def test_md_to_tw_table_alignment(self):
        """Test Markdown alignment converts to TracWiki whitespace."""
        md = """| Left | Center | Right |
| :--- | :---: | ---: |
| L | C | R |"""
        result = markdown_to_tracwiki(md)
        # Left aligned header: =text =
        self.assertIn("=Left =", result)
        # Center aligned header: = text =
        self.assertIn("= Center =", result)
        # Right aligned header: = text=
        self.assertIn("= Right=", result)
        # Body cells should have alignment too
        self.assertIn("||L ||", result)  # left
        self.assertIn("|| C ||", result)  # center
        self.assertIn("|| R||", result)  # right

    def test_md_to_tw_empty_cells(self):
        """Test empty cells in Markdown table."""
        md = """| A | | C |
| --- | --- | --- |
| 1 | | 3 |"""
        result = markdown_to_tracwiki(md)
        # Empty cells should produce || without content
        self.assertIn("||=A=||||=C=||", result)
        self.assertIn("||1||||3||", result)

    def test_md_to_tw_single_column(self):
        """Test single column Markdown table."""
        md = """| Only |
| --- |
| A |
| B |"""
        result = markdown_to_tracwiki(md)
        self.assertIn("||=Only=||", result)
        self.assertIn("||A||", result)
        self.assertIn("||B||", result)

    def test_md_to_tw_formatted_content(self):
        """Test Markdown table with formatted content."""
        md = """| **Bold** | *Italic* |
| --- | --- |
| `code` | plain |"""
        result = markdown_to_tracwiki(md)
        self.assertIn("'''Bold'''", result)
        self.assertIn("''Italic''", result)
        self.assertIn("`code`", result)

    # TracWiki to Markdown tests

    def test_tw_to_md_basic_table(self):
        """Test basic TracWiki table converts to Markdown."""
        tw = "||A||B||\n||1||2||"
        result = tracwiki_to_markdown(tw)
        self.assertIn("| A | B |", result.text)
        self.assertIn("|---|---|", result.text)
        self.assertIn("| 1 | 2 |", result.text)

    def test_tw_to_md_header_row(self):
        """Test TracWiki header row converts to Markdown header."""
        tw = "||= H1 =||= H2 =||\n||a||b||"
        result = tracwiki_to_markdown(tw)
        lines = result.text.split("\n")
        self.assertEqual(lines[0], "| H1 | H2 |")
        self.assertEqual(lines[2], "| a | b |")

    def test_tw_to_md_alignment(self):
        """Test TracWiki alignment converts to Markdown separator."""
        tw = "||=Left =||= Center =||= Right=||\n||left || center || right||"
        result = tracwiki_to_markdown(tw)
        # Check separator has alignment markers
        sep_line = result.text.split("\n")[1]
        self.assertIn(":---", sep_line)
        self.assertIn(":---:", sep_line)
        self.assertIn("---:", sep_line)

    def test_tw_to_md_spanning_warning(self):
        """Test TracWiki cell spanning produces warning."""
        tw = "||= A =||= B =||\n|||| Span ||"
        result = tracwiki_to_markdown(tw)
        self.assertTrue(
            any("span" in w.lower() for w in result.warnings)
        )

    def test_tw_to_md_multiline_warning(self):
        """Test TracWiki multi-line rows produce warning."""
        tw = "||= H1 =||= H2 =||\n|| col1 \\\n|| col2 ||"
        result = tracwiki_to_markdown(tw)
        self.assertTrue(
            any("multi-line" in w.lower() for w in result.warnings)
        )

    # Round-trip tests

    def test_table_roundtrip_md_to_tw_to_md(self):
        """Test Markdown -> TracWiki -> Markdown preserves structure."""
        original_md = """| A | B |
| --- | --- |
| 1 | 2 |"""
        to_tw = markdown_to_tracwiki(original_md)
        back_to_md = tracwiki_to_markdown(to_tw)
        # Should have table structure
        self.assertIn("| A | B |", back_to_md.text)
        self.assertIn("| 1 | 2 |", back_to_md.text)

    def test_table_roundtrip_tw_to_md_to_tw(self):
        """Test TracWiki -> Markdown -> TracWiki preserves structure."""
        original_tw = "||= H1 =||= H2 =||\n||a||b||"
        to_md = tracwiki_to_markdown(original_tw)
        back_to_tw = markdown_to_tracwiki(to_md.text)
        # Should have TracWiki table structure
        self.assertIn("||", back_to_tw)
        # Header content preserved (may have alignment spaces)
        self.assertIn("H1", back_to_tw)
        self.assertIn("H2", back_to_tw)

    def test_table_roundtrip_alignment_preserved(self):
        """Test alignment is preserved in round-trip."""
        original_md = """| Left | Center | Right |
| :--- | :---: | ---: |
| L | C | R |"""
        to_tw = markdown_to_tracwiki(original_md)
        back_to_md = tracwiki_to_markdown(to_tw)
        sep_line = back_to_md.text.split("\n")[1]
        # Alignment should be preserved
        self.assertIn(":---", sep_line)
        self.assertIn(":---:", sep_line)
        self.assertIn("---:", sep_line)


class TestRoundTripConversion(unittest.TestCase):
    """Test round-trip conversion behavior (lossy and compatible elements)."""

    def test_roundtrip_lossy_macros(self):
        """Test macros survive round-trip but become [MACRO: ...] notation."""
        original = "Text [[PageOutline]] more"
        to_md = tracwiki_to_markdown(original)
        # Macro becomes [MACRO: ...] - not identical but preserved
        self.assertIn("[MACRO: PageOutline]", to_md.text)
        self.assertGreater(len(to_md.warnings), 0)

    def test_roundtrip_compatible_elements(self):
        """Test elements that survive round-trip semantically."""
        # Elements that convert cleanly both ways
        original_tw = "= H1 =\n\n'''bold''' and ''italic''\n\n * list"
        to_md = tracwiki_to_markdown(original_tw)
        to_tw = markdown_to_tracwiki(to_md.text)
        # Should be semantically equivalent
        self.assertIn("= H1 =", to_tw)
        self.assertIn("'''bold'''", to_tw)
        self.assertIn("''italic''", to_tw)

    def test_roundtrip_tracwiki_to_markdown_to_tracwiki(self):
        """Test TracWiki -> Markdown -> TracWiki preserves basic formatting."""
        original = "== Section ==\n\nSome '''bold''' text."
        to_md = tracwiki_to_markdown(original)
        to_tw = markdown_to_tracwiki(to_md.text)
        # Should preserve headings and bold
        self.assertIn("== Section ==", to_tw)
        self.assertIn("'''bold'''", to_tw)


class TestCodeBlockLanguageMapping(unittest.TestCase):
    """Test bidirectional language mapping for code blocks."""

    # ==========================================================================
    # Direct lookup tests: markdown_to_tracwiki_lang
    # ==========================================================================

    def test_md_to_tw_lang_bash_to_sh(self):
        """Test bash maps to sh."""
        self.assertEqual(markdown_to_tracwiki_lang("bash"), "sh")

    def test_md_to_tw_lang_shell_to_sh(self):
        """Test shell maps to sh."""
        self.assertEqual(markdown_to_tracwiki_lang("shell"), "sh")

    def test_md_to_tw_lang_zsh_to_sh(self):
        """Test zsh maps to sh."""
        self.assertEqual(markdown_to_tracwiki_lang("zsh"), "sh")

    def test_md_to_tw_lang_js_to_javascript(self):
        """Test js maps to javascript."""
        self.assertEqual(markdown_to_tracwiki_lang("js"), "javascript")

    def test_md_to_tw_lang_ts_to_typescript(self):
        """Test ts maps to typescript."""
        self.assertEqual(markdown_to_tracwiki_lang("ts"), "typescript")

    def test_md_to_tw_lang_cpp_variants(self):
        """Test c++ maps to cpp."""
        self.assertEqual(markdown_to_tracwiki_lang("c++"), "cpp")

    def test_md_to_tw_lang_plaintext_variants(self):
        """Test plaintext/plain/text all map to text."""
        self.assertEqual(markdown_to_tracwiki_lang("plaintext"), "text")
        self.assertEqual(markdown_to_tracwiki_lang("plain"), "text")
        self.assertEqual(markdown_to_tracwiki_lang("text"), "text")

    def test_md_to_tw_lang_identity_python(self):
        """Test python passes through unchanged."""
        self.assertEqual(markdown_to_tracwiki_lang("python"), "python")

    def test_md_to_tw_lang_identity_languages(self):
        """Test common identity languages pass through unchanged."""
        identity_langs = [
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
        ]
        for lang in identity_langs:
            self.assertEqual(markdown_to_tracwiki_lang(lang), lang)

    def test_md_to_tw_lang_unknown_passthrough(self):
        """Test unknown languages pass through unchanged."""
        self.assertEqual(
            markdown_to_tracwiki_lang("obscurelang"), "obscurelang"
        )
        self.assertEqual(
            markdown_to_tracwiki_lang("myspeciallang"), "myspeciallang"
        )

    def test_md_to_tw_lang_case_insensitive(self):
        """Test mapping is case-insensitive."""
        self.assertEqual(markdown_to_tracwiki_lang("BASH"), "sh")
        self.assertEqual(markdown_to_tracwiki_lang("Bash"), "sh")
        self.assertEqual(markdown_to_tracwiki_lang("JS"), "javascript")

    # ==========================================================================
    # Direct lookup tests: tracwiki_to_markdown_lang
    # ==========================================================================

    def test_tw_to_md_lang_sh_to_bash(self):
        """Test sh maps to bash (canonical form)."""
        self.assertEqual(tracwiki_to_markdown_lang("sh"), "bash")

    def test_tw_to_md_lang_identity_python(self):
        """Test python passes through unchanged."""
        self.assertEqual(tracwiki_to_markdown_lang("python"), "python")

    def test_tw_to_md_lang_identity_languages(self):
        """Test common identity languages pass through unchanged."""
        identity_langs = [
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
            "javascript",
            "typescript",
            "cpp",
        ]
        for lang in identity_langs:
            self.assertEqual(tracwiki_to_markdown_lang(lang), lang)

    def test_tw_to_md_lang_unknown_passthrough(self):
        """Test unknown processors pass through unchanged."""
        self.assertEqual(
            tracwiki_to_markdown_lang("obscurelang"), "obscurelang"
        )
        self.assertEqual(
            tracwiki_to_markdown_lang("custom_proc"), "custom_proc"
        )

    def test_tw_to_md_lang_case_insensitive(self):
        """Test mapping is case-insensitive."""
        self.assertEqual(tracwiki_to_markdown_lang("SH"), "bash")
        self.assertEqual(tracwiki_to_markdown_lang("Sh"), "bash")

    # ==========================================================================
    # Integration tests: full code block conversion with language mapping
    # ==========================================================================

    def test_md_to_tw_code_block_bash(self):
        """Test Markdown bash code block converts to TracWiki sh."""
        md = """```bash
echo "hello"
```"""
        result = markdown_to_tracwiki(md)
        self.assertIn("{{{#!sh", result)
        self.assertIn('echo "hello"', result)

    def test_md_to_tw_code_block_shell(self):
        """Test Markdown shell code block converts to TracWiki sh."""
        md = """```shell
ls -la
```"""
        result = markdown_to_tracwiki(md)
        self.assertIn("{{{#!sh", result)

    def test_md_to_tw_code_block_js(self):
        """Test Markdown js code block converts to TracWiki javascript."""
        md = """```js
console.log("hello");
```"""
        result = markdown_to_tracwiki(md)
        self.assertIn("{{{#!javascript", result)

    def test_md_to_tw_code_block_python_unchanged(self):
        """Test Markdown python code block stays python in TracWiki."""
        md = """```python
print("hello")
```"""
        result = markdown_to_tracwiki(md)
        self.assertIn("{{{#!python", result)

    def test_tw_to_md_code_block_sh(self):
        """Test TracWiki sh code block converts to Markdown bash."""
        tw = """{{{#!sh
echo "hello"
}}}"""
        result = tracwiki_to_markdown(tw)
        self.assertIn("```bash", result.text)
        self.assertIn('echo "hello"', result.text)

    def test_tw_to_md_code_block_python_unchanged(self):
        """Test TracWiki python code block stays python in Markdown."""
        tw = """{{{#!python
print("hello")
}}}"""
        result = tracwiki_to_markdown(tw)
        self.assertIn("```python", result.text)

    # ==========================================================================
    # Round-trip tests: verify asymmetric mappings work correctly
    # ==========================================================================

    def test_roundtrip_bash_sh_bash(self):
        """Test bash -> sh -> bash round-trip."""
        original_md = """```bash
echo "test"
```"""
        to_tw = markdown_to_tracwiki(original_md)
        # Should be sh in TracWiki
        self.assertIn("{{{#!sh", to_tw)

        back_to_md = tracwiki_to_markdown(to_tw)
        # Should be bash in Markdown (canonical form)
        self.assertIn("```bash", back_to_md.text)

    def test_roundtrip_shell_sh_bash(self):
        """Test shell -> sh -> bash (normalizes to canonical bash)."""
        original_md = """```shell
ls -la
```"""
        to_tw = markdown_to_tracwiki(original_md)
        self.assertIn("{{{#!sh", to_tw)

        back_to_md = tracwiki_to_markdown(to_tw)
        # Returns canonical form 'bash', not original 'shell'
        self.assertIn("```bash", back_to_md.text)

    def test_roundtrip_js_javascript_js(self):
        """Test js -> javascript -> javascript (one-way normalization)."""
        original_md = """```js
console.log("x");
```"""
        to_tw = markdown_to_tracwiki(original_md)
        self.assertIn("{{{#!javascript", to_tw)

        back_to_md = tracwiki_to_markdown(to_tw)
        # javascript is identity, stays as javascript
        self.assertIn("```javascript", back_to_md.text)

    def test_roundtrip_python_unchanged(self):
        """Test python stays python through round-trip."""
        original_md = """```python
x = 1
```"""
        to_tw = markdown_to_tracwiki(original_md)
        self.assertIn("{{{#!python", to_tw)

        back_to_md = tracwiki_to_markdown(to_tw)
        self.assertIn("```python", back_to_md.text)


class TestAutoConvert(unittest.TestCase):
    """Tests for auto_convert() — automatic format conversion with capability detection."""

    def _run(self, coro):
        """Helper to run async coroutine in sync test."""
        import asyncio

        return asyncio.run(coro)

    @patch("trac_mcp_server.detection.capabilities.get_server_capabilities")
    def test_explicit_tracwiki_target(self, mock_caps):
        """target_format='tracwiki' with markdown input converts to tracwiki."""
        from trac_mcp_server.converters.common import auto_convert

        mock_config = MagicMock()
        result = self._run(
            auto_convert("# Heading\n\nParagraph", mock_config, target_format="tracwiki")
        )

        self.assertTrue(result.converted)
        self.assertEqual(result.target_format, "tracwiki")
        self.assertIn("= Heading =", result.text)
        # Capabilities should not be queried when target is explicit
        mock_caps.assert_not_called()

    @patch("trac_mcp_server.detection.capabilities.get_server_capabilities")
    def test_explicit_markdown_target(self, mock_caps):
        """target_format='markdown' with tracwiki input converts to markdown."""
        from trac_mcp_server.converters.common import auto_convert

        mock_config = MagicMock()
        result = self._run(
            auto_convert("= Heading =\n\nParagraph", mock_config, target_format="markdown")
        )

        self.assertTrue(result.converted)
        self.assertEqual(result.target_format, "markdown")
        self.assertIn("# Heading", result.text)
        mock_caps.assert_not_called()

    @patch("trac_mcp_server.detection.capabilities.get_server_capabilities")
    def test_same_format_passthrough_markdown(self, _mock_caps):
        """target_format='markdown' with markdown input — no conversion."""
        from trac_mcp_server.converters.common import auto_convert

        mock_config = MagicMock()
        text = "# Markdown Heading\n\nSome **bold** text"
        result = self._run(
            auto_convert(text, mock_config, target_format="markdown")
        )

        self.assertFalse(result.converted)
        self.assertEqual(result.text, text)

    @patch("trac_mcp_server.detection.capabilities.get_server_capabilities")
    def test_auto_detect_with_markdown_processor(self, mock_caps):
        """target_format=None, server has markdown processor — target becomes 'markdown'."""
        from trac_mcp_server.converters.common import auto_convert

        mock_config = MagicMock()
        mock_caps_result = MagicMock()
        mock_caps_result.markdown_processor = True

        async def fake_caps(_config):
            return mock_caps_result

        mock_caps.side_effect = fake_caps

        # TracWiki input should be converted to markdown
        result = self._run(
            auto_convert("= Heading =\n\nText", mock_config, target_format=None)
        )

        self.assertEqual(result.target_format, "markdown")
        mock_caps.assert_called_once_with(mock_config)

    @patch("trac_mcp_server.detection.capabilities.get_server_capabilities")
    def test_auto_detect_without_markdown_processor(self, mock_caps):
        """target_format=None, no markdown processor — target becomes 'tracwiki'."""
        from trac_mcp_server.converters.common import auto_convert

        mock_config = MagicMock()
        mock_caps_result = MagicMock()
        mock_caps_result.markdown_processor = False

        async def fake_caps(_config):
            return mock_caps_result

        mock_caps.side_effect = fake_caps

        # Markdown input should be converted to tracwiki
        result = self._run(
            auto_convert("# Heading\n\nText", mock_config, target_format=None)
        )

        self.assertEqual(result.target_format, "tracwiki")

    @patch("trac_mcp_server.detection.capabilities.get_server_capabilities")
    def test_capability_detection_failure_defaults_tracwiki(self, mock_caps):
        """target_format=None, capability detection raises — defaults to 'tracwiki'."""
        from trac_mcp_server.converters.common import auto_convert

        mock_config = MagicMock()

        async def raise_error(_config):
            raise ConnectionError("Cannot reach server")

        mock_caps.side_effect = raise_error

        result = self._run(
            auto_convert("# Heading\n\nText", mock_config, target_format=None)
        )

        self.assertEqual(result.target_format, "tracwiki")
        self.assertTrue(result.converted)

    @patch("trac_mcp_server.detection.capabilities.get_server_capabilities")
    def test_same_format_passthrough_tracwiki(self, _mock_caps):
        """target_format='tracwiki' with tracwiki input — no conversion."""
        from trac_mcp_server.converters.common import auto_convert

        mock_config = MagicMock()
        text = "= TracWiki Heading =\n\n'''bold'''"
        result = self._run(
            auto_convert(text, mock_config, target_format="tracwiki")
        )

        self.assertFalse(result.converted)
        self.assertEqual(result.text, text)

    @patch("trac_mcp_server.detection.capabilities.get_server_capabilities")
    def test_returns_conversion_result(self, _mock_caps):
        """Return type is ConversionResult with all expected fields."""
        from trac_mcp_server.converters.common import auto_convert

        mock_config = MagicMock()
        result = self._run(
            auto_convert("# Test", mock_config, target_format="tracwiki")
        )

        self.assertIsInstance(result, ConversionResult)
        self.assertIsNotNone(result.text)
        self.assertIsNotNone(result.source_format)
        self.assertIsNotNone(result.target_format)
        self.assertIsInstance(result.converted, bool)
        self.assertIsInstance(result.warnings, list)


if __name__ == "__main__":
    unittest.main()
