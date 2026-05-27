# Future: Logging

## Motivation

Logging across all perag operations would aid debugging, provide an audit trail of
what was ingested and when, and surface warnings (such as permission issues or skipped
pages) that are otherwise lost after a terminal session ends.

## Log location

The log follows the same local-first lookup as the database and config:

```
./.perag/perag.log   — project-local (default)
~/.perag/perag.log   — global fallback when no local .perag/ exists
```

The location is configurable:

```toml
[log]
path = "/custom/path/perag.log"   # absolute path override
enabled = true                    # set to false to disable logging entirely
level = "warning"                 # warning | info | debug
```

## Default level

The default level is `warning`. At this level the log is small, the fast path is
unaffected, and no sensitive content is written. `info` adds operation summaries
(files ingested, chunks written, query terms). `debug` adds per-chunk and per-batch
detail and may include query text and chunk content — only enable deliberately.

## File permissions

The log file is created with `600` permissions (owner read/write only, no execute).

## Speed

Python's `logging` module writes synchronously by default. This adds latency on the
query path, which is already slow due to model loading. A `RotatingFileHandler` with
buffering mitigates this. Async logging is possible but disproportionately complex
for this tool.

## Disk consumption

A single `RotatingFileHandler` with a 5 MB cap and one backup file
(`maxBytes=5_000_000, backupCount=1`) is the simplest defensible default. This bounds
disk use to ~10 MB per project regardless of usage volume.

## Concurrency

The pipeline (`perag chunk | perag embed | perag ingest`) runs three processes
simultaneously, all potentially writing to the same log file. Python's built-in
`RotatingFileHandler` is not safe for concurrent multi-process writes. Options:

- Accept occasional garbled lines at the default warning level, where concurrent
  writes are rare
- Use `ConcurrentLogHandler` (third-party dependency) for correctness
- Write to a per-process temp file and merge on exit (complex)

For v1 the pragmatic choice is to accept the limitation and document it. Concurrent
log corruption at warning level is unlikely and non-fatal.

## Sensitive content

The log must never write chunk content or query text at the default level. Both are
potentially sensitive — contract terms, personal notes, medical records. This must be
enforced by convention in the codebase, not left to individual call sites.

## Why not now

- The user base at v0.1.x is too small to know which log levels and retention policies
  are useful in practice.
- The concurrent write problem has no clean solution without adding a dependency.

Revisit when users report difficulty diagnosing problems after the fact.
