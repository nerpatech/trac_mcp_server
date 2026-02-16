# MCP Resources Reference

The Trac MCP Server exposes wiki pages as resources via URI templates, enabling direct content access without tool calls.

## Resource URIs

| URI Pattern | Description |
|-------------|-------------|
| `trac://wiki/{page_name}` | Read specific wiki page (Markdown by default) |
| `trac://wiki/{page_name}?format=tracwiki` | Read page in raw TracWiki format |
| `trac://wiki/{page_name}?version=N` | Read specific historical version |
| `trac://wiki/_index` | List all wiki pages in hierarchical tree structure |

## Query Parameters

| Parameter | Values | Description |
|-----------|--------|-------------|
| `format` | `markdown` (default), `tracwiki` | Output format for page content |
| `version` | Integer (1+) | Retrieve specific version instead of latest |

## Examples

**Read WikiStart in Markdown:**
```
trac://wiki/WikiStart
```

**Read raw TracWiki:**
```
trac://wiki/WikiStart?format=tracwiki
```

**Read specific version:**
```
trac://wiki/WikiStart?version=5
```

**Read nested page:**
```
trac://wiki/API/Reference
```

**List all pages:**
```
trac://wiki/_index
```

## Response Format

**Page Content:**
```
# WikiStart

**Author:** admin
**Version:** 5
**Last Modified:** 2025-01-20 10:00

---

[Page content in Markdown...]
```

**Page Index:**
```
# Wiki Pages

API
|-- Authentication
|-- Reference
`-- Examples
Dev
|-- Setup
`-- Testing
WikiStart
```

## Error Responses

**Page not found:**
```
Error (not_found): Page 'NoSuchPage' not found.

Similar pages: WikiStart, WikiSandbox
```

**Version not found:**
```
Error (invalid_version): Version 99 not found for page 'WikiStart'.

Hint: Use trac://wiki/WikiStart to see the latest version.
```

---

[Back to Reference Overview](overview.md)
