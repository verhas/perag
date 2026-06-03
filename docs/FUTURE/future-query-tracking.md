# Future: Query Hit Tracking and Organic Memory

**Status:** planned

## Motivation

`perag` is currently a passive index. It stores documents, retrieves relevant chunks,
and forgets the interaction immediately. Every query starts from the same blank slate
regardless of how many times a document has proved useful in the past.

Human memory does not work this way. Memories that are recalled frequently are
strengthened. Memories that are never recalled fade. The pattern of *what was useful
when* is itself knowledge — knowledge that a purely static RAG system throws away.

Tracking which documents and chunks appear in query results is the minimal step that
turns `perag` from a static retrieval index into a system that knows its own usage
history. That history is the foundation for a qualitatively different kind of tool:
an organic, agentic memory system.

---

## The immediate feature: query hit tracking

Every time `perag query` returns results, record which chunks were returned, at what
rank, and when. Nothing more is needed to start.

### What gets recorded

| Field | Description |
|---|---|
| `queried_at` | ISO 8601 timestamp |
| `chunk_id` | Foreign key into `chunks` table |
| `source` | Denormalized file path (survives chunk re-ingestion) |
| `rank` | Position in result list (1 = most relevant) |
| `score` | Raw similarity score from the vector search |

The query text itself is **not stored** — it may contain sensitive content (contract
terms, personal notes, medical details). A `query_length` integer is recorded for
statistical purposes only, never the text.

### Schema

```sql
CREATE TABLE query_hits (
    id          INTEGER PRIMARY KEY,
    queried_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    chunk_id    TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    rank        INTEGER NOT NULL,
    score       REAL    NOT NULL,
    query_length INTEGER
);

CREATE INDEX query_hits_source     ON query_hits (source);
CREATE INDEX query_hits_queried_at ON query_hits (queried_at);
```

`chunk_id` is stored because a source file contains multiple chunks, and different
chunks may have very different retrieval patterns. One chunk from a document might be
consistently retrieved at rank 1 while another chunk from the same file is rarely
surfaced. Tracking at chunk level lets you identify which *parts* of a document are
actually useful, not just whether the document as a whole was ever hit. This
granularity exists in the raw tier only — during aggregation it is collapsed and
counts are tracked at the source level.

`chunk_id` is not a hard foreign key — chunks are replaced on re-ingest, and the hit
history for a source file should survive that replacement. `source` is the durable
identifier.

### Write path

The `query` command (and `perag_query` MCP tool) writes hit rows after returning
results to the user. The write is best-effort: a failure to log must never block or
slow the query response. If the database is locked or the table missing, log a warning
and continue.

Hits are only recorded when the user actually receives results — not for empty queries
or error paths.

### Retention

Retention uses a multi-resolution time series: recent history is kept at full
granularity; older history is progressively aggregated rather than discarded. No
information is ever fully lost — it becomes less precise over time.

#### Three tiers

**Tier 1 — raw hits** (full detail, recent)

Individual hit rows are kept for the last `raw_days` days. Each row records the
exact timestamp, chunk, rank, and score.

**Tier 2 — level-1 aggregates** (X-day buckets)

When raw rows age past `raw_days`, an aggregation pass groups them by source and
`period_days`-day bucket (e.g. weekly). Each bucket stores the start date of the
period and the total hit count for that source within that period. Fine-grained
timestamps and per-chunk detail are dropped; the count and the period are kept.

**Tier 3 — level-2 aggregates** (Y × X-day buckets)

When Y consecutive level-1 buckets accumulate for the same source, they are merged
into a single coarser bucket spanning Y × `period_days` days, again summing the
counts. This second aggregation can repeat recursively if a third level is ever needed,
but two levels are sufficient for most personal document collections.

#### Example with default values

```
raw_days   = 90     # keep individual hits for 90 days
period_days = 7     # roll up to weekly buckets after 90 days
merge_periods = 4   # merge every 4 weekly buckets into one 28-day bucket
```

A document accessed 5 times in the last week has 5 raw hit rows.
The same document accessed heavily a year ago appears as a handful of 28-day
buckets with summed counts — enough to know it was important then, without
storing thousands of individual rows.

#### Schema

```sql
-- Tier 1: raw individual hits (recent)
CREATE TABLE query_hits (
    id           INTEGER PRIMARY KEY,
    queried_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    chunk_id     TEXT    NOT NULL,
    source       TEXT    NOT NULL,
    rank         INTEGER NOT NULL,
    score        REAL    NOT NULL,
    query_length INTEGER
);

-- Tiers 2 and 3: aggregated buckets
-- period_days = period_days      → level-1 bucket
-- period_days = merge_periods × period_days → level-2 bucket
CREATE TABLE query_hits_agg (
    id           INTEGER PRIMARY KEY,
    source       TEXT    NOT NULL,
    period_start TEXT    NOT NULL,   -- ISO date of the first day of the bucket
    period_days  INTEGER NOT NULL,   -- width of the bucket in days
    hit_count    INTEGER NOT NULL,   -- total hits within the period
    avg_rank     REAL,               -- mean rank across all hits in the period
    avg_score    REAL                -- mean similarity score
);

CREATE INDEX query_hits_agg_source ON query_hits_agg (source, period_start);
```

#### Aggregation trigger

Aggregation runs as part of `perag prune` and optionally as a standalone
`perag hits aggregate` subcommand. It is never triggered inline on the query path.
The steps are:

1. Find all raw rows in `query_hits` older than `raw_days`.
2. Group by source and `period_days`-day window; insert into `query_hits_agg`
   with `period_days = period_days`.
3. Delete the aggregated raw rows.
4. Find all level-1 buckets where Y or more consecutive buckets exist for the same
   source; sum their `hit_count`; replace them with a single level-2 row with
   `period_days = merge_periods × period_days`.

#### Configuration

```toml
[hits]
enabled       = true
raw_days      = 90    # individual hits kept for this many days
period_days   = 7     # level-1 bucket width in days
merge_periods = 4     # number of level-1 buckets merged into one level-2 bucket
```

---

## Derived statistics

Once hit rows accumulate, straightforward queries over `query_hits` produce useful
signals.

### Access frequency

How often has each source file appeared in any query result?

```sql
SELECT source, COUNT(*) AS hit_count
FROM query_hits
GROUP BY source
ORDER BY hit_count DESC;
```

This identifies the documents the user actually finds useful — not the documents they
thought would be useful when they ingested them.

### Recency of last access

```sql
SELECT source, MAX(queried_at) AS last_hit
FROM query_hits
GROUP BY source;
```

Documents with a `last_hit` far in the past are candidates for review: are they still
relevant, or can they be archived?

### Rank quality

A document that consistently appears at rank 1–2 is a high-quality match for the
user's queries. A document that appears only at rank 8–10 (near the bottom of top-k)
contributes weakly and may not be worth the storage and retrieval noise.

```sql
SELECT source, AVG(rank) AS avg_rank, AVG(score) AS avg_score
FROM query_hits
GROUP BY source;
```

### Co-retrieval

Documents frequently retrieved in the same query session are likely topically related.
This signal can inform future chunking strategies or suggest that two document
collections should be merged or cross-linked.

---

## The five-memory vision

Query hit tracking is not just a usage dashboard. It is the first step toward `perag`
implementing the five canonical types of memory studied in cognitive science and
increasingly referenced in agentic AI system design.

### 1. Working memory

**What it is:** The small amount of information actively held in mind during a task —
what fits in the context window right now.

**Current state:** The LLM's context window is working memory. `perag query` feeds
relevant chunks into it on demand. This already works.

**Future:** Hit tracking enables *smarter* working memory loading. Instead of always
retrieving by pure vector similarity, retrieval can be weighted toward documents with
a strong access history for this class of query — preferring documents the user has
found useful before over documents that are merely similar in embedding space.

### 2. Long-term memory

**What it is:** Persistent knowledge not tied to any specific event — a stable store
of facts and documents.

**Current state:** The indexed document collection is long-term memory. Documents
survive across sessions and are retrieved on demand.

**Future:** Hit frequency data allows long-term memory to be *managed*, not just
accumulated. Documents never retrieved in a year are a signal for archival review.
Documents retrieved daily deserve higher-quality chunking or re-embedding with a
better model. Long-term memory becomes curated rather than merely accumulated.

### 3. Episodic memory

**What it is:** Memory of specific events in time — *when* something happened, not
just *what* is true.

**Current state:** None. `perag` has no concept of time except `ingested_at` in the
`files` table.

**Future:** The `query_hits` table *is* episodic memory. It records that on a specific
date, a specific document was consulted. Over time this builds a temporal map of the
user's knowledge work: which documents were heavily used during a particular project,
which were consulted once and never again, what the rhythm of the user's research
looked like over weeks and months.

Episodic memory enables questions like:
- "What was I reading about in March?"
- "Which documents did I consult before the contract negotiation?"
- "Which files haven't I looked at since I ingested them?"

These are qualitatively different from retrieval queries — they are questions about
the user's *history with their documents*, not about the documents themselves.

### 4. Semantic memory

**What it is:** General conceptual knowledge — categories, facts, relationships —
independent of specific episodes.

**Current state:** Implicit in the embedding vectors. Documents about similar topics
cluster together in the vector space, but this structure is never made explicit.

**Future:** Hit patterns reveal semantic structure that the user themselves has
validated. Documents consistently co-retrieved are semantically related *in this
user's context*, which may differ from what a general-purpose embedding model assumes.
This signal can drive:

- Automatic topic clustering based on co-retrieval graphs
- Suggested tags or categories derived from access patterns
- Detection of semantic drift: a document ingested as "relevant to project X" but
  never retrieved during project X work may have been mislabelled

Document-level metadata fields (a future `[metadata]` section per source) would store
the explicit semantic annotations that this analysis produces.

### 5. Procedural memory

**What it is:** Knowledge of *how to do things* — skills, processes, workflows —
as opposed to declarative facts.

**Current state:** Not represented. A how-to guide and a research paper are stored and
retrieved identically.

**Future:** Hit patterns can expose procedural documents. A document retrieved
repeatedly at the *start* of sessions, often as the first result, is likely a
reference document or a workflow guide — the user reaches for it habitually. Tagging
such documents as `type = procedural` changes how they are surfaced:

- Procedural documents could be pre-loaded into context at session start rather than
  retrieved on demand.
- A `perag query --procedural` flag could search only within procedural documents.
- The MCP server could expose a `perag_get_procedures` tool distinct from
  `perag_query`.

---

## From RAG to organic agentic memory

The trajectory this feature enables:

| Stage | Capability |
|---|---|
| RAG (current) | Store documents, retrieve by similarity |
| + Hit tracking | Know which documents are useful and when |
| + Frequency weighting | Prefer historically useful documents in retrieval |
| + Episodic queries | Answer questions about the user's knowledge history |
| + Semantic clustering | Discover topic structure from usage, not just embeddings |
| + Procedural tagging | Distinguish reference material from factual content |
| + Forgetting curve | Time-decay access weights; surface neglected documents |
| + Memory consolidation | Merge or link frequently co-retrieved documents |

At the far end of this trajectory, `perag` is no longer a passive retrieval tool. It
is an active memory system that reflects the user's actual intellectual life — what
they read, what they found useful, what they have forgotten, and what they habitually
reach for. This is what distinguishes organic agentic memory from a document database
with a search function.

---

## Privacy design

The query text is never stored. Only the *effect* of a query (which chunks it
surfaced) is recorded. This means:

- The hit log cannot reconstruct what the user was thinking about.
- Sensitive query terms (medical conditions, legal matters, personal relationships)
  leave no trace.
- The source file paths are stored, which are themselves potentially sensitive. Hit
  tracking is opt-in via `[hits] enabled = true` (default true) and can be disabled
  entirely.

The `query_hits` table is part of `perag.db`, which is already gitignored by `perag
init`. No additional configuration is needed to keep it local.

---

## Why not now

- **Volume needed:** The statistics are only meaningful once hundreds or thousands of
  queries have been run. At v0.1.x the user base is too small to validate which
  signals are actually useful.
- **Schema commitment:** Adding `query_hits` to the database schema is a migration
  that must be handled gracefully across versions. The migration infrastructure does
  not yet exist.
- **Retention policy UX:** Deciding how long to keep hit records, and communicating
  that clearly to users, requires more design work than the tracking itself.
- **The memory vision is long-term:** Each stage in the trajectory above is its own
  feature. Building toward organic agentic memory is a multi-version arc, not a
  single release.

Implement hit tracking as soon as there are enough active users to generate meaningful
data. The rest of the memory vision follows from there.
