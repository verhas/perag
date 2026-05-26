# perag — Claude Code Skill

## What this skill does

`perag` is a local RAG tool. Use it to:
1. **Ingest documents** the user wants to store in their personal knowledge base
2. **Query the knowledge base** to retrieve relevant context before answering questions
3. **Manage the collection** — check status, list files, prune deleted entries

---

## Ingesting documents

### When to ingest

Ingest whenever the user says something like:
- "Add this document to your knowledge base"
- "Remember this file"
- "Store this in the RAG"
- "Index this for me"
- "Feed this into the RAG"
- "I want you to be able to search through this later"

Also ingest proactively when a user provides a file path alongside a task and it's
clear they want it to be part of the searchable collection.

### How to ingest

**Step 1 — ensure the collection is initialized** (only needed the first time):

```bash
ls .perag/ 2>/dev/null || perag init
```

**Step 2 — run the full pipeline:**

```bash
perag chunk path/to/document.pdf | perag embed | perag ingest
```

Supported formats: `.pdf`, `.docx`, `.doc`, `.md`, `.markdown`, `.txt`, `.text`

**After ingesting**, confirm to the user which file was added and that it is now
searchable. Example: "I've added `contracts/nda_2024.pdf` to your knowledge base.
You can now ask me questions about it."

### Ingesting multiple files

```bash
perag chunk report.pdf notes.md summary.txt | perag embed | perag ingest
```

### Ingesting new or changed files only

```bash
# New files not yet in the database
perag chunk $(perag ls --new) | perag embed | perag ingest

# Files changed since last ingest
perag chunk $(perag ls --stale) | perag embed | perag ingest

# Both at once
perag chunk $(perag ls --new --stale) | perag embed | perag ingest
```

### Re-ingesting an updated file

Just run the pipeline again — ingest automatically replaces all existing chunks for
that source file.

---

## Querying for context

### When to query

Before answering any question that might be covered by the user's document collection:
- Questions about contracts, policies, reports, notes, or any documents the user has mentioned
- When the user asks "what does my X say about Y"
- When prior conversation suggests relevant documents have been ingested

### How to query

```bash
perag query "the specific aspect you need context on"
```

Run this **before** formulating your answer. Prepend the retrieved chunks to your
working context.

If no results come back, answer from your own knowledge and note that nothing relevant
was found in the knowledge base.

```bash
perag query "question" --json   # structured output if needed
```

---

## Managing the collection

### Check status

```bash
perag status          # quick summary: file count, chunk count, last ingest
perag status --full   # adds ok/stale/missing/new counts from disk scan
perag status --full -R  # recursive scan
```

### List files by status

```bash
perag ls              # all files: ok, stale, new, missing
perag ls --new        # files on disk not yet in the database
perag ls --stale      # files changed since last ingest
perag ls --ok         # files that are up to date
perag ls --missing    # database entries whose file no longer exists
perag ls -R           # recurse into subdirectories
```

### Remove stale database entries

When files have been deleted from disk, clean up their database entries:

```bash
perag prune
```

### Show active configuration

```bash
perag config
```

---

## Initializing a new collection

If `.perag/` does not exist in the current directory:

```bash
perag init
```

This creates `.perag/config.toml`, registers `.perag/perag.db` in `.gitignore`,
and installs this skill into `~/.claude/skills/perag.md`.

---

## Output format (plain text query results)

Each result block looks like:

```
# path/to/file.pdf, page 3, section: Termination
The agreement shall terminate upon 30 days written notice...
```

Multiple results are separated by blank lines.

---

## Notes

- The database is at `.perag/perag.db` (local) or `~/.perag/perag.db` (global fallback)
- Config is at `.perag/config.toml` or `~/.perag/config.toml`
- `perag chunk` and `perag embed` write to stdout; `perag ingest` confirms to stderr
- `perag ls` outputs one filename per line when piped — suitable for `$()`
- Ingesting a document fully replaces its previous chunks — safe to re-run after edits
- Embedding runs locally by default (no API key or running service needed)
