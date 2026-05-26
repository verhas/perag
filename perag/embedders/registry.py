from perag.config import EmbeddingConfig

from perag.embedders.base import Embedder


def get_embedder(cfg: EmbeddingConfig) -> Embedder:
    match cfg.provider:
        case "local":
            from perag.embedders.local import LocalEmbedder
            return LocalEmbedder(model=cfg.model)
        case "ollama":
            from perag.embedders.ollama import OllamaEmbedder
            return OllamaEmbedder(model=cfg.model, url=cfg.url)
        case "openai":
            from perag.embedders.openai import OpenAIEmbedder
            return OpenAIEmbedder(model=cfg.model, api_key=cfg.api_key)
        case _:
            raise ValueError(f"Unknown embedding provider '{cfg.provider}'. Choose: local, ollama, openai")
