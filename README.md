# perag

A personal RAG (Retrieval-Augmented Generation) toolkit for non-developers who work
with textual documents. It provides a local, private pipeline that lets you ask
questions across a collection of PDF, Word, Markdown, and plain-text files.

No server. No cloud. No daemon. Runs locally, stores data locally.

---

## Installation

```bash
uv tool install perag
```

Or with pip:

```bash
pip install perag
```

---

## Quick start

```bash
# 1. Initialize a collection in the current directory
perag init

# 2. Add documents
perag chunk report.pdf notes.md | perag embed | perag ingest

# 3. Ask a question
perag query "what are the termination conditions?"

# 4. Check what's in the collection
perag status --full
```

---

## Commands

### `perag init`

Creates a `.perag/` directory, writes a starter `config.toml`, adds `.perag/perag.db`
to `.gitignore`, and installs the Claude Code skill into `~/.claude/skills/perag.md`.
Safe to re-run — never overwrites an existing config.

### `perag chunk <file> [<file> ...]`

Splits one or more documents into chunks and writes JSON to stdout.

```bash
perag chunk contract.pdf
perag chunk notes.md summary.txt report.docx
perag chunk *.md
```

Supported formats: `.pdf` `.docx` `.doc` `.md` `.markdown` `.txt` `.text`

### `perag embed`

Reads chunks from stdin, adds embedding vectors, writes JSON to stdout. Shows a
spinner during model loading and embedding.

```bash
perag chunk notes.md | perag embed
```

### `perag ingest`

Reads embedded chunks from stdin and stores them in the local database. Re-ingesting
a document fully replaces its previous chunks.

```bash
perag chunk notes.md | perag embed | perag ingest
```

### `perag query "<text>"`

Retrieves the most relevant chunks from the database for a given question.

```bash
perag query "what is the notice period for termination?"
perag query "budget for Q3" --json   # structured JSON output
```

### `perag ls [paths...] [flags]`

Lists files and their status relative to the database. When piped, outputs one
filename per line — suitable for use with `$()`.

```bash
perag ls                  # all files: ok, stale, new, missing
perag ls --new            # not yet in the database
perag ls --stale          # changed since last ingest
perag ls --ok             # up to date
perag ls --missing        # in database but deleted from disk
perag ls -R               # recurse into subdirectories
perag ls --new --stale    # combine flags (OR)
perag ls docs/ *.md       # scan specific paths
```

### `perag status`

Shows a summary of the database and collection health.

```bash
perag status          # fast: file count, chunk count, model, last ingest, db size
perag status --full   # adds ok/stale/missing/new counts from disk scan
perag status --full -R  # recursive scan
```

### `perag prune`

Removes database entries for files that no longer exist on disk.

```bash
perag prune
```

### `perag config`

Shows which config files are active and the full set of effective settings.

```bash
perag config
```

---

## Common workflows

```bash
# Ingest everything new and changed in the current directory
perag chunk $(perag ls --new --stale) | perag embed | perag ingest

# Ingest new files recursively
perag chunk $(perag ls --new -R) | perag embed | perag ingest

# Clean up after deleting files
perag prune

# Debug why a query returns unexpected results
perag config
perag status --full
```

---

## Full pipeline with intermediate files

```bash
perag chunk document.pdf    > chunks.json
perag embed < chunks.json   > chunks_embedded.json
perag ingest < chunks_embedded.json
```

---

## Configuration

Perag uses a local-first config lookup — project config takes precedence over the
global default.

| Path | Purpose |
|---|---|
| `./.perag/config.toml` | Project-local settings (committed or gitignored) |
| `~/.perag/config.toml` | User-level defaults (shared across all projects) |
| `./.perag/perag.db` | Project-local vector database |
| `~/.perag/perag.db` | Global database (fallback when no local `.perag/`) |

`cd` is the context switch — different directories are different collections.

### `~/.perag/config.toml` (user defaults)

```toml
[embedding]
provider   = "local"             # local | ollama | openai
model      = "all-MiniLM-L6-v2"
batch_size = 32

[query]
top_k  = 5
output = "text"                  # text | json
```

### `./.perag/config.toml` (project override)

Only specify what differs from the global config:

```toml
[embedding]
model = "all-mpnet-base-v2"      # higher quality for this project
```

---

## Embedding providers

### local (default)

Uses [sentence-transformers](https://www.sbert.net/) — fully local, no API key,
no running service. Model weights are downloaded on first use and cached automatically.

```toml
[embedding]
provider = "local"
model    = "all-MiniLM-L6-v2"   # fast, good quality
# model = "all-mpnet-base-v2"   # slower, higher quality
```

### Ollama

Calls a locally running [Ollama](https://ollama.com) instance.

```toml
[embedding]
provider = "ollama"
model    = "nomic-embed-text"
url      = "http://localhost:11434"
```

### OpenAI

Calls the OpenAI embeddings API.

```toml
[embedding]
provider = "openai"
model    = "text-embedding-3-small"
api_key  = "sk-..."
```

---

## Claude Code integration

Run `perag init` to install the Claude Code skill automatically. It will be
copied to `~/.claude/skills/perag.md`, enabling Claude to query and ingest
documents on your behalf.

Claude will ingest documents when you say things like "remember this file" or
"add this to the knowledge base", and will query the collection before answering
questions about your documents.

---

## Development

```bash
git clone https://github.com/verhas/perag
cd perag
uv sync --all-extras
uv run pytest
```

Requires Python 3.11+.
