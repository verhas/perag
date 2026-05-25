from pathlib import Path

from markdown_it import MarkdownIt

from chunkers.base import Chunker
from perag.schema import Chunk


class MarkdownChunker(Chunker):
    """Splits Markdown at top-level headings (h1/h2). Falls back to paragraph chunks."""

    def chunk(self, path: Path) -> list[Chunk]:
        source = str(path)
        text = path.read_text(encoding="utf-8")
        md = MarkdownIt()
        tokens = md.parse(text)

        sections: list[tuple[str | None, list[str]]] = []
        current_heading: str | None = None
        current_lines: list[str] = []

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.type == "heading_open" and tok.tag in ("h1", "h2"):
                if current_lines or current_heading is not None:
                    sections.append((current_heading, current_lines))
                    current_lines = []
                inline = tokens[i + 1] if i + 1 < len(tokens) else None
                current_heading = inline.content if inline else None
                i += 3  # heading_open, inline, heading_close
                continue
            if tok.type in ("html_block", "fence", "code_block"):
                current_lines.append(tok.content.strip())
            elif tok.type == "inline":
                current_lines.append(tok.content.strip())
            i += 1

        if current_lines or current_heading is not None:
            sections.append((current_heading, current_lines))

        chunks: list[Chunk] = []
        for heading, lines in sections:
            content_parts = [heading] if heading else []
            content_parts.extend(l for l in lines if l)
            content = "\n\n".join(content_parts).strip()
            if not content:
                continue
            chunks.append(
                Chunk(
                    id=f"{source}::chunk::{len(chunks)}",
                    source=source,
                    content=content,
                    metadata={"format": "markdown", "section": heading},
                )
            )
        return chunks
