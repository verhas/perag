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
