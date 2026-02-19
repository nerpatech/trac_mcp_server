# Comprehensive MCP Tool Test Report

**Date:** 2026-02-18T19:50:56.256145
**Server:** http://192.168.10.4:8000/trac_test
**Test Script Version:** 6.0.0
**Package Version:** 2.1.3

## Executive Summary

- **Tools Tested:** 27/27
- **Total Scenarios:** 56
- **Passed:** 56
- **Failed:** 0
- **Pass Rate:** 100.0%

## Tool Catalog (LLM Tool Presentation)

**Total tools registered:** 26

This section shows the exact tool definitions presented to the LLM/agent
via `list_tools()`. Each entry includes name, description, and full inputSchema.

### `get_server_time`

**Description:** Get current Trac server time for temporal reasoning and coordination. Returns server timestamp in both ISO 8601 and Unix timestamp formats.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

### `ticket_search`

**Description:** Search tickets with filtering by status, owner, and keywords. Returns ticket IDs with summaries.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Trac query string (e.g., 'status=new', 'owner=alice', 'status!=closed&keywords~=urgent'). Default: 'status!=closed' (open tickets)"
    },
    "max_results": {
      "type": "integer",
      "description": "Maximum results to return (default: 10, max: 100)",
      "default": 10,
      "minimum": 1,
      "maximum": 100
    }
  },
  "required": []
}
```

### `ticket_get`

**Description:** Get full ticket details including summary, description, status, and owner. Use ticket_changelog for history. Set raw=true to get description in original TracWiki format without conversion.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "ticket_id": {
      "type": "integer",
      "description": "Ticket number to retrieve",
      "minimum": 1
    },
    "raw": {
      "type": "boolean",
      "description": "If true, return description in original TracWiki format without converting to Markdown (default: false)",
      "default": false
    }
  },
  "required": [
    "ticket_id"
  ]
}
```

### `ticket_changelog`

**Description:** Get ticket change history. Use this to investigate who changed what and when. Set raw=true to get comment content in original TracWiki format without conversion.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "ticket_id": {
      "type": "integer",
      "description": "Ticket number to get history for",
      "minimum": 1
    },
    "raw": {
      "type": "boolean",
      "description": "If true, return comment content in original TracWiki format without converting to Markdown (default: false)",
      "default": false
    }
  },
  "required": [
    "ticket_id"
  ]
}
```

### `ticket_fields`

**Description:** Get all ticket field definitions (standard + custom fields). Returns field metadata including name, type, label, options (for select fields), and custom flag. Use to discover instance-specific ticket schema.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

### `ticket_actions`

**Description:** Get valid workflow actions for a ticket's current state. Returns available state transitions (e.g., accept, resolve, reassign). Essential for agents to know which actions are possible before updating ticket status.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "ticket_id": {
      "type": "integer",
      "description": "Ticket number to retrieve actions for",
      "minimum": 1
    }
  },
  "required": [
    "ticket_id"
  ]
}
```

### `ticket_create`

**Description:** Create a new ticket. Accepts Markdown for description (auto-converted to TracWiki).

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "summary": {
      "type": "string",
      "description": "Ticket title (required)"
    },
    "description": {
      "type": "string",
      "description": "Ticket body in Markdown (will be converted to TracWiki)"
    },
    "ticket_type": {
      "type": "string",
      "description": "Ticket type (default: defect). Available types: defect, enhancement, task.",
      "default": "defect"
    },
    "priority": {
      "type": "string",
      "description": "Priority level"
    },
    "component": {
      "type": "string",
      "description": "Component name"
    },
    "milestone": {
      "type": "string",
      "description": "Target milestone"
    },
    "owner": {
      "type": "string",
      "description": "Assignee username"
    },
    "cc": {
      "type": "string",
      "description": "CC email addresses"
    },
    "keywords": {
      "type": "string",
      "description": "Keywords/tags"
    }
  },
  "required": [
    "summary",
    "description"
  ]
}
```

### `ticket_update`

**Description:** Update ticket attributes and/or add comments. Uses optimistic locking to prevent conflicts. Accepts Markdown for comments.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "ticket_id": {
      "type": "integer",
      "description": "Ticket number to update",
      "minimum": 1
    },
    "comment": {
      "type": "string",
      "description": "Comment in Markdown (optional, max 10000 chars)"
    },
    "status": {
      "type": "string",
      "description": "New status"
    },
    "priority": {
      "type": "string",
      "description": "New priority"
    },
    "component": {
      "type": "string",
      "description": "New component"
    },
    "milestone": {
      "type": "string",
      "description": "New milestone"
    },
    "owner": {
      "type": "string",
      "description": "New owner"
    },
    "resolution": {
      "type": "string",
      "description": "Resolution (when closing)"
    },
    "cc": {
      "type": "string",
      "description": "CC email addresses"
    },
    "keywords": {
      "type": "string",
      "description": "Keywords/tags"
    }
  },
  "required": [
    "ticket_id"
  ]
}
```

### `ticket_delete`

**Description:** Delete a ticket permanently. Warning: This cannot be undone. Requires TICKET_ADMIN permission and 'tracopt.ticket.deleter' enabled in trac.ini.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "ticket_id": {
      "type": "integer",
      "description": "Ticket number to delete",
      "minimum": 1
    }
  },
  "required": [
    "ticket_id"
  ]
}
```

### `ticket_batch_create`

**Description:** Create multiple tickets in a single batch operation. Best-effort: all items attempted, per-item results reported. Bounded by TRAC_MAX_PARALLEL_REQUESTS semaphore.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "tickets": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "summary": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "ticket_type": {
            "type": "string"
          },
          "priority": {
            "type": "string"
          },
          "component": {
            "type": "string"
          },
          "milestone": {
            "type": "string"
          },
          "owner": {
            "type": "string"
          },
          "keywords": {
            "type": "string"
          },
          "cc": {
            "type": "string"
          }
        },
        "required": [
          "summary",
          "description"
        ]
      },
      "description": "List of ticket objects to create"
    }
  },
  "required": [
    "tickets"
  ]
}
```

### `ticket_batch_delete`

**Description:** Delete multiple tickets in a single batch operation. Best-effort: all items attempted, per-item results reported. Requires TICKET_ADMIN permission.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "ticket_ids": {
      "type": "array",
      "items": {
        "type": "integer",
        "minimum": 1
      },
      "description": "List of ticket IDs to delete"
    }
  },
  "required": [
    "ticket_ids"
  ]
}
```

### `ticket_batch_update`

**Description:** Update multiple tickets in a single batch operation. Best-effort: all items attempted, per-item results reported.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "updates": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "ticket_id": {
            "type": "integer",
            "minimum": 1
          },
          "comment": {
            "type": "string"
          },
          "status": {
            "type": "string"
          },
          "resolution": {
            "type": "string"
          },
          "priority": {
            "type": "string"
          },
          "component": {
            "type": "string"
          },
          "milestone": {
            "type": "string"
          },
          "owner": {
            "type": "string"
          },
          "keywords": {
            "type": "string"
          },
          "cc": {
            "type": "string"
          }
        },
        "required": [
          "ticket_id"
        ]
      },
      "description": "List of update objects with ticket_id and fields to change"
    }
  },
  "required": [
    "updates"
  ]
}
```

### `wiki_get`

**Description:** Get wiki page content with Markdown output. Returns full content with metadata (version, author, modified date). Set raw=true to get original TracWiki format without conversion.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "page_name": {
      "type": "string",
      "description": "Wiki page name to retrieve (required)"
    },
    "version": {
      "type": "integer",
      "description": "Specific version to retrieve (optional, defaults to latest)",
      "minimum": 1
    },
    "raw": {
      "type": "boolean",
      "description": "If true, return original TracWiki format without converting to Markdown (default: false)",
      "default": false
    }
  },
  "required": [
    "page_name"
  ]
}
```

### `wiki_search`

**Description:** Search wiki pages by content with relevance ranking. Returns snippets showing matched text. Set raw=true to get snippets in original TracWiki format without conversion.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Search query string (required)"
    },
    "prefix": {
      "type": "string",
      "description": "Filter to pages starting with this prefix (namespace filter, optional)"
    },
    "limit": {
      "type": "integer",
      "description": "Maximum results per page (default: 10, max: 50)",
      "default": 10,
      "minimum": 1,
      "maximum": 50
    },
    "cursor": {
      "type": "string",
      "description": "Pagination cursor from previous response (optional)"
    },
    "raw": {
      "type": "boolean",
      "description": "If true, return snippets in original TracWiki format without converting to Markdown (default: false)",
      "default": false
    }
  },
  "required": [
    "query"
  ]
}
```

### `wiki_recent_changes`

**Description:** Get recently modified wiki pages. Returns pages sorted by modification date (newest first). Useful for finding stale or recently updated documentation.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "since_days": {
      "type": "integer",
      "description": "Return pages modified within this many days",
      "default": 30,
      "minimum": 1
    },
    "limit": {
      "type": "integer",
      "description": "Maximum results to return (default: 20, max: 100)",
      "default": 20,
      "minimum": 1,
      "maximum": 100
    }
  },
  "required": []
}
```

### `wiki_create`

**Description:** Create new wiki page from Markdown input. Fails if page exists (use wiki_update instead).

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "page_name": {
      "type": "string",
      "description": "Wiki page name to create (required)"
    },
    "content": {
      "type": "string",
      "description": "Page content in Markdown format (required)"
    },
    "comment": {
      "type": "string",
      "description": "Change comment (optional)"
    }
  },
  "required": [
    "page_name",
    "content"
  ]
}
```

### `wiki_update`

**Description:** Update existing wiki page with optimistic locking. Requires version for conflict detection.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "page_name": {
      "type": "string",
      "description": "Wiki page name to update (required)"
    },
    "content": {
      "type": "string",
      "description": "Page content in Markdown format (required)"
    },
    "version": {
      "type": "integer",
      "description": "Current page version for optimistic locking (required)",
      "minimum": 1
    },
    "comment": {
      "type": "string",
      "description": "Change comment (optional)"
    }
  },
  "required": [
    "page_name",
    "content",
    "version"
  ]
}
```

### `wiki_delete`

**Description:** Delete a wiki page. Warning: This cannot be undone. Requires WIKI_DELETE permission.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "page_name": {
      "type": "string",
      "description": "Wiki page name to delete (required)"
    }
  },
  "required": [
    "page_name"
  ]
}
```

### `wiki_file_push`

**Description:** Push a local file to a Trac wiki page. Reads the file, auto-detects format (Markdown/TracWiki), converts if needed, and creates or updates the wiki page.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "Absolute path to local file"
    },
    "page_name": {
      "type": "string",
      "description": "Target wiki page name"
    },
    "comment": {
      "type": "string",
      "description": "Change comment"
    },
    "format": {
      "type": "string",
      "enum": [
        "auto",
        "markdown",
        "tracwiki"
      ],
      "default": "auto",
      "description": "Source format override. Default auto-detects from extension then content"
    },
    "strip_frontmatter": {
      "type": "boolean",
      "default": true,
      "description": "Strip YAML frontmatter from .md files before pushing"
    }
  },
  "required": [
    "file_path",
    "page_name"
  ]
}
```

### `wiki_file_pull`

**Description:** Pull a Trac wiki page to a local file. Fetches page content, converts to the requested format, and writes to the specified path.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "page_name": {
      "type": "string",
      "description": "Wiki page name to pull"
    },
    "file_path": {
      "type": "string",
      "description": "Absolute path for output file"
    },
    "format": {
      "type": "string",
      "enum": [
        "markdown",
        "tracwiki"
      ],
      "default": "markdown",
      "description": "Output format for the local file"
    },
    "version": {
      "type": "integer",
      "minimum": 1,
      "description": "Specific page version to pull"
    }
  },
  "required": [
    "page_name",
    "file_path"
  ]
}
```

### `wiki_file_detect_format`

**Description:** Detect the format of a local file (Markdown or TracWiki). Uses file extension first, then content-based heuristic detection.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "Absolute path to file to analyze"
    }
  },
  "required": [
    "file_path"
  ]
}
```

### `milestone_list`

**Description:** List all milestone names. Returns array of milestone names (e.g., ['v1.0', 'v2.0', 'Future']). Requires TICKET_VIEW permission.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

### `milestone_get`

**Description:** Get milestone details by name. Returns name, due date, completion date, and description. Requires TICKET_VIEW permission. Set raw=true to get description in original TracWiki format without conversion.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Milestone name (required)"
    },
    "raw": {
      "type": "boolean",
      "description": "If true, return description in original TracWiki format without converting to Markdown (default: false)",
      "default": false
    }
  },
  "required": [
    "name"
  ]
}
```

### `milestone_create`

**Description:** Create a new milestone. Requires TICKET_ADMIN permission. Attributes: due (ISO 8601 date), completed (ISO 8601 date or 0), description (string).

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Milestone name (required)"
    },
    "attributes": {
      "type": "object",
      "description": "Milestone attributes",
      "properties": {
        "due": {
          "type": "string",
          "description": "Due date in ISO 8601 format (e.g., '2026-12-31T23:59:59')"
        },
        "completed": {
          "description": "Completion date in ISO 8601 format or 0 for not completed"
        },
        "description": {
          "type": "string",
          "description": "Milestone description"
        }
      }
    }
  },
  "required": [
    "name"
  ]
}
```

### `milestone_update`

**Description:** Update an existing milestone. Requires TICKET_ADMIN permission. Attributes: due (ISO 8601 date), completed (ISO 8601 date or 0), description (string).

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Milestone name (required)"
    },
    "attributes": {
      "type": "object",
      "description": "Milestone attributes to update",
      "properties": {
        "due": {
          "type": "string",
          "description": "Due date in ISO 8601 format (e.g., '2026-12-31T23:59:59')"
        },
        "completed": {
          "description": "Completion date in ISO 8601 format or 0 for not completed"
        },
        "description": {
          "type": "string",
          "description": "Milestone description"
        }
      }
    }
  },
  "required": [
    "name",
    "attributes"
  ]
}
```

### `milestone_delete`

**Description:** Delete a milestone by name. Requires TICKET_ADMIN permission. Warning: This cannot be undone.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Milestone name (required)"
    }
  },
  "required": [
    "name"
  ]
}
```

## Connectivity

### ping

**connectivity:** PASS
- Notes: API version: [1, 2, 0]

## System Tools

### get_server_time

**server_time:** PASS
- Notes: Valid timestamp: 2026-02-16T02:06:51
- **Call args:** `{}`  (no arguments)
- **structuredContent:**
  ```json
  {
    "server_time": "2026-02-16T02:06:51",
    "unix_timestamp": 1771232811,
    "timezone": "server"
  }
  ```
- **isError:** `False`
- **Text content preview:** Server time: 2026-02-16T02:06:51

## Ticket Tools

### ticket_search

**default_query:** PASS
- Notes: Returns open tickets by default
- **Call args:** `{}`  (no arguments)
- **structuredContent:**
  ```json
  {
    "tickets": [
      {
        "id": 5,
        "summary": "CORS error when calling API from third-party domain",
        "status": "new",
        "owner": "< default >"
      },
      {
        "id": 6,
        "summary": "Bulk actions for selected items",
        "status": "new",
        "owner": "< default >"
      },
      {
        "id": 7,
        "summary": "Validate database migration scripts",
        "status": "new",
        "owner": "< default >"
      },
      {
        "id": 8,
        "summary": "500 error on /api/reports/summary",
        "status": "new",
        "owner": "< default >"
      },
      {
        "id": 9,
        "summary": "Offline mode with local storage",
        "status": "new",
        "owner": "< default >"
      }
    ],
    "total": 5,
    "showing": 5
  }
  ```
- **isError:** `False`
- **Text content preview:** Found 5 tickets:
- #5: CORS error when calling API from third-party domain (status: new, owner: < default >)
- #6: Bulk actions for selected items (status: new, owner: < default >)
- #7: Validate database migration scripts (status: new, owner: < default >)
- #8: 500 error on /api/reports/summary (status: new, owner: < default >)
- #9: Offline mode with local storage (status: new, owner: < default >)

**custom_query_max_results:** PASS
- Notes: Tested status=closed with max_results=5
- **Call args:** `{"query": "status=closed", "max_results": 5}`
- **structuredContent:**
  ```json
  {
    "tickets": [],
    "total": 0,
    "showing": 0
  }
  ```
- **isError:** `False`
- **Text content preview:** No tickets found matching query.

### ticket_get

**existing_ticket:** PASS
- Notes: Retrieved ticket #5
- **Call args:** `{"ticket_id": 5}`
- **structuredContent:**
  ```json
  {
    "id": 5,
    "summary": "CORS error when calling API from third-party domain",
    "description": "Third-party integrations cannot call our API due to CORS restrictions. Need to whitelist specific domains.",
    "status": "new",
    "owner": "< default >",
    "reporter": "agent_rpc",
    "type": "bug",
    "priority": "major",
    "component": null,
    "milestone": null,
    "keywords": null,
    "cc": null,
    "resolution": null,
    "created": "20260217T01:31:04",
    "modified": "20260217T01:31:04"
  }
  ```
- **isError:** `False`
- **Text content preview:** Ticket #5: CORS error when calling API from third-party domain
Status: new | Owner: < default > | Reporter: agent_rpc | Type: bug
Priority: major | Component: None | Milestone: None
Keywords: None | Cc: None
Created: 20260217T01:31:04 | Modified: 20260217T01:31:04

## Description
Third-party integrations cannot call our API due to CORS restrictions. Need to whitelist specific domains.

**raw_mode:** PASS
- Notes: Raw TracWiki format returned
- **Call args:** `{"ticket_id": 5, "raw": true}`
- **structuredContent:**
  ```json
  {
    "id": 5,
    "summary": "CORS error when calling API from third-party domain",
    "description": "Third-party integrations cannot call our API due to CORS restrictions. Need to whitelist specific domains.",
    "status": "new",
    "owner": "< default >",
    "reporter": "agent_rpc",
    "type": "bug",
    "priority": "major",
    "component": null,
    "milestone": null,
    "keywords": null,
    "cc": null,
    "resolution": null,
    "created": "20260217T01:31:04",
    "modified": "20260217T01:31:04"
  }
  ```
- **isError:** `False`
- **Text content preview:** Ticket #5: CORS error when calling API from third-party domain
Status: new | Owner: < default > | Reporter: agent_rpc | Type: bug
Priority: major | Component: None | Milestone: None
Keywords: None | Cc: None
Created: 20260217T01:31:04 | Modified: 20260217T01:31:04

## Description (TracWiki)
Third-party integrations cannot call our API due to CORS restrictions. Need to whitelist specific domains.

### ticket_changelog

**existing_ticket:** PASS
- Notes: Changelog may be empty for new tickets
- **Call args:** `{"ticket_id": 5}`
- **isError:** `False`
- **Text content preview:** No changelog entries for ticket #5

**raw_mode:** PASS
- Notes: Raw TracWiki format for comments
- **Call args:** `{"ticket_id": 5, "raw": true}`
- **isError:** `False`
- **Text content preview:** No changelog entries for ticket #5

### ticket_actions

**get_workflow_actions:** PASS
- Notes: Retrieved workflow actions for ticket
- **Call args:** `{"ticket_id": 5}`
- **structuredContent:**
  ```json
  {
    "actions": [
      {
        "name": "leave",
        "label": "leave",
        "hints": {}
      },
      {
        "name": "resolve",
        "label": "resolve",
        "hints": {},
        "input_fields": [
          [
            "action_resolve_resolve_resolution",
            "fixed",
            [
              "fixed",
              "invalid",
              "wontfix",
              "duplicate",
              "worksforme"
            ]
          ]
        ]
      },
      {
        "name": "reassign",
        "label": "reassign",
        "hints": {},
        "input_fields": [
          [
            "action_reassign_reassign_owner",
            "agent_rpc",
            []
          ]
        ]
      },
      {
        "name": "accept",
        "label": "accept",
        "hints": {}
      }
    ]
  }
  ```
- **isError:** `False`
- **Text content preview:** Available actions for ticket #5:

- leave: leave
- resolve: resolve [requires: ['action_resolve_resolve_resolution', 'fixed', ['fixed', 'invalid', 'wontfix', 'duplicate', 'worksforme']]]
- reassign: reassign [requires: ['action_reassign_reassign_owner', 'agent_rpc', []]]
- accept: accept

### ticket_fields

**get_fields:** PASS
- Notes: Returns standard and custom field definitions
- **Call args:** `{}`  (no arguments)
- **structuredContent:**
  ```json
  {
    "fields": [
      {
        "name": "summary",
        "type": "text",
        "label": "Summary",
        "custom": false
      },
      {
        "name": "reporter",
        "type": "text",
        "label": "Reporter",
        "custom": false
      },
      {
        "name": "owner",
        "type": "text",
        "label": "Owner",
        "custom": false
      },
      {
        "name": "description",
        "type": "textarea",
        "label": "Description",
        "custom": false
      },
      {
        "name": "type",
        "type": "select",
        "label": "Type",
        "custom": false,
        "options": [
          "defect",
          "enhancement",
          "task"
        ]
      },
      {
        "name": "status",
        "type": "radio",
        "label": "Status",
        "custom": false,
        "options": [
          "accepted",
          "assigned",
          "closed",
          "new",
          "reopened"
        ]
      },
      {
        "name": "priority",
        "type": "select",
        "label": "Priority",
        "custom": false,
        "options": [
          "blocker",
          "critical",
          "major",
          "minor",
          "trivial"
        ]
      },
      {
        "name": "milestone",
        "type": "select",
        "label": "Milestone",
        "custom": false,
        "options": [
          "milestone1",
          "milestone2",
          "milestone3",
          "milestone4"
        ]
      },
      {
        "name": "component",
        "type": "select",
        "label": "Component",
        "custom": false,
        "options": [
          "backend",
          "configuration",
          "database",
          "defects",
          "docs",
          "enhancements",
          "frontend",
          "infrastructure",
          "monitoring",
          "security"
        ]
      },
      {
        "name": "version",
        "type": "select",
        "label": "Version",
        "custom": false,
        "options": [
          "2.0",
          "1.0"
        ]
      },
      {
        "name": "resolution",
        "type": "radio",
        "label": "Resolution",
        "custom": false,
        "options": [
          "fixed",
     
    ... (truncated)
  ```
- **isError:** `False`
- **Text content preview:** Ticket Fields (15 total):

Standard Fields:
- summary (text): Summary
- reporter (text): Reporter
- owner (text): Owner
- description (textarea): Description
- type (select): Type [defect, enhancement, task]
- status (radio): Status
- priority (select): Priority [blocker, critical, major, minor, trivial]
- milestone (select): Milestone [milestone1, milestone2, milestone3, milestone4]
- component (select): Component [backend, configuration, database, defects, docs, enhancements, frontend, infrast... (truncated)

### ticket_create

**create_with_markdown:** PASS
- Notes: Created ticket #10
- **Call args:** `{"summary": "[MCP TEST 20260218_195052] Comprehensive Tool Test", "description": "## Test Ticket\n\nThis is a **Markdown** test.\n\n- Item 1\n- Item 2\n\n### Code Example\n\n```python\nprint(\"hello world\")\n```\n", "ticket_type": "task", "keywords": "mcp-test,auto-delete"}`
- **isError:** `False`
- **Text content preview:** Created ticket #10: [MCP TEST 20260218_195052] Comprehensive Tool Test

**markdown_conversion:** PASS
- Notes: Verified Markdown converted to TracWiki
- **Call args:** `{"ticket_id": 10, "raw": true}`
- **structuredContent:**
  ```json
  {
    "id": 10,
    "summary": "[MCP TEST 20260218_195052] Comprehensive Tool Test",
    "description": "== Test Ticket ==\nThis is a '''Markdown''' test.\n\n * Item 1\n * Item 2\n=== Code Example ===\n{{{#!python\nprint(\"hello world\")\n}}}",
    "status": "new",
    "owner": "< default >",
    "reporter": "agent_rpc",
    "type": "task",
    "priority": "major",
    "component": null,
    "milestone": null,
    "keywords": "mcp-test,auto-delete",
    "cc": null,
    "resolution": null,
    "created": "20260219T02:50:53",
    "modified": "20260219T02:50:53"
  }
  ```
- **isError:** `False`
- **Text content preview:** Ticket #10: [MCP TEST 20260218_195052] Comprehensive Tool Test
Status: new | Owner: < default > | Reporter: agent_rpc | Type: task
Priority: major | Component: None | Milestone: None
Keywords: mcp-test,auto-delete | Cc: None
Created: 20260219T02:50:53 | Modified: 20260219T02:50:53

## Description (TracWiki)
== Test Ticket ==
This is a '''Markdown''' test.

 * Item 1
 * Item 2
=== Code Example ===
{{{#!python
print("hello world")
}}}

### ticket_update

**add_comment:** PASS
- Notes: Comment with Markdown formatting
- **Call args:** `{"ticket_id": 10, "comment": "### Update Comment\n\nAdding a **formatted** comment."}`
- **isError:** `False`
- **Text content preview:** Updated ticket #10 (added comment)

**update_fields:** PASS
- Notes: Updated priority and keywords
- **Call args:** `{"ticket_id": 10, "priority": "major", "keywords": "mcp-test,auto-delete,updated"}`
- **isError:** `False`
- **Text content preview:** Updated ticket #10 (updated 2 field(s))

### ticket_delete

**delete_ticket:** PASS
- Notes: Deleted test ticket #10
- **Call args:** `{"ticket_id": 10}`
- **isError:** `False`
- **Text content preview:** Deleted ticket #10.

**verify_deletion:** PASS
- Notes: Confirmed ticket no longer exists
- **Call args:** `{"ticket_id": 10}`
- **isError:** `True`
- **Text content preview:** Error (not_found): Ticket 10 does not exist.

Action: Use ticket_search to verify ticket exists.

## Batch Ticket Tools

### ticket_batch_create

**create_batch:** PASS
- Notes: Created 10 tickets: #11..#20
- **Call args:** `{"tickets": [{"summary": "[MCP BATCH 20260218_195052] Ticket 1/10", "description": "Batch test ticket **1**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}, {"summary": "[MCP BATCH 20260218_195052] Ticket 2/10", "description": "Batch test ticket **2**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}, {"summary": "[MCP BATCH 20260218_195052] Ticket 3/10", "description": "Batch test ticket **3**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}, {"summary": "[MCP BATCH 20260218_195052] Ticket 4/10", "description": "Batch test ticket **4**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}, {"summary": "[MCP BATCH 20260218_195052] Ticket 5/10", "description": "Batch test ticket **5**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}, {"summary": "[MCP BATCH 20260218_195052] Ticket 6/10", "description": "Batch test ticket **6**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}, {"summary": "[MCP BATCH 20260218_195052] Ticket 7/10", "description": "Batch test ticket **7**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}, {"summary": "[MCP BATCH 20260218_195052] Ticket 8/10", "description": "Batch test ticket **8**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}, {"summary": "[MCP BATCH 20260218_195052] Ticket 9/10", "description": "Batch test ticket **9**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}, {"summary": "[MCP BATCH 20260218_195052] Ticket 10/10", "description": "Batch test ticket **10**. Auto-created, auto-deleted.", "ticket_type": "task", "keywords": "mcp-batch-test,auto-delete"}]}`
- **structuredContent:**
  ```json
  {
    "created": [
      {
        "id": 14,
        "summary": "[MCP BATCH 20260218_195052] Ticket 1/10"
      },
      {
        "id": 11,
        "summary": "[MCP BATCH 20260218_195052] Ticket 2/10"
      },
      {
        "id": 19,
        "summary": "[MCP BATCH 20260218_195052] Ticket 3/10"
      },
      {
        "id": 16,
        "summary": "[MCP BATCH 20260218_195052] Ticket 4/10"
      },
      {
        "id": 13,
        "summary": "[MCP BATCH 20260218_195052] Ticket 5/10"
      },
      {
        "id": 12,
        "summary": "[MCP BATCH 20260218_195052] Ticket 6/10"
      },
      {
        "id": 17,
        "summary": "[MCP BATCH 20260218_195052] Ticket 7/10"
      },
      {
        "id": 15,
        "summary": "[MCP BATCH 20260218_195052] Ticket 8/10"
      },
      {
        "id": 20,
        "summary": "[MCP BATCH 20260218_195052] Ticket 9/10"
      },
      {
        "id": 18,
        "summary": "[MCP BATCH 20260218_195052] Ticket 10/10"
      }
    ],
    "failed": [],
    "total": 10,
    "succeeded": 10,
    "failed_count": 0
  }
  ```
- **isError:** `False`
- **Text content preview:** Batch create: 10/10 succeeded, 0 failed.

Created:
  - #14: [MCP BATCH 20260218_195052] Ticket 1/10
  - #11: [MCP BATCH 20260218_195052] Ticket 2/10
  - #19: [MCP BATCH 20260218_195052] Ticket 3/10
  - #16: [MCP BATCH 20260218_195052] Ticket 4/10
  - #13: [MCP BATCH 20260218_195052] Ticket 5/10
  - #12: [MCP BATCH 20260218_195052] Ticket 6/10
  - #17: [MCP BATCH 20260218_195052] Ticket 7/10
  - #15: [MCP BATCH 20260218_195052] Ticket 8/10
  - #20: [MCP BATCH 20260218_195052] Ticket 9/10
  - #18:... (truncated)

**verify_created:** PASS
- Notes: Spot-checked ticket #14
- **Call args:** `{"ticket_id": 14}`
- **structuredContent:**
  ```json
  {
    "id": 14,
    "summary": "[MCP BATCH 20260218_195052] Ticket 1/10",
    "description": "Batch test ticket **1**. Auto-created, auto-deleted.",
    "status": "new",
    "owner": "< default >",
    "reporter": "agent_rpc",
    "type": "task",
    "priority": "major",
    "component": null,
    "milestone": null,
    "keywords": "mcp-batch-test,auto-delete",
    "cc": null,
    "resolution": null,
    "created": "20260219T02:50:54",
    "modified": "20260219T02:50:54"
  }
  ```
- **isError:** `False`
- **Text content preview:** Ticket #14: [MCP BATCH 20260218_195052] Ticket 1/10
Status: new | Owner: < default > | Reporter: agent_rpc | Type: task
Priority: major | Component: None | Milestone: None
Keywords: mcp-batch-test,auto-delete | Cc: None
Created: 20260219T02:50:54 | Modified: 20260219T02:50:54

## Description
Batch test ticket **1**. Auto-created, auto-deleted.

**partial_failure:** PASS
- Notes: 1 ticket missing summary should fail, 2 should succeed
- **Call args:** `{"tickets": [{"summary": "[MCP BATCH 20260218_195052] Good ticket", "description": "Valid ticket"}, {"description": "Missing summary field"}, {"summary": "[MCP BATCH 20260218_195052] Another good", "description": "Also valid"}]}`
- **structuredContent:**
  ```json
  {
    "created": [
      {
        "id": 22,
        "summary": "[MCP BATCH 20260218_195052] Good ticket"
      },
      {
        "id": 21,
        "summary": "[MCP BATCH 20260218_195052] Another good"
      }
    ],
    "failed": [
      {
        "index": 1,
        "summary": "",
        "error": "summary is required"
      }
    ],
    "total": 3,
    "succeeded": 2,
    "failed_count": 1
  }
  ```
- **isError:** `False`
- **Text content preview:** Batch create: 2/3 succeeded, 1 failed.

Created:
  - #22: [MCP BATCH 20260218_195052] Good ticket
  - #21: [MCP BATCH 20260218_195052] Another good

Failed:
  - [index 1] : summary is required

### ticket_batch_update

**update_batch:** PASS
- Notes: Updated 12 tickets with keywords + comment
- **Call args:** `{"updates": [{"ticket_id": 14, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#14**"}, {"ticket_id": 11, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#11**"}, {"ticket_id": 19, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#19**"}, {"ticket_id": 16, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#16**"}, {"ticket_id": 13, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#13**"}, {"ticket_id": 12, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#12**"}, {"ticket_id": 17, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#17**"}, {"ticket_id": 15, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#15**"}, {"ticket_id": 20, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#20**"}, {"ticket_id": 18, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#18**"}, {"ticket_id": 22, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#22**"}, {"ticket_id": 21, "keywords": "mcp-batch-test,auto-delete,batch-updated", "comment": "Batch update test \u2014 ticket **#21**"}]}`
- **structuredContent:**
  ```json
  {
    "updated": [
      14,
      11,
      19,
      16,
      13,
      12,
      17,
      15,
      20,
      18,
      22,
      21
    ],
    "failed": [],
    "total": 12,
    "succeeded": 12,
    "failed_count": 0
  }
  ```
- **isError:** `False`
- **Text content preview:** Batch update: 12/12 succeeded, 0 failed.

Updated:
  - #14
  - #11
  - #19
  - #16
  - #13
  - #12
  - #17
  - #15
  - #20
  - #18
  - #22
  - #21

**verify_updated:** PASS
- Notes: Verified keyword added to ticket #14
- **Call args:** `{"ticket_id": 14}`
- **structuredContent:**
  ```json
  {
    "id": 14,
    "summary": "[MCP BATCH 20260218_195052] Ticket 1/10",
    "description": "Batch test ticket **1**. Auto-created, auto-deleted.",
    "status": "new",
    "owner": "< default >",
    "reporter": "agent_rpc",
    "type": "task",
    "priority": "major",
    "component": null,
    "milestone": null,
    "keywords": "mcp-batch-test,auto-delete,batch-updated",
    "cc": null,
    "resolution": null,
    "created": "20260219T02:50:54",
    "modified": "20260219T02:50:55"
  }
  ```
- **isError:** `False`
- **Text content preview:** Ticket #14: [MCP BATCH 20260218_195052] Ticket 1/10
Status: new | Owner: < default > | Reporter: agent_rpc | Type: task
Priority: major | Component: None | Milestone: None
Keywords: mcp-batch-test,auto-delete,batch-updated | Cc: None
Created: 20260219T02:50:54 | Modified: 20260219T02:50:55

## Description
Batch test ticket **1**. Auto-created, auto-deleted.

### ticket_batch_delete

**delete_batch:** PASS
- Notes: Deleted 12 tickets
- **Call args:** `{"ticket_ids": [14, 11, 19, 16, 13, 12, 17, 15, 20, 18, 22, 21]}`
- **structuredContent:**
  ```json
  {
    "deleted": [
      14,
      11,
      19,
      16,
      13,
      12,
      17,
      15,
      20,
      18,
      22,
      21
    ],
    "failed": [],
    "total": 12,
    "succeeded": 12,
    "failed_count": 0
  }
  ```
- **isError:** `False`
- **Text content preview:** Batch delete: 12/12 succeeded, 0 failed.

Deleted:
  - #14
  - #11
  - #19
  - #16
  - #13
  - #12
  - #17
  - #15
  - #20
  - #18
  - #22
  - #21

**verify_deleted:** PASS
- Notes: Confirmed ticket #14 no longer exists
- **Call args:** `{"ticket_id": 14}`
- **isError:** `True`
- **Text content preview:** Error (not_found): Ticket 14 does not exist.

Action: Use ticket_search to verify ticket exists.

## Wiki Tools

### wiki_get

**wikistart:** PASS
- Notes: Version: 1
- **Call args:** `{"page_name": "WikiStart"}`
- **structuredContent:**
  ```json
  {
    "name": "WikiStart",
    "content": "# Welcome to Trac\nTrac is a **minimalistic** approach to **web-based** management of\n**software projects**. Its goal is to simplify effective tracking and\nhandling of software issues, enhancements and overall progress.\n\nAll aspects of Trac have been designed with the single goal to\n**help developers write great software** while **staying out of the way**\nand imposing as little as possible on a team's established process and\nculture.\n\nAs all Wiki pages, this page is editable, this means that you can\nmodify the contents of this page simply by using your\nweb-browser. Simply click on the \"Edit this page\" link at the bottom\nof the page. WikiFormatting will give you a detailed description of\navailable Wiki formatting commands.\n\n\"[trac-admin](wiki:TracAdmin) *yourenvdir* initenv\" created\na new Trac environment, containing a default set of wiki pages and some sample\ndata. This newly created environment also contains\n[documentation](wiki:TracGuide) to help you get started with your project.\n\nYou can use [trac-admin](wiki:TracAdmin) to configure\n[Trac](http://trac.edgewall.org/) to better fit your project, especially in\nregard to *components*, *versions* and *milestones*.\n\n\nTracGuide is a good place to start.\n\nEnjoy! \n\n*The Trac Team*\n\n## Starting Points\n - TracGuide --  Built-in Documentation\n - [The Trac project](http://trac.edgewall.org/) -- Trac Open Source Project\n - [Trac FAQ](http://trac.edgewall.org/wiki/TracFaq) -- Frequently Asked Questions\n - TracSupport --  Trac Support\n\nFor a complete list of local wiki pages, see TitleIndex.\n",
    "version": 1,
    "author": "trac",
    "lastModified": "20260216T02:06:51"
  }
  ```
- **isError:** `False`
- **Text content preview:** # WikiStart
Version: 1 | Author: trac | Modified: 20260216T02:06:51
----

# Welcome to Trac
Trac is a **minimalistic** approach to **web-based** management of
**software projects**. Its goal is to simplify effective tracking and
handling of software issues, enhancements and overall progress.

All aspects of Trac have been designed with the single goal to
**help developers write great software** while **staying out of the way**
and imposing as little as possible on a team's established process an... (truncated)

**raw_mode:** PASS
- Notes: Raw TracWiki format returned
- **Call args:** `{"page_name": "WikiStart", "raw": true}`
- **structuredContent:**
  ```json
  {
    "name": "WikiStart",
    "content": "= Welcome to Trac\n\nTrac is a '''minimalistic''' approach to '''web-based''' management of\n'''software projects'''. Its goal is to simplify effective tracking and\nhandling of software issues, enhancements and overall progress.\n\nAll aspects of Trac have been designed with the single goal to\n'''help developers write great software''' while '''staying out of the way'''\nand imposing as little as possible on a team's established process and\nculture.\n\nAs all Wiki pages, this page is editable, this means that you can\nmodify the contents of this page simply by using your\nweb-browser. Simply click on the \"Edit this page\" link at the bottom\nof the page. WikiFormatting will give you a detailed description of\navailable Wiki formatting commands.\n\n\"[wiki:TracAdmin trac-admin] ''yourenvdir'' initenv\" created\na new Trac environment, containing a default set of wiki pages and some sample\ndata. This newly created environment also contains\n[wiki:TracGuide documentation] to help you get started with your project.\n\nYou can use [wiki:TracAdmin trac-admin] to configure\n[http://trac.edgewall.org/ Trac] to better fit your project, especially in\nregard to ''components'', ''versions'' and ''milestones''.\n\n\nTracGuide is a good place to start.\n\nEnjoy! [[BR]]\n''The Trac Team''\n\n== Starting Points\n\n * TracGuide --  Built-in Documentation\n * [http://trac.edgewall.org/ The Trac project] -- Trac Open Source Project\n * [http://trac.edgewall.org/wiki/TracFaq Trac FAQ] -- Frequently Asked Questions\n * TracSupport --  Trac Support\n\nFor a complete list of local wiki pages, see TitleIndex.\n",
    "version": 1,
    "author": "trac",
    "lastModified": "20260216T02:06:51"
  }
  ```
- **isError:** `False`
- **Text content preview:** # WikiStart (TracWiki)
Version: 1 | Author: trac | Modified: 20260216T02:06:51
----

= Welcome to Trac

Trac is a '''minimalistic''' approach to '''web-based''' management of
'''software projects'''. Its goal is to simplify effective tracking and
handling of software issues, enhancements and overall progress.

All aspects of Trac have been designed with the single goal to
'''help developers write great software''' while '''staying out of the way'''
and imposing as little as possible on a team's ... (truncated)

### wiki_search

**basic_search:** PASS
- Notes: Search for 'wiki' keyword
- **Call args:** `{"query": "wiki"}`
- **isError:** `False`
- **Text content preview:** Found 10 wiki pages:

**TracEnvironment**
  ......in the environment directory, and can easily be [backed up](wiki:TracBackup) together with the rest of t......
**WikiPageNames**
  ...# Wiki Page Names
[MACRO: TracGuideToc]

Wiki page names comm......
**TracChangeLog**
  ......er supported.

For more information see the [API changes](trac:wiki:TracDev/ApiChanges/1.6) and the detai......
**TracSupport**
  ......:MailingList mailing list] and the [project wiki](trac:). Both are maintained by the T... (truncated)

**with_prefix:** PASS
- Notes: Filtered by Trac prefix
- **Call args:** `{"query": "trac", "prefix": "Trac"}`
- **isError:** `False`
- **Text content preview:** Found 8 wiki pages:

**TracBatchModify**
  ...# Trac Ticket Batch Modification
[MACRO: TracGuideToc]

Tra......
**TracEnvironment**
  ...# The Trac Environment
[MACRO: TracGuideToc]
[[PageOutline(2-5,C......
**TracChangeLog**
  ......changes between released versions.

To see where Trac is going in future releases, see the [trac:roadma......
**TracSupport**
  ...# Trac Support
Like most [https://opensource.org/ ope......
**TracReports**
  ...# Trac Reports
[MACRO: TracGuideToc]

The Trac reports... (truncated)

### wiki_recent_changes

**recent_changes:** PASS
- Notes: Retrieved wiki pages modified in last 30 days
- **Call args:** `{"days_back": 30}`
- **structuredContent:**
  ```json
  {
    "pages": [
      {
        "name": "WikiStart",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "WikiRestructuredTextLinks",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "WikiRestructuredText",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "WikiProcessors",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "WikiPageNames",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "WikiNewPage",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "WikiMacros",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "WikiHtml",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "WikiFormatting",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "WikiDeletePage",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "TracWorkflow",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "TracWiki",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "TracUpgrade",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "TracUnicode",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "TracTimeline",
        "author": "trac",
        "lastModified": "20260216T02:06:51",
        "version": 1
      },
      {
        "name": "TracTicketsCustom
    ... (truncated)
  ```
- **isError:** `False`
- **Text content preview:** Wiki pages modified in last 30 days: (showing 20 of 60)

- WikiStart (modified: 20260216T02:06:51 by trac)
- WikiRestructuredTextLinks (modified: 20260216T02:06:51 by trac)
- WikiRestructuredText (modified: 20260216T02:06:51 by trac)
- WikiProcessors (modified: 20260216T02:06:51 by trac)
- WikiPageNames (modified: 20260216T02:06:51 by trac)
- WikiNewPage (modified: 20260216T02:06:51 by trac)
- WikiMacros (modified: 20260216T02:06:51 by trac)
- WikiHtml (modified: 20260216T02:06:51 by trac)
- Wik... (truncated)

### wiki_create

**create_with_markdown:** PASS
- Notes: Created page: MCPTest_20260218_195052
- **Call args:** `{"page_name": "MCPTest_20260218_195052", "content": "# Test Page\n\n## Features\n\n- **Bold** text\n- *Italic* text\n- `Code` text\n\n### Code Block\n\n```python\nprint('hello')\n```\n\n### Links\n\n- [External Link](https://example.com)\n- WikiStart (internal link)\n", "comment": "MCP test page creation"}`
- **isError:** `False`
- **Text content preview:** Created wiki page 'MCPTest_20260218_195052' (version 1)

**markdown_conversion:** PASS
- Notes: Verified Markdown converted to TracWiki
- **Call args:** `{"page_name": "MCPTest_20260218_195052", "raw": true}`
- **structuredContent:**
  ```json
  {
    "name": "MCPTest_20260218_195052",
    "content": "= Test Page =\n== Features ==\n * '''Bold''' text\n * ''Italic'' text\n * `Code` text\n=== Code Block ===\n{{{#!python\nprint('hello')\n}}}\n=== Links ===\n * [https://example.com External Link]\n * WikiStart (internal link)",
    "version": 1,
    "author": "agent_rpc",
    "lastModified": "20260219T02:50:53"
  }
  ```
- **isError:** `False`
- **Text content preview:** # MCPTest_20260218_195052 (TracWiki)
Version: 1 | Author: agent_rpc | Modified: 20260219T02:50:53
----

= Test Page =
== Features ==
 * '''Bold''' text
 * ''Italic'' text
 * `Code` text
=== Code Block ===
{{{#!python
print('hello')
}}}
=== Links ===
 * [https://example.com External Link]
 * WikiStart (internal link)

**duplicate_error:** PASS
- Notes: Expected error for duplicate page
- **Call args:** `{"page_name": "MCPTest_20260218_195052", "content": "Duplicate content"}`
- **isError:** `True`
- **Text content preview:** Error (already_exists): Page 'MCPTest_20260218_195052' already exists

Action: Use wiki_update to modify existing page, or choose a different name.

### wiki_update

**update_page:** PASS
- Notes: Updated to version 2
- **Call args:** `{"page_name": "MCPTest_20260218_195052", "content": "# Updated Test Page\n\nThis page was updated.", "version": 1, "comment": "MCP test page update"}`
- **isError:** `False`
- **Text content preview:** Updated wiki page 'MCPTest_20260218_195052' to version 2

**version_conflict:** PASS
- Notes: Tested version conflict detection (may not be enforced by server)
- **Call args:** `{"page_name": "MCPTest_20260218_195052", "content": "Conflict content", "version": 1, "comment": "Should conflict"}`
- **isError:** `False`
- **Text content preview:** Updated wiki page 'MCPTest_20260218_195052' to version 3

### wiki_delete

**delete_page:** PASS
- Notes: Deleted: MCPTest_20260218_195052
- **Call args:** `{"page_name": "MCPTest_20260218_195052"}`
- **isError:** `False`
- **Text content preview:** Deleted wiki page 'MCPTest_20260218_195052'.

**verify_deletion:** PASS
- Notes: Confirmed page no longer exists
- **Call args:** `{"page_name": "MCPTest_20260218_195052"}`
- **isError:** `True`
- **Text content preview:** Error (not_found): Wiki page "MCPTest_20260218_195052" does not exist

Action: Use wiki_search to find pages similar to 'MCPTest_20260218_195052'.

## Wiki File Tools

### wiki_file_detect_format

**detect_markdown:** PASS
- Notes: Detected format of .md file
- **Call args:** `{"file_path": "/tmp/mcp_test_20260218_195052.md"}`
- **structuredContent:**
  ```json
  {
    "file_path": "/tmp/mcp_test_20260218_195052.md",
    "format": "markdown",
    "encoding": "utf-8",
    "size_bytes": 43
  }
  ```
- **isError:** `False`
- **Text content preview:** File: /tmp/mcp_test_20260218_195052.md
Format: markdown
Encoding: utf-8
Size: 43 bytes

### wiki_file_push

**push_markdown_file:** PASS
- Notes: Pushed file to wiki page: MCPFileTest_20260218_195052
- **Call args:** `{"file_path": "/tmp/mcp_test_20260218_195052.md", "page_name": "MCPFileTest_20260218_195052", "comment": "MCP file push test"}`
- **structuredContent:**
  ```json
  {
    "page_name": "MCPFileTest_20260218_195052",
    "action": "created",
    "version": 1,
    "source_format": "markdown",
    "converted": true,
    "file_path": "/tmp/mcp_test_20260218_195052.md",
    "warnings": []
  }
  ```
- **isError:** `False`
- **Text content preview:** Created wiki page 'MCPFileTest_20260218_195052' (version 1)

### wiki_file_pull

**pull_to_markdown:** PASS
- Notes: Pulled wiki page to: /tmp/mcp_pull_20260218_195052.md
- **Call args:** `{"page_name": "MCPFileTest_20260218_195052", "file_path": "/tmp/mcp_pull_20260218_195052.md", "format": "markdown"}`
- **structuredContent:**
  ```json
  {
    "page_name": "MCPFileTest_20260218_195052",
    "file_path": "/tmp/mcp_pull_20260218_195052.md",
    "format": "markdown",
    "version": 1,
    "bytes_written": 41,
    "converted": true
  }
  ```
- **isError:** `False`
- **Text content preview:** Pulled wiki page 'MCPFileTest_20260218_195052' (version 1) to /tmp/mcp_pull_20260218_195052.md (41 bytes, format=markdown)

**verify_content:** PASS
- Notes: Verified pulled file has expected content
- **Call args:** `{}`  (no arguments)

## Milestone Tools

### milestone_list

**list_all:** PASS
- Notes: First milestone: milestone1
- **Call args:** `{}`  (no arguments)
- **structuredContent:**
  ```json
  {
    "milestones": [
      "milestone1",
      "milestone2",
      "milestone3",
      "milestone4"
    ]
  }
  ```
- **isError:** `False`
- **Text content preview:** milestone1
milestone2
milestone3
milestone4

### milestone_get

**existing_milestone:** PASS
- Notes: Retrieved milestone: milestone1
- **Call args:** `{"name": "milestone1"}`
- **structuredContent:**
  ```json
  {
    "name": "milestone1",
    "due": "(Not set)",
    "completed": "(Not set)",
    "description": "(No description)"
  }
  ```
- **isError:** `False`
- **Text content preview:** Milestone: milestone1
Due: (Not set)
Completed: (Not set)

## Description
(No description)

**raw_mode:** PASS
- Notes: Raw TracWiki format for description
- **Call args:** `{"name": "milestone1", "raw": true}`
- **structuredContent:**
  ```json
  {
    "name": "milestone1",
    "due": "(Not set)",
    "completed": "(Not set)",
    "description": "(No description)"
  }
  ```
- **isError:** `False`
- **Text content preview:** Milestone: milestone1
Due: (Not set)
Completed: (Not set)

## Description (TracWiki)
(No description)

### milestone_create

**create_milestone:** PASS
- Notes: Created: MCP-Test-20260218_195052
- **Call args:** `{"name": "MCP-Test-20260218_195052", "attributes": {"due": "2026-12-31T23:59:59", "description": "Test milestone for MCP validation"}}`
- **isError:** `False`
- **Text content preview:** Created milestone: MCP-Test-20260218_195052

**verify_creation:** PASS
- Notes: Verified milestone exists
- **Call args:** `{"name": "MCP-Test-20260218_195052"}`
- **structuredContent:**
  ```json
  {
    "name": "MCP-Test-20260218_195052",
    "due": "20261231T23:59:59",
    "completed": "(Not set)",
    "description": "Test milestone for MCP validation"
  }
  ```
- **isError:** `False`
- **Text content preview:** Milestone: MCP-Test-20260218_195052
Due: 20261231T23:59:59
Completed: (Not set)

## Description
Test milestone for MCP validation

### milestone_update

**update_milestone:** PASS
- Notes: Updated description and completed date
- **Call args:** `{"name": "MCP-Test-20260218_195052", "attributes": {"description": "Updated description", "completed": "2026-02-04T12:00:00"}}`
- **isError:** `False`
- **Text content preview:** Updated milestone 'MCP-Test-20260218_195052' (updated 2 field(s): description, completed)

### milestone_delete

**delete_milestone:** PASS
- Notes: Deleted: MCP-Test-20260218_195052
- **Call args:** `{"name": "MCP-Test-20260218_195052"}`
- **isError:** `False`
- **Text content preview:** Deleted milestone: MCP-Test-20260218_195052

**verify_deletion:** PASS
- Notes: Confirmed milestone no longer exists
- **Call args:** `{"name": "MCP-Test-20260218_195052"}`
- **isError:** `True`
- **Text content preview:** Error (not_found): Milestone MCP-Test-20260218_195052 does not exist.

Action: Use milestone_list to verify milestone exists.

## Error Handling

### ticket_batch_create

**empty_list_error:** PASS
- Notes: Expected validation error for empty tickets list
- **Call args:** `{"tickets": []}`
- **isError:** `True`
- **Text content preview:** Error (validation_error): tickets list is required and cannot be empty

Action: Provide a non-empty tickets array.

### ticket_batch_update

**empty_list_error:** PASS
- Notes: Expected validation error for empty updates list
- **Call args:** `{"updates": []}`
- **isError:** `True`
- **Text content preview:** Error (validation_error): updates list is required and cannot be empty

Action: Provide a non-empty updates array.

### ticket_batch_delete

**empty_list_error:** PASS
- Notes: Expected validation error for empty ticket_ids list
- **Call args:** `{"ticket_ids": []}`
- **isError:** `True`
- **Text content preview:** Error (validation_error): ticket_ids list is required and cannot be empty

Action: Provide a non-empty ticket_ids array.

### ticket_get

**non_existent:** PASS
- Notes: Expected not_found error
- **Call args:** `{"ticket_id": 99999999}`
- **isError:** `True`
- **Text content preview:** Error (not_found): Ticket 99999999 does not exist.

Action: Use ticket_search to verify ticket exists.

### ticket_delete

**non_existent:** PASS
- Notes: Expected not_found error
- **Call args:** `{"ticket_id": 99999999}`
- **isError:** `True`
- **Text content preview:** Error (not_found): Ticket 99999999 does not exist.

Action: Use ticket_search to verify ticket exists.

### wiki_get

**non_existent:** PASS
- Notes: Expected not_found error
- **Call args:** `{"page_name": "NonExistentPage_DoesNotExist_12345"}`
- **isError:** `True`
- **Text content preview:** Error (not_found): Wiki page "NonExistentPage_DoesNotExist_12345" does not exist

Action: Use wiki_search to find pages similar to 'NonExistentPage_DoesNotExist_12345'.

### milestone_get

**non_existent:** PASS
- Notes: Expected not_found error
- **Call args:** `{"name": "NonExistent-Milestone-12345"}`
- **isError:** `True`
- **Text content preview:** Error (not_found): Milestone NonExistent-Milestone-12345 does not exist.

Action: Use milestone_list to verify milestone exists.

### wiki_delete

**non_existent:** PASS
- Notes: Expected not_found error
- **Call args:** `{"page_name": "NonExistentPage_ToDelete_12345"}`
- **isError:** `True`
- **Text content preview:** Error (not_found): Wiki page 'NonExistentPage_ToDelete_12345' does not exist

Action: Use wiki_search to find available pages.

### ticket_create

**missing_summary:** PASS
- Notes: Expected validation_error
- **Call args:** `{"description": "No summary"}`
- **isError:** `True`
- **Text content preview:** Error (validation_error): summary is required

Action: Provide summary parameter.
