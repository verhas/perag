# FAQ: When Should I Use `perag` Instead of Claude Cowork?

## I already use Claude Cowork to work with documents. Why would I need `perag`?

For most Cowork users, the honest answer is: **probably never** — at least not right away.

If you're uploading a handful of documents to Cowork and asking questions about them, Cowork handles that fine. You get the full document content in context, Claude reasons over it directly, and you're done. `perag` adds zero value here — it's extra machinery solving a problem you don't have.

---

## So when *does* `perag` actually win?

The RAG pattern only pays off when your document collection is **too large to fit in context** and **grows over time**. Two dimensions drive this:

**Volume.** If you have 50+ substantial documents — hundreds of pages of contracts, a whole codebase's worth of specs, years of meeting notes, a technical library — you physically cannot upload them all to Cowork at once, and even if you could, Claude would be flooded with irrelevant content. `perag` indexes everything once and retrieves only the 3–5 most relevant passages per query. The context window stays clean regardless of collection size.

**Persistence.** Cowork works session by session. You upload documents, work, done. `perag` builds a *database* that persists across sessions and grows incrementally. You `perag ingest` a new document once; it's queryable forever. The next Claude Code session doesn't need you to re-upload anything.

---

## What are the specific use cases where I'd reach for `perag`?

### 1. A large, stable reference corpus you query repeatedly
Legal documents, technical specs, product documentation, a personal knowledge base. You ingest once, query forever. Re-uploading these every Cowork session would be tedious and impractical at scale.

### 2. You're a developer using Claude Code heavily
`perag` is specifically designed for Claude Code users who want their AI to have background knowledge about a project's own documentation — design docs, ADRs, READMEs across many repos — without stuffing the context window at the start of every session.

### 3. Privacy-sensitive documents with an offline embedding requirement
Cowork sends file content to Anthropic's cloud (the model has to see it). `perag` with the **local embedding provider** never sends your documents anywhere — not even for the vector generation step. For highly confidential material (legal, medical, financial) where you need RAG but not cloud exposure, `perag`'s local-first architecture is the point.

### 4. Reproducible, scriptable retrieval
`perag query "termination clause" --json` gives you structured, auditable output you can pipe into other tools. It's programmable retrieval. Cowork is an interactive agent; it's not designed for automation scripts or CI pipelines.

---

## Quick decision table

| Situation | Recommended tool |
|---|---|
| A few documents, one-off question | **Cowork** — simpler, no setup needed |
| Large collection (50+ docs), queried repeatedly | **`perag` + Claude Code** |
| Living project with documents that change over time | **`perag` + Claude Code** |
| Fully offline, no-cloud document search required | **`perag`** (local embeddings) |
| Non-developer, GUI preferred | **Cowork** — always |
| Scripted or automated retrieval pipelines | **`perag`** |

---

## What's the trigger to switch?

You'll know it's time for `perag` when you find yourself **re-uploading the same documents session after session** — or when your collection grows to the point where selective retrieval would give Claude better signal than drowning it in raw content.

---

## Where can I get `perag`?

- GitHub: [github.com/verhas/perag](https://github.com/verhas/perag)
- PyPI: `pip install perag` or `uv tool install perag`