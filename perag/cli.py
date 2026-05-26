import json
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from perag.config import find_db_path, load_config
from perag.schema import Chunk

_VERSION = _pkg_version("perag")

app = typer.Typer(help=f"perag — personal RAG toolkit  (version {_VERSION})")
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
    pass


@app.command()
def chunk(
    file: Annotated[Path, typer.Argument(help="Document to chunk")],
) -> None:
    """Chunk a document and write JSON to stdout."""
    if not file.exists():
        err.print(f"[red]Error:[/red] file not found: {file}")
        raise typer.Exit(1)

    from chunkers.registry import get_chunker
    try:
        chunker = get_chunker(file)
        chunks = chunker.chunk(file)
    except ValueError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    print(json.dumps([c.to_dict() for c in chunks], ensure_ascii=False))


@app.command()
def embed() -> None:
    """Read chunks from stdin, add embeddings, write JSON to stdout."""
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        err.print(f"[red]Error:[/red] invalid JSON on stdin: {e}")
        raise typer.Exit(1)

    chunks = [Chunk.from_dict(d) for d in raw]
    if not chunks:
        print("[]")
        return

    cfg = load_config()
    from embedders.registry import get_embedder
    embedder = get_embedder(cfg.embedding)

    to_embed_idx = []
    to_embed_texts = []

    for i, c in enumerate(chunks):
        if c.embedding_model is None:
            to_embed_idx.append(i)
            to_embed_texts.append(c.content)
        elif c.embedding_model != embedder.model_name:
            to_embed_idx.append(i)
            to_embed_texts.append(c.content)
        # else: already embedded with current model — pass through

    if to_embed_texts:
        batch_size = cfg.embedding.batch_size
        all_vectors: list[list[float]] = []
        for i in range(0, len(to_embed_texts), batch_size):
            batch = to_embed_texts[i : i + batch_size]
            all_vectors.extend(embedder.embed(batch))

        for list_idx, chunk_idx in enumerate(to_embed_idx):
            chunks[chunk_idx].embedding_model = embedder.model_name
            chunks[chunk_idx].embedding_provider = embedder.provider_name
            chunks[chunk_idx].vector = all_vectors[list_idx]

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
        return

    from db.store import init_db, ingest as db_ingest
    db_path = find_db_path()
    conn = init_db(db_path)
    try:
        db_ingest(conn, chunks)
    except ValueError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()

    err.print(f"[green]Ingested[/green] {len(chunks)} chunks into {db_path}")


@app.command(name="init")
def init_cmd() -> None:
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
            example = Path(__file__).parent.parent / "config.example.toml"
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
    skill_src = importlib.resources.files("perag.data").joinpath("SKILL.md")
    with importlib.resources.as_file(skill_src) as src:
        shutil.copy(src, skill_dest)
    err.print(f"[green]Installed[/green] Claude Code skill → {skill_dest}")

    err.print(f"[green]Done.[/green] Database will be created at {perag_dir / 'perag.db'} on first ingest.")


@app.command()
def query(
    text: Annotated[str, typer.Argument(help="Query text")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON instead of plain text")] = False,
) -> None:
    """Embed a query and retrieve the top-k matching chunks."""
    cfg = load_config()
    db_path = find_db_path()

    if not db_path.exists():
        err.print(f"[red]Error:[/red] no database found at {db_path}. Run `perag ingest` first.")
        raise typer.Exit(1)

    from embedders.registry import get_embedder
    from db.store import init_db
    from db.search import search

    embedder = get_embedder(cfg.embedding)
    vector = embedder.embed([text])[0]

    conn = init_db(db_path)
    try:
        results = search(conn, vector, top_k=cfg.query.top_k)
    finally:
        conn.close()

    if not results:
        err.print("[yellow]No results found.[/yellow]")
        return

    if json_output or cfg.query.output == "json":
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
