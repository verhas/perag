# Future: MCP Server (`perag mcp`)

**Status:** planned

## Motivation

`perag` currently integrates with Claude Code via a SKILL.md file that teaches the
assistant to invoke CLI subcommands as shell processes. This works, but has limitations:

- It depends on Claude Code reading and following the skill description correctly.
- Each operation spawns a subprocess, including model loading overhead on every query.
- It only works with Claude Code; other MCP-compatible clients (Cursor, Zed, custom
  agents) cannot use `perag` at all.

Implementing `perag` as an MCP server exposes the same functionality as structured,
typed tool calls over the Model Context Protocol. Any MCP-compatible client can
discover and invoke the tools without needing a skill description or shell access.

## What is MCP

The [Model Context Protocol](https://modelcontextprotocol.io) is an open standard for
connecting AI assistants to local tools and data sources. A local MCP server runs as a
child process and communicates with the client over stdio using JSON-RPC 2.0. No
network port is opened; no external service is involved.

## New command

```bash
perag mcp
```

Starts the MCP server on stdio. The client (Claude Code, Cursor, etc.) launches this
process and communicates with it over stdin/stdout. The server runs until the client
closes the connection.

```bash
perag mcp --directory /path/to/project   # explicit project root (default: cwd)
```

The `--directory` flag pins the server to a specific project root. Without it the
server uses the directory from which it was launched, following the same `.perag/`
walk-up logic as the other commands.

## Transport

stdio is the standard transport for local MCP servers. The client starts the process;
the server reads JSON-RPC requests from stdin and writes responses to stdout. Logging
and user-facing warnings go to stderr (never stdout, which is reserved for the
protocol).

HTTP/SSE transport is not planned — it would open a network port and reintroduce the
"no daemon" concerns.

## Tools exposed

Each tool maps directly to an existing `perag` subcommand.

### `perag_query`

Retrieves the most relevant chunks for a query string.

```json
{
  "name": "perag_query",
  "description": "Search the local document collection for relevant passages.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "text":   { "type": "string", "description": "Query text" },
      "top_k":  { "type": "integer", "description": "Number of results (default: config value)" },
      "output": { "type": "string", "enum": ["text", "json", "files"] }
    },
    "required": ["text"]
  }
}
```

Returns the same plain-text or JSON output as `perag query`.

### `perag_add`

Chunks, embeds, and ingests one or more files.

```json
{
  "name": "perag_add",
  "description": "Add documents to the knowledge base.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "paths":     { "type": "array", "items": { "type": "string" } },
      "as_format": { "type": "string", "enum": ["txt","text","md","markdown","pdf","docx","doc"] }
    },
    "required": ["paths"]
  }
}
```

### `perag_ls`

Lists files and their status relative to the database. Ignore rules (hardcoded
exclusions, `.perag/ignore`, and optionally `.gitignore`) are applied automatically,
matching the behaviour of the CLI.

```json
{
  "name": "perag_ls",
  "description": "List tracked files and their status (ok, stale, new, missing). Ignore rules are applied automatically.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "paths":     { "type": "array", "items": { "type": "string" }, "description": "Files or directories to scan (default: cwd)" },
      "filter":    {
        "type": "array",
        "items": { "type": "string", "enum": ["ok", "stale", "new", "missing"] },
        "description": "Show only these statuses (default: all). Multiple values are combined with OR."
      },
      "recurse":   { "type": "boolean", "description": "Recurse into subdirectories" },
      "gitignore": { "type": "boolean", "description": "Apply .gitignore patterns (overrides [ls] use_gitignore config)" }
    }
  }
}
```

`filter` is an array so the caller can request multiple statuses in one call, mirroring
the CLI's `perag ls --new --stale` behaviour. Omitting `filter` returns all statuses.

### `perag_status`

Returns a summary of the collection. With `full: true`, also scans the file system for
stale, new, and missing file counts — ignore rules are applied to the disk scan.

```json
{
  "name": "perag_status",
  "description": "Return database statistics: file count, chunk count, model, last ingest. Pass full=true for file system counts.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "full":    { "type": "boolean", "description": "Include file system scan for stale/new/missing counts" },
      "recurse": { "type": "boolean", "description": "Recurse into subdirectories when scanning (requires full=true)" }
    }
  }
}
```

### `perag_update`

Prunes deleted entries and re-ingests stale files.

```json
{
  "name": "perag_update",
  "description": "Remove deleted files from the database and re-ingest changed files.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "recurse": { "type": "boolean" }
    }
  }
}
```

### `perag_rm`

Removes one or more files from the database.

```json
{
  "name": "perag_rm",
  "description": "Remove files from the knowledge base.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "paths": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["paths"]
  }
}
```

### `perag_prune`

Removes database entries for files that no longer exist on disk.

```json
{
  "name": "perag_prune",
  "description": "Remove database entries for files that no longer exist on disk.",
  "inputSchema": { "type": "object", "properties": {} }
}
```

## Tools deliberately not exposed

### `perag_chunk` and `perag_embed`

These two are intentionally excluded from the MCP surface.

`perag chunk` and `perag embed` are pipeline primitives designed for shell composition:
they read and write JSON on stdin/stdout so a human or a script can inspect
intermediate state, swap in a custom chunker, or save embedded chunks to a file for
reuse. That composability is their entire value.

An AI assistant has no use for intermediate JSON. When it wants to add a document to
the knowledge base it wants a single operation that succeeds or fails — exactly what
`perag_add` provides. Exposing `perag_chunk` and `perag_embed` as separate MCP tools
would require the client to coordinate a multi-step stateful pipeline across tool
calls, passing large JSON payloads back and forth through the protocol. This is
fragile, slow, and leaks implementation detail that the client should never need to
care about.

The low-level pipeline remains available on the command line for power users and
scripting. The MCP surface stays at the task level.

## Implementation

The Python `mcp` package (Anthropic's official SDK) provides the server runtime.
It handles the JSON-RPC framing, capability negotiation, and stdio transport.

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

app = Server("perag")

@app.list_tools()
async def list_tools(): ...

@app.call_tool()
async def call_tool(name, arguments): ...
```

Each tool handler calls the same internal functions that the CLI commands use
(`get_chunker`, `_embed_chunks`, `db_ingest`, `search`, etc.) — no subprocess,
no CLI parsing overhead.

### New optional dependency

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0"]
```

Installed with:

```bash
uv tool install perag --extra mcp
pip install "perag[mcp]"
```

The `perag mcp` command raises a clear error if the `mcp` package is not installed.

## Client configuration

### Claude Code

Add to `.mcp.json` in the project root or to the global Claude Code MCP config:

```json
{
  "mcpServers": {
    "perag": {
      "command": "perag",
      "args": ["mcp"],
      "cwd": "/path/to/project"
    }
  }
}
```

Claude Code launches `perag mcp` as a child process when the session starts. The
`cwd` field pins the server to the right project directory.

### Relationship to SKILL.md

The MCP server and SKILL.md serve different clients:

| | SKILL.md | MCP server |
|---|---|---|
| Works with | Claude Code only | Any MCP client |
| Integration | Shell subcommands | Typed tool calls |
| Model loading | Per invocation | Once per session |
| Discovery | Manual (skill file) | Automatic (MCP protocol) |

Once the MCP server is mature, the SKILL.md can be simplified to just explain
what `perag` is — tool invocation is handled by the protocol, not by instructions.

## Directory scope

The server is scoped to the directory it was started in (or `--directory`). All tool
calls operate on that directory's `.perag/` collection. Starting two server instances
in two different directories gives two independent scopes — consistent with how the
CLI works.

## Why not now

- The `mcp` Python SDK is still stabilizing; the API may change between minor versions.
- The embedding daemon (0.1.4) already addresses the model-loading latency problem for
  the CLI path. The MCP server would be the cleaner long-term solution but is not
  urgent.
- Adding an optional dependency and a new server runtime increases the maintenance
  surface.

Revisit when the MCP SDK reaches a stable 1.x release and there is user demand from
non-Claude-Code clients.
