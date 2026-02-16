# trac-mcp-server

Standalone MCP server that gives AI agents full access to Trac project management -- tickets, wiki, milestones, and search -- via the Model Context Protocol.

## Quick Start

```bash
pip install .
```

Set your Trac connection:

```bash
export TRAC_URL="https://trac.example.com"
export TRAC_USERNAME="your-username"
export TRAC_PASSWORD="your-password"
```

Run the server:

```bash
trac-mcp-server
```

## Configuration

All configuration is via environment variables (or a `.env` file in the working directory):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRAC_URL` | Yes | -- | Trac instance URL |
| `TRAC_USERNAME` | Yes | -- | Trac username |
| `TRAC_PASSWORD` | Yes | -- | Trac password |
| `TRAC_INSECURE` | No | `false` | Skip SSL verification (development only) |
| `TRAC_DEBUG` | No | `false` | Enable debug logging |
| `TRAC_MAX_PARALLEL_REQUESTS` | No | `5` | Max parallel XML-RPC requests |
| `TRAC_MAX_BATCH_SIZE` | No | `500` | Max items per batch operation (1-10000) |

## MCP Client Integration

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "trac": {
      "command": "trac-mcp-server",
      "env": {
        "TRAC_URL": "https://trac.example.com",
        "TRAC_USERNAME": "your-username",
        "TRAC_PASSWORD": "your-password"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add trac -e TRAC_URL=https://trac.example.com \
  -e TRAC_USERNAME=your-username \
  -e TRAC_PASSWORD=your-password \
  -- trac-mcp-server
```

### Other MCP Clients

Any MCP client that supports stdio transport can launch `trac-mcp-server` as a subprocess. Pass Trac credentials via environment variables.

## Available Tools (29)

### Tickets (11)
| Tool | Description |
|------|-------------|
| `ticket_search` | Search tickets with Trac query language |
| `ticket_get` | Get ticket details by ID |
| `ticket_create` | Create new tickets |
| `ticket_update` | Update existing tickets |
| `ticket_delete` | Delete tickets |
| `ticket_changelog` | Get ticket change history |
| `ticket_fields` | List available ticket fields |
| `ticket_actions` | Get available ticket actions |
| `ticket_batch_create` | Create multiple tickets in one batch |
| `ticket_batch_delete` | Delete multiple tickets in one batch |
| `ticket_batch_update` | Update multiple tickets in one batch |

### Wiki (6)
| Tool | Description |
|------|-------------|
| `wiki_get` | Get wiki page content (with Markdown conversion) |
| `wiki_search` | Search wiki pages |
| `wiki_create` | Create new wiki pages |
| `wiki_update` | Update existing wiki pages |
| `wiki_delete` | Delete wiki pages |
| `wiki_recent_changes` | List recent wiki changes |

### Wiki Files (3)
| Tool | Description |
|------|-------------|
| `wiki_file_push` | Push local file to wiki (auto format conversion) |
| `wiki_file_pull` | Pull wiki page to local file |
| `wiki_file_detect_format` | Detect content format (Markdown/TracWiki) |

### Milestones (5)
| Tool | Description |
|------|-------------|
| `milestone_list` | List all milestones |
| `milestone_get` | Get milestone details |
| `milestone_create` | Create new milestones |
| `milestone_update` | Update existing milestones |
| `milestone_delete` | Delete milestones |

### Sync (2)
| Tool | Description |
|------|-------------|
| `doc_sync` | Synchronize documents between local files and wiki |
| `doc_sync_status` | Check sync status |

### System (2)
| Tool | Description |
|------|-------------|
| `ping` | Test connectivity and return API version |
| `get_server_time` | Get Trac server time |

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Project Structure

```
src/trac_mcp_server/
  config.py       # Environment variable configuration
  core/           # Trac XML-RPC client, async utilities
  mcp/            # MCP server, tools, resources
  converters/     # Markdown <-> TracWiki conversion
  sync/           # Document synchronization
  detection/      # Content format detection
```

## Documentation

See [docs/reference/overview.md](docs/reference/overview.md) for detailed tool reference, configuration, and troubleshooting.
