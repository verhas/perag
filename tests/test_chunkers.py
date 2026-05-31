from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def test_text_chunker_produces_chunks():
    from perag.chunkers.text import TextChunker
    chunker = TextChunker()
    chunks = chunker.chunk(FIXTURES / "sample.txt")
    assert len(chunks) >= 1
    for c in chunks:
        assert c.content
        assert c.source == str(FIXTURES / "sample.txt")
        assert c.metadata["format"] == "text"


def test_text_chunker_ids_are_unique():
    from perag.chunkers.text import TextChunker
    chunks = TextChunker().chunk(FIXTURES / "sample.txt")
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_markdown_chunker_splits_on_headings():
    from perag.chunkers.markdown import MarkdownChunker
    chunks = MarkdownChunker().chunk(FIXTURES / "sample.md")
    assert len(chunks) >= 3
    for c in chunks:
        assert c.content
        assert c.metadata["format"] == "markdown"


def test_markdown_chunker_ids_are_unique():
    from perag.chunkers.markdown import MarkdownChunker
    chunks = MarkdownChunker().chunk(FIXTURES / "sample.md")
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_registry_dispatches_by_extension():
    from perag.chunkers.registry import get_chunker
    from perag.chunkers.text import TextChunker
    from perag.chunkers.markdown import MarkdownChunker
    assert isinstance(get_chunker(Path("foo.txt")), TextChunker)
    assert isinstance(get_chunker(Path("foo.md")), MarkdownChunker)


def test_registry_raises_on_unknown_extension():
    from perag.chunkers.registry import get_chunker
    with pytest.raises(ValueError, match="Unsupported"):
        get_chunker(Path("foo.xyz"))


def test_pdf_chunker_produces_chunks():
    from perag.chunkers.pdf import PdfChunker
    chunks = PdfChunker().chunk(FIXTURES / "sample.pdf")
    assert len(chunks) >= 1
    for c in chunks:
        assert c.content
        assert c.source == str((FIXTURES / "sample.pdf").resolve())
        assert c.metadata["format"] == "pdf"
        assert "page" in c.metadata
        assert c.file_hash is not None


def test_pdf_chunker_ids_are_unique():
    from perag.chunkers.pdf import PdfChunker
    chunks = PdfChunker().chunk(FIXTURES / "sample.pdf")
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_pdf_chunker_covers_all_pages():
    from perag.chunkers.pdf import PdfChunker
    import pdfplumber
    path = FIXTURES / "sample.pdf"
    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
    chunks = PdfChunker().chunk(path)
    assert len(chunks) == total_pages


def test_pdf_chunker_warns_on_blank_pages(tmp_path, capsys):
    from perag.chunkers.pdf import PdfChunker

    # Minimal single-page PDF with no text content
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
    )
    blank_pdf = tmp_path / "blank.pdf"
    blank_pdf.write_bytes(pdf_bytes)

    chunks = PdfChunker().chunk(blank_pdf)
    assert chunks == []
    captured = capsys.readouterr()
    assert "scanned" in captured.err or "no extractable text" in captured.err


def test_docx_chunker_produces_chunks():
    from perag.chunkers.docx import DocxChunker
    chunks = DocxChunker().chunk(FIXTURES / "sample.docx")
    assert len(chunks) >= 1
    for c in chunks:
        assert c.content
        assert c.source == str((FIXTURES / "sample.docx").resolve())
        assert c.metadata["format"] == "docx"
        assert c.file_hash is not None


def test_docx_chunker_ids_are_unique():
    from perag.chunkers.docx import DocxChunker
    chunks = DocxChunker().chunk(FIXTURES / "sample.docx")
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_docx_chunker_groups_paragraphs():
    from perag.chunkers.docx import DocxChunker, _CHUNK_PARAS
    from docx import Document
    chunks = DocxChunker().chunk(FIXTURES / "sample.docx")
    # sample.docx has 21 paragraphs + 1 heading = 22 non-empty → ceil(22/_CHUNK_PARAS) chunks
    assert len(chunks) >= 2
