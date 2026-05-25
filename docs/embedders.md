# Embedding providers

## local (default)

Uses `sentence-transformers` — fully local, no API key or running service required.
Models are downloaded on first use and cached by sentence-transformers.

```toml
[embedding]
provider = "local"
model    = "all-MiniLM-L6-v2"   # fast, 384-dim
# model = "all-mpnet-base-v2"   # higher quality, 768-dim
```

## ollama

Calls a locally running Ollama instance.

```toml
[embedding]
provider = "ollama"
model    = "nomic-embed-text"
url      = "http://localhost:11434"
```

## openai

Calls the OpenAI embeddings API.

```toml
[embedding]
provider = "openai"
model    = "text-embedding-3-small"
api_key  = "sk-..."
```
