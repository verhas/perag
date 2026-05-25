# Pipeline walkthrough

## Full pipeline (piped)

```bash
perag chunk document.pdf | perag embed | perag ingest
```

## Full pipeline (with intermediate files)

```bash
perag chunk document.pdf      > chunks.json
perag embed   < chunks.json   > chunks_embedded.json
perag ingest  < chunks_embedded.json
```

## Query

```bash
perag query "what are the termination conditions?"
perag query "what are the termination conditions?" --json
```

## Initialization

```bash
cd my-project/
perag init
# Creates .perag/config.toml and adds .perag/perag.db to .gitignore
```

## Re-ingesting after provider change

If you change the embedding provider or model:

```bash
# Re-embed existing chunks.json from a previous run:
perag embed < chunks.json > chunks_new.json
perag ingest < chunks_new.json

# Or re-chunk and re-embed from scratch:
perag chunk document.pdf | perag embed | perag ingest
```

The embedder detects that chunks were embedded with a different model and re-embeds
them automatically. The ingestor replaces all chunks for each source document.
