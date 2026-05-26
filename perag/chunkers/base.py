import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

from perag.schema import Chunk


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


class Chunker(ABC):
    @abstractmethod
    def chunk(self, path: Path) -> list[Chunk]:
        """Split a document into chunks."""
