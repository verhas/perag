# Future: Ignore Rules
**Status:** implemented in 0.1.6

## Problem

`perag ls` and `perag status --full` scan the file system for supported document
formats. Without any exclusion logic they find files inside virtual environments,
build artefacts, caches, IDE metadata, and version control internals — none of which
are user documents. These appear as `NEW` in `perag ls` and get accidentally ingested
when the user runs:

```bash
perag chunk $(perag ls -Rn) | perag embed | perag ingest
```

## Design

Three layers of exclusion, applied in order. Each layer can be individually disabled.

### Layer 1 — Hardcoded exclusions (always on by default)

A built-in list of directories and patterns that are never user documents. Disabling
this layer requires an explicit config opt-out.

**Version control:**
```
.git/
.hg/
.svn/
.bzr/
```

**Python:**
```
.venv/
venv/
env/
ENV/
__pycache__/
*.pyc
*.pyo
*.egg-info/
.eggs/
dist/
build/
.tox/
.mypy_cache/
.pytest_cache/
.ruff_cache/
.pytype/
```

**JavaScript / Node:**
```
node_modules/
.npm/
.yarn/
dist/
.next/
.nuxt/
```

**JVM (Java, Kotlin, Scala):**
```
target/
*.class
*.jar
*.war
out/
```

**Rust:**
```
target/
```

**IDE and editors:**
```
.idea/
.vscode/
.vs/
*.iml
```

**OS artefacts:**
```
.DS_Store
Thumbs.db
desktop.ini
```

**Build and output:**
```
bin/
obj/
_site/
.cache/
```

**Docker:**
```
.docker/
```

**Ruby:**
```
.bundle/
vendor/bundle/
```

Opt-out via config:

```toml
[ls]
hardcoded_exclusions = false   # default: true
```

When disabled, no built-in patterns are applied. The user takes full responsibility
for what is scanned.

### Layer 2 — `.perag/ignore`

A project-local ignore file at `.perag/ignore`, using the same pattern syntax as
`.gitignore` (glob patterns, `#` comments, `!` negation). Committed or not at the
user's discretion. Useful for excluding documents that are tracked by git but should
not be indexed (drafts, sensitive files, large reference corpora).

Example `.perag/ignore`:

```
# Do not index draft documents
drafts/
*-draft.pdf

# Do not index raw data exports
data/raw/
```

This file is always read when present. There is no config option to disable it —
its presence is itself the opt-in.

### Layer 3 — `.gitignore` (opt-in)

When enabled, perag reads the project's `.gitignore` and applies its patterns during
file scanning. Useful because `.gitignore` already excludes build artefacts and
environment directories that overlap with Layer 1.

Controlled by config:

```toml
[ls]
use_gitignore = true   # default: false
```

And overridable per invocation:

```bash
perag ls --gitignore       # enable for this run
perag ls --no-gitignore    # disable for this run
```

The global gitignore (`~/.gitignore_global` or `~/.config/git/ignore`) is also read
when `use_gitignore = true`, following the same lookup git uses.

Implementation requires the `pathspec` library, which parses gitignore patterns
correctly including negation, anchoring, and `**` double-star matching.

---

## Ingest warning

When `perag ingest` receives a chunk whose `source` path matches any active ignore
rule, it emits a warning to stderr:

```
Warning: /path/to/file.txt matches ignore rule '.venv/' — ingesting anyway
```

This catches accidental ingestion of non-document files that bypassed `perag ls`
by being passed directly to `perag chunk`. The ingest proceeds — the warning is
advisory only.

The warning can be suppressed:

```toml
[ingest]
warn_ignored = false   # default: true
```

---

## Scope

Ignore rules apply to:

- `perag ls` — file listing and status
- `perag status --full` — disk scan counts
- `perag ingest` — warning only, does not block

Ignore rules do **not** apply to:

- `perag chunk <file>` — explicit file arguments are always respected
- `perag query` — searches the database, not the file system
- `perag prune` — operates on database entries, not disk

---

## Why not now

- The immediate problem (`.venv/` appearing in results) can be fixed with a small
  hardcoded exclusion list in the scanner without the full design above.
- `pathspec` as a dependency for `.gitignore` support needs evaluation.
- The ignore rule scope and opt-out semantics need user feedback to get right.

Implement Layer 1 (hardcoded exclusions) first as a bug fix. Layers 2 and 3 follow
when users request finer control.
