# perag

`perag` is a personal RAG (Retrieval-Augmented Generation) system that works out of
the box. It gives your AI assistant access to your own documents — no cloud service,
no configuration, no infrastructure to manage.

AI assistants like Claude Code are powerful — but they can only work with what fits in
their context window. You cannot simply hand them a folder of a hundred documents and
ask a question. `perag` solves this by reading and indexing your documents locally,
then selecting only the passages relevant to your question and feeding those to the
assistant. The result is accurate, grounded answers drawn from your own files — without
overwhelming the context window and without sending your documents to any cloud service.

Note: `perag` works with AI assistants that can run programs on your computer, such as
Claude Code.

## How it works with an AI assistant

Install `perag` and run `perag init` once. After that, just talk to your AI assistant
as you normally would:

- "Remember this contract — I'll want to ask questions about it later."
- "What does the NDA say about liability?"
- "Find everything in my notes about the Q3 budget."

The assistant remembers your documents, finds the relevant passages, and gives you
accurate answers grounded in what is actually written — not guesses. Everything stays
on your computer. Nothing is sent to a cloud service. No account required.

You can also run `perag` directly from the terminal if you prefer.

---

## Installation

`perag` is a Python program. You need Python 3.11 or later installed on your computer.
If you are not sure whether you have it, open a terminal and type `python3 --version`.
If Python is missing or too old, download it from [python.org](https://www.python.org/downloads/).

Once Python is available, install `perag` using one of the two standard Python package
managers:

### With uv (recommended)

`uv` is a fast, modern Python package manager. If you do not have it yet, install it
by following the instructions at [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) —
it is a one-line command for macOS, Linux, and Windows.

```bash
uv tool install perag
```

### With pip

`pip` comes bundled with Python. No separate installation needed.

```bash
pip install perag
```

---

## Quick start

There is only one thing you need to do yourself: run `perag init` once in the folder
where your documents live. This sets everything up — your AI assistant handles the
rest automatically.

```bash
perag init
```

After that, tell your AI assistant what you want:

> "Remember report.pdf — I'll want to ask questions about it."
> "What are the termination conditions in the contract?"
> "What changed in my notes since last week?"

The assistant reads the skill description that `perag init` installs and knows how to
add documents, search them, and keep track of what has changed. You do not need to
learn the individual commands.

---

## Commands

### `perag add <file> [<file> ...]`

Chunks, embeds, and ingests one or more documents in a single step. This is the
everyday shortcut — equivalent to running `perag chunk | perag embed | perag ingest`
but without the pipe.

```bash
perag add report.pdf
perag add notes.md summary.txt contract.docx
perag add *.md
```

Use the full pipeline (`perag chunk | perag embed | perag ingest`) when you need to
inspect intermediate output, use a custom chunker, or save embedded chunks to a file.

### `perag init`

Creates a `.perag/` directory, writes a starter `config.toml`, adds `.perag/perag.db`
to `.gitignore`, and installs the Claude Code skill into `~/.claude/skills/perag.md`.
Safe to re-run — never overwrites an existing config or an existing skill file.
Use `--reinstall-skill` to force the skill file to be overwritten.

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
spinner during model loading and embedding, and prints a summary line to stderr
when complete. The local model (`all-MiniLM-L6-v2`, ~90 MB) is downloaded from
HuggingFace Hub on first use and cached locally; subsequent runs load it from
the cache without a network connection.

```bash
perag chunk notes.md | perag embed
```

### `perag ingest`

Reads embedded chunks from stdin and stores them in the local database. Re-ingesting
a document fully replaces its previous chunks.

```bash
perag chunk notes.md | perag embed | perag ingest
```

### `perag query [text]`

Retrieves the most relevant chunks from the database for a given question.
Query text can be passed as an argument or supplied via stdin — useful when the
query is long or comes from a file.

```bash
perag query "what is the notice period for termination?"
perag query "budget for Q3" --json    # structured JSON output
perag query "budget for Q3" --files   # filenames only, ordered by relevance
perag query < question.txt            # read query from a file
cat context.md | perag query          # pipe query text from another command
```

`--files` returns deduplicated source filenames instead of chunk content, ordered by
how many matching chunks each file contributed. When piped, one filename per line —
suitable for use with `$()` or wiki-style navigation.

### `perag ls [paths...] [flags]`

Lists files and their status relative to the database. When piped, outputs one
filename per line — suitable for use with `$()`.

```bash
perag ls                  # all files: ok, stale, new, missing
perag ls --new            # not yet in the database
perag ls --stale          # changed since last ingest
perag ls --ok             # up to date
perag ls --missing        # in database but deleted from disk
perag ls --recurse        # recurse into subdirectories (short: -R)
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

> **Large collections:** each pipeline invocation holds all chunks in memory at once.
> If you have hundreds of files, ingest them one at a time using a shell loop to avoid
> high memory use:
>
> ```bash
> for f in docs/*.pdf; do
>     perag chunk "$f" | perag embed | perag ingest
> done
> ```

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

---

## License

`perag` is dual-licensed under the **Apache License 2.0** (`LICENSE`) and the
**MIT License** (`LICENSE-MIT`). You may choose either license when using,
modifying, or distributing this software.
