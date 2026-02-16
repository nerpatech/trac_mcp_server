# Format Conversion

## Overview

The Trac MCP Server automatically converts between Markdown and TracWiki formats:

- **Markdown -> TracWiki:** When creating/updating wiki pages and ticket descriptions
- **TracWiki -> Markdown:** When reading wiki pages and ticket content

## Conversion Direction by Operation

| Operation | Input Format | Output Format | Conversion |
|-----------|--------------|---------------|------------|
| `wiki_create` | Markdown | TracWiki | Auto-converts content |
| `wiki_update` | Markdown | TracWiki | Auto-converts content |
| `wiki_get` | TracWiki | Markdown | Auto-converts (unless `raw=true`) |
| `ticket_create` | Markdown | TracWiki | Auto-converts description |
| `ticket_get` | TracWiki | Markdown | Auto-converts (unless `raw=true`) |
| `ticket_update` | Markdown | TracWiki | Auto-converts comment |

## The `raw` Parameter

Use `raw=true` to skip format conversion and get/send content in original TracWiki format:

```json
{
  "name": "wiki_get",
  "arguments": {
    "page_name": "WikiStart",
    "raw": true
  }
}
```

## ConversionResult Structure

```python
@dataclass
class ConversionResult:
    text: str           # Converted text output
    source_format: str  # 'markdown', 'tracwiki', or 'unknown'
    target_format: str  # 'markdown' or 'tracwiki'
    converted: bool     # True if conversion performed
    warnings: list[str] # Warnings about lossy conversions
```

## Language Mappings for Code Blocks

Code block languages are mapped between formats:

| Markdown | TracWiki | Notes |
|----------|----------|-------|
| `bash`, `shell`, `zsh` | `sh` | Shell variants normalize to `sh` |
| `js` | `javascript` | Short form expanded |
| `ts` | `typescript` | Short form expanded |
| `c++` | `cpp` | Normalized name |
| `text`, `plaintext`, `plain` | `text` | Text variants normalized |

**Identity languages (unchanged):** `python`, `java`, `c`, `ruby`, `go`, `rust`, `sql`, `html`, `css`, `xml`, `json`, `yaml`, `diff`, etc.

## Conversion Warnings

The converter detects potentially lossy conversions and returns warnings:

**Markdown to TracWiki:**
- HTML tags (may not render correctly)
- TOC macros (use `[[PageOutline]]` instead)

**TracWiki to Markdown:**
- Unknown macros (preserved as `[MACRO: Name]` notation)
- Definition lists (converted to bold text)
- Table cell spanning (merged into single cell)
- Multi-line table rows (joined into single line)
- Processor-based table cells (converted to plain text)
- TracLinks (preserved but not clickable)

## Markup Conversion Examples

**Headings:**
```
Markdown:  # Heading 1
TracWiki:  = Heading 1 =

Markdown:  ## Heading 2
TracWiki:  == Heading 2 ==
```

**Bold/Italic:**
```
Markdown:  **bold** and *italic*
TracWiki:  '''bold''' and ''italic''
```

**Code Blocks:**
```
Markdown:  ```python
           print("hello")
           ```

TracWiki:  {{{#!python
           print("hello")
           }}}
```

**Links:**
```
Markdown:  [Link Text](https://example.com)
TracWiki:  [https://example.com Link Text]

Markdown:  [Wiki Link](WikiPage)
TracWiki:  [wiki:WikiPage Wiki Link]
```

**Images:**
```
Markdown:  ![alt](image.png)
TracWiki:  [[Image(image.png)]]
```

**Lists:**
```
Markdown:  - Item 1
           - Item 2
             - Nested

TracWiki:   * Item 1
            * Item 2
              * Nested
```

---

[Back to Reference Overview](overview.md)
