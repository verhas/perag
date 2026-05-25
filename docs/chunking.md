# Chunking strategies

## PDF (`chunkers/pdf.py`)

One chunk per page. Pages with fewer than 50 characters are merged into the next
page's chunk. The `page` metadata field records the page where the chunk starts.

## Word / DOCX (`chunkers/docx.py`)

Groups non-empty paragraphs into batches of 10. The `paragraph_start` metadata field
records the index of the first paragraph in the chunk.

## Markdown (`chunkers/markdown.py`)

Splits at h1 and h2 headings. Each heading and its body text become one chunk. The
`section` metadata field holds the heading text. Content before the first heading
becomes a chunk with `section: null`.

## Plain text (`chunkers/text.py`)

Paragraph-aware: splits the document on blank lines, then merges short paragraphs
until a chunk reaches ~1500 characters. The last 150 characters of each chunk are
carried over as overlap into the next chunk to preserve context at boundaries.
