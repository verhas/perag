import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    model: str = "all-MiniLM-L6-v2"
    url: str = "http://localhost:11434"
    api_key: str = ""
    batch_size: int = 32
    daemon: bool = True
    daemon_ack_timeout: int = 20
    daemon_idle_timeout: int = 300


@dataclass
class QueryConfig:
    top_k: int = 5
    output: str = "text"


@dataclass
class LogConfig:
    enabled: bool = True
    level: str = "warning"
    path: str = ""   # empty = <perag_dir>/perag.log


@dataclass
class Config:
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    log: LogConfig = field(default_factory=LogConfig)


def find_perag_dir() -> Path:
    """Walk up from cwd to find the nearest .perag directory, then fall back to ~/.perag."""
    for directory in [Path.cwd(), *Path.cwd().parents]:
        candidate = directory / ".perag"
        if candidate.exists():
            return candidate
    global_dir = Path.home() / ".perag"
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _apply_section(defaults: Any, raw: dict, cls: type) -> Any:
    """Replace entire section with raw values merged into defaults."""
    d = {k: getattr(defaults, k) for k in defaults.__dataclass_fields__}
    d.update(raw)
    return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def load_config() -> Config:
    """Load config: nearest-ancestor .perag/config.toml overrides ~/.perag/config.toml."""
    global_raw = _load_toml(Path.home() / ".perag" / "config.toml")
    local_raw = _load_toml(find_perag_dir() / "config.toml")

    # Section-level replace: local section fully overrides global section
    embedding_raw = local_raw.get("embedding") or global_raw.get("embedding") or {}
    query_raw = local_raw.get("query") or global_raw.get("query") or {}

    log_raw = local_raw.get("log") or global_raw.get("log") or {}

    return Config(
        embedding=_apply_section(EmbeddingConfig(), embedding_raw, EmbeddingConfig),
        query=_apply_section(QueryConfig(), query_raw, QueryConfig),
        log=_apply_section(LogConfig(), log_raw, LogConfig),
    )


def find_db_path() -> Path:
    """Walk up from cwd to find the nearest .perag directory, then fall back to ~/.perag."""
    perag_dir = find_perag_dir()
    return perag_dir / "perag.db"
