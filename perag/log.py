import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_ROOT = "perag"
_configured = False


def setup() -> None:
    """Configure the perag logger. Safe to call multiple times — only runs once."""
    global _configured
    if _configured:
        return
    _configured = True

    from perag.config import find_perag_dir, load_config
    cfg = load_config()
    log_cfg = cfg.log

    logger = logging.getLogger(_ROOT)

    if not log_cfg.enabled:
        logger.addHandler(logging.NullHandler())
        return

    numeric_level = getattr(logging, log_cfg.level.upper(), logging.WARNING)
    logger.setLevel(numeric_level)

    log_path = Path(log_cfg.path) if log_cfg.path else find_perag_dir() / "perag.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Pre-create with 600 permissions before RotatingFileHandler opens it,
    # so umask cannot widen access.
    if not log_path.exists():
        fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    logger.addHandler(handler)


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{_ROOT}.{name}" if name else _ROOT)
