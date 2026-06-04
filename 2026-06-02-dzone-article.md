# Give Your AI Assistant Long-Term Memory With perag

You have a folder of contracts, a year of meeting notes, three product specification
PDFs, and a research report you keep meaning to read properly. Your AI assistant is
brilliant — but it cannot see any of it. Every conversation starts from zero. You paste
snippets by hand, copy-paste summaries, and still get answers that miss the nuance
buried on page 14 of the spec.

The root cause is architectural. AI assistants work within a context window — the amount
of text they can hold in mind at once. A single lengthy PDF can fill it completely. A
folder of a hundred documents is simply out of reach. You cannot hand an assistant your
entire document archive and ask a question; the math does not allow it.

This is the problem `perag` solves.

---

## The Idea

The technique is called Retrieval-Augmented Generation, or RAG. Instead of feeding an
AI assistant everything at once, you pre-process your documents into a searchable index.
When a question arrives, you search the index for the passages most likely to be
relevant, and feed only those — a few paragraphs at most — into the assistant's context.
The assistant answers from real source material, not from training data guesses.

RAG is not new. What is new is how much machinery it normally requires: a vector
database service, an embedding API, a retrieval layer, a prompt engineering layer, and
something to hold all of it together. For a developer experimenting on a personal
project, or a researcher with a document archive, that stack is far too heavy.

`perag` is RAG that works out of the box.

---

## What perag Is

`perag` is a command-line tool that indexes your local documents and makes them
searchable by your AI assistant. It runs entirely on your machine. It needs no server,
no cloud account, no API key, and no configuration beyond a single `init` command.
Embeddings are computed locally using
[sentence-transformers](https://www.sbert.net/). The index lives in a
[sqlite-vec](https://github.com/asg017/sqlite-vec) database file next to your
documents. Nothing leaves your computer.

The design is deliberately minimal. There is no daemon to keep running, no web UI to
open, no project to register. You `cd` into a directory and `perag` treats that
directory as your collection. Switch directories and you switch collections — the same
mental model as `git`.

Architecturally, `perag` is a UNIX pipeline. The three stages — chunk, embed, ingest
— are separate processes that communicate via a defined JSON format on stdin and stdout.
`perag add` is a shortcut for the full pipeline; the pipeline itself is the extension
point. Any tool that reads or writes the JSON format can participate.

`perag` integrates with Claude Code by installing a skill file that teaches the
assistant how to query and ingest documents on your behalf. You talk to your assistant
naturally; it runs `perag` in the background.

---

## See It Work

Install once:

```bash
uv tool install perag
# or: pip install perag
```

Initialise a collection in your project directory:

```bash
cd ~/documents/my-project
perag init
```

Add your documents:

```bash
perag add report.pdf notes.md contract.docx
# Added 3 file(s), 47 chunks → .perag/perag.db
```

`perag add` is a one-step shortcut. When you want to see what is happening — or
substitute your own chunker or embedder — you run the pipeline explicitly:

```bash
perag chunk contract.docx | perag embed | perag ingest
```

That is it. Now ask your AI assistant a question about the contract:

> *"What are the termination conditions in the contract?"*

Behind the scenes, Claude runs:

```bash
perag query "termination conditions contract"
```

And receives back the relevant passages:

```
# contract.docx, paragraph 42
Either party may terminate this agreement with 30 days written notice.
Termination for cause requires written documentation of the breach and
a 10-day cure period before the termination becomes effective.
```

Claude answers your question grounded in what the contract actually says — not a
plausible guess. It tells you where it found the answer. You can verify it in seconds.

---

## How It Fits Into Your Workflow

A document collection is a living thing. Files change. Notes are updated. Old
contracts expire and new ones arrive. `perag` is designed for this.

Check what has changed since your last ingest:

```bash
perag ls --stale
perag ls --new
```

Re-ingest everything that has changed in one command:

```bash
perag update
```

Remove a file that no longer belongs in the collection:

```bash
perag rm old-contract.pdf
```

Query from the terminal when you want to search without the assistant:

```bash
perag query "indemnification clause" --files
# Returns the files most likely to contain relevant content, ranked by match quality
```

The collection reflects the current state of your documents at all times. `perag`
does not require a separate sync step or a scheduled job.

---

## Under the Hood

`perag` uses [sentence-transformers](https://www.sbert.net/) for local embedding — the
`all-MiniLM-L6-v2` model by default, a 90 MB download that runs comfortably on a
laptop CPU. Vectors are stored and searched in
[sqlite-vec](https://github.com/asg017/sqlite-vec), an extension that brings
approximate nearest-neighbour search to ordinary SQLite files. The entire index for a
few hundred documents typically fits in well under 100 MB.

Documents are split into chunks before embedding. The chunking strategy is
format-aware: PDFs are split by page, Markdown files by heading, Word documents by
paragraph groups. Each chunk carries metadata — page number, section heading,
paragraph index — so the assistant can cite its sources precisely.

If you prefer to use Ollama or the OpenAI embeddings API instead of the local model,
a one-line config change switches providers. The same database works across providers
as long as you re-embed after switching.

---

## Open by Design

The three pipeline stages communicate via a documented JSON format. Each chunk flowing
between stages looks like this:

```json
{
  "id":       "contracts/nda_2024.pdf::chunk::7",
  "source":   "contracts/nda_2024.pdf",
  "content":  "The agreement shall terminate upon 30 days written notice...",
  "metadata": { "format": "pdf", "page": 3, "section": "Termination" },
  "embedding_model":    null,
  "embedding_provider": null,
  "vector":             null
}
```

After `perag chunk`, the embedding fields are `null`. After `perag embed`, they are
populated. After `perag ingest`, the chunks are stored. Any tool that reads or writes
this format can replace or extend any stage.

### Custom chunkers

If your organisation uses a proprietary document format — a legacy system export, a
structured XML schema, an internal binary — you can write a chunker in any language
that outputs this JSON to stdout:

```bash
my-proprietary-chunker legal-brief.prp | perag embed | perag ingest
```

The chunker does not need to be Python. It does not need to know anything about
embeddings or databases. It only needs to produce JSON chunks.

### Custom embedders

If your organisation runs an internal embedding API — for data governance, compliance,
or because you have a domain-specific model fine-tuned on your corpus — you can replace
`perag embed` with your own:

```bash
perag chunk document.pdf | my-internal-embedder | perag ingest
```

Your embedder reads the JSON array from stdin, calls whatever API it needs, populates
the `vector`, `embedding_model`, and `embedding_provider` fields, and writes the result
back to stdout. `perag ingest` does not care where the vectors came from.

### Intermediate inspection

Because each stage writes to stdout, you can examine the output of any stage before it
reaches the next:

```bash
perag chunk report.pdf       > chunks.json
perag embed  < chunks.json   > embedded.json
perag ingest < embedded.json
```

This is useful when tuning a custom chunker: run it in isolation, inspect the JSON, and
feed it through the rest of the pipeline only when the output looks right. It is also
useful for saving embeddings to a file and re-ingesting them after switching models —
`perag embed` detects already-embedded chunks and skips them automatically.

The UNIX pipeline design means `perag` is not a closed system you configure, but an
open one you extend. The built-in chunkers and embedders cover the common cases; the
pipe interface and the JSON contract cover everything else.

---

## What Is Coming

`perag` is at version 0.1.x. The foundation is stable; the roadmap is ambitious.

- **MCP server** — a `perag mcp` command will expose the full collection as a native
  Model Context Protocol server, making it available to any MCP-compatible client
  (Claude Code, Cursor, Zed, custom agents) without a skill file.

- **Query hit tracking** — every time a document chunk appears in a query result,
  `perag` will remember it. Over time the system learns which documents you actually
  find useful, not just which ones you thought would be useful when you ingested them.

- **Organic agentic memory** — hit tracking is the first step toward implementing all
  five cognitive memory types: working, long-term, episodic, semantic, and procedural.
  The goal is a system that knows not just what your documents say, but which ones
  matter, when you consulted them, and which ones you habitually reach for — an organic
  memory that reflects your actual intellectual life rather than a static archive.

- **Hybrid BM25 + vector search** — vector search excels at semantic similarity but
  struggles with rare terms, proper nouns, and exact phrases. Adding BM25 keyword
  search and combining the two with reciprocal rank fusion will improve precision
  across a wider range of queries.

- **Forgetting curve** — access weights will decay over time, so documents you stopped
  consulting gradually fade from prominence. Documents you return to repeatedly are
  strengthened. The collection becomes less of a database and more of a memory.

---

## Try It

```bash
uv tool install perag
cd your-document-folder
perag init
perag add *.pdf *.md
```

Then ask your AI assistant a question about your documents.

Source code and documentation: [github.com/verhas/perag](https://github.com/verhas/perag)

`perag` is dual-licensed under Apache 2.0 and MIT — use whichever suits your project.
It is written in Python and requires Python 3.11 or later. Feedback and contributions
are welcome.
