from abc import ABC, abstractmethod
from pathlib import Path

from perag.schema import Chunk


class Chunker(ABC):
    @abstractmethod
    def chunk(self, path: Path) -> list[Chunk]:
        """Split a document into chunks."""
