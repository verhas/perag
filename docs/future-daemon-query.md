# Future: Persistent Embedding Daemon

## Problem

Every `perag embed` and `perag query` invocation starts a fresh Python process. For
the local embedding provider (sentence-transformers) this incurs a fixed startup cost —
Python interpreter initialisation, PyTorch import, and model weight loading — before
any embedding work is done. The model weights themselves load quickly; the overhead is
the framework infrastructure around them, which cannot be serialised to disk in an
already-initialised state.

This makes both embedding and interactive querying feel sluggish. The problem is
specific to the local provider. Ollama and OpenAI providers are unaffected — the model
already lives in a running process and perag communicates with it over HTTP.

## Proposed solution

An optional persistent daemon that keeps the local embedding model resident in memory.
Both `perag embed` and `perag query` delegate embedding work to the daemon instead of
loading the model themselves. If no daemon is running, both commands fall back to the
current in-process behaviour transparently — the daemon is purely an acceleration path,
not a requirement.

The daemon is never started or used when the embedding provider is not `local`.

The "no daemon" statement in the project non-goals was motivated by two concerns:
avoiding a network-accessible surface that could introduce security issues, and keeping
the tool simple to install and use. The embedding daemon violates neither: it
communicates exclusively over a Unix domain socket that is not reachable from the
network, and it starts and stops automatically without any service registration,
configuration, or user intervention.

## Design

### Files

All daemon artefacts live in `.perag/`, consistent with the database and config:

```
.perag/embed.sock   — Unix domain socket
.perag/embed.pid    — PID of the running daemon process
```

### Lifecycle

The client (`perag embed` or `perag query`) is responsible for starting the daemon.
The daemon is never responsible for restarting itself.

**Client side:**

1. Check for `.perag/embed.pid`. If the file exists, read the PID and call
   `os.kill(pid, 0)` to verify the process is alive without sending a signal.
2. If the process is gone, delete both `.perag/embed.pid` and `.perag/embed.sock` and
   fall back to in-process embedding for this invocation.
3. If the process is alive, connect to `.perag/embed.sock` and send the request.
4. If no daemon is running at all, start one as a background process, then proceed
   with in-process embedding for this invocation (the daemon will be available for the
   next call).

**Daemon side:**

- On startup, load the embedding model and write its PID to `.perag/embed.pid`.
- On each request, check that the `config_fingerprint` matches the one it loaded with.
  If it does not match, respond with `{"status": "error", "message": "config changed"}`
  and exit gracefully, deleting both artefact files. It is then the next client's
  responsibility to start a fresh daemon.
- Exit automatically after a configurable idle timeout (default: 5 minutes), deleting
  both artefact files on clean shutdown.
- The daemon never reloads the model, never restarts itself, and never attempts to
  recover from any detected inconsistency. Any problem it cannot serve correctly results
  in a graceful exit.

**Explicit start** (for debugging or pre-warming):

```bash
perag embed --daemon   # start the embedding daemon in the foreground
```

### Protocol

Line-delimited JSON over the Unix socket. The daemon replies in two messages to let
the client show a spinner and distinguish "processing" from "dead":

```
client → daemon:  {"texts": ["...", "..."], "config_fingerprint": "abc123"}\n
daemon → client:  {"status": "ack"}\n
daemon → client:  {"status": "ok", "vectors": [[0.021, ...], ...]}\n
```

On a detected problem, the daemon responds with an error and then exits:

```
daemon → client:  {"status": "error", "message": "config changed — restart daemon"}\n
```

The client treats any error response as a signal to fall back to in-process embedding
for the current invocation and, if it started the daemon itself, to attempt a fresh
start for subsequent invocations.

### ACK timeout

The client waits for the ACK with a configurable timeout (default: 20 seconds). There
is no timeout on the response that follows the ACK — once the daemon has acknowledged
the request, the client waits as long as needed for the embedding to complete.

If the ACK does not arrive within the timeout, the client:

1. Kills the daemon process using the PID from `.perag/embed.pid`
2. Deletes both `.perag/embed.pid` and `.perag/embed.sock`
3. Logs an error and prints a message to stderr
4. Falls back to in-process embedding for the current invocation
5. Starts a fresh daemon in the background, exactly as it would if no daemon were running

The timeout is configurable:

```toml
[embedding]
daemon_ack_timeout = 20   # seconds; set to 0 to disable the timeout
```

A hung or overloaded daemon that fails to ACK is treated the same as a crashed one —
the client does not wait indefinitely and does not attempt to send the request again.
The immediate daemon restart ensures subsequent invocations benefit from the daemon
without waiting for the next natural start opportunity.

### Config fingerprint

The request includes a `config_fingerprint` — a hash of the fields that affect
embedding behaviour: `model` and `batch_size`. Since the daemon is only ever used with
the local provider, `provider` is always `local` and there is no URL to consider. If
the fingerprint in the request does not match what the daemon loaded with, the daemon
returns an error and exits. It does not attempt to reload.

### Stale socket handling

Stale artefact files left by a crashed daemon are detected via the PID file. If
`os.kill(pid, 0)` raises `ProcessLookupError`, both files are cleaned up by the client
and it falls back gracefully. No timeout guessing is needed.

### Concurrency

If two invocations race to start the daemon, both may attempt to bind the same socket.
A lockfile (`.perag/embed.lock`) with an atomic `O_CREAT | O_EXCL` open ensures only
one wins; the other falls back to in-process embedding for that invocation.

### Configuration

A config option disables the daemon entirely, for users who do not want any background
process, prefer fully predictable behaviour, or are running in an environment where
background processes are inappropriate:

```toml
[embedding]
daemon = false   # default: true for local provider, ignored for ollama and openai
```

When `daemon = false`, the client never starts or connects to a daemon, regardless of
whether one happens to be running.

## Why not now

- The user base at v0.1.x is too small to know whether embedding latency is actually a
  pain point in practice. The startup cost is real but may be acceptable for the
  typical usage pattern (occasional queries, not tight loops).
- The fallback path must be maintained and tested regardless, so the daemon only adds
  complexity without reducing the existing code surface.
- Daemon lifecycle management (startup races, stale file cleanup, idle shutdown) adds
  meaningful complexity and new failure modes even with the deliberately simple design.

Revisit when embedding latency appears consistently in user feedback.
