# Perago — Personal RAG Toolkit

## Project Overview

**Perago** (Latin: *to carry through to completion*) is a personal productivity tool for
non-developers who work with textual documents (PDF, Word, Markdown, plain text). It
provides a local, private RAG (Retrieval-Augmented Generation) pipeline that enriches
prompts with relevant context retrieved from a personal document collection.

The command-line tool is called `perag`. It is intentionally not a service — no server,
no daemon, no cloud dependency. It runs locally, stores data locally, and is invoked
from the command line or by Claude Code via a SKILL.md.

---

## Repository Structure

```
perago/
├── CLAUDE.md                  # This file
├── README.md                  # User-facing documentation
├── pyproject.toml             # Root package definition (if monorepo build)
├── config.example.toml        # Example configuration file
│
├── perag/                     # Main CLI package (entry point: perag <subcommand>)
│   ├── __init__.py
│   ├── cli.py                 # Subcommand dispatcher (chunk/embed/ingest/query)
│   ├── config.py              # Config loading from config.toml
│   └── schema.py              # Shared JSON chunk schema (dataclass/TypedDict)
│
├── chunkers/                  # Format-aware chunkers (one module per format)
│   ├── __init__.py
│   ├── base.py                # Abstract base class: Chunker.chunk(path) -> [Chunk]
│   ├── pdf.py                 # PDF chunking via pdfplumber
│   ├── docx.py                # Word chunking via python-docx
│   ├── markdown.py            # Markdown chunking via markdown-it-py
│   ├── text.py                # Plain text / paragraph-aware fallback
│   └── registry.py            # Maps file extension -> Chunker class
│
├── embedders/                 # Embedding providers (one module per provider)
│   ├── __init__.py
│   ├── base.py                # Abstract base class: Embedder.embed([str]) -> [[float]]
│   ├── ollama.py              # Ollama HTTP API
│   ├── openai.py              # OpenAI embeddings API
│   ├── local.py               # sentence-transformers (fully local, no API key)
│   └── registry.py            # Maps provider name -> Embedder class
│
├── db/                        # sqlite-vec database layer
│   ├── __init__.py
│   ├── store.py               # Schema init, upsert, meta table management
│   └── search.py              # ANN query, returns top-k chunks
│
├── tests/
│   ├── fixtures/              # Sample PDF, DOCX, MD, TXT files for testing
│   ├── test_chunkers.py
│   ├── test_embedders.py
│   ├── test_db.py
│   └── test_pipeline.py       # End-to-end: chunk -> embed -> ingest -> query
│
├── skills/
│   └── SKILL.md               # Claude Code skill: how to use perag from Claude Code
│
└── docs/
    ├── chunking.md            # How chunking works per format
    ├── embedders.md           # Supported embedding providers and configuration
    └── pipeline.md            # Full pipeline walkthrough
```

---

## Subcommand Design

All subcommands read/write JSON on stdin/stdout, making the pipeline composable:

```bash
# Full pipeline (piped)
perag chunk document.pdf | perag embed | perag ingest

# Full pipeline (with intermediate files for inspection/debugging)
perag chunk document.pdf      > chunks.json
perag embed   < chunks.json   > chunks_embedded.json
perag ingest  < chunks_embedded.json

# Query
perag query "what are the termination conditions?"
```

### `perag chunk <file>`
- Detects format from extension
- Dispatches to the appropriate chunker in `chunkers/`
- Outputs a JSON array of Chunk objects to stdout

### `perag embed`
- Reads JSON array of Chunk objects from stdin
- Calls the configured embedding provider in batches
- Outputs the same JSON array with `vector` field added

### `perag ingest`
- Reads JSON array of embedded Chunk objects from stdin
- Writes to the sqlite-vec database
- Enforces dimension and model name consistency via the `meta` table
- Upserts by `id` (re-ingesting an updated document replaces existing chunks)

### `perag init`
- Creates `.perag/` in the current directory
- Writes a minimal `config.toml` inheriting from `~/.perag/config.toml` if it exists
- Adds `.perag/perag.db` to `.gitignore` if a `.gitignore` is present
- Safe to re-run — never overwrites an existing config

### `perag query "<text>"`
- Embeds the query text using the configured provider
- Performs ANN search against the sqlite-vec database
- Outputs top-k chunks as plain text (suitable for Claude Code context injection)
- `--json` flag outputs structured JSON instead

---

## JSON Chunk Schema

Every chunk flowing through the pipeline conforms to this schema:

```json
{
  "id":                 "contracts/nda_2024.pdf::chunk::7",
  "source":             "contracts/nda_2024.pdf",
  "content":            "The agreement shall terminate upon 30 days written notice...",
  "metadata": {
    "format":           "pdf",
    "page":             3,
    "section":          "Termination"
  },
  "embedding_model":    "nomic-embed-text",
  "embedding_provider": "ollama",
  "vector":             [0.021, -0.134, 0.087, "..."]
}
```

After `perag chunk`, the fields `embedding_model`, `embedding_provider`, and `vector`
are all `null`. After `perag embed` all three are populated by the embedder with its
own identity. The `metadata` fields are format-specific and optional for downstream
consumers.

### Embedder behaviour with pre-embedded chunks

`perag embed` inspects `embedding_model` on every incoming chunk before deciding what
to do:

| `embedding_model` in chunk | Matches current config? | Action |
|---|---|---|
| `null` | — | Embed, populate all three fields |
| set | yes | Skip — pass through unchanged |
| set | no | Re-embed, overwrite vector and embedding fields |

This means re-running `perag embed` after changing providers is safe and correct —
leftover JSON files from a previous run are detected and re-embedded automatically.

### Ingestor validation

The ingestor enforces consistency between the chunk and the database before writing:

| Chunk state | Action |
|---|---|
| `vector` is `null` | Hard error: *"chunks have no vectors — run `perag embed` first"* |
| `embedding_model` matches `meta` table | Ingest (upsert by `id`) |
| `embedding_model` differs from `meta` table | Hard error: *"embedding model mismatch — re-run `perag embed` or rebuild the database"* |

---

## Database Design

A single SQLite file (`perag.db`) located in `.perag/` in the current directory, or
falling back to `~/.perag/perag.db` if no local `.perag/` exists.

Tables:
- **`chunks`**: id, source, content, metadata (JSON), vector (sqlite-vec column)
- **`meta`**: embedding model name, embedding provider, vector dimensions, creation timestamp

On first `perag ingest`, the meta table is written. On subsequent ingests, both
`embedding_model` and `embedding_provider` are validated against the meta table — a
mismatch on either is a hard error with a clear message directing the user to re-embed
or rebuild the database.

---

## Configuration

Perago uses a local-first lookup strategy, the same pattern as `.git` and `.claude`.
The tool always checks the current directory first and falls back to the user-level
global config.

### Lookup order

```
./.perag/config.toml       # project-local config (may be committed)
./.perag/perag.db          # project-local database
~/.perag/config.toml       # user-level defaults (fallback)
~/.perag/perag.db          # user-level database (fallback)
```

A researcher with three document collections simply has three directories, each with
its own `.perag/`. The `cd` is the context switch — no flags, no project names.

The global `~/.perag/config.toml` holds the user's preferred embedding provider and
model so every new project inherits sensible defaults without repeating configuration.
A project-local config only needs to override what differs from the global defaults.

### `.gitignore` recommendation

```
.perag/perag.db        # large, machine-generated — never commit
.perag/config.toml     # optional: commit if you want to share project config
```

### Config file format

`~/.perag/config.toml` (user-level defaults):

```toml
[embedding]
provider   = "ollama"          # ollama | openai | local
model      = "nomic-embed-text"
url        = "http://localhost:11434"   # only for ollama
# api_key  = "sk-..."                  # only for openai
batch_size = 32

[query]
top_k  = 5
output = "text"                # text | json
```

`./.perag/config.toml` (project-local override — only specify what differs):

```toml
[embedding]
model = "mxbai-embed-large"    # override model for this project only
```

---

## Development Conventions

### Python version
Python 3.11+. No older versions. Use `match` statements freely.

### Dependencies
Managed with `uv`. Lock file committed. No unpinned dependencies in production code.

```
pdfplumber        # PDF parsing
python-docx       # Word parsing
markdown-it-py    # Markdown parsing
sqlite-vec        # Vector search SQLite extension
sentence-transformers  # Local embeddings (optional)
httpx             # HTTP client for Ollama/OpenAI
tomllib           # Config parsing (stdlib in 3.11+)
typer             # CLI framework
rich              # Terminal output formatting
```

### Code style
- `ruff` for linting and formatting
- Type annotations on all public functions
- Docstrings on all public classes and methods
- No global state — everything flows through config and explicit arguments

### Testing
- `pytest` with fixtures in `tests/fixtures/`
- Each chunker must have at least one real-file test (not mocked)
- The embedder tests mock the HTTP/model calls — no network in CI
- One end-to-end pipeline test using the `local` embedder (no API key needed)

### Adding a new chunker
1. Create `chunkers/<format>.py` implementing `base.Chunker`
2. Register it in `chunkers/registry.py`
3. Add at least one fixture file to `tests/fixtures/`
4. Add tests in `tests/test_chunkers.py`
5. Document the chunking strategy in `docs/chunking.md`

### Adding a new embedder
1. Create `embedders/<provider>.py` implementing `base.Embedder`
2. Register it in `embedders/registry.py`
3. Add config documentation in `docs/embedders.md`

---

## Claude Code Integration (SKILL.md)

The `skills/SKILL.md` file teaches Claude Code how to use `perag` as a context
enrichment tool. The typical workflow Claude Code should follow:

1. When given a task that might benefit from document context, run:
   `perag query "<relevant aspect of the task>"` 
2. Prepend the output to the working context before responding
3. When new documents are provided, run the full pipeline:
   `perag chunk <file> | perag embed | perag ingest`

The SKILL.md lives inside the repo so it is versioned alongside the tool itself.
Users copy or symlink it into their Claude Code skills directory.

---

## Non-Goals

- No web UI
- No REST API or daemon mode
- No multi-user support
- No cloud sync
- No support for source code files (use RustRAG or similar for that)
- No streaming ingestion of live data sources

This is a tool for a person with a folder of documents who wants to ask questions
across them. It should stay that simple.
