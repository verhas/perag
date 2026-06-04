import json
import sys
from enum import Enum
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console


class ChunkFormat(str, Enum):
    txt = "txt"
    text = "text"
    md = "md"
    markdown = "markdown"
    pdf = "pdf"
    docx = "docx"
    doc = "doc"

from perag.config import find_db_path, load_config
from perag.log import get_logger, setup as _setup_logging
from perag.schema import Chunk

_log = get_logger("cli")

_VERSION = _pkg_version("perag")

app = typer.Typer(
    help=f"perag — personal RAG toolkit  (version {_VERSION})",
    context_settings={"help_option_names": ["-h", "--help"]},
)
err = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        print(f"perag {_VERSION}")
        raise typer.Exit()


@app.callback()
def _main(
    _: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    _setup_logging()


@app.command()
def chunk(
    files: Annotated[list[Path], typer.Argument(help="Documents to chunk")],
    as_format: Annotated[ChunkFormat | None, typer.Option("--as", help="Treat all files as this format")] = None,
) -> None:
    """Chunk one or more documents and write JSON to stdout."""
    from perag.chunkers.registry import get_chunker

    all_chunks = []
    failed = False
    for file in files:
        if not file.exists():
            err.print(f"[red]Error:[/red] file not found: {file}")
            _log.warning("chunk: file not found: %s", file)
            failed = True
            continue
        try:
            chunks = get_chunker(file, as_format=as_format.value if as_format else None).chunk(file)
            all_chunks.extend(chunks)
            _log.info("chunk: %s → %d chunk(s)", file.resolve(), len(chunks))
        except ValueError as e:
            err.print(f"[red]Error:[/red] {e}")
            _log.warning("chunk: %s — %s", file, e)
            failed = True

    _log.info("chunk: total %d chunk(s) from %d file(s)", len(all_chunks), len(files))
    print(json.dumps([c.to_dict() for c in all_chunks], ensure_ascii=False))
    if failed:
        raise typer.Exit(1)


@app.command()
def embed(
    daemon_mode: Annotated[bool, typer.Option("--daemon", help="Start the embedding daemon in the foreground and exit")] = False,
) -> None:
    """Read chunks from stdin, add embeddings, write JSON to stdout."""
    cfg = load_config()

    if daemon_mode:
        if cfg.embedding.provider != "local":
            err.print("[red]Error:[/red] --daemon is only supported for the local embedding provider")
            raise typer.Exit(1)
        from perag.config import find_perag_dir
        from perag.embed_daemon import serve
        perag_dir = find_perag_dir()
        err.print(f"[green]Starting[/green] embedding daemon in {perag_dir}")
        serve(perag_dir, cfg.embedding.model, cfg.embedding.batch_size, cfg.embedding.daemon_idle_timeout)
        return

    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        err.print(f"[red]Error:[/red] invalid JSON on stdin: {e}")
        raise typer.Exit(1)

    chunks = [Chunk.from_dict(d) for d in raw]
    if not chunks:
        print("[]")
        return

    _log.info("embed: %d chunk(s) received from stdin", len(chunks))
    n_embedded, n_passthrough = _embed_chunks(chunks, cfg)
    _log.info("embed: %d chunk(s) written to stdout", len(chunks))
    if n_passthrough:
        err.print(f"[dim]Embedded {n_embedded} chunk(s); {n_passthrough} already embedded (passed through).[/dim]")
    else:
        err.print(f"[dim]Embedded {n_embedded} chunk(s).[/dim]")
    print(json.dumps([c.to_dict() for c in chunks], ensure_ascii=False))


@app.command()
def ingest() -> None:
    """Read embedded chunks from stdin and store them in the database."""
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        err.print(f"[red]Error:[/red] invalid JSON on stdin: {e}")
        raise typer.Exit(1)

    chunks = [Chunk.from_dict(d) for d in raw]
    if not chunks:
        err.print("[yellow]Warning:[/yellow] no chunks to ingest")
        _log.warning("ingest: no chunks received on stdin")
        return

    cfg = load_config()
    if cfg.ingest.warn_ignored:
        from perag.ignore import IgnoreChecker
        from perag.config import find_perag_dir as _find_perag_dir
        ignore = IgnoreChecker(_find_perag_dir(), cfg)
        warned: set[str] = set()
        for c in chunks:
            if c.source not in warned:
                rule = ignore.matching_rule(Path(c.source))
                if rule:
                    err.print(
                        f"[yellow]Warning:[/yellow] {c.source} matches ignore rule "
                        f"'{rule}' — ingesting anyway"
                    )
                    _log.warning("ingest: %s matches ignore rule '%s'", c.source, rule)
                    warned.add(c.source)

    from perag.db.store import init_db, ingest as db_ingest
    db_path = find_db_path()
    try:
        conn = init_db(db_path)
    except RuntimeError as e:
        err.print(f"[red]Error:[/red] {e}")
        _log.warning("ingest: db init failed: %s", e)
        raise typer.Exit(1)
    try:
        db_ingest(conn, chunks)
    except ValueError as e:
        err.print(f"[red]Error:[/red] {e}")
        _log.warning("ingest: %s", e)
        raise typer.Exit(1)
    finally:
        conn.close()

    sources = {c.source for c in chunks}
    _log.info("ingest: %d chunk(s) for %d file(s) → %s", len(chunks), len(sources), db_path)
    err.print(f"[green]Ingested[/green] {len(chunks)} chunks into {db_path}")


def _embed_chunks(chunks: list[Chunk], cfg) -> tuple[int, int]:
    """Embed chunks in-place, using the daemon when available.

    Returns (n_embedded, n_passthrough).
    Raises typer.Exit(1) on model load or network failure.
    """
    from perag.embedders.registry import get_embedder
    from perag.spinner import spinner

    embedder = get_embedder(cfg.embedding)
    to_embed_idx = [
        i for i, c in enumerate(chunks)
        if c.embedding_model is None or c.embedding_model != embedder.model_name
    ]
    if not to_embed_idx:
        return 0, len(chunks)

    texts = [chunks[i].content for i in to_embed_idx]
    batch_size = cfg.embedding.batch_size
    all_vectors: list[list[float]] = []

    use_daemon = cfg.embedding.provider == "local" and cfg.embedding.daemon
    if use_daemon:
        from perag.config import find_perag_dir
        from perag.daemon_client import try_embed
        perag_dir = find_perag_dir()
        _log.info("embed: requesting %d vector(s) from daemon (model=%s)", len(texts), cfg.embedding.model)
        with spinner("Embedding via daemon"):
            all_vectors = try_embed(
                perag_dir, cfg.embedding.model, batch_size,
                cfg.embedding.daemon_ack_timeout, cfg.embedding.daemon_idle_timeout,
                texts, err.print,
            ) or []

    if len(all_vectors) != len(texts):
        all_vectors = []
        _log.info("embed: loading model %s for in-process embedding", cfg.embedding.model)
        if embedder.needs_preload:
            cached = not (hasattr(embedder, "is_model_cached") and not embedder.is_model_cached())
            msg = (
                f"Loading model {cfg.embedding.model}"
                if cached
                else f"Downloading model {cfg.embedding.model} (~90 MB, first use only)"
            )
            try:
                with spinner(msg):
                    embedder.preload()
            except RuntimeError as e:
                err.print(f"[red]Error:[/red] {e}")
                _log.error("embed: model load failed: %s", e)
                raise typer.Exit(1)
        n_batches = (len(texts) + batch_size - 1) // batch_size
        try:
            for batch_num, i in enumerate(range(0, len(texts), batch_size), start=1):
                _log.debug("embed: batch %d/%d (%d texts)", batch_num, n_batches, len(texts[i : i + batch_size]))
                with spinner(f"Embedding {batch_num}/{n_batches}"):
                    all_vectors.extend(embedder.embed(texts[i : i + batch_size]))
        except RuntimeError as e:
            err.print(f"[red]Error:[/red] {e}")
            _log.error("embed: embedding failed: %s", e)
            raise typer.Exit(1)

    for list_idx, chunk_idx in enumerate(to_embed_idx):
        chunks[chunk_idx].embedding_model = embedder.model_name
        chunks[chunk_idx].embedding_provider = embedder.provider_name
        chunks[chunk_idx].vector = all_vectors[list_idx]

    return len(to_embed_idx), len(chunks) - len(to_embed_idx)


@app.command(name="add")
def add_cmd(
    files: Annotated[list[Path], typer.Argument(help="Documents to chunk, embed, and ingest")],
    as_format: Annotated[ChunkFormat | None, typer.Option("--as", help="Treat all files as this format")] = None,
) -> None:
    """Chunk, embed, and ingest one or more documents in a single step."""
    from perag.chunkers.registry import get_chunker
    from perag.db.store import init_db, ingest as db_ingest

    cfg = load_config()

    all_chunks: list[Chunk] = []
    failed = False
    for file in files:
        if not file.exists():
            err.print(f"[red]Error:[/red] file not found: {file}")
            _log.warning("add: file not found: %s", file)
            failed = True
            continue
        try:
            chunks = get_chunker(file, as_format=as_format.value if as_format else None).chunk(file)
            all_chunks.extend(chunks)
            _log.info("add: %s → %d chunk(s)", file.resolve(), len(chunks))
        except ValueError as e:
            err.print(f"[red]Error:[/red] {e}")
            _log.warning("add: %s — %s", file, e)
            failed = True

    if not all_chunks:
        if failed:
            raise typer.Exit(1)
        err.print("[yellow]Warning:[/yellow] no chunks produced")
        _log.warning("add: no chunks produced from %d file(s)", len(files))
        return

    _embed_chunks(all_chunks, cfg)

    db_path = find_db_path()
    try:
        conn = init_db(db_path)
    except RuntimeError as e:
        err.print(f"[red]Error:[/red] {e}")
        _log.warning("add: db init failed: %s", e)
        raise typer.Exit(1)
    try:
        db_ingest(conn, all_chunks)
    except ValueError as e:
        err.print(f"[red]Error:[/red] {e}")
        _log.warning("add: %s", e)
        raise typer.Exit(1)
    finally:
        conn.close()

    n_ok = len(files) - (1 if failed else 0)
    _log.info("add: %d file(s), %d chunk(s) → %s", n_ok, len(all_chunks), db_path)
    err.print(f"[green]Added[/green] {n_ok} file(s), {len(all_chunks)} chunks → {db_path}")
    if failed:
        raise typer.Exit(1)


@app.command(name="init")
def init_cmd(
    reinstall_skill: Annotated[bool, typer.Option("--reinstall-skill", help="Overwrite an existing Claude Code skill file")] = False,
) -> None:
    """Initialize a .perag/ directory in the current working directory."""
    import importlib.resources
    import shutil

    perag_dir = Path.cwd() / ".perag"
    config_path = perag_dir / "config.toml"

    perag_dir.mkdir(exist_ok=True)

    if config_path.exists():
        err.print(f"[yellow]Already exists:[/yellow] {config_path} — not overwritten")
    else:
        global_config = Path.home() / ".perag" / "config.toml"
        if global_config.exists():
            config_path.write_text(
                "# Project-local overrides — inherits from ~/.perag/config.toml\n"
                "# Uncomment and change only what differs:\n\n"
                "# [embedding]\n"
                "# model = \"all-MiniLM-L6-v2\"\n"
            )
        else:
            example_src = importlib.resources.files("perag.data").joinpath("config.example.toml")
            with importlib.resources.as_file(example_src) as example:
                shutil.copy(example, config_path)
        err.print(f"[green]Created[/green] {config_path}")

    gitignore = Path.cwd() / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        entry = ".perag/perag.db"
        if entry not in content:
            with open(gitignore, "a") as f:
                f.write(f"\n{entry}\n")
            err.print(f"[green]Added[/green] '{entry}' to .gitignore")

    skills_dir = Path.home() / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_dest = skills_dir / "perag.md"
    if skill_dest.exists() and not reinstall_skill:
        err.print(f"[yellow]Already exists:[/yellow] {skill_dest} — use --reinstall-skill to overwrite")
        _log.info("init: skill already installed at %s", skill_dest)
    else:
        skill_src = importlib.resources.files("perag.data").joinpath("SKILL.md")
        with importlib.resources.as_file(skill_src) as src:
            shutil.copy(src, skill_dest)
        err.print(f"[green]Installed[/green] Claude Code skill → {skill_dest}")
        _log.info("init: skill installed → %s", skill_dest)

    err.print(f"[green]Done.[/green] Database will be created at {perag_dir / 'perag.db'} on first ingest.")
    _log.info("init: complete, perag_dir=%s", perag_dir)


@app.command()
def config() -> None:
    """Show the active configuration."""
    from rich.table import Table
    from rich.console import Console as RichConsole

    cfg = load_config()
    db_path = find_db_path()

    from perag.config import find_perag_dir
    global_cfg_path = Path.home() / ".perag" / "config.toml"
    local_cfg_path = find_perag_dir() / "config.toml"

    out = RichConsole()

    # Config file sources
    out.print("[bold]Config files[/bold]")
    for label, path in [("global", global_cfg_path), ("local", local_cfg_path)]:
        if path.exists():
            out.print(f"  [green]✓[/green] {label}: {path}")
        else:
            out.print(f"  [dim]–[/dim] {label}: {path} [dim](not found)[/dim]")

    # Effective settings
    out.print("\n[bold]Effective settings[/bold]")
    table = Table(show_header=False, box=None, pad_edge=False, show_edge=False)
    table.add_column(style="dim", width=20)
    table.add_column()

    table.add_row("embedding.provider", cfg.embedding.provider)
    table.add_row("embedding.model", cfg.embedding.model)
    if cfg.embedding.provider == "ollama":
        table.add_row("embedding.url", cfg.embedding.url)
    if cfg.embedding.provider == "openai":
        table.add_row("embedding.api_key", "***" if cfg.embedding.api_key else "[red]not set[/red]")
    table.add_row("embedding.batch_size", str(cfg.embedding.batch_size))
    table.add_row("query.top_k", str(cfg.query.top_k))
    table.add_row("query.output", cfg.query.output)
    table.add_row("database", str(db_path))
    table.add_row("log.enabled", str(cfg.log.enabled))
    table.add_row("log.level", cfg.log.level)
    from perag.config import find_perag_dir as _find_perag_dir
    log_path = cfg.log.path or str(_find_perag_dir() / "perag.log")
    table.add_row("log.path", log_path)

    out.print(table)


@app.command()
def status(
    full: Annotated[bool, typer.Option("--full", help="Include file system scan for stale/new/missing counts")] = False,
    recurse: Annotated[bool, typer.Option("--recurse", "-R", help="Recurse into directories (with --full)")] = False,
) -> None:
    """Show database statistics and health summary."""
    from rich.console import Console as RichConsole
    from rich.table import Table
    from perag.db.store import get_stats, get_file_records, init_db

    cfg = load_config()
    out = RichConsole()
    db_path = find_db_path()

    if not db_path.exists():
        out.print("[yellow]No database found.[/yellow] Run [bold]perag ingest[/bold] first.")
        return

    try:
        conn = init_db(db_path)
    except RuntimeError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        stats = get_stats(conn)
        file_records = get_file_records(conn) if full else {}
    finally:
        conn.close()

    db_size = db_path.stat().st_size
    db_size_str = (
        f"{db_size / 1_048_576:.1f} MB" if db_size >= 1_048_576
        else f"{db_size / 1024:.1f} KB"
    )

    out.print("[bold]Database[/bold]")
    table = Table(show_header=False, box=None, pad_edge=False, show_edge=False)
    table.add_column(style="dim", width=22)
    table.add_column()
    table.add_row("location", str(db_path))
    table.add_row("size", db_size_str)
    table.add_row("embedding model", stats["embedding_model"] or "[dim]none[/dim]")
    table.add_row("embedding provider", stats["embedding_provider"] or "[dim]none[/dim]")
    table.add_row("files tracked", str(stats["file_count"]))
    table.add_row("chunks", str(stats["chunk_count"]))
    table.add_row("last ingest", stats["last_ingest"] or "[dim]never[/dim]")
    out.print(table)

    if not full:
        out.print("\n[dim]Run [bold]perag status --full[/bold] for file system counts.[/dim]")
        return

    # Disk scan
    from perag.chunkers.base import md5
    from perag.chunkers.registry import SUPPORTED_EXTENSIONS
    from perag.ignore import IgnoreChecker
    from perag.config import find_perag_dir as _find_perag_dir

    ignore = IgnoreChecker(_find_perag_dir(), cfg)
    glob = "**/*" if recurse else "*"
    disk_files = {
        str(f.resolve())
        for f in Path.cwd().glob(glob)
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS and not ignore.is_ignored(f.resolve())
    }

    n_ok = n_stale = n_new = n_missing = 0
    for path_str in disk_files:
        if path_str in file_records:
            if md5(Path(path_str)) == file_records[path_str]:
                n_ok += 1
            else:
                n_stale += 1
        else:
            n_new += 1
    for source in file_records:
        if not Path(source).exists():
            n_missing += 1

    out.print("\n[bold]File system[/bold]")
    fs_table = Table(show_header=False, box=None, pad_edge=False, show_edge=False)
    fs_table.add_column(style="dim", width=22)
    fs_table.add_column()
    fs_table.add_row("[green]ok[/green]",      f"[green]{n_ok}[/green]")
    fs_table.add_row("[yellow]stale[/yellow]",  f"[yellow]{n_stale}[/yellow]")
    fs_table.add_row("[red]missing[/red]",      f"[red]{n_missing}[/red]")
    fs_table.add_row("[cyan]new[/cyan]",        f"[cyan]{n_new}[/cyan]")
    out.print(fs_table)
    if not recurse:
        out.print("[dim](subdirectories not scanned — use --recurse / -R to include them)[/dim]")


@app.command()
def prune() -> None:
    """Remove database entries for files that no longer exist on disk."""
    from perag.db.store import init_db, prune as db_prune

    db_path = find_db_path()
    if not db_path.exists():
        err.print("[yellow]No database found — nothing to prune.[/yellow]")
        return

    try:
        conn = init_db(db_path)
    except RuntimeError as e:
        err.print(f"[red]Error:[/red] {e}")
        _log.warning("prune: db init failed: %s", e)
        raise typer.Exit(1)

    try:
        pruned = db_prune(conn)
    finally:
        conn.close()

    if not pruned:
        err.print("[dim]Nothing to prune — all files accounted for.[/dim]")
        return

    for source in pruned:
        err.print(f"[red]Pruned[/red] {source}")
        _log.warning("prune: removed missing file: %s", source)
    _log.info("prune: removed %d file(s) from %s", len(pruned), db_path)
    err.print(f"\n[green]Done.[/green] Removed {len(pruned)} file(s) from the database.")


@app.command(name="rm")
def rm_cmd(
    paths: Annotated[list[str], typer.Argument(help="Files to remove from the database")],
) -> None:
    """Remove one or more files from the database."""
    from perag.db.store import init_db, get_file_records, remove_source

    db_path = find_db_path()
    if not db_path.exists():
        err.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(1)

    try:
        conn = init_db(db_path)
    except RuntimeError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        file_records = get_file_records(conn)
        sources = list(file_records.keys())
        failed = False

        for path_arg in paths:
            p = Path(path_arg)

            if p.exists():
                # File is on disk — resolve to absolute path for an exact match.
                source = str(p.resolve())
                if source not in file_records:
                    err.print(f"[red]Error:[/red] '{path_arg}' is not in the database")
                    _log.warning("rm: '%s' not found in database", path_arg)
                    failed = True
                    continue
            else:
                # File gone from disk — match by path suffix against stored sources.
                p_parts = p.parts
                matches = [s for s in sources if Path(s).parts[-len(p_parts):] == p_parts]
                if not matches:
                    err.print(f"[red]Error:[/red] no database entry matching '{path_arg}'")
                    _log.warning("rm: no match for '%s'", path_arg)
                    failed = True
                    continue
                if len(matches) > 1:
                    err.print(f"[red]Error:[/red] '{path_arg}' is ambiguous — be more specific:")
                    for m in matches:
                        err.print(f"  {m}")
                    _log.warning("rm: ambiguous match for '%s': %s", path_arg, matches)
                    failed = True
                    continue
                source = matches[0]
                if Path(source).exists():
                    err.print(
                        f"[yellow]Warning:[/yellow] '{source}' still exists on disk — "
                        "it will appear as NEW on the next scan."
                    )
                    _log.warning("rm: '%s' removed from DB but file still exists on disk", source)

            n = remove_source(conn, source)
            _log.info("rm: %s (%d chunk(s))", source, n)
            err.print(f"[green]Removed[/green] {source} ({n} chunk(s))")
    finally:
        conn.close()

    if failed:
        raise typer.Exit(1)


@app.command()
def update(
    recurse: Annotated[bool, typer.Option("--recurse", "-R", help="Recurse into subdirectories when scanning for stale files")] = False,
) -> None:
    """Prune deleted files and re-ingest stale documents."""
    from perag.chunkers.base import md5
    from perag.chunkers.registry import SUPPORTED_EXTENSIONS, get_chunker
    from perag.db.store import init_db, prune as db_prune, get_file_records, ingest as db_ingest

    db_path = find_db_path()
    if not db_path.exists():
        err.print("[yellow]No database found — nothing to update.[/yellow]")
        return

    cfg = load_config()

    try:
        conn = init_db(db_path)
    except RuntimeError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        pruned = db_prune(conn)
        file_records = get_file_records(conn)
    finally:
        conn.close()

    for source in pruned:
        err.print(f"[red]Pruned[/red] {source}")
        _log.warning("update: pruned missing file: %s", source)
    if pruned:
        _log.info("update: pruned %d missing file(s)", len(pruned))
        err.print(f"Removed {len(pruned)} missing file(s) from the database.")

    from perag.ignore import IgnoreChecker
    from perag.config import find_perag_dir as _find_perag_dir
    ignore = IgnoreChecker(_find_perag_dir(), cfg)

    glob = "**/*" if recurse else "*"
    stale: list[Path] = [
        f for f in sorted(Path.cwd().glob(glob))
        if f.is_file()
        and f.suffix.lower() in SUPPORTED_EXTENSIONS
        and not ignore.is_ignored(f.resolve())
        and str(f.resolve()) in file_records
        and md5(f) != file_records[str(f.resolve())]
    ]

    if not stale:
        err.print("[dim]No stale files — collection is up to date.[/dim]")
        return

    all_chunks: list[Chunk] = []
    failed = False
    for file in stale:
        err.print(f"[yellow]Re-ingesting[/yellow] {file}")
        _log.info("update: re-ingesting %s", file.resolve())
        try:
            all_chunks.extend(get_chunker(file).chunk(file))
        except ValueError as e:
            err.print(f"[red]Error:[/red] {e}")
            _log.warning("update: %s — %s", file, e)
            failed = True

    if not all_chunks:
        if failed:
            raise typer.Exit(1)
        return

    _embed_chunks(all_chunks, cfg)

    try:
        conn = init_db(db_path)
        db_ingest(conn, all_chunks)
    except (RuntimeError, ValueError) as e:
        err.print(f"[red]Error:[/red] {e}")
        _log.warning("update: db error: %s", e)
        raise typer.Exit(1)
    finally:
        conn.close()

    _log.info("update: %d file(s), %d chunk(s) → %s", len(stale), len(all_chunks), db_path)
    err.print(f"[green]Updated[/green] {len(stale)} file(s), {len(all_chunks)} chunks → {db_path}")
    if failed:
        raise typer.Exit(1)


@app.command(name="ls")
def ls_cmd(
    paths: Annotated[list[Path] | None, typer.Argument(help="Files or directories to scan (default: current directory)")] = None,
    new: Annotated[bool, typer.Option("--new", "-n", help="Show files not yet in the database")] = False,
    stale: Annotated[bool, typer.Option("--stale", "-s", help="Show files modified since last ingest")] = False,
    ok: Annotated[bool, typer.Option("--ok", "-o", help="Show files that are up to date")] = False,
    missing: Annotated[bool, typer.Option("--missing", "-m", help="Show database entries whose file no longer exists")] = False,
    recurse: Annotated[bool, typer.Option("--recurse", "-R", help="Recurse into directories")] = False,
    gitignore: Annotated[bool | None, typer.Option("--gitignore/--no-gitignore", help="Apply .gitignore rules (overrides config)")] = None,
) -> None:
    """List files and their status relative to the database."""
    from perag.chunkers.base import md5
    from perag.chunkers.registry import SUPPORTED_EXTENSIONS
    from perag.db.store import get_file_records, init_db
    from perag.ignore import IgnoreChecker

    # No flags → show everything
    any_flag = new or stale or ok or missing
    show_new     = new     or not any_flag
    show_stale   = stale   or not any_flag
    show_ok      = ok      or not any_flag
    show_missing = missing or not any_flag

    cfg = load_config()
    from perag.config import find_perag_dir as _find_perag_dir
    ignore = IgnoreChecker(_find_perag_dir(), cfg, use_gitignore=gitignore)

    # Load DB records
    db_path = find_db_path()
    file_records: dict[str, str] = {}
    if db_path.exists():
        try:
            conn = init_db(db_path)
            file_records = get_file_records(conn)
            conn.close()
        except RuntimeError as e:
            err.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    # Collect files from disk
    scan_paths = paths or [Path.cwd()]
    disk_files: list[str] = []
    for path in scan_paths:
        if path.is_file():
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                disk_files.append(str(path))
        elif path.is_dir():
            glob = "**/*" if recurse else "*"
            for f in sorted(path.glob(glob)):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS and not ignore.is_ignored(f.resolve()):
                    disk_files.append(str(f))
        else:
            err.print(f"[yellow]Warning:[/yellow] path not found: {path}")

    # Classify disk files
    results: list[tuple[str, str]] = []  # (status, path)
    for path_str in disk_files:
        if path_str in file_records:
            current_hash = md5(Path(path_str))
            if current_hash == file_records[path_str]:
                if show_ok:
                    results.append(("OK", path_str))
            else:
                if show_stale:
                    results.append(("STALE", path_str))
        else:
            if show_new:
                results.append(("NEW", path_str))

    # Missing: DB records not found on disk (not limited to scanned dirs)
    if show_missing:
        disk_set = set(disk_files)
        for source in sorted(file_records):
            if not Path(source).exists():
                results.append(("MISSING", source))

    if sys.stdout.isatty():
        _ls_tty(results, db_entries=len(file_records), recurse=recurse)
    else:
        _ls_pipe(results)


_STATUS_STYLE = {
    "NEW":     "green",
    "STALE":   "yellow",
    "OK":      "dim",
    "MISSING": "red",
}


def _ls_tty(results: list[tuple[str, str]], db_entries: int = 0, recurse: bool = False) -> None:
    from rich.console import Console as RichConsole
    from rich.table import Table

    out = RichConsole()
    if not results:
        msg = "[dim]No matching files.[/dim]"
        if db_entries:
            msg += f" [dim](database has {db_entries} file(s) — try a different path or -R)[/dim]"
        out.print(msg)
        if not recurse:
            out.print("[dim](subdirectories not scanned — use -R to include them)[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False, show_edge=False)
    table.add_column("Status", width=9)
    table.add_column("Path")
    for status, path in results:
        style = _STATUS_STYLE[status]
        table.add_row(f"[{style}]{status}[/{style}]", path)

    out.print(table)
    counts: dict[str, int] = {}
    for status, _ in results:
        counts[status] = counts.get(status, 0) + 1
    summary = "  ".join(
        f"[{_STATUS_STYLE[s]}]{counts[s]} {s.lower()}[/{_STATUS_STYLE[s]}]"
        for s in ("NEW", "STALE", "OK", "MISSING")
        if s in counts
    )
    out.print(f"\n{summary}")
    if not recurse:
        out.print("[dim](subdirectories not scanned — use -R to include them)[/dim]")


def _ls_pipe(results: list[tuple[str, str]]) -> None:
    for status, path in results:
        print(path)


@app.command()
def query(
    text: Annotated[str | None, typer.Argument(help="Query text. Omit to read from stdin.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON instead of plain text")] = False,
    files: Annotated[bool, typer.Option("--files", "--file", is_eager=False, help="Output deduplicated source filenames instead of chunk content")] = False,
) -> None:
    """Embed a query and retrieve the top-k matching chunks.

    Query text can be supplied as an argument or piped / redirected via stdin:

        perag query "short question"
        perag query < long_query.txt
        cat notes.txt | perag query
    """
    if json_output and files:
        err.print("[red]Error:[/red] --json and --files are mutually exclusive")
        raise typer.Exit(1)

    if text is None:
        if sys.stdin.isatty():
            err.print("[red]Error:[/red] provide query text as an argument or pipe it via stdin.")
            err.print("  Example: perag query \"what is the notice period?\"")
            err.print("           perag query < query.txt")
            raise typer.Exit(1)
        text = sys.stdin.read().strip()
        if not text:
            err.print("[red]Error:[/red] stdin was empty — nothing to query.")
            raise typer.Exit(1)

    cfg = load_config()
    db_path = find_db_path()

    if not db_path.exists():
        err.print(f"[red]Error:[/red] no database found at {db_path}. Run `perag ingest` first.")
        _log.warning("query: no database at %s", db_path)
        raise typer.Exit(1)

    _log.info("query: %d chars", len(text))
    _log.debug("query: text=%r", text)

    from perag.embedders.registry import get_embedder
    from perag.db.store import init_db
    from perag.db.search import search
    from perag.spinner import spinner

    embedder = get_embedder(cfg.embedding)

    vector: list[float] | None = None
    use_daemon = cfg.embedding.provider == "local" and cfg.embedding.daemon
    if use_daemon:
        from perag.config import find_perag_dir
        from perag.daemon_client import try_embed
        perag_dir = find_perag_dir()
        with spinner("Embedding via daemon"):
            result = try_embed(
                perag_dir, cfg.embedding.model, cfg.embedding.batch_size,
                cfg.embedding.daemon_ack_timeout, cfg.embedding.daemon_idle_timeout,
                [text], err.print,
            )
        if result:
            vector = result[0]

    if vector is None:
        if embedder.needs_preload:
            cached = not (hasattr(embedder, "is_model_cached") and not embedder.is_model_cached())
            msg = (
                f"Loading model {cfg.embedding.model}"
                if cached
                else f"Downloading model {cfg.embedding.model} (~90 MB, first use only)"
            )
            try:
                with spinner(msg):
                    embedder.preload()
            except RuntimeError as e:
                err.print(f"[red]Error:[/red] {e}")
                _log.error("query: model load failed: %s", e)
                raise typer.Exit(1)
        try:
            vector = embedder.embed([text])[0]
        except RuntimeError as e:
            err.print(f"[red]Error:[/red] {e}")
            _log.error("query: embedding failed: %s", e)
            raise typer.Exit(1)

    top_k = cfg.query.top_k * 4 if files else cfg.query.top_k

    try:
        conn = init_db(db_path)
    except RuntimeError as e:
        err.print(f"[red]Error:[/red] {e}")
        _log.warning("query: db init failed: %s", e)
        raise typer.Exit(1)
    try:
        results = search(conn, vector, top_k=top_k)
    finally:
        conn.close()

    _log.info("query: %d result(s)", len(results))
    if not results:
        err.print("[yellow]No results found.[/yellow]")
        return

    if files:
        counts: dict[str, int] = {}
        for c in results:
            counts[c.source] = counts.get(c.source, 0) + 1
        ranked = sorted(counts.items(), key=lambda x: -x[1])
        if sys.stdout.isatty():
            from rich.console import Console as RichConsole
            from rich.table import Table
            out = RichConsole()
            table = Table(show_header=True, header_style="bold", box=None, pad_edge=False, show_edge=False)
            table.add_column("Chunks", width=7, justify="right", style="dim")
            table.add_column("File")
            for source, count in ranked:
                table.add_row(str(count), source)
            out.print(table)
        else:
            for source, _ in ranked:
                print(source)
    elif json_output or cfg.query.output == "json":
        print(json.dumps([c.to_dict() for c in results], ensure_ascii=False))
    else:
        parts = []
        for c in results:
            meta = c.metadata
            header_parts = [c.source]
            if "page" in meta:
                header_parts.append(f"page {meta['page']}")
            if "section" in meta and meta["section"]:
                header_parts.append(f"section: {meta['section']}")
            header = f"# {', '.join(header_parts)}"
            parts.append(f"{header}\n{c.content}")
        print("\n\n".join(parts))
