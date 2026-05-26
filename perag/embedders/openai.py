import httpx

from perag.embedders.base import Embedder

_API_URL = "https://api.openai.com/v1/embeddings"


class OpenAIEmbedder(Embedder):
    def __init__(self, model: str = "text-embedding-3-small", api_key: str = "") -> None:
        self._model = model
        self._api_key = api_key

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            _API_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "input": texts},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]
