import json
import sqlite3
import warnings
from pathlib import Path

import sqlite_vec

from perag.schema import Chunk


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    if not hasattr(conn, "enable_load_extension"):
        import platform
        if platform.system() == "Darwin":
            hint = (
                "Your Python was built without SQLite extension support (common with pyenv on macOS).\n"
                "Reinstall perag using Homebrew Python:\n\n"
                "  uv tool install perag --reinstall --python /opt/homebrew/bin/python3"
            )
        else:
            hint = (
                "Your Python was built without SQLite extension support.\n"
                "Try reinstalling with a different Python interpreter."
            )
        raise RuntimeError(f"perag requires SQLite extension loading.\n{hint}")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = _connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
            id       TEXT PRIMARY KEY,
            source   TEXT NOT NULL,
            content  TEXT NOT NULL,
            metadata TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS files (
            source    TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    return conn


def prune(conn: sqlite3.Connection) -> list[str]:
    """Remove all DB entries for files that no longer exist on disk.

    Returns the list of sources that were pruned.
    """
    from pathlib import Path

    records = get_file_records(conn)
    pruned = [source for source in records if not Path(source).exists()]

    for source in pruned:
        existing = conn.execute(
            "SELECT id FROM chunks WHERE source = ?", (source,)
        ).fetchall()
        for row in existing:
            conn.execute(
                "DELETE FROM chunk_vectors WHERE rowid = "
                "(SELECT rowid FROM chunks WHERE id = ?)",
                (row["id"],),
            )
        conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
        conn.execute("DELETE FROM files WHERE source = ?", (source,))

    conn.commit()
    return pruned


def get_stats(conn: sqlite3.Connection) -> dict:
    """Return summary statistics from the database."""
    file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    last_ingest = conn.execute(
        "SELECT MAX(ingested_at) FROM files"
    ).fetchone()[0]
    meta = _get_meta(conn)
    return {
        "file_count": file_count,
        "chunk_count": chunk_count,
        "last_ingest": last_ingest,
        "embedding_model": meta.get("embedding_model"),
        "embedding_provider": meta.get("embedding_provider"),
    }


def get_file_records(conn: sqlite3.Connection) -> dict[str, str]:
    """Return {source: file_hash} for all files recorded in the database."""
    rows = conn.execute("SELECT source, file_hash FROM files").fetchall()
    return {r["source"]: r["file_hash"] for r in rows}


def _get_meta(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM meta").fetchall()
    return {r["key"]: r["value"] for r in rows}


def _ensure_vec_table(conn: sqlite3.Connection, dims: int) -> None:
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors
        USING vec0(embedding FLOAT[{dims}])
    """)
    conn.commit()


def ingest(conn: sqlite3.Connection, chunks: list[Chunk]) -> None:
    if not chunks:
        return

    first = chunks[0]
    if first.vector is None:
        raise ValueError("chunks have no vectors — run `perag embed` first")

    model = first.embedding_model
    provider = first.embedding_provider
    dims = len(first.vector)

    meta = _get_meta(conn)

    if "embedding_model" not in meta:
        # First ingest — write meta and create vector table
        conn.executemany(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            [
                ("embedding_model", model),
                ("embedding_provider", provider),
                ("dims", str(dims)),
            ],
        )
        _ensure_vec_table(conn, dims)
        conn.commit()
    else:
        if meta["embedding_model"] != model:
            raise ValueError(
                f"embedding model mismatch — DB has '{meta['embedding_model']}', "
                f"chunks use '{model}'. Re-run `perag embed` or rebuild the database."
            )
        _ensure_vec_table(conn, int(meta["dims"]))

    # Resolve one hash per source, warning if chunks disagree.
    source_hashes: dict[str, str] = {}
    for chunk in chunks:
        h = chunk.file_hash
        if h is None:
            continue
        if chunk.source not in source_hashes:
            source_hashes[chunk.source] = h
        elif source_hashes[chunk.source] != h:
            warnings.warn(
                f"Conflicting file_hash values for '{chunk.source}' — "
                f"using '{source_hashes[chunk.source]}', ignoring '{h}'. "
                "The chunk pipeline may be corrupted.",
                stacklevel=2,
            )

    # Delete all existing chunks for each source in this batch (full replacement per source)
    sources = {c.source for c in chunks}
    for source in sources:
        existing = conn.execute(
            "SELECT id FROM chunks WHERE source = ?", (source,)
        ).fetchall()
        for row in existing:
            conn.execute("DELETE FROM chunk_vectors WHERE rowid = (SELECT rowid FROM chunks WHERE id = ?)", (row["id"],))
        conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
    conn.commit()

    for chunk in chunks:
        if chunk.vector is None:
            raise ValueError(f"Chunk '{chunk.id}' has no vector — run `perag embed` first")

        conn.execute(
            "INSERT INTO chunks (id, source, content, metadata) VALUES (?, ?, ?, ?)",
            (chunk.id, chunk.source, chunk.content, json.dumps(chunk.metadata)),
        )
        rowid = conn.execute("SELECT rowid FROM chunks WHERE id = ?", (chunk.id,)).fetchone()["rowid"]
        conn.execute(
            "INSERT INTO chunk_vectors (rowid, embedding) VALUES (?, ?)",
            (rowid, sqlite_vec.serialize_float32(chunk.vector)),
        )

    # Update files table with resolved hashes.
    for source, file_hash in source_hashes.items():
        conn.execute(
            "INSERT OR REPLACE INTO files (source, file_hash, ingested_at) "
            "VALUES (?, ?, datetime('now'))",
            (source, file_hash),
        )

    conn.commit()
