"""End-to-end: chunk -> embed (local) -> ingest -> query."""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.slow
def test_full_pipeline_txt(tmp_path):
    from perag.chunkers.text import TextChunker
    from perag.embedders.local import LocalEmbedder
    from perag.db.store import init_db, ingest
    from perag.db.search import search

    chunks = TextChunker().chunk(FIXTURES / "sample.txt")
    assert chunks

    embedder = LocalEmbedder(model="all-MiniLM-L6-v2")
    texts = [c.content for c in chunks]
    vectors = embedder.embed(texts)
    for c, v in zip(chunks, vectors):
        c.embedding_model = embedder.model_name
        c.embedding_provider = embedder.provider_name
        c.vector = v

    db = init_db(tmp_path / "pipeline.db")
    ingest(db, chunks)

    query_vec = embedder.embed(["conclusion final paragraph"])[0]
    results = search(db, query_vec, top_k=2)
    assert results
    assert results[0].source == str(FIXTURES / "sample.txt")
