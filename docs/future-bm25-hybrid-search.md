# Future: Hybrid Search (BM25 + Vector)

## Problem

`perag query` uses pure vector (ANN) search — it embeds the query and finds chunks
whose embedding is closest in semantic space. This works well for paraphrased questions
and meaning-based retrieval, but fails silently for precise terminology: proper names,
article numbers, clause identifiers, product codes, or any term where exact wording
matters more than meaning.

A user asking "what does Article 7.3 say?" may get back semantically adjacent chunks
about termination clauses in general rather than the chunk that actually contains the
text "Article 7.3". The failure is invisible — the query returns something, just not
the right thing.

## Proposed solution

Add BM25 full-text search alongside vector search and merge the results before
returning to the caller. This is called hybrid retrieval.

SQLite includes a built-in full-text search extension, FTS5, which implements BM25
natively. No new dependency is required — FTS5 is part of SQLite itself and is always
available in any standard SQLite build.

## Design

### Schema addition

A new FTS5 virtual table mirrors the `chunks` table:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
USING fts5(content, content='chunks', content_rowid='rowid');
```

This is a content-backed FTS5 table — it indexes the `content` column of `chunks`
without duplicating the text. It is populated and kept in sync during `perag ingest`
and pruned during `perag prune`.

### Query flow

1. Embed the query text (existing step)
2. Run ANN search against `chunk_vectors` — retrieve top-k × 2 candidates
3. Run BM25 search against `chunks_fts` — retrieve top-k × 2 candidates
4. Merge both result sets, deduplicate by chunk id
5. Re-rank the merged set by combined score (reciprocal rank fusion is the simplest
   approach — no additional model required)
6. Return the top-k results

### Reciprocal rank fusion

Each chunk receives a score based on its rank in each result list:

```
score = 1 / (rank_bm25 + k) + 1 / (rank_vector + k)
```

where `k` is a smoothing constant (typically 60). Chunks that appear in both lists
rank highest. Chunks that appear in only one list are still included, which is the
key advantage over intersection-only approaches.

### Configuration

The hybrid mode can be enabled or disabled per project:

```toml
[query]
search = "hybrid"   # hybrid | vector | bm25
top_k  = 5
```

`vector` preserves the current behaviour exactly. `bm25` runs keyword search only
(useful for debugging). `hybrid` is the new default once the feature is implemented.

## Implementation cost

Low. The main work items are:

- Add `chunks_fts` creation to `db/store.py:init_db()`
- Populate `chunks_fts` during `db/store.py:ingest()`
- Delete from `chunks_fts` during `db/store.py:prune()` and source replacement
- Add `db/search.py:search_bm25()` alongside the existing `search()`
- Add `db/search.py:hybrid_search()` implementing reciprocal rank fusion
- Update `cli.py:query()` to dispatch based on config

No new dependencies. No schema migration needed for existing databases — FTS5 table
creation is idempotent (`CREATE VIRTUAL TABLE IF NOT EXISTS`), and databases created
before this feature will simply have no FTS index until the next ingest.

## Why not now

- The user base at v0.1.x is too small to know whether pure vector search is actually
  failing in practice. Vector search fails silently, so users may not realise they are
  missing relevant chunks.
- The signal to act is users reporting that queries return irrelevant results despite
  the answer clearly being present in their documents.

The implementation cost is low enough that it can be added quickly once the need is
confirmed. The schema and query layer changes are self-contained and do not affect the
chunk/embed pipeline.
