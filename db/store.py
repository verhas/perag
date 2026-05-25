import json
import sqlite3
from pathlib import Path

import sqlite_vec

from perag.schema import Chunk


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
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
    """)
    conn.commit()
    return conn


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

    conn.commit()
