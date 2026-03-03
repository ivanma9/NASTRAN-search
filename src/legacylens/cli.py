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

    # Show source references with relevance scores
    console.print("[bold]Sources:[/bold]")
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        score = r.get("score", 0)
        score_str = f" (score: {score:.4f})" if score else ""
        console.print(
            f"  {i}. {meta.get('unit_type', '').upper()} {meta.get('unit_name', '?')} "
            f"— {meta.get('file_path', '?')}:{meta.get('line_start', '?')}-{meta.get('line_end', '?')}"
            f"{score_str}"
        )

    # Generate answer
    console.print(f"\n[blue]Generating answer...[/blue]\n")
    context = assemble_context(results)
    answer = generate_answer(question, context)

    console.print(Markdown(answer))


@app.command()
def validate(
    sample_size: int = typer.Option(10, "--sample", "-n", help="Number of chunks to spot-check"),
):
    """Spot-check stored chunks for quality and metadata completeness."""
    import json
    import random

    import chromadb

    from legacylens.config import get_settings

    settings = get_settings()

    try:
        client = chromadb.PersistentClient(path=settings.chromadb_path)
        collection = client.get_collection(name=settings.collection_name)
    except Exception as e:
        console.print(f"[red]Cannot access ChromaDB: {e}[/red]")
        raise typer.Exit(1)

    total = collection.count()
    if total == 0:
        console.print("[red]No chunks found. Run 'legacylens ingest' first.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Validating {sample_size} of {total} chunks...[/bold]\n")

    # Fetch a random sample
    all_data = collection.get(include=["documents", "metadatas"])
    indices = random.sample(range(len(all_data["ids"])), min(sample_size, len(all_data["ids"])))

    issues = []
    for idx in indices:
        chunk_id = all_data["ids"][idx]
        doc = all_data["documents"][idx]
        meta = all_data["metadatas"][idx]

        chunk_issues = []

        # Check document quality
        if not doc or len(doc.strip()) < 10:
            chunk_issues.append("Document text too short or empty")
        if doc and ord(doc[0]) < 32 and doc[0] != "\n":
            chunk_issues.append(f"Starts with control character (0x{ord(doc[0]):02x})")

        # Check metadata completeness
        required_fields = ["unit_name", "unit_type", "file_path", "line_start", "line_end"]
        for field in required_fields:
            if field not in meta or meta[field] in (None, ""):
                chunk_issues.append(f"Missing metadata: {field}")

        # Check file_path exists
        if meta.get("file_path"):
            from pathlib import Path

            if not Path(meta["file_path"]).exists():
                chunk_issues.append(f"File not found: {meta['file_path']}")

        # Check line numbers are valid
        if meta.get("line_start") and meta.get("line_end"):
            if meta["line_start"] > meta["line_end"]:
                chunk_issues.append(f"Invalid line range: {meta['line_start']}-{meta['line_end']}")

        # Check JSON-encoded list fields are valid
        for list_field in ["common_blocks", "calls", "entry_points", "includes", "externals"]:
            val = meta.get(list_field)
            if val:
                try:
                    parsed = json.loads(val)
                    if not isinstance(parsed, list):
                        chunk_issues.append(f"{list_field} is not a JSON list")
                except json.JSONDecodeError:
                    chunk_issues.append(f"{list_field} is invalid JSON")

        if chunk_issues:
            issues.append((chunk_id, chunk_issues))
            console.print(f"[red]FAIL[/red] {chunk_id}")
            for issue in chunk_issues:
                console.print(f"      {issue}")
        else:
            unit_info = f"{meta.get('unit_type', '').upper()} {meta.get('unit_name', '?')}"
            console.print(f"[green]OK[/green]   {chunk_id} — {unit_info}")

    console.print()
    if issues:
        console.print(f"[red]{len(issues)}/{len(indices)} chunks have issues[/red]")
        raise typer.Exit(1)
    else:
        console.print(f"[green]All {len(indices)} sampled chunks passed validation![/green]")


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
