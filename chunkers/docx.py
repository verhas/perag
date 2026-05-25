from pathlib import Path

from docx import Document

from chunkers.base import Chunker
from perag.schema import Chunk

_CHUNK_PARAS = 10


class DocxChunker(Chunker):
    """Groups paragraphs into chunks of ~_CHUNK_PARAS non-empty paragraphs."""

    def chunk(self, path: Path) -> list[Chunk]:
        source = str(path)
        doc = Document(path)

        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        chunks: list[Chunk] = []
        for i in range(0, len(paragraphs), _CHUNK_PARAS):
            group = paragraphs[i : i + _CHUNK_PARAS]
            content = "\n\n".join(group)
            chunks.append(
                Chunk(
                    id=f"{source}::chunk::{len(chunks)}",
                    source=source,
                    content=content,
                    metadata={"format": "docx", "paragraph_start": i},
                )
            )
        return chunks
