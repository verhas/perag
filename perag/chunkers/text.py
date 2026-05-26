from pathlib import Path

from perag.chunkers.base import Chunker, md5
from perag.schema import Chunk

_MAX_CHARS = 1500
_OVERLAP_CHARS = 150


class TextChunker(Chunker):
    """Paragraph-aware chunker for plain text. Splits on blank lines, then merges
    short paragraphs up to _MAX_CHARS with a small overlap between chunks."""

    def chunk(self, path: Path) -> list[Chunk]:
        source = str(path.resolve())
        file_hash = md5(path)
        text = path.read_text(encoding="utf-8")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        chunks: list[Chunk] = []
        current = ""

        for para in paragraphs:
            candidate = (current + "\n\n" + para).strip() if current else para
            if len(candidate) > _MAX_CHARS and current:
                chunks.append(
                    Chunk(
                        id=f"{source}::chunk::{len(chunks)}",
                        source=source,
                        content=current,
                        metadata={"format": "text"},
                        file_hash=file_hash,
                    )
                )
                # overlap: carry last _OVERLAP_CHARS of previous chunk
                overlap = current[-_OVERLAP_CHARS:].strip()
                current = (overlap + "\n\n" + para).strip() if overlap else para
            else:
                current = candidate

        if current:
            chunks.append(
                Chunk(
                    id=f"{source}::chunk::{len(chunks)}",
                    source=source,
                    content=current,
                    metadata={"format": "text"},
                    file_hash=file_hash,
                )
            )
        return chunks
