import httpx

from embedders.base import Embedder


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
