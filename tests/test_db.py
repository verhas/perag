import sqlite3
import tempfile
from pathlib import Path

import pytest

from perag.schema import Chunk


def _make_chunk(i: int, source: str = "test.txt", file_hash: str = "abc123") -> Chunk:
    return Chunk(
        id=f"{source}::chunk::{i}",
        source=source,
        content=f"Content block {i}",
        metadata={"format": "text"},
        file_hash=file_hash,
        embedding_model="all-MiniLM-L6-v2",
        embedding_provider="local",
        vector=[float(i)] * 4,
    )


@pytest.fixture
def db(tmp_path):
    from perag.db.store import init_db
    return init_db(tmp_path / "test.db")


def test_ingest_and_search(db):
    from perag.db.store import ingest
    from perag.db.search import search

    chunks = [_make_chunk(i) for i in range(3)]
    ingest(db, chunks)

    results = search(db, [0.0] * 4, top_k=2)
    assert len(results) == 2
    assert all(isinstance(r, Chunk) for r in results)


def test_ingest_replaces_source(db):
    from perag.db.store import ingest
    from perag.db.search import search

    ingest(db, [_make_chunk(0), _make_chunk(1)])
    # Re-ingest same source with fewer chunks
    ingest(db, [_make_chunk(0)])

    results = search(db, [0.0] * 4, top_k=10)
    sources = [r.source for r in results]
    assert sources.count("test.txt") == 1


def test_ingest_model_mismatch_raises(db):
    from perag.db.store import ingest

    ingest(db, [_make_chunk(0)])

    bad_chunk = Chunk(
        id="test.txt::chunk::1",
        source="test.txt",
        content="Different model content",
        metadata={},
        embedding_model="other-model",
        embedding_provider="local",
        vector=[0.1] * 4,
    )
    with pytest.raises(ValueError, match="embedding model mismatch"):
        ingest(db, [bad_chunk])


def test_ingest_no_vector_raises(db):
    from perag.db.store import ingest

    bad = Chunk(id="x::chunk::0", source="x", content="no vector", metadata={})
    with pytest.raises(ValueError, match="no vectors"):
        ingest(db, [bad])


def test_ingest_records_file_hash(db):
    from perag.db.store import ingest

    ingest(db, [_make_chunk(0, file_hash="deadbeef"), _make_chunk(1, file_hash="deadbeef")])

    row = db.execute("SELECT file_hash FROM files WHERE source = 'test.txt'").fetchone()
    assert row is not None
    assert row["file_hash"] == "deadbeef"


def test_ingest_updates_file_hash_on_reingest(db):
    from perag.db.store import ingest

    ingest(db, [_make_chunk(0, file_hash="oldhash")])
    ingest(db, [_make_chunk(0, file_hash="newhash")])

    row = db.execute("SELECT file_hash FROM files WHERE source = 'test.txt'").fetchone()
    assert row["file_hash"] == "newhash"


def test_ingest_warns_on_conflicting_hashes(db):
    import warnings
    from perag.db.store import ingest

    chunks = [
        _make_chunk(0, file_hash="hash_a"),
        _make_chunk(1, file_hash="hash_b"),
    ]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ingest(db, chunks)

    assert any("Conflicting file_hash" in str(w.message) for w in caught)
