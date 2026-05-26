from perag.embedders.base import Embedder


class LocalEmbedder(Embedder):
    """sentence-transformers embedder — fully local, no API key or service required."""

    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model
        self._model = None  # lazy load

    def _load(self):
        if self._model is None:
            import os
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
            os.environ.setdefault("HF_HUB_VERBOSITY", "error")
            os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str:
        return "local"

    def preload(self) -> None:
        self._load()

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load()
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]
