# FAQ: LLM Wiki vs. RAG (`perag`) — When to Use Which?

## Architecture

RAG is mechanical and lossless: the original document is preserved intact, the embedding model produces deterministic vectors, and retrieval is pure mathematics — the LLM is only involved in the final generation step. The LLM Wiki is lossy and interpretive: the LLM actively reasons at every stage — ingestion, querying, and maintenance (lint) — producing synthesized, summarized, cross-linked pages from raw source material.

## Cost Structure

RAG is cheap on the indexing side: an embedding model runs, not a full LLM. The LLM Wiki is expensive on the indexing side: every ingest and every lint pass requires full LLM inference. At query time the gap widens further — RAG retrieval is pure vector math with the LLM only generating the final answer; LLM Wiki has the agent traversing a graph, loading multiple pages, with the entire navigation consuming LLM time.

## Retrieval Quality

RAG degrades when vocabulary diverges: if the question uses different terminology than the source, cosine similarity fails. The LLM Wiki is strong here — links encode editorial judgment, not mathematical proximity. A "memory management" page can link to an "arena allocation" page even if those two terms never appeared together in the source.

## Scale

RAG scales to millions of documents without issue. The LLM Wiki, by Karpathy's own estimate, operates optimally at ~100 pages and ~400,000 words — designed for personal and role-specific knowledge bases, not enterprise document repositories.

## Source Attribution

In RAG, attribution is chunk-level and approximate. In the LLM Wiki it is exact: the agent knows which page it read — the source is a specific file and section. Where auditability is a requirement (legal, professional, compliance contexts) this is a meaningful difference.

## Nature of the Artifact

A RAG index is unreadable by humans (vectors in a database). The LLM Wiki is itself a human knowledge base: readable, searchable, git-versionable, hand-editable — the same Markdown files serve both human and machine simultaneously. There is no synchronization problem and no "which is the real source" ambiguity.

---

## When to Use Which

| Criterion | `perag` (RAG) | LLM Wiki |
|---|---|---|
| Large, raw document corpus (50+ heterogeneous docs) | ✓ | ✗ |
| Changing, growing source material | ✓ (only re-embed changed chunks) | △ (lint pass is expensive) |
| Role-specific, curated knowledge base | △ | ✓ |
| Precise, auditable source attribution | △ | ✓ |
| No infrastructure dependency | △ (local DB required) | ✓ (files only) |
| Human-readable artifact as a by-product | ✗ | ✓ |
| Fully offline, no cloud exposure | ✓ (local embeddings) | △ (LLM required for every operation) |
| Low long-term operational cost | ✓ | △ |

---

## In One Sentence

`perag` is for raw document stores where scale and lossless preservation matter; the LLM Wiki is the product of curation and interpretation, where the knowledge base itself is a deliverable — not merely a retrieval aid.