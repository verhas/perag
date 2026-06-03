import httpx

from perag.embedders.base import Embedder


class OllamaEmbedder(Embedder):
    def __init__(self, model: str = "nomic-embed-text", url: str = "http://localhost:11434") -> None:
        self._model = model
        self._url = url.rstrip("/")

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "ollama"

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Try the newer batch endpoint (Ollama >= 0.1.28)
        resp = httpx.post(
            f"{self._url}/api/embed",
            json={"model": self._model, "input": texts},
            timeout=120,
        )
        if resp.status_code != 404:
            resp.raise_for_status()
            return resp.json()["embeddings"]

        # Older Ollama: fall back to single-text endpoint
        vectors = []
        for text in texts:
            resp = httpx.post(
                f"{self._url}/api/embeddings",
                json={"model": self._model, "prompt": text},
                timeout=60,
            )
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"])
        return vectors
