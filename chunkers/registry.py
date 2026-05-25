from pathlib import Path

from chunkers.base import Chunker
from chunkers.docx import DocxChunker
from chunkers.markdown import MarkdownChunker
from chunkers.pdf import PdfChunker
from chunkers.text import TextChunker

_REGISTRY: dict[str, type[Chunker]] = {
    ".pdf": PdfChunker,
    ".docx": DocxChunker,
    ".doc": DocxChunker,
    ".md": MarkdownChunker,
    ".markdown": MarkdownChunker,
    ".txt": TextChunker,
    ".text": TextChunker,
}


def get_chunker(path: Path) -> Chunker:
    ext = path.suffix.lower()
    cls = _REGISTRY.get(ext)
    if cls is None:
        supported = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {supported}")
    return cls()
