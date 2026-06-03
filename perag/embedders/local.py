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
            try:
                self._model = SentenceTransformer(self._model_name)
            except Exception as e:
                raise RuntimeError(
                    f"Cannot load model '{self._model_name}'.\n"
                    "The model is downloaded from HuggingFace Hub on first use (~90 MB).\n"
                    "Your network may be blocking the connection to huggingface.co.\n\n"
                    "Options:\n"
                    "  • Allow outbound HTTPS to huggingface.co and try again.\n"
                    "  • Run perag on a machine with internet access to populate the local\n"
                    "    model cache (~/.cache/huggingface/), then copy it to this machine.\n"
                    "  • Switch to an Ollama or OpenAI provider in your perag config."
                ) from e

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def needs_preload(self) -> bool:
        return True

    def is_model_cached(self) -> bool:
        """Return True if the model weights are already in the local HuggingFace cache."""
        if self._model is not None:
            return True
        try:
            from huggingface_hub import try_to_load_from_cache
            for repo_id in [f"sentence-transformers/{self._model_name}", self._model_name]:
                if try_to_load_from_cache(repo_id, "config.json") is not None:
                    return True
            return False
        except Exception:
            return True  # Can't determine; assume cached to avoid a false "downloading" message

    def preload(self) -> None:
        self._load()

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load()
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]
