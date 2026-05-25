import json
import sqlite3

import sqlite_vec

from perag.schema import Chunk


def search(conn: sqlite3.Connection, query_vector: list[float], top_k: int = 5) -> list[Chunk]:
    serialized = sqlite_vec.serialize_float32(query_vector)
    rows = conn.execute(
        """
        SELECT c.id, c.source, c.content, c.metadata
        FROM chunk_vectors v
        JOIN chunks c ON c.rowid = v.rowid
        WHERE v.embedding MATCH ?
          AND k = ?
        ORDER BY distance
        """,
        (serialized, top_k),
    ).fetchall()

    meta_row = conn.execute("SELECT value FROM meta WHERE key = 'embedding_model'").fetchone()
    model = meta_row["value"] if meta_row else None
    provider_row = conn.execute("SELECT value FROM meta WHERE key = 'embedding_provider'").fetchone()
    provider = provider_row["value"] if provider_row else None

    return [
        Chunk(
            id=row["id"],
            source=row["source"],
            content=row["content"],
            metadata=json.loads(row["metadata"]),
            embedding_model=model,
            embedding_provider=provider,
        )
        for row in rows
    ]
