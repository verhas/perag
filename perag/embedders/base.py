from abc import ABC, abstractmethod


class Embedder(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Canonical model identifier stored in chunks and meta table."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier stored in chunks and meta table."""

    @property
    def needs_preload(self) -> bool:
        """True if preload() does real work (loads model weights locally)."""
        return False

    def preload(self) -> None:
        """Pre-load model weights before embed(). No-op for API-based providers."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
