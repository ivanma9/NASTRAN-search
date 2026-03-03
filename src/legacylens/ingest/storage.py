"""ChromaDB storage for embedded FORTRAN chunks."""

import json
import logging

import chromadb

from legacylens.config import get_settings
from legacylens.ingest.chunker import FortranChunk

logger = logging.getLogger(__name__)


def _get_collection(collection_name: str | None = None, persist_dir: str | None = None):
    settings = get_settings()
    path = persist_dir or settings.chromadb_path
    name = collection_name or settings.collection_name
    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(name=name)


def _chunk_id(chunk: FortranChunk) -> str:
    return f"{chunk.file_path}:{chunk.line_start}"


def store_chunks(
    chunks_with_embeddings: list[tuple[FortranChunk, list[float]]],
    collection_name: str | None = None,
    persist_dir: str | None = None,
) -> int:
    """Store embedded chunks in ChromaDB. Returns count of newly stored chunks."""
    collection = _get_collection(collection_name, persist_dir)

    # Get existing IDs for resumability
    existing_ids = set()
    if collection.count() > 0:
        all_existing = collection.get()
        existing_ids = set(all_existing["ids"])

    new_count = 0
    batch_ids = []
    batch_docs = []
    batch_embeddings = []
    batch_metadatas = []

    for chunk, embedding in chunks_with_embeddings:
        chunk_id = _chunk_id(chunk)
        if chunk_id in existing_ids:
            continue

        metadata = {
            "unit_name": chunk.unit_name,
            "unit_type": chunk.unit_type,
            "file_path": chunk.file_path,
            "line_start": chunk.line_start,
            "line_end": chunk.line_end,
            "common_blocks": json.dumps(chunk.common_blocks),
            "calls": json.dumps(chunk.calls),
            "entry_points": json.dumps(chunk.entry_points),
            "includes": json.dumps(chunk.includes),
            "externals": json.dumps(chunk.externals),
            "comment_ratio": chunk.comment_ratio,
            "token_count": chunk.token_count,
        }

        batch_ids.append(chunk_id)
        batch_docs.append(chunk.text)
        batch_embeddings.append(embedding)
        batch_metadatas.append(metadata)

        # ChromaDB batch limit
        if len(batch_ids) >= 500:
            collection.add(
                ids=batch_ids,
                documents=batch_docs,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
            )
            new_count += len(batch_ids)
            batch_ids, batch_docs, batch_embeddings, batch_metadatas = [], [], [], []

    # Flush remaining
    if batch_ids:
        collection.add(
            ids=batch_ids,
            documents=batch_docs,
            embeddings=batch_embeddings,
            metadatas=batch_metadatas,
        )
        new_count += len(batch_ids)

    logger.info(f"Stored {new_count} new chunks (total in collection: {collection.count()})")
    return new_count
