"""LegacyLens CLI — Typer app with Rich rendering."""

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown

app = typer.Typer(help="LegacyLens — RAG pipeline for legacy FORTRAN codebases")
console = Console()


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="Path to NASTRAN-95 source directory"),
    subset: str | None = typer.Option(None, help="Subdirectory to scope ingestion"),
    skip_embedding: bool = typer.Option(False, "--skip-embedding", help="Skip embedding and storage"),
):
    """Ingest FORTRAN source files into ChromaDB."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from legacylens.ingest.pipeline import run_ingestion

    chunks = run_ingestion(path, subset=subset, skip_embedding=skip_embedding)

    if not skip_embedding and chunks:
        # Build indices
        console.print("\n[blue]Building cross-reference indices...[/blue]")
        from legacylens.index.call_graph import build_call_graph, save_index as save_cg
        from legacylens.index.common_blocks import build_common_block_index, save_index as save_cb

        cb_index = build_common_block_index(chunks)
        save_cb(cb_index)
        console.print(f"  COMMON block index: {len(cb_index)} blocks")

        cg_index = build_call_graph(chunks)
        save_cg(cg_index)
        console.print(f"  Call graph: {len(cg_index)} nodes")

    console.print("\n[bold green]Ingestion complete![/bold green]")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Natural language question about the codebase"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of chunks to retrieve"),
):
    """Ask a question about the NASTRAN-95 codebase."""
    logging.basicConfig(level=logging.WARNING)

    from legacylens.search.context import assemble_context
    from legacylens.search.generator import generate_answer
    from legacylens.search.retriever import retrieve

    console.print(f"\n[blue]Searching for relevant code...[/blue]")
    results = retrieve(question, top_k=top_k)

    if not results:
        console.print("[red]No results found. Have you run 'legacylens ingest' first?[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Found {len(results)} relevant chunks[/green]\n")

    # Show source references
    console.print("[bold]Sources:[/bold]")
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        console.print(
            f"  {i}. {meta.get('unit_type', '').upper()} {meta.get('unit_name', '?')} "
            f"— {meta.get('file_path', '?')}:{meta.get('line_start', '?')}-{meta.get('line_end', '?')}"
        )

    # Generate answer
    console.print(f"\n[blue]Generating answer...[/blue]\n")
    context = assemble_context(results)
    answer = generate_answer(question, context)

    console.print(Markdown(answer))


@app.command()
def stats():
    """Print index statistics."""
    import json

    import chromadb

    from legacylens.config import get_settings

    settings = get_settings()

    # ChromaDB stats
    try:
        client = chromadb.PersistentClient(path=settings.chromadb_path)
        collection = client.get_collection(name=settings.collection_name)
        count = collection.count()
        console.print(f"[bold]ChromaDB Index[/bold]")
        console.print(f"  Collection: {settings.collection_name}")
        console.print(f"  Chunks: {count}")

        # Sample metadata
        if count > 0:
            sample = collection.peek(5)
            unit_types = set()
            for meta in sample["metadatas"]:
                if meta.get("unit_type"):
                    unit_types.add(meta["unit_type"])
            if unit_types:
                console.print(f"  Unit types: {', '.join(sorted(unit_types))}")
    except Exception as e:
        console.print(f"[red]ChromaDB not available: {e}[/red]")

    # Index stats
    cb_path = Path("data/indices/common_blocks.json")
    cg_path = Path("data/indices/call_graph.json")

    if cb_path.exists():
        cb = json.loads(cb_path.read_text())
        console.print(f"\n[bold]COMMON Block Index[/bold]")
        console.print(f"  Blocks: {len(cb)}")
    else:
        console.print("\n[yellow]COMMON block index not built yet[/yellow]")

    if cg_path.exists():
        cg = json.loads(cg_path.read_text())
        console.print(f"\n[bold]Call Graph[/bold]")
        console.print(f"  Nodes: {len(cg)}")
        has_callers = sum(1 for v in cg.values() if v.get("called_by"))
        console.print(f"  Nodes with callers: {has_callers}")
    else:
        console.print("\n[yellow]Call graph not built yet[/yellow]")


if __name__ == "__main__":
    app()
