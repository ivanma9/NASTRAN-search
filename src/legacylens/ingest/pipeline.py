"""Ingestion pipeline orchestrator."""

import logging
from pathlib import Path

from rich.console import Console

from legacylens.ingest.chunker import FortranChunk, chunk_fortran
from legacylens.ingest.discovery import discover_fortran_files
from legacylens.ingest.embedder import embed_chunks
from legacylens.ingest.metadata import extract_metadata
from legacylens.ingest.preprocess import preprocess_fixed_form
from legacylens.ingest.storage import store_chunks

logger = logging.getLogger(__name__)
console = Console()


def run_ingestion(
    source_dir: Path,
    subset: str | None = None,
    skip_embedding: bool = False,
) -> list[FortranChunk]:
    """Run the full ingestion pipeline.

    Args:
        source_dir: Root directory containing FORTRAN source files
        subset: Optional subdirectory to scope ingestion (e.g., "bd")
        skip_embedding: If True, skip embedding and storage (for testing)

    Returns:
        List of all FortranChunk objects created
    """
    # Discovery
    search_dir = source_dir / subset if subset else source_dir
    files = discover_fortran_files(search_dir)
    if not files:
        console.print(f"[red]No FORTRAN files found in {search_dir}[/red]")
        return []

    console.print(f"[green]Found {len(files)} FORTRAN files[/green]")

    # Process each file
    all_chunks: list[FortranChunk] = []
    skipped_files: list[tuple[Path, str]] = []
    total_tokens = 0

    for file_path in files:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            preprocessed, line_map = preprocess_fixed_form(text)
            chunks = chunk_fortran(preprocessed, str(file_path), line_map)

            for chunk in chunks:
                extract_metadata(chunk)
                total_tokens += chunk.token_count

            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning(f"Failed to process {file_path}: {e}")
            skipped_files.append((file_path, str(e)))

    console.print(f"\n[bold]Ingestion Summary[/bold]")
    console.print(f"  Files processed: {len(files) - len(skipped_files)}/{len(files)}")
    console.print(f"  Chunks created:  {len(all_chunks)}")
    console.print(f"  Total tokens:    {total_tokens:,}")

    if skipped_files:
        console.print(f"\n[yellow]Skipped {len(skipped_files)} files:[/yellow]")
        for path, err in skipped_files:
            console.print(f"  {path}: {err}")

    if skip_embedding:
        console.print("[yellow]Skipping embedding and storage (--skip-embedding)[/yellow]")
        return all_chunks

    # Embedding
    console.print(f"\n[blue]Embedding {len(all_chunks)} chunks...[/blue]")
    embedded = embed_chunks(all_chunks)
    console.print(f"[green]Embedded {len(embedded)} chunks[/green]")

    # Storage
    console.print("[blue]Storing in ChromaDB...[/blue]")
    new_count = store_chunks(embedded)
    console.print(f"[green]Stored {new_count} new chunks[/green]")

    # Cost estimate (Voyage code-3: ~$0.06/1M tokens)
    cost = total_tokens * 0.06 / 1_000_000
    console.print(f"\n  Estimated embedding cost: ${cost:.4f}")

    return all_chunks
