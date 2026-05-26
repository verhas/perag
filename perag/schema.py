from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    id: str
    source: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    file_hash: str | None = None
    embedding_model: str | None = None
    embedding_provider: str | None = None
    vector: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "content": self.content,
            "metadata": self.metadata,
            "file_hash": self.file_hash,
            "embedding_model": self.embedding_model,
            "embedding_provider": self.embedding_provider,
            "vector": self.vector,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Chunk":
        return cls(
            id=d["id"],
            source=d["source"],
            content=d["content"],
            metadata=d.get("metadata", {}),
            file_hash=d.get("file_hash"),
            embedding_model=d.get("embedding_model"),
            embedding_provider=d.get("embedding_provider"),
            vector=d.get("vector"),
        )
