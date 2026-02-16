# Configuration

trac-mcp-server is configured via environment variables. There are no configuration files.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRAC_URL` | Yes | -- | Trac instance URL (must start with `http://` or `https://`) |
| `TRAC_USERNAME` | Yes | -- | Trac username for XML-RPC authentication |
| `TRAC_PASSWORD` | Yes | -- | Trac password for XML-RPC authentication |
| `TRAC_INSECURE` | No | `false` | Skip SSL certificate verification (development only) |
| `TRAC_DEBUG` | No | `false` | Enable debug logging |
| `TRAC_MAX_PARALLEL_REQUESTS` | No | `5` | Maximum parallel XML-RPC requests to Trac |
| `TRAC_MAX_BATCH_SIZE` | No | `500` | Maximum items per batch ticket operation (1-10000) |

Boolean variables (`TRAC_INSECURE`, `TRAC_DEBUG`) accept `true`, `1`, `yes`, or `on` (case-insensitive). Any other value is treated as `false`.

## .env File Support

trac-mcp-server uses [python-dotenv](https://pypi.org/project/python-dotenv/) to load a `.env` file from the working directory. This is useful for local development.

```bash
# .env
TRAC_URL=https://trac.example.com
TRAC_USERNAME=your-username
TRAC_PASSWORD=your-password
TRAC_INSECURE=false
TRAC_DEBUG=false
TRAC_MAX_PARALLEL_REQUESTS=5
TRAC_MAX_BATCH_SIZE=500
```

Environment variables set in the shell take precedence over values in `.env`.

## MCP Client Configuration

When an MCP client (Claude Desktop, Claude Code, etc.) launches `trac-mcp-server`, it passes environment variables in the client configuration.

**Claude Desktop** (`claude_desktop_config.json`):

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

**Claude Code:**

```bash
claude mcp add trac -e TRAC_URL=https://trac.example.com \
  -e TRAC_USERNAME=your-username \
  -e TRAC_PASSWORD=your-password \
  -- trac-mcp-server
```

## Validation

Configuration is validated at server startup. The server will refuse to start with a clear error message if validation fails.

**Validation rules:**

- `TRAC_URL` must start with `http://` or `https://`
- `TRAC_USERNAME` cannot be empty
- `TRAC_PASSWORD` cannot be empty
- When `TRAC_INSECURE=true`, a warning is logged (use only for development)

The `trac-mcp-server` command also supports CLI flags that override environment variables. See the [CLI Reference](cli.md) for details.

---

[Back to Reference Overview](overview.md)
