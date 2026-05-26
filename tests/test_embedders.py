from unittest.mock import MagicMock, patch

import pytest

from perag.schema import Chunk


def _make_chunk(i: int = 0) -> Chunk:
    return Chunk(id=f"test::chunk::{i}", source="test.txt", content=f"Text {i}", metadata={})


def test_ollama_embedder_calls_api():
    import httpx
    from perag.embedders.ollama import OllamaEmbedder

    embedder = OllamaEmbedder(model="nomic-embed-text", url="http://localhost:11434")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(httpx, "post", return_value=mock_resp) as mock_post:
        vectors = embedder.embed(["hello world"])

    assert vectors == [[0.1, 0.2, 0.3]]
    mock_post.assert_called_once()


def test_openai_embedder_calls_api():
    import httpx
    from perag.embedders.openai import OpenAIEmbedder

    embedder = OpenAIEmbedder(model="text-embedding-3-small", api_key="sk-test")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [{"index": 0, "embedding": [0.4, 0.5, 0.6]}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch.object(httpx, "post", return_value=mock_resp) as mock_post:
        vectors = embedder.embed(["test text"])

    assert vectors == [[0.4, 0.5, 0.6]]
    mock_post.assert_called_once()


def test_embedder_registry_local(monkeypatch):
    from perag.config import EmbeddingConfig
    from perag.embedders.registry import get_embedder
    from perag.embedders.local import LocalEmbedder

    cfg = EmbeddingConfig(provider="local", model="all-MiniLM-L6-v2")
    embedder = get_embedder(cfg)
    assert isinstance(embedder, LocalEmbedder)


def test_embedder_registry_unknown():
    from perag.config import EmbeddingConfig
    from perag.embedders.registry import get_embedder

    cfg = EmbeddingConfig(provider="unknown")
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        get_embedder(cfg)
