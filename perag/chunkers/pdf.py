import sys
from pathlib import Path

import pdfplumber

from perag.chunkers.base import Chunker, md5
from perag.schema import Chunk

_MIN_CHARS = 50


class PdfChunker(Chunker):
    """One chunk per page; merges pages with fewer than _MIN_CHARS into the next."""

    def chunk(self, path: Path) -> list[Chunk]:
        source = str(path.resolve())
        file_hash = md5(path)
        chunks: list[Chunk] = []
        pending_text = ""
        pending_start = 1
        blank_pages: list[int] = []

        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if not text:
                    blank_pages.append(page_num)
                    continue
                pending_text = (pending_text + "\n\n" + text).strip() if pending_text else text
                if len(pending_text) >= _MIN_CHARS:
                    idx = len(chunks)
                    chunks.append(
                        Chunk(
                            id=f"{source}::chunk::{idx}",
                            source=source,
                            content=pending_text,
                            metadata={"format": "pdf", "page": pending_start},
                            file_hash=file_hash,
                        )
                    )
                    pending_text = ""
                    pending_start = page_num + 1

        if pending_text:
            idx = len(chunks)
            chunks.append(
                Chunk(
                    id=f"{source}::chunk::{idx}",
                    source=source,
                    content=pending_text,
                    metadata={"format": "pdf", "page": pending_start},
                    file_hash=file_hash,
                )
            )

        if blank_pages:
            if len(blank_pages) == total_pages:
                print(
                    f"Warning: {path.name}: all {total_pages} pages have no extractable text — "
                    "this PDF may be a scanned image and requires OCR to index.",
                    file=sys.stderr,
                )
            else:
                pages_str = ", ".join(str(p) for p in blank_pages)
                print(
                    f"Warning: {path.name}: {len(blank_pages)} page(s) had no extractable text "
                    f"and were skipped (pages: {pages_str}). "
                    "Those pages may be scanned images and require OCR to index.",
                    file=sys.stderr,
                )

        return chunks
