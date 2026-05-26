# Future: Persistent Query Daemon

## Problem

Every `perag query` invocation starts a fresh Python process. For the local embedding
provider (sentence-transformers) this incurs a fixed startup cost — Python interpreter
initialisation, PyTorch import, and model weight loading — before any embedding or
search work is done. The model weights themselves load quickly; the overhead is the
framework infrastructure around them, which cannot be serialised to disk in an already-
initialised state.

This makes interactive querying feel sluggish. The problem does not affect Ollama or
OpenAI providers in the same way (the model lives in an already-running process), but
those providers still pay per-invocation process startup and an HTTP round-trip.

## Proposed solution

An optional persistent daemon that keeps the embedding model resident in memory.
`perag query` communicates with the daemon instead of loading the model itself.
If no daemon is running, `perag query` falls back to the current in-process behaviour
transparently — the daemon is purely an acceleration path, not a requirement.

This contradicts the "no daemon" statement in the project non-goals, but only as an
opt-in feature. The default behaviour and the "no server" guarantee remain unchanged.

## Design

### Files

All daemon artefacts live in `.perag/`, consistent with the database and config:

```
.perag/perag.sock   — Unix domain socket
.perag/perag.pid    — PID of the running daemon process
```

### Lifecycle

- `perag query` checks for `.perag/perag.pid`. If the file exists, it reads the PID
  and calls `os.kill(pid, 0)` to verify the process is alive without sending a signal.
  If the process is gone, both files are deleted and the client falls back to
  in-process embedding.
- If the daemon is alive, the client connects to `.perag/perag.sock` and sends the
  request.
- The daemon starts automatically on the first query that finds no running instance,
  or explicitly via `perag query --daemon` (foreground, for debugging).
- The daemon exits automatically after a configurable idle timeout (default: 5 minutes).

### Protocol

Line-delimited JSON over the Unix socket. The daemon replies in two messages to let
the client show a spinner and distinguish "processing" from "dead":

```
client → daemon:  {"query": "...", "top_k": 5, "config_fingerprint": "abc123"}\n
daemon → client:  {"status": "ack"}\n
daemon → client:  {"status": "ok", "chunks": [...]}\n
```

On error after the ACK:

```
daemon → client:  {"status": "error", "message": "..."}\n
```

### Config changes

The request includes a `config_fingerprint` (hash of the effective embedding config).
If the fingerprint differs from the one the daemon loaded with, the daemon reloads the
model before sending the ACK. The client waits transparently — it would have paid the
same cost with an in-process load anyway.

### Stale socket handling

A stale `.perag/perag.sock` with no corresponding live process is detected via the PID
file: if `os.kill(pid, 0)` raises `ProcessLookupError`, both files are cleaned up and
the client falls back gracefully. No timeout guessing is needed.

### Concurrency

If two `perag query` calls race to start the daemon, both may attempt to bind the same
socket. A lockfile (`.perag/perag.daemon.lock`) with an atomic `O_CREAT | O_EXCL` open
ensures only one wins; the other falls back to in-process embedding for that invocation.

## Why not now

- The user base at v0.1.x is too small to know whether query latency is actually a
  pain point in practice. The local provider startup cost is real but may be acceptable
  for the typical usage pattern (occasional queries, not tight loops).
- Daemon lifecycle management (auto-start, idle shutdown, crash recovery, stale file
  cleanup, config reload) adds meaningful complexity and new failure modes.
- The fallback path must be maintained and tested regardless, so the daemon only adds
  complexity without reducing the existing code surface.

Revisit when query latency appears consistently in user feedback.
