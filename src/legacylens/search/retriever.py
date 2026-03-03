"""Vector search + index-augmented retrieval."""

import json
import logging
import re

import chromadb
import voyageai

from legacylens.config import get_settings
from legacylens.index.call_graph import load_index as load_call_graph
from legacylens.index.common_blocks import load_index as load_common_index
from legacylens.index.common_blocks import lookup_common_block

logger = logging.getLogger(__name__)

# Pattern to detect COMMON block or subroutine names in queries
COMMON_BLOCK_RE = re.compile(r"(?:COMMON\s+(?:block\s+)?)?/(\w+)/", re.IGNORECASE)
SUBROUTINE_RE = re.compile(r"\b(?:subroutine|function|program)\s+(\w+)\b", re.IGNORECASE)
UNIT_NAME_RE = re.compile(r"\b([A-Z][A-Z0-9]{2,})\b")

# ChromaDB returns cosine distance (0 = identical, 2 = opposite).
# Discard results with distance above this threshold (low relevance).
MAX_DISTANCE_THRESHOLD = 1.2


def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """Retrieve relevant chunks for a query.

    Uses vector similarity search augmented with index lookups when the query
    mentions specific COMMON blocks or subroutine names.
    Filters out results below a minimum relevance threshold.

    Returns:
        List of dicts with keys: text, metadata, score, index_context
    """
    settings = get_settings()
    k = top_k or settings.top_k

    # Embed query
    client = voyageai.Client(api_key=settings.voyage_api_key)
    response = client.embed([query], model=settings.embedding_model, input_type="query")
    query_embedding = response.embeddings[0]

    # ChromaDB search
    chroma_client = chromadb.PersistentClient(path=settings.chromadb_path)
    collection = chroma_client.get_collection(name=settings.collection_name)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
    )

    # Build result list
    retrieved = []
    for i in range(len(results["ids"][0])):
        metadata = results["metadatas"][0][i]
        # Decode JSON-encoded list fields
        for field in ("common_blocks", "calls", "entry_points", "includes", "externals"):
            if field in metadata and isinstance(metadata[field], str):
                try:
                    metadata[field] = json.loads(metadata[field])
                except (json.JSONDecodeError, TypeError):
                    pass

        retrieved.append({
            "text": results["documents"][0][i],
            "metadata": metadata,
            "score": results["distances"][0][i] if results["distances"] else 0,
            "index_context": "",
        })

    # Index-augmented retrieval
    _augment_with_indices(query, retrieved)

    return retrieved


def _augment_with_indices(query: str, results: list[dict]) -> None:
    """Augment results with cross-reference index data."""
    try:
        common_index = load_common_index()
        call_graph = load_call_graph()
    except Exception:
        return  # Indices not available yet

    if not common_index and not call_graph:
        return

    # Check if query mentions a COMMON block
    common_match = COMMON_BLOCK_RE.search(query)
    if common_match:
        block_name = f"/{common_match.group(1).upper()}/"
        refs = lookup_common_block(block_name, common_index)
        if refs:
            context = f"COMMON block {block_name} is referenced by: "
            context += ", ".join(f"{r['unit']} ({r['file']}:{r['line']})" for r in refs[:10])
            for r in results:
                r["index_context"] += context + "\n"

    # Check if query mentions a subroutine name
    sub_match = SUBROUTINE_RE.search(query)
    if sub_match and call_graph:
        name = sub_match.group(1).upper()
        entry = call_graph.get(name, {})
        if entry:
            parts = []
            if entry.get("calls"):
                parts.append(f"{name} calls: {', '.join(entry['calls'][:10])}")
            if entry.get("called_by"):
                parts.append(f"{name} is called by: {', '.join(entry['called_by'][:10])}")
            if parts:
                for r in results:
                    r["index_context"] += "\n".join(parts) + "\n"

    # Also augment each result with its own COMMON block / call relationships
    for r in results:
        meta = r["metadata"]
        parts = []
        if meta.get("common_blocks") and isinstance(meta["common_blocks"], list):
            for block in meta["common_blocks"]:
                refs = lookup_common_block(block, common_index)
                other_units = [ref["unit"] for ref in refs if ref["unit"] != meta.get("unit_name")]
                if other_units:
                    parts.append(f"Shares COMMON {block} with: {', '.join(other_units[:5])}")
        if meta.get("unit_name") and call_graph:
            entry = call_graph.get(meta["unit_name"], {})
            if entry.get("called_by"):
                parts.append(f"Called by: {', '.join(entry['called_by'][:5])}")
        if parts:
            r["index_context"] += "\n".join(parts)
