# Chunk JSON Schema

This document specifies the JSON format that flows between `perag chunk`, `perag embed`,
and `perag ingest`. Third-party chunkers and embedders must conform to this schema to
be composable with the rest of the perag pipeline.

---

## Overview

The pipeline is a sequence of three Unix processes connected by pipes:

```
perag chunk <file>  |  perag embed  |  perag ingest
```

`perag chunk` takes file paths as arguments and writes a JSON array to stdout.
`perag embed` reads a JSON array from stdin and writes a JSON array to stdout.
`perag ingest` reads a JSON array from stdin and writes nothing to stdout.

The array contains one object per chunk. A third-party program may replace any stage
as long as it reads and writes the same format.

### Memory usage

Each stage holds the entire chunk array in memory. For large document collections
(thousands of files) this can exhaust available memory. The recommended approach is to
ingest files one at a time — or in small batches — using a shell loop rather than
passing all files to a single pipeline invocation:

```bash
for f in *.pdf; do
    perag chunk "$f" | perag embed | perag ingest
done
```

---

## Full schema

```json
[
  {
    "id":                 "contracts/nda_2024.pdf::chunk::7",
    "source":             "/absolute/path/to/contracts/nda_2024.pdf",
    "content":            "The agreement shall terminate upon 30 days written notice...",
    "metadata": {
      "format":           "pdf",
      "page":             3,
      "section":          "Termination"
    },
    "file_hash":          "d41d8cd98f00b204e9800998ecf8427e",
    "embedding_model":    "all-MiniLM-L6-v2",
    "embedding_provider": "local",
    "vector":             [0.021, -0.134, 0.087, "..."]
  }
]
```

---

## Field reference

| Field | Type | Required | Set by | Description |
|---|---|---|---|---|
| `id` | string | yes | chunker | Unique identifier for this chunk (see [ID format](#id-format)) |
| `source` | string | yes | chunker | Absolute path to the source file |
| `content` | string | yes | chunker | The text content of this chunk |
| `metadata` | object | yes | chunker | Format-specific metadata; may be empty (`{}`) |
| `file_hash` | string or null | no | chunker | MD5 hex digest of the whole source file |
| `embedding_model` | string or null | no | embedder | Model identifier, e.g. `"all-MiniLM-L6-v2"` |
| `embedding_provider` | string or null | no | embedder | Provider name, e.g. `"local"`, `"ollama"`, `"openai"` |
| `vector` | array of float or null | no | embedder | Embedding vector; length must match all other chunks in the database |

Fields set by the chunker are present after `perag chunk`. Fields set by the embedder
are `null` after `perag chunk` and populated after `perag embed`.

---

## ID format

```
<source>::chunk::<index>
```

- `<source>` is the absolute path to the source file (same value as the `source` field)
- `<index>` is a zero-based integer, unique within a single source file

Example: `/home/alice/docs/report.pdf::chunk::0`

IDs must be globally unique within a database. Because the source path is absolute and
the index is scoped to that source, collisions are impossible as long as two different
files do not share the same absolute path.

`perag ingest` uses the ID as the primary key. Re-ingesting the same source file
(same `source` value) replaces all previous chunks for that file regardless of ID.

---

## Source field

`source` must be an **absolute path**. Relative paths are rejected by `perag ingest`
and produce unreliable results in `perag ls` and `perag status`.

Use `str(Path(path).resolve())` in Python, or the equivalent in other languages, to
convert a user-supplied path before writing it into chunks.

---

## Metadata field

`metadata` is a free-form object. perag does not validate its contents. The built-in
chunkers populate the following keys:

| Key | Type | Set by | Description |
|---|---|---|---|
| `format` | string | all chunkers | File format: `"pdf"`, `"docx"`, `"markdown"`, `"text"` |
| `page` | integer | pdf chunker | Page number where the chunk begins (1-based) |
| `section` | string | markdown chunker | Heading text of the enclosing section, if any |

Third-party chunkers may add any keys they find useful. Keys not listed above are
passed through unchanged by `perag embed` and stored verbatim by `perag ingest`.
The query output includes the metadata as part of the result header line.

---

## File hash field

`file_hash` is the lowercase MD5 hex digest of the entire source file, computed once
per file and stamped on every chunk produced from that file. It is used by `perag ls`
and `perag status` to detect whether a file has changed since it was last ingested.

It is optional (`null` is accepted) but strongly recommended. Without it, `perag ls
--stale` cannot detect changes and will report the file as `ok`.

All chunks from the same source file must carry the same `file_hash`. If they differ,
`perag ingest` emits a warning; the outcome is unspecified.

---

## Embedding fields

After `perag chunk`, the three embedding fields are `null`:

```json
{
  "embedding_model":    null,
  "embedding_provider": null,
  "vector":             null
}
```

`perag embed` inspects `embedding_model` on each incoming chunk before deciding what
to do:

| `embedding_model` in chunk | Matches current config? | Action |
|---|---|---|
| `null` | — | Embed; populate all three fields |
| set | yes | Pass through unchanged (already embedded with this model) |
| set | no | Re-embed; overwrite all three fields |

This means a JSON file produced by a previous run can be safely re-embedded after
changing providers — stale vectors are detected and replaced automatically.

`perag ingest` enforces that all chunks in the database share the same
`embedding_model`. Mixing models in one database is a hard error.

---

## Vector field

`vector` is a JSON array of IEEE 754 double-precision floats. Its length (the embedding
dimension) must be consistent across all chunks passed to a single `perag ingest`
invocation, and must match the dimension already stored in the database if the database
has been used before.

The dimension is determined by the embedding model. Common values:

| Model | Dimension |
|---|---|
| `all-MiniLM-L6-v2` | 384 |
| `all-mpnet-base-v2` | 768 |
| `nomic-embed-text` (Ollama) | 768 |
| `text-embedding-3-small` (OpenAI) | 1536 |

---

## Validation enforced by `perag ingest`

| Condition | Result |
|---|---|
| `vector` is `null` on any chunk | Hard error: *"chunks have no vectors — run `perag embed` first"* |
| `embedding_model` does not match the database `meta` table | Hard error: *"embedding model mismatch — re-run `perag embed` or rebuild the database"* |
| Chunks from the same source carry different `file_hash` values | Warning; outcome is unspecified |
| `source` collides with an existing file in the database | All previous chunks for that source are deleted and replaced |

---

## Writing a third-party chunker

A conforming chunker reads nothing from stdin and writes a JSON array to stdout. It
must:

1. Set `id`, `source`, `content`, and `metadata` on every chunk.
2. Set `source` to the **absolute path** of the source file.
3. Set `file_hash` to the MD5 hex digest of the source file (strongly recommended).
4. Set `embedding_model`, `embedding_provider`, and `vector` to `null`.
5. Write a single JSON array (not newline-delimited JSON) to stdout.
6. Write any warnings or progress information to stderr.

Minimal Python example:

```python
import hashlib, json, sys
from pathlib import Path

def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()

path = Path(sys.argv[1]).resolve()
source = str(path)
file_hash = md5(path)
text = path.read_text()

# Simple: one chunk per file
chunks = [{
    "id": f"{source}::chunk::0",
    "source": source,
    "content": text,
    "metadata": {"format": "custom"},
    "file_hash": file_hash,
    "embedding_model": None,
    "embedding_provider": None,
    "vector": None,
}]

json.dump(chunks, sys.stdout)
```

Pipe it into the rest of the pipeline:

```bash
python my_chunker.py document.xyz | perag embed | perag ingest
```

---

## Writing a third-party embedder

A conforming embedder reads a JSON array from stdin and writes a JSON array to stdout
with `embedding_model`, `embedding_provider`, and `vector` populated on every chunk.
It must:

1. Decode the input array.
2. For each chunk where `embedding_model` is `null` (or does not match the provider's
   model), compute the embedding and set all three fields.
3. Pass through chunks that already carry a matching `embedding_model` unchanged.
4. Write a single JSON array to stdout.
5. Write any warnings or progress information to stderr.

Minimal Python example:

```python
import json, sys

MODEL = "my-custom-model"
PROVIDER = "custom"

chunks = json.load(sys.stdin)

for chunk in chunks:
    if chunk.get("embedding_model") == MODEL:
        continue  # already embedded with this model
    text = chunk["content"]
    chunk["vector"] = embed(text)         # your embedding function
    chunk["embedding_model"] = MODEL
    chunk["embedding_provider"] = PROVIDER

json.dump(chunks, sys.stdout)
```

Pipe it between `perag chunk` and `perag ingest`:

```bash
perag chunk document.pdf | python my_embedder.py | perag ingest
```
