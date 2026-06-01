from pathlib import Path

from perag.chunkers.base import Chunker
from perag.chunkers.docx import DocxChunker
from perag.chunkers.markdown import MarkdownChunker
from perag.chunkers.pdf import PdfChunker
from perag.chunkers.text import TextChunker

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".docx", ".doc", ".md", ".markdown", ".txt", ".text",
})

_REGISTRY: dict[str, type[Chunker]] = {
    ".pdf": PdfChunker,
    ".docx": DocxChunker,
    ".doc": DocxChunker,
    ".md": MarkdownChunker,
    ".markdown": MarkdownChunker,
    ".txt": TextChunker,
    ".text": TextChunker,
}


def get_chunker(path: Path, as_format: str | None = None) -> Chunker:
    if as_format is not None:
        key = as_format if as_format.startswith(".") else f".{as_format}"
        cls = _REGISTRY.get(key.lower())
        if cls is None:
            supported = ", ".join(sorted(_REGISTRY))
            raise ValueError(f"Unknown format '{as_format}'. Supported: {supported}")
        return cls()
    ext = path.suffix.lower()
    cls = _REGISTRY.get(ext)
    if cls is None:
        supported = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {supported}. Use --as to force a format.")
    return cls()
