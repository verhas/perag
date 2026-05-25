import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    model: str = "all-MiniLM-L6-v2"
    url: str = "http://localhost:11434"
    api_key: str = ""
    batch_size: int = 32


@dataclass
class QueryConfig:
    top_k: int = 5
    output: str = "text"


@dataclass
class Config:
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    query: QueryConfig = field(default_factory=QueryConfig)


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _apply_section(defaults: dataclass, raw: dict, cls: type) -> object:
    """Replace entire section with raw values merged into defaults."""
    d = {k: getattr(defaults, k) for k in defaults.__dataclass_fields__}
    d.update(raw)
    return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def load_config() -> Config:
    """Load config using local-first lookup: ./.perag/config.toml > ~/.perag/config.toml."""
    global_raw = _load_toml(Path.home() / ".perag" / "config.toml")
    local_raw = _load_toml(Path.cwd() / ".perag" / "config.toml")

    # Section-level replace: local section fully overrides global section
    embedding_raw = local_raw.get("embedding") or global_raw.get("embedding") or {}
    query_raw = local_raw.get("query") or global_raw.get("query") or {}

    return Config(
        embedding=_apply_section(EmbeddingConfig(), embedding_raw, EmbeddingConfig),
        query=_apply_section(QueryConfig(), query_raw, QueryConfig),
    )


def find_db_path() -> Path:
    """Find the database path using local-first lookup."""
    local = Path.cwd() / ".perag" / "perag.db"
    if local.parent.exists():
        return local
    global_dir = Path.home() / ".perag"
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir / "perag.db"
